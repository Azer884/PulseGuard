"""
Deterministic AI Twins simulation engine.

No LLM calls here. Every number traces to input data. Missing data
triggers exclusion + warning, never a fabricated fallback value.

Assignment-aware stress
-----------------------
When an employee carries `weekly_available_hours`, the engine projects the
burnout inputs for a given task assignment:

    assigned_hours  = sum(effort / speed_for(task_type)) over their assigned tasks
    load            = current_workload_hours + assigned_hours
    overtime        = max(overtime_hours_last_7d, load - weekly_available_hours, 0)

The whole backlog is treated as falling inside the current 7-day window, so
`load` is compared with one week of availability. These projected values feed
the unchanged burnout formula. Employees without `weekly_available_hours` keep
their recorded inputs, so their stress does not depend on the assignment.
"""
from __future__ import annotations

import itertools

from .taxonomy import role_task_types

# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------

# Hours lost when an employee's consecutive scheduled tasks differ in task_type.
TASK_SWITCH_PENALTY_HOURS = 1.0

# Exhaustive enumeration is used when the candidate space is at most this big.
MAX_ENUMERATION_ROTATIONS = 200

# Upper bound on rotations evaluated by the local search used for larger spaces.
MAX_SEARCH_EVALUATIONS = 3000

# Neutral speed used when an employee has no velocity data for a task type.
UNKNOWN_SPEED = 1.0

RISK_NORMAL_MAX = 30
RISK_WARNING_MAX = 65
RISK_RANK = {"Normal": 0, "Warning": 1, "Critical": 2}

# Contributing-factor thresholds.
HIGH_COGNITIVE_LOAD = 0.7
OVERTIME_HOURS = 10
LEGACY_HIGH_WORKLOAD_HOURS = 40
LOW_AUTONOMY = 0.4
TASK_MISMATCH_PCT = 80
BOTTLENECK_DEPENDENTS = 2


# ---------------------------------------------------------------------------
# Per-employee helpers
# ---------------------------------------------------------------------------


def _employee_speed(employee: dict, task_type: str) -> float | None:
    hist = employee.get("historical_task_velocity")
    if hist and task_type in hist and hist[task_type] > 0:
        return hist[task_type]
    return None


def task_hours(employee: dict, task: dict) -> float:
    """Hours this employee needs for a task (no switch penalty)."""
    speed = _employee_speed(employee, task["task_type"]) or UNKNOWN_SPEED
    return task["effort_estimate_hours"] / speed


def _strongest_speed(employee: dict) -> float | None:
    hist = employee.get("historical_task_velocity")
    if not hist:
        return None
    return max(hist.values())


def can_take(employee: dict, task: dict) -> bool:
    """A task is within an employee's available roles when one of those roles
    maps to the task's type in the shared taxonomy."""
    return task["task_type"] in role_task_types(employee.get("available_roles", []))


def _recovery_multiplier(employee: dict) -> float:
    workload = employee.get("current_workload_hours", 0)
    if not workload:
        return 0.1
    return max(1 + (employee.get("historical_velocity", 0) / workload), 0.1)


def _burnout_score(employee: dict) -> float | None:
    autonomy = employee.get("autonomy_score")
    if not autonomy:
        return None
    recovery = _recovery_multiplier(employee)
    score = (employee.get("cognitive_load_factor", 0) * employee.get("overtime_hours_last_7d", 0)) / (recovery * autonomy)
    return round(score, 2)


def _risk_level(stress_score: int) -> str:
    if stress_score < RISK_NORMAL_MAX:
        return "Normal"
    if stress_score <= RISK_WARNING_MAX:
        return "Warning"
    return "Critical"


def is_assignment_aware(employee: dict) -> bool:
    return bool(employee.get("weekly_available_hours"))


def project_employee(employee: dict, assigned_hours: float) -> dict:
    """Burnout inputs under a specific assignment (see module docstring)."""
    if not is_assignment_aware(employee):
        return employee
    projected = dict(employee)
    load = employee.get("current_workload_hours", 0) + assigned_hours
    projected["current_workload_hours"] = load
    projected["overtime_hours_last_7d"] = max(
        employee.get("overtime_hours_last_7d", 0), load - employee["weekly_available_hours"], 0.0
    )
    return projected


