# 0001. Next.js server side observability console stack

**Date**: 2026-09-29
**Status**: In Progress

## Summary

This spec decides the stack and the core read contract for the NovaMart Agent Operations Console, a read only web app that turns the NovaMart agent's CloudWatch and X Ray telemetry into screens a non AWS reader can use. We build one Next.js app with TypeScript, shadcn for components, Lucide for icons, and Recharts for charts, and every AWS call happens on the server so no credential can reach the browser. Pages read live on each request with caching explicitly turned off, because a monitoring screen that serves a stale number is worse than a slow one. The app runs locally, is screenshotted while the AWS resources still exist, then the resources are torn down.

Reasoning, options, and the cross check record: see [`rationale.md`](rationale.md).

## Requirements

**Design constraints the stack must honour** (these shape the decision; they are not a build task list):

- **AC-1**: The app boots and renders with no AWS credential present in any client side bundle, and a server route returns one real value read from AWS.
- **AC-2**: Every telemetry page read reaches AWS on each request, with no route or segment caching, so a browser refresh issues a new AWS read. Routes that read telemetry are declared dynamic explicitly, and a test asserts that two successive reads produce two distinct AWS call timestamps.
- **AC-3**: A failed, denied, or timed out read renders an error state inside the affected panel only, while every other panel on the same page still renders real data. The panel error shows a plain sentence naming what failed, with the raw AWS error code and request id available in a collapsed detail line for an engineer.
- **AC-4**: No health or severity state is conveyed by colour alone, and never by an icon alone. Every state carries a visible text label; icons and colour supplement that label. A failed read renders in the `unknown` state, never in a healthy colour.
- **AC-5**: A series with no data in the selected range renders as an explicit gap, and the panel distinguishes three separate empty conditions: no activity in range (the agent was idle), no telemetry found (misconfigured or outside retention), and read failed. A genuine measured value of zero renders as zero and is labelled as such, because a healthy idle agent must not look identical to a broken one.
- **AC-6**: One documented command runs the whole suite, and it requires a valid AWS session because the end to end layer renders live data. The unit layer covers the data layer and health evaluation only, and the rendered behaviour of panels is covered by the end to end layer, because async server components cannot be rendered by the unit test runner.
- **AC-7**: Health colours and the chart series palette are defined as theme tokens rather than as literals inside page code, defined in both light and dark themes, and the busiest chart in the console stays within the available series tokens.
- **AC-8**: The console displays the AWS account it is reading and the AWS region, in the footer, and both come from the resolved caller identity rather than from configuration alone.
- **AC-9**: Any list that can be truncated by an AWS pagination cap says so explicitly, showing the count actually displayed alongside the total available, so a truncated list is never mistaken for a complete one.
- **AC-10**: No string rendered on screen contains the AWS account id, so screenshots taken for the portfolio cannot leak it.

## Decision

**Chosen option**: Next.js App Router, server components read AWS, client components render charts.

One Next.js App Router application in TypeScript, reading CloudWatch and X Ray only from server components and server only modules, rendering charts through shadcn's Recharts based chart component, using Lucide as the icon set, verified with Vitest and Playwright, run locally for screenshots.

**Implementation skills**: `shadcn` (`shadcn-ui/ui`, `.agents/skills/shadcn/`) · `aws-observability` (`aws/agent-toolkit-for-aws`, `.agents/skills/aws-observability/`) · `nextjs-app-router-patterns` (`wshobson/agents`, `.agents/skills/nextjs-app-router-patterns/`)

## Proposed stack

