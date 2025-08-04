import json
import subprocess
import sys
from pathlib import Path


def test_cli_output(tmp_path):
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
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(config))

    script_path = Path(__file__).resolve().parent.parent / "sprint_velocity.py"
    result = subprocess.run(
        [sys.executable, str(script_path), str(cfg_file)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Sprint Velocity Calculation Breakdown" in result.stdout
    assert "Resource Availability Breakdown" in result.stdout


def test_output_file_atomic_write(tmp_path):
    config = {
        "sprint_days": 5,
        "last_velocity": 50,
        "carryover_points": 0,
        "resources": [
            {
                "name": "B",
                "last_pto_days": 0,
                "last_pct_avail": 100,
                "next_pto_days": 0,
                "next_pct_avail": 100,
            }
        ],
    }
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(config))

    output_file = tmp_path / "out.json"
    script_path = Path(__file__).resolve().parent.parent / "sprint_velocity.py"
    result = subprocess.run(
        [sys.executable, str(script_path), str(cfg_file), "-o", str(output_file)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert output_file.exists()
    assert not output_file.with_suffix(".tmp").exists()
    data = json.loads(output_file.read_text())
    assert "metrics" in data and "resource_details" in data
