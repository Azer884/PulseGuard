"""Plane integration: connection, import/sync, and Plane-user -> employee mapping.

Plane responses are normalized here into PulseGuard's StoredTask model; nothing
outside this package reads Plane's format. Rules:

* Task type comes from labels via the shared taxonomy, only when exactly one
  type matches. Otherwise it stays unknown and the user picks one.
* Estimates are kept verbatim. Only explicit time values ("2h", "1h 30m") are
  hours. Numeric values are points and need the project's hours-per-point
  setting; categories (e.g. "M") need hours entered by the user.
* Dependencies come from Plane work-item relations (blocked_by / blocking).
  Other relation kinds are not treated as dependencies.
* Plane user IDs never become employee IDs; an explicit mapping is required.
"""
from __future__ import annotations

import html
import json
import os
import re
import threading
from collections import Counter
from pathlib import Path

import httpx

from ...models.employee import EmployeeSummary
from ...models.project import Cycle
from ...services.project_service import ProjectService
from ...taxonomy import TASK_TYPES, matched_task_types
from .client import PlaneAuthError, PlaneClient, PlaneError, PlaneNotFound, PlaneRateLimited
from .models import ImportReport, MemberMappingRequest, PlaneConfig, PlaneMember, PlaneProjectDetail, PlaneProjectSummary, PlaneStatus

SOURCE = "plane"
# Plane allows 60 requests/minute; keep headroom when fetching per-item relations.
REQUEST_BUDGET_PER_SYNC = 55
DESCRIPTION_LIMIT = 1000
TIME_ESTIMATE = re.compile(r"(?:(\d+(?:\.\d+)?)\s*h(?:ours?|rs?)?)?\s*(?:(\d+)\s*m(?:in(?:utes?)?)?)?")


class PlaneNotConfigured(Exception):
    pass


class PlaneMappingError(Exception):
    pass


# ---------------------------------------------------------------------------
# Normalization (pure functions)
# ---------------------------------------------------------------------------


def _ref_id(value) -> str | None:
    if isinstance(value, dict):
        return value.get("id")
    return value if isinstance(value, str) else None


def relation_ids(values) -> list[str]:
    """Relation buckets hold IDs (Plane Cloud docs) or {"issue_id": ...} objects (Plane CE)."""
    ids = []
    for value in values or []:
        if isinstance(value, str):
            ids.append(value)
        elif isinstance(value, dict):
            found = value.get("issue_id") or value.get("work_item_id") or value.get("id")
            if found:
                ids.append(found)
    return ids


def cycle_item_id(item: dict) -> str | None:
    """Cycle listings may return work items or join rows that point at one."""
    for key in ("issue", "work_item", "issue_id", "work_item_id"):
        value = item.get(key)
        if value:
            return _ref_id(value)
    return item.get("id")


def parse_estimate(value: str) -> tuple[str | None, str | None, float | None]:
    text = value.strip()
    if not text:
        return None, None, None
    match = TIME_ESTIMATE.fullmatch(text.lower())
    if match and (match.group(1) or match.group(2)):
        hours = float(match.group(1) or 0) + float(match.group(2) or 0) / 60
        return "time", text, round(hours, 4)
    try:
        return "points", text, float(text)
    except ValueError:
        return "category", text, None


def resolve_estimate(estimate_point, estimate_points: dict[str, str]) -> tuple[str | None, str | None, float | None]:
    if estimate_point in (None, ""):
        return None, None, None
    if isinstance(estimate_point, dict):
        return parse_estimate(str(estimate_point.get("value", "")))
    if isinstance(estimate_point, (int, float)) and not isinstance(estimate_point, bool):
        # Older Plane versions store an index into the estimate scale, not its value.
        return None, f"legacy estimate index {estimate_point}", None
    value = estimate_points.get(str(estimate_point))
    if value is None:
        return None, "unresolved estimate point", None
    return parse_estimate(str(value))


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    plain = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()
    return plain[:DESCRIPTION_LIMIT] or None


