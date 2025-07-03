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
    with open(path, 'r') as f:
        return json.load(f)


def calculate_velocity(config):
    """
    Calculate the scaled story point velocity and available SP for the next sprint,
    using a moving average of completed_points from a velocity log if configured,
    and produce a per-resource availability breakdown.

    Configuration options:
      velocity_log: path to JSON file with historical sprint entries
      velocity_window: number of most recent sprints to average (default: 4)
      last_velocity: fallback single-sprint velocity if no log is provided
      carryover_points, sprint_days, resources: as in previous versions

    Returns:
      metrics: dict of overall velocity metrics
      resource_details: list of dicts for each resource's availability breakdown
    """
    resources = config["resources"]
    velocity_window = config.get("velocity_window", 4)
    velocity_log_path = config.get("velocity_log")
    if velocity_log_path:
        with open(velocity_log_path, 'r') as f:
            log_entries = json.load(f)
        log_entries = sorted(log_entries, key=lambda rec: rec.get("sprint", 0))
        recent = log_entries[-velocity_window:]
        if recent:
            last_velocity = sum(r.get("completed_points", 0) for r in recent) / len(recent)
        else:
            last_velocity = config.get("last_velocity", 0)
    else:
        last_velocity = config.get("last_velocity", 0)
    carryover = config.get("carryover_points", 0)
    sprint_days = config.get("sprint_days", 10)
    num_resources = len(resources)

    resource_details = []
    total_eff_days_last = 0.0
    total_eff_days_next = 0.0

    # Compute per-resource effective days
    for r in resources:
        eff_last = (sprint_days - r["last_pto_days"]) * (r["last_pct_avail"] / 100)
        eff_next = (sprint_days - r["next_pto_days"]) * (r["next_pct_avail"] / 100)
        total_eff_days_last += eff_last
        total_eff_days_next += eff_next
        resource_details.append({
            "Name": r.get("name", ""),
            "Last PTO Days": r["last_pto_days"],
            "Last % Avail": r["last_pct_avail"],
            "Eff Days Last": round(eff_last, 2),
            "Next PTO Days": r["next_pto_days"],
            "Next % Avail": r["next_pct_avail"],
            "Eff Days Next": round(eff_next, 2)
        })

    # Single-step scaling formula
    raw_scaled_next = last_velocity * (total_eff_days_next / total_eff_days_last)
    scaled_next = math.floor(raw_scaled_next)

    # Subtract carry-over and ensure non-negative
    available_sp = max(scaled_next - carryover, 0)

    metrics = {
        "Sprint Days (per resource)": sprint_days,
        "Number of Resources": num_resources,
        "Total Effective Days (Last Sprint)": round(total_eff_days_last, 2),
        "Total Effective Days (Next Sprint)": round(total_eff_days_next, 2),
        "Full Capacity Days (Baseline)": sprint_days * num_resources,
        "Raw Scaled Next Velocity": round(raw_scaled_next, 2),
        "Scaled Next Velocity (floored)": scaled_next,
        "Carry-over Story Points": carryover,
        "Available Story Points for New Work": available_sp
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
    json.dump(synthetic_log, temp)
    temp.close()
    base_config["velocity_log"] = temp.name
    metrics2, _ = calculate_velocity(base_config)
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

    # Load config and calculate
    config = load_config(sys.argv[1])
    metrics, resource_details = calculate_velocity(config)

    # Display with DataFrames
    metrics_df = pd.DataFrame(list(metrics.items()), columns=["Metric", "Value"])
    resources_df = pd.DataFrame(resource_details)

    print("\nSprint Velocity Calculation Breakdown:\n")
    print(metrics_df.to_string(index=False))

    print("\nResource Availability Breakdown:\n")
    print(resources_df.to_string(index=False))


if __name__ == "__main__":
    main()
