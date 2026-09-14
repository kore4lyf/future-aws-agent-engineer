# Reviewer Note — AI Support Agent (08-ai-support-agent)

Hi reviewer, thanks for reviewing. Everything is in this GitHub repo so you do not need a zip. Here is where to find each checklist item.

**Repo:** https://github.com/kore4lyf/future-aws-agent-engineer  
**Branch:** master  
**Agent folder:** `08-ai-support-agent/`

## Checklist mapping

1. **Completed main.py** — `08-ai-support-agent/main.py` (303 lines, all 8 TODOs implemented, no `pass` or `None` left). Run `grep -n "TODO" main.py` to see none remain. Also includes `lambda/`, `product_catalog.txt`, `pyproject.toml`.

2. **Test 1 — Order Tracking** — `08-ai-support-agent/proof/test1-order.png`  
   Prompt: `Can you track order ORD-001?` with `CUST-123` / `t1`. Shows `TRK987654321`, UPS, Sept 16, via `order-tracker___get_order`.

3. **Test 2 — Refund Processing** — `08-ai-support-agent/proof/test2-refund.png`  
   Prompt: `I want to return my Kindle Paperwhite (ORD-002). Please initiate a refund.`  
   Shows refund ID, `APPROVED`, 3 to 5 business days via `refund-processor___initiate_refund`.

4. **Test 3 — Knowledge Base (RAG)** — `08-ai-support-agent/proof/test3-platinum.png`  
   Prompt: `What are the benefits of the Platinum loyalty tier?`  
   Shows free same-day shipping, 15 percent discount, priority support from `CZGKR1BS45`.

5. **Test 4 — Long-Term Memory (both sessions)** — `proof/test4a-jane-intro.png` and `proof/test4b-jane-recall.png`  
   s-A: `Hi, I am Jane. I prefer concise responses.` with `CUST-123` / `s-A`  
   Wait 35 seconds, then s-B: `Do you remember my name and communication preference?` with same `CUST-123` / `s-B` recalls Jane and concise. Memory: `CustomerSupportMemory-dg71VY2DLx` with `cs_agent/{actorId}/facts` and `cs_agent/{actorId}/preferences`.

6. **Test 5 — Loyalty Discount Calculation** — `08-ai-support-agent/proof/test5-discount.png`  
   Prompt: `I am a Gold member with 4250 points. Calculate my discount on a $150 standard order.`  
   Shows `points_redeemed 4000`, `tier_discount_pct 10`, `final_total 99`, `remaining_points 349` via Code Interpreter sandbox.

7. **Test 6 — Browser Tool** — `08-ai-support-agent/proof/test6-browser.png`  
   Prompt: `Go to https://www.udacity.com and tell me the page title.`  
   Shows `Learn the Latest Tech Skills; Advance Your Career | Udacity` via `AgentCoreBrowser`. Session `6767408d-182c-4cd6-bd1b-ec1bc73bb21e` on `customer_support_agent-bTwdev6Upa`.

8. **Written reflection** — `08-ai-support-agent/reflection.md` (312 words, human voice, no em dashes). Covers Gateway MCP choice, AccessDenied fixes for KB/Memory/Browser, and production cost and auth notes.

9. **Other assets** — `08-ai-support-agent/lambda/` (both Lambdas), `product_catalog.txt`, `docs/scope/scope.md`, `pyproject.toml`, `uv.lock`.

## Deployment (if you want to re-run)

- Runtime ARN: `arn:aws:bedrock-agentcore:us-east-1:789095801094:runtime/customer_support_agent-bTwdev6Upa`
- Gateway: `CustomerSupportGateway` with `https://customersupportgateway-1rvyrs9sm7.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp`
- KB: `CZGKR1BS45`, Memory: `CustomerSupportMemory-dg71VY2DLx`, Region `us-east-1`, Model `global.amazon.nova-2-lite-v1:0`

To re-run locally: `cd 08-ai-support-agent && uv sync && agentcore invoke '{"prompt": "Hello", "customer_id": "CUST-123", "session_id": "s1"}'`

Thanks again. If anything is missing, open an issue or check `08-ai-support-agent/docs/scope/scope.md` for the full slice checklist.
