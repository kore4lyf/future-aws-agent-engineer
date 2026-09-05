# Bedrock Flows API — Lessons Learned

## Overview

Bedrock Flows allows visual orchestration of AI workflows using nodes and connections. We built a Text Helper Flow that classifies user intent and routes to specialist prompts.

## Key Learnings

### 1. Node Types and Their Required Input/Output Names

| Node Type | Required Input Name | Required Output Name |
|-----------|---------------------|----------------------|
| **FlowInput** | — | `document` (String) |
| **Prompt** | `input` (String) | `modelCompletion` (String) |
| **Condition** | `conditionInput` (String) | — (no outputs) |
| **FlowOutput** | `document` (String) | — |

**Critical:** You cannot use custom names for these. Bedrock Flows enforces specific names.

### 2. FlowInput Must Output `document`

```python
# WRONG
{
    'name': 'FlowInput',
    'type': 'Input',
    'outputs': [{'name': 'user_message', 'type': 'String'}]  # ❌ Wrong name
}

# CORRECT
{
    'name': 'FlowInput',
    'type': 'Input',
    'outputs': [{'name': 'document', 'type': 'String'}]  # ✅ Correct
}
```

### 3. Prompt Nodes Output `modelCompletion`

```python
# WRONG
{
    'name': 'Classifier',
    'type': 'Prompt',
    'outputs': [{'name': 'response', 'type': 'String'}]  # ❌ Wrong name
}

# CORRECT
{
    'name': 'Classifier',
    'type': 'Prompt',
    'outputs': [{'name': 'modelCompletion', 'type': 'String'}]  # ✅ Correct
}
```

### 4. Expressions Use `$.data` Format

```python
# WRONG - using $.node.output
{
    'name': 'input',
    'expression': '$.FlowInput.document'  # ❌ Wrong format
}

# CORRECT - using $.data
{
    'name': 'input',
    'expression': '$.data'  # ✅ Correct
}
```

### 5. Condition Node Needs a Default

```python
# WRONG - no default condition
{
    'name': 'RouteByIntent',
    'type': 'Condition',
    'configuration': {
        'condition': {
            'conditions': [
                {'name': 'summarize', 'expression': 'conditionInput == "summarize"'},
                {'name': 'rewrite', 'expression': 'conditionInput == "rewrite"'}
            ]
        }
    }
}

# CORRECT - with default
{
    'name': 'RouteByIntent',
    'type': 'Condition',
    'configuration': {
        'condition': {
            'conditions': [
                {'name': 'summarize', 'expression': 'conditionInput == "summarize"'},
                {'name': 'rewrite', 'expression': 'conditionInput == "rewrite"'},
                {'name': 'default'}  # ✅ Required
            ]
        }
    }
}
```

### 6. Condition Expressions Are Limited to 64 Characters

```python
# WRONG - too long
'expression': 'conditionInput == "summarize" or conditionInput == "summary"'  # ❌ Too long

# CORRECT - keep short
'expression': 'conditionInput == "summarize"'  # ✅ Under 64 chars
```

### 7. Multiple Output Nodes Required

Bedrock Flows only allows **one connection per Output input**. You cannot have multiple Prompt nodes connecting to the same Output node.

```python
# WRONG - shared output node
{
    'connections': [
        {'source': 'Summarizer', 'target': 'FlowOutput'},
        {'source': 'Rewriter', 'target': 'FlowOutput'}  # ❌ Fails
    ]
}

# CORRECT - separate output nodes
{
    'connections': [
        {'source': 'Summarizer', 'target': 'SummarizerOutput'},
        {'source': 'Rewriter', 'target': 'RewriterOutput'}  # ✅ Works
    ]
}
```

### 8. Specialist Nodes Need Data Connections from FlowInput

Condition nodes only pass control, not data. Specialist nodes need separate Data connections from FlowInput.

```python
# WRONG - no data connection
{
    'connections': [
        {'type': 'Conditional', 'source': 'RouteByIntent', 'target': 'Summarizer'}
        # ❌ Summarizer has no input data
    ]
}

# CORRECT - add data connection
{
    'connections': [
        {'type': 'Conditional', 'source': 'RouteByIntent', 'target': 'Summarizer'},
        {'type': 'Data', 'source': 'FlowInput', 'target': 'Summarizer',  # ✅ Data
         'configuration': {'data': {'sourceOutput': 'document', 'targetInput': 'input'}}}
    ]
}
```

