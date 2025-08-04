import argparse
import json
import math
import pandas as pd


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


__version__ = "1.0.0"


def build_parser():
    """Create and return the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Calculate next sprint velocity from a configuration file"
    )
    parser.add_argument("config", help="Path to configuration JSON file")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Optional path to write results as JSON",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    config = load_config(args.config)
    metrics, resource_details = calculate_velocity(config)

    metrics_df = pd.DataFrame(list(metrics.items()), columns=["Metric", "Value"])
    resources_df = pd.DataFrame(resource_details)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump({"metrics": metrics, "resource_details": resource_details}, f, indent=2)

    print("\nSprint Velocity Calculation Breakdown:\n")
    print(metrics_df.to_string(index=False))

    print("\nResource Availability Breakdown:\n")
    print(resources_df.to_string(index=False))


if __name__ == "__main__":
    main()
