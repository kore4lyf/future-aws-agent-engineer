# Scope: NovaMart Agent Operations Console

A read only web console that turns the NovaMart multi agent telemetry living in Amazon CloudWatch and AWS X Ray into a screen a non AWS reader can act on. It exists so support staff, managers, and engineers can answer is the agent healthy, is it fast enough, what is the guardrail blocking, and where did this request go, without opening a console. It observes the NovaMart agent, it never changes it.

**Build approach:** Tracer Bullet (one real read path proven end to end from AWS to screen, then thicken it segment by segment).
**Workflow:** Medium (check verify, then test). The audience includes people who cannot check the work themselves, so a failing panel must be caught, not eyeballed; no compliance surface, so a fresh model review is not warranted.

## At a glance

| # | Feature | Phase | Status |
|---|---------|-------|--------|
| 1 | Stack & architecture | Foundation | in-progress |
| 2 | Coding standards & tooling | Foundation | planned |
| 3 | Developer setup & API reference path | Foundation | planned |
| 4 | Telemetry data contract | Foundation | planned |
| 5 | Design system & console shell | Foundation | planned |
| 6 | Health overview read path | Skeleton | planned |
| 7 | Request volume & agent latency | Slice 2 | planned |
| 8 | Guardrail activity | Slice 3 | planned |
| 9 | Errors & failed requests | Slice 4 | planned |
| 10 | Request traces & service map | Slice 5 | planned |
| 11 | Time range control & refresh | Slice 6 | planned |

## Foundations

### 1. Stack & architecture · in-progress
Decide the stack and scaffold a runnable app so every later slice reads real AWS data, never a fixture. Server side only access to CloudWatch and X Ray, so no AWS credential can reach the browser.
**Done when:** the stack is recorded in a spec, the app boots, and a server route reaches AWS and returns one real value with no browser credential path.
- [x] Decide the stack (spec): `/architect stack & architecture`
- [x] Scaffold from the decision: `/develop stack & architecture`
- [ ] Verify it: `/check verify stack & architecture`
- [ ] Test it: `/test stack & architecture`
Spec [0001](../specs/0001-nextjs-server-side-observability-console-stack/index.md) · code in `app/`, `lib/`

### 2. Coding standards & tooling
Capture conventions and install lint, format, and type strictness from the real scaffolded project.
**Done when:** root `AGENTS.md` reflects the real stack, and lint, format, and typecheck run clean.
- [ ] Capture conventions + tooling choices: `/audit`
- [ ] Install the tooling: `/develop tooling`
- [ ] Check it runs clean: `/test`

### 3. Developer setup & API reference path
Get the developer to a fast loop and to current documentation before any panel is built. The scaffold installs shadcn, so components arrive as source in the project rather than as a dependency, and a single shared AWS client with typed responses means panels are data wiring rather than repeated credential and retry code. A short written reference records where the AWS API documentation lives and which of the service specific reading is load bearing, so nobody reverse engineers an API from guesswork or stale memory.
**Done when:** a new developer runs one command to start the app with fast refresh, a new component is added through the shadcn CLI into the project rather than hand built, every AWS read goes through the shared typed client, and the reference names the current SDK packages plus the CloudWatch Logs, metric, and query documentation and the X Ray segment documentation.
- [ ] Design it (spec): `/architect developer setup & API reference path`

### 4. Telemetry data contract
Define, in one place, what each panel reads and what it shows: the log group, the log line shapes parsed, the X Ray queries, the agent and knowledge base names, and the health states. This is the shared vocabulary every slice renders from, and it records what is verified against live AWS versus assumed.
**Done when:** every planned panel names its data source and shape, agent and knowledge base names match NovaMart exactly, and each binding is marked verified or pending.
- [ ] Design it (spec): `/architect telemetry data contract`

### 5. Design system & console shell
One visual language for a dense operations screen, built by configuring shadcn rather than styling from scratch. Theme tokens carry the health colour semantics, and the shadcn card, badge, table, tabs, and chart components become the operations primitives, so an operations page is assembled rather than drawn. The shell adds navigation and a time range slot around them. Every page inherits it, so this comes before any panel.
**Done when:** health and severity colours are defined as theme tokens and not as one off values, the console is assembled from shadcn components with no bespoke rebuild of a stock component, the chart component renders a time series in both themes, and the shell renders with navigation and no data.
- [ ] Design it (spec): `/architect design system & console shell`

## Skeleton

### 6. Health overview read path
The walking skeleton, and the thinnest real thread through the whole stack. One server route reads real AWS telemetry, the overview page renders a health verdict and a few real numbers, and the first screenshot is possible. Proves the whole pipe before any breadth.
**Done when:** the overview page shows live health and real request numbers from AWS, it loads with no browser credential, and an empty window renders an honest empty state rather than zeros.
- [ ] Design it (spec): `/architect health overview read path`
- [ ] Build it: `/develop health overview read path`
   - [ ] Server route reads AWS through the shared client
   - [ ] Overview page renders health verdict and real numbers
   - [ ] Loading, empty, and error states render
- [ ] Verify it: `/check verify health overview read path`
- [ ] Test it: `/test health overview read path`

## Slice 2

### 7. Request volume & agent latency
Thicken the read path into the RED style question: how much traffic, how fast, and is any one worker slow. Per agent invocation counts and latency distribution for the orchestrator and the four workers, and throughput over the selected window.
**Done when:** the page shows invocation count over time and average and high percentile latency per agent, each worker is comparable on one scale, and a time with no traffic renders as a gap rather than a drop to zero.
- [ ] Design it (spec): `/architect request volume & agent latency`

