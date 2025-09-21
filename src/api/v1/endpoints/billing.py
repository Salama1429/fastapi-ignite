"""Endpoints for managing tenant subscriptions."""
from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session
from src.auth.jwt import require_auth
from src.repositories.plan_repo import PlanRepo
from src.repositories.subscription_repo import SubscriptionRepo
from src.repositories.tenant_repo import TenantRepo
from src.services.limits import check_rate_limit


router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/subscribe")
async def subscribe(
    plan_id: str,
    cycle: str = "monthly",
    auth=Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
):
    tenant_id = auth["tenant_id"]

    if cycle not in {"monthly", "annual"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid billing cycle",
        )

    await check_rate_limit(str(tenant_id))

    plan_repo = PlanRepo(db)
    plan = await plan_repo.get(plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    start = date.today()
    delta = relativedelta(months=1) if cycle == "monthly" else relativedelta(years=1)
    end = start + delta

    subscription_repo = SubscriptionRepo(db)
    subscription = await subscription_repo.upsert(tenant_id, plan.id, cycle, start, end)

    tenant_repo = TenantRepo(db)
    tenant = await tenant_repo.get(tenant_id)
    if tenant is not None:
        tenant.plan = plan.id
        tenant.plan_messages = plan.monthly_message_cap
        db.add(tenant)
        await db.flush()

    return {
        "status": "ok",
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
    }

