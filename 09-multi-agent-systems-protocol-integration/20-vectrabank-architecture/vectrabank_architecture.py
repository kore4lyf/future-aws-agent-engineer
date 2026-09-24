# =============================================================================
# VectraBank Architecture — Lesson 10 Exercise
# =============================================================================
# Production deployment architecture for a multi-agent financial services platform.
#   1. Runtime environment (VPC, guardrails, env vars)
#   2. Agent definitions (4 agents, multi-model tiering)
#   3. Monitoring strategy (6 widgets, 3 alarms, X-Ray)
#   4. Infrastructure cost estimate
#   5. Operational runbooks
#   6. Formatted architecture plan output
# ============================================================================

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import boto3

sys.path.insert(0, str(Path(__file__).parent))

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
STACK_NAME = "lesson-10-exercise-runtime"

# CloudFormation export names
_EXPORT_ROLE = "lesson-10-exercise-AgentCoreRoleArn"
_EXPORT_BUCKET = "lesson-10-exercise-ArtifactBucketName"
_EXPORT_GUARDRAIL = "lesson-10-exercise-GuardrailId"

# Model pricing (per 1K tokens, blended input/output)
MODEL_PRICING = {
    "amazon.nova-lite-v1:0": {"input": 0.00006, "output": 0.00024},
    "amazon.nova-pro-v1:0": {"input": 0.0008, "output": 0.0032},
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0": {"input": 0.003, "output": 0.015},
}


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
# Step 1: Runtime environment (VPC, guardrails, env vars)
# ============================================================================

RUNTIME_CONFIG: dict[str, Any] = {
    "agentRuntimeName": "vectrabank_runtime",
    "roleArn": "",  # filled from CF export
    "networkConfiguration": {
        "networkMode": "VPC",
        "vpcConfiguration": {
            "vpcId": "vpc-vectrabank-production",
            "subnetIds": ["subnet-vectrabank-private-a", "subnet-vectrabank-private-b"],
            "securityGroupIds": ["sg-vectrabank-agentcore"],
        },
    },
    "protocolConfiguration": {"serverProtocol": "MCP"},
    "guardrailConfiguration": {
        "guardrailIdentifier": "",  # filled from CF export
        "guardrailVersion": "DRAFT",
    },
    "environmentVariables": {
        "QUERY_KB_ID": "KB-QUERY-001",
        "MARKET_KB_ID": "KB-MARKET-002",
        "COMPLIANCE_KB_ID": "KB-COMPLIANCE-003",
        "STATE_TABLE_NAME": "vectrabank-session-state",
        "AWS_REGION": AWS_REGION,
        "LOG_LEVEL": "INFO",
        "ENVIRONMENT": "production",
    },
}


# ============================================================================
# Step 2: Agent definitions (4 agents, multi-model tiering)
# ============================================================================

AGENT_DEFINITIONS = [
    {
        "name": "QueryRouter",
        "model": "amazon.nova-lite-v1:0",
        "temperature": 0.0,
        "daily_requests": 20_000,
        "tokens_per_request": 300,
        "role": "Routes incoming queries to the appropriate specialized agent",
    },
    {
        "name": "MarketDataRetriever",
        "model": "amazon.nova-lite-v1:0",
        "temperature": 0.0,
        "daily_requests": 15_000,
        "tokens_per_request": 500,
        "role": "Retrieves real-time market data and stock information",
    },
    {
        "name": "ComplianceRetriever",
        "model": "amazon.nova-lite-v1:0",
        "temperature": 0.0,
        "daily_requests": 8_000,
        "tokens_per_request": 800,
        "role": "Retrieves regulatory compliance information and policies",
    },
    {
        "name": "FinancialAdvisor",
        "model": "us.anthropic.claude-sonnet-4-20250514-v1:0",
        "temperature": 0.1,
        "daily_requests": 10_000,
        "tokens_per_request": 2_500,
        "role": "Synthesizes retrieved data into grounded financial analysis with citations",
    },
]


# ============================================================================
# Step 3: Monitoring strategy (6 widgets, 3 alarms, X-Ray)
# ============================================================================

