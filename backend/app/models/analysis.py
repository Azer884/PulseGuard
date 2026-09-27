"""Pydantic request/response models for the AI Twins analysis engine."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AssignmentEntry(BaseModel):
    task_id: str
    assigned_employee_id: str


class Task(BaseModel):
    task_id: str
    task_type: str
    dependencies: list[str] = Field(default_factory=list)
    effort_estimate_hours: float
    deadline: Optional[str] = None


class Employee(BaseModel):
    employee_id: str
    name: str
    current_role: str
    available_roles: list[str] = Field(default_factory=list)
    historical_velocity: float
    current_workload_hours: float
    overtime_hours_last_7d: float
    autonomy_score: float
    cognitive_load_factor: float
    historical_task_velocity: Optional[dict[str, float]] = None
    # Optional extension. When present, hours of assigned backlog work are added
    # to the employee's load and hours beyond this availability count as overtime.
    weekly_available_hours: Optional[float] = Field(default=None, gt=0)


class AnalyzeRequest(BaseModel):
    current_assignment: list[AssignmentEntry]
    backlog: list[Task]
    employees: list[Employee]
    mode: str
    target_employee_id: Optional[str] = None


class RotationAssignment(BaseModel):
    task_id: str
    assigned_employee_id: str


class Rotation(BaseModel):
    rotation_id: str
    total_completion_time_hours: float
    assignments: list[RotationAssignment]


class DeltaMetrics(BaseModel):
    velocity_boost_pct: float
    burnout_mitigation_pct: Optional[float]
    milestone_time_saved_hours: float


class EmployeeResult(BaseModel):
    employee_id: str
    stamina: int
    stress_score: int
    risk_level: str
    compatibility_pct: Optional[int]
    velocity_tasks_per_day: Optional[float]
    primary_contributing_factors: list[str]


class ActionableSwap(BaseModel):
    swap_between: list[str]
    tasks_affected: list[str]
    rationale: str
    expected_stress_reduction_pct: float


class Recommendations(BaseModel):
    role_swap_required: bool
    actionable_swaps: list[ActionableSwap]


class AnalyzeResponse(BaseModel):
    mode: str
    rotations_evaluated: int
    rotations_ranked: list[Rotation]
    delta_metrics: Optional[DeltaMetrics]
    employees: list[EmployeeResult]
    recommendations: Recommendations
    warnings: list[str]
