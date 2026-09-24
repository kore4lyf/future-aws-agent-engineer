# Deployment Walkthrough — Lesson 10 Demo

Production deployment walkthrough for an insurance claims multi-agent system on Amazon Bedrock AgentCore Runtime.

## What this demo covers

| Step | Topic | What it shows |
|------|-------|---------------|
| 1 | Resource discovery | Auto-discovers IAM role, S3 bucket, guardrail from CloudFormation exports |
| 2 | Runtime config | PUBLIC network, MCP protocol, guardrail attachment, env vars |
| 3 | Agent architecture | Three-tier: ClaimsRouter (Nova Lite), ClaimsAnalyzer (Claude Sonnet), ClaimsResponder (Nova Pro) |
| 4 | Deployment pipeline | Six gated steps: build, guardrail, runtime, memory, observability, smoke test |
| 5 | Monitoring | CloudWatch widgets, X-Ray tracing, SNS alarms with automated kill switch |
| 6 | Cost estimation | Per-model pricing breakdown (~$2,000/mo at 10K req/day) |
| 7 | Live deploy | Packages ZIP, uploads to S3, calls `create_agent_runtime`, configures logging |

## Setup

```bash
cp .env.example .env   # ensure AWS_REGION is set
python infrastructure/deploy_stack.py
python deployment_walkthrough.py
```

## Cleanup

```bash
aws cloudformation delete-stack --stack-name lesson-10-demo-runtime --region us-east-1
```