MONITORING_STRATEGY: dict[str, Any] = {
    "cloudwatch_widgets": [
        "Invocations per minute by agent",
        "Latency P50/P99 by agent",
        "Error rate by agent and error type",
        "Guardrail blocks by policy (PII, topic, content, word)",
        "RAG Retrieval Quality (avg relevance score)",
        "Kill Switch Status",
    ],
    "alarms": [
        {
            "name": "HighErrorRate",
            "metric": "AgentCore/Errors",
            "threshold": 0.02,
            "period": 300,
            "action": "SNS -> kill-switch-topic -> Lambda disables runtime",
            "description": "Error rate exceeds 2% in 5 minutes - automatic kill switch",
        },
        {
            "name": "HighLatency",
            "metric": "AgentCore/Latency",
            "stat": "p99",
            "threshold": 8.0,
            "period": 300,
            "action": "SNS -> ops-team-pager",
            "description": "P99 latency exceeds 8 seconds - page on-call",
        },
        {
            "name": "GuardrailViolationSpike",
            "metric": "Guardrail/TotalBlocks",
            "threshold": 50,
            "period": 300,
            "action": "SNS -> security-team + rate-limit-increase",
            "description": "50+ guardrail blocks in 5 minutes - potential coordinated attack",
        },
    ],
    "xray_tracing": {
        "enabled": True,
        "sampling_rate": 0.10,
        "annotations": ["query_type", "agent_name", "model_id", "customer_tier"],
    },
}


# ============================================================================
# Step 4: Infrastructure cost estimate
# ============================================================================

_INFRA_COSTS = {
    "dynamodb_monthly": 25.0,
    "knowledge_bases_monthly": 45.0,
    "cloudwatch_monthly": 25.0,
    "vpc_nat_gateway_monthly": 35.0,
    "s3_storage_monthly": 5.0,
    "xray_monthly": 10.0,
}


def estimate_monthly_costs(agents: list[dict[str, Any]]) -> dict[str, Any]:
    """Estimate monthly costs including model usage and infrastructure."""
    total = 0.0
    breakdown = []

    # Model costs
    for agent in agents:
        pricing = MODEL_PRICING.get(agent["model"], {"input": 0.001, "output": 0.005})
        daily_reqs = agent["daily_requests"]
        tokens = agent["tokens_per_request"]
        monthly = daily_reqs * 30 * tokens / 1000 * (
            (pricing["input"] + pricing["output"]) / 2
        )
        total += monthly
        breakdown.append({
            "agent": agent["name"],
            "model": agent["model"],
            "type": "model",
            "monthly_usd": round(monthly, 2),
        })

    # Infrastructure costs
    for name, cost in _INFRA_COSTS.items():
        total += cost
        breakdown.append({
            "agent": name,
            "model": "infrastructure",
            "type": "infrastructure",
            "monthly_usd": cost,
        })

    return {
        "total_monthly_usd": round(total, 2),
        "breakdown": breakdown,
    }


# ============================================================================
# Step 5: Operational runbooks
# ============================================================================

