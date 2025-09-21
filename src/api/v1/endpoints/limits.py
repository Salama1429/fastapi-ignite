"""Endpoints exposing current subscription limits and usage."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session
from src.auth.jwt import require_auth
from src.repositories.project_repo import ProjectRepo
from src.repositories.subscription_repo import SubscriptionRepo
from src.repositories.usage_repo import UsageRepo
from src.services.limits import check_rate_limit


router = APIRouter(prefix="/limits", tags=["limits"])


@router.get("/current")
async def current_limits(
    auth=Depends(require_auth), db: AsyncSession = Depends(get_db_session)
):
    tenant_id = auth["tenant_id"]
    await check_rate_limit(str(tenant_id))

    subscription_repo = SubscriptionRepo(db)
    subscription = await subscription_repo.get_with_plan(tenant_id)
    if not subscription:
        return {"subscribed": False}

    plan = subscription.plan
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Subscription plan data missing",
        )

    usage_repo = UsageRepo(db)
    messages_used = await usage_repo.messages_in_period(
        tenant_id,
        subscription.current_period_start,
        subscription.current_period_end,
    )
    chars_uploaded = await usage_repo.chars_uploaded_in_period(
        tenant_id,
        subscription.current_period_start,
        subscription.current_period_end,
    )

    project_repo = ProjectRepo(db)
    project_count = await project_repo.count_for_tenant(tenant_id)

    return {
        "subscribed": True,
        "plan_id": subscription.plan_id,
        "plan_name": plan.name,
        "billing_cycle": subscription.billing_cycle,
        "period_start": str(subscription.current_period_start),
        "period_end": str(subscription.current_period_end),
        "limits": {
            "max_projects": plan.max_projects,
            "monthly_message_cap": plan.monthly_message_cap,
            "monthly_upload_char_cap": plan.monthly_upload_char_cap,
        },
        "usage": {
            "projects": project_count,
            "messages_used": messages_used,
            "chars_uploaded": chars_uploaded,
        },
    }

