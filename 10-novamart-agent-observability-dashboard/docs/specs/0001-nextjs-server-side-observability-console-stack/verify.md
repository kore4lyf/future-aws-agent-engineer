# Verify: Stack & architecture · spec 0001 · updated 2026-09-29

_Steps derived from spec 0001 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual

- [x] `npm run dev`, open `http://localhost:3000` → shows masked account `****9477`, region `us-east-1`, log group `/aws/bedrock/agentcore/novamart-agentcore`, and a real latest log stream with a real timestamp → AC-1, AC-8
- [x] Read the account shown on screen, it is masked and never the full 12 digit id → AC-10
- [x] Refresh the browser twice, watch the last log event and the read time change between loads, a stale number never persists → AC-2
- [x] Set `LOG_GROUP=/aws/bedrock/does-not-exist` in `.env.local`, reload → the log group section shows a plain sentence naming the failure with the AWS code in parentheses, and the caller identity section still renders real data → AC-3
- [x] Run with no AWS session, reload → reads fail with the AWS error code and request id visible in the collapsed detail line, and the app does not crash → AC-3
- [x] Point `AWS_REGION` at a region the session cannot use, read the whole error sentence → no 12 digit account id appears anywhere on screen → AC-10
- [x] Delete `.env.local` and restart the dev server → both panels degrade to a panel error naming `AWS_REGION`, no global error screen → AC-3
- [ ] When a client component or chart is added later, the server to client boundary passes plain arrays only, no client object or `Date` crosses it → AC-2 (architecture note)

## Commands

- [x] `npx tsc --noEmit` → no errors, on a clean checkout with no `.next` directory present → AC-1
- [x] `npx eslint` → no findings → AC-1
- [x] `npx next build` → `/` and `/api/telemetry` both listed as dynamic (`ƒ`), never static → AC-2
- [x] `npm run build && npm start`, then `curl localhost:3000/api/telemetry` twice three seconds apart → two different `readAt` values on both `identity` and `logActivity` → AC-2
- [x] `Select-String -Path .next/static/**/* -Pattern "AWS_SECRET_ACCESS_KEY|client-cloudwatch-logs|CloudWatchLogsClient"` after a build → no matches → AC-1
- [x] Point `AWS_REGION` at a region the session cannot reach, `ap-southeast-1` → the log group panel shows a plain sentence with the AWS code in parentheses, the collapsed detail line carries the code and the request id, the account id appears nowhere on screen even though the raw AWS message names it in an ARN, and the caller identity panel still renders real data → AC-3, AC-10
- [x] Remove `.env.local` and restart the dev server → both panels show `MissingConfiguration` and a sentence naming `AWS_REGION`, no error boundary and no blank screen → AC-3
- [x] Stop the AWS session → both panels show the AWS error code, and the collapsed detail line carries the code and the request id → AC-3
- [x] Reload the page twice, three seconds apart → each panel's "Read at" line shows a different timestamp → AC-2

## Acceptance-criteria coverage

- AC-1 covered by the page render, the clean checkout typecheck, lint, and the client bundle grep
- AC-2 covered by the two read timestamps on both panels, the build output showing dynamic routes, and the refresh check
- AC-3 covered by the wrong region check, the missing `AWS_REGION` check, and the expired session check, each showing the code and the request id in the collapsed detail line
- AC-10 covered by the masked account row and by the wrong region check, where the raw AWS message names the account id in an ARN and the rendered sentence does not
- AC-4, AC-5, AC-6, AC-7, AC-9 not yet covered, they land with the panels, the theme tokens, and the test runner in later features

## Known build behaviour to re-check

- The Turbopack build cache in `.next` held the AWS credential values in plain text after a build that used a live session. `.next` is gitignored and was deleted after the check, but the cache holds secrets on a shared machine until it is removed. Re-checked 2026-09-30: confirmed again, the live access key and secret were both found in `.next/cache/turbopack/v16.3.7-4c20699e/00000001.sst`, and `.next` was deleted afterwards. The client bundle itself (`.next/static`, 22 files) held no AWS name and no credential variable name.

## Findings from the 2026-09-30 run, resolved

All five findings below were fixed and re verified. Each line says what changed.

- `npx tsc --noEmit` failed on a clean checkout with `Cannot find name 'LayoutProps'`. **Fixed.** `app/layout.tsx` now types its props as `{ children: ReactNode }` instead of the build generated `LayoutProps<"/">`, so the file typechecks with no `.next` directory present and no `next typegen` step. Verified with `.next` deleted: exit 0.
- The request id never reached the screen. **Fixed.** The error panels now render a collapsed `Technical detail` disclosure under the plain sentence, carrying the AWS code, the request id when AWS returned one, and the read time. Verified with an expired session: both panels showed `ExpiredToken` / `ExpiredTokenException` in the sentence and their request ids in the detail line.
- The per read `readAt` was dropped, so two page loads rendered byte identical text. **Fixed.** `ReadResult` already carried `readAt` on both branches; the page now prints a "Read at" line under each panel and the API returns the per read `readAt` rather than a single response level one. Verified: three seconds apart, `identity` gave `…876925` then `…883185`, `logActivity` gave `…876927` then `…883186`, in both dev and `next start`.
- The account id leaked to the screen inside AWS error messages. **Fixed.** New `lib/aws/redact.ts` replaces any 12 digit run with `[redacted account]`, applied to the message inside the shared `toReadFailure` mapper, so every read path is covered by construction. Verified with the region pointed at `ap-southeast-1`: the `AccessDeniedException` sentence still names the denied action, the log group, and the service control policy, and every one of the three ARNs now reads `::[redacted account]:`.
- A missing `AWS_REGION` was a hard crash. **Fixed.** Client construction moved behind a lazy `defaultDeps` factory that each read calls inside its own `try`, so `readConsoleConfig()` throwing is now caught like any other read failure and surfaces as `MissingConfiguration` with the message "Set AWS_REGION in .env.local before starting the console." Verified with no `.env.local` at all: both panels degraded, the page rendered fully, no error boundary.

## Still open

- The per read timeout is wired but has no runtime evidence. Every read carries `AbortSignal.timeout(8000)` and the abort branch maps to `ReadTimeout`, but no failure so far came close to 8 seconds, since a denied read resolves in under two. The wrong region step passes on "the panel degrades" and "the account id is redacted", not on the timeout firing. A slow or hung read is what exercises it, and that needs a network level fault injection, so this stays open until `/test` can simulate one.

