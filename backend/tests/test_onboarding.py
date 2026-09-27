import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_employee_service, get_slack_client
from app.services.employee_service import EmployeeService
from app.services.slack_client import SlackClient

SLACK_USERS = [
    {"id": "U001", "real_name": "Alex Johnson", "profile": {"real_name": "Alex Johnson", "title": "Backend Developer"}},
    {"id": "U002", "profile": {"real_name": "Priya Shah", "title": ""}},
    {"id": "U003", "profile": {"real_name": "Old Account"}, "deleted": True},
    {"id": "B001", "profile": {"real_name": "Deploy Bot"}, "is_bot": True},
    {"id": "USLACKBOT", "profile": {"real_name": "Slackbot"}},
    {"id": "U004", "profile": {"real_name": "Diego Ramos", "title": "QA Engineer"}},
]


def slack_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["Authorization"] == "Bearer xoxb-test"
    method = request.url.path.rsplit("/", 1)[-1]
    if method == "auth.test":
        return httpx.Response(200, json={"ok": True, "team": "Acme"})
    if method == "users.list":
        # Two pages to exercise cursor pagination.
        if request.url.params.get("cursor") == "page2":
            return httpx.Response(200, json={"ok": True, "members": SLACK_USERS[3:], "response_metadata": {"next_cursor": ""}})
        return httpx.Response(200, json={"ok": True, "members": SLACK_USERS[:3], "response_metadata": {"next_cursor": "page2"}})
    if method == "users.info":
        user = next((u for u in SLACK_USERS if u["id"] == request.url.params["user"]), None)
        if user is None:
            return httpx.Response(200, json={"ok": False, "error": "user_not_found"})
        return httpx.Response(200, json={"ok": True, "user": user})
    return httpx.Response(404)


@pytest.fixture
def service(tmp_path):
    return EmployeeService(tmp_path / "team.json")


@pytest.fixture
def client(service):
    app.dependency_overrides[get_employee_service] = lambda: service
    app.dependency_overrides[get_slack_client] = lambda: SlackClient("xoxb-test", transport=httpx.MockTransport(slack_handler))
    yield TestClient(app)


def row(**overrides):
    data = {
        "name": "Alex Johnson",
        "current_role": "Backend Developer",
        "skills": ["Python", "FastAPI"],
        "experience_years": 3,
        "available_roles": [],
        "current_workload_hours": 24,
        "weekly_available_hours": 40,
    }
    data.update(overrides)
    return data


def slack_row(slack_user_id, **overrides):
    data = {"slack_user_id": slack_user_id, "experience_years": 4, "current_workload_hours": 30, "weekly_available_hours": 40}
    data.update(overrides)
    return data


# ---------------------------------------------------------------- JSON import


def test_json_import_creates_employees(client):
    res = client.post("/api/employees/import", json={"employees": [row(), row(name="Priya Shah", current_role="Frontend Developer")]})
    assert res.status_code == 200, res.text
    created = res.json()["created"]
    assert [e["employee_id"] for e in created] == ["emp_001", "emp_002"]
    assert all(e["source"] == "json_import" and e["twin_status"] == "not_generated" for e in created)
    assert len(client.get("/api/employees").json()) == 2


def test_json_import_can_generate_twins(client):
    res = client.post("/api/employees/import", json={"employees": [row()], "generate_twins": True})
    assert res.json()["created"][0]["twin_status"] == "generated"
    twin = client.get("/api/employees/emp_001/twin").json()
    # Same generator as manual creation.
    manual = client.post("/api/employees", json=row()).json()
    assert client.post(f"/api/employees/{manual['employee_id']}/generate-twin").json()["historical_task_velocity"] == twin["historical_task_velocity"]


def test_json_import_is_all_or_nothing(client):
    res = client.post("/api/employees/import", json={"employees": [row(), row(name=""), row(weekly_available_hours=0)]})
    assert res.status_code == 422
    locs = [d["loc"] for d in res.json()["detail"]]
    assert ["body", "employees", 1, "name"] in locs
    assert ["body", "employees", 2, "weekly_available_hours"] in locs
    assert client.get("/api/employees").json() == []


def test_json_import_rejects_empty_list(client):
    assert client.post("/api/employees/import", json={"employees": []}).status_code == 422


# ---------------------------------------------------------------- removal


