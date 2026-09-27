import copy

from app.analyze import analyze


def make_payload(mode="status_snapshot", target_employee_id=None):
    return {
        "mode": mode,
        "target_employee_id": target_employee_id,
        "current_assignment": [
            {"task_id": "T1", "assigned_employee_id": "E1"},
            {"task_id": "T2", "assigned_employee_id": "E2"},
            {"task_id": "T3", "assigned_employee_id": "E1"},
        ],
        "backlog": [
            {"task_id": "T1", "task_type": "Backend", "dependencies": [], "effort_estimate_hours": 10, "deadline": "2026-10-01T00:00:00Z"},
            {"task_id": "T2", "task_type": "Frontend", "dependencies": ["T1"], "effort_estimate_hours": 8, "deadline": "2026-10-02T00:00:00Z"},
            {"task_id": "T3", "task_type": "Testing", "dependencies": ["T2"], "effort_estimate_hours": 4, "deadline": "2026-10-03T00:00:00Z"},
        ],
        "employees": [
            {
                "employee_id": "E1",
                "name": "Alice",
                "current_role": "Backend Dev",
                "available_roles": ["Backend Dev", "Frontend Dev"],
                "historical_velocity": 4.0,
                "current_workload_hours": 30,
                "overtime_hours_last_7d": 12,
                "autonomy_score": 0.8,
                "cognitive_load_factor": 0.7,
                "historical_task_velocity": {"Backend": 1.2, "Frontend": 0.6, "Testing": 0.9},
            },
            {
                "employee_id": "E2",
                "name": "Bob",
                "current_role": "Frontend Dev",
                "available_roles": ["Frontend Dev", "Backend Dev"],
                "historical_velocity": 3.0,
                "current_workload_hours": 20,
                "overtime_hours_last_7d": 2,
                "autonomy_score": 0.9,
                "cognitive_load_factor": 0.4,
                "historical_task_velocity": {"Backend": 0.8, "Frontend": 1.1, "Testing": 1.0},
            },
        ],
    }


def test_status_snapshot_shape():
    result = analyze(make_payload("status_snapshot"))
    assert result["mode"] == "status_snapshot"
    assert result["rotations_ranked"] == []
    assert result["delta_metrics"] is None
    assert result["rotations_evaluated"] == 0
    for emp in result["employees"]:
        assert set(emp.keys()) == {
            "employee_id",
            "stamina",
            "stress_score",
            "risk_level",
            "compatibility_pct",
            "velocity_tasks_per_day",
            "primary_contributing_factors",
        }


def test_optimize_fastest_deterministic():
    payload = make_payload("optimize_fastest")
    r1 = analyze(copy.deepcopy(payload))
    r2 = analyze(copy.deepcopy(payload))
    assert r1 == r2
    assert r1["rotations_evaluated"] > 0
    assert len(r1["rotations_ranked"]) <= 5
    assert r1["delta_metrics"] is not None
    times = [r["total_completion_time_hours"] for r in r1["rotations_ranked"]]
    assert times == sorted(times)


def test_rotations_evaluated_matches_actual_count():
    payload = make_payload("optimize_fastest")
    result = analyze(payload)
    assert isinstance(result["rotations_evaluated"], int)
    assert result["rotations_evaluated"] >= len(result["rotations_ranked"])


def test_every_task_assigned_exactly_once_in_rotation():
    payload = make_payload("optimize_fastest")
    result = analyze(payload)
    task_ids = {t["task_id"] for t in payload["backlog"]}
    for rotation in result["rotations_ranked"]:
        assigned_ids = {a["task_id"] for a in rotation["assignments"]}
        assert assigned_ids == task_ids


def test_resolve_burnout_single_without_target_warns():
    payload = make_payload("resolve_burnout_single")
    result = analyze(payload)
    assert any("target_employee_id" in w for w in result["warnings"])
    assert result["recommendations"]["actionable_swaps"] == []


def test_resolve_burnout_all_no_fabricated_swap_when_none_valid():
    payload = make_payload("resolve_burnout_all")
    # Make E1 critical, E2 has no available_roles overlap so no valid swap possible.
    payload["employees"][0]["overtime_hours_last_7d"] = 40
    payload["employees"][1]["available_roles"] = ["Something Else Entirely"]
    result = analyze(payload)
    e1_risk = next(e for e in result["employees"] if e["employee_id"] == "E1")
    assert e1_risk["risk_level"] in ("Warning", "Critical")
    assert result["recommendations"]["actionable_swaps"] == []
    assert result["recommendations"]["role_swap_required"] is False


def test_missing_historical_task_velocity_excludes_compatibility():
    payload = make_payload("status_snapshot")
    del payload["employees"][0]["historical_task_velocity"]
    result = analyze(payload)
    e1 = next(e for e in result["employees"] if e["employee_id"] == "E1")
    assert e1["compatibility_pct"] is None
    assert any("compatibility_pct unavailable for E1" in w for w in result["warnings"])


def test_division_by_zero_handled_safely():
    payload = make_payload("status_snapshot")
    payload["employees"][0]["current_workload_hours"] = 0
    payload["employees"][0]["autonomy_score"] = 0
    result = analyze(payload)
    # autonomy_score 0 -> burnout unscoreable -> employee excluded + warning, no crash.
    assert any("E1" in w for w in result["warnings"])
    assert all(e["employee_id"] != "E1" for e in result["employees"])


def test_unknown_mode_returns_default_shape_and_warning():
    payload = make_payload("bogus_mode")
    result = analyze(payload)
    assert result["rotations_ranked"] == []
    assert result["delta_metrics"] is None
    assert result["employees"] == []
    assert any("unsupported mode" in w for w in result["warnings"])
