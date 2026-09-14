# Scope: AI Support Agent (Course 2 Capstone)

A conversational support agent for an ecommerce shop. It serves shoppers who track orders, return items, ask product questions, and earn loyalty rewards, all in one chat.

**Build approach:** Tracer Bullet (prove the full pipe with one live run first, then thicken each capability).
**Workflow:** Medium (check verify, then test). The project default rigor tier; architect still gates any feature that needs a decision at every tier; a feature's own tier tag overrides it.

## At a glance

| # | Feature | Phase | Status |
| --- | --- | --- | --- |
| 1 | Local setup and starter scaffold | Foundation | planned |
| 2 | Backend and AWS base | Foundation | planned |
| 3 | Slice 1 core loop with order tracking | Slice 1 | planned |
| 4 | Refund processing | Slice 2 | planned |
| 5 | Product answers with RAG | Slice 3 | planned |
| 6 | Memory across sessions | Slice 4 | planned |
| 7 | Exact discount math | Slice 5 | planned |
| 8 | Live web lookup | Slice 6 | planned |
| 9 | Submission close | Slice 7 | planned |

## Foundations

### 1. Local setup and starter scaffold

Get a clean runnable project in `future-aws-agent-engineer/08-ai-support-agent` with deps installed and deploy config created, so every later slice builds on real structure.
**Done when:** Python 3.14 plus `uv` plus AWS CLI v2 plus Node 18 pass version checks (`pyproject.toml` requires `>=3.14`), `global.amazon.nova-2-lite-v1:0` is enabled in Bedrock Model access (exact ID from `starter/main.py`; the README short form `amazon.nova-lite-v1:0` is stale), the starter repo `udacity/cd14763-project-starter` is cloned, `starter/main.py` is copied in with all 8 TODO sections visible plus `product_catalog.txt` plus `starter/lambda/` untouched, `uv sync` passes (`strands-agents`, `strands-agents-tools`, `bedrock-agentcore`, `bedrock-agentcore-starter-toolkit`, `playwright`, `nest-asyncio`), `aws configure` points at `us-east-1`, and `agentcore configure --entrypoint main.py --name <agent-name>` has created `.bedrock_agentcore.yaml`.

- [ ] Build it: `/develop local setup and starter scaffold`

### 2. Backend and AWS base

Create the cloud ground the agent stands on in `us-east-1` with the exact names from the brief, so Gateway tools, retrieval, and memory have live targets before any agent slice runs.
**Done when:** `order-tracker` (Python 3.12, pasted from `order_tracker.py`) and `refund-processor` (pasted from `refund_processor.py`) are deployed as Lambdas, the REST API exposes `GET /orders/{order_id}` as `get_order` plus `GET /customers/{customer_id}/orders` as `get_customer_orders` plus `GET /customers/{customer_id}` as `get_customer` as Lambda proxy integrations on a live stage (`prod`), `CustomerSupportGateway` uses the NONE authorizer with target `order-tracker` (API Gateway REST API stage, the three GET ops) plus target `refund-processor` (Lambda, tool schema from `starter/lambda/lambda_schema`) and a copied Gateway URL ending in `/mcp`, `product_catalog.txt` is in S3 and `CustomerSupportKB` (Titan Embeddings v2, OpenSearch Serverless auto-created) is synced, `CustomerSupportMemory` holds strategies `customer_facts` at `cs_agent/{actorId}/facts` plus `customer_preferences` at `cs_agent/{actorId}/preferences` with the Memory ID copied, `main.py` holds `GATEWAY_URL` plus `KB_ID` plus `REGION = "us-east-1"` plus `MEMORY_ID`, and all four verify checks pass: (1) `aws sts get-caller-identity`, (2) MCP Inspector lists both targets, (3) KB Test tab answers the 15-day electronics return probe, (4) `uv sync` clean. Cost warning accepted (< $15, sandbox account, NONE authorizer is temporary, no sensitive data).

