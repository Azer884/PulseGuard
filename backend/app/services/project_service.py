"""Projects (a local backlog plus imported ones) persisted in one JSON file.

Imported projects keep their source identity (source + source_project_id,
source_task_id), so re-syncing updates tasks instead of duplicating them.
User corrections (task type, hours, manual assignee) are stored separately
from source data and survive syncs.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime, timezone
from pathlib import Path

from ..models.project import (
    LOCAL_PROJECT_ID,
    SAMPLE_BACKLOG,
    Cycle,
    ProjectDetail,
    ProjectMeta,
    ProjectSettings,
    ProjectSummary,
)
from ..models.task import AssignmentChange, StoredTask, TaskInput, TaskOverrides, TaskView
from ..taxonomy import TASK_TYPES

CLOSED_STATUS_GROUPS = {"completed", "cancelled"}


class ProjectNotFound(Exception):
    pass


class TaskNotFound(Exception):
    pass


class InvalidProjectChange(Exception):
    pass


# ---------------------------------------------------------------------------
# Effective values (pure functions shared with the simulation builder)
# ---------------------------------------------------------------------------


def effective_task_type(task: StoredTask) -> tuple[str | None, str | None]:
    if task.task_type_override:
        return task.task_type_override, "override"
    if task.task_type:
        return task.task_type, task.task_type_origin
    return None, None


def effective_effort(task: StoredTask, settings: ProjectSettings) -> tuple[float | None, str | None]:
    if task.effort_hours_override is not None:
        return task.effort_hours_override, "override"
    if task.estimate_kind == "hours" and task.estimate_value is not None:
        return task.estimate_value, "manual"
    if task.estimate_kind == "time" and task.estimate_value is not None:
        return round(task.estimate_value, 2), "plane_time"
    if task.estimate_kind == "points" and task.estimate_value is not None and settings.hours_per_point:
        return round(task.estimate_value * settings.hours_per_point, 2), "points"
    return None, None


def effective_assignee(
    task: StoredTask, manual: dict[str, str | None], assignee_map: dict[str, str | None], valid_employee_ids: set[str]
) -> tuple[str | None, str | None]:
    """Manual choice wins; otherwise the first source assignee explicitly mapped
    to an existing employee. Source user IDs never become employee IDs."""
    if task.task_id in manual:
        employee = manual[task.task_id]
        return (employee if employee in valid_employee_ids else None), "manual"
    for user_id in task.source_assignee_ids:
        employee = assignee_map.get(user_id)
        if employee and employee in valid_employee_ids:
            return employee, "plane"
    return None, None


def is_open(task: StoredTask) -> bool:
    return task.status_group not in CLOSED_STATUS_GROUPS


def in_scope(task: StoredTask, settings: ProjectSettings) -> bool:
    if not settings.include_completed and not is_open(task):
        return False
    return settings.cycle_id is None or task.cycle_id == settings.cycle_id


def current_cycle(cycles: list[Cycle], today: date | None = None) -> Cycle | None:
    today = today or date.today()
    flagged = [c for c in cycles if (c.status or "").lower() == "current"]
    if flagged:
        return sorted(flagged, key=lambda c: (c.start_date or date.min, c.cycle_id))[0]
    running = [c for c in cycles if c.start_date and c.end_date and c.start_date <= today <= c.end_date]
    return sorted(running, key=lambda c: (c.start_date, c.cycle_id))[0] if running else None


def task_issues(task: StoredTask, settings: ProjectSettings, effort: float | None, task_type: str | None, assignee: str | None) -> list[str]:
    issues = []
    if effort is None:
        if task.estimate_kind == "points":
            issues.append(f"estimate is {task.estimate_raw} points; set hours per point or enter hours")
        elif task.estimate_kind == "category":
            issues.append(f"estimate '{task.estimate_raw}' is a category, not hours; enter hours")
        else:
            issues.append("no hour estimate; enter hours")
    if task_type is None:
        if task.task_type_candidates:
            issues.append(f"task type ambiguous ({', '.join(task.task_type_candidates)}); pick one")
        else:
            issues.append("task type unknown; pick one")
    if assignee is None and task.source_assignee_ids:
        issues.append("source assignee not matched to a PulseGuard employee")
    if task.external_dependency_ids:
        issues.append(f"{len(task.external_dependency_ids)} dependency(ies) outside this project were not imported")
    return issues


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class ProjectService:
    def __init__(self, store_path: Path):
        self._path = Path(store_path)
        self._lock = threading.Lock()

    # -- persistence -------------------------------------------------------

    def _load(self) -> dict:
        if self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
        else:
            data = {"next_project_seq": 1, "projects": {}}
        if LOCAL_PROJECT_ID not in data["projects"]:
            data["projects"][LOCAL_PROJECT_ID] = self._new_record(
                ProjectMeta(project_id=LOCAL_PROJECT_ID, source="local", name="Local Backlog")
            )
        return data

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)

    @staticmethod
    def _new_record(meta: ProjectMeta) -> dict:
        return {"meta": meta.model_dump(mode="json"), "tasks": {}, "assignment": {}, "next_task_id": 1}

    @staticmethod
    def _project(data: dict, project_id: str) -> dict:
        record = data["projects"].get(project_id)
        if record is None:
            raise ProjectNotFound(project_id)
        return record

    @staticmethod
    def _require_local(record: dict) -> None:
        if record["meta"]["source"] != "local":
            raise InvalidProjectChange("imported tasks are managed in their source tool; edit them there and sync")

    # -- views -------------------------------------------------------------

    @staticmethod
    def _views(record: dict, assignee_map: dict, valid_employee_ids: set[str]) -> list[TaskView]:
        settings = ProjectSettings(**record["meta"]["settings"])
        views = []
        for raw in record["tasks"].values():
            task = StoredTask(**raw)
            task_type, type_source = effective_task_type(task)
            effort, effort_source = effective_effort(task, settings)
            assignee, assignment_source = effective_assignee(task, record["assignment"], assignee_map, valid_employee_ids)
            views.append(
                TaskView(
                    **task.model_dump(),
                    effective_task_type=task_type,
                    task_type_source=type_source,
                    effort_estimate_hours=effort,
                    effort_source=effort_source,
                    assigned_employee_id=assignee,
                    assignment_source=assignment_source,
                    in_simulation=in_scope(task, settings) and effort is not None,
                    issues=task_issues(task, settings, effort, task_type, assignee) if in_scope(task, settings) else [],
                )
            )
        return views

    def _summary(self, record: dict, views: list[TaskView]) -> ProjectSummary:
        meta = ProjectMeta(**record["meta"])
        return ProjectSummary(
            **meta.model_dump(),
            task_count=len(views),
            open_task_count=sum(1 for v in views if is_open(v)),
            simulated_task_count=sum(1 for v in views if v.in_simulation),
            attention_count=sum(1 for v in views if v.issues),
            current_cycle=current_cycle(meta.cycles),
        )

    def list(self, assignee_map: dict | None = None, valid_employee_ids: set[str] | None = None) -> list[ProjectSummary]:
        with self._lock:
            data = self._load()
            return [
                self._summary(record, self._views(record, assignee_map or {}, valid_employee_ids or set()))
                for record in data["projects"].values()
            ]

    def detail(self, project_id: str, assignee_map: dict | None = None, valid_employee_ids: set[str] | None = None) -> ProjectDetail:
        with self._lock:
            record = self._project(self._load(), project_id)
            views = self._views(record, assignee_map or {}, valid_employee_ids or set())
            return ProjectDetail(**self._summary(record, views).model_dump(), tasks=views, task_types=TASK_TYPES)

    def find_by_source(self, source: str, source_project_id: str) -> str | None:
        with self._lock:
            for pid, record in self._load()["projects"].items():
                meta = record["meta"]
                if meta["source"] == source and meta["source_project_id"] == source_project_id:
                    return pid
            return None

    def stored_tasks(self, project_id: str) -> list[StoredTask]:
        with self._lock:
            return [StoredTask(**t) for t in self._project(self._load(), project_id)["tasks"].values()]

    # -- local task editing --------------------------------------------------

    @staticmethod
    def _check_dependencies(tasks: dict, task_id: str, dependencies: list[str]) -> None:
        if task_id in dependencies:
            raise InvalidProjectChange("a task cannot depend on itself")
        missing = [d for d in dependencies if d not in tasks]
        if missing:
            raise InvalidProjectChange(f"unknown dependencies: {', '.join(missing)}")
        graph = {tid: list(t["dependencies"]) for tid, t in tasks.items()}
        graph[task_id] = list(dependencies)
        stack, seen = list(dependencies), set()
        while stack:
            node = stack.pop()
            if node == task_id:
                raise InvalidProjectChange("these dependencies would create a cycle")
            if node in seen:
                continue
            seen.add(node)
            stack.extend(graph.get(node, []))

    @staticmethod
    def _local_record(task_id: str, payload: TaskInput) -> dict:
        return StoredTask(
            task_id=task_id,
            title=payload.title,
            task_type=payload.task_type,
            task_type_origin="manual",
            estimate_kind="hours",
            estimate_raw=f"{payload.effort_estimate_hours:g}h",
            estimate_value=payload.effort_estimate_hours,
            dependencies=payload.dependencies,
            deadline=payload.deadline,
        ).model_dump(mode="json")

    def create_task(self, project_id: str, payload: TaskInput) -> StoredTask:
        with self._lock:
            data = self._load()
            record = self._project(data, project_id)
            self._require_local(record)
            task_id = f"T-{record['next_task_id']:03d}"
            self._check_dependencies(record["tasks"], task_id, payload.dependencies)
            record["next_task_id"] += 1
            record["tasks"][task_id] = self._local_record(task_id, payload)
            self._save(data)
            return StoredTask(**record["tasks"][task_id])

    def update_task(self, project_id: str, task_id: str, payload: TaskInput) -> StoredTask:
        with self._lock:
            data = self._load()
            record = self._project(data, project_id)
            self._require_local(record)
            if task_id not in record["tasks"]:
                raise TaskNotFound(task_id)
            self._check_dependencies(record["tasks"], task_id, payload.dependencies)
            record["tasks"][task_id] = self._local_record(task_id, payload)
            self._save(data)
            return StoredTask(**record["tasks"][task_id])

    def delete_task(self, project_id: str, task_id: str) -> None:
        with self._lock:
            data = self._load()
            record = self._project(data, project_id)
            self._require_local(record)
            if record["tasks"].pop(task_id, None) is None:
                raise TaskNotFound(task_id)
            record["assignment"].pop(task_id, None)
            for task in record["tasks"].values():
                task["dependencies"] = [d for d in task["dependencies"] if d != task_id]
            self._save(data)

    def clear(self, project_id: str) -> None:
        with self._lock:
            data = self._load()
            record = self._project(data, project_id)
            self._require_local(record)
            record["tasks"], record["assignment"] = {}, {}
            self._save(data)

    def load_sample(self, project_id: str) -> bool:
        with self._lock:
            data = self._load()
            record = self._project(data, project_id)
            self._require_local(record)
            if record["tasks"]:
                return False
            ids: list[str] = []
            for spec in SAMPLE_BACKLOG:
                task_id = f"T-{record['next_task_id']:03d}"
                record["next_task_id"] += 1
                payload = TaskInput(**{**spec, "dependencies": [ids[i] for i in spec["dependencies"]]})
                record["tasks"][task_id] = self._local_record(task_id, payload)
                ids.append(task_id)
            self._save(data)
            return True

    # -- corrections, settings, assignment ------------------------------------

    def set_overrides(self, project_id: str, task_id: str, overrides: TaskOverrides) -> StoredTask:
        with self._lock:
            data = self._load()
            record = self._project(data, project_id)
            task = record["tasks"].get(task_id)
            if task is None:
                raise TaskNotFound(task_id)
            task["task_type_override"] = overrides.task_type
            task["effort_hours_override"] = overrides.effort_hours
            self._save(data)
            return StoredTask(**task)

    def update_settings(self, project_id: str, settings: ProjectSettings) -> ProjectMeta:
        with self._lock:
            data = self._load()
            record = self._project(data, project_id)
            meta = ProjectMeta(**record["meta"])
            if settings.cycle_id and settings.cycle_id not in {c.cycle_id for c in meta.cycles}:
                raise InvalidProjectChange(f"unknown cycle: {settings.cycle_id}")
            record["meta"]["settings"] = settings.model_dump(mode="json")
            self._save(data)
            return ProjectMeta(**record["meta"])

    def apply_changes(self, project_id: str, changes: list[AssignmentChange], valid_employee_ids: set[str]) -> None:
        with self._lock:
            data = self._load()
            record = self._project(data, project_id)
            unknown_tasks = [c.task_id for c in changes if c.task_id not in record["tasks"]]
            if unknown_tasks:
                raise InvalidProjectChange(f"unknown tasks: {', '.join(unknown_tasks)}")
            unknown_employees = sorted(
                {c.assigned_employee_id for c in changes if c.assigned_employee_id and c.assigned_employee_id not in valid_employee_ids}
            )
            if unknown_employees:
                raise InvalidProjectChange(f"unknown employees: {', '.join(unknown_employees)}")
            imported = record["meta"]["source"] != "local"
            for change in changes:
                if change.follow_source or (not imported and change.assigned_employee_id is None):
                    record["assignment"].pop(change.task_id, None)
                else:
                    # For imported tasks an explicit None records "leave unassigned".
                    record["assignment"][change.task_id] = change.assigned_employee_id
            self._save(data)

    def unassign_employees(self, employee_ids: list[str]) -> None:
        gone = set(employee_ids)
        with self._lock:
            data = self._load()
            changed = False
            for record in data["projects"].values():
                kept = {t: e for t, e in record["assignment"].items() if e not in gone}
                if len(kept) != len(record["assignment"]):
                    record["assignment"] = kept
                    changed = True
            if changed:
                self._save(data)

    def delete_project(self, project_id: str) -> None:
        with self._lock:
            data = self._load()
            if project_id == LOCAL_PROJECT_ID:
                raise InvalidProjectChange("the local backlog cannot be removed")
            self._project(data, project_id)
            del data["projects"][project_id]
            self._save(data)

    # -- import / sync --------------------------------------------------------

    def sync_external(
        self,
        source: str,
        meta: dict,
        tasks: list[dict],
        synced_relation_ids: set[str],
        notes: list[str],
    ) -> tuple[str, dict]:
        """Create or update an imported project from normalized tasks.

        Each task dict is a StoredTask payload plus `dependency_source_ids`.
        Identity is (source, source_project_id) for the project and
        source_task_id for tasks. Returns (project_id, counts).
        """
        with self._lock:
            data = self._load()
            project_id = next(
                (pid for pid, r in data["projects"].items() if r["meta"]["source"] == source and r["meta"]["source_project_id"] == meta["source_project_id"]),
                None,
            )
            if project_id is None:
                project_id = f"{source}_{data['next_project_seq']:03d}"
                data["next_project_seq"] += 1
                data["projects"][project_id] = self._new_record(ProjectMeta(project_id=project_id, source=source, **meta))
            record = data["projects"][project_id]

            existing = {t["source_task_id"]: t for t in record["tasks"].values()}
            used_ids = set()
            task_id_by_source: dict[str, str] = {}
            for incoming in tasks:
                old = existing.get(incoming["source_task_id"])
                task_id = old["task_id"] if old else incoming["task_id"]
                base, suffix = task_id, 2
                while task_id in used_ids or (not old and task_id in {t["task_id"] for t in existing.values()}):
                    task_id, suffix = f"{base}-{suffix}", suffix + 1
                used_ids.add(task_id)
                task_id_by_source[incoming["source_task_id"]] = task_id

            new_tasks: dict[str, dict] = {}
            counts = {"created": 0, "updated": 0, "removed": 0}
            old_task_ids = {t["task_id"] for t in existing.values()}
            for incoming in tasks:
                source_id = incoming["source_task_id"]
                old = existing.get(source_id)
                task_id = task_id_by_source[source_id]
                dep_sources = incoming.get("dependency_source_ids", [])
                dependencies = sorted({task_id_by_source[s] for s in dep_sources if s in task_id_by_source} - {task_id})
                external = sorted({s for s in dep_sources if s not in task_id_by_source})
                relations_synced = source_id in synced_relation_ids
                if old and not relations_synced:
                    # Relations not refetched this time: keep what we knew, plus anything learned from the other side.
                    dependencies = sorted((set(old["dependencies"]) & set(task_id_by_source.values()) | set(dependencies)) - {task_id})
                    external = sorted(set(old.get("external_dependency_ids", [])) | set(external))
                    relations_synced = old.get("relations_synced", False)
                task = {k: v for k, v in incoming.items() if k != "dependency_source_ids"}
                task.update(
                    task_id=task_id,
                    dependencies=dependencies,
                    external_dependency_ids=external,
                    relations_synced=relations_synced,
                    task_type_override=old.get("task_type_override") if old else None,
                    effort_hours_override=old.get("effort_hours_override") if old else None,
                )
                new_tasks[task_id] = StoredTask(**task).model_dump(mode="json")
                counts["updated" if old else "created"] += 1

            counts["removed"] = len(old_task_ids - set(new_tasks))
            record["tasks"] = new_tasks
            record["assignment"] = {t: e for t, e in record["assignment"].items() if t in new_tasks}
            settings = record["meta"]["settings"]
            cycle_ids = {c["cycle_id"] for c in meta.get("cycles", [])}
            if settings.get("cycle_id") and settings["cycle_id"] not in cycle_ids:
                settings["cycle_id"] = None
                notes.append("the selected simulation cycle no longer exists in the source; showing all cycles")
            record["meta"].update(
                {k: v for k, v in ProjectMeta(project_id=project_id, source=source, **meta).model_dump(mode="json").items() if k not in ("project_id", "settings")},
                last_synced_at=datetime.now(timezone.utc).isoformat(),
                sync_notes=notes,
            )
            self._save(data)
            return project_id, counts
