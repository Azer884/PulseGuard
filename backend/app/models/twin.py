"""AI Twin: simulation parameters derived from an Employee.

The engine-facing fields (employee_id ... historical_task_velocity) match the
analysis contract, so a twin dict can be placed directly in the `employees`
array of POST /api/ai-twins/analyze. Extra fields are ignored by that endpoint.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class RoleCompatibility(BaseModel):
    role: str
    matched_task_types: list[str]
    compatibility_pct: int | None


class TaskTypeFit(BaseModel):
    task_type: str
    matched_signals: list[str]
    estimated_speed: float
    compatibility_pct: int


class SimulationProfile(BaseModel):
    current_workload_hours: float
    weekly_available_hours: float
    capacity_used_pct: int
    autonomy_pct: int
    cognitive_load_pct: int


class AITwin(BaseModel):
    # Analysis-engine contract fields.
    employee_id: str
    name: str
    current_role: str
    available_roles: list[str]
    historical_velocity: float
    current_workload_hours: float
    # Optional engine field: makes stress respond to assigned backlog hours.
    # None only on twins stored by generator version 1.
    weekly_available_hours: float | None = None
    overtime_hours_last_7d: float
    autonomy_score: float
    cognitive_load_factor: float
    historical_task_velocity: dict[str, float]

    # Twin profile / provenance.
    skills: list[str]
    experience_years: float
    role_compatibility: list[RoleCompatibility]
    task_type_fit: list[TaskTypeFit]
    simulation_profile: SimulationProfile
    parameter_basis: Literal["estimated_defaults"] = "estimated_defaults"
    parameter_notes: dict[str, str]
    generator_version: str
    source_fingerprint: str
