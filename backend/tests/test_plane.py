from datetime import date, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_plane_service
from app.integrations.plane.models import PlaneConfig
from app.integrations.plane.service import PlaneService, normalize_work_item, parse_estimate, relation_ids
from app.main import app

TODAY = date.today()
API_KEY = "plane_api_0123456789"


class FakePlane:
    """Mimics the documented Plane REST API v1 (cursor pagination, X-API-Key auth)."""

    def __init__(self, host="api.plane.so", slug="acme"):
        self.host, self.slug = host, slug
        self.calls: list[str] = []
        self.page_size = 2
        self.relations_available = True
        self.project = {"id": "p-apollo", "name": "Apollo", "identifier": "APOLLO", "description": "<p>Payments &amp; checkout</p>", "estimate": "est-1"}
        self.states = [
            {"id": "s-todo", "name": "Todo", "group": "unstarted"},
            {"id": "s-prog", "name": "In Progress", "group": "started"},
            {"id": "s-done", "name": "Done", "group": "completed"},
        ]
        self.labels = [{"id": "l-be", "name": "backend"}, {"id": "l-fe", "name": "Frontend"}, {"id": "l-bug", "name": "bug"}]
        self.estimate_points = [
            {"id": "ep-3", "key": 1, "value": "3"},
            {"id": "ep-5", "key": 2, "value": "5"},
            {"id": "ep-t", "key": 3, "value": "2h 30m"},
            {"id": "ep-m", "key": 4, "value": "M"},
        ]
        self.cycles = [
            {"id": "c-4", "name": "Sprint 4", "start_date": str(TODAY - timedelta(days=3)), "end_date": str(TODAY + timedelta(days=10)), "status": "current"},
            {"id": "c-3", "name": "Sprint 3", "start_date": str(TODAY - timedelta(days=20)), "end_date": str(TODAY - timedelta(days=4)), "status": "completed"},
        ]
        # Sprint 4 lists join rows ({"issue": id}); Sprint 3 lists work items.
        self.cycle_items = {"c-4": [{"id": "ci-1", "issue": "wi-1"}, {"id": "ci-2", "issue": "wi-2"}, {"id": "ci-3", "issue": "wi-3"}], "c-3": [{"id": "wi-5"}]}
        self.members = [
            {"id": "u-alex", "first_name": "Alex", "last_name": "Johnson", "email": "alex@example.com", "display_name": "alex"},
            {"id": "u-john", "first_name": "John", "last_name": "Smith", "email": "john@example.com", "display_name": "john"},
            {"id": "u-priya", "first_name": "", "last_name": "", "email": "priya@example.com", "display_name": "Priya Shah"},
        ]
        self.work_items = [
            {"id": "wi-1", "sequence_id": 1, "name": "Implement authentication", "description_html": "<p>OAuth &amp; <b>JWT</b></p>",
             "labels": ["l-be"], "estimate_point": "ep-3", "assignees": ["u-alex"], "state": "s-prog", "priority": "high",
             "start_date": "2026-09-28", "target_date": "2026-10-05"},
            {"id": "wi-2", "sequence_id": 2, "name": "Checkout page", "labels": ["l-fe"], "estimate_point": "ep-t",
             "assignees": ["u-john"], "state": "s-todo", "priority": "medium", "target_date": "2026-10-09"},
            {"id": "wi-3", "sequence_id": 3, "name": "Fix flaky login", "labels": ["l-bug"], "estimate_point": None,
             "assignees": [], "state": "s-todo", "priority": "none"},
            {"id": "wi-4", "sequence_id": 4, "name": "Full-stack spike", "labels": ["l-be", "l-fe"], "estimate_point": "ep-m",
             "assignees": ["u-priya"], "state": "s-todo", "priority": "low"},
            {"id": "wi-5", "sequence_id": 5, "name": "Old done work", "labels": ["l-be"], "estimate_point": "ep-5",
             "assignees": ["u-alex"], "state": "s-done", "priority": "low"},
        ]
        empty = {k: [] for k in ("blocking", "blocked_by", "duplicate", "relates_to", "start_after", "start_before", "finish_after", "finish_before")}
        self.relations = {
            "wi-1": dict(empty),
            "wi-2": {**empty, "blocked_by": ["wi-1"]},  # Plane Cloud shape
            "wi-3": {**empty, "blocked_by": [{"project_id": "p-apollo", "issue_id": "wi-2"}]},  # Plane CE shape
            "wi-4": {**empty, "blocked_by": ["wi-external"], "relates_to": ["wi-1"]},
            "wi-5": dict(empty),
        }

    def _page(self, items, request):
        page = int(request.url.params.get("cursor", "0"))
        chunk = items[page * self.page_size : (page + 1) * self.page_size]
        more = (page + 1) * self.page_size < len(items)
        return {"results": chunk, "next_cursor": str(page + 1) if more else None, "next_page_results": more, "count": len(chunk)}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(str(request.url))
        assert request.url.host == self.host
        if request.headers.get("X-API-Key") != API_KEY:
            return httpx.Response(401, json={"error": "Invalid API key"})
        assert request.url.path.startswith("/api/v1/")
        parts = request.url.path[len("/api/v1/"):].strip("/").split("/")
        if parts == ["users", "me"]:
            return httpx.Response(200, json={"id": "u-me", "display_name": "Scrum Bot", "email": "bot@example.com"})
        if parts[:2] != ["workspaces", self.slug]:
            return httpx.Response(404, json={"error": "workspace not found"})
        rest = parts[2:]
        if rest == ["members"]:
            return httpx.Response(200, json=self.members)
        if rest == ["projects"]:
            return httpx.Response(200, json=self._page([self.project], request))
        if len(rest) < 2 or rest[1] != self.project["id"]:
            return httpx.Response(404, json={"error": "project not found"})
        sub = rest[2:]
        if sub == []:
            return httpx.Response(200, json=self.project)
        if sub == ["states"]:
            return httpx.Response(200, json=self._page(self.states, request))
        if sub == ["labels"]:
            return httpx.Response(200, json=self._page(self.labels, request))
        if sub == ["cycles"]:
            return httpx.Response(200, json=self._page(self.cycles, request))
        if len(sub) == 3 and sub[0] == "cycles" and sub[2] == "cycle-issues":
            return httpx.Response(200, json=self._page(self.cycle_items.get(sub[1], []), request))
        if sub == ["work-items"]:
            return httpx.Response(200, json=self._page(self.work_items, request))
        if len(sub) == 3 and sub[0] == "work-items" and sub[2] == "relations":
            if not self.relations_available:
                return httpx.Response(404, json={"error": "not found"})
            return httpx.Response(200, json=self.relations.get(sub[1], {}))
        if sub == ["estimates", "est-1", "estimate-points"]:
            return httpx.Response(200, json=self.estimate_points)
        return httpx.Response(404, json={"error": "unknown path"})


