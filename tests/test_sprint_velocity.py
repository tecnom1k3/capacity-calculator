import json
import os
import pwd
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import sprint_velocity as sv  # noqa: E402
from version import __version__  # noqa: E402


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


def test_compute_effective_days_missing_key():
    resources = [{
        "name": "X",
        "last_pto_days": 1,
        "last_pct_avail": 50,
        "next_pto_days": 2,
        # Missing next_pct_avail
    }]
    with pytest.raises(ValueError):
        sv.compute_effective_days(resources, 10)


def test_compute_effective_days_negative_pto():
    resources = [{
        "name": "Y",
        "last_pto_days": -1,
        "last_pct_avail": 50,
        "next_pto_days": 0,
        "next_pct_avail": 100,
    }]
    with pytest.raises(ValueError):
        sv.compute_effective_days(resources, 10)


def test_compute_effective_days_negative_percentage():
    resources = [{
        "name": "Y",
        "last_pto_days": 0,
        "last_pct_avail": -5,
        "next_pto_days": 0,
        "next_pct_avail": 100,
    }]
    with pytest.raises(ValueError):
        sv.compute_effective_days(resources, 10)


def test_compute_effective_days_percentage_out_of_range():
    resources = [{
        "name": "Z",
        "last_pto_days": 0,
        "last_pct_avail": 150,
        "next_pto_days": 0,
        "next_pct_avail": 100,
    }]
    with pytest.raises(ValueError):
        sv.compute_effective_days(resources, 10)


def test_compute_effective_days_pto_exceeds_sprint_days_last():
    resources = [{
        "name": "TooMuch",
        "last_pto_days": 11,
        "last_pct_avail": 100,
        "next_pto_days": 0,
        "next_pct_avail": 100,
    }]
    with pytest.raises(ValueError):
        sv.compute_effective_days(resources, 10)


def test_compute_effective_days_pto_exceeds_sprint_days_next():
    resources = [{
        "name": "TooMuch",
        "last_pto_days": 0,
        "last_pct_avail": 100,
        "next_pto_days": 11,
        "next_pct_avail": 100,
    }]
    with pytest.raises(ValueError):
        sv.compute_effective_days(resources, 10)


def test_compute_effective_days_non_numeric():
    resources = [{
        "name": "Invalid",
        "last_pto_days": "five",
        "last_pct_avail": 100,
        "next_pto_days": 0,
        "next_pct_avail": 100,
    }]
    with pytest.raises(ValueError):
        sv.compute_effective_days(resources, 10)


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


def test_main_requires_config(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["sprint_velocity.py"])
    with pytest.raises(SystemExit):
        sv.main()


def test_main_version_flag(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["sprint_velocity.py", "--version"])
    with pytest.raises(SystemExit) as exc:
        sv.main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == f"sprint_velocity.py {__version__}"


def test_main_output_flag(monkeypatch, tmp_path):
    config = {
        "sprint_days": 5,
        "last_velocity": 100,
        "carryover_points": 0,
        "resources": [
            {"name": "A", "last_pto_days": 0, "last_pct_avail": 100,
             "next_pto_days": 0, "next_pct_avail": 100}
        ]
    }
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(config))
    output_path = tmp_path / "out.json"
    monkeypatch.setattr(
        sys, "argv", ["sprint_velocity.py", str(cfg_path), "--output", str(output_path)]
    )
    sv.main()
    assert output_path.exists()
    data = json.loads(output_path.read_text())
    assert "metrics" in data and "resources" in data


def test_main_output_exists_without_force(monkeypatch, tmp_path, capsys):
    config = {
        "sprint_days": 5,
        "last_velocity": 100,
        "carryover_points": 0,
        "resources": [
            {
                "name": "A",
                "last_pto_days": 0,
                "last_pct_avail": 100,
                "next_pto_days": 0,
                "next_pct_avail": 100,
            }
        ],
    }
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(config))
    output_path = tmp_path / "out.json"
    output_path.write_text("existing")
    monkeypatch.setattr(
        sys,
        "argv",
        ["sprint_velocity.py", str(cfg_path), "--output", str(output_path)],
    )
    with pytest.raises(SystemExit) as exc:
        sv.main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert (
        f"output file '{output_path}' already exists" in captured.err
    )


def test_main_output_exists_with_force(monkeypatch, tmp_path, capsys):
    config = {
        "sprint_days": 5,
        "last_velocity": 100,
        "carryover_points": 0,
        "resources": [
            {
                "name": "A",
                "last_pto_days": 0,
                "last_pct_avail": 100,
                "next_pto_days": 0,
                "next_pct_avail": 100,
            }
        ],
    }
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(config))
    output_path = tmp_path / "out.json"
    output_path.write_text("existing")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sprint_velocity.py",
            str(cfg_path),
            "--output",
            str(output_path),
            "--force",
        ],
    )
    sv.main()
    data = json.loads(output_path.read_text())
    assert "metrics" in data and "resources" in data
    captured = capsys.readouterr()
    assert "Warning: Overwriting" in captured.err