def normalize_work_item(
    item: dict,
    *,
    identifier: str | None,
    states: dict[str, dict],
    labels: dict[str, str],
    estimate_points: dict[str, str],
    cycle_of: dict[str, str],
) -> dict:
    work_item_id = item["id"]
    sequence = item.get("sequence_id")
    task_id = f"{identifier}-{sequence}" if identifier and sequence is not None else f"PLANE-{work_item_id[:8]}"

    label_names = []
    for label in item.get("labels") or []:
        name = label.get("name") if isinstance(label, dict) else labels.get(label)
        if name:
            label_names.append(name)
    types = sorted({t for name in label_names for t in matched_task_types(name)}, key=TASK_TYPES.index)

    state = item.get("state")
    state = state if isinstance(state, dict) else states.get(state or "", {})
    kind, raw, value = resolve_estimate(item.get("estimate_point"), estimate_points)
    priority = item.get("priority")

    return {
        "task_id": task_id,
        "title": (item.get("name") or task_id).strip(),
        "description": item.get("description_stripped") or _strip_html(item.get("description_html") or item.get("description")),
        "source": SOURCE,
        "source_task_id": work_item_id,
        "task_type": types[0] if len(types) == 1 else None,
        "task_type_origin": "label" if len(types) == 1 else None,
        "task_type_candidates": types if len(types) > 1 else [],
        "estimate_kind": kind,
        "estimate_raw": raw,
        "estimate_value": value,
        "deadline": item.get("target_date"),
        "start_date": item.get("start_date"),
        "priority": priority if priority and priority != "none" else None,
        "status": state.get("name"),
        "status_group": state.get("group"),
        "cycle_id": cycle_of.get(work_item_id) or _ref_id(item.get("cycle")) or _ref_id(item.get("cycle_id")),
        "source_assignee_ids": [a for a in (_ref_id(x) for x in item.get("assignees") or []) if a],
        "dependency_source_ids": [],
    }


def _member_record(raw: dict) -> dict:
    user = raw.get("member") if isinstance(raw.get("member"), dict) else raw
    full = " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p).strip()
    return {
        "plane_user_id": user["id"],
        "display_name": full or user.get("display_name") or user.get("email") or user["id"],
        "alt_name": user.get("display_name"),
        "email": user.get("email"),
    }


