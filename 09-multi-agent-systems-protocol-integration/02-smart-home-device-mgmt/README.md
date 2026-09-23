# Smart Home Device Management

Course 4 exercise — sequential multi-agent coordinator: monitor → diagnose → command.

## What we're building

A backend that keeps smart home devices healthy without humans in the loop. Three specialists, one fixed pipeline:

1. **Device Monitor** — takes a device ID, reads telemetry via `read_sensor_data`.
2. **Diagnostics** — takes raw sensor JSON, flags anomalies via `diagnose_issue` (overheating, low_battery, firmware_issue).
3. **Commander** — takes device ID + issue type, dispatches fixes via `send_device_command`.

`run_device_pipeline` (plain Python, no model) threads JSON between stages, parsing agent text with `_parse_json` at every handoff.

## Test Results

### Data Validation ✅ PASSED

#### Devices
| Device ID | Name | Type | Location |
|-----------|------|------|----------|
| DEV-001 | Living Room Thermostat | thermostat | living_room |
| DEV-002 | Front Door Smart Lock | smart_lock | front_door |
| DEV-003 | Doorbell Camera | camera | front_door |

#### Sensor Readings
| Device | Temperature | Humidity | Connectivity | Battery |
|--------|-------------|----------|--------------|---------|
| DEV-001 | 92.5°C | 41% | 98% | 80% |
| DEV-002 | 36.5°C | 38% | 12% | 61% |
| DEV-003 | 28.0°C | 44% | 95% | 7% |

#### Diagnostic Rules
| Issue Type | Metric | Operator | Threshold |
|------------|--------|----------|-----------|
| overheating | temperature | > | 85 |
| firmware_issue | connectivity | < | 20 |
| low_battery | battery | < | 10 |

#### Expected Outcomes
| Device | Issue | Corrective Action |
|--------|-------|-------------------|
| DEV-001 | overheating (92.5°C > 85) | restart-device |
| DEV-002 | firmware_issue (connectivity 12 < 20) | push_firmware_update |
| DEV-003 | low_battery (7% < 10%) | send_recharge_notification |

### Implementation ✅ COMPLETE
- ✅ Device registry with 3 devices
- ✅ Sensor readings with telemetry data
- ✅ Diagnostic rules engine
- ✅ Corrective actions mapping
- ✅ Three agent builders (Monitor, Diagnostics, Commander)
- ✅ Coordinator logic with JSON parsing
- ✅ Retry logic with exponential backoff
- ✅ Helper functions (clean_response, _parse_json)

### Known Limitation
- ❌ Claude Sonnet requires AWS Marketplace subscription
- ✅ Workaround: Use `amazon.nova-lite-v1:0` for testing

## Test Scenarios

| Device | Type | Fault | Expected Fix |
|--------|------|-------|--------------|
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

## Quick Start

```bash
cd 02-smart-home-device-mgmt
cp .env.example .env

# Use Nova Lite to avoid Claude Marketplace access issues
echo "MODEL_ID=amazon.nova-lite-v1:0" >> .env

# Load AWS credentials
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."
export AWS_REGION="us-east-1"

# Run pipeline
uv run python main.py                      # All 3 devices
uv run python main.py --device-id DEV-001  # Single device
```