| Layer | Choice | Reason |
|---|---|---|
| Language | TypeScript, strict | One language across the server reads, the pages, and the tests, and AWS response shapes are checked at compile time. |
| Framework | Next.js 16, App Router, Turbopack | Server components read AWS directly, so no credential can reach the browser, and Turbopack is the default bundler with fast refresh. |
| Node runtime | Node.js 20.9 or newer | The floor Next.js 16 requires, and it satisfies the AWS SDK client engines requirement. |
| UI components | shadcn/ui on Tailwind CSS v4, neutral base colour | Components are copied into the repo as source, so an operations card or badge can be adapted, and the chart wrapper handles theme aware colours. |
| Icons | Lucide | shadcn's default icon set, so added components already use it and the CLI can migrate away from it if that ever changes. |
| Charting | Recharts 3 through the shadcn chart component | Required by the shadcn chart component, and it declares React 19 in its peer range. |
| Styling | Tailwind CSS v4 with tokens in `app/globals.css` | Health and series colours are theme tokens defined once and consumed by class name, not literals in page code. |
| Data access | Plain typed async functions wrapping the AWS SDK for JavaScript v3 | No query layer to learn, and the plain object shapes are obvious to a reviewer reading the code. |
| AWS clients | `@aws-sdk/client-cloudwatch-logs`, `@aws-sdk/client-xray` | The two services this console actually reads. The X Ray package is `client-xray`, one word, which is easy to get wrong. The metrics client is not installed, see the note below. |
| Server only guard | The `server-only` package, plus the AWS clients listed in `serverExternalPackages` | Without both, a client ward import can pull the SDK's browser build into the bundle and undo the credential boundary. |
| Caching | None, with dynamicness declared explicitly | A monitoring screen must not serve a stale number, and SDK reads bypass the data cache, so each telemetry route declares itself dynamic. |
| Database | None | The console owns no data; every value it shows comes from an AWS read at request time. |
| Auth | None for the app itself, and server only for AWS | The console is not published, and AWS access rides the existing session through the SDK's provider chain. |
| Testing | Vitest with React Testing Library, plus Playwright | Vitest covers the data layer and health evaluation with injected clients, and Playwright covers the rendered pages against live data, which sidesteps the async server component limitation. |
| Hosting | Local, `next dev` and `next build` then `next start` | Matches a project that is screenshotted and then torn down, and adds no ongoing hosting cost. The dev server binds a reachable interface by default, so it stays unpublished and unused during the screenshot phase. |
| Observability | The console's own behaviour is out of scope | The console observes NovaMart; instrumenting the console is a later decision, not part of the foundation. |

### The telemetry read contract

This is the single vocabulary every panel renders from. The values below are confirmed from the NovaMart source. The telemetry data contract feature verifies them against live AWS and records which are confirmed, and a binding that cannot be confirmed becomes a panel that says so rather than a panel that guesses.

| Value | Confirmed value | Where it comes from |
|---|---|---|
| Region | `us-east-1` | NovaMart's deployed region. |
| Log group | `/aws/bedrock/agentcore/novamart-agentcore` | The NovaMart foundation stack's CloudFormation export. |
| Log stream prefix | `local/` for local runs, `agentcore-runtime/` for the deployed runtime | The stream name is `<mode>/<host>/<date>/<id>`. |
| X Ray service name | `NovaMart-Orchestrator` | The service name constant in the agent's tracing module. |
| Tool call line | `tool call  <tool_name> <args>` | One per tool invocation. |
| Tool completion line | `tool done  <tool_name> (<seconds>s)` | Carries the duration. |
| Trace line | `trace <id> started \| session=<id> customer=<id>` | One per request. |
| Worker agent names | `route_to_inventory_agent`, `route_to_policy_agent`, `route_to_refund_agent`, `route_to_communication_agent` | The routing tool names, which are the per agent identifiers in the log text. |
| Knowledge base subsegment names | `KnowledgeBase:returns`, `KnowledgeBase:shipping`, `KnowledgeBase:warranty` | Emitted by the agent's knowledge base retrieval helper, and present in published traces. |
| Trace sampling rate | 1.0, set by the NovaMart observability configuration | Read from the deployed runtime's configuration rather than assumed. |

**On the CloudWatch metrics client.** The first draft of this spec listed `@aws-sdk/client-cloudwatch` for metric reads. Cross checking showed the agent publishes no custom CloudWatch metrics, so every number in this console derives from log text or from trace subsegments, and that client would have had no defined use. It is therefore not installed. Reinstating it is a deliberate later decision, and the correct first route if it ever is needed is Embedded Metric Format in the agent's own logging, not scraping derived numbers back out of log text.

### The nine panels

AC-3, AC-5, and the empty environment behaviour all depend on this list, so it is enumerated here rather than implied. Each panel reads only the sources named.

| # | Panel | Shows | Source |
|---|---|---|---|
| 1 | Health verdict | One overall state, `ok`, `warn`, `critical`, or `unknown` | Derived by `evaluateHealth` from panels 2, 3, and 9 |
| 2 | Request volume | Request count over the selected range | Count of `trace ... started` lines, bucketed |
| 3 | Agent latency | Per agent average and high percentile duration | Parse of `tool done` lines, grouped by tool name |
| 4 | Routing split | Share of requests handled by each worker | Count of `route_to_*` tool call lines |
| 5 | Knowledge base activity | Retrieval count and timing per knowledge base | `KnowledgeBase:*` subsegments in X Ray traces |
| 6 | Error rate | Failed tool calls against total calls | Tool calls without a matching `tool done` line |
| 7 | Recent failures | The most recent failed requests with context | Log lines around a failure, plus the trace id |
| 8 | Guardrail | Configuration and topics in force, and intervention counts only where a real signal is confirmed | Guardrail configuration; trace error flags if confirmed |
| 9 | Request traces | A browsable list of traces leading to one readable timeline | `GetTraceSummaries`, then `GetTrace` |