@pytest.fixture
def fake():
    return FakePlane()


@pytest.fixture
def plane(isolated_services, tmp_path, fake):
    service = PlaneService(tmp_path / "plane-state.json", isolated_services["projects"], transport=httpx.MockTransport(fake))
    app.dependency_overrides[get_plane_service] = lambda: service
    return service


@pytest.fixture
def client(plane):
    return TestClient(app)


def connect(client, base_url="https://api.plane.so", api_key=API_KEY, slug="acme"):
    return client.post("/api/integrations/plane/connect", json={"base_url": base_url, "api_key": api_key, "workspace_slug": slug})


def imported(client):
    assert connect(client).status_code == 200
    report = client.post("/api/plane/projects/p-apollo/import")
    assert report.status_code == 200, report.text
    return report.json()


def tasks_by_title(client, project_id):
    return {t["title"]: t for t in client.get(f"/api/projects/{project_id}/tasks").json()}


def person(name, role="Backend Developer", skills=("Python", "FastAPI")):
    return {"name": name, "current_role": role, "skills": list(skills), "experience_years": 4, "available_roles": [],
            "current_workload_hours": 20, "weekly_available_hours": 40}


def team(client, *people):
    res = client.post("/api/employees/import", json={"employees": list(people), "generate_twins": True})
    return [e["employee_id"] for e in res.json()["created"]]


