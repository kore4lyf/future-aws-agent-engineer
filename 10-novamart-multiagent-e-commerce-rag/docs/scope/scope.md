# Scope: NovaMart Multi-Agent Customer Support System

A multi agent AI customer support system for NovaMart that automatically understands customer requests, gathers information from multiple data sources, makes decisions based on company policies, and composes professional responses. It serves the NovaMart customer support team by automating order inquiries, return requests, policy questions, and refund decisions using Amazon Bedrock AgentCore and the Strands Agents SDK.

**Build approach:** Journey (each phase delivers a complete, testable slice of the system, building toward full end to end operation).
**Workflow:** Medium (verify then test after build; multi agent graph and guardrail run Full for complexity and safety).

## At a glance

| # | Feature | Phase | Status |
|---|---------|-------|--------|
| 1 | Foundation deployment | Setup | done |
| 2 | Multi-agent graph | Phase 1 | done |
| 3 | Bedrock Guardrail | Phase 2 | in-progress |
| 4 | AgentCore Runtime deployment | Phase 2 | planned |
| 5 | AgentCore Memory | Phase 2 | planned |
| 6 | Bedrock Knowledge Bases | Phase 3 | planned |
| 7 | Observability & tracing | Phase 4 | planned |
| 8 | End-to-end validation | Phase 4 | planned |
| 9 | Persistent DynamoDB session memory | Phase 4 | planned |
| 10 | CloudWatch operations dashboard | Phase 4 | planned |
| 11 | Adversarial guardrail testing | Phase 4 | planned |
| 12 | Frontend & Cognito auth | Phase 4 | planned |

## Setup

### 1. Foundation deployment
Deploy the provided CloudFormation stack, seed DynamoDB tables and S3 with sample data, and verify the environment is ready for agent development.
**Done when:** `python config.py` shows all resource names, `python infrastructure/seed_data.py` populates DynamoDB with mock customers and orders, and S3 contains the policy documents.
- [x] Deploy CloudFormation stack: `python infrastructure/deploy_stack.py` or AWS Console
- [x] Seed data: `python infrastructure/seed_data.py`
- [x] Verify environment: `python config.py` shows all resources
- [x] Copy `.env.example` to `.env`
- [x] Review it: `/check review foundation deployment`

## Phase 1: Multi-Agent Graph

### 2. Multi-agent graph · Full
Build the five Strands Agents in `src/agents/` that form the Orchestrator to Workers hierarchy, plus the shared WorkflowState in DynamoDB with optimistic locking. Every tool function and every data fetch must use a Pydantic schema for input and output validation.
**Done when:** `python tests/test_agent.py task2` passes, all five agents route correctly with WorkflowState management, and every tool function has a Pydantic schema for its inputs and outputs.
- [x] Build it: `/develop multi-agent graph`
   - [x] InventoryAgent: three DynamoDB tools with Pydantic schemas, data gatherer only
   - [x] RefundAgent: two tools with Pydantic schemas, eligibility logic with tier based windows
   - [x] PolicyAgent: three parallel retriever sub agents with ThreadPoolExecutor, all data wrapped in Pydantic schemas
   - [x] CommunicationAgent: one tool with Pydantic schema, composes empathetic response
   - [x] OrchestratorAgent: five routing tools with Pydantic schemas, WorkflowState management
   - code in `src/agents/`
- [x] Verify it: `/check verify multi-agent graph`
- [x] Test it: `/test multi-agent graph`
- [x] Review it: `/check review multi-agent graph`
- [x] Document it: `/document multi-agent graph`

## Phase 2: Deployment

### 3. Bedrock Guardrail · Full
Create a Bedrock Guardrail in `src/deploy/guardrail.py` with content, PII, topic, and word policies, then publish a numbered version.
**Done when:** `create_guardrail()` returns `(guardrail_id, guardrail_version)` and the guardrail correctly blocks or anonymizes test inputs.
- [x] Build it: `/develop bedrock guardrail`
   - [x] Content policy: SEXUAL, VIOLENCE, HATE at HIGH strength; INSULTS, MISCONDUCT at MEDIUM
   - [x] PII policy: BLOCK credit card numbers and SSNs; ANONYMIZE emails and phone numbers
   - [x] Topic policy: DENY competitor products, pricing negotiations, legal threats
   - [x] Word policy: enable managed profanity list
   - [x] Publish numbered version via `create_guardrail_version()`
   - code in `src/agent_orchestrator.py`
- [x] Verify it: `/check verify bedrock guardrail`
- [x] Test it: `/test bedrock guardrail`
- [x] Review it: `/check review bedrock guardrail`
- [x] Document it: `/document bedrock guardrail`

