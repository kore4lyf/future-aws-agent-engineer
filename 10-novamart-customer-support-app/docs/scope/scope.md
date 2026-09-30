# Scope: NovaMart Customer Support App

A web app where NovaMart customers sign up or sign in and chat with the AI support agent, so someone with a problem gets help without opening a terminal or a support ticket. The app never lets the browser choose whose data it sees: a server piece checks who is signed in, takes the customer identity from that check, and only then asks the deployed agent for an answer. The app is built to production standards and run locally for screenshots.

**Build approach:** Tracer Bullet (one real path from sign up through a real agent answer, proven end to end, then thickened).
**Workflow:** Lean (verify on the real app after building, no separate test suite by default). The logic here is mostly wiring and screens, and the risk sits in the browser to agent path, which verification on the running app catches.

## At a glance

| # | Feature | Phase | Status |
|---|---------|-------|--------|
| 1 | Stack and architecture | Foundation | planned |
| 2 | Coding standards and tooling | Foundation | planned |
| 3 | Developer setup and AWS path | Foundation | planned |
| 4 | Customer identity mapping | Foundation | planned |
| 5 | Sign up and sign in | Skeleton | planned |
| 6 | Support chat | Slice 2 | planned |
| 7 | Conversation history | Slice 3 | planned |
| 8 | Responsive layout and keyboard access | Slice 4 | planned |
| 9 | Session and error handling | Slice 5 | planned |

## Foundations

### 1. Stack and architecture
Decide the stack and scaffold a runnable app. The one hard rule: the browser never holds an AWS credential and never chooses a customer id, so every call to the agent goes through a server piece that derives identity from the signed in session.
**Done when:** the stack is recorded in a spec, the app boots locally, and one server path reaches the agent and returns a real answer with no AWS credential in any browser bundle.
- [ ] Decide the stack (spec): `/architect stack and architecture`

### 2. Coding standards and tooling
Capture conventions from the real scaffolded project and install lint, format, and type checking.
**Done when:** the root `AGENTS.md` reflects the real stack, and lint, format, and type checking run clean.
- [ ] Capture conventions and tooling: `/audit`
- [ ] Install the tooling: `/develop tooling`
- [ ] Check it runs clean: `/test`

### 3. Developer setup and AWS path
Get a new developer to a working app fast, and record where the AWS pieces are and how to reach them. Names the local credentials, the deployed agent endpoint, and the documentation for the identity service and the runtime.
**Done when:** a new developer starts the app with one command using credentials already in their shell, the app reaches the deployed agent, and the written reference names the identity and runtime APIs the app uses.
- [ ] Design it (spec): `/architect developer setup and AWS path`

### 4. Customer identity mapping
Decide how a signed in email becomes the customer id the agent understands, and what happens for an email the agent has never seen. This is the foundation everything else stands on, because the agent reads order data by customer id and the browser must not be able to choose it.
**Done when:** a signed in email always resolves to one customer id that the server uses without the browser supplying it, a brand new email resolves to a new empty record rather than an error, and the rule is written down with the known limits.
- [ ] Design it (spec): `/architect customer identity mapping`

## Skeleton

### 5. Sign up and sign in
The first working slice and the whole core loop's front door. A customer creates an account with email and password, or signs in with an existing one, and lands in the app as themselves. No email verification, no password reset, and no second factor, by choice.
**Done when:** a new email can create an account and sign in, an existing one can sign in, a wrong password is refused with a clear message, signing out returns to the sign in screen, and the session survives a page refresh.
- [ ] Design it (spec): `/architect sign up and sign in`
- [ ] Build it: `/develop sign up and sign in`
   - [ ] Identity service configured and app wired to it
   - [ ] Sign up and sign in screens
   - [ ] Session persists across refresh and sign out clears it
- [ ] Verify it: `/check verify sign up and sign in`

## Slice 2

### 6. Support chat
The reason the app exists. The customer asks a question in plain language and sees the agent's answer, with the server taking the customer id from the signed in session rather than from the browser.
**Done when:** a signed in customer can send a message and see a real answer from the deployed agent, the customer id comes from the session and not from anything the browser sends, the chat reads well on a phone, and a failed call shows a clear retryable message rather than a blank screen.
- [ ] Design it (spec): `/architect support chat`

## Slice 3

### 7. Conversation history
Coming back to the app should not lose the conversation. Past chats are listed, and picking one continues it where it left off, because the agent already remembers a session.
**Done when:** a returning customer sees their past chats, can reopen one and keep talking, and a brand new customer sees an empty state that invites them to start, with no other customer's chats ever visible.
- [ ] Design it (spec): `/architect conversation history`

