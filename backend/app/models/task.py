"""PulseGuard's own task model. Tasks from any source (local backlog, Plane)
are normalized into StoredTask; the simulation never sees source formats."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from ..taxonomy import TASK_TYPES

TaskSource = Literal["local", "plane"]
EstimateKind = Literal["hours", "time", "points", "category"]


def _known_task_type(value: str | None) -> str | None:
    if value is not None and value not in TASK_TYPES:
        raise ValueError(f"must be one of: {', '.join(TASK_TYPES)}")
    return value


class TaskInput(BaseModel):
    """A task created by hand in a local project."""

    title: str = Field(max_length=200)
    task_type: str
    effort_estimate_hours: float = Field(gt=0, le=1000)
    dependencies: list[str] = Field(default_factory=list, max_length=50)
    deadline: Optional[date] = None

    @field_validator("title")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("task_type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        return _known_task_type(value)

    @field_validator("dependencies")
    @classmethod
    def _dedupe(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(v.strip() for v in values if v.strip()))


class TaskOverrides(BaseModel):
    """User corrections for imported tasks. They survive re-syncs. None clears."""

    task_type: Optional[str] = None
    effort_hours: Optional[float] = Field(default=None, gt=0, le=1000)

    @field_validator("task_type")
    @classmethod
    def _known_type(cls, value: str | None) -> str | None:
        return _known_task_type(value)


class StoredTask(BaseModel):
    task_id: str
    title: str
    description: Optional[str] = None
    source: TaskSource = "local"
    source_task_id: Optional[str] = None

    # Task type as entered (local) or inferred from source labels (None = unknown).
    task_type: Optional[str] = None
    task_type_origin: Optional[Literal["manual", "label"]] = None
    task_type_candidates: list[str] = Field(default_factory=list)
    task_type_override: Optional[str] = None

    # Original estimate, kept verbatim. Only "hours" and "time" are hours.
    estimate_kind: Optional[EstimateKind] = None
    estimate_raw: Optional[str] = None
    estimate_value: Optional[float] = None
    effort_hours_override: Optional[float] = None

    dependencies: list[str] = Field(default_factory=list)
    external_dependency_ids: list[str] = Field(default_factory=list)
    relations_synced: bool = False

    deadline: Optional[date] = None
    start_date: Optional[date] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    status_group: Optional[str] = None
    cycle_id: Optional[str] = None
    source_assignee_ids: list[str] = Field(default_factory=list)


class TaskView(StoredTask):
    effective_task_type: Optional[str]
    task_type_source: Optional[Literal["manual", "label", "override"]]
    effort_estimate_hours: Optional[float]
    effort_source: Optional[Literal["manual", "plane_time", "points", "override"]]
    assigned_employee_id: Optional[str]
    assignment_source: Optional[Literal["manual", "plane"]]
    in_simulation: bool
    issues: list[str]


class AssignmentChange(BaseModel):
    task_id: str
    # None unassigns the task.
    assigned_employee_id: Optional[str] = None
    # Imported tasks only: drop the manual choice and follow the source assignee again.
    follow_source: bool = False


class AssignmentUpdate(BaseModel):
    changes: list[AssignmentChange] = Field(min_length=1, max_length=1000)
