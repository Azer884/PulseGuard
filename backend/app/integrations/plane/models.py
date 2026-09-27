"""API models for the Plane integration (PulseGuard-facing, not Plane's own schema)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from ...models.project import Cycle

DEFAULT_PLANE_BASE_URL = "https://api.plane.so"


class PlaneConfig(BaseModel):
    base_url: str = DEFAULT_PLANE_BASE_URL
    api_key: str = Field(min_length=1)
    workspace_slug: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")

    @field_validator("base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        """Accepts Plane Cloud or any self-hosted URL, with or without /api/v1."""
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("must start with http:// or https://")
        for suffix in ("/api/v1", "/api"):
            if value.endswith(suffix):
                value = value[: -len(suffix)]
        return value

    @field_validator("api_key", "workspace_slug")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class PlaneStatus(BaseModel):
    configured: bool
    connected: bool
    config_source: Optional[Literal["env", "saved"]] = None
    base_url: Optional[str] = None
    workspace_slug: Optional[str] = None
    api_key_hint: Optional[str] = None
    user: Optional[str] = None
    error: Optional[str] = None


class PlaneProjectSummary(BaseModel):
    plane_project_id: str
    name: str
    identifier: Optional[str]
    description: Optional[str]
    imported_project_id: Optional[str] = None


class PlaneProjectDetail(PlaneProjectSummary):
    cycles: list[Cycle]


class ImportReport(BaseModel):
    project_id: str
    created: int
    updated: int
    removed: int
    notes: list[str]


class PlaneMember(BaseModel):
    plane_user_id: str
    display_name: str
    email: Optional[str]
    status: Literal["matched", "left_unassigned", "unmatched"]
    employee_id: Optional[str] = None
    suggested_employee_id: Optional[str] = None
    assigned_task_count: int = 0


class MemberMappingRequest(BaseModel):
    plane_user_id: str
    # "match" requires employee_id; "leave_unassigned" records an explicit choice;
    # "clear" forgets any choice (back to unmatched).
    action: Literal["match", "leave_unassigned", "clear"]
    employee_id: Optional[str] = None