def test_main_output_missing_directory(monkeypatch, tmp_path, capsys):
    config = {
        "sprint_days": 5,
        "last_velocity": 100,
        "carryover_points": 0,
        "resources": [
            {
                "name": "A",
                "last_pto_days": 0,
                "last_pct_avail": 100,
                "next_pto_days": 0,
                "next_pct_avail": 100,
            }
        ],
    }
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(config))
    output_path = tmp_path / "missing_dir" / "out.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["sprint_velocity.py", str(cfg_path), "--output", str(output_path)],
    )
    with pytest.raises(SystemExit) as exc:
        sv.main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Error writing output file" in captured.err
    with pytest.raises(FileNotFoundError):
        sv.write_output_json(output_path, {}, [], force=False)


def test_main_output_permission_denied(monkeypatch, capsys):
    if os.geteuid() != 0:
        pytest.skip("requires root privileges to adjust user IDs")

    config = {
        "sprint_days": 5,
        "last_velocity": 100,
        "carryover_points": 0,
        "resources": [
            {
                "name": "A",
                "last_pto_days": 0,
                "last_pct_avail": 100,
                "next_pto_days": 0,
                "next_pct_avail": 100,
            }
        ],
    }

    work_dir = Path(tempfile.mkdtemp())
    restricted_dir = None
    try:
        work_dir.chmod(0o755)
        cfg_path = work_dir / "cfg.json"
        cfg_path.write_text(json.dumps(config))
        restricted_dir = work_dir / "restricted"
        restricted_dir.mkdir()
        restricted_dir.chmod(0o555)
        output_path = restricted_dir / "out.json"
        monkeypatch.setattr(
            sys,
            "argv",
            ["sprint_velocity.py", str(cfg_path), "--output", str(output_path)],
        )

        try:
            nobody_uid = pwd.getpwnam("nobody").pw_uid
        except KeyError:
            pytest.skip("nobody user not found")

        @contextmanager
        def switch_euid(uid):
            original_uid = os.geteuid()
            os.seteuid(uid)
            try:
                yield
            finally:
                os.seteuid(original_uid)

        with switch_euid(nobody_uid):
            with pytest.raises(SystemExit) as exc:
                sv.main()
            assert exc.value.code == 1
            captured = capsys.readouterr()
            assert "Error writing output file" in captured.err
            assert "Permission denied" in captured.err
    finally:
        if restricted_dir is not None:
            try:
                restricted_dir.chmod(0o700)
            except Exception:
                pass
        shutil.rmtree(work_dir)

def test_write_output_json_serialization_error(tmp_path):
    output_path = tmp_path / "out.json"
    with pytest.raises(RuntimeError):
        sv.write_output_json(output_path, {"bad": set()}, [], force=False)


def test_main_concurrent_file_creation(monkeypatch, tmp_path):
    config = {
        "sprint_days": 5,
        "last_velocity": 100,
        "carryover_points": 0,
        "resources": [
            {
                "name": "A",
                "last_pto_days": 0,
                "last_pct_avail": 100,
                "next_pto_days": 0,
                "next_pct_avail": 100,
            }
        ],
    }
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(config))
    output_path = tmp_path / "out.json"

    original_write = sv.write_output_json

    def race_write(path, metrics, resources, *, force=False):
        # Create the file just before the actual write to simulate a race
        Path(path).write_text("existing")
        return original_write(path, metrics, resources, force=force)

    monkeypatch.setattr(sv, "write_output_json", race_write)
    monkeypatch.setattr(
        sys, "argv", ["sprint_velocity.py", str(cfg_path), "--output", str(output_path)]
    )
    with pytest.raises(SystemExit) as exc:
        sv.main()
    assert exc.value.code == 1


def test_main_serialization_error(monkeypatch, tmp_path):
    config = {
        "sprint_days": 5,
        "last_velocity": 100,
        "carryover_points": 0,
        "resources": [
            {
                "name": "A",
                "last_pto_days": 0,
                "last_pct_avail": 100,
                "next_pto_days": 0,
                "next_pct_avail": 100,
            }
        ],
    }
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(config))
    output_path = tmp_path / "out.json"

    def bad_dump(*args, **kwargs):
        raise TypeError("bad serialize")

    monkeypatch.setattr(sv.json, "dump", bad_dump)
    monkeypatch.setattr(
        sys, "argv", [
            "sprint_velocity.py", str(cfg_path), "--output", str(output_path), "--force"
        ]
    )
    with pytest.raises(SystemExit) as exc:
        sv.main()
    assert exc.value.code == 1
