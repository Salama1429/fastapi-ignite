"""Pydantic schemas for Project resources"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    """Schema for creating a project."""

    tenant_id: UUID = Field(..., description="Tenant identifier")
    name: str = Field(..., description="Project name")


class ProjectRead(BaseModel):
    """Schema returned when reading a project."""

    id: UUID = Field(..., description="Project identifier")
    tenant_id: UUID = Field(..., description="Tenant identifier")
    name: str = Field(..., description="Project name")
    vector_store_id: Optional[str] = Field(
        default=None, description="OpenAI vector store identifier"
    )
    created_at: Optional[datetime] = Field(
        default=None, description="Creation timestamp"
    )

    model_config = ConfigDict(from_attributes=True)
