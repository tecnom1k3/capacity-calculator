import json
import math
import sys
import pandas as pd
import tempfile
import os


def load_config(path):
    """
    Load JSON configuration from the given file path.
    """
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_baseline_velocity(config):
    """
    Determine the baseline velocity to use:
    - Use the moving average of the last `velocity_window` completed_points if available.
    - Otherwise, fall back to the single-sprint last_velocity from config.
    """
    window = config.get("velocity_window", 4)
    path = config.get("velocity_log")
    if path:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                entries = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Could not load velocity_log '{path}': {e}")
        entries = sorted(entries, key=lambda rec: rec.get("sprint", 0))
        if len(entries) >= window:
            recent = entries[-window:]
            return sum(r.get("completed_points", 0) for r in recent) / window
    return config.get("last_velocity", 0)


def compute_effective_days(resources, sprint_days):
    """
    Compute each resource's effective days last and next sprint based on PTO and availability.

    Returns:
      resource_details: list of per-resource availability dicts
      total_last: sum of all resources' effective days last sprint
      total_next: sum of all resources' effective days next sprint
    """
    resource_details = []
    total_last = total_next = 0.0
    for r in resources:
        last_eff = (sprint_days - r["last_pto_days"]) * (r["last_pct_avail"] / 100)
        next_eff = (sprint_days - r["next_pto_days"]) * (r["next_pct_avail"] / 100)
        total_last += last_eff
        total_next += next_eff
        resource_details.append({
            "Name": r.get("name", ""),
            "Last PTO Days": r["last_pto_days"],
            "Last % Avail": r["last_pct_avail"],
            "Eff Days Last": round(last_eff, 2),
            "Next PTO Days": r["next_pto_days"],
            "Next % Avail": r["next_pct_avail"],
            "Eff Days Next": round(next_eff, 2),
        })
    return resource_details, total_last, total_next


def perform_scaling(last_velocity, total_last, total_next):
    """
    Scale last_velocity by the ratio of total_next to total_last effective days.

    Returns:
      raw_scaled: float value before flooring
      scaled: int(floor(raw_scaled))

    Raises:
      ValueError: if total_last is zero or negative (cannot scale)
    """
    if total_last <= 0:
        raise ValueError("Cannot scale velocity: total effective days last sprint is zero or negative")
    raw_scaled = last_velocity * (total_next / total_last)
    return raw_scaled, math.floor(raw_scaled)


def calculate_velocity(config):
    """
    Calculate the next sprint's metrics and per-resource availability breakdown.

    Uses moving average for velocity baseline when enough history exists,
    otherwise falls back to the last_velocity in config.
    """
    sprint_days = config.get("sprint_days", 10)
    carryover = config.get("carryover_points", 0)

    last_velocity = get_baseline_velocity(config)
    resource_details, total_last, total_next = compute_effective_days(
        config["resources"], sprint_days
    )
    raw_scaled, scaled = perform_scaling(last_velocity, total_last, total_next)
    available = max(scaled - carryover, 0)

    metrics = {
        "Sprint Days (per resource)": sprint_days,
        "Number of Resources": len(resource_details),
        "Total Effective Days (Last Sprint)": round(total_last, 2),
        "Total Effective Days (Next Sprint)": round(total_next, 2),
        "Full Capacity Days (Baseline)": sprint_days * len(resource_details),
        "Raw Scaled Next Velocity": round(raw_scaled, 2),
        "Scaled Next Velocity (floored)": scaled,
        "Carry-over Story Points": carryover,
        "Available Story Points for New Work": available,
    }

    return metrics, resource_details


def run_quick_test():
    """
    Quick verification covering:
      1) No velocity log (fallback to single-sprint last_velocity)
      2) An explicit velocity log with default window size
    """
    base_config = {
        "sprint_days": 10,
        "last_velocity": 10,
        "carryover_points": 0,
        "resources": [
            {"name": "A", "last_pto_days": 2, "last_pct_avail": 100, "next_pto_days": 3, "next_pct_avail": 100},
            {"name": "B", "last_pto_days": 2, "last_pct_avail": 100, "next_pto_days": 3, "next_pct_avail": 100},
            {"name": "C", "last_pto_days": 2, "last_pct_avail": 100, "next_pto_days": 4, "next_pct_avail": 100}
        ]
    }

    metrics1, _ = calculate_velocity(base_config)
    expected = 8
    assert metrics1["Scaled Next Velocity (floored)"] == expected, (
        f"Fallback test failed: expected {expected}, got {metrics1['Scaled Next Velocity (floored)']}"
    )

    synthetic_log = [{"sprint": i, "completed_points": 10}
                     for i in range(1, base_config.get("velocity_window", 4) + 1)]
    temp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json")
    try:
        json.dump(synthetic_log, temp)
        temp.close()
        base_config["velocity_log"] = temp.name
        metrics2, _ = calculate_velocity(base_config)
    finally:
        os.remove(temp.name)
    assert metrics2["Scaled Next Velocity (floored)"] == expected, (
        f"Log-based test failed: expected {expected}, got {metrics2['Scaled Next Velocity (floored)']}"
    )

    print("Quick tests passed: fallback and log-based scenarios both yield", expected)


def main():
    if len(sys.argv) < 2:
        print("Usage: python sprint_velocity.py <config.json> or --test")
        sys.exit(1)

    if sys.argv[1] == "--test":
        run_quick_test()
        return

    config = load_config(sys.argv[1])
    metrics, resource_details = calculate_velocity(config)

    metrics_df = pd.DataFrame(list(metrics.items()), columns=["Metric", "Value"])
    resources_df = pd.DataFrame(resource_details)

    print("\nSprint Velocity Calculation Breakdown:\n")
    print(metrics_df.to_string(index=False))

    print("\nResource Availability Breakdown:\n")
    print(resources_df.to_string(index=False))


if __name__ == "__main__":
    main()
