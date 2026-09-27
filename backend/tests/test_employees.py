import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_employee_service
from app.services.employee_service import EmployeeService


@pytest.fixture
def client(tmp_path):
    service = EmployeeService(tmp_path / "team.json")
    app.dependency_overrides[get_employee_service] = lambda: service
    yield TestClient(app)


def alex(**overrides):
    data = {
        "name": "Alex Johnson",
        "current_role": "Backend Developer",
        "skills": ["Python", "FastAPI", "PostgreSQL"],
        "experience_years": 3,
        "available_roles": ["Backend Developer", "API Integration"],
        "current_workload_hours": 24,
        "weekly_available_hours": 40,
    }
    data.update(overrides)
    return data


def create(client, **overrides):
    res = client.post("/api/employees", json=alex(**overrides))
    assert res.status_code == 201, res.text
    return res.json()


def test_empty_team(client):
    res = client.get("/api/employees")
    assert res.status_code == 200
    assert res.json() == []


def test_create_employee(client):
    emp = create(client)
    assert emp["employee_id"] == "emp_001"
    assert emp["name"] == "Alex Johnson"
    assert emp["source"] == "manual"
    assert emp["twin_status"] == "not_generated"


def test_backend_generates_ids_ignoring_client_id(client):
    res = client.post("/api/employees", json={**alex(), "employee_id": "hacked"})
    assert res.json()["employee_id"] == "emp_001"
    assert create(client)["employee_id"] == "emp_002"


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": ""},
        {"name": "   "},
        {"current_role": ""},
        {"experience_years": -1},
        {"current_workload_hours": -5},
        {"weekly_available_hours": 0},
        {"weekly_available_hours": 200},
    ],
)
def test_rejects_invalid_employee(client, overrides):
    res = client.post("/api/employees", json=alex(**overrides))
    assert res.status_code == 422
    assert client.get("/api/employees").json() == []


def test_rejects_missing_required_fields(client):
    res = client.post("/api/employees", json={"skills": ["Python"]})
    assert res.status_code == 422


def test_list_employees(client):
    create(client)
    create(client, name="Priya Shah", current_role="Frontend Developer", skills=["React"])
    names = [e["name"] for e in client.get("/api/employees").json()]
    assert names == ["Alex Johnson", "Priya Shah"]


def test_get_employee_and_404(client):
    emp = create(client)
    assert client.get(f"/api/employees/{emp['employee_id']}").json()["name"] == "Alex Johnson"
    assert client.get("/api/employees/emp_999").status_code == 404


def test_edit_employee(client):
    emp = create(client)
    res = client.put(f"/api/employees/{emp['employee_id']}", json=alex(name="Alex J.", current_workload_hours=30))
    assert res.status_code == 200
    assert res.json()["name"] == "Alex J."
    assert client.get(f"/api/employees/{emp['employee_id']}").json()["current_workload_hours"] == 30
    assert client.put("/api/employees/emp_999", json=alex()).status_code == 404


def test_edit_rejects_invalid_data(client):
    emp = create(client)
    res = client.put(f"/api/employees/{emp['employee_id']}", json=alex(current_role=" "))
    assert res.status_code == 422
    assert client.get(f"/api/employees/{emp['employee_id']}").json()["current_role"] == "Backend Developer"


def test_delete_employee(client):
    emp = create(client)
    client.post(f"/api/employees/{emp['employee_id']}/generate-twin")
    assert client.delete(f"/api/employees/{emp['employee_id']}").status_code == 204
    assert client.get("/api/employees").json() == []
    assert client.get(f"/api/employees/{emp['employee_id']}/twin").status_code == 404
    assert client.delete(f"/api/employees/{emp['employee_id']}").status_code == 404
    # IDs are not reused after deletion.
    assert create(client)["employee_id"] == "emp_002"


def test_multiple_available_roles(client):
    emp = create(client, available_roles=["API Integration", "Testing", "api integration", ""])
    # Current role is kept available, blanks and case-insensitive duplicates are dropped.
    assert emp["available_roles"] == ["Backend Developer", "API Integration", "Testing"]
    twin = client.post(f"/api/employees/{emp['employee_id']}/generate-twin").json()
    assert [r["role"] for r in twin["role_compatibility"]] == ["Backend Developer", "API Integration", "Testing"]