def map_user(client, plane_user_id, employee_id=None, action="match"):
    res = client.put("/api/plane/members/mapping", json={"plane_user_id": plane_user_id, "action": action, "employee_id": employee_id})
    assert res.status_code == 200, res.text
    return {m["plane_user_id"]: m for m in res.json()}


# 1 -------------------------------------------------------------------------------


def test_connection_success(client):
    assert client.get("/api/integrations/plane/status").json()["configured"] is False
    status = connect(client).json()
    assert status["connected"] is True
    assert status["user"] == "Scrum Bot"
    assert status["config_source"] == "saved"
    assert status["api_key_hint"] == "…6789"
    assert API_KEY not in str(status)
    assert client.get("/api/integrations/plane/status").json()["connected"] is True
    assert client.delete("/api/integrations/plane/connect").status_code == 204
    assert client.get("/api/integrations/plane/status").json()["configured"] is False


# 2 -------------------------------------------------------------------------------


def test_invalid_credentials_are_rejected_and_not_saved(client):
    res = connect(client, api_key="wrong-key")
    assert res.status_code == 400
    assert "rejected the API key" in res.json()["detail"]
    assert client.get("/api/integrations/plane/status").json()["configured"] is False
    assert client.get("/api/plane/projects").status_code == 503


def test_unknown_workspace_is_rejected(client):
    res = connect(client, slug="nope")
    assert res.status_code == 502
    assert "workspace 'nope' not found" in res.json()["detail"]


def test_config_validation(client):
    assert connect(client, base_url="ftp://plane").status_code == 422
    assert connect(client, slug="bad slug!").status_code == 422


def test_environment_config_takes_precedence(isolated_services, tmp_path, fake):
    env = PlaneConfig(base_url="https://api.plane.so", api_key=API_KEY, workspace_slug="acme")
    service = PlaneService(tmp_path / "p.json", isolated_services["projects"], env_config=env, transport=httpx.MockTransport(fake))
    app.dependency_overrides[get_plane_service] = lambda: service
    client = TestClient(app)
    assert client.get("/api/integrations/plane/status").json()["config_source"] == "env"
    assert connect(client).status_code == 400


# 3 -------------------------------------------------------------------------------


def test_self_hosted_base_url(isolated_services, tmp_path):
    fake = FakePlane(host="plane.acme.internal")
    service = PlaneService(tmp_path / "p.json", isolated_services["projects"], transport=httpx.MockTransport(fake))
    app.dependency_overrides[get_plane_service] = lambda: service
    client = TestClient(app)
    status = connect(client, base_url="https://plane.acme.internal/api/v1/").json()
    assert status["connected"] is True
    assert status["base_url"] == "https://plane.acme.internal"
    assert all(call.startswith("https://plane.acme.internal/api/v1/") for call in fake.calls)


# 4 -------------------------------------------------------------------------------


def test_project_retrieval(client):
    connect(client)
    projects = client.get("/api/plane/projects").json()
    assert projects == [
        {"plane_project_id": "p-apollo", "name": "Apollo", "identifier": "APOLLO", "description": "Payments & checkout", "imported_project_id": None}
    ]
    detail = client.get("/api/plane/projects/p-apollo").json()
    assert [c["name"] for c in detail["cycles"]] == ["Sprint 4", "Sprint 3"]
    assert client.get("/api/plane/projects/missing").status_code == 404
    report = client.post("/api/plane/projects/p-apollo/import").json()
    assert client.get("/api/plane/projects").json()[0]["imported_project_id"] == report["project_id"]


