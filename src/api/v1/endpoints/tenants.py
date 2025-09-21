"""Endpoints for managing tenants (bootstrap utilities)."""
from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session
from src.db.models.tenant import Tenant
from src.repositories.plan_repo import PlanRepo
from src.repositories.subscription_repo import SubscriptionRepo


router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("/create")
async def create_tenant(
    name: str,
    plan_id: str = "hobby",
    billing_cycle: str = "monthly",
    db: AsyncSession = Depends(get_db_session),
):
    if billing_cycle not in {"monthly", "annual"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid billing cycle",
        )

    plan_repo = PlanRepo(db)
    plan = await plan_repo.get(plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    tenant = Tenant(
        name=name,
        plan=plan.id,
        plan_messages=plan.monthly_message_cap,
    )
    db.add(tenant)
    await db.flush()

    start = date.today()
    delta = relativedelta(months=1) if billing_cycle == "monthly" else relativedelta(years=1)
    end = start + delta

    subscription_repo = SubscriptionRepo(db)
    subscription = await subscription_repo.upsert(
        tenant.id, plan.id, billing_cycle, start, end
    )

    return {
        "tenant_id": str(tenant.id),
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