def test_multiple_skills(client):
    emp = create(client, skills=["Python", "FastAPI", "PostgreSQL", "Docker", "React", "python"])
    assert emp["skills"] == ["Python", "FastAPI", "PostgreSQL", "Docker", "React"]
    twin = client.post(f"/api/employees/{emp['employee_id']}/generate-twin").json()
    fit = {f["task_type"]: f for f in twin["task_type_fit"]}
    assert set(fit["Backend"]["matched_signals"]) >= {"Python", "FastAPI", "PostgreSQL"}
    assert fit["DevOps"]["matched_signals"] == ["Docker"]
    assert fit["Frontend"]["matched_signals"] == ["React"]


def test_generate_twin(client):
    emp = create(client)
    res = client.post(f"/api/employees/{emp['employee_id']}/generate-twin")
    assert res.status_code == 200
    twin = res.json()
    assert twin["parameter_basis"] == "estimated_defaults"
    assert twin["skills"] == ["Python", "FastAPI", "PostgreSQL"]
    assert twin["overtime_hours_last_7d"] == 0
    assert twin["simulation_profile"]["capacity_used_pct"] == 60
    fit = {f["task_type"]: f["compatibility_pct"] for f in twin["task_type_fit"]}
    assert fit["Backend"] == 100
    assert fit["Frontend"] < fit["Backend"]
    roles = {r["role"]: r["compatibility_pct"] for r in twin["role_compatibility"]}
    assert roles == {"Backend Developer": 100, "API Integration": 100}
    assert client.get(f"/api/employees/{emp['employee_id']}/twin").json() == twin
    assert client.get(f"/api/employees/{emp['employee_id']}").json()["twin_status"] == "generated"


def test_twin_before_generation_and_unknown_employee(client):
    emp = create(client)
    assert client.get(f"/api/employees/{emp['employee_id']}/twin").status_code == 404
    assert client.post("/api/employees/emp_999/generate-twin").status_code == 404


def test_twin_is_deterministic(client):
    emp = create(client)
    first = client.post(f"/api/employees/{emp['employee_id']}/generate-twin").json()
    second = client.post(f"/api/employees/{emp['employee_id']}/generate-twin").json()
    assert first == second


def test_twin_has_employee_id(client):
    create(client)
    emp = create(client, name="Priya Shah")
    twin = client.post(f"/api/employees/{emp['employee_id']}/generate-twin").json()
    assert twin["employee_id"] == emp["employee_id"] == "emp_002"


def test_edit_marks_twin_outdated_until_regenerated(client):
    emp = create(client)
    eid = emp["employee_id"]
    client.post(f"/api/employees/{eid}/generate-twin")
    client.put(f"/api/employees/{eid}", json=alex(current_workload_hours=50))
    assert client.get(f"/api/employees/{eid}").json()["twin_status"] == "outdated"
    twin = client.post(f"/api/employees/{eid}/generate-twin").json()
    assert twin["overtime_hours_last_7d"] == 10
    assert client.get(f"/api/employees/{eid}").json()["twin_status"] == "generated"


def test_twin_passes_into_analysis_engine(client):
    backend = create(client)
    frontend = create(client, name="Priya Shah", current_role="Frontend Developer", skills=["React", "TypeScript"],
                      available_roles=["Frontend Developer"])
    twins = [client.post(f"/api/employees/{e['employee_id']}/generate-twin").json() for e in (backend, frontend)]

    payload = {
        "employees": twins,
        "backlog": [
            {"task_id": "T1", "task_type": "Backend", "dependencies": [], "effort_estimate_hours": 8, "deadline": None},
            {"task_id": "T2", "task_type": "Frontend", "dependencies": ["T1"], "effort_estimate_hours": 6, "deadline": None},
        ],
        "current_assignment": [
            {"task_id": "T1", "assigned_employee_id": backend["employee_id"]},
            {"task_id": "T2", "assigned_employee_id": frontend["employee_id"]},
        ],
    }
    for mode in ("status_snapshot", "optimize_fastest", "resolve_burnout_all"):
        res = client.post("/api/ai-twins/analyze", json={**payload, "mode": mode})
        assert res.status_code == 200, res.text
        body = res.json()
        # No warning may point at missing twin data. (A zero-overtime team can
        # still yield the engine's own "burnout_mitigation_pct unavailable".)
        assert not [w for w in body["warnings"] if "emp_" in w]
        assert {e["employee_id"] for e in body["employees"]} == {"emp_001", "emp_002"}
        assert all(e["compatibility_pct"] == 100 for e in body["employees"])


def test_persists_across_service_instances(tmp_path):
    from app.models.employee import EmployeeInput

    path = tmp_path / "team.json"
    EmployeeService(path).create(EmployeeInput(**alex()))
    assert [e.name for e in EmployeeService(path).list()] == ["Alex Johnson"]