The trace list is browsed rather than reached by pasting a trace id, because a reader who does not know AWS cannot know a trace id to paste.

### Health states and thresholds

`evaluateHealth` is a single pure function over a set of samples and is the only subject of unit tests for health logic. It returns one of four states.

| State | Condition | Meaning to the reader |
|---|---|---|
| `unknown` | Any required input is missing, or a read failed | The console cannot tell you, and it says which input is missing |
| `ok` | Error rate at or below 1 percent, p95 agent duration at or below 15 seconds, at least one request in range | Working normally |
| `warn` | Error rate at or above 1 percent, or p95 agent duration above 15 seconds, or no request in range | Needs attention |
| `critical` | Error rate at or above 10 percent, or p95 agent duration above 60 seconds | Needs attention now |

Thresholds are deliberately generous, because the agent's own tool calls include three parallel knowledge base retrievals and a multi step refund decision, so a few seconds per agent is normal and a sub second threshold would report a healthy agent as unhealthy. The thresholds live in one module and are the first thing to adjust once real traffic exists.

### Time range

The selection lives in the URL, because a client component cannot drive a server read, and a shareable link that shows the same range as the screenshot is worth more than a dropdown that resets. `searchParams.range` is read on the server, with a default of `1h`.

| Range | Bucket size | Notes |
|---|---|---|
| `1h` | 1 minute | The default, and what most screenshots will show |
| `6h` | 5 minutes | |
| `24h` | 15 minutes | |
| `7d` | 1 hour | Approaches the usual CloudWatch retention on older data |

A missing bucket is plotted as a gap rather than interpolated, so `connectNulls` stays false and a reader can see where telemetry stopped rather than a straight line bridging a hole.

### Configuration

All configuration is server only. Nothing here is prefixed with `NEXT_PUBLIC_`, so none of it can reach the browser. A committed `.env.example` lists every name with an empty value.

| Variable | Purpose |
|---|---|
| `AWS_REGION` | Region for every client, declared explicitly since the SDK does not infer it |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | The existing session, read only by the default credential factory |
| `LOG_GROUP` | The agent log group, defaulting to the confirmed value |
| `XRAY_SERVICE` | The X Ray service name, defaulting to the confirmed value |

Configuration is read inside one config module, not scattered across constructors. That module is the only place AWS configuration is read, so changing where credentials come from later is a change to that module rather than a refactor across the data layer.

### Architecture notes that constrain the build

- **Dynamicness is explicit.** Every telemetry route declares itself dynamic, because an SDK call is not a `fetch` and build time prerendering is not gated on one. This is the single most consequential line in the spec.
- **Server only boundary.** The data layer is marked with `import 'server-only'`, and the AWS clients are listed in `serverExternalPackages` so the SDK's browser build can never enter the graph.
- **Server and client boundary.** Page files stay async server components that read AWS and pass plain serialisable arrays as props. Chart and interactive components are the only client components. No AWS client object, class instance, or `Date` crosses that boundary.
- **Client construction and mockability.** Every data function takes a `deps` argument defaulting to the real client factory, so tests inject fakes and the environment is read only inside the default factory. This is what makes the data layer unit testable without a live session.
- **Per read timeout.** Every read carries an `AbortSignal` timeout, because the default provider chain can block on a credential refresh or a hung metadata probe and produce a hung page rather than a failed panel.
- **Identity resolution.** The console calls `GetCallerIdentity` once and displays the account and region in the footer, so a wrong account cannot go unnoticed. Account identifiers are masked in any text that can reach a screenshot.
- **Read result shape.** Every data function returns a discriminated union, either success with data or failure with a code and message, so per panel error handling is a type level concern rather than a try and catch in each component.
- **No `use cache` on telemetry.** Data functions must not sit inside a `use cache` boundary. If a later slice wants caching, it is a deliberate change to this spec.
- **Chart colour.** The shadcn chart tokens are the source of series colour, defined per theme, so adding an agent is a token change rather than a chart code change.
- **Loading states.** A route level `loading.tsx` with per panel skeletons, because nine uncached reads otherwise produce a long blank wait on the screen that exists to communicate health.
- **No AWS credentials in any client bundle.** Enforced by the `server-only` guard, and verified by a test that greps the client build output for the credential variable names.
- **Scaffold details that change the output.** App directory at `app/`, the `@/*` import alias, the shadcn `new-york` style with the `neutral` base colour, and the development server port left at its default.

