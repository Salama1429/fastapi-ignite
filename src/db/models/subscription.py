"""Subscription model linking tenants to plans."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class Subscription(Base):
    """Represents the active plan selection for a tenant."""

    __tablename__ = "subscriptions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), primary_key=True
    )
    plan_id: Mapped[str] = mapped_column(String, ForeignKey("plans.id"), nullable=False)
    billing_cycle: Mapped[str] = mapped_column(String, nullable=False, default="monthly")
    current_period_start: Mapped[dt.date] = mapped_column(
        Date, nullable=False, default=dt.date.today
    )
    current_period_end: Mapped[dt.date] = mapped_column(Date, nullable=False)

    plan: Mapped["Plan"] = relationship("Plan")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Subscription tenant={self.tenant_id} plan={self.plan_id}>"

