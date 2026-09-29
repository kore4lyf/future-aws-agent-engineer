# Rationale: 0001 Next.js server side observability console stack

**Spec**: [`index.md`](index.md)
**Date**: 2026-09-29

The decision record for spec 0001: the problem space, the options weighed, the reasoning, and the cross check record. The build spec lives in the linked file, which is what `/develop` reads.

## Context

The NovaMart agent emits seven kinds of log line to CloudWatch and publishes one X Ray trace per customer request, with remote subsegments for its knowledge base calls. It publishes no custom CloudWatch metrics, so every per agent number has to be derived from log text or from trace subsegments. The reader is not an AWS reader, so the console exists to translate a metrics namespace and a query language into a health verdict. The product is a capstone piece that is screenshotted while working and then dismantled, which makes the order of teardown relative to screenshots a hard constraint rather than a preference.

Two further forces shaped the design. Security is a constraint rather than a nicety, because the console reads a real AWS account and a browser cannot be trusted with a credential, so all AWS access must stay on the server. And reusing an existing session, which the engineer chose, does not pin an identity: the SDK's default provider chain can resolve some other source, so the console must resolve and display whose account it is reading or it can faithfully display the wrong account's telemetry.

The NovaMart deployment also has two known defects that limit what this console can honestly show. Its modules import the plain Strands tool decorator rather than the tracing decorator, so the worker agent subsegments are never emitted and the X Ray service map shows only the orchestrator and the knowledge base nodes. Its runtime build was staged before the session memory module was added, so the deployed runtime runs older code than the repository. The console observes what exists and does not attempt to correct the agent, but both facts are recorded so no panel claims more than the data supports.

## Options considered

### Option 1: Server components read AWS, client components render charts

One Next.js app where each page reads AWS on the server and passes plain arrays into a client chart component.

**Pros**: one deployable, credentials server only by construction, no extra test tooling invented.
**Cons**: async server components cannot be unit rendered, so the end to end layer needs a live AWS session.

### Option 2: Pages call same origin route handlers and fetch JSON on the client

One Next.js app with the same credential boundary, but data arrives through route handlers the page fetches.

**Pros**: still one deployable and still server only credentials; the end to end layer can intercept requests and serve fixtures without a session.
**Cons**: nine panels become nine round trips on a page, and loading and error state move into the client.

### Option 3: Separate React app with a thin API proxy

**Pros**: a clean API seam, portable front end.
**Cons**: two deployables to operate and tear down, a second place to misconfigure credentials, and a place a credential could leak.

## Rationale

Option 1 was chosen over Option 2 on audience grounds rather than technical ones. Option 2 is the better testing story and remains the runner up. The deciding factor is that a support staff member opening the overview would watch nine panels resolve at different times, and the one screen whose job is to communicate health would look unsettled while it loaded. Option 3 was rejected because its second deployable costs real effort to tear down and adds a second configuration surface for a project whose entire purpose is to be deleted afterwards.

The comparison against charting and icons was structural rather than meritorious. Recharts is adopted because shadcn's chart component wraps it and supplies the theme aware container, tooltip, and legend, so choosing anything else would mean building the layer shadcn already provides. Lucide is adopted for the same reason: it is shadcn's default, so it is what `shadcn add` already emits and the CLI has a migration path away from it. That coupling is a real cost and is recorded in Consequences.

Two corrections were made during design rather than left standing.

**Caching required an explicit correction.** The first draft argued that AWS SDK calls bypass the Next.js fetch cache and therefore caching was a non issue. The claim is true and the reasoning was wrong, because build time prerendering is not gated on `fetch` at all. A route whose only data source is an SDK call can be prerendered at build time and then serve one build time reading forever, which is the single worst failure a monitoring console can have. The fix is to declare dynamicness explicitly on every telemetry route and to assert it in a test.

**The first empty state criterion was self contradictory.** It said an empty series must never render as zero, which taken literally also forbids rendering an honest measured zero, making a healthy idle agent indistinguishable from a broken one, while also contradicting the promise never to show data that is not real. The criterion now separates three genuinely different conditions, no activity in range, no telemetry at all, and read failed, and requires a real zero to render as a labelled zero.

## Cross check record

