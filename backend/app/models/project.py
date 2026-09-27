"""PulseGuard's own project model (local backlog or imported from Plane)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .analysis import AnalyzeRequest, AnalyzeResponse
from .task import TaskView

ProjectSource = Literal["local", "plane"]
LOCAL_PROJECT_ID = "local"


class ProjectSettings(BaseModel):
    # Converts point estimates to hours. None means points stay unconverted.
    hours_per_point: Optional[float] = Field(default=None, gt=0, le=100)
    # Simulate only tasks in this cycle (None = all cycles).
    cycle_id: Optional[str] = None
    include_completed: bool = False


class Cycle(BaseModel):
    cycle_id: str
    name: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None


class ProjectMeta(BaseModel):
    project_id: str
    source: ProjectSource
    source_project_id: Optional[str] = None
    name: str
    identifier: Optional[str] = None
    description: Optional[str] = None
    settings: ProjectSettings = Field(default_factory=ProjectSettings)
    cycles: list[Cycle] = Field(default_factory=list)
    last_synced_at: Optional[datetime] = None
    sync_notes: list[str] = Field(default_factory=list)


class ProjectSummary(ProjectMeta):
    task_count: int
    open_task_count: int
    simulated_task_count: int
    attention_count: int
    current_cycle: Optional[Cycle]


class ProjectDetail(ProjectSummary):
    tasks: list[TaskView]
    task_types: list[str]


class SimulateRequest(BaseModel):
    mode: Literal["optimize_fastest", "resolve_burnout_all", "resolve_burnout_single", "status_snapshot"]
    target_employee_id: Optional[str] = None


class SimulationEmployee(BaseModel):
    employee_id: str
    name: str
    current_role: str
    twin_status: str


class ExcludedEmployee(BaseModel):
    employee_id: str
    name: str
    reason: str


class ExcludedTask(BaseModel):
    task_id: str
    title: str
    reason: str


class SimulationContext(BaseModel):
    project_id: str
    project_name: str
    employees: list[SimulationEmployee]
    excluded_employees: list[ExcludedEmployee]
    tasks: list[TaskView]
    excluded_tasks: list[ExcludedTask]
    unassigned_task_ids: list[str]


class SimulateResponse(BaseModel):
    analysis: AnalyzeResponse
    payload: AnalyzeRequest
    context: SimulationContext


SAMPLE_BACKLOG: list[dict] = [
    {"title": "Auth service API", "task_type": "Backend", "effort_estimate_hours": 12, "dependencies": []},
    {"title": "Payments API", "task_type": "Backend", "effort_estimate_hours": 10, "dependencies": [0]},
    {"title": "Checkout UI", "task_type": "Frontend", "effort_estimate_hours": 14, "dependencies": [1]},
    {"title": "Design tokens & components", "task_type": "Design", "effort_estimate_hours": 6, "dependencies": []},
    {"title": "API contract tests", "task_type": "Testing", "effort_estimate_hours": 8, "dependencies": [1]},
    {"title": "End-to-end checkout tests", "task_type": "Testing", "effort_estimate_hours": 10, "dependencies": [2, 4]},
    {"title": "CI pipeline", "task_type": "DevOps", "effort_estimate_hours": 6, "dependencies": []},
    {"title": "Staging deployment", "task_type": "DevOps", "effort_estimate_hours": 4, "dependencies": [5, 6]},
]