OPERATIONAL_RUNBOOKS = {
    "deploy_new_version": {
        "name": "Deploy New Version",
        "description": "Safe deployment procedure for updating the VectraBank runtime",
        "steps": [
            "1. Run full test suite: pytest test/ -v --tb=short",
            "2. Promote guardrail to new version: python infrastructure/promote_guardrail.py --to-version <N>",
            "3. Build deployment artifact: python infrastructure/build_artifact.py",
            "4. Upload artifact to S3: aws s3 cp deployment.zip s3://<bucket>/<prefix>/",
            "5. Update runtime: aws bedrock-agentcore-control update-agent-runtime --agent-runtime-name vectrabank_runtime --agent-runtime-artifact <s3-path>",
            "6. Wait for ACTIVE status: aws bedrock-agentcore-control get-agent-runtime --agent-runtime-name vectrabank_runtime",
            "7. Run smoke test: python smoke_test.py --claims 10 --max-latency 5s",
            "8. Monitor CloudWatch dashboard for 15 minutes",
            "9. If all gates pass, mark deployment as successful",
            "10. If any gate fails, execute emergency rollback runbook",
        ],
    },
    "emergency_rollback": {
        "name": "Rollback",
        "description": "Immediate rollback to previous stable version",
        "steps": [
            "1. Identify last known good version from deployment history",
            "2. Disable current runtime: aws bedrock-agentcore-control update-agent-runtime --agent-runtime-name vectrabank_runtime --status DISABLED",
            "3. Restore previous artifact: aws s3 cp s3://<bucket>/<prefix>/previous/deployment.zip ./",
            "4. Re-upload and update runtime with previous artifact",
            "5. Wait for ACTIVE status",
            "6. Run smoke test to verify rollback",
            "7. Notify stakeholders via SNS topic: vectrabank-deployment-alerts",
            "8. Create incident ticket with timeline and root cause",
            "9. Schedule post-mortem within 24 hours",
        ],
    },
    "kill_switch_triggered": {
        "name": "Kill Switch Triggered",
        "description": "Emergency disable of the runtime during active security incident",
        "steps": [
            "1. Trigger immediate disable: aws bedrock-agentcore-control update-agent-runtime --agent-runtime-name vectrabank_runtime --status DISABLED",
            "2. Verify runtime status: aws bedrock-agentcore-control get-agent-runtime --agent-runtime-name vectrabank_runtime",
            "3. Notify security team via SNS: vectrabank-security-incidents",
            "4. Preserve logs: aws logs create-export-task --log-group-name /aws/bedrock-agentcore/runtimes/vectrabank_runtime --from <timestamp> --to <timestamp> --destination <s3-bucket>",
            "5. Capture CloudWatch metrics snapshot for forensic analysis",
            "6. Do NOT re-enable until security team conducts full investigation",
            "7. Document incident in compliance tracker with timestamps and affected services",
        ],
    },
    "latency_investigation": {
        "name": "Latency Investigation",
        "description": "Systematic troubleshooting for P99 latency exceeding 8 seconds",
        "steps": [
            "1. Check CloudWatch dashboard for latency spike timeline",
            "2. Identify which agent(s) show elevated latency",
            "3. Review X-Ray traces for affected requests - look for:",
            "   - Model invocation latency (Bedrock throttling?)",
            "   - Tool call latency (Knowledge Base retrieval slow?)",
            "   - Network latency (VPC NAT gateway issues?)",
            "4. Check Bedrock throttling metrics: GetMetricData for ThrottledRequests",
            "5. Review recent deployments - did a new version correlate with spike?",
            "6. Check Knowledge Base query latency in CloudWatch",
            "7. If model throttling: request quota increase via AWS Support",
            "8. If KB slow: check OpenSearch Serverless collection health",
            "9. If network: check VPC flow logs and NAT gateway metrics",
            "10. Implement fix and monitor for 30 minutes before closing incident",
        ],
    },
}


# ============================================================================
# Step 6: Format output
# ============================================================================

