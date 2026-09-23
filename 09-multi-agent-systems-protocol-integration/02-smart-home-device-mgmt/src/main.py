# =============================================================================
# Smart Home Device Management — sequential multi-agent coordinator
# Pipeline: Device Monitor -> Diagnostics -> Commander
# Each stage owns one tool and one agent; the coordinator threads JSON
# between stages, parsing agent text with _parse_json (loads + regex fallback).
# =============================================================================
import json
import logging
import os
import re
import time
from datetime import datetime

from dotenv import load_dotenv
from strands import Agent, tool
from strands.models import BedrockModel

load_dotenv()

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")

# -----------------------------------------------------------------------------
# Sample data — device registry, sensor readings, diagnostic rules, fixes.
# In production telemetry streams in from device shadows / IoT Core.
# -----------------------------------------------------------------------------
DEVICE_REGISTRY = {
    "DEV-001": {"name": "Living Room Thermostat", "type": "thermostat", "location": "living_room"},
    "DEV-002": {"name": "Front Door Smart Lock", "type": "smart_lock", "location": "front_door"},
    "DEV-003": {"name": "Doorbell Camera", "type": "camera", "location": "front_door"},
}

SENSOR_READINGS = [
    {
        "device_id": "DEV-001",
        "timestamp": "2026-09-16T18:00:00",
        "readings": {"temperature": 92.5, "humidity": 41, "connectivity": 98, "battery": 80},
    },
    {
        "device_id": "DEV-002",
        "timestamp": "2026-09-16T18:00:00",
        "readings": {"temperature": 36.5, "humidity": 38, "connectivity": 12, "battery": 61},
    },
    {
        "device_id": "DEV-003",
        "timestamp": "2026-09-16T18:00:00",
        "readings": {"temperature": 28.0, "humidity": 44, "connectivity": 95, "battery": 7},
    },
]

DIAGNOSTIC_RULES = {
    "overheating": {"metric": "temperature", "operator": ">", "threshold": 85},
    "firmware_issue": {"metric": "connectivity", "operator": "<", "threshold": 20},
    "low_battery": {"metric": "battery", "operator": "<", "threshold": 10},
}

CORRECTIVE_ACTIONS = {
    "overheating": "restart-device",
    "firmware_issue": "push_firmware_update",
    "low_battery": "send_recharge_notification",
}

TEST_DEVICES = ["DEV-001", "DEV-002", "DEV-003"]

# -----------------------------------------------------------------------------
# Shared helpers
# Agents return strings that may carry extra text, so every handoff parses
# with _parse_json: json.loads first, regex JSON extractor as fallback.
# -----------------------------------------------------------------------------
def clean_response(text: str) -> str:
    # Strip model thinking blocks so downstream parsing never chokes.
    return re.sub(r"<thinking>.*?</thinking>", "", str(text), flags=re.DOTALL).strip()


def _parse_json(text: str) -> tuple:
    cleaned = clean_response(text)
    try:
        return json.loads(cleaned), cleaned
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(0)), match.group(0)
        raise ValueError(f"No JSON object found in: {cleaned[:200]}")


def run_agent_with_retry(agent_builder, prompt: str, max_retries: int = 3) -> str:
    # Rebuild a fresh agent per attempt with exponential backoff (1s, 2s, 4s).
    for attempt in range(max_retries):
        try:
            agent = agent_builder()
            result = agent(prompt)
            return clean_response(result)
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2**attempt
                print(f"[Retry ({attempt + 1})/{max_retries}] ({e.__class__.__name__}), waiting ({wait}s...)")
                time.sleep(wait)
            else:
                print(f"[Failed] ({e.__class__.__name__}) after ({max_retries}) attempts")
                raise


def _rule_broken(value, operator: str, threshold) -> bool:
    return value > threshold if operator == ">" else value < threshold


# -----------------------------------------------------------------------------
# Stage 1 — Device Monitor: device ID -> registry info + sensor readings
# Tool and agent live together; the tool computes, the agent only routes.
# -----------------------------------------------------------------------------
@tool
def read_sensor_data(device_id: str) -> str:
    """Look up a device in the registry and return its latest sensor readings as JSON.

    Args:
        device_id: The device identifier, e.g. DEV-001

    Returns:
        JSON string with device info plus readings, or an error object when unknown
    """
    device_info = DEVICE_REGISTRY.get(device_id)
    if not device_info:
        return json.dumps({"error": f"Device {device_id} not found"})
    reading = next((r for r in SENSOR_READINGS if r["device_id"] == device_id), None)
    if reading is None:
        return json.dumps({"error": f"No readings for device {device_id}"})
    return json.dumps(
        {
            "device_id": device_id,
            **device_info,
            "timestamp": reading["timestamp"],
            "readings": reading["readings"],
        },
        indent=2,
    )


def build_device_monitor() -> Agent:
    model = BedrockModel(
        model_id=MODEL_ID,
        region_name=AWS_REGION,
        temperature=0.0,
    )
    system_prompt = """You are a Device Monitor agent. Your ONLY job is reading sensor data.
Call read_sensor_data with the device_id, then output ONLY the raw JSON.
Do not diagnose issues or send commands."""
    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[read_sensor_data],
    )


# -----------------------------------------------------------------------------
# Stage 2 — Diagnostics: sensor readings -> flagged rule violations
# Rules live in DIAGNOSTIC_RULES data; the model never invents thresholds.
# -----------------------------------------------------------------------------
@tool
def diagnose_issue(sensor_data_json: str) -> str:
    """Flag sensor readings that break diagnostic rules.

    Args:
        sensor_data_json: JSON string of device info plus readings

    Returns:
        JSON string with device_id, issues_found count, issue list, and status
    """
    try:
        data = json.loads(sensor_data_json)
    except (json.JSONDecodeError, AttributeError, TypeError):
        match = re.search(r"\{.*\}", str(sensor_data_json), re.DOTALL)
        if not match:
            return json.dumps({"issues": [], "status": "error", "error": "Malformed sensor data"})
        data = json.loads(match.group(0))
    if "error" in data:
        return json.dumps({"issues": [], "status": "error", "error": data["error"]})
    readings = data.get("readings", {})
    issues = []
    for issue_type, rule in DIAGNOSTIC_RULES.items():
        value = readings.get(rule["metric"])
        if value is not None and _rule_broken(value, rule["operator"], rule["threshold"]):
            issues.append(
                {
                    "issue": issue_type,
                    "metric": rule["metric"],
                    "value": value,
                    "threshold": rule["threshold"],
                }
            )
    return json.dumps(
        {
            "device_id": data.get("device_id"),
            "issues_found": len(issues),
            "issues": issues,
            "status": "issues_detected" if issues else "healthy",
        },
        indent=2,
    )


def build_diagnostics_agent() -> Agent:
    model = BedrockModel(
        model_id=MODEL_ID,
        region_name=AWS_REGION,
        temperature=0.0,
    )
    system_prompt = """You are a Diagnostics agent. Your ONLY job is fault diagnosis.
Call diagnose_issue with the sensor data JSON, then output ONLY the raw JSON.
Do not read sensors or send commands."""
    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[diagnose_issue],
    )


# -----------------------------------------------------------------------------
# Stage 3 — Commander: device ID + issue type -> dispatched fix
# Actions come from the CORRECTIVE_ACTIONS table; unknown issues are rejected.
# -----------------------------------------------------------------------------
@tool
def send_device_command(device_id: str, issue_type: str) -> str:
    """Dispatch the corrective action mapped to a diagnosed issue.

    Args:
        device_id: The device identifier, e.g. DEV-001
        issue_type: One of overheating, firmware_issue, low_battery

    Returns:
        JSON string confirming the dispatched command
    """
    action = CORRECTIVE_ACTIONS.get(issue_type)
    if action is None:
        return json.dumps({"status": "rejected", "device_id": device_id, "message": f"Unknown issue type: {issue_type}"})
    return json.dumps(
        {
            "status": "command_sent",
            "device_id": device_id,
            "issue": issue_type,
            "action": action,
            "message": f"Dispatched {action} to {device_id}",
            "timestamp": datetime.now().isoformat(),
        },
        indent=2,
    )


def build_command_agent() -> Agent:
    model = BedrockModel(
        model_id=MODEL_ID,
        region_name=AWS_REGION,
        temperature=0.0,
    )
    system_prompt = """You are a Command agent. Your ONLY job is dispatching corrective actions.
Call send_device_command with the device_id and issue_type, then output ONLY the raw JSON.
Do not read sensors or diagnose issues."""
    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[send_device_command],
    )


# -----------------------------------------------------------------------------
# Coordinator — plain Python, no model. Fixed recipe: monitor, diagnose,
# then one command call per issue (skipped when healthy). Parses agent text
# with _parse_json at every handoff instead of trusting prose.
# -----------------------------------------------------------------------------
def run_device_pipeline(device_id: str) -> dict:
    print(f"[1/3] Device Monitor ({device_id})...")
    monitor_result = run_agent_with_retry(
        build_device_monitor, f"Read sensor data for device_id={device_id}"
    )
    sensor_json, sensor_str = _parse_json(monitor_result)
    if "error" in sensor_json:
        print(f"Monitor error: ({sensor_json['error']})")
        return {"device_id": device_id, "sensor_data": sensor_json, "diagnosis": {}, "commands": []}

    print("[2/3] Diagnostics...")
    diag_result = run_agent_with_retry(
        build_diagnostics_agent,
        f"Diagnose issues from this sensor data: {sensor_str}",
    )
    diag_json, _ = _parse_json(diag_result)
    issues = diag_json.get("issues", [])
    print(f"Found ({len(issues)}) issue(s)")

    print("[3/3] Command...")
    commands = []
    for issue in issues:
        cmd_result = run_agent_with_retry(
            build_command_agent,
            f"Send command for device_id={device_id} with issue_type={issue['issue']}",
        )
        cmd_json, _ = _parse_json(cmd_result)
        commands.append(cmd_json)
        print(f"Command: ({cmd_json.get('action', cmd_json.get('status'))})")

    return {
        "device_id": device_id,
        "sensor_data": sensor_json,
        "diagnosis": diag_json,
        "commands": commands,
    }



