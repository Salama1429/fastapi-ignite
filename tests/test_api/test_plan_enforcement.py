from __future__ import annotations

import datetime as dt
from typing import Dict, List, Tuple
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
import pytest_asyncio
from fastapi import status
from sqlalchemy import select

from src.core.config import settings
from src.db.models.message import Message
from src.db.models.plan import Plan
from src.db.models.project import Project
from src.db.models.subscription import Subscription
from src.db.models.tenant import Tenant
from src.services import limits as limits_service


# Ensure the application under test avoids external dependencies.
settings.ENV = "test"
settings.scheduler.enabled = False
settings.cache.backend_type = "memory"
settings.DATABASE_URI = "sqlite+aiosqlite:///./test_app.db"
API_PREFIX = f"{settings.API_PREFIX}/v1"


class FakeRedis:
    """Minimal async Redis stub for rate limiting and idempotency tests."""

    def __init__(self) -> None:
        self.store: Dict[str, int | str] = {}

    async def incr(self, key: str) -> int:
        current = int(self.store.get(key, 0)) + 1
        self.store[key] = current
        return current

    async def expire(self, key: str, seconds: int) -> None:
        # Track expiry for introspection if desired
        self.store.setdefault(f"{key}:ttl", seconds)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> bool:
        if nx and key in self.store:
            return False
        self.store[key] = value
        if ex is not None:
            self.store[f"{key}:ttl"] = ex
        return True


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedis:
    """Patch the limits module to use an in-memory Redis stub."""

    fake = FakeRedis()
    monkeypatch.setattr(limits_service, "_redis_client", fake, raising=False)
    yield fake
    monkeypatch.setattr(limits_service, "_redis_client", None, raising=False)


def build_auth_header(tenant_id: UUID) -> Dict[str, str]:
    token = jwt.encode({"tenant_id": str(tenant_id)}, settings.JWT_SECRET, algorithm=settings.JWT_ALG)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def client(test_app):
    """Provide an HTTPX client compatible with httpx>=0.28."""

    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.fixture(autouse=True)
def patch_increment_message(monkeypatch):
    async def _noop(self, tenant_id, project_id, tokens_in, tokens_out):
        return None

    monkeypatch.setattr(
        "src.repositories.usage_repo.UsageRepo.increment_message",
        _noop,
    )


async def seed_plan_subscription(
    session,
    *,
    tenant_id: UUID | None = None,
    plan_id: str | None = None,
    max_projects: int = 5,
    message_cap: int = 100,
    upload_cap: int = 1_000_000,
) -> Tuple[Tenant, Plan, Subscription]:
    tenant_id = tenant_id or uuid4()
    plan_id = plan_id or f"plan_{uuid4().hex[:6]}"

    plan = Plan(
        id=plan_id,
        name="Test",
        max_projects=max_projects,
        monthly_message_cap=message_cap,
        monthly_upload_char_cap=upload_cap,
        is_annual_available=True,
    )
    tenant = Tenant(id=tenant_id, name="Tenant", plan=plan_id, plan_messages=message_cap)
    start = dt.date.today()
    end = start + dt.timedelta(days=30)
    subscription = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_id,
        billing_cycle="monthly",
        current_period_start=start,
        current_period_end=end,
    )

    session.add_all([plan, tenant, subscription])
    await session.commit()
    await session.refresh(subscription)
    return tenant, plan, subscription


async def seed_project(session, tenant_id: UUID, name: str = "Project", vector_store_id: str | None = "vs_mock") -> Project:
    project = Project(tenant_id=tenant_id, name=name, vector_store_id=vector_store_id)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@pytest.mark.asyncio
async def test_query_enforces_monthly_message_quota(
    client,
    test_db,
    fake_redis,
    monkeypatch,
):
    tenant, _, subscription = await seed_plan_subscription(
        test_db, message_cap=1, upload_cap=1000
    )
    project = await seed_project(test_db, tenant.id, name="Quota", vector_store_id="vs_quota")

    async def _messages_in_period(_self, _tenant_id, _start, _end):
        return 1

    monkeypatch.setattr(
        "src.repositories.usage_repo.UsageRepo.messages_in_period",
        _messages_in_period,
    )

    def _no_call(*_args, **_kwargs):
        raise AssertionError("OpenAI should not be invoked when over quota")

    monkeypatch.setattr(
        "src.api.v1.endpoints.query.responses_file_search",
        _no_call,
    )

    response = await client.post(
        f"{API_PREFIX}/query/ask",
        json={"project_id": str(project.id), "question": "hello"},
        headers=build_auth_header(tenant.id),
    )

    assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED, response.text
    assert response.json()["message"] == "Monthly message cap reached. Upgrade plan."