def format_architecture_plan(
    runtime_config: dict[str, Any],
    agents: list[dict[str, Any]],
    monitoring: dict[str, Any],
    costs: dict[str, Any],
    runbooks: dict[str, Any],
) -> str:
    """Format the complete architecture plan for console output."""
    lines = []
    lines.append("=" * 70)
    lines.append("VectraBank Production Architecture Plan")
    lines.append("=" * 70)

    # Runtime configuration
    lines.append("\n## AgentCore Runtime Configuration")
    lines.append(f"  Runtime name  : {runtime_config['agentRuntimeName']}")
    lines.append(f"  Network mode  : {runtime_config['networkConfiguration']['networkMode']}")
    lines.append(f"  Protocol      : {runtime_config['protocolConfiguration']['serverProtocol']}")
    lines.append(f"  Guardrail     : {runtime_config['guardrailConfiguration']['guardrailIdentifier']}")
    lines.append(f"  Guardrail ver : {runtime_config['guardrailConfiguration']['guardrailVersion']}")
    lines.append("  Environment variables:")
    for k, v in runtime_config["environmentVariables"].items():
        lines.append(f"    {k} = {v}")

    # Agent definitions
    lines.append("\n## Agent Definitions")
    for agent in agents:
        lines.append(f"  {agent['name']:25s} model={agent['model']}")
        lines.append(f"    {'':25s} temp={agent['temperature']} req/day={agent['daily_requests']:,} tokens/req={agent['tokens_per_request']}")

    # Monitoring
    lines.append("\n## Monitoring Strategy")
    lines.append("  CloudWatch widgets:")
    for widget in monitoring["cloudwatch_widgets"]:
        lines.append(f"    - {widget}")
    lines.append("  Alarms:")
    for alarm in monitoring["alarms"]:
        lines.append(f"    - {alarm['name']}: {alarm['metric']} threshold={alarm['threshold']} -> {alarm['action']}")
    xray = monitoring["xray_tracing"]
    lines.append(f"  X-Ray tracing: enabled={xray['enabled']} sampling_rate={xray['sampling_rate']}")

    # Costs
    lines.append("\n## Cost Estimate")
    for item in costs["breakdown"]:
        lines.append(f"  {item['agent']:30s} {item['model']:50s} ${item['monthly_usd']:>7.2f}/mo")
    lines.append(f"  {'TOTAL':30s} {'':50s} ${costs['total_monthly_usd']:>7.2f}/mo")

    # Runbooks
    lines.append("\n## Operational Runbooks")
    for key, runbook in runbooks.items():
        lines.append(f"  {runbook['name']}:")
        for step in runbook["steps"]:
            lines.append(f"    {step}")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    print("=" * 70)
    print("VectraBank Architecture — Lesson 10 Exercise")
    print("=" * 70)

    # Discover infrastructure
    print("\n[1] Discovering infrastructure via CloudFormation exports...")
    exports = _load_cf_exports()
    role_arn = _require_export(exports, _EXPORT_ROLE)
    bucket_name = _require_export(exports, _EXPORT_BUCKET)
    guardrail_id = _require_export(exports, _EXPORT_GUARDRAIL)
    print(f"  Role ARN      : {role_arn}")
    print(f"  Artifact bucket: {bucket_name}")
    print(f"  Guardrail ID  : {guardrail_id}")

    # Runtime config
    print("\n[2] Configuring runtime environment (VPC)...")
    RUNTIME_CONFIG["roleArn"] = role_arn
    RUNTIME_CONFIG["guardrailConfiguration"]["guardrailIdentifier"] = guardrail_id
    print(f"  Runtime       : {RUNTIME_CONFIG['agentRuntimeName']}")
    print(f"  Network       : {RUNTIME_CONFIG['networkConfiguration']['networkMode']}")
    print(f"  Guardrail     : {guardrail_id}")

    # Agent definitions
    print("\n[3] Defining agents...")
    for agent in AGENT_DEFINITIONS:
        print(f"  {agent['name']:25s} model={agent['model']}")

    # Monitoring
    print("\n[4] Designing monitoring strategy...")
    print(f"  Widgets: {len(MONITORING_STRATEGY['cloudwatch_widgets'])}")
    print(f"  Alarms  : {len(MONITORING_STRATEGY['alarms'])}")
    print(f"  X-Ray   : sampling_rate={MONITORING_STRATEGY['xray_tracing']['sampling_rate']}")

    # Cost estimate
    print("\n[5] Estimating infrastructure costs...")
    costs = estimate_monthly_costs(AGENT_DEFINITIONS)
    for item in costs["breakdown"]:
        print(f"  {item['agent']:30s} ${item['monthly_usd']:>7.2f}/mo")
    print(f"  {'TOTAL':30s} ${costs['total_monthly_usd']:>7.2f}/mo")

    # Runbooks
    print("\n[6] Developing operational runbooks...")
    for key, runbook in OPERATIONAL_RUNBOOKS.items():
        print(f"  {runbook['name']}: {len(runbook['steps'])} steps")

    # Format and print architecture plan
    print("\n[7] Formatting architecture plan...")
    plan = format_architecture_plan(
        RUNTIME_CONFIG, AGENT_DEFINITIONS, MONITORING_STRATEGY, costs, OPERATIONAL_RUNBOOKS
    )
    print(plan)

    print("\n" + "=" * 70)
    print("Architecture plan complete")
    print("=" * 70)


if __name__ == "__main__":
    main()
