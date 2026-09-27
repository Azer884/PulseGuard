"""Request/response models for bulk onboarding (JSON import, Slack) and bulk removal.
Every method ends in the same EmployeeInput -> EmployeeService.create_many path."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .employee import EmployeeInput, EmployeeSummary

MAX_IMPORT_ROWS = 500


class JsonImportRequest(BaseModel):
    employees: list[EmployeeInput] = Field(min_length=1, max_length=MAX_IMPORT_ROWS)
    generate_twins: bool = False


class SkippedImport(BaseModel):
    ref: str
    name: str
    reason: str


class ImportResult(BaseModel):
    created: list[EmployeeSummary]
    skipped: list[SkippedImport]


class BulkDeleteRequest(BaseModel):
    employee_ids: list[str] = Field(min_length=1, max_length=MAX_IMPORT_ROWS)


class BulkDeleteResult(BaseModel):
    deleted: list[str]
    not_found: list[str]


class SlackStatus(BaseModel):
    configured: bool
    connected: bool
    workspace: str | None = None
    error: str | None = None


class SlackMember(BaseModel):
    slack_user_id: str
    name: str
    title: str | None
    existing_employee_id: str | None = None


class SlackImportMember(BaseModel):
    """Slack only supplies identity (name) and optionally a job title. Everything
    else the twin needs must come from the user; nothing is guessed."""

    slack_user_id: str = Field(pattern=r"^[UW][A-Z0-9]{2,}$")
    current_role: str | None = None
    skills: list[str] = Field(default_factory=list)
    experience_years: float
    available_roles: list[str] = Field(default_factory=list)
    current_workload_hours: float
    weekly_available_hours: float


class SlackImportRequest(BaseModel):
    members: list[SlackImportMember] = Field(min_length=1, max_length=200)
    generate_twins: bool = False