# 5 -------------------------------------------------------------------------------


def test_work_item_retrieval_across_pages(client, fake):
    report = imported(client)
    assert report["created"] == 5
    # page size 2 -> work items fetched over 3 pages
    assert sum("/work-items/?" in c and "cursor=" in c for c in fake.calls) == 2
    summary = next(p for p in client.get("/api/projects").json() if p["project_id"] == report["project_id"])
    assert (summary["source"], summary["name"], summary["identifier"], summary["task_count"], summary["open_task_count"]) == ("plane", "Apollo", "APOLLO", 5, 4)


# 6 -------------------------------------------------------------------------------


def test_cycle_retrieval(client):
    report = imported(client)
    detail = client.get(f"/api/projects/{report['project_id']}").json()
    assert detail["current_cycle"]["name"] == "Sprint 4"
    tasks = tasks_by_title(client, report["project_id"])
    assert tasks["Implement authentication"]["cycle_id"] == "c-4"  # via join row
    assert tasks["Old done work"]["cycle_id"] == "c-3"  # via work-item row
    assert tasks["Full-stack spike"]["cycle_id"] is None
    # Scope the simulation to Sprint 4.
    res = client.put(f"/api/projects/{report['project_id']}/settings", json={"cycle_id": "c-4", "hours_per_point": None, "include_completed": False})
    in_sim = {t["title"] for t in res.json()["tasks"] if t["in_simulation"]}
    assert in_sim == {"Checkout page"}  # wi-1 has points (no conversion), wi-3 has no estimate
    assert client.put(f"/api/projects/{report['project_id']}/settings", json={"cycle_id": "nope"}).status_code == 400


# 7 -------------------------------------------------------------------------------


def test_normalization(client):
    report = imported(client)
    t = tasks_by_title(client, report["project_id"])["Implement authentication"]
    assert t["task_id"] == "APOLLO-1"
    assert t["source"] == "plane" and t["source_task_id"] == "wi-1"
    assert t["description"] == "OAuth & JWT"
    assert (t["task_type"], t["task_type_origin"], t["effective_task_type"]) == ("Backend", "label", "Backend")
    assert (t["priority"], t["status"], t["status_group"]) == ("high", "In Progress", "started")
    assert (t["start_date"], t["deadline"]) == ("2026-09-28", "2026-10-05")
    assert t["source_assignee_ids"] == ["u-alex"]
    assert t["assigned_employee_id"] is None  # no mapping yet: Plane IDs never become employee IDs
    assert tasks_by_title(client, report["project_id"])["Fix flaky login"]["priority"] is None


def test_normalize_work_item_pure():
    task = normalize_work_item(
        {"id": "x", "sequence_id": 9, "name": "API", "labels": [{"id": "l", "name": "Backend API"}], "assignees": [{"id": "u1"}],
         "state": {"id": "s", "name": "Todo", "group": "unstarted"}, "estimate_point": {"value": "1h"}},
        identifier="ABC", states={}, labels={}, estimate_points={}, cycle_of={},
    )
    assert (task["task_id"], task["task_type"], task["estimate_kind"], task["estimate_value"], task["source_assignee_ids"]) == ("ABC-9", "Backend", "time", 1.0, ["u1"])


# 8 -------------------------------------------------------------------------------


def test_estimate_conversion(client):
    report = imported(client)
    pid = report["project_id"]
    tasks = tasks_by_title(client, pid)
    auth, checkout = tasks["Implement authentication"], tasks["Checkout page"]
    assert (auth["estimate_kind"], auth["estimate_raw"], auth["estimate_value"]) == ("points", "3", 3.0)
    assert auth["effort_estimate_hours"] is None  # points are never treated as hours
    assert "estimate is 3 points" in auth["issues"][0]
    assert (checkout["estimate_kind"], checkout["effort_estimate_hours"], checkout["effort_source"]) == ("time", 2.5, "plane_time")

    detail = client.put(f"/api/projects/{pid}/settings", json={"hours_per_point": 2}).json()
    auth = next(t for t in detail["tasks"] if t["task_id"] == "APOLLO-1")
    assert (auth["effort_estimate_hours"], auth["effort_source"]) == (6.0, "points")


