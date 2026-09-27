import pytest
from fastapi.testclient import TestClient

from app.analyze import analyze
from app.main import app


LOCAL = "/api/projects/local"


@pytest.fixture
def client():
    return TestClient(app)


def person(name, role="Backend Developer", skills=("Python", "FastAPI", "PostgreSQL"), workload=30, weekly=40, exp=3, roles=()):
    return {
        "name": name,
        "current_role": role,
        "skills": list(skills),
        "experience_years": exp,
        "available_roles": list(roles),
        "current_workload_hours": workload,
        "weekly_available_hours": weekly,
    }


def task(title, task_type="Backend", effort=14, deps=()):
    return {"title": title, "task_type": task_type, "effort_estimate_hours": effort, "dependencies": list(deps)}


def add_team(client, *people, twins=True):
    res = client.post("/api/employees/import", json={"employees": list(people), "generate_twins": twins})
    assert res.status_code == 200, res.text
    return [e["employee_id"] for e in res.json()["created"]]


def add_tasks(client, *tasks):
    ids = []
    for t in tasks:
        res = client.post(f"{LOCAL}/tasks", json=t)
        assert res.status_code == 201, res.text
        ids.append(res.json()["tasks"][-1]["task_id"])
    return ids


def assignment_of(detail):
    return {t["task_id"]: t["assigned_employee_id"] for t in detail["tasks"] if t["assigned_employee_id"]}


def assign(client, mapping):
    res = client.put(f"{LOCAL}/assignment", json={"changes": [{"task_id": t, "assigned_employee_id": e} for t, e in mapping.items()]})
    assert res.status_code == 200, res.text
    return res.json()


def simulate(client, mode, target=None):
    res = client.post(f"{LOCAL}/simulate", json={"mode": mode, "target_employee_id": target})
    assert res.status_code == 200, res.text
    return res.json()


def overloaded_team(client):
    """Alex holds four 14h backend tasks on top of 30h of other work; Bob has room."""
    alex, bob = add_team(client, person("Alex"), person("Bob", workload=10))
    tasks = add_tasks(client, *(task(f"API {i}") for i in range(4)))
    assign(client, {t: alex for t in tasks})
    return alex, bob, tasks


# ---------------------------------------------------------------- backlog CRUD


def test_empty_project(client):
    projects = client.get("/api/projects").json()
    assert [(p["project_id"], p["source"], p["task_count"]) for p in projects] == [("local", "local", 0)]
    detail = client.get(LOCAL).json()
    assert detail["tasks"] == []
    assert detail["task_types"] == ["Backend", "Frontend", "Testing", "DevOps", "Data", "Design"]
    assert client.get("/api/projects/nope").status_code == 404


def test_task_crud_and_validation(client):
    t1, t2 = add_tasks(client, task("Auth"), task("UI", "Frontend", 8))
    assert (t1, t2) == ("T-001", "T-002")
    res = client.put(f"{LOCAL}/tasks/{t2}", json={**task("UI v2", "Frontend", 9), "deadline": "2026-10-01"})
    updated = next(t for t in res.json()["tasks"] if t["task_id"] == t2)
    assert updated["title"] == "UI v2" and updated["deadline"] == "2026-10-01"
    assert updated["effort_estimate_hours"] == 9 and updated["effort_source"] == "manual"
    assert client.get(f"{LOCAL}/tasks").json()[1]["task_id"] == t2
    for bad in ({"title": " "}, {"task_type": "Cooking"}, {"effort_estimate_hours": 0}):
        assert client.post(f"{LOCAL}/tasks", json={**task("x"), **bad}).status_code == 422
    assert client.put(f"{LOCAL}/tasks/T-999", json=task("x")).status_code == 404


def test_dependency_rules(client):
    t1, t2 = add_tasks(client, task("A"), task("B"))
    assert client.put(f"{LOCAL}/tasks/{t2}", json=task("B", deps=[t1])).status_code == 200
    cycle = client.put(f"{LOCAL}/tasks/{t1}", json=task("A", deps=[t2]))
    assert cycle.status_code == 400 and "cycle" in cycle.json()["detail"]
    assert client.put(f"{LOCAL}/tasks/{t1}", json=task("A", deps=[t1])).status_code == 400
    assert client.post(f"{LOCAL}/tasks", json=task("C", deps=["T-404"])).status_code == 400


