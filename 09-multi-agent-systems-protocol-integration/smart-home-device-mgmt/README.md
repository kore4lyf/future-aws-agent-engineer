# Smart Home Device Management

Course 4 exercise — sequential multi-agent coordinator: monitor → diagnose → command.

## What we're building

A backend that keeps smart home devices healthy without humans in the loop. Three specialists, one fixed pipeline:

1. **Device Monitor** — takes a device ID, reads telemetry via `read_sensor_data`.
2. **Diagnostics** — takes raw sensor JSON, flags anomalies via `diagnose_issue` (overheating, low_battery, firmware_issue).
3. **Commander** — takes device ID + issue type, dispatches fixes via `send_device_command`.

`run_device_pipeline` (plain Python, no model) threads JSON between stages, parsing agent text with `_parse_json` at every handoff.

## Test scenarios

| Device | Type | Fault | Expected fix |
|---|---|---|---|
| DEV-001 | thermostat | overheating (92.5C > 85) | restart-device |
| DEV-002 | smart_lock | firmware_issue (connectivity 12 < 20) | push_firmware_update |
| DEV-003 | camera | low_battery (7% < 10%) | send_recharge_notification |

## Layout

- `main.py` — entrypoint: AgentCore `invoke` plus local CLI
- `src/main.py` — pipeline: builders, coordinator, data tables, helpers

## Development plan

1. TODO 1–3: builders — one `BedrockModel` (temp 0.0) + one tool + fenced prompt each.
2. TODO 4–6: coordinator — monitor → surface sensor JSON → diagnose → surface issues → command per issue.
3. Run: `cp .env.example .env`, load AWS creds, `uv run main.py` (all devices) or `uv run main.py --device-id DEV-001` (one device), confirm 3/3 summaries.
