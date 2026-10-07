# NovaMart Customer Support App

## What this project is

A customer-facing chat application for NovaMart that:

- Lets customers sign up and sign in with AWS Cognito.
- Streams an AI support agent's replies back into the chat.
- Keeps conversation history in DynamoDB.
- Validates every request with a JWT before forwarding it to the AgentCore Runtime.

## Architecture

```
Browser (React + Tailwind)
  └─ POST /api/sessions/messages   (bearer JWT + session id)
        │
        ▼
Gateway (Express + JOSE)
  ├─ Verifies Cognito JWT
  ├─ SigV4-signs InvokeAgentRuntime
  └─ Returns { sessionId, userMessage, assistantMessage }
        │
        ▼
AgentCore Runtime  (InvokeAgentRuntime ARN + runtimeSessionId)
        │
        ▼
DynamoDB  (history per user + session)
```

The gateway is the only thing that talks to AWS. The browser never
sees IAM credentials or raw DynamoDB access.

## Project layout

```
frontend/         Vite + React + TS + Tailwind v4
  src/auth/       Auth service abstraction + Cognito + demo impl
  src/api/        ChatApi (real gateway) + DemoChatApi (local fake)
  src/hooks/      useChatStore (all conversation state)
  src/components/ AuthScreen, ChatWindow, Composer, SessionList
  .env.example    Copy to .env.local and fill in

gateway/          Express server that validates + proxies
  src/auth.ts     Cognito JWT verification (JOSE)
  src/agentcore.ts InvokeAgentRuntime via AWS SDK v3
  src/history.ts  DynamoDB session/message persistence
  src/mockAgent.ts In-process fake agent for local dev
  .env.example    Copy to .env and fill in

.env.local / .env   NEVER committed. Contains secrets.
```

## Running locally (demo mode)

1. Copy the env files:
   ```powershell
   Copy-Item frontend/.env.example frontend/.env.local
   Copy-Item gateway/.env.example gateway/.env
   ```
2. Edit `frontend/.env.local`:
   ```
   VITE_DEMO_MODE=true
   VITE_GATEWAY_URL=http://localhost:3001
   ```
3. Edit `gateway/.env`:
   ```
   MOCK_MODE=true
   ```
   Demo mode works without AWS, but if you set `HISTORY_TABLE_NAME` the gateway
   will persist sessions to that table — useful for testing the real history
   path locally.
4. Start both packages:
   ```powershell
   npm run dev
   ```
   - Frontend on `http://localhost:5173`
   - Gateway on `http://localhost:3001`

## Connecting Cognito

### 1. Create the user pool (AWS Console)

1. **IAM → Identity providers → Create user pool.**
2. **Sign-in options**: email (this app signs in with email, not username).
3. **Password policy**: minimum 8 chars, allow users to change password.
4. **Account recovery**: email only.
5. **Create the pool.** Copy its **Pool ID** (`us-east-1_xxxxx`) and **Region**.

### 2. Create the app client

1. In the pool, open **App integration → App client**.
2. Create a client named `novamart-frontend`.
3. **App client secret: OFF** (SPAs cannot hold a secret).
4. **Authentication flows**: `ALLOW_USER_PASSWORD_AUTH`, `ALLOW_REFRESH_TOKEN_AUTH`.
5. **Token expiration**: leave defaults (ID token 60 min). The gateway refreshes tokens on expiry.
6. Copy the **Client ID**.

### 3. Configure the frontend

Copy `frontend/.env.example` to `frontend/.env.local` and fill in:

```
VITE_COGNITO_USER_POOL_ID=us-east-1_xxxxx
VITE_COGNITO_USER_POOL_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
VITE_AWS_REGION=us-east-1
VITE_GATEWAY_URL=
VITE_DEMO_MODE=false
```

### 4. Configure the gateway

Copy `gateway/.env.example` to `gateway/.env` and fill in:

```
AWS_REGION=us-east-1
COGNITO_USER_POOL_ID=us-east-1_xxxxx
COGNITO_USER_POOL_REGION=us-east-1
COGNITO_USER_POOL_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
AGENT_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/xxxxxxxx
HISTORY_TABLE_NAME=novamart-agentcore-agent-sessions
MOCK_MODE=false
```

The gateway must run with an IAM identity that has:
- `bedrock-agentcore:InvokeAgentRuntime` on the runtime ARN
- `dynamodb:GetItem`, `dynamodb:UpdateItem`, `dynamodb:DeleteItem`, `dynamodb:Scan` on the history table (if used)

The history table is single-keyed on `session_id`; each item holds the whole
conversation in a `messages` array, so loading a thread is one `GetItem` and
appending a message is one `UpdateItem`. No schema migration is needed.

### 5. Disable demo mode

Set `VITE_DEMO_MODE=false` in the frontend and `MOCK_MODE=false` in the gateway.

### 6. Restart and test

```powershell
npm run dev
```

Sign up a test user in the UI, then confirm the gateway logs show a verified
JWT (`unverified: false`) and a real `InvokeAgentRuntime` call.

## Production

- Serve the Vite build behind CloudFront or your CDN.
- Run the gateway on ECS/Fargate or an EC2 instance with an IAM role
  that has `bedrock-agentcore:InvokeAgentRuntime` and, if you propagate
  the user id, `bedrock-agentcore:InvokeAgentRuntimeForUser`.
- Set `VITE_GATEWAY_URL` to the gateway's production URL.

## Verified

- Frontend typechecks: `npm run typecheck --workspace frontend`
- Gateway typechecks: `npm run typecheck --workspace gateway`
- Unit tests: `npm run test --workspace frontend` and `npm run test --workspace gateway`
- Demo mode runs end-to-end without AWS credentials.

## Design notes

- **No bearer token in the browser for AgentCore calls.** The browser
  sends the Cognito JWT to the gateway; the gateway signs the
  `InvokeAgentRuntime` call with AWS SigV4. This keeps IAM credentials
  out of the client.
- **Session continuity.** The `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id`
  header carries the session id so the agent can maintain context.
- **Resumable sessions.** Every message is persisted to DynamoDB keyed by
  `USER#<sub>#SESSION#<id>` / `MESSAGE#<ts>#<id>`, so refresh or a new
  tab restores the full transcript.
- **Offline first.** Demo mode uses an in-memory + localStorage
  provider so the UI is fully testable without AWS.