def test_delete_task_cleans_dependencies_and_assignment(client):
    (alex,) = add_team(client, person("Alex"))
    t1, t2 = add_tasks(client, task("A"))[0], None
    t2 = add_tasks(client, task("B", deps=[t1]))[0]
    assign(client, {t1: alex, t2: alex})
    assert client.delete(f"{LOCAL}/tasks/{t1}").status_code == 200
    state = client.get(LOCAL).json()
    assert state["tasks"][0]["dependencies"] == []
    assert assignment_of(state) == {t2: alex}


def test_sample_backlog_only_when_empty(client):
    state = client.post(f"{LOCAL}/sample").json()
    assert len(state["tasks"]) == 8
    assert state["tasks"][7]["dependencies"] == ["T-006", "T-007"]
    assert client.post(f"{LOCAL}/sample").status_code == 400
    assert client.delete(f"{LOCAL}/tasks").status_code == 200
    assert client.get(LOCAL).json()["tasks"] == []


def test_assignment_validation_and_unassign(client):
    (alex,) = add_team(client, person("Alex"))
    (t1,) = add_tasks(client, task("A"))
    assert client.put(f"{LOCAL}/assignment", json={"changes": [{"task_id": t1, "assigned_employee_id": "emp_999"}]}).status_code == 400
    assert client.put(f"{LOCAL}/assignment", json={"changes": [{"task_id": "T-999", "assigned_employee_id": alex}]}).status_code == 400
    assign(client, {t1: alex})
    assert assignment_of(assign(client, {t1: None})) == {}


def test_deleting_employee_unassigns_their_tasks(client):
    alex, bob = add_team(client, person("Alex"), person("Bob"))
    t1, t2 = add_tasks(client, task("A"), task("B"))
    assign(client, {t1: alex, t2: bob})
    client.delete(f"/api/employees/{alex}")
    assert assignment_of(client.get(LOCAL).json()) == {t2: bob}
    client.post("/api/employees/bulk-delete", json={"employee_ids": [bob]})
    assert assignment_of(client.get(LOCAL).json()) == {}


# ---------------------------------------------------------------- simulation on the real team


def test_simulation_uses_team_twins(client):
    alex, bob, _ = overloaded_team(client)
    (carol,) = add_team(client, person("Carol"), twins=False)
    body = simulate(client, "status_snapshot")
    assert [e["employee_id"] for e in body["payload"]["employees"]] == [alex, bob]
    assert body["context"]["excluded_employees"] == [{"employee_id": carol, "name": "Carol", "reason": "no AI Twin generated"}]
    assert body["context"]["unassigned_task_ids"] == []
    scores = {e["employee_id"]: e for e in body["analysis"]["employees"]}
    assert scores[alex]["risk_level"] == "Warning"
    assert "overtime" in scores[alex]["primary_contributing_factors"]
    assert scores[bob]["risk_level"] == "Normal"


def test_stress_depends_on_assignment(client):
    alex, bob, tasks = overloaded_team(client)
    before = {e["employee_id"]: e["stress_score"] for e in simulate(client, "status_snapshot")["analysis"]["employees"]}
    assign(client, {tasks[0]: bob, tasks[1]: bob})
    after = {e["employee_id"]: e["stress_score"] for e in simulate(client, "status_snapshot")["analysis"]["employees"]}
    assert after[alex] < before[alex]


def test_swap_recommendation_is_real_and_applies(client):
    alex, bob, tasks = overloaded_team(client)
    body = simulate(client, "resolve_burnout_all")["analysis"]
    assert body["recommendations"]["role_swap_required"] is True
    (swap,) = body["recommendations"]["actionable_swaps"]
    assert swap["swap_between"] == [alex, bob]
    assert set(swap["tasks_affected"]) <= set(tasks)
    assert swap["expected_stress_reduction_pct"] > 0

    before = next(e for e in body["employees"] if e["employee_id"] == alex)["stress_score"]
    assign(client, {swap["tasks_affected"][0]: bob})
    after = next(e for e in simulate(client, "status_snapshot")["analysis"]["employees"] if e["employee_id"] == alex)
    assert after["stress_score"] < before
    assert after["risk_level"] == "Normal"


