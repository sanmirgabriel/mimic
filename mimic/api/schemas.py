"""HTTP-only request schemas; domain and application remain Pydantic-free."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class EngagementInput(BaseModel):
    name: str
    description: str | None = None


class EngagementPatch(BaseModel):
    name: str | None = None
    description: str | None = None


class OrganizationInput(BaseModel):
    name: str
    engagement_id: UUID | None = None
    aliases: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    relevant_dates: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)


class OrganizationPatch(BaseModel):
    name: str | None = None
    engagement_id: UUID | None = None
    aliases: list[str] | None = None
    locations: list[str] | None = None
    keywords: list[str] | None = None
    relevant_dates: list[str] | None = None
    domains: list[str] | None = None


class TargetInput(BaseModel):
    name: str
    profile: dict = Field(default_factory=dict)
    organization_id: UUID | None = None
    engagement_id: UUID | None = None


class TargetPatch(BaseModel):
    name: str | None = None
    profile: dict | None = None
    organization_id: UUID | None = None
    engagement_id: UUID | None = None


if hasattr(BaseModel, "model_config"):
    class _StrictModel(BaseModel):
        model_config = {"extra": "forbid"}
else:
    class _StrictModel(BaseModel):
        class Config:
            extra = "forbid"


class JobInput(_StrictModel):
    request: dict = Field(default_factory=dict)
    target_id: UUID | None = None
    engagement_id: UUID | None = None