def test_parse_estimate():
    assert parse_estimate("5") == ("points", "5", 5.0)
    assert parse_estimate("1h 30m") == ("time", "1h 30m", 1.5)
    assert parse_estimate("45m") == ("time", "45m", 0.75)
    assert parse_estimate("XL") == ("category", "XL", None)


# 9 -------------------------------------------------------------------------------


def test_missing_estimate_handling(client):
    report = imported(client)
    pid = report["project_id"]
    tasks = tasks_by_title(client, pid)
    flaky, spike = tasks["Fix flaky login"], tasks["Full-stack spike"]
    assert flaky["estimate_kind"] is None and flaky["effort_estimate_hours"] is None
    assert "no hour estimate; enter hours" in flaky["issues"]
    assert (spike["estimate_kind"], spike["estimate_raw"]) == ("category", "M")
    assert "estimate 'M' is a category, not hours; enter hours" in spike["issues"]

    sim = client.post(f"/api/projects/{pid}/simulate", json={"mode": "status_snapshot"}).json()
    excluded = {t["task_id"] for t in sim["context"]["excluded_tasks"]}
    assert excluded == {"APOLLO-1", "APOLLO-3", "APOLLO-4"}
    assert any("excluded from simulation: no hour estimate" in w for w in sim["analysis"]["warnings"])

    client.put(f"/api/projects/{pid}/tasks/APOLLO-3/overrides", json={"task_type": "Testing", "effort_hours": 3})
    fixed = tasks_by_title(client, pid)["Fix flaky login"]
    assert (fixed["effort_estimate_hours"], fixed["effort_source"], fixed["issues"]) == (3.0, "override", [])


# 10 ------------------------------------------------------------------------------


def test_missing_task_type_handling(client):
    report = imported(client)
    pid = report["project_id"]
    tasks = tasks_by_title(client, pid)
    assert tasks["Fix flaky login"]["effective_task_type"] is None
    assert "task type unknown; pick one" in tasks["Fix flaky login"]["issues"]
    assert tasks["Full-stack spike"]["task_type_candidates"] == ["Backend", "Frontend"]
    assert "task type ambiguous (Backend, Frontend); pick one" in tasks["Full-stack spike"]["issues"]

    client.put(f"/api/projects/{pid}/tasks/APOLLO-3/overrides", json={"effort_hours": 2})
    sim = client.post(f"/api/projects/{pid}/simulate", json={"mode": "status_snapshot"}).json()
    task_types = {t["task_id"]: t["task_type"] for t in sim["payload"]["backlog"]}
    assert task_types["APOLLO-3"] == "Unknown"
    assert any("APOLLO-3: task type unknown" in w for w in sim["analysis"]["warnings"])

    assert client.put(f"/api/projects/{pid}/tasks/APOLLO-3/overrides", json={"task_type": "Cooking"}).status_code == 422
    client.put(f"/api/projects/{pid}/tasks/APOLLO-3/overrides", json={"task_type": "Testing", "effort_hours": 2})
    assert tasks_by_title(client, pid)["Fix flaky login"]["task_type_source"] == "override"


# 11 ------------------------------------------------------------------------------


