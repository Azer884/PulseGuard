"""Mode orchestration for the AI Twins analysis engine. Wires engine.py
primitives into the exact output contract for each of the four modes."""
from __future__ import annotations

from . import engine

VALID_MODES = {"optimize_fastest", "resolve_burnout_all", "resolve_burnout_single", "status_snapshot"}


def analyze(payload: dict) -> dict:
    mode = payload.get("mode")
    warnings: list[str] = []

    response = {
        "mode": mode,
        "rotations_evaluated": 0,
        "rotations_ranked": [],
        "delta_metrics": None,
        "employees": [],
        "recommendations": {"role_swap_required": False, "actionable_swaps": []},
        "warnings": warnings,
    }

    if mode not in VALID_MODES:
        warnings.append(f"unsupported mode '{mode}': no analysis performed")
        return response

    current_assignment = [dict(a) for a in payload.get("current_assignment", [])]
    backlog = [dict(t) for t in payload.get("backlog", [])]
    employees = [dict(e) for e in payload.get("employees", [])]
    backlog_by_id = {t["task_id"]: t for t in backlog}
    employees_by_id = {e["employee_id"]: e for e in employees}

    valid_task_ids = set(backlog_by_id.keys())
    valid_employee_ids = set(employees_by_id.keys())
    current_assignment = [
        a
        for a in current_assignment
        if a["task_id"] in valid_task_ids and a["assigned_employee_id"] in valid_employee_ids
    ]

    employee_scores = engine.score_employees(employees, current_assignment, backlog_by_id, warnings)

    if mode == "optimize_fastest":
        evaluated, rotations_evaluated = engine.generate_rotations(current_assignment, backlog, employees, warnings)
        response["rotations_evaluated"] = rotations_evaluated
        ranked = engine.rank_rotations(evaluated, employees, backlog_by_id)
        response["rotations_ranked"] = ranked

        baseline_assignment = {a["task_id"]: a["assigned_employee_id"] for a in current_assignment}
        baseline_completion = None
        if len(baseline_assignment) == len(backlog) and backlog:
            baseline_completion = engine.simulate_schedule(baseline_assignment, backlog_by_id, employees_by_id)
        else:
            warnings.append("baseline completion time unavailable: current_assignment does not cover full backlog")

        rotation_completion = ranked[0]["total_completion_time_hours"] if ranked else None

        baseline_scores = employee_scores
        baseline_avg_stress = (
            sum(s["stress_score"] for s in baseline_scores) / len(baseline_scores) if baseline_scores else None
        )

        rotation_avg_stress = None
        if ranked:
            top_assignment = {a["task_id"]: a["assigned_employee_id"] for a in ranked[0]["assignments"]}
            rotation_current_assignment = [
                {"task_id": tid, "assigned_employee_id": emp} for tid, emp in top_assignment.items()
            ]
            rotation_scores = engine.score_employees(employees, rotation_current_assignment, backlog_by_id, [])
            if rotation_scores:
                rotation_avg_stress = sum(s["stress_score"] for s in rotation_scores) / len(rotation_scores)
            employee_scores = rotation_scores or employee_scores

        response["delta_metrics"] = engine.compute_delta_metrics(
            baseline_completion, rotation_completion, baseline_avg_stress, rotation_avg_stress, warnings
        )

    elif mode in ("resolve_burnout_all", "resolve_burnout_single"):
        target_employee_id = payload.get("target_employee_id")
        if mode == "resolve_burnout_single" and not target_employee_id:
            warnings.append(
                "resolve_burnout_single requires 'target_employee_id' in the payload; "
                "input schema does not define this field separately, so no employee-specific swap was computed"
            )
        else:
            swaps = engine.find_actionable_swaps(
                employees, employee_scores, current_assignment, backlog_by_id, target_employee_id, warnings
            )
            response["recommendations"]["actionable_swaps"] = swaps
            response["recommendations"]["role_swap_required"] = len(swaps) > 0

    # status_snapshot: employees only, everything else stays at defaults.

    response["employees"] = [
        {
            "employee_id": s["employee_id"],
            "stamina": s["stamina"],
            "stress_score": s["stress_score"],
            "risk_level": s["risk_level"],
            "compatibility_pct": s["compatibility_pct"],
            "velocity_tasks_per_day": s["velocity_tasks_per_day"],
            "primary_contributing_factors": s["primary_contributing_factors"],
        }
        for s in employee_scores
    ]

    return response
