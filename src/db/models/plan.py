"""Billing plan model definition."""
from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class Plan(Base):
    """Represents an available subscription plan tier."""

    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    max_projects: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    monthly_message_cap: Mapped[int] = mapped_column(Integer, nullable=False, default=2000)
    monthly_upload_char_cap: Mapped[int] = mapped_column(
        Integer, nullable=False, default=500_000
    )
    is_annual_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Plan {self.id} projects={self.max_projects}>"

