import json
import pytest

import sprint_velocity as sv


def test_load_config(tmp_path):
    config_file = tmp_path / "cfg.json"
    data = {"foo": 1, "bar": [1, 2, 3]}
    config_file.write_text(json.dumps(data))
    loaded = sv.load_config(str(config_file))
    assert loaded == data


def test_get_baseline_velocity_no_log():
    config = {"last_velocity": 42}
    assert sv.get_baseline_velocity(config) == 42


def test_get_baseline_velocity_insufficient_log(tmp_path):
    entries = [{"sprint": 1, "completed_points": 10}]
    log_file = tmp_path / "log.json"
    log_file.write_text(json.dumps(entries))
    config = {"last_velocity": 20, "velocity_window": 4, "velocity_log": str(log_file)}
    assert sv.get_baseline_velocity(config) == 20


def test_get_baseline_velocity_exact_window(tmp_path):
    entries = [
        {"sprint": 1, "completed_points": 5},
        {"sprint": 2, "completed_points": 15},
        {"sprint": 3, "completed_points": 25},
    ]
    log_file = tmp_path / "log.json"
    log_file.write_text(json.dumps(entries))
    config = {"velocity_window": 3, "velocity_log": str(log_file)}
    assert sv.get_baseline_velocity(config) == pytest.approx((5 + 15 + 25) / 3)


def test_get_baseline_velocity_file_error(tmp_path):
    bad_file = tmp_path / "does_not_exist.json"
    config = {"velocity_window": 2, "velocity_log": str(bad_file)}
    with pytest.raises(RuntimeError):
        sv.get_baseline_velocity(config)


def test_compute_effective_days_single():
    resources = [{
        "name": "X",
        "last_pto_days": 1,
        "last_pct_avail": 50,
        "next_pto_days": 2,
        "next_pct_avail": 100,
    }]
    rd, total_last, total_next = sv.compute_effective_days(resources, 10)
    assert total_last == pytest.approx(4.5)
    assert total_next == pytest.approx(8.0)
    assert rd[0]["Name"] == "X"
    assert rd[0]["Eff Days Last"] == pytest.approx(4.5)
    assert rd[0]["Eff Days Next"] == pytest.approx(8.0)


def test_perform_scaling_normal_cases():
    raw, scaled = sv.perform_scaling(10, 5, 10)
    assert raw == pytest.approx(20.0)
    assert scaled == 20
    raw2, scaled2 = sv.perform_scaling(10, 4, 5)
    assert raw2 == pytest.approx(12.5)
    assert scaled2 == 12


def test_perform_scaling_zero_total_last():
    with pytest.raises(ValueError):
        sv.perform_scaling(10, 0, 5)


def test_calculate_velocity_basic():
    config = {
        "sprint_days": 5,
        "last_velocity": 100,
        "carryover_points": 0,
        "resources": [
            {"name": "A", "last_pto_days": 0, "last_pct_avail": 100,
             "next_pto_days": 0, "next_pct_avail": 100}
        ]
    }
    metrics, rd = sv.calculate_velocity(config)
    assert metrics["Scaled Next Velocity (floored)"] == 100
    assert metrics["Available Story Points for New Work"] == 100
    assert len(rd) == 1 and rd[0]["Name"] == "A"


def test_calculate_velocity_with_velocity_log(tmp_path):
    entries = [
        {"sprint": 1, "completed_points": 10},
        {"sprint": 2, "completed_points": 20},
    ]
    log_file = tmp_path / "log.json"
    log_file.write_text(json.dumps(entries))
    config = {
        "sprint_days": 5,
        "velocity_log": str(log_file),
        "velocity_window": 2,
        "carryover_points": 0,
        "resources": [
            {"name": "A", "last_pto_days": 0, "last_pct_avail": 100,
             "next_pto_days": 0, "next_pct_avail": 100}
        ]
    }
    metrics, rd = sv.calculate_velocity(config)
    # baseline avg = (10 + 20) / 2 = 15
    assert metrics["Scaled Next Velocity (floored)"] == 15
    assert metrics["Available Story Points for New Work"] == 15