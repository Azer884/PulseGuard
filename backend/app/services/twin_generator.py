"""Single twin generator shared by every onboarding method.

Twins built here are simulation parameters for fictional/demo employees,
estimated with fixed deterministic rules from the employee profile. They are
NOT measurements of a real person. Same input always yields the same twin.
"""
from __future__ import annotations

import hashlib
import json

from ..models.employee import Employee
from ..models.twin import AITwin, RoleCompatibility, SimulationProfile, TaskTypeFit
from ..taxonomy import TASK_TYPE_KEYWORDS, matched_task_types

GENERATOR_VERSION = "2"

# Deterministic estimation constants. See parameter_notes for their meaning.
SPEED_BASE = 0.5
SPEED_SKILL_WEIGHT = 0.7
SPEED_EXPERIENCE_WEIGHT = 0.3
SKILL_SIGNAL_CAP = 3
EXPERIENCE_CAP_YEARS = 10
VELOCITY_BASE_TASKS_PER_DAY = 1.0
VELOCITY_PER_EXPERIENCE_YEAR = 0.15
AUTONOMY_BASE = 0.5
AUTONOMY_PER_EXPERIENCE_YEAR = 0.04
COGNITIVE_LOAD_BASE = 0.2
COGNITIVE_LOAD_PER_UTILIZATION = 0.6
COGNITIVE_LOAD_MIN = 0.1
COGNITIVE_LOAD_MAX = 0.95


def employee_fingerprint(employee: Employee) -> str:
    """Hash of the profile fields a twin is derived from; used to detect stale twins."""
    payload = employee.model_dump(exclude={"source", "external_ref"})
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _task_type_fit(employee: Employee) -> list[TaskTypeFit]:
    experience_score = min(employee.experience_years, EXPERIENCE_CAP_YEARS) / EXPERIENCE_CAP_YEARS
    signals: dict[str, list[str]] = {task_type: [] for task_type in TASK_TYPE_KEYWORDS}
    for skill in employee.skills:
        for task_type in matched_task_types(skill):
            signals[task_type].append(skill)
    for task_type in matched_task_types(employee.current_role):
        signals[task_type].append(f"current role: {employee.current_role}")

    speeds = {
        task_type: round(
            SPEED_BASE
            + SPEED_SKILL_WEIGHT * min(len(found), SKILL_SIGNAL_CAP) / SKILL_SIGNAL_CAP
            + SPEED_EXPERIENCE_WEIGHT * experience_score,
            2,
        )
        for task_type, found in signals.items()
    }
    strongest = max(speeds.values())
    # Same definition the analysis engine uses: 100 - mismatch_penalty * 100,
    # mismatch_penalty = (strongest - speed) / strongest.
    return [
        TaskTypeFit(
            task_type=task_type,
            matched_signals=signals[task_type],
            estimated_speed=speed,
            compatibility_pct=round(speed / strongest * 100),
        )
        for task_type, speed in speeds.items()
    ]


def _role_compatibility(employee: Employee, fit: list[TaskTypeFit]) -> list[RoleCompatibility]:
    pct_by_type = {f.task_type: f.compatibility_pct for f in fit}
    result = []
    for role in employee.available_roles:
        types = matched_task_types(role)
        result.append(
            RoleCompatibility(
                role=role,
                matched_task_types=types,
                # Roles that map to no known task type get no score rather than a guess.
                compatibility_pct=max(pct_by_type[t] for t in types) if types else None,
            )
        )
    return result


def generate_twin(employee: Employee) -> AITwin:
    experience = min(employee.experience_years, EXPERIENCE_CAP_YEARS)
    utilization = employee.current_workload_hours / employee.weekly_available_hours

    historical_velocity = round(VELOCITY_BASE_TASKS_PER_DAY + VELOCITY_PER_EXPERIENCE_YEAR * experience, 2)
    autonomy = round(AUTONOMY_BASE + AUTONOMY_PER_EXPERIENCE_YEAR * experience, 2)
    cognitive_load = round(
        min(COGNITIVE_LOAD_MAX, max(COGNITIVE_LOAD_MIN, COGNITIVE_LOAD_BASE + COGNITIVE_LOAD_PER_UTILIZATION * utilization)),
        2,
    )
    overtime = round(max(0.0, employee.current_workload_hours - employee.weekly_available_hours), 2)

    fit = _task_type_fit(employee)

    return AITwin(
        employee_id=employee.employee_id,
        name=employee.name,
        current_role=employee.current_role,
        available_roles=list(employee.available_roles),
        historical_velocity=historical_velocity,
        current_workload_hours=employee.current_workload_hours,
        weekly_available_hours=employee.weekly_available_hours,
        overtime_hours_last_7d=overtime,
        autonomy_score=autonomy,
        cognitive_load_factor=cognitive_load,
        historical_task_velocity={f.task_type: f.estimated_speed for f in fit},
        skills=list(employee.skills),
        experience_years=employee.experience_years,
        role_compatibility=_role_compatibility(employee, fit),
        task_type_fit=fit,
        simulation_profile=SimulationProfile(
            current_workload_hours=employee.current_workload_hours,
            weekly_available_hours=employee.weekly_available_hours,
            capacity_used_pct=round(utilization * 100),
            autonomy_pct=round(autonomy * 100),
            cognitive_load_pct=round(cognitive_load * 100),
        ),
        parameter_notes={
            "historical_task_velocity": (
                "Estimated speed multiplier per task type, not measured history: "
                f"{SPEED_BASE} + {SPEED_SKILL_WEIGHT} x min(matching skills/role, {SKILL_SIGNAL_CAP})/{SKILL_SIGNAL_CAP} "
                f"+ {SPEED_EXPERIENCE_WEIGHT} x min(experience_years, {EXPERIENCE_CAP_YEARS})/{EXPERIENCE_CAP_YEARS}."
            ),
            "historical_velocity": (
                f"Estimated tasks/day baseline: {VELOCITY_BASE_TASKS_PER_DAY} + "
                f"{VELOCITY_PER_EXPERIENCE_YEAR} x min(experience_years, {EXPERIENCE_CAP_YEARS})."
            ),
            "overtime_hours_last_7d": "Scheduled hours beyond weekly availability: max(0, current_workload_hours - weekly_available_hours).",
            "autonomy_score": (
                f"Estimated from experience: {AUTONOMY_BASE} + {AUTONOMY_PER_EXPERIENCE_YEAR} x "
                f"min(experience_years, {EXPERIENCE_CAP_YEARS})."
            ),
            "cognitive_load_factor": (
                f"Estimated from utilization: {COGNITIVE_LOAD_BASE} + {COGNITIVE_LOAD_PER_UTILIZATION} x "
                f"(current_workload_hours / weekly_available_hours), clamped to [{COGNITIVE_LOAD_MIN}, {COGNITIVE_LOAD_MAX}]."
            ),
        },
        generator_version=GENERATOR_VERSION,
        source_fingerprint=employee_fingerprint(employee),
    )