## Slice 3

### 8. Guardrail activity
Answer what the safety layer is doing, without inventing numbers. Block and intervention counts where AWS genuinely exposes them, the policies and topics in force, and a visible statement of what the data can and cannot say. A guardrail block happens inside Bedrock, so this slice must prove from real data what a block looks like before it renders a count.
**Done when:** the page states the guardrail configuration and topics in force, shows intervention counts only where a real signal was verified, and labels any unverified count as unavailable instead of showing zero.
- [ ] Design it (spec): `/architect guardrail activity`

## Slice 4

### 9. Errors & failed requests
Answer what is broken. Error rate against traffic, errors grouped by type, and the most recent failures with enough context to act. Keeps health honest, since a green latency panel means nothing if the system is failing quietly.
**Done when:** the page shows error rate over time beside traffic, breaks errors down by type, lists recent failures with trace and session links, and distinguishes a genuine zero from no data.
- [ ] Design it (spec): `/architect errors & failed requests`

## Slice 5

### 10. Request traces & service map
Answer where did this request go, which is the question a trace exists to settle. A readable request timeline from orchestrator through the workers and the parallel knowledge base retrieval, plus the service map, so a non AWS reader sees the system shape and can drill into one slow or failed request.
**Done when:** a trace list leads to one readable timeline with the orchestrator, its workers, and the knowledge base calls, the service map renders the node graph, and a missing or partial trace explains itself instead of rendering empty.
- [ ] Design it (spec): `/architect request traces & service map`

## Slice 6

### 11. Time range control & refresh
Make the console usable rather than a static screenshot: one time range control that every page honours, manual refresh, and last updated status, so a reader can compare windows and knows how fresh the numbers are.
**Done when:** the range control applies to every page, refresh re reads AWS, the last updated time is always visible, and a range with no data says so rather than implying health.
- [ ] Design it (spec): `/architect time range control & refresh`

## Deferred
Out of scope for the current build pass, kept so the plan stays honest.
- **Alerting and notifications**: alarms, email, and paging · needs a decision
- **Write actions**: fixing, retrying, or acknowledging from the console · needs a decision
- **Multi system views**: one console spanning more than the NovaMart agent · needs a decision
- **Account wide cost and usage**: budgets, forecasts, and billing views · needs a decision
- **Historical comparison and reporting**: week over week, exports, and scheduled reports · needs a decision

## Legend

**The decision box.** Every feature carries exactly one, the sub-task whose label ends with `(spec)`. Its wording varies (`Design it (spec)` normally, `Decide the stack (spec)` on Stack & architecture), so skills locate it by that `(spec)` suffix, never by an exact label. Every other box is an execution box and `/architect` never ticks one.

**Feature lifecycle**: the scope updates as a feature moves; each row is what it shows and who sets it:

| State | Set by | The feature shows |
|---|---|---|
| `planned` · needs a decision | `/scope` | one box: `Design it (spec): /architect <feature>` |
| `in-progress` (designed) | `/architect` at spec capture | `Design it` ticked; spec linked; `Build it: /develop <feature>` + 2 to 5 milestones; the tier's closing boxes (`Verify it` Lean+, `Test it` Medium+, `Review it` + `Document it` Full); any surfaced follow-up enrolled |
| `in-progress` (building) | `/develop` | milestone sub-boxes tick one by one; code pointer filled |
| `in-progress` (verified) | `/check verify` | `Build it` + milestones ticked; `Verify it` ticked |
| `done` | the tier's last required stage (`Vibe` → `/develop`; `Lean` → `/check verify`; `Medium`/`Full` → `/test`), then `/sync` | required boxes ticked; `Review it`/`Document it` (Full) ticked by `/check review`/`/document`, tracked but not part of the `done` gate (Design/Build/Verify/Test); `/sync` captures conventions |

- **Next step** = the first unticked box (always a command or a tracked milestone).
- **needs a decision** = run `/architect` first; otherwise straight to `/develop` (or `/audit` for standards & tooling). The tag drops once the spec is captured.
- **Atomic build tasks live in the spec's `## Build plan`, not here**: the scope carries only the milestone rollup.
- **Status** `planned` → `in-progress` → `done`, plus `existing` (pre-workflow) and `dropped` (de-scoped, kept for history).
- **Approach tag** beside a heading (e.g. `· Facade`) overrides the project default for this feature; no tag = inherits it.
- **Workflow tier tag** beside a heading (e.g. `· Full`, `· Vibe`) overrides the project default `**Workflow:**` tier for that one feature; no tag = inherit. It is the single rigor dial (there is no separate "weight").
- **Workflow** (header line) is the project default tier, the stages each feature runs **after** `/develop`: **Vibe** = nothing after `/develop` (rely on its build time self check); **Lean** = `/check verify`; **Medium** = `/check verify` then `/test`; **Full** = `/check verify`, `/test`, a fresh model `/check review`, then `/document` (and most features need a spec). The tier also sets what closes a feature to `done`, the last required stage marks it: **Vibe** → `/develop` (build + self check); **Lean** → `/check verify` on PASS; **Medium**/**Full** → `/test` (with verify passed). At every tier an `Assumed` spec still blocks `done` until `/architect` ratifies it, and `/architect` still gates any feature that needs a decision (tier does not turn the gate off). A feature's own tier tag overrides this default. `/develop` reads the effective tier to scale the next steps it recommends.
- **Pointer line** (`spec <n> · code in <path>`): the spec link added by `/architect`, the code path by `/develop`.