@pytest.mark.asyncio
async def test_upload_blocks_when_character_cap_exceeded(
    client,
    test_db,
    fake_redis,
    monkeypatch,
):
    tenant, _, subscription = await seed_plan_subscription(
        test_db, upload_cap=10, message_cap=10
    )
    project = await seed_project(test_db, tenant.id, name="Upload", vector_store_id="vs_upload")

    async def _chars_uploaded_for_project_in_period(
        _self, _tenant_id, _project_id, _start, _end
    ) -> int:
        return 9

    monkeypatch.setattr(
        "src.repositories.usage_repo.UsageRepo.chars_uploaded_for_project_in_period",
        _chars_uploaded_for_project_in_period,
    )

    def _fail_upload(*_args, **_kwargs):
        raise AssertionError("Upload should be blocked before reaching OpenAI")

    monkeypatch.setattr(
        "src.api.v1.endpoints.ingestion.upload_files_to_openai",
        _fail_upload,
    )

    response = await client.post(
        f"{API_PREFIX}/ingestion/projects/{project.id}/upload_and_attach",
        params={"tenant_id": str(tenant.id)},
        files=[("files", ("test.txt", b"hello world", "text/plain"))],
        headers=build_auth_header(tenant.id),
    )

    assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
    assert (
        response.json()["message"]
        == "Upload character cap exceeded for this billing period. Upgrade your plan."
    )


