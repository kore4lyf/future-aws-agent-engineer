# Flow Diagram Evidence

## Bedrock Flow: customer-support-flow

**Flow ID:** JA2RHHT2BG
**Flow ARN:** arn:aws:bedrock:us-east-1:708026873259:flow/JA2RHHT2BG
**Flow Alias:** ABAVBNIFQQ
**Status:** Prepared

## Flow Structure (7 nodes)

```
FlowInput
   │
   ▼
Classifier (Prompt)
   │
   ▼
RouteByCategory (Condition)
   │
   ├── bug_report ──► BugReportHandler (Prompt) ──► BugReportOutput
   │
   ├── platform_question ──► FAQHandler (Prompt) ──► FAQOutput
   │
   └── default ──► OtherHandler (Prompt) ──► OtherOutput
```

## Screenshot Instructions

To capture the flow diagram screenshot:
1. Open AWS Console → Amazon Bedrock → Flows
2. Select `customer-support-flow`
3. The visual flow diagram will show all 7 nodes and connections
4. Take a screenshot showing the complete flow from FlowInput to the three Output nodes

## Node Details

| Node | Type | Purpose |
|------|------|---------|
| FlowInput | Input | Receives customer message |
| Classifier | Prompt | Classifies message into bug_report/platform_question/other |
| RouteByCategory | Condition | Routes to appropriate handler based on classifier output |
| BugReportHandler | Prompt | Collects bug report details and files ticket |
| FAQHandler | Prompt | Answers platform questions from FAQ |
| OtherHandler | Prompt | Redirects non-platform requests to human support |
| BugReportOutput | Output | Bug report response output |
| FAQOutput | Output | FAQ response output |
| OtherOutput | Output | Redirect response output |