def test_swap_respects_role_coverage(client):
    alex, designer = add_team(client, person("Alex"), person("Dana", role="Product Designer", skills=["Figma"], workload=0))
    tasks = add_tasks(client, *(task(f"API {i}") for i in range(4)))
    assign(client, {t: alex for t in tasks})
    body = simulate(client, "resolve_burnout_all")["analysis"]
    assert body["recommendations"]["actionable_swaps"] == []
    assert f"no valid swap found for at-risk employee {alex}" in body["warnings"]


def test_resolve_single_for_normal_employee(client):
    _, bob, _ = overloaded_team(client)
    body = simulate(client, "resolve_burnout_single", bob)["analysis"]
    assert body["recommendations"]["actionable_swaps"] == []
    assert f"{bob} is at Normal risk; no swap is needed" in body["warnings"]


def test_optimize_balances_load_and_reports_mitigation(client):
    alex, bob, _ = overloaded_team(client)
    body = simulate(client, "optimize_fastest")["analysis"]
    delta = body["delta_metrics"]
    assert delta["velocity_boost_pct"] > 0
    assert delta["burnout_mitigation_pct"] > 0
    top = {a["assigned_employee_id"] for a in body["rotations_ranked"][0]["assignments"]}
    assert top == {alex, bob}


def test_optimize_with_unassigned_tasks_uses_search(client):
    add_team(client, person("Alex"), person("Bob"), person("Priya", role="Frontend Developer", skills=["React"]),
             person("Diego", role="QA Engineer", skills=["Pytest"]), person("Rae", role="DevOps Engineer", skills=["Docker"]))
    client.post(f"{LOCAL}/sample")
    body = simulate(client, "optimize_fastest")["analysis"]
    assert body["rotations_evaluated"] > 5
    assert len(body["rotations_ranked"]) == 5
    assert body["delta_metrics"] is None
    assert "baseline completion time unavailable: current_assignment does not cover full backlog" in body["warnings"]
    # Design task has nobody whose roles cover it.
    assert any("task_type 'Design'" in w for w in body["warnings"])


def test_auto_assign_fills_only_unassigned_with_covering_roles(client):
    alex, priya = add_team(client, person("Alex"), person("Priya", role="Frontend Developer", skills=["React"]))
    backend, ui = add_tasks(client, task("API"), task("UI", "Frontend"))
    assign(client, {backend: priya})  # manual choice is kept even if unusual
    state = client.post(f"{LOCAL}/auto-assign").json()
    assert assignment_of(state) == {backend: priya, ui: priya}


def test_auto_assign_requires_twins(client):
    add_team(client, person("Alex"), twins=False)
    add_tasks(client, task("API"))
    res = client.post(f"{LOCAL}/auto-assign")
    assert res.status_code == 400


def test_simulation_is_deterministic(client):
    overloaded_team(client)
    assert simulate(client, "optimize_fastest") == simulate(client, "optimize_fastest")


# ---------------------------------------------------------------- engine compatibility


def test_legacy_payload_without_weekly_hours_gets_no_fabricated_swap():
    payload = {
        "mode": "resolve_burnout_all",
        "backlog": [{"task_id": "T1", "task_type": "Backend", "dependencies": [], "effort_estimate_hours": 10}],
        "current_assignment": [{"task_id": "T1", "assigned_employee_id": "E1"}],
        "employees": [
            {"employee_id": "E1", "name": "A", "current_role": "Backend Dev", "available_roles": ["Backend Dev"],
             "historical_velocity": 1, "current_workload_hours": 50, "overtime_hours_last_7d": 40,
             "autonomy_score": 0.4, "cognitive_load_factor": 0.9},
            {"employee_id": "E2", "name": "B", "current_role": "Backend Dev", "available_roles": ["Backend Dev"],
             "historical_velocity": 1, "current_workload_hours": 10, "overtime_hours_last_7d": 0,
             "autonomy_score": 0.9, "cognitive_load_factor": 0.3},
        ],
    }
    result = analyze(payload)
    assert result["recommendations"]["actionable_swaps"] == []
    assert any("does not depend on task assignment" in w for w in result["warnings"])
