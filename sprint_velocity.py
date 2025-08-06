import argparse
import json
import math
import os
import sys
from pathlib import Path

import pandas as pd

try:
    from version import __version__
except ImportError:  # pragma: no cover - fallback for missing module
    __version__ = "0.0.0-dev"


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
    required = ["last_pto_days", "last_pct_avail", "next_pto_days", "next_pct_avail"]
    for idx, r in enumerate(resources):
        name = r.get("name", f"resource_{idx}")

        for key in required:
            if key not in r:
                raise ValueError(f"Resource '{name}' is missing required field '{key}'")

        last_pto = r["last_pto_days"]
        last_pct = r["last_pct_avail"]
        next_pto = r["next_pto_days"]
        next_pct = r["next_pct_avail"]

        fields = [
            ("last_pto_days", last_pto, False),
            ("last_pct_avail", last_pct, True),
            ("next_pto_days", next_pto, False),
            ("next_pct_avail", next_pct, True),
        ]

        for field, value, is_pct in fields:
            if not isinstance(value, (int, float)):
                raise ValueError(
                    f"Resource '{name}' field '{field}' must be a number"
                )
            if value < 0:
                raise ValueError(
                    f"Resource '{name}' field '{field}' cannot be negative"
                )
            if is_pct and value > 100:
                raise ValueError(
                    f"Resource '{name}' field '{field}' must be between 0 and 100"
                )

        if last_pto > sprint_days:
            raise ValueError(
                f"Resource '{name}' last_pto_days ({last_pto}) exceeds sprint days ({sprint_days})"
            )
        if next_pto > sprint_days:
            raise ValueError(
                f"Resource '{name}' next_pto_days ({next_pto}) exceeds sprint days ({sprint_days})"
            )

        last_eff = (sprint_days - last_pto) * (last_pct / 100)
        next_eff = (sprint_days - next_pto) * (next_pct / 100)
        total_last += last_eff
        total_next += next_eff
        resource_details.append({
            "Name": name,
            "Last PTO Days": last_pto,
            "Last % Avail": last_pct,
            "Eff Days Last": round(last_eff, 2),
            "Next PTO Days": next_pto,
            "Next % Avail": next_pct,
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
        raise ValueError(
            "Cannot scale velocity: total effective days last sprint is zero or negative"
        )
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
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output file if it exists",
    )
    return parser


def write_output_json(output_path, metrics, resource_details, *, force=False):
    """Safely write metrics and resource details to ``output_path``.

    The data is first written to a sibling temporary file which is then
    atomically moved into place. When ``force`` is ``False`` an atomic
    existence check is performed so that an existing file is never
    clobbered inadvertently.

    Raises:
        OSError: If there is an error writing to ``output_path`` or the file
            already exists when ``force`` is False.
        RuntimeError: If there is an error serializing the data.
    """
    output_path = Path(output_path)
    tmp_path = output_path.with_suffix(f".tmp.{os.getpid()}")
    placeholder_created = False
    replaced = False
    try:
        if not force:
            try:
                fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            except FileExistsError as e:
                raise OSError(f"Output file '{output_path}' already exists") from e
            else:
                os.close(fd)
                placeholder_created = True

        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(
                {"metrics": metrics, "resource_details": resource_details},
                f,
                indent=2,
            )
        os.replace(tmp_path, output_path)
        replaced = True
    except (TypeError, ValueError) as e:
        raise RuntimeError(f"Data serialization error: {e}") from e
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError as cleanup_err:
                print(f"Cleanup failed: {cleanup_err}", file=sys.stderr)
        if placeholder_created and not replaced and output_path.exists():
            try:
                output_path.unlink()
            except OSError as cleanup_err:
                print(f"Cleanup failed: {cleanup_err}", file=sys.stderr)


def main():
    parser = build_parser()
    args = parser.parse_args()

    config = load_config(args.config)
    metrics, resource_details = calculate_velocity(config)

    metrics_df = pd.DataFrame(list(metrics.items()), columns=["Metric", "Value"])
    resources_df = pd.DataFrame(resource_details)

    if args.output:
        output_path = Path(args.output)
        if output_path.exists():
            if not args.force:
                print(
                    f"Error: output file '{output_path}' already exists. Use --force to overwrite.",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(f"Warning: Overwriting existing file '{output_path}'", file=sys.stderr)
        try:
            write_output_json(output_path, metrics, resource_details, force=args.force)
        except (OSError, RuntimeError) as e:
            print(f"Error writing output file: {e}", file=sys.stderr)
            sys.exit(1)

    print("\nSprint Velocity Calculation Breakdown:\n")
    print(metrics_df.to_string(index=False))

    print("\nResource Availability Breakdown:\n")
    print(resources_df.to_string(index=False))


if __name__ == "__main__":
    main()