## Slice 4

### 8. Responsive layout and keyboard access
The app has to work on a phone, because that is where most people will use it, and it has to be usable without a mouse.
**Done when:** every screen is usable at phone width with no sideways scrolling, text and controls meet readable contrast, the whole app can be driven by keyboard alone, and form errors are announced rather than only coloured.
- [ ] Design it (spec): `/architect responsive layout and keyboard access`

## Slice 5

### 9. Session and error handling
Make the app behave when things go wrong: the session expires mid chat, the agent is slow, the agent is down, or the network drops.
**Done when:** an expired session returns the customer to sign in without losing their message, a slow agent shows progress rather than a frozen screen, an agent failure shows a plain message and a retry, and a dropped connection recovers the message instead of losing it.
- [ ] Design it (spec): `/architect session and error handling`

## Deferred
Out of scope for the current build pass, kept so the plan stays honest.
- **Email verification and password reset**: proving an inbox and recovering a forgotten password, deliberately left out of the first pass
- **Second factor sign in**: an extra step on top of email and password
- **File attachments**: letting a customer upload a photo of a damaged item
- **Rich streaming answers**: showing the answer as it is written, which the deployed runtime does not support today
- **Sending email or push**: any outbound notification to a customer
- **Staff view**: an internal screen for support staff to read or take over a conversation
- **Deployment to a live host**: running it on a real public host rather than locally
- **Analytics and product tracking**: measuring sign up and chat usage

## Legend

**The decision box.** Every feature carries exactly one, the sub task whose label ends with `(spec)`. Its wording varies (`Design it (spec)` normally, `Decide the stack (spec)` on Stack and architecture), so skills locate it by that `(spec)` suffix, never by an exact label. Every other box is an execution box and `/architect` never ticks one.

**Feature lifecycle**: the scope updates as a feature moves; each row is what it shows and who sets it:

| State | Set by | The feature shows |
|---|---|---|
| `planned` · needs a decision | `/scope` | one box: `Design it (spec): /architect <feature>` |
| `in-progress` (designed) | `/architect` at spec capture | `Design it` ticked; spec linked; `Build it: /develop <feature>` + 2 to 5 milestones; the tier's closing boxes (`Verify it` Lean+, `Test it` Medium+); any surfaced follow-up enrolled |
| `in-progress` (building) | `/develop` | milestone sub boxes tick one by one; code pointer filled |
| `in-progress` (verified) | `/check verify` | `Build it` + milestones ticked; `Verify it` ticked |
| `done` | the tier's last required stage (`Vibe` → `/develop`; `Lean` → `/check verify`; `Medium`/`Full` → `/test`), then `/sync` | required boxes ticked; `Review it`/`Document it` (Full) ticked by `/check review`/`/document`, tracked but not part of the `done` gate (Design/Build/Verify/Test); `/sync` captures conventions |

- **Next step** = the first unticked box (always a command or a tracked milestone).
- **needs a decision** = run `/architect` first; otherwise straight to `/develop` (or `/audit` for standards and tooling). The tag drops once the spec is captured.
- **Atomic build tasks live in the spec's `## Build plan`, not here**: the scope carries only the milestone rollup.
- **Status** `planned` → `in-progress` → `done`, plus `existing` (pre-workflow) and `dropped` (de-scoped, kept for history).
- **Approach tag** beside a heading (e.g. `· Facade`) overrides the project default for this feature; no tag = inherits it.
- **Workflow tier tag** beside a heading (e.g. `· Full`, `· Vibe`) overrides the project default `**Workflow:**` tier for that one feature; no tag = inherit. It is the single rigor dial (there is no separate "weight").
- **Workflow** (header line) is the project default tier, the stages each feature runs **after** `/develop`: **Vibe** = nothing after `/develop` (rely on its build time self check); **Lean** = `/check verify`; **Medium** = `/check verify` then `/test`; **Full** = `/check verify`, `/test`, a fresh model `/check review`, then `/document` (and most features need a spec). The tier also sets what closes a feature to `done`, the last required stage marks it: **Vibe** → `/develop` (build + self check); **Lean** → `/check verify` on PASS; **Medium**/**Full** → `/test` (with verify passed). At every tier an `Assumed` spec still blocks `done` until `/architect` ratifies it, and `/architect` still gates any feature that needs a decision (tier does not turn the gate off). A feature's own tier tag overrides this default. `/develop` reads the effective tier to scale the next steps it recommends.
- **Pointer line** (`spec <n> · code in <path>`): the spec link added by `/architect`, the code path by `/develop`.
