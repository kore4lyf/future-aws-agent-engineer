# Verify: Stack & architecture · spec 0001 · updated 2026-09-29

_Steps derived from spec 0001 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual

- [ ] `npm run dev`, open `http://localhost:3000` → shows masked account `****9477`, region `us-east-1`, log group `/aws/bedrock/agentcore/novamart-agentcore`, and a real latest log stream with a real timestamp → AC-1, AC-8
- [ ] Read the account shown on screen, it is masked and never the full 12 digit id → AC-10
- [ ] Refresh the browser twice, watch the last log event and the read time change between loads, a stale number never persists → AC-2
- [ ] Set `LOG_GROUP=/aws/bedrock/does-not-exist` in `.env.local`, reload → the log group section shows a plain sentence naming the failure with the AWS code in parentheses, and the caller identity section still renders real data → AC-3
- [ ] Run with no AWS session, reload → reads fail with the AWS error code and request id visible, and the app does not crash → AC-3
- [ ] When a client component or chart is added later, the server to client boundary passes plain arrays only, no client object or `Date` crosses it → AC-2 (architecture note)

## Commands

- [ ] `npx tsc --noEmit` → no errors → AC-1
- [ ] `npx eslint` → no findings → AC-1
- [ ] `npx next build` → `/` and `/api/telemetry` both listed as dynamic (`ƒ`), never static → AC-2
- [ ] `npm run build && npm start`, then `curl localhost:3000/api/telemetry` twice three seconds apart → two different `readAt` values → AC-2
- [ ] `Select-String -Path .next/static/**/* -Pattern "AWS_SECRET_ACCESS_KEY|client-cloudwatch-logs|CloudWatchLogsClient"` after a build → no matches → AC-1
- [ ] Point `AWS_REGION` at a region the session cannot reach → the read fails fast with a per read timeout, the page still renders → AC-3

## Acceptance-criteria coverage

- AC-1 covered by the page render, typecheck, lint, and the client bundle grep
- AC-2 covered by the two read timestamps, the build output showing dynamic routes, and the refresh check
- AC-3 covered by the bad log group check, the no session check, and the wrong region check
- AC-4, AC-5, AC-6, AC-7, AC-9 not yet covered, they land with the panels, the theme tokens, and the test runner in later features

## Known build behaviour to re-check

- The Turbopack build cache in `.next` held the AWS credential values in plain text after a build that used a live session. `.next` is gitignored and was deleted after the check, but the cache holds secrets on a shared machine until it is removed.
