# Capacity Calculator

A simple CLI tool to project and scale sprint velocity based on team availability (PTO, percent availability) and historical velocity data.

## Features

- Scale last sprint's velocity to the next sprint using effective working days
- Support a moving average of completed story points from a velocity log
- Produce a per-resource availability breakdown
- Pretty-print results as tables via pandas

## Requirements

- Python 3.7 or newer
- pandas

## Installation

1. Clone this repository:
   ```bash
   git clone <repo-url>
   cd capacity-calculator
   ```
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install runtime (and test) dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Copy the sample config and adjust values for your team:

```bash
cp config.json.sample config.json
```

Update `config.json` fields:

- `sprint_days`: number of work days per sprint
- `last_velocity`: last sprint's actual story point velocity (fallback)
- `carryover_points`: story points carried into the next sprint
- `velocity_log`: path to a JSON log of past sprints
- `velocity_window`: number of most recent sprints to average
- `resources`: list of team members with PTO and % availability for last/next sprint

## Usage

Run the calculator with your config:

```bash
python sprint_velocity.py config.json
```

Example output:

```
Sprint Velocity Calculation Breakdown:

                             Metric  Value
         Sprint Days (per resource)  10.00
                Number of Resources   3.00
 Total Effective Days (Last Sprint)  25.40
 Total Effective Days (Next Sprint)  30.00
      Full Capacity Days (Baseline)  30.00
           Raw Scaled Next Velocity  42.81
     Scaled Next Velocity (floored)  42.00
            Carry-over Story Points   6.00
Available Story Points for New Work  36.00

Resource Availability Breakdown:

   Name  Last PTO Days  Last % Avail  Eff Days Last  Next PTO Days  Next % Avail  Eff Days Next
Matthew              2            80            6.4              0           100           10.0
Aswin                0           100           10.0              0           100           10.0
Angel                1           100            9.0              0           100           10.0
```

## Testing

Unit tests are implemented with pytest:

```bash
python -m pytest
```

## License

This project is provided as-is without warranty.