- [ ] Create the cloud base (console plus CLI): deploy `order-tracker` and `refund-processor`, create the REST API with `get_order` plus `get_customer_orders` plus `get_customer`, create `CustomerSupportGateway` with the API target and the Lambda target, create `CustomerSupportKB` with the catalog data source synced, create `CustomerSupportMemory` with `customer_facts` and `customer_preferences`, fill `GATEWAY_URL` plus `KB_ID` plus `REGION` plus `MEMORY_ID`, pass all four verify checks

## Slice 1: Core loop with order tracking

### 3. Slice 1 core loop with order tracking

Thin real thread through every layer: app clients plus entrypoint plus Gateway order tools plus cloud deploy plus one live invoke, proving the whole pipe connects before thicker slices. Covers TODO 1-3 (init app and clients) plus TODO 8 (entrypoint).
**Done when:** code has `BedrockAgentCoreApp` at module level plus async `invoke` with `@app.entrypoint` plus `app.run()` as main, connects via `MCPClient` plus `streamable_http_client` to `GATEWAY_URL`, loads Gateway tools into the agent tool list, `agentcore deploy` succeeds, and Test 1 `{"prompt": "Can you track order ORD-001?", "customer_id": "CUST-123", "session_id": "t1"}` returns shipping status with tracking number `TRK987654321`, carrier UPS, and a delivery date with no errors. This is the API-based half of the two-tool rubric proof (Slice 2 is the other half).

- [ ] Build it: `/develop Slice 1 core loop with order tracking`

## Slice 2: Returns

### 4. Refund processing

Thicken the thread with the Lambda backed return path, so shoppers can return an item and get a clear refund answer in chat.
**Done when:** the Lambda-target Gateway tool is in the agent tool list, Test 2 `{"prompt": "I want to return my Kindle Paperwhite (ORD-002). Please initiate a refund.", "customer_id": "CUST-123", "session_id": "t2"}` returns a refund ID with `APPROVED` status and the 3 to 5 business days message, and the combined Test 1 plus Test 2 logs prove two distinct Gateway tools (one API target, one Lambda target) each returning well-formed responses.

- [ ] Build it: `/develop refund processing`

## Slice 3: Grounded answers

### 5. Product answers with RAG

Thicken the thread with grounded product and policy answers from the Knowledge Base, including the guard path when the base is unconfigured. Covers TODO 6.
**Done when:** code has `search_knowledge_base` with `@tool` plus a docstring stating when to call it, calls the Retrieve API against `KB_ID`, joins retrieved chunks into one formatted string, returns a descriptive message when `KB_ID` is unset, and Test 3 `{"prompt": "What are the benefits of the Platinum loyalty tier?", "customer_id": "CUST-123", "session_id": "t3"}` returns the Platinum facts (free same day shipping, 15 percent discount, priority support) drawn from retrieved chunks.

- [ ] Build it: `/develop product answers with RAG`

## Slice 4: Memory

### 6. Memory across sessions · needs a decision

Thicken the thread with recall across separate sessions for the same customer, using namespaced retrieval before each reply and event persistence after it. Covers TODO 4 (namespace helper) plus TODO 5 (`MemoryHook`).
**Done when:** code has `get_namespaces` fetching strategy types and templates from the memory resource (handles `namespaceTemplates` with fallback to legacy `namespaces`), `MemoryHook` extends `HookProvider` and wires via `register_hooks`, `retrieve_customer_context` queries all strategy namespaces, tags hits by strategy type, and prepends them to the user message, `save_support_interaction` extracts the last user query plus assistant response and calls `memory_client.create_event()`, and Test 4 passes with a 30s-plus gap: session A `{"prompt": "Hi, I am Jane. I prefer concise responses.", "customer_id": "CUST-123", "session_id": "s-A"}` then session B `{"prompt": "Do you remember my name and communication preference?", "customer_id": "CUST-123", "session_id": "s-B"}` recalls Jane plus concise style.