def _tasks_by_employee(assignment: dict[str, str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for tid, emp in sorted(assignment.items()):
        result.setdefault(emp, []).append(tid)
    return result


def burnout_under(employee: dict, task_ids: list[str], backlog_by_id: dict[str, dict]) -> float | None:
    hours = sum(task_hours(employee, backlog_by_id[t]) for t in task_ids)
    return _burnout_score(project_employee(employee, hours))


def _compatibility_pct(employee: dict, tasks: list[dict]) -> tuple[int | None, str | None]:
    """Effort-weighted compatibility across the employee's assigned tasks:
    per task, 100 - mismatch_penalty * 100 with
    mismatch_penalty = (strongest_speed - task_speed) / strongest_speed."""
    emp_id = employee["employee_id"]
    if not tasks:
        return None, f"compatibility_pct unavailable for {emp_id}: no tasks assigned"
    strongest = _strongest_speed(employee)
    if not strongest or strongest <= 0:
        return None, f"compatibility_pct unavailable for {emp_id}: missing historical_task_velocity"
    total_effort = 0.0
    weighted = 0.0
    for task in tasks:
        speed = _employee_speed(employee, task["task_type"])
        if speed is None:
            return None, f"compatibility_pct unavailable for {emp_id}: no historical velocity for task_type '{task['task_type']}'"
        penalty = max(0.0, (strongest - speed) / strongest)
        effort = max(task["effort_estimate_hours"], 0.0)
        weighted += (100 - penalty * 100) * effort
        total_effort += effort
    if total_effort == 0:
        return None, f"compatibility_pct unavailable for {emp_id}: assigned tasks have zero effort"
    return round(weighted / total_effort), None


def _velocity_tasks_per_day(employee: dict) -> float | None:
    """velocity_tasks_per_day is the employee's historical_velocity (a
    tasks-per-day baseline per the input contract), unscaled."""
    hv = employee.get("historical_velocity")
    return None if hv is None else round(hv, 2)


def _primary_contributing_factors(
    employee: dict,
    projected: dict,
    tasks: list[dict],
    compat_pct: int | None,
    assignment: dict[str, str],
    backlog: list[dict],
) -> list[str]:
    factors = []
    if employee.get("cognitive_load_factor", 0) >= HIGH_COGNITIVE_LOAD:
        factors.append("high cognitive load")
    if projected.get("overtime_hours_last_7d", 0) >= OVERTIME_HOURS:
        factors.append("overtime")
    if is_assignment_aware(employee):
        if projected["current_workload_hours"] > employee["weekly_available_hours"]:
            factors.append("high workload")
    elif employee.get("current_workload_hours", 0) >= LEGACY_HIGH_WORKLOAD_HOURS:
        factors.append("high workload")
    if employee.get("autonomy_score", 1) <= LOW_AUTONOMY:
        factors.append("low autonomy")
    if compat_pct is not None and compat_pct < TASK_MISMATCH_PCT:
        factors.append("task-type mismatch")

    own = {t["task_id"] for t in tasks}
    blocked_others = {
        t["task_id"]
        for t in backlog
        if own & set(t.get("dependencies", [])) and assignment.get(t["task_id"]) not in (None, employee["employee_id"])
    }
    if len(blocked_others) >= BOTTLENECK_DEPENDENTS:
        factors.append("dependency bottleneck")

    covered = role_task_types(employee.get("available_roles", []))
    role_missing = employee.get("current_role") not in employee.get("available_roles", [])
    # Only claimable when the roles map to known task types at all.
    uncovered_task = bool(covered) and any(t["task_type"] not in covered for t in tasks)
    if role_missing or uncovered_task:
        factors.append("role mismatch")

    return sorted(factors)


# ---------------------------------------------------------------------------
# Dependency-aware scheduler
# ---------------------------------------------------------------------------


def simulate_schedule(assignments: dict[str, str], backlog_by_id: dict[str, dict], employees_by_id: dict[str, dict]) -> float:
    """
    Project makespan for a complete task->employee mapping.

    A task starts when all its dependencies have finished and its employee is
    free. Among ready tasks, the one that can start earliest runs next
    (tie-break by task_id). Consecutive tasks of different types for the same
    employee add TASK_SWITCH_PENALTY_HOURS.
    """
    remaining = set(backlog_by_id.keys())
    finish_time: dict[str, float] = {}
    employee_free_at: dict[str, float] = {}
    employee_last_type: dict[str, str] = {}

    while remaining:
        ready = [
            tid
            for tid in sorted(remaining)
            if all(dep in finish_time or dep not in backlog_by_id for dep in backlog_by_id[tid].get("dependencies", []))
        ]
        if not ready:
            # Cyclic dependencies: release remaining tasks deterministically.
            ready = sorted(remaining)

        best_tid = None
        best_start = None
        for tid in ready:
            dep_ready_at = max((finish_time[d] for d in backlog_by_id[tid].get("dependencies", []) if d in finish_time), default=0.0)
            start = max(dep_ready_at, employee_free_at.get(assignments[tid], 0.0))
            if best_start is None or start < best_start:
                best_start, best_tid = start, tid

        task = backlog_by_id[best_tid]
        emp_id = assignments[best_tid]
        duration = task_hours(employees_by_id[emp_id], task)
        last_type = employee_last_type.get(emp_id)
        if last_type is not None and last_type != task["task_type"]:
            duration += TASK_SWITCH_PENALTY_HOURS

        finish_time[best_tid] = best_start + duration
        employee_free_at[emp_id] = finish_time[best_tid]
        employee_last_type[emp_id] = task["task_type"]
        remaining.discard(best_tid)

    return max(finish_time.values()) if finish_time else 0.0


# ---------------------------------------------------------------------------
# Rotation generation
# ---------------------------------------------------------------------------


def task_candidates(backlog: list[dict], employees: list[dict], warnings: list[str]) -> dict[str, list[str]]:
    """Valid candidates per task: employees whose available roles cover the
    task type. If nobody qualifies, every employee is allowed and a warning
    says so rather than leaving the task unassignable."""
    candidates = {}
    for task in backlog:
        eligible = sorted(e["employee_id"] for e in employees if can_take(e, task))
        if not eligible:
            eligible = sorted(e["employee_id"] for e in employees)
            warnings.append(
                f"no employee's available_roles cover task_type '{task['task_type']}' for task {task['task_id']}; "
                "all employees were considered for it"
            )
        candidates[task["task_id"]] = eligible
    return candidates


def complete_assignment(
    partial: dict[str, str],
    backlog: list[dict],
    candidates: dict[str, list[str]],
    employees_by_id: dict[str, dict],
) -> dict[str, str]:
    """Fill unassigned tasks greedily (task_id order): each goes to the
    candidate giving the lowest makespan for the tasks placed so far; ties go
    to whoever would carry the fewest total hours (existing workload plus
    assigned task hours), then to the lowest employee_id."""
    backlog_by_id = {t["task_id"]: t for t in backlog}
    result = {tid: emp for tid, emp in partial.items() if tid in backlog_by_id}
    for tid in sorted(backlog_by_id):
        if tid in result:
            continue
        placed = {t: backlog_by_id[t] for t in [*result, tid]}
        by_emp = _tasks_by_employee(result)
        best = None
        for emp in candidates[tid]:
            trial = {**result, tid: emp}
            makespan = round(simulate_schedule(trial, placed, employees_by_id), 6)
            employee = employees_by_id[emp]
            load = employee.get("current_workload_hours", 0) + sum(
                task_hours(employee, backlog_by_id[t]) for t in [*by_emp.get(emp, []), tid]
            )
            key = (makespan, round(load, 6), emp)
            if best is None or key < best:
                best = key
        result[tid] = best[2]
    return result


def _neighbors(current: dict[str, str], task_ids: list[str], candidates: dict[str, list[str]]):
    for tid in task_ids:
        for emp in candidates[tid]:
            if emp != current[tid]:
                yield {**current, tid: emp}
    for i, a in enumerate(task_ids):
        for b in task_ids[i + 1:]:
            ea, eb = current[a], current[b]
            if ea != eb and eb in candidates[a] and ea in candidates[b]:
                yield {**current, a: eb, b: ea}


def generate_rotations(
    current_assignment: list[dict],
    backlog: list[dict],
    employees: list[dict],
    warnings: list[str],
) -> tuple[list[dict], int]:
    """Returns (evaluated rotations, count). Small spaces are enumerated;
    larger ones use deterministic steepest-descent local search from the
    current assignment (unassigned tasks filled greedily first), moving one
    task or exchanging two tasks per step."""
    if not backlog or not employees:
        return [], 0
    backlog_by_id = {t["task_id"]: t for t in backlog}
    employees_by_id = {e["employee_id"]: e for e in employees}
    task_ids = sorted(backlog_by_id)
    candidates = task_candidates(backlog, employees, warnings)

    evaluated: dict[tuple, dict] = {}

    def evaluate(assignment: dict[str, str]) -> float:
        signature = tuple(sorted(assignment.items()))
        if signature not in evaluated:
            evaluated[signature] = {
                "assignments": dict(assignment),
                "total_completion_time_hours": simulate_schedule(assignment, backlog_by_id, employees_by_id),
            }
        return evaluated[signature]["total_completion_time_hours"]

    space = 1
    for tid in task_ids:
        space *= len(candidates[tid])
        if space > MAX_ENUMERATION_ROTATIONS:
            break

    if space <= MAX_ENUMERATION_ROTATIONS:
        for combo in itertools.product(*(candidates[tid] for tid in task_ids)):
            evaluate(dict(zip(task_ids, combo)))
    else:
        baseline = {a["task_id"]: a["assigned_employee_id"] for a in current_assignment}
        current = complete_assignment(baseline, backlog, candidates, employees_by_id)
        current_time = evaluate(current)
        while len(evaluated) < MAX_SEARCH_EVALUATIONS:
            best = None
            for neighbor in _neighbors(current, task_ids, candidates):
                if len(evaluated) >= MAX_SEARCH_EVALUATIONS:
                    break
                time = evaluate(neighbor)
                if best is None or time < best[0]:
                    best = (time, neighbor)
            if best is None or best[0] >= current_time - 1e-9:
                break
            current_time, current = best

    rotations = list(evaluated.values())
    return rotations, len(rotations)


def average_stress(employees: list[dict], assignment: dict[str, str], backlog_by_id: dict[str, dict]) -> float | None:
    by_emp = _tasks_by_employee(assignment)
    scores = [burnout_under(e, by_emp.get(e["employee_id"], []), backlog_by_id) for e in employees]
    scores = [round(s) for s in scores if s is not None]
    return sum(scores) / len(scores) if scores else None


def rank_rotations(evaluated: list[dict], employees: list[dict], backlog_by_id: dict[str, dict]) -> list[dict]:
    """Rank by completion time ascending; equal times prefer lower average
    projected stress, then the lexicographically smallest assignment."""

    def key(r):
        stress = average_stress(employees, r["assignments"], backlog_by_id)
        return (round(r["total_completion_time_hours"], 6), stress if stress is not None else 0.0, tuple(sorted(r["assignments"].items())))

    top = sorted(evaluated, key=key)[:5]
    return [
        {
            "rotation_id": f"rotation-{i:03d}",
            "total_completion_time_hours": round(r["total_completion_time_hours"], 2),
            "assignments": [{"task_id": tid, "assigned_employee_id": emp} for tid, emp in sorted(r["assignments"].items())],
        }
        for i, r in enumerate(top)
    ]


# ---------------------------------------------------------------------------
# Employee scoring (shared across modes)
# ---------------------------------------------------------------------------


def score_employees(
    employees: list[dict],
    current_assignment: list[dict],
    backlog_by_id: dict[str, dict],
    warnings: list[str],
) -> list[dict]:
    assignment = {a["task_id"]: a["assigned_employee_id"] for a in current_assignment}
    by_emp = _tasks_by_employee(assignment)
    backlog = list(backlog_by_id.values())

    results = []
    for emp in employees:
        emp_id = emp["employee_id"]
        tasks = [backlog_by_id[t] for t in by_emp.get(emp_id, [])]
        projected = project_employee(emp, sum(task_hours(emp, t) for t in tasks))
        burnout = _burnout_score(projected)
        if burnout is None:
            warnings.append(f"stress/stamina unavailable for {emp_id}: missing or zero autonomy_score")
            continue

        stress_score = round(burnout)
        compat_pct, compat_warning = _compatibility_pct(emp, tasks)
        if compat_warning:
            warnings.append(compat_warning)
        velocity = _velocity_tasks_per_day(emp)
        if velocity is None:
            warnings.append(f"velocity_tasks_per_day unavailable for {emp_id}: missing historical_velocity")

        results.append(
            {
                "employee_id": emp_id,
                "stamina": max(0, 100 - stress_score),
                "stress_score": stress_score,
                "risk_level": _risk_level(stress_score),
                "compatibility_pct": compat_pct,
                "velocity_tasks_per_day": velocity,
                "primary_contributing_factors": _primary_contributing_factors(emp, projected, tasks, compat_pct, assignment, backlog),
                "_burnout_score": burnout,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Delta metrics (optimize_fastest only)
# ---------------------------------------------------------------------------


def compute_delta_metrics(
    baseline_completion: float | None,
    rotation_completion: float | None,
    baseline_avg_stress: float | None,
    rotation_avg_stress: float | None,
    warnings: list[str],
) -> dict | None:
    if baseline_completion is None or rotation_completion is None:
        warnings.append("delta_metrics unavailable: baseline or rotation completion time could not be calculated")
        return None
    if baseline_completion == 0:
        warnings.append("delta_metrics unavailable: baseline completion time is zero")
        return None

    velocity_boost_pct = round((baseline_completion - rotation_completion) / baseline_completion * 100, 1) + 0.0
    milestone_time_saved_hours = round(baseline_completion - rotation_completion, 1) + 0.0

    if baseline_avg_stress is None or rotation_avg_stress is None or baseline_avg_stress == 0:
        warnings.append("burnout_mitigation_pct unavailable: baseline average stress is zero or missing")
        burnout_mitigation_pct = None
    else:
        burnout_mitigation_pct = round((baseline_avg_stress - rotation_avg_stress) / baseline_avg_stress * 100, 1) + 0.0

    return {
        "velocity_boost_pct": velocity_boost_pct,
        "burnout_mitigation_pct": burnout_mitigation_pct,
        "milestone_time_saved_hours": milestone_time_saved_hours,
    }


# ---------------------------------------------------------------------------
# Swap recommendations (resolve_burnout_all / resolve_burnout_single)
# ---------------------------------------------------------------------------


def _label(employee: dict) -> str:
    name = employee.get("name")
    return f"{name} ({employee['employee_id']})" if name else employee["employee_id"]


def find_actionable_swaps(
    employees: list[dict],
    employee_scores: list[dict],
    current_assignment: list[dict],
    backlog_by_id: dict[str, dict],
    target_employee_id: str | None,
    warnings: list[str],
) -> list[dict]:
    """For each at-risk employee, find the best single change to the current
    assignment: hand one of their tasks to a colleague, or exchange one task
    each. A change is valid only if

    1. every moved task's type is covered by the receiver's available roles,
    2. dependencies are untouched (only assignees change; the scheduler still
       enforces every dependency, and the resulting completion time is reported),
    3. both tasks exist in the backlog,
    4. the at-risk employee's projected burnout strictly drops, while the
       colleague neither becomes Critical nor moves to a worse risk level,
    5. ties resolve deterministically (larger reduction, then shorter project,
       then fewer moved tasks, then ids).
    """
    employees_by_id = {e["employee_id"]: e for e in employees}
    scores_by_id = {s["employee_id"]: s for s in employee_scores}
    assignment = {a["task_id"]: a["assigned_employee_id"] for a in current_assignment}
    by_emp = _tasks_by_employee(assignment)
    complete = len(assignment) == len(backlog_by_id)
    makespan_before = simulate_schedule(assignment, backlog_by_id, employees_by_id) if complete and assignment else None

    at_risk = sorted(s["employee_id"] for s in employee_scores if s["risk_level"] in ("Warning", "Critical"))
    if target_employee_id is not None:
        if target_employee_id not in employees_by_id:
            warnings.append(f"target employee {target_employee_id} is not in the payload")
            return []
        if target_employee_id not in scores_by_id:
            warnings.append(f"target employee {target_employee_id} could not be scored")
            return []
        if target_employee_id not in at_risk:
            warnings.append(f"{target_employee_id} is at Normal risk; no swap is needed")
            return []
        at_risk = [target_employee_id]

    swaps = []
    for a_id in at_risk:
        a_emp = employees_by_id[a_id]
        if not is_assignment_aware(a_emp):
            warnings.append(
                f"no valid swap for {a_id}: stress does not depend on task assignment without weekly_available_hours"
            )
            continue
        a_tasks = by_emp.get(a_id, [])
        if not a_tasks:
            warnings.append(f"no valid swap for {a_id}: no tasks assigned to move")
            continue
        a_before = scores_by_id[a_id]["_burnout_score"]

        best = None
        for b_id in sorted(employees_by_id):
            if b_id == a_id or b_id not in scores_by_id:
                continue
            b_emp = employees_by_id[b_id]
            b_tasks = by_emp.get(b_id, [])
            b_before = scores_by_id[b_id]["_burnout_score"]
            b_level_before = scores_by_id[b_id]["risk_level"]

            for give in a_tasks:
                if not can_take(b_emp, backlog_by_id[give]):
                    continue
                options = [None] + [t for t in b_tasks if can_take(a_emp, backlog_by_id[t])]
                for take in options:
                    a_after_tasks = [t for t in a_tasks if t != give] + ([take] if take else [])
                    b_after_tasks = [t for t in b_tasks if t != take] + [give]
                    a_after = burnout_under(a_emp, a_after_tasks, backlog_by_id)
                    b_after = burnout_under(b_emp, b_after_tasks, backlog_by_id)
                    if a_after is None or b_after is None or a_after >= a_before:
                        continue
                    b_level_after = _risk_level(round(b_after))
                    if b_level_after == "Critical" or RISK_RANK[b_level_after] > RISK_RANK[b_level_before]:
                        continue
                    reduction = round((a_before - a_after) / a_before * 100, 1) if a_before else 0.0
                    if reduction <= 0:
                        continue
                    new_assignment = {**assignment, give: b_id, **({take: a_id} if take else {})}
                    makespan_after = simulate_schedule(new_assignment, backlog_by_id, employees_by_id) if makespan_before is not None else None
                    tasks = [give] + ([take] if take else [])
                    key = (-reduction, makespan_after if makespan_after is not None else 0.0, len(tasks), b_id, tuple(tasks))
                    if best is None or key < best[0]:
                        best = (key, b_id, tasks, a_after, b_before, b_after, makespan_after)

        if best is None:
            warnings.append(f"no valid swap found for at-risk employee {a_id}")
            continue

        (neg_reduction, *_), b_id, tasks, a_after, b_before, b_after, makespan_after = best
        b_emp = employees_by_id[b_id]
        give = backlog_by_id[tasks[0]]
        moves = f"Move {give['task_id']} ({give['task_type']}, {give['effort_estimate_hours']:g}h effort) from {_label(a_emp)} to {_label(b_emp)}"
        if len(tasks) == 2:
            take = backlog_by_id[tasks[1]]
            moves += f" and {take['task_id']} ({take['task_type']}, {take['effort_estimate_hours']:g}h effort) back to {_label(a_emp)}"
        timing = (
            f" Simulated project completion: {makespan_before:.1f}h before, {makespan_after:.1f}h after."
            if makespan_before is not None and makespan_after is not None
            else ""
        )
        swaps.append(
            {
                "swap_between": [a_id, b_id],
                "tasks_affected": tasks,
                "rationale": (
                    f"{moves}. {a_id} burnout score {a_before} -> {a_after}; {b_id} {b_before} -> {b_after}. "
                    f"Each moved task's type is covered by the receiver's available roles.{timing}"
                ),
                "expected_stress_reduction_pct": -neg_reduction,
            }
        )

    swaps.sort(key=lambda s: (-s["expected_stress_reduction_pct"], s["swap_between"][0]))
    return swaps