### 4. AgentCore Runtime deployment
Deploy the multi-agent system to AgentCore Runtime in `src/agent_orchestrator.py` using the AgentCore CLI, with guardrail attached via environment variables.
**Done when:** `.env` contains `AGENTCORE_RUNTIME_ARN` and `python tests/test_agent.py task3` passes.
- [x] Build it: `/develop agentcore runtime deployment`
   - [x] Stage code and configure runtime with PUBLIC networking, HTTP protocol, foundation execution role
   - [x] Set runtime environment variables: AWS_REGION, PROJECT_NAME, KB IDs, AGENT_LOG_GROUP, GUARDRAIL_ID, GUARDRAIL_VERSION
   - [x] Deploy via `agentcore_cli.deploy()` and read deployed ARN
- [x] Verify it: `/check verify agentcore runtime deployment`
- [x] Test it: `/test agentcore runtime deployment`

Deployed: `novamart_agentcore_runtime-KFKbdJ7XXQ` (READY, PUBLIC, HTTP). The runtime answers a live
`invoke_agent_runtime` end to end through Orchestrator → Inventory → Communication.
Regression suite: `python -m unittest tests.test_agentcore_runtime_deploy` (44 tests; add
`$env:RUN_LIVE_INVOKE = "1"` for the one real invocation).

Status stays `in-progress` while task3 scores 13/20 rather than 20/20: `test_3_4` also requires
`RETURNS_KB_ID`, `SHIPPING_KB_ID` and `WARRANTY_KB_ID`, which belong to feature 6 (Knowledge Bases,
manual console work). Re-running `python src/agent_orchestrator.py deploy` once those IDs are in
`.env` adds them to the runtime and closes the remaining 7 points, with no code change needed.

### 5. AgentCore Memory
Configure AgentCore Memory in `src/agent_orchestrator.py` with a session summary strategy and seven day event retention. Session memory must be managed at a reasonable length with compression so context stays relevant and efficient.
**Done when:** `python tests/test_agent.py task4` passes, the memory resource reaches ACTIVE status, and session memory compression keeps context within reasonable bounds.
- [x] Build it: `/develop agentcore memory`
   - [x] Create memory resource with `summaryMemoryStrategy` and `eventExpiryDuration=7`
   - [x] Wait for ACTIVE status and return memoryArn
   - [x] Implement session memory management with compression to keep context at a reasonable length
- [x] Verify it: `/check verify agentcore memory`
- [ ] Test it: `/test agentcore memory`

## Phase 3: Knowledge Bases

### 6. Bedrock Knowledge Bases
Create three Bedrock Knowledge Bases in the AWS Console, one per policy domain, backed by the S3 Vectors bucket provisioned by the stack. This is a console task, no code changes required.
**Done when:** All three KBs are created, synced, and `.env` contains valid KB IDs; `python tests/test_agent.py task5` passes including parallel retrieval from all three KBs.
- [ ] Create Returns KB: `novamart-returns-policy-kb` with `policies/returns/` prefix
- [ ] Create Shipping KB: `novamart-shipping-policy-kb` with `policies/shipping/` prefix
- [ ] Create Warranty KB: `novamart-warranty-policy-kb` with `policies/warranty/` prefix
- [ ] Sync each KB and add IDs to `.env`
- [ ] Verify parallel retrieval returns non-empty results from all three KBs

## Phase 4: Observability & Testing

### 7. Observability & tracing
Configure CloudWatch logging and X-Ray tracing in `src/agent_orchestrator.py` for the deployed AgentCore runtime.
**Done when:** `configure_observability()` builds the logging configuration, `python tests/test_agent.py task6` passes, and the X-Ray Service Map shows the full call chain.
- [ ] Build it: `/develop observability`
   - [ ] CloudWatch config: point to `config.AGENT_LOG_GROUP`, INFO level, enabled
   - [ ] X-Ray config: enabled, samplingRate=1.0
   - [ ] Apply via `apply_observability_config()` in try/except
- [ ] Verify it: `/check verify observability`
- [ ] Test it: `/test observability`

### 8. End-to-end validation
Run the full deployment, test all request types, capture screenshots, and confirm all tests pass.
**Done when:** Full test suite passes with 120 scores, X-Ray Service Map screenshot shows connected trace graph, and all submission deliverables are ready.
- [ ] Build it: `/develop end-to-end validation`
   - [ ] Run full deployment: `python src/agent_orchestrator.py deploy`
   - [ ] Run full test suite: `python tests/test_agent.py all`
   - [ ] Test refund scenario: "I want to return my order ORD-27176" routes Inventory to Refund to Communication
   - [ ] Test policy scenario: "What is the return policy for premium customers?" routes Policy to Communication
   - [ ] Test math scenario: "How much are 5 items at $29.99 with 10% off?" routes to CommunicationAgent only
   - [ ] Capture X-Ray Service Map screenshot
   - [ ] Capture passing test suite screenshot
- [ ] Verify it: `/check verify end-to-end validation`
- [ ] Test it: `/test end-to-end validation`