def test_employee_mapping(client):
    report = imported(client)
    alex, priya = team(client, person("Alex Johnson"), person("Priya Shah", "Frontend Developer", ["React"]))
    members = {m["plane_user_id"]: m for m in client.get("/api/plane/members").json()}
    # Suggestions are offered, never applied automatically.
    assert (members["u-alex"]["status"], members["u-alex"]["suggested_employee_id"]) == ("unmatched", alex)
    assert members["u-priya"]["suggested_employee_id"] == priya
    assert members["u-alex"]["assigned_task_count"] == 2

    members = map_user(client, "u-alex", alex)
    assert (members["u-alex"]["status"], members["u-alex"]["employee_id"]) == ("matched", alex)
    auth = tasks_by_title(client, report["project_id"])["Implement authentication"]
    assert (auth["assigned_employee_id"], auth["assignment_source"]) == (alex, "plane")

    assert client.put("/api/plane/members/mapping", json={"plane_user_id": "u-alex", "action": "match", "employee_id": "emp_999"}).status_code == 400
    assert client.put("/api/plane/members/mapping", json={"plane_user_id": "u-ghost", "action": "match", "employee_id": alex}).status_code == 400

    # Manual override beats Plane, and can be reset to follow Plane again.
    pid = report["project_id"]
    client.put(f"/api/projects/{pid}/assignment", json={"changes": [{"task_id": "APOLLO-1", "assigned_employee_id": priya}]})
    assert tasks_by_title(client, pid)["Implement authentication"]["assignment_source"] == "manual"
    client.put(f"/api/projects/{pid}/assignment", json={"changes": [{"task_id": "APOLLO-1", "follow_source": True}]})
    assert tasks_by_title(client, pid)["Implement authentication"]["assigned_employee_id"] == alex


# 12 ------------------------------------------------------------------------------


def test_unmatched_plane_users(client):
    report = imported(client)
    members = {m["plane_user_id"]: m for m in client.get("/api/plane/members").json()}
    assert members["u-john"]["status"] == "unmatched" and members["u-john"]["suggested_employee_id"] is None
    checkout = tasks_by_title(client, report["project_id"])["Checkout page"]
    assert checkout["assigned_employee_id"] is None
    assert "source assignee not matched to a PulseGuard employee" in checkout["issues"]
    assert client.get("/api/employees").json() == []  # no employees are created silently

    members = map_user(client, "u-john", action="leave_unassigned")
    assert members["u-john"]["status"] == "left_unassigned"
    members = map_user(client, "u-john", action="clear")
    assert members["u-john"]["status"] == "unmatched"


# 13 ------------------------------------------------------------------------------


def test_sync_updates_without_duplicates(client, fake):
    report = imported(client)
    pid = report["project_id"]
    client.put(f"/api/projects/{pid}/tasks/APOLLO-3/overrides", json={"task_type": "Testing", "effort_hours": 4})

    fake.work_items[0]["name"] = "Implement authentication v2"
    fake.work_items = [w for w in fake.work_items if w["id"] != "wi-5"]
    fake.work_items.append({"id": "wi-6", "sequence_id": 6, "name": "Rate limiting", "labels": ["l-be"], "estimate_point": "ep-t", "assignees": [], "state": "s-todo"})

    res = client.post(f"/api/projects/{pid}/sync")
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["report"]["project_id"], body["report"]["created"], body["report"]["updated"], body["report"]["removed"]) == (pid, 1, 4, 1)
    assert len(client.get("/api/projects").json()) == 2  # local + one Plane project
    tasks = tasks_by_title(client, pid)
    assert len(tasks) == 5
    assert tasks["Implement authentication v2"]["task_id"] == "APOLLO-1"
    assert tasks["Rate limiting"]["task_id"] == "APOLLO-6"
    assert "Old done work" not in tasks
    # User corrections survive the sync.
    assert (tasks["Fix flaky login"]["effective_task_type"], tasks["Fix flaky login"]["effort_estimate_hours"]) == ("Testing", 4.0)
    # Importing again by Plane project ID also syncs instead of duplicating.
    assert client.post("/api/plane/projects/p-apollo/import").json()["project_id"] == pid


# 14 ------------------------------------------------------------------------------


