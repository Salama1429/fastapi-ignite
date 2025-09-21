"""Repository utilities for tenant subscriptions."""
from __future__ import annotations

import datetime as dt
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.subscription import Subscription


class SubscriptionRepo:
    """Data-access helpers for :class:`Subscription`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_with_plan(self, tenant_id: UUID) -> Subscription | None:
        result = await self.session.execute(
            select(Subscription)
            .options(selectinload(Subscription.plan))
            .where(Subscription.tenant_id == tenant_id)
        )
        return result.scalars().first()

    async def upsert(
        self,
        tenant_id: UUID,
        plan_id: str,
        billing_cycle: str,
        period_start: dt.date,
        period_end: dt.date,
    ) -> Subscription:
        subscription = await self.session.get(Subscription, tenant_id)
        if subscription is None:
            subscription = Subscription(
                tenant_id=tenant_id,
                plan_id=plan_id,
                billing_cycle=billing_cycle,
                current_period_start=period_start,
                current_period_end=period_end,
            )
            self.session.add(subscription)
        else:
            subscription.plan_id = plan_id
            subscription.billing_cycle = billing_cycle
            subscription.current_period_start = period_start
            subscription.current_period_end = period_end
            self.session.add(subscription)

        await self.session.flush()
        await self.session.refresh(subscription)
        return subscription

