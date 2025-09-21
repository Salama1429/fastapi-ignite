"""Endpoints for ingesting content into OpenAI vector stores."""
from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session
from src.auth.jwt import require_auth
from src.repositories.project_repo import ProjectRepo
from src.repositories.subscription_repo import SubscriptionRepo
from src.repositories.usage_repo import UsageRepo
from src.services.openai_service import (
    attach_files_batch,
    create_vector_store,
    list_vector_store_files,
    remove_file_from_store,
    upload_files_to_openai,
)
from src.services.limits import check_rate_limit


router = APIRouter(prefix="/ingestion", tags=["ingestion"])


def _parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:  # pragma: no cover - FastAPI validation handles in tests
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name}",
        ) from exc


def _project_response(project, status_flag: str):
    return {
        "id": str(project.id),
        "tenant_id": str(project.tenant_id),
        "name": project.name,
        "vector_store_id": project.vector_store_id,
        "status": status_flag,
    }


@router.post("/projects/create")
async def create_project(
    tenant_id: str,
    name: str,
    auth=Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
):
    tenant_uuid = _parse_uuid(tenant_id, "tenant_id")
    if auth["tenant_id"] != tenant_uuid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch",
        )
    await check_rate_limit(str(tenant_uuid))
    repo = ProjectRepo(db)
    subscription_repo = SubscriptionRepo(db)
    subscription = await subscription_repo.get_with_plan(tenant_uuid)
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active subscription",
        )

    existing = await repo.get_by_tenant_and_name(tenant_uuid, name)
    if existing:
        return _project_response(existing, "exists")

    plan = subscription.plan
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Subscription plan data missing",
        )

    max_projects = plan.max_projects
    current_projects = await repo.count_for_tenant(tenant_uuid)
    if current_projects >= max_projects:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Project limit reached for your plan. Upgrade to add more chatbots.",
        )

    project = await repo.create(tenant_uuid, name)
    return _project_response(project, "created")


@router.post("/projects/{project_id}/ensure_vector_store")
async def ensure_vector_store(
    tenant_id: str,
    project_id: str,
    auth=Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
):
    tenant_uuid = _parse_uuid(tenant_id, "tenant_id")
    project_uuid = _parse_uuid(project_id, "project_id")

    if auth["tenant_id"] != tenant_uuid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch",
        )
    await check_rate_limit(str(tenant_uuid))

    repo = ProjectRepo(db)
    project = await repo.get_by_id(project_uuid)
    if not project or project.tenant_id != tenant_uuid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if project.vector_store_id:
        return {
            "project_id": str(project.id),
            "vector_store_id": project.vector_store_id,
            "status": "exists",
        }

    vector_store_id = create_vector_store(name=f"proj_{project.id}")
    await repo.set_vector_store_id(project, vector_store_id)
    return {
        "project_id": str(project.id),
        "vector_store_id": vector_store_id,
        "status": "created",
    }


@router.post("/projects/{project_id}/upload_and_attach")
async def upload_and_attach(
    tenant_id: str,
    project_id: str,
    files: List[UploadFile] = File(...),
    auth=Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
):
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided")

    tenant_uuid = _parse_uuid(tenant_id, "tenant_id")
    project_uuid = _parse_uuid(project_id, "project_id")

    if auth["tenant_id"] != tenant_uuid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch",
        )
    await check_rate_limit(str(tenant_uuid))

    repo = ProjectRepo(db)
    project = await repo.get_by_id(project_uuid)
    if not project or project.tenant_id != tenant_uuid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if not project.vector_store_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vector store missing. Call ensure_vector_store first.",
        )

    payload: List[tuple[str, bytes, str]] = []
    total_chars = 0
    for upload in files:
        file_bytes = await upload.read()
        await upload.close()
        try:
            decoded = file_bytes.decode("utf-8", "ignore")
            total_chars += len(decoded)
        except Exception:  # pragma: no cover - defensive fallback
            total_chars += len(file_bytes)
        payload.append(
            (
                upload.filename or "upload.bin",
                file_bytes,
                upload.content_type or "application/octet-stream",
            )
        )

    subscription_repo = SubscriptionRepo(db)
    subscription = await subscription_repo.get_with_plan(tenant_uuid)
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active subscription",
        )
    plan = subscription.plan
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Subscription plan data missing",
        )

    usage_repo = UsageRepo(db)
    already_uploaded = await usage_repo.chars_uploaded_for_project_in_period(
        tenant_uuid,
        project_uuid,
        subscription.current_period_start,
        subscription.current_period_end,
    )
    if already_uploaded + total_chars > plan.monthly_upload_char_cap:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Upload character cap exceeded for this billing period. Upgrade your plan.",
        )

    uploaded_ids = upload_files_to_openai(payload)
    batch = attach_files_batch(project.vector_store_id, uploaded_ids)

    file_counts = getattr(batch, "file_counts", None)
    if hasattr(file_counts, "model_dump"):
        file_counts = file_counts.model_dump()

    if total_chars:
        await usage_repo.record_upload_chars(tenant_uuid, project_uuid, total_chars)

    return {
        "project_id": str(project.id),
        "vector_store_id": project.vector_store_id,
        "batch_status": getattr(batch, "status", None),
        "file_counts": file_counts,
    }


@router.get("/projects/{project_id}/files")
async def list_files(
    tenant_id: str,
    project_id: str,
    auth=Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
):
    tenant_uuid = _parse_uuid(tenant_id, "tenant_id")
    project_uuid = _parse_uuid(project_id, "project_id")

    if auth["tenant_id"] != tenant_uuid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch",
        )
    await check_rate_limit(str(tenant_uuid))
    repo = ProjectRepo(db)
    project = await repo.get_by_id(project_uuid)
    if not project or project.tenant_id != tenant_uuid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if not project.vector_store_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vector store missing")

    files = list_vector_store_files(project.vector_store_id)
    serialized_files = []
    for entry in files:
        if hasattr(entry, "model_dump"):
            serialized_files.append(entry.model_dump())
        elif hasattr(entry, "to_dict"):
            serialized_files.append(entry.to_dict())
        elif hasattr(entry, "__dict__"):
            serialized_files.append(
                {k: v for k, v in entry.__dict__.items() if not k.startswith("_")}
            )
        else:  # pragma: no cover - fallback for unexpected SDK shapes
            serialized_files.append(entry)

    return {
        "project_id": str(project.id),
        "vector_store_id": project.vector_store_id,
        "files": serialized_files,
    }


@router.delete("/projects/{project_id}/remove_file")
async def remove_file(
    tenant_id: str,
    project_id: str,
    openai_file_id: str,
    delete_raw: bool = False,
    auth=Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
):
    tenant_uuid = _parse_uuid(tenant_id, "tenant_id")
    project_uuid = _parse_uuid(project_id, "project_id")

    if auth["tenant_id"] != tenant_uuid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch",
        )
    await check_rate_limit(str(tenant_uuid))
    repo = ProjectRepo(db)
    project = await repo.get_by_id(project_uuid)
    if not project or project.tenant_id != tenant_uuid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if not project.vector_store_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vector store missing")

    remove_file_from_store(project.vector_store_id, openai_file_id, delete_raw=delete_raw)
    return {
        "project_id": str(project.id),
        "vector_store_id": project.vector_store_id,
        "removed_file_id": openai_file_id,
        "delete_raw": delete_raw,
    }