def test_dependency_preservation(client):
    report = imported(client)
    pid = report["project_id"]
    tasks = {t["task_id"]: t for t in client.get(f"/api/projects/{pid}/tasks").json()}
    assert tasks["APOLLO-2"]["dependencies"] == ["APOLLO-1"]  # Cloud shape (IDs)
    assert tasks["APOLLO-3"]["dependencies"] == ["APOLLO-2"]  # CE shape ({issue_id})
    assert tasks["APOLLO-4"]["dependencies"] == []  # relates_to is not a dependency
    assert tasks["APOLLO-4"]["external_dependency_ids"] == ["wi-external"]
    assert all(t["relations_synced"] for t in tasks.values())

    client.put(f"/api/projects/{pid}/settings", json={"hours_per_point": 2})
    client.put(f"/api/projects/{pid}/tasks/APOLLO-3/overrides", json={"task_type": "Testing", "effort_hours": 2})
    backlog = {t["task_id"]: t for t in client.post(f"/api/projects/{pid}/simulate", json={"mode": "status_snapshot"}).json()["payload"]["backlog"]}
    # Chain APOLLO-1 -> APOLLO-2 -> APOLLO-3 reaches the engine intact.
    assert backlog["APOLLO-2"]["dependencies"] == ["APOLLO-1"]
    assert backlog["APOLLO-3"]["dependencies"] == ["APOLLO-2"]


def test_relations_unavailable_is_reported_not_fabricated(client, fake):
    fake.relations_available = False
    report = imported(client)
    assert any("does not expose work-item relations" in n for n in report["notes"])
    assert all(t["dependencies"] == [] for t in client.get(f"/api/projects/{report['project_id']}/tasks").json())


def test_relation_fetches_respect_rate_budget(client, fake):
    fake.work_items += [
        {"id": f"wi-x{i}", "sequence_id": 100 + i, "name": f"Bulk {i}", "labels": [], "assignees": [], "state": "s-todo"} for i in range(60)
    ]
    report = imported(client)
    assert any("sync again in a minute" in n for n in report["notes"])
    assert len(fake.calls) <= 60
    first = sum(t["relations_synced"] for t in client.get(f"/api/projects/{report['project_id']}/tasks").json())
    client.post(f"/api/projects/{report['project_id']}/sync")
    second = sum(t["relations_synced"] for t in client.get(f"/api/projects/{report['project_id']}/tasks").json())
    assert second > first  # the next sync continues with items not read yet


def test_relation_ids_shapes():
    assert relation_ids(["a", {"issue_id": "b"}, {"project_id": "p"}, None]) == ["a", "b"]


# 15 ------------------------------------------------------------------------------


def test_imported_project_runs_through_analysis_engine(client):
    report = imported(client)
    pid = report["project_id"]
    alex, priya, qa = team(
        client, person("Alex Johnson"), person("Priya Shah", "Frontend Developer", ["React"]), person("Dana QA", "QA Engineer", ["Pytest"])
    )
    map_user(client, "u-alex", alex)
    map_user(client, "u-priya", priya)
    client.put(f"/api/projects/{pid}/settings", json={"hours_per_point": 2})
    client.put(f"/api/projects/{pid}/tasks/APOLLO-3/overrides", json={"task_type": "Testing", "effort_hours": 3})
    client.put(f"/api/projects/{pid}/tasks/APOLLO-4/overrides", json={"task_type": "Frontend", "effort_hours": 5})
    client.post(f"/api/projects/{pid}/auto-assign")

    sim = client.post(f"/api/projects/{pid}/simulate", json={"mode": "optimize_fastest"}).json()
    payload = sim["payload"]
    assert {t["task_id"] for t in payload["backlog"]} == {"APOLLO-1", "APOLLO-2", "APOLLO-3", "APOLLO-4"}
    assert sim["context"]["unassigned_task_ids"] == []
    assert sim["analysis"]["delta_metrics"] is not None

    res = client.post("/api/ai-twins/analyze", json=payload)
    assert res.status_code == 200, res.text
    assert res.json() == sim["analysis"] | {"warnings": res.json()["warnings"]}
    assert {e["employee_id"] for e in res.json()["employees"]} == {alex, priya, qa}