def _norm(name: str | None) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class PlaneService:
    def __init__(
        self,
        state_path: Path,
        projects: ProjectService,
        env_config: PlaneConfig | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self._path = Path(state_path)
        self._projects = projects
        self._env_config = env_config
        self._transport = transport
        self._lock = threading.Lock()

    # -- state ---------------------------------------------------------------

    def _load(self) -> dict:
        if not self._path.exists():
            return {"config": None, "user_map": {}, "members": []}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)

    def _config(self) -> tuple[PlaneConfig | None, str | None]:
        if self._env_config:
            return self._env_config, "env"
        with self._lock:
            saved = self._load()["config"]
        return (PlaneConfig(**saved), "saved") if saved else (None, None)

    def _client_for(self, config: PlaneConfig) -> PlaneClient:
        return PlaneClient(config.base_url, config.api_key, config.workspace_slug, transport=self._transport)

    def client(self) -> PlaneClient:
        config, _ = self._config()
        if config is None:
            raise PlaneNotConfigured("Plane is not connected")
        return self._client_for(config)

    def user_map(self) -> dict[str, str | None]:
        with self._lock:
            return dict(self._load()["user_map"])

    # -- connection ------------------------------------------------------------

    @staticmethod
    def _check(client: PlaneClient) -> str:
        me = client.me()
        try:
            client._get(client._ws("projects/"), {"per_page": 1})
        except PlaneNotFound as exc:
            raise PlaneError(f"workspace '{client.workspace_slug}' not found or not accessible") from exc
        return me.get("display_name") or me.get("email") or me.get("id", "unknown user")

    def status(self) -> PlaneStatus:
        config, source = self._config()
        if config is None:
            return PlaneStatus(configured=False, connected=False)
        base = PlaneStatus(
            configured=True,
            connected=False,
            config_source=source,
            base_url=config.base_url,
            workspace_slug=config.workspace_slug,
            api_key_hint=f"…{config.api_key[-4:]}" if len(config.api_key) >= 8 else "set",
        )
        try:
            return base.model_copy(update={"connected": True, "user": self._check(self._client_for(config))})
        except PlaneError as exc:
            return base.model_copy(update={"error": str(exc)})

    def connect(self, config: PlaneConfig) -> PlaneStatus:
        if self._env_config:
            raise PlaneMappingError("Plane is configured through environment variables; change PLANE_* in backend/.env instead")
        self._check(self._client_for(config))  # raises on failure; nothing is saved
        with self._lock:
            data = self._load()
            data["config"] = config.model_dump()
            self._save(data)
        return self.status()

    def disconnect(self) -> None:
        with self._lock:
            data = self._load()
            data["config"] = None
            self._save(data)

    # -- browsing --------------------------------------------------------------

    def _summary(self, raw: dict) -> PlaneProjectSummary:
        return PlaneProjectSummary(
            plane_project_id=raw["id"],
            name=raw.get("name") or raw["id"],
            identifier=raw.get("identifier"),
            description=_strip_html(raw.get("description")),
            imported_project_id=self._projects.find_by_source(SOURCE, raw["id"]),
        )

    def list_projects(self) -> list[PlaneProjectSummary]:
        projects = [self._summary(p) for p in self.client().list_projects() if not p.get("archived_at")]
        return sorted(projects, key=lambda p: (p.name.lower(), p.plane_project_id))

    @staticmethod
    def _cycles(client: PlaneClient, project_id: str, notes: list[str]) -> list[dict]:
        try:
            return client.list_cycles(project_id)
        except PlaneNotFound:
            notes.append("cycles are not available for this project (the feature may be disabled)")
            return []

    @staticmethod
    def _cycle_models(raw_cycles: list[dict]) -> list[Cycle]:
        return [
            Cycle(
                cycle_id=c["id"],
                name=c.get("name") or c["id"],
                start_date=(c.get("start_date") or "")[:10] or None,
                end_date=(c.get("end_date") or "")[:10] or None,
                status=(c.get("status") or None),
            )
            for c in raw_cycles
        ]

    def get_project(self, plane_project_id: str) -> PlaneProjectDetail:
        client = self.client()
        raw = client.get_project(plane_project_id)
        cycles = self._cycle_models(self._cycles(client, plane_project_id, []))
        return PlaneProjectDetail(**self._summary(raw).model_dump(), cycles=cycles)

    # -- import / sync -----------------------------------------------------------

    def import_project(self, plane_project_id: str) -> ImportReport:
        client = self.client()
        notes: list[str] = []
        project = client.get_project(plane_project_id)
        states = {s["id"]: s for s in client.list_states(plane_project_id)}
        labels = {l["id"]: l.get("name", "") for l in client.list_labels(plane_project_id)}

        raw_cycles = self._cycles(client, plane_project_id, notes)
        cycle_of: dict[str, str] = {}
        for cycle in raw_cycles:
            try:
                for entry in client.list_cycle_work_items(plane_project_id, cycle["id"]):
                    item_id = cycle_item_id(entry)
                    if item_id:
                        cycle_of.setdefault(item_id, cycle["id"])
            except PlaneNotFound:
                notes.append(f"work items of cycle '{cycle.get('name')}' could not be listed")

        estimate_points: dict[str, str] = {}
        estimate_id = _ref_id(project.get("estimate"))
        if estimate_id:
            try:
                estimate_points = {p["id"]: str(p.get("value", "")) for p in client.list_estimate_points(plane_project_id, estimate_id)}
            except PlaneNotFound:
                notes.append("estimate points could not be read; estimates were not imported")

        items = [i for i in client.list_work_items(plane_project_id) if not i.get("archived_at") and not i.get("deleted_at")]
        try:
            members = [_member_record(m) for m in client.list_members()]
            with self._lock:
                data = self._load()
                data["members"] = members
                self._save(data)
        except PlaneNotFound:
            notes.append("workspace members could not be listed; assignee names are unavailable")

        # Relations cost one request per work item. Fetch items never synced first,
        # within the rate budget; the next sync continues where this one stopped.
        existing_id = self._projects.find_by_source(SOURCE, plane_project_id)
        already = {t.source_task_id for t in self._projects.stored_tasks(existing_id) if t.relations_synced} if existing_id else set()
        order = sorted(items, key=lambda i: (i["id"] in already, i.get("sequence_id") or 0, i["id"]))
        fetched: set[str] = set()
        dependencies: dict[str, set[str]] = {i["id"]: set() for i in items}
        for item in order:
            if client.request_count >= REQUEST_BUDGET_PER_SYNC:
                break
            try:
                relations = client.list_relations(plane_project_id, item["id"])
            except PlaneNotFound:
                notes.append("this Plane instance does not expose work-item relations; dependencies were not imported")
                break
            except PlaneRateLimited:
                notes.append("Plane rate limit reached while reading dependencies")
                break
            if not isinstance(relations, dict):
                continue
            fetched.add(item["id"])
            dependencies[item["id"]].update(relation_ids(relations.get("blocked_by")))
            for blocked in relation_ids(relations.get("blocking")):
                dependencies.setdefault(blocked, set()).add(item["id"])
        pending = sum(1 for i in items if i["id"] not in fetched and i["id"] not in already)
        if pending:
            notes.append(
                f"dependencies not read yet for {pending} work item(s) (Plane allows 60 requests/minute); sync again in a minute to continue"
            )

        normalized = []
        for item in items:
            task = normalize_work_item(
                item,
                identifier=project.get("identifier"),
                states=states,
                labels=labels,
                estimate_points=estimate_points,
                cycle_of=cycle_of,
            )
            task["dependency_source_ids"] = sorted(dependencies.get(item["id"], set()))
            normalized.append(task)

        meta = {
            "source_project_id": plane_project_id,
            "name": project.get("name") or plane_project_id,
            "identifier": project.get("identifier"),
            "description": _strip_html(project.get("description")),
            "cycles": [c.model_dump(mode="json") for c in self._cycle_models(raw_cycles)],
        }
        project_id, counts = self._projects.sync_external(SOURCE, meta, normalized, fetched, notes)
        return ImportReport(project_id=project_id, notes=notes, **counts)

    def sync(self, project_id: str) -> ImportReport:
        detail = self._projects.detail(project_id)
        if detail.source != SOURCE or not detail.source_project_id:
            raise PlaneMappingError("this project was not imported from Plane")
        return self.import_project(detail.source_project_id)

    # -- people ------------------------------------------------------------------

    def members(self, team: list[EmployeeSummary], refresh: bool = True) -> list[PlaneMember]:
        with self._lock:
            state = self._load()
        records = state["members"]
        if refresh:
            try:
                records = [_member_record(m) for m in self.client().list_members()]
                with self._lock:
                    data = self._load()
                    data["members"] = records
                    self._save(data)
            except (PlaneError, PlaneNotConfigured):
                if not records:
                    raise
        valid = {e.employee_id for e in team}
        by_name: dict[str, list[str]] = {}
        for e in team:
            by_name.setdefault(_norm(e.name), []).append(e.employee_id)

        counts: Counter = Counter()
        for summary in self._projects.list():
            if summary.source == SOURCE:
                for task in self._projects.stored_tasks(summary.project_id):
                    counts.update(task.source_assignee_ids)

        result = []
        for m in records:
            uid = m["plane_user_id"]
            mapped = state["user_map"].get(uid, "__none__")
            if mapped not in ("__none__", None) and mapped in valid:
                status, employee = "matched", mapped
            elif uid in state["user_map"] and mapped is None:
                status, employee = "left_unassigned", None
            else:
                status, employee = "unmatched", None
            suggestion = None
            if status == "unmatched":
                for name in (m["display_name"], m.get("alt_name")):
                    matches = by_name.get(_norm(name), [])
                    if len(matches) == 1:
                        suggestion = matches[0]
                        break
            result.append(
                PlaneMember(
                    plane_user_id=uid,
                    display_name=m["display_name"],
                    email=m.get("email"),
                    status=status,
                    employee_id=employee,
                    suggested_employee_id=suggestion,
                    assigned_task_count=counts.get(uid, 0),
                )
            )
        return sorted(result, key=lambda r: (-r.assigned_task_count, r.display_name.lower(), r.plane_user_id))

    def set_mapping(self, request: MemberMappingRequest, valid_employee_ids: set[str]) -> None:
        with self._lock:
            data = self._load()
            known = {m["plane_user_id"] for m in data["members"]}
            if request.plane_user_id not in known:
                raise PlaneMappingError(f"unknown Plane user {request.plane_user_id}; refresh the member list first")
            if request.action == "match":
                if request.employee_id not in valid_employee_ids:
                    raise PlaneMappingError(f"unknown employee {request.employee_id}")
                data["user_map"][request.plane_user_id] = request.employee_id
            elif request.action == "leave_unassigned":
                data["user_map"][request.plane_user_id] = None
            else:
                data["user_map"].pop(request.plane_user_id, None)
            self._save(data)


__all__ = [
    "PlaneAuthError",
    "PlaneError",
    "PlaneMappingError",
    "PlaneNotConfigured",
    "PlaneRateLimited",
    "PlaneService",
    "normalize_work_item",
    "parse_estimate",
    "relation_ids",
]
