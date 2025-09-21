"""Repository utilities for subscription plans."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.plan import Plan


class PlanRepo:
    """Data-access helpers for :class:`Plan`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, plan_id: str) -> Plan | None:
        result = await self.session.execute(select(Plan).where(Plan.id == plan_id))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Plan]:  # pragma: no cover - convenience helper
        result = await self.session.execute(select(Plan))
        return list(result.scalars().all())