- [ ] Design it (spec): `/architect memory across sessions`

## Slice 5: Exact math

### 7. Exact discount math

Thicken the thread with precise loyalty math run in the code sandbox, with a safe fallback when the sandbox is unavailable. Covers TODO 7.
**Done when:** code has `calculate_loyalty_discount` with `@tool`, builds a self-contained Python string encoding points redemption plus tier discounts plus earn rates, executes via `code_session(REGION).invoke("executeCode", ...)` with `clearContext=True`, falls back to a tier-only discount when the interpreter is unavailable, returns `points_redeemed` plus `tier_discount_pct` plus `final_total` plus `remaining_points`, and Test 5 `{"prompt": "I am a Gold member with 4250 points. Calculate my discount on a $150 standard order.", "customer_id": "CUST-123", "session_id": "t5"}` returns points redeemed, tier discount 10 percent, a correct final total, and remaining points.

- [ ] Build it: `/develop exact discount math`

## Slice 6: Live web

### 8. Live web lookup

Thicken the thread with live page reads through the browser tool, so the agent can fetch current facts beyond its training and catalog.
**Done when:** code instantiates `AgentCoreBrowser` with `REGION` and adds it to the agent tool list, and Test 6 `{"prompt": "Go to https://www.udacity.com and tell me the page title.", "customer_id": "CUST-123", "session_id": "t6"}` returns the live page title from the fetched page.

- [ ] Build it: `/develop live web lookup`

## Slice 7: Submit

### 9. Submission close

Close the loop for grading: full evidence in both forms, the short reflection, resource cleanup, and a final pass over every rubric row.
**Done when:** (a) evidence: completed `main.py` with zero `pass`/`None` TODOs plus all six `agentcore invoke` runs saved as text logs plus screenshots (Test 4 keeps both s-A and s-B); (b) reflection: 200 to 400 words naming one specific tool/integration and why the choice was made, plus one concrete challenge and its fix, plus one production consideration with a concrete example for this agent; (c) cleanup in order: 1. `agentcore destroy`, 2. Bedrock console deletes Gateway plus Memory plus Knowledge Base, 3. OpenSearch Serverless collection delete plus S3 empty-and-delete (KB delete does NOT remove these — cost trap), 4. API Gateway delete plus both Lambdas delete, 5. optional IAM role cleanup; (d) every Submission Checklist row 1-9 plus every Rubric row (deploy, MCP, RAG, memory, code interpreter, browser, reflection) ticked.

- [ ] Build it: `/develop submission close`

## Traceability (capstone → scope)

| Capstone | Scope |
| --- | --- |
| TODO 1-3 (app/clients), TODO 8 (entrypoint), deploy | Feature 3 |
| TODO 4 (namespaces), TODO 5 (MemoryHook) | Feature 6 |
| TODO 6 (KB search) | Feature 5 |
| TODO 7 (discount calculator) | Feature 7 |
| Tests 1-6 | Features 3-8 in order |
| Submission Checklist 1-9, Cleanup 1-5, Rubric | Feature 9 |

## Deferred

Kept visible so nothing is missed. Optional after the pass path above is green.

1. **Structured output validation** · needs a decision
Typed checks on tool replies before they reach the user, so malformed data never renders as a final answer.
2. **Conversation summarization** · needs a decision
Shortening of older turns when history grows, so cost and context stay bounded on long chats.
3. **Personalize the agent scenario** · needs a decision
Same architecture pointed at a domain you care about, with your own catalog and tools.

## Legend

**The decision box.** Every feature carries exactly one box whose label ends with `(spec)`. Every other box is an execution box. Next step always equals the first unticked box.

**Feature lifecycle**: `planned` then `in-progress` then `done`, plus `existing` (predates this workflow) and `dropped` (out of scope, kept for history). Tag `needs a decision` means run `/architect` first. No tag means build straight with `/develop`. Atomic build tasks live in the spec, never here. Status shows in the table and beside the heading, nowhere else.
