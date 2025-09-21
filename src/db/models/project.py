"""Project model definition"""
from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class Project(Base):
    """Represents a tenant-scoped RAG project."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    vector_store_id: Mapped[Optional[str]] = mapped_column(
        String, unique=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_project_tenant_name"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Project {self.id} tenant={self.tenant_id}>"