### 9. Prompt Nodes Require `inputVariables` in Template Config

```python
# WRONG - no inputVariables
{
    'templateConfiguration': {
        'text': {
            'text': 'Summarize: {{input}}'
        }
    }
}

# CORRECT - with inputVariables
{
    'templateConfiguration': {
        'text': {
            'text': 'Summarize: {{input}}',
            'inputVariables': [{'name': 'input'}]  # ✅ Required
        }
    }
}
```

### 10. InvokeFlow API Uses `nodeOutputName`

```python
# WRONG - using nodeInputName
response = bedrock_runtime.invoke_flow(
    flowIdentifier=flow_id,
    flowAliasIdentifier=alias_arn,
    inputs=[{'nodeInputName': 'document', 'content': {'document': 'Hello'}}]  # ❌ Wrong
)

# CORRECT - using nodeOutputName
response = bedrock_runtime.invoke_flow(
    flowIdentifier=flow_id,
    flowAliasIdentifier=alias_arn,
    inputs=[{'nodeOutputName': 'document', 'content': {'document': 'Hello'}}]  # ✅ Correct
)
```

### 11. FlowOutput Content Format

```python
# WRONG - string content
{'content': {'document': 'Hello'}}  # ❌ Wrong

# CORRECT - dict content
{'content': {'document': {'document': 'Hello'}}}  # ✅ Correct
```

### 12. Flow Validation Is Async

After creating a flow, check validation status:

```python
response = bedrock_agent.get_flow(flowIdentifier=flow_id)
validation = response.get('validation', {})
if validation.get('status') == 'FAILED':
    for detail in validation.get('details', []):
        print(f"Error: {detail.get('message')}")
```

## Complete Connection Map (Text Helper Flow)

```
FlowInput ──(Data)──> Classifier ──(Data)──> RouteByIntent
    │                                            │
    │                              ┌─────────────┼─────────────┐
    │                              │             │             │
    │                         (Conditional) (Conditional) (Conditional)
    │                              │             │             │
    ├──(Data)──> Summarizer <──────┘             │             │
    │              │                             │             │
    │         (Data)                            │             │
    │              │                             │             │
    │         SummarizerOutput                   │             │
    │                                            │             │
    ├──(Data)──> Rewriter <──────────────────────┘             │
    │              │                                          │
    │         (Data)                                          │
    │              │                                          │
    │         RewriterOutput                                  │
    │                                                         │
    └──(Data)──> Clarifier <──────────────────────────────────┘
                    │
               (Data)
                    │
               ClarifierOutput
```

## Cost Optimization

### Model Selection

| Model | Input (per 1M) | Output (per 1M) | Use When |
|-------|----------------|------------------|----------|
| Nova Micro | $0.035 | $0.14 | Simple classification |
| Nova Lite | $0.06 | $0.24 | Most tasks |
| Nova Pro | $0.80 | $3.20 | Complex reasoning |

### Cost Per Invocation (Text Helper Flow)

| Component | Nova Pro | Nova Lite |
|-----------|----------|-----------|
| Classifier | ~$0.0001 | ~$0.00001 |
| Specialist | ~$0.001 | ~$0.0001 |
| Node transitions | ~$0.0002 | ~$0.0002 |
| **Total** | ~$0.0013 | ~$0.00013 |

**Recommendation:** Use Nova Lite for classifier and specialist unless complex reasoning is needed.

## Debugging Tips

1. **Check validation status** after creating/updating a flow
2. **Enable CloudWatch logging** for flow executions
3. **Test with simple inputs** first
4. **Verify node output names** match connection targets
5. **Check condition expressions** for syntax errors

## Files Created

| File | Purpose |
|------|---------|
| `create_flow.py` | Creates the flow via boto3 |
| `test_flow.py` | Tests the flow with sample inputs |
| `cleanup.py` | Deletes the flow and alias |
| `.env` | AWS credentials and config |
| `.gitignore` | Prevents committing .env |

## IAM Requirements

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:CreateFlow",
                "bedrock:PrepareFlow",
                "bedrock:CreateFlowVersion",
                "bedrock:CreateFlowAlias",
                "bedrock:InvokeFlow",
                "bedrock:GetFlow",
                "bedrock:DeleteFlow"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "iam:CreateRole",
                "iam:PutRolePolicy",
                "iam:GetRole"
            ],
            "Resource": "*"
        }
    ]
}
```
