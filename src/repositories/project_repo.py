"""Repository utilities for working with Project records."""
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.project import Project


class ProjectRepo:
    """Simple data-access helper for Project entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, project_id: UUID) -> Optional[Project]:
        result = await self.session.execute(
            select(Project).where(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def get_by_tenant_and_name(
        self, tenant_id: UUID, name: str
    ) -> Optional[Project]:
        result = await self.session.execute(
            select(Project).where(
                Project.tenant_id == tenant_id,
                Project.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, tenant_id: UUID, name: str) -> Project:
        project = Project(tenant_id=tenant_id, name=name)
        self.session.add(project)
        await self.session.flush()
        return project

    async def set_vector_store_id(self, project: Project, vector_store_id: str) -> Project:
        project.vector_store_id = vector_store_id
        self.session.add(project)
        await self.session.flush()
        return project

    async def count_for_tenant(self, tenant_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Project).where(Project.tenant_id == tenant_id)
        )
        value = result.scalar_one()
        return int(value or 0)
