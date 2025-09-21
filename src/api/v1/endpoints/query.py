"""Endpoints for querying OpenAI Responses with project-specific context."""
from __future__ import annotations

from typing import Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session
from src.auth.jwt import require_auth
from src.core.config import settings
from src.db.models.message import Message
from src.repositories.project_repo import ProjectRepo
from src.repositories.subscription_repo import SubscriptionRepo
from src.repositories.usage_repo import UsageRepo
from src.services.limits import check_rate_limit, ensure_idempotent
from src.services.openai_service import responses_file_search


router = APIRouter(prefix="/query", tags=["query"])


class AskBody(BaseModel):
    """Payload for the question endpoint."""

    project_id: UUID = Field(..., description="Project identifier")
    question: str = Field(..., description="User question to ask")


def _extract_citations(raw_response: Any) -> List[dict]:
    citations: List[dict] = []
    try:
        output_items = getattr(raw_response, "output", [])
        for item in output_items or []:
            content_list = getattr(item, "content", [])
            for content in content_list or []:
                annotations = getattr(content, "annotations", None) or getattr(
                    content, "text_annotations", None
                )
                for annotation in annotations or []:
                    file_citation = getattr(annotation, "file_citation", None)
                    if file_citation is None:
                        continue
                    if hasattr(file_citation, "model_dump"):
                        citations.append(file_citation.model_dump())
                    else:  # pragma: no cover - fallback for other SDK shapes
                        citations.append(dict(file_citation))
    except Exception:  # pragma: no cover - best-effort parsing
        citations = []
    return citations


def _extract_usage_token(usage_data: Any, key: str) -> int:
    if usage_data is None:
        return 0
    if hasattr(usage_data, key):
        value = getattr(usage_data, key)
    elif isinstance(usage_data, dict):
        value = usage_data.get(key, 0)
    else:  # pragma: no cover - fallback for SDK updates
        value = 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return 0


@router.post("/ask")
async def ask(
    body: AskBody,
    auth=Depends(require_auth),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db_session),
):
    tenant_id = auth["tenant_id"]

    await check_rate_limit(str(tenant_id))
    await ensure_idempotent(str(tenant_id), idempotency_key)

    project_repo = ProjectRepo(db)
    project = await project_repo.get_by_id(body.project_id)
    if not project or project.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    if not project.vector_store_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vector store missing. Ingest files first.",
        )

    usage_repo = UsageRepo(db)
    subscription_repo = SubscriptionRepo(db)
    subscription = await subscription_repo.get_with_plan(tenant_id)
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

    messages_used = await usage_repo.messages_in_period(
        tenant_id,
        subscription.current_period_start,
        subscription.current_period_end,
    )
    if messages_used >= plan.monthly_message_cap:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Monthly message cap reached. Upgrade plan.",
        )

    user_message = Message(
        tenant_id=tenant_id,
        project_id=body.project_id,
        role="user",
        content=body.question,
        idempotency_key=idempotency_key,
    )
    db.add(user_message)
    await db.flush()

    answer, raw_response = responses_file_search(
        [project.vector_store_id], body.question, settings.OPENAI_MODEL_DEFAULT
    )

    usage_data = getattr(raw_response, "usage", None)
    tokens_in = _extract_usage_token(usage_data, "input_tokens")
    tokens_out = _extract_usage_token(usage_data, "output_tokens")

    assistant_message = Message(
        tenant_id=tenant_id,
        project_id=body.project_id,
        role="assistant",
        content=answer,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )
    db.add(assistant_message)

    await usage_repo.increment_message(tenant_id, body.project_id, tokens_in, tokens_out)

    citations = _extract_citations(raw_response)

    return {
        "answer": answer,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "citations": citations,
    }
