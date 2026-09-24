# VectraBank Architecture — Lesson 10 Exercise

Production deployment architecture for a multi-agent financial services platform on Amazon Bedrock AgentCore Runtime.

## What this exercise teaches

| Concept | Implementation |
|---------|----------------|
| VPC runtime isolation | Network mode = VPC with private subnets and security groups |
| Compliance guardrails | Financial PII blocking, topic denial (insider trading, fraud), profanity filters |
| Multi-model tiering | Lightweight models for routing/retrieval, capable model for financial synthesis |
| Monitoring strategy | 6 CloudWatch widgets, 3 alarms (error rate, latency, guardrail violations), X-Ray tracing |
| Cost estimation | Model usage + infrastructure costs (DynamoDB, KBs, CloudWatch, VPC NAT) |
| Operational runbooks | Deploy, rollback, kill switch, latency investigation procedures |
| Resource discovery | CloudFormation exports for role ARN, bucket name, guardrail ID |

## Setup

```bash
cp .env.example .env   # ensure AWS_REGION is set
python infrastructure/deploy_stack.py
python vectrabank_architecture.py
```

## Cleanup

```bash
aws cloudformation delete-stack --stack-name lesson-10-exercise-runtime --region us-east-1
```