An independent model read the first draft of this spec and returned twenty two findings. All twenty two were closed in the spec. The findings that changed the substance, rather than the wording, were these.

**The prerender defect.** As described above, the first draft's caching reasoning hid a failure that made the console serve stale readings indefinitely. Fixed by requiring explicit dynamicness and by turning the assertion into a design constraint.

**The empty state criterion was wrong.** Rewritten, as above.

**Identity was not pinned.** Reusing a session does not fix which identity the provider chain resolves, so the console could display the wrong account. Fixed by requiring `GetCallerIdentity` to be displayed in the footer.

**No timeout, so a hung page instead of a failed panel.** The default provider chain can block on a credential refresh or a hung metadata probe, which defeats the per panel isolation the spec promises. Fixed by a per read `AbortSignal` timeout.

**The metrics client was a phantom dependency.** The first draft installed the CloudWatch metrics client while admitting the agent publishes no custom metrics, so it had no defined use. Removed, with Embedded Metric Format recorded as the correct future route.

**Client injection contradicted mockability.** Saying the credential source was a single configuration value implied reading the environment in the constructor, which is exactly what makes a module unmockable. Fixed by giving every data function a `deps` argument that defaults to the real factory.

**Silent truncation was unspecified.** A pagination cap that silently shortens a list produces a wrong total, which is the one thing this console must not show. Fixed by requiring truncation to be stated on screen.

**Trace sampling was unaddressed.** If traces are sampled and request volume is derived from logs, the two counts will not reconcile and a reader will read that as a bug. Fixed by recording the sampling rate in the read contract and requiring the trace panel to state it is sampled.

The remaining findings, closed without changing the shape of the design: the data contract is now an explicit table of confirmed values, the nine panels are enumerated, health states and thresholds are defined with a single pure evaluation function, the time range control is specified as a URL parameter with bucket sizes, error copy is split into a plain sentence and a collapsed technical detail, configuration variable names are listed with none exposed to the browser, the `server-only` guard and `serverExternalPackages` are required, a route level loading state is named, and the account identifier is masked from anything that can reach a screenshot.

Two soundness notes were also accepted. The claim about Vitest was imprecise, since it is the React Testing Library that has no server component renderer rather than Vitest itself, and the wording was corrected while the decision stood. And the dev server binds a reachable interface by default, which is recorded as a reason the console stays unpublished during the screenshot phase.

The cross check also raised a materially simpler rendering seam, namely keeping one Next.js app but having pages fetch JSON from same origin route handlers. It was considered seriously and rejected on audience grounds, recorded under Option 2 above. The critique was right that it would make the end to end layer deterministic without a live session, and that benefit was accepted as a known tradeoff rather than ignored.

## References

**Project sources** (verifiable, in this repo):
- The installed `shadcn` skill (`.agents/skills/shadcn/`), supplying the component, theming, and icon conventions.
- The installed `aws-observability` skill (`.agents/skills/aws-observability/`), covering the CloudWatch Logs Insights, tracing, and dashboard documentation the console reads.
- The installed `nextjs-app-router-patterns` skill (`.agents/skills/nextjs-app-router-patterns/`), informing the server and client boundary.
- Scope feature 1 in `docs/scope/scope.md`, and the Tracer Bullet build approach in that scope's header.
- The NovaMart agent's logging and tracing code, the source of the confirmed values in the read contract.

**Practices & standards**:
- Keep AWS credentials server side and enforce it at build time, not by review.
- Declare dynamic rendering explicitly where the data source is not a `fetch`.
- Design for failure, so one failed, denied, or hung read degrades a panel rather than the page.
- Never let colour alone, and never an icon alone, carry meaning.
- Make the identity of a data source visible so reading the wrong account is detected.
- Surface pagination caps so a truncated list is never mistaken for a complete one.

**Links** (web verified during the design conversation, not re fetched):
- shadcn/ui chart component, which uses Recharts v3: https://ui.shadcn.com/docs/components/chart
- `@aws-sdk/client-xray`: https://registry.npmjs.org/@aws-sdk/client-xray/latest
- `@aws-sdk/client-cloudwatch-logs`: https://registry.npmjs.org/@aws-sdk/client-cloudwatch-logs/latest
- `recharts` peer dependency range, which includes React 19: https://registry.npmjs.org/recharts/latest