def test_bulk_delete(client):
    client.post("/api/employees/import", json={"employees": [row(), row(name="B"), row(name="C")], "generate_twins": True})
    res = client.post("/api/employees/bulk-delete", json={"employee_ids": ["emp_001", "emp_003", "emp_999"]})
    assert res.json() == {"deleted": ["emp_001", "emp_003"], "not_found": ["emp_999"]}
    assert [e["employee_id"] for e in client.get("/api/employees").json()] == ["emp_002"]
    assert client.get("/api/employees/emp_001/twin").status_code == 404


def test_bulk_delete_rejects_empty(client):
    assert client.post("/api/employees/bulk-delete", json={"employee_ids": []}).status_code == 422


# ---------------------------------------------------------------- Slack


def test_slack_status_not_configured(client):
    app.dependency_overrides[get_slack_client] = lambda: None
    assert client.get("/api/integrations/slack/status").json() == {"configured": False, "connected": False, "workspace": None, "error": None}
    assert client.get("/api/integrations/slack/members").status_code == 503


def test_slack_status_connected(client):
    body = client.get("/api/integrations/slack/status").json()
    assert body["connected"] is True and body["workspace"] == "Acme"


def test_slack_status_reports_auth_error(client):
    bad = httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": False, "error": "invalid_auth"}))
    app.dependency_overrides[get_slack_client] = lambda: SlackClient("xoxb-test", transport=bad)
    body = client.get("/api/integrations/slack/status").json()
    assert body == {"configured": True, "connected": False, "workspace": None, "error": "invalid_auth"}
    assert client.get("/api/integrations/slack/members").status_code == 502


def test_slack_members_paginates_and_filters_non_people(client):
    members = client.get("/api/integrations/slack/members").json()
    assert [m["slack_user_id"] for m in members] == ["U001", "U004", "U002"]  # sorted by name
    assert members[0]["title"] == "Backend Developer"
    assert members[2]["title"] is None


def test_slack_import_uses_slack_identity(client):
    res = client.post(
        "/api/integrations/slack/import",
        json={"members": [slack_row("U001", skills=["Python"]), slack_row("U002", current_role="Frontend Developer")], "generate_twins": True},
    )
    assert res.status_code == 200, res.text
    created = res.json()["created"]
    assert [(e["name"], e["current_role"], e["source"]) for e in created] == [
        ("Alex Johnson", "Backend Developer", "slack"),  # role defaults to Slack title
        ("Priya Shah", "Frontend Developer", "slack"),
    ]
    assert created[0]["external_ref"] == "slack:U001"
    assert all(e["twin_status"] == "generated" for e in created)

    members = {m["slack_user_id"]: m for m in client.get("/api/integrations/slack/members").json()}
    assert members["U001"]["existing_employee_id"] == "emp_001"
    assert members["U004"]["existing_employee_id"] is None


def test_slack_import_skips_already_imported(client):
    client.post("/api/integrations/slack/import", json={"members": [slack_row("U001")]})
    res = client.post("/api/integrations/slack/import", json={"members": [slack_row("U001"), slack_row("U004")]})
    body = res.json()
    assert [e["name"] for e in body["created"]] == ["Diego Ramos"]
    assert body["skipped"] == [{"ref": "slack:U001", "name": "Alex Johnson", "reason": "already on the team"}]


def test_slack_import_requires_role_when_slack_has_no_title(client):
    res = client.post("/api/integrations/slack/import", json={"members": [slack_row("U004"), slack_row("U002")]})
    assert res.status_code == 422
    assert res.json()["detail"][0]["loc"] == ["body", "members", 1, "current_role"]
    assert client.get("/api/employees").json() == []


def test_slack_import_rejects_unknown_or_non_person(client):
    for user_id in ("U999", "B001"):
        res = client.post("/api/integrations/slack/import", json={"members": [slack_row(user_id)]})
        assert res.status_code == 422, user_id
    assert client.get("/api/employees").json() == []


def test_slack_employee_edit_keeps_link(client):
    client.post("/api/integrations/slack/import", json={"members": [slack_row("U001")]})
    edited = client.put("/api/employees/emp_001", json=row(current_workload_hours=10)).json()
    assert edited["source"] == "slack" and edited["external_ref"] == "slack:U001"
