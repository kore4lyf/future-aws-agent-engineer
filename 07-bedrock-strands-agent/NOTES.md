# Console Walkthrough — WanderBot (AWS Console Only)

## 1. Lambda
- **Lambda → Create function → Author from scratch**
  - Name `wanderbot-booking-tools` → Runtime **Python 3.10** → Create new role → Create → paste `lambda/booking_lambda.py` → **Deploy** → Test `{"booking_ref":"BK-1001"}`
  - Name `wanderbot-loyalty-points` → Runtime **Python 3.12** → Create → paste `lambda/loyalty_points_api.py` → **Deploy**

## 2. API Gateway (REST)
- **API Gateway → Create API → REST API → Build** → Name `wanderbot-loyalty-api` → Create
- **Resources → Create Resource** → Path `/` + Name `loyalty` → Create
- Select `/loyalty` → **Create Resource** → Path `{member_id}` → Create
- Select `/{member_id}` → **Create Method** → **GET** → Integration **Lambda function** (proxy **ON**) → Lambda `wanderbot-loyalty-points` → **Grant permission** → **API key required: ON** → Create (if URI error, paste full ARN)
- **Deploy API** → New Stage `prod` → Deploy → copy Invoke URL `https://s6ku1j6mpj.execute-api.us-east-1.amazonaws.com/prod`
- **API Keys → Create** → `wanderbot-loyalty-key` → Copy `LdHNb...`
- **Usage Plans → Create** → `wanderbot-loyalty-plan` (Rate 10000/Burst 5000) → Add API Stage `wanderbot-loyalty-api/prod` → Add API Key `wanderbot-loyalty-key`

## 3. Identity
- **Bedrock → AgentCore → Identity → Add Outbound Auth** → Type **API Key** → Variant **API key only** → Name `wanderbot-loyalty-api-key` → Paste `LdHNb...` → Create

## 4. Gateway
- **Bedrock → AgentCore → Gateways → Create Gateway** → Name `wanderbot-gateway` → No Auth → New service role → Create → copy URL `https://wanderbot-gateway-foziumjcew.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp`
- **Targets → Add**
  - `wanderbot-booking-target` → Type **Lambda ARN** → ARN `arn:aws:lambda:us-east-1:789095801094:function:wanderbot-booking-tools` + inline `schema/booking_lambda.json` → No auth → Add
  - `wanderbot-loyalty-target` → Type **API Gateway** → Select `wanderbot-loyalty-api` / `prod` / `GET /loyalty/{member_id}` → Name override `get_loyalty_points` → Outbound Auth **API key** → Select `wanderbot-loyalty-api-key` → Header `x-api-key` → Add

## 5. Runtime (Test)
- **Bedrock → AgentCore → Runtime → `wanderbot_Agent-Dp1oks5MVy` → Test** → Payload `{"message":"What are the loyalty points for member hz-001?"}` → Invoke → expect `45200` (hz-001)
- Logs: **CloudWatch → Log groups → `/aws/bedrock-agentcore/runtimes/wanderbot_Agent-Dp1oks5MVy-DEFAULT`**