@pytest.mark.asyncio
async def test_create_project_respects_max_project_quota(
    client,
    test_db,
    fake_redis,
):
    tenant, _, _ = await seed_plan_subscription(
        test_db, max_projects=1, message_cap=10, upload_cap=100
    )
    # Existing project consumes the only slot
    await seed_project(test_db, tenant.id, name="Existing", vector_store_id="vs1")

    response = await client.post(
        f"{API_PREFIX}/ingestion/projects/create",
        params={"tenant_id": str(tenant.id), "name": "Another"},
        headers=build_auth_header(tenant.id),
    )

    assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
    assert (
        response.json()["message"]
        == "Project limit reached for your plan. Upgrade to add more chatbots."
    )


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_is_rejected(
    client,
    test_db,
    fake_redis,
    monkeypatch,
):
    tenant, _, _ = await seed_plan_subscription(test_db, message_cap=5, upload_cap=1000)
    project = await seed_project(test_db, tenant.id, name="Idempotent", vector_store_id="vs_idemp")

    call_count = 0

    class DummyResponse:
        def __init__(self) -> None:
            self.output: List = []
            self.usage = type("Usage", (), {"input_tokens": 2, "output_tokens": 3})()

    def _mock_response(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        return "ok", DummyResponse()

    monkeypatch.setattr(
        "src.api.v1.endpoints.query.responses_file_search",
        _mock_response,
    )

    headers = build_auth_header(tenant.id)
    headers["Idempotency-Key"] = "dup-key"

    first = await client.post(
        f"{API_PREFIX}/query/ask",
        json={"project_id": str(project.id), "question": "ping"},
        headers=headers,
    )
    assert first.status_code == status.HTTP_200_OK
    assert call_count == 1

    second = await client.post(
        f"{API_PREFIX}/query/ask",
        json={"project_id": str(project.id), "question": "ping"},
        headers=headers,
    )
    assert second.status_code == status.HTTP_409_CONFLICT
    assert second.json()["message"] == "Duplicate request (idempotency)"
    assert call_count == 1


@pytest.mark.asyncio
async def test_rate_limit_blocks_second_request_within_window(
    client,
    test_db,
    fake_redis,
    monkeypatch,
):
    tenant, _, _ = await seed_plan_subscription(test_db, message_cap=5, upload_cap=1000)
    project = await seed_project(test_db, tenant.id, name="Rate", vector_store_id="vs_rate")

    monkeypatch.setattr(settings.limits, "rate_limit_rpm", 1)

    class DummyResponse:
        def __init__(self) -> None:
            self.output: List = []
            self.usage = type("Usage", (), {"input_tokens": 1, "output_tokens": 1})()

    def _mock_response(*_args, **_kwargs):
        return "ok", DummyResponse()

    monkeypatch.setattr(
        "src.api.v1.endpoints.query.responses_file_search",
        _mock_response,
    )

    headers = build_auth_header(tenant.id)

    first = await client.post(
        f"{API_PREFIX}/query/ask",
        json={"project_id": str(project.id), "question": "hi"},
        headers=headers,
    )
    assert first.status_code == status.HTTP_200_OK

    second = await client.post(
        f"{API_PREFIX}/query/ask",
        json={"project_id": str(project.id), "question": "hi"},
        headers=headers,
    )
    assert second.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert second.json()["message"] == "Rate limit exceeded"


@pytest.mark.asyncio
async def test_tenant_mismatch_returns_forbidden(
    client,
    test_db,
    fake_redis,
):
    tenant, _, _ = await seed_plan_subscription(test_db)
    other_tenant = uuid4()

    response = await client.post(
        f"{API_PREFIX}/ingestion/projects/create",
        params={"tenant_id": str(other_tenant), "name": "Cross"},
        headers=build_auth_header(tenant.id),
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["message"] == "Tenant mismatch"


@pytest.mark.asyncio
async def test_ingestion_to_query_smoke_flow(
    client,
    test_db,
    fake_redis,
    monkeypatch,
):
    tenant, _, _ = await seed_plan_subscription(test_db, max_projects=2, message_cap=5, upload_cap=1000)

    created_vector_names: List[str] = []
    uploaded_payloads: List[Tuple[str, bytes, str]] = []

    def _mock_create_vector_store(name: str) -> str:
        created_vector_names.append(name)
        return "vs_smoke"

    def _mock_upload(files: List[Tuple[str, bytes, str]]) -> List[str]:
        uploaded_payloads.extend(files)
        return ["file_1"]

    class FakeBatch:
        status = "completed"
        file_counts = {"processed": 1}

    class DummyResponse:
        def __init__(self) -> None:
            self.output = []
            self.usage = type("Usage", (), {"input_tokens": 3, "output_tokens": 7})()

    def _mock_responses(*_args, **_kwargs):
        return "Mock answer", DummyResponse()

    monkeypatch.setattr(
        "src.api.v1.endpoints.ingestion.create_vector_store",
        _mock_create_vector_store,
    )
    monkeypatch.setattr(
        "src.api.v1.endpoints.ingestion.upload_files_to_openai",
        _mock_upload,
    )
    monkeypatch.setattr(
        "src.api.v1.endpoints.ingestion.attach_files_batch",
        lambda *_args, **_kwargs: FakeBatch(),
    )
    monkeypatch.setattr(
        "src.api.v1.endpoints.query.responses_file_search",
        _mock_responses,
    )

    headers = build_auth_header(tenant.id)

    create_response = await client.post(
        f"{API_PREFIX}/ingestion/projects/create",
        params={"tenant_id": str(tenant.id), "name": "DocBot"},
        headers=headers,
    )
    assert create_response.status_code == status.HTTP_200_OK
    project_id = create_response.json()["id"]
    assert create_response.json()["status"] == "created"

    ensure_response = await client.post(
        f"{API_PREFIX}/ingestion/projects/{project_id}/ensure_vector_store",
        params={"tenant_id": str(tenant.id)},
        headers=headers,
    )
    assert ensure_response.status_code == status.HTTP_200_OK
    assert ensure_response.json()["vector_store_id"] == "vs_smoke"
    assert created_vector_names

    upload_response = await client.post(
        f"{API_PREFIX}/ingestion/projects/{project_id}/upload_and_attach",
        params={"tenant_id": str(tenant.id)},
        files=[("files", ("notes.txt", b"hello world", "text/plain"))],
        headers=headers,
    )
    assert upload_response.status_code == status.HTTP_200_OK
    assert upload_response.json()["batch_status"] == "completed"
    assert uploaded_payloads and uploaded_payloads[0][0] == "notes.txt"

    query_headers = headers.copy()
    query_headers["Idempotency-Key"] = "smoke-key"
    query_response = await client.post(
        f"{API_PREFIX}/query/ask",
        json={"project_id": project_id, "question": "What was uploaded?"},
        headers=query_headers,
    )
    assert query_response.status_code == status.HTTP_200_OK
    body = query_response.json()
    assert body["answer"] == "Mock answer"
    assert body["tokens_in"] == 3
    assert body["tokens_out"] == 7

    await test_db.commit()
    messages = (
        await test_db.execute(
            select(Message).where(Message.tenant_id == tenant.id)
        )
    ).scalars().all()
    assert any(msg.role == "user" for msg in messages)