## Consequences

**Positive**:
- No AWS credential can reach the browser, and the `server-only` guard makes that a build time error rather than a review finding.
- One app and one language, so a reviewer can read the whole thing in one sitting and there is no second deployable to clean up.
- Live data with no cache and explicit dynamicness, so what a screenshot shows was true at the moment it was taken.
- Per panel error isolation with per read timeouts, so a throttled, denied, or hung read degrades a panel rather than the page.
- The caller identity is displayed, so reading the wrong account is visible rather than silent.
- Panels are data wiring rather than chart construction, since the primitives, the chart wrapper, and the icon set all already exist.

**Negative / tradeoffs**:
- The console cannot run once the AWS resources are torn down, so every screenshot must be captured first and there is no way to demo it later without rebuilding the resources.
- The end to end layer needs a valid AWS session, so the single test command is not runnable by anyone without one, and the suite cannot be a gate in an automated pipeline.
- Credential freshness is an operational concern: an expired session makes every panel fail, and the fix is outside the app.
- The read only guarantee cannot be demonstrated from the repository, because it comes from the session rather than from a policy in the code.
- Charts force a client and server boundary, and that boundary is a place mistakes happen, such as passing a non serialisable value from a server component to a client one.
- Async server components cannot be rendered by the unit test runner, so the data logic must live outside the component tree to remain unit testable, and panel behaviour is covered only by the end to end layer.
- Recharts and Lucide are adopted because the component library wraps and emits them, so neither can be swapped independently later without a migration.
- The chart series palette has a fixed token count, so a chart needing more series than tokens must either reuse tokens or gain more.
- Nine uncached reads make a slow first render, mitigated by skeletons but not removed.
- Health thresholds are guesses until real traffic exists, so the first reader to use this in anger will need to adjust them.

**Neutral**:
- No database and no auth means there is nothing to migrate and no session to manage.
- The project ships with a `.env.local` that must be gitignored, and an empty one produces nine failing panels plus an app level banner, not an empty screen.
- Local run only, so the app is untested under a production host and no infrastructure as code is needed.
- The agent's own observability defects, the missing worker subsegments and the stale runtime build, are recorded but not fixed, so the trace panel shows a flatter graph than the architecture implies.

## Follow-up

- [ ] All screenshots must be captured before the NovaMart resources are deleted, and the teardown must be the last step. This is a sequencing constraint on the whole scope, not only on this spec.
- [ ] Record the AWS read permissions the console actually needs, verified against real calls, so the read only claim becomes checkable. A dedicated read only role can then replace the borrowed session when the project is reused beyond a capstone.
- [ ] `/audit` must create the root `AGENTS.md` and record the three installed skills, since none of them are referenced by any context file yet. The shadcn and Next.js conventions are project wide, so they belong at root. The AWS observability conventions affect only the data layer, so they belong in a nested file for that area.
- [ ] The telemetry data contract feature must confirm the read contract in this spec against live AWS, especially the log line shapes, the knowledge base subsegment names, and the trace sampling rate, and must record which bindings are confirmed. A binding that cannot be confirmed becomes a panel that says so.
- [ ] The guardrail panel has two settled fallbacks. If no guardrail signal is derivable from the traces, the panel shows the configured policies and topics in force and states that per block counts are not available from this data, rather than showing a count of zero. If a signal is derivable, the panel shows the count and names the signal.
- [ ] Reconsider Embedded Metric Format in the agent as a follow on, which would give real CloudWatch metrics for per agent latency and error rate and would remove the log text parsing this console depends on. It requires changing the agent, which is out of scope here.
- [ ] Decide whether the console needs any instrumentation of its own. It currently reports NovaMart's health and says nothing about its own, which is acceptable for a local capstone.
- [ ] The two NovaMart defects recorded in Context in `rationale.md`, the missing worker subsegments and the stale runtime build, should be raised as separate work in the NovaMart project. Neither is this console's to fix, and both limit what the trace panel can honestly show.