### 9. Persistent DynamoDB session memory
Add persistent conversation memory using the Strands SDK DynamoDbSessionStorage so the agent can recall earlier messages in the same chat session, complementing AgentCore Memory with local session storage.
**Done when:** The Orchestrator uses DynamoDbSessionStorage for multi turn conversation recall, and multi turn conversations retain earlier messages without relying solely on AgentCore Memory.
- [ ] Build it: `/develop persistent DynamoDB session memory`
   - [ ] Create DynamoDB agent-sessions table
   - [ ] Integrate Strands SDK DynamoDbSessionStorage into the Orchestrator
   - [ ] Verify multi turn conversation recall works alongside AgentCore Memory
- [ ] Verify it: `/check verify persistent DynamoDB session memory`
- [ ] Test it: `/test persistent DynamoDB session memory`

### 10. CloudWatch operations dashboard
Build a CloudWatch dashboard showing agent invocation count over time, average response latency per agent type, and Guardrail trigger frequency.
**Done when:** The dashboard displays invocation count, average latency per agent type, and Guardrail trigger frequency, demonstrating production grade observability.
- [ ] Build it: `/develop CloudWatch operations dashboard`
   - [ ] Create dashboard widget for agent invocation count over time
   - [ ] Create dashboard widget for average response latency per agent type
   - [ ] Create dashboard widget for Guardrail trigger frequency
- [ ] Verify it: `/check verify CloudWatch operations dashboard`
- [ ] Test it: `/test CloudWatch operations dashboard`

### 11. Adversarial guardrail testing
Run adversarial inputs against the guardrail including prompt injection attempts, competitor mentions, and legal threats, and document how each is handled with screenshots of blocked responses.
**Done when:** Adversarial inputs are tested, blocked responses are captured in screenshots, and documentation shows how each input type is handled.
- [ ] Build it: `/develop adversarial guardrail testing`
   - [ ] Test prompt injection attempts against the guardrail
   - [ ] Test competitor mentions against the guardrail
   - [ ] Test legal threats against the guardrail
   - [ ] Capture screenshots of blocked responses for each category
   - [ ] Document how each input type is handled
- [ ] Verify it: `/check verify adversarial guardrail testing`
- [ ] Test it: `/test adversarial guardrail testing`

### 12. Frontend & Cognito auth
Integrate AWS Cognito for customer authentication and build a frontend interface that connects to the AgentCore Runtime endpoint, transforming the terminal only system into a fully deployable, user facing customer support application.
**Done when:** Customers can sign in with Cognito, use the web interface to submit support requests, and receive responses from the deployed AgentCore Runtime.
- [ ] Build it: `/develop frontend & Cognito auth`
   - [ ] Set up AWS Cognito user pool and authentication flow
   - [ ] Build React or HTML/JS frontend interface
   - [ ] Connect frontend to AgentCore Runtime endpoint
   - [ ] Test end to end customer journey through the web interface
- [ ] Verify it: `/check verify frontend & Cognito auth`
- [ ] Test it: `/test frontend & Cognito auth`

## Legend

**The decision box.** Every feature carries exactly one, the sub-task whose label ends with `(spec)`. Its wording varies (`Design it (spec)` normally, `Decide the stack (spec)` on Stack & architecture), so skills locate it by that `(spec)` suffix, never by an exact label. Every other box is an execution box and `/architect` never ticks one.

**Feature lifecycle**: the scope updates as a feature moves; each row is what it shows and who sets it:

| State | Set by | The feature shows |
|---|---|---|
| `planned` · needs a decision | `/scope` | one box: `Design it (spec): /architect <feature>` |
| `in-progress` (designed) | `/architect` at spec capture | `Design it` ticked; spec linked; `Build it: /develop <feature>` + 2 to 5 milestones; the tier's closing boxes |
| `in-progress` (building) | `/develop` | milestone sub-boxes tick one by one; code pointer filled |
| `in-progress` (verified) | `/check verify` | `Build it` + milestones ticked; `Verify it` ticked |
| `done` | the tier's last required stage | required boxes ticked; `Review it`/`Document it` (Full) ticked by `/check review`/`/document` |

- **Next step** = the first unticked box (always a command or a tracked milestone).
- **needs a decision** = run `/architect` first; otherwise straight to `/develop`. The tag drops once the spec is captured.
- **Atomic build tasks live in the spec's `## Build plan`, not here**: the scope carries only the milestone rollup.
- **Status** `planned` → `in-progress` → `done`, plus `existing` (pre-workflow) and `dropped` (de-scoped, kept for history).
- **Approach tag** beside a heading (e.g. `· Facade`) overrides the project default for that feature; no tag = inherits it.
- **Workflow tier tag** beside a heading (e.g. `· Full`) overrides the project default tier for that one feature; no tag = inherit.
- **Pointer line** (`spec <n> · code in <path>`): the spec link added by `/architect`, the code path by `/develop`.
