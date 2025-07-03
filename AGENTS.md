# AI/LLM CLI Agents Guide

This document explains how AI or LLM-powered CLI agents can interact with the Capacity Calculator project.

## Project Overview

The Capacity Calculator is a Python-based command-line tool to:
- Scale a team's previous sprint velocity into the next sprint based on PTO and availability
- Optionally use a moving average from historical velocity logs
- Provide overall metrics and per-resource breakdowns

## Key CLI Commands

| Command                                    | Description                                           |
|--------------------------------------------|-------------------------------------------------------|
| `python sprint_velocity.py config.json`    | Run the calculator against the provided config file.  |
| `python sprint_velocity.py --help`         | Show usage information.                               |

## Configuration for Agents

AI agents should prepare a valid `config.json` (see `config.json.sample`) before invocation. Key settings:
- `sprint_days`: work days per sprint
- `last_velocity`: fallback velocity if insufficient history
- `carryover_points`: points carried into next sprint
- `velocity_log`: optional path to a JSON history file
- `velocity_window`: how many past sprints to average
- `resources`: list of team members with PTO/availability entries

## Expected Output

The tool prints two tables to stdout:
1. **Sprint Velocity Calculation Breakdown** – overall metrics
2. **Resource Availability Breakdown** – per-person effective days

LLM agents can parse these tables to extract numeric results or render human-friendly reports.

## Example Agent Workflow

```bash
# 1) Ensure config.json is up-to-date
agent> write_file("config.json", updated_config)

# 2) Execute the velocity script
agent> run_shell("python sprint_velocity.py config.json")

# 3) Capture and parse the tables
agent> output = capture_output()
agent> metrics = parse_table(output, table=1)
agent> resources = parse_table(output, table=2)

# 4) Summarize for users
agent> respond(f"Next sprint capacity: {metrics['Available Story Points for New Work']}")
```

Agents may integrate this CLI into larger planning or reporting pipelines.