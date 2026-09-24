# =============================================================================
# Deployment Walkthrough — Lesson 10 Demo
# =============================================================================
# Production deployment walkthrough for an insurance claims multi-agent system:
#   1. Discover infrastructure via CloudFormation exports
#   2. Configure AgentCore Runtime
#   3. Define three-tier agent architecture
#   4. Six-step gated deployment pipeline
#   5. Monitoring strategy (CloudWatch, X-Ray, SNS alarms)
#   6. Cost estimation
#   7. Deploy to AgentCore Runtime via boto3 control plane
# ============================================================================

from __future__ import annotations

import json
import os
import sys
import time
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).parent))

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
STACK_NAME = "lesson-10-demo-runtime"

# CloudFormation export names
_EXPORT_ROLE = "lesson-10-demo-AgentCoreRoleArn"
_EXPORT_BUCKET = "lesson-10-demo-ArtifactBucketName"
_EXPORT_GUARDRAIL = "lesson-10-demo-GuardrailId"


# ============================================================================
# Step 0: Resource discovery via CloudFormation exports
# ============================================================================

def _load_cf_exports() -> dict[str, str]:
    """Discover infrastructure IDs from CloudFormation exports."""
    cf = boto3.client("cloudformation", region_name=AWS_REGION)
    paginator = cf.get_paginator("list_exports")
    exports: dict[str, str] = {}
    for page in paginator.paginate():
        for export in page.get("Exports", []):
            exports[export["Name"]] = export["Value"]
    return exports


def _require_export(exports: dict[str, str], name: str) -> str:
    value = exports.get(name)
    if not value:
        print(f"ERROR: missing CloudFormation export {name}")
        print("Run: python infrastructure/deploy_stack.py")
        sys.exit(1)
    return value


# ============================================================================
# Step 1: AgentCore Runtime configuration
# ============================================================================

RUNTIME_CONFIG: dict[str, Any] = {
    "agentRuntimeName": "insurance_claims_runtime",
    "roleArn": "",  # filled from CF export
    "networkConfiguration": {"networkMode": "PUBLIC"},
    "protocolConfiguration": {"serverProtocol": "MCP"},
    "guardrailConfiguration": {
        "guardrailIdentifier": "",
        "guardrailVersion": "DRAFT",
    },
    "environmentVariables": {
        "CLAIMS_KB_ID": "KB-CLAIMS-001",
        "POLICY_KB_ID": "KB-POLICY-002",
        "STATE_TABLE_NAME": "lesson10-demo-claims-state",
        "AWS_REGION": AWS_REGION,
        "LOG_LEVEL": "INFO",
        "ENVIRONMENT": "production",
    },
}


# ============================================================================
# Step 2: Agent definitions and deployment pipeline
# ============================================================================

AGENT_DEFINITIONS = [
    {
        "name": "ClaimsRouter",
        "model": "amazon.nova-lite-v1:0",
        "temperature": 0.0,
        "daily_requests": 10_000,
        "tokens_per_request": 500,
        "role": "Routes incoming claims to the correct processing path",
    },
    {
        "name": "ClaimsAnalyzer",
        "model": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "temperature": 0.1,
        "daily_requests": 3_000,
        "tokens_per_request": 2_000,
        "role": "Deep fraud analysis, coverage gap analysis, policy lookup",
    },
    {
        "name": "ClaimsResponder",
        "model": "amazon.nova-pro-v1:0",
        "temperature": 0.3,
        "daily_requests": 10_000,
        "tokens_per_request": 1_000,
        "role": "Drafts customer-facing claim responses",
    },
]

DEPLOYMENT_PIPELINE = [
    {
        "step": 1,
        "name": "Build & Test",
        "command": "pytest test/ -v --tb=short",
        "gate": "All tests pass",
    },
    {
        "step": 2,
        "name": "Guardrail Promotion",
        "command": "python infrastructure/promote_guardrail.py --to-version 1",
        "gate": "Guardrail version 1 created",
    },
    {
        "step": 3,
        "name": "Runtime Deployment",
        "command": "python deploy_to_agentcore.py",
        "gate": "Runtime status = ACTIVE",
    },
    {
        "step": 4,
        "name": "Memory Setup",
        "command": "agentcore memory create --name claims-memory --ttl 24h",
        "gate": "Memory resource ready",
    },
    {
        "step": 5,
        "name": "Observability",
        "command": "python setup_monitoring.py --enable-xray --create-alarms",
        "gate": "CloudWatch dashboard populated",
    },
    {
        "step": 6,
        "name": "Smoke Test",
        "command": "python smoke_test.py --claims 10 --max-latency 5s",
        "gate": "10/10 claims processed, P99 latency < 5s",
    },
]


# ============================================================================
# Step 3: Monitoring strategy
# ============================================================================

MONITORING_STRATEGY: dict[str, Any] = {
    "cloudwatch_widgets": [
        "Invocations per minute",
        "Latency P50/P99",
        "Error rate by agent",
        "Guardrail blocks by policy",
    ],
    "alarms": [
        {
            "name": "HighErrorRate",
            "metric": "AgentCore/Errors",
            "threshold": 0.05,
            "period": 300,
            "action": "SNS -> kill-switch-topic -> Lambda disables runtime",
        },
        {
            "name": "HighLatency",
            "metric": "AgentCore/Latency",
            "stat": "p99",
            "threshold": 10.0,
            "period": 300,
            "action": "SNS -> ops-team-pager",
        },
    ],
    "xray_tracing": {
        "enabled": True,
        "sampling_rate": 0.05,
        "annotations": ["claim_type", "agent_name", "model_id"],
    },
}


# ============================================================================
# Cost estimation
# ============================================================================

_MODEL_PRICING = {
    "amazon.nova-lite-v1:0": {"input": 0.00006, "output": 0.00024},
    "amazon.nova-pro-v1:0": {"input": 0.0008, "output": 0.0032},
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0": {"input": 0.003, "output": 0.015},
}
_INFRA_COSTS = {
    "dynamodb_monthly": 25.0,
    "cloudwatch_monthly": 15.0,
    "xray_monthly": 5.0,
}


def estimate_monthly_costs(agents: list[dict[str, Any]]) -> dict[str, Any]:
    total = 0.0
    breakdown = []
    for agent in agents:
        pricing = _MODEL_PRICING.get(agent["model"], {"input": 0.001, "output": 0.005})
        daily_reqs = agent["daily_requests"]
        tokens = agent["tokens_per_request"]
        monthly = daily_reqs * 30 * tokens / 1000 * (
            (pricing["input"] + pricing["output"]) / 2
        )
        total += monthly
        breakdown.append({
            "agent": agent["name"],
            "model": agent["model"],
            "monthly_usd": round(monthly, 2),
        })
    for name, cost in _INFRA_COSTS.items():
        total += cost
        breakdown.append({"agent": name, "model": "infrastructure", "monthly_usd": cost})
    return {
        "total_monthly_usd": round(total, 2),
        "breakdown": breakdown,
    }


# ============================================================================
# Step 4: Deploy to AgentCore Runtime
# ============================================================================

def _build_artifact_zip() -> bytes:
    """Package main.py into a deployment ZIP in memory."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        main_path = Path(__file__).parent / "main.py"
        if main_path.exists():
            zf.write(main_path, "main.py")
        else:
            zf.writestr("main.py", "# AgentCore Runtime entrypoint\n")
    return buf.getvalue()


def deploy_to_agentcore(
    exports: dict[str, str],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Deploy the insurance claims runtime to AgentCore Runtime."""
    role_arn = _require_export(exports, _EXPORT_ROLE)
    bucket_name = _require_export(exports, _EXPORT_BUCKET)
    guardrail_id = _require_export(exports, _EXPORT_GUARDRAIL)

    RUNTIME_CONFIG["roleArn"] = role_arn
    RUNTIME_CONFIG["guardrailConfiguration"]["guardrailIdentifier"] = guardrail_id

    print("\n=== Deployment Plan ===")
    print(f"  Runtime name : {RUNTIME_CONFIG['agentRuntimeName']}")
    print(f"  Role ARN     : {role_arn}")
    print(f"  Artifact bucket: {bucket_name}")
    print(f"  Guardrail ID : {guardrail_id}")
    print(f"  Network      : {RUNTIME_CONFIG['networkConfiguration']['networkMode']}")
    print(f"  Protocol     : {RUNTIME_CONFIG['protocolConfiguration']['serverProtocol']}")

    if dry_run:
        print("\n[dry-run] skipping actual deployment")
        return {"status": "dry-run"}

    s3 = boto3.client("s3", region_name=AWS_REGION)
    control = boto3.client("bedrock-agentcore-control", region_name=AWS_REGION)

    # Upload artifact
    artifact_key = f"{RUNTIME_CONFIG['agentRuntimeName']}/deployment.zip"
    print(f"\nUploading artifact to s3://{bucket_name}/{artifact_key}...")
    s3.put_object(
        Bucket=bucket_name,
        Key=artifact_key,
        Body=_build_artifact_zip(),
        ContentType="application/zip",
    )

    # Idempotency check
    try:
        existing = control.get_agent_runtime(
            agentRuntimeName=RUNTIME_CONFIG["agentRuntimeName"]
        )
        print(f"Runtime already exists: {existing.get('agentRuntimeArn')}")
        return {"status": "already-exists", "arn": existing.get("agentRuntimeArn")}
    except control.exceptions.ResourceNotFoundException:
        pass

    # WORKAROUND: inject guardrail via before-call event hook
    def _inject_guardrail(params, **kwargs):
        params["guardrailConfiguration"] = {
            "guardrailIdentifier": guardrail_id,
            "guardrailVersion": RUNTIME_CONFIG["guardrailConfiguration"]["guardrailVersion"],
        }

    control.meta.events.register(
        "before-call.bedrock-agentcore-control.CreateAgentRuntime", _inject_guardrail
    )

    print("Creating AgentCore Runtime...")
    try:
        response = control.create_agent_runtime(
            agentRuntimeName=RUNTIME_CONFIG["agentRuntimeName"],
            roleArn=role_arn,
            networkConfiguration=RUNTIME_CONFIG["networkConfiguration"],
            protocolConfiguration=RUNTIME_CONFIG["protocolConfiguration"],
            environmentVariables=RUNTIME_CONFIG["environmentVariables"],
            agentRuntimeArtifact={
                "codeConfiguration": {
                    "code": {
                        "s3": {
                            "bucket": bucket_name,
                            "prefix": artifact_key,
                        }
                    },
                    "runtime": "PYTHON_3_12",
                    "entryPoint": ["main.py"],
                }
            },
        )
        runtime_arn = response.get("agentRuntimeArn", "")
        print(f"Created: {runtime_arn}")
    except ClientError as error:
        print(f"ERROR creating runtime: {error}")
        return {"status": "error", "message": str(error)}

    # Wait for ready
    print("Waiting for runtime to become ACTIVE...")
    for _ in range(60):
        try:
            status = control.get_agent_runtime(
                agentRuntimeName=RUNTIME_CONFIG["agentRuntimeName"]
            )
            state = status.get("status", "")
            if state == "ACTIVE":
                print(f"Runtime ACTIVE: {runtime_arn}")
                break
        except ClientError:
            pass
        time.sleep(5)
    else:
        print("WARNING: runtime did not reach ACTIVE within timeout")

    # Configure logging
    try:
        control.put_agent_runtime_logging_configuration(
            agentRuntimeName=RUNTIME_CONFIG["agentRuntimeName"],
            loggingConfiguration={
                "cloudWatch": {
                    "logGroupName": f"/aws/bedrock-agentcore/runtimes/{RUNTIME_CONFIG['agentRuntimeName']}",
                    "roleArn": role_arn,
                },
                "xrayEnabled": MONITORING_STRATEGY["xray_tracing"]["enabled"],
            },
        )
        print("Logging configuration applied (CloudWatch + X-Ray)")
    except ClientError as error:
        print(f"WARNING: logging config failed: {error}")

    return {"status": "deployed", "arn": runtime_arn}


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    print("=" * 70)
    print("Lesson 10 Demo — Insurance Claims Deployment Walkthrough")
    print("=" * 70)

    # Discover infrastructure
    print("\n[1] Discovering infrastructure via CloudFormation exports...")
    exports = _load_cf_exports()
    role_arn = _require_export(exports, _EXPORT_ROLE)
    bucket_name = _require_export(exports, _EXPORT_BUCKET)
    guardrail_id = _require_export(exports, _EXPORT_GUARDRAIL)
    print(f"  Role ARN     : {role_arn}")
    print(f"  Artifact bucket: {bucket_name}")
    print(f"  Guardrail ID : {guardrail_id}")

    # Runtime config
    print("\n[2] AgentCore Runtime configuration...")
    RUNTIME_CONFIG["roleArn"] = role_arn
    RUNTIME_CONFIG["guardrailConfiguration"]["guardrailIdentifier"] = guardrail_id
    print(f"  Runtime      : {RUNTIME_CONFIG['agentRuntimeName']}")
    print(f"  Network      : {RUNTIME_CONFIG['networkConfiguration']['networkMode']}")
    print(f"  Protocol     : {RUNTIME_CONFIG['protocolConfiguration']['serverProtocol']}")
    print(f"  Guardrail    : {guardrail_id} ({RUNTIME_CONFIG['guardrailConfiguration']['guardrailVersion']})")
    for k, v in RUNTIME_CONFIG["environmentVariables"].items():
        print(f"  env[{k}] = {v}")

    # Agent definitions
    print("\n[3] Agent definitions...")
    for agent in AGENT_DEFINITIONS:
        print(f"  {agent['name']:20s} model={agent['model']} temp={agent['temperature']} "
              f"req/day={agent['daily_requests']:,}")

    # Deployment pipeline
    print("\n[4] Deployment pipeline...")
    for step in DEPLOYMENT_PIPELINE:
        print(f"  Step {step['step']}: {step['name']}")
        print(f"    command : {step['command']}")
        print(f"    gate    : {step['gate']}")

    # Monitoring
    print("\n[5] Monitoring strategy...")
    print(f"  Widgets       : {', '.join(MONITORING_STRATEGY['cloudwatch_widgets'])}")
    for alarm in MONITORING_STRATEGY["alarms"]:
        print(f"  Alarm {alarm['name']}: {alarm['metric']} {alarm['stat'] or ''} "
              f"threshold={alarm['threshold']} -> {alarm['action']}")
    xray = MONITORING_STRATEGY["xray_tracing"]
    print(f"  X-Ray         : enabled={xray['enabled']} sampling={xray['sampling_rate']}")

    # Cost estimate
    print("\n[6] Cost estimate (10,000 requests/day)...")
    costs = estimate_monthly_costs(AGENT_DEFINITIONS)
    for item in costs["breakdown"]:
        print(f"  {item['agent']:20s} {item['model']:50s} ${item['monthly_usd']:>7.2f}/mo")
    print(f"  {'TOTAL':20s} {'':50s} ${costs['total_monthly_usd']:>7.2f}/mo")

    # Deploy
    print("\n[7] Deploying to AgentCore Runtime...")
    result = deploy_to_agentcore(exports, dry_run=False)
    print(f"\n  Result: {result.get('status')}")
    if result.get("arn"):
        print(f"  ARN: {result['arn']}")

    print("\n" + "=" * 70)
    print("Walkthrough complete")
    print("=" * 70)


if __name__ == "__main__":
    main()
