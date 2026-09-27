"""Builds analysis-engine payloads from the team's AI Twins and a project,
so the simulation always runs on the real team and normalized tasks. It never
reads source-tool (e.g. Plane) formats directly."""
from __future__ import annotations

from .. import engine
from ..analyze import analyze
from ..models.analysis import AnalyzeRequest, AnalyzeResponse
from ..models.project import ExcludedEmployee, ExcludedTask, SimulateResponse, SimulationContext, SimulationEmployee
from ..models.task import AssignmentChange
from .employee_service import EmployeeService
from .project_service import ProjectService, in_scope

UNKNOWN_TASK_TYPE = "Unknown"


def build_payload(
    employees: EmployeeService,
    projects: ProjectService,
    project_id: str,
    mode: str,
    target_employee_id: str | None,
    assignee_map: dict[str, str | None],
):
    team = employees.list()
    twins = employees.twins()
    valid_ids = {e.employee_id for e in team}
    project = projects.detail(project_id, assignee_map, valid_ids)

    included, excluded, notes, twin_payloads = [], [], [], []
    for member in team:
        twin = twins.get(member.employee_id)
        if twin is None:
            excluded.append(ExcludedEmployee(employee_id=member.employee_id, name=member.name, reason="no AI Twin generated"))
            continue
        if member.twin_status == "outdated":
            notes.append(f"AI Twin for {member.employee_id} is outdated; regenerate it to use the latest profile")
        included.append(SimulationEmployee(employee_id=member.employee_id, name=member.name, current_role=member.current_role, twin_status=member.twin_status))
        twin_payloads.append(twin.model_dump())
    included_ids = {e.employee_id for e in included}

    scoped = [t for t in project.tasks if in_scope(t, project.settings)]
    simulated = [t for t in scoped if t.effort_estimate_hours is not None]
    excluded_tasks = [
        ExcludedTask(task_id=t.task_id, title=t.title, reason=next((i for i in t.issues if "estimate" in i or "hours" in i), "no hour estimate"))
        for t in scoped
        if t.effort_estimate_hours is None
    ]
    if excluded_tasks:
        notes.append(f"{len(excluded_tasks)} task(s) excluded from simulation: no hour estimate")
    simulated_ids = {t.task_id for t in simulated}

    backlog = []
    for t in simulated:
        dropped = [d for d in t.dependencies if d not in simulated_ids]
        if dropped:
            notes.append(f"{t.task_id}: dependencies {', '.join(dropped)} are outside the simulated scope and were not enforced")
        task_type = t.effective_task_type or UNKNOWN_TASK_TYPE
        if t.effective_task_type is None:
            notes.append(f"{t.task_id}: task type unknown; simulated as '{UNKNOWN_TASK_TYPE}' (no role covers it, neutral speed)")
        backlog.append(
            {
                "task_id": t.task_id,
                "task_type": task_type,
                "dependencies": [d for d in t.dependencies if d in simulated_ids],
                "effort_estimate_hours": t.effort_estimate_hours,
                "deadline": t.deadline.isoformat() if t.deadline else None,
            }
        )

    assignment = [
        {"task_id": t.task_id, "assigned_employee_id": t.assigned_employee_id}
        for t in simulated
        if t.assigned_employee_id in included_ids
    ]
    assigned = {a["task_id"] for a in assignment}

    payload = AnalyzeRequest(
        mode=mode,
        target_employee_id=target_employee_id,
        employees=twin_payloads,
        backlog=backlog,
        current_assignment=assignment,
    )
    context = SimulationContext(
        project_id=project.project_id,
        project_name=project.name,
        employees=included,
        excluded_employees=excluded,
        tasks=simulated,
        excluded_tasks=excluded_tasks,
        unassigned_task_ids=[t.task_id for t in simulated if t.task_id not in assigned],
    )
    return payload, context, notes


def simulate(employees, projects, project_id, mode, target_employee_id, assignee_map) -> SimulateResponse:
    payload, context, notes = build_payload(employees, projects, project_id, mode, target_employee_id, assignee_map)
    result = analyze(payload.model_dump())
    result["warnings"] = notes + result["warnings"]
    return SimulateResponse(analysis=AnalyzeResponse(**result), payload=payload, context=context)


def auto_assign(employees: EmployeeService, projects: ProjectService, project_id: str, assignee_map) -> None:
    """Assign every simulated-but-unassigned task to a team member with a twin:
    candidates are people whose available roles cover the task type, and each
    task goes to whoever yields the shortest simulated project so far.
    Existing assignments are kept."""
    payload, context, _ = build_payload(employees, projects, project_id, "status_snapshot", None, assignee_map)
    if not context.unassigned_task_ids:
        return
    data = payload.model_dump()
    if not data["employees"]:
        raise ValueError("generate at least one AI Twin before auto-assigning tasks")
    employees_by_id = {e["employee_id"]: e for e in data["employees"]}
    candidates = engine.task_candidates(data["backlog"], data["employees"], [])
    current = {a["task_id"]: a["assigned_employee_id"] for a in data["current_assignment"]}
    completed = engine.complete_assignment(current, data["backlog"], candidates, employees_by_id)
    changes = [AssignmentChange(task_id=tid, assigned_employee_id=emp) for tid, emp in sorted(completed.items()) if tid not in current]
    projects.apply_changes(project_id, changes, set(employees_by_id))
