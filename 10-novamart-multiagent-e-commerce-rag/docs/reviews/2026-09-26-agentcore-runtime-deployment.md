# check verify: AgentCore Runtime deployment

Feature: scope feature 4, "AgentCore Runtime deployment" (docs/scope/scope.md, Phase 2).
Run date: 2026-09-26. Mode: verify (drive the real app, read real AWS state).
No implementation code was changed during this run.

## Verdict

**FAIL.** The runtime exists in AWS and is configured exactly as specced, but the deployed
artifact cannot start, so the multi agent system is not actually running on AgentCore.
The task3 test suite scores 13/20 for a different reason (the three Knowledge Base IDs),
which hides this.

## What was run

| Command | Result |
|---|---|
| `python tests/test_agent.py task3` | 13/20 pts, exit 0. Guardrail checks 3 of 3 pass. `test_3_4_agentcore_runtime_ready` fails with "environment variable RETURNS_KB_ID missing; environment variable SHIPPING_KB_ID missing; environment variable WARRANTY_KB_ID missing" |
| `bedrock-agentcore-control get_agent_runtime` (direct boto3, no project code) | status READY, networkMode PUBLIC, serverProtocol HTTP, roleArn arn:aws:iam::067269469477:role/novamart-agentcore-agentcore-role, entryPoint ["agent_orchestrator.py"], runtime PYTHON_3_12 |
| `python src/agent_orchestrator.py invoke "Can you check the status of my order ORD-27176?" CUST-001` (4 attempts) | all 4 fail: `RuntimeClientError: Runtime initialization time exceeded. Please make sure that initialization completes in 30s.` |
| CloudWatch tail of `/aws/bedrock-agentcore/runtimes/novamart_agentcore_runtime-KFKbdJ7XXQ-DEFAULT` | 4 streams, every one ends the same way: `File "/var/task/agent_orchestrator.py", line 112, in <module> from workflow.state import ( ModuleNotFoundError: No module named 'workflow'` |
| `s3 get_object` on the deployed artifact `s3://bedrock-agentcore-codebuild-sources-067269469477-us-east-1/novamart_agentcore_runtime/deployment.zip`, then a zip listing | third party deps present as aarch64 wheels (strands, bedrock_agentcore, boto3, pydantic_core .cpython-312-aarch64-linux-gnu.so). Project packages ABSENT: `workflow/`, `agents/`, `deploy/`, `serving/`, `cli/`. Only these project files are in the zip: agent_orchestrator.py, agent_utils.py, agent_observability.py, bedrock_kb_retrieval.py, agentcore_cli.py, config.py, pyproject.toml, requirements.txt, .agentcore-runtime |
| `python src/agent_orchestrator.py serve` locally, then `GET /ping` and `POST /invocations` | `/ping` 200 `{"status":"Healthy"}`, `/invocations` 200 with the real answer (order ORD-27176, status Delivered, Wireless Headphones Pro, $149.99), full Inventory to Communication routing in the server output. The code is sound. The staging is the only thing broken. |
| `create_guardrail()` (live, idempotent re-run) | prints "Guardrail already exists: puwoy0wtj9a7 (version: 1)", returns ('puwoy0wtj9a7', '1'). The new `_find_guardrail` and `_latest_published_version` helpers work against real Bedrock and create no duplicate |
| `python src/agentcore_cli.py` | reports the Python toolkit 0.3.12, and `deployed_runtime_arn()` returns the correct ARN through the paginated AWS fallback |
| Guardrail wiring with only the runtime env vars set (no .env): `workflow.graph.build_agent_graph()` | all 5 agents plus the orchestrator pick up `guardrail_id=puwoy0wtj9a7`, `guardrail_version=1` on their BedrockModel. The "guardrail attached via environment variables" path is correct |

## Acceptance criteria

| Criterion | Verdict | Evidence |
|---|---|---|
| Deploy the multi agent system to AgentCore Runtime | **FAIL** | Control plane shows a READY runtime, but every invocation dies at import with `ModuleNotFoundError: No module named 'workflow'`, and the deployed zip has no `workflow/`, `agents/`, `deploy/`, `serving/` or `cli/` package. The system is not serving. |
| Using the AgentCore CLI | PASS | `agentcore` resolves to the Python toolkit 0.3.12, `agentcore_cli.deploy()` ran, artifact uploaded, runtime created. The adaptation away from the Node CLI works. |
| Guardrail attached via environment variables | PASS | Runtime env vars `GUARDRAIL_ID=puwoy0wtj9a7`, `GUARDRAIL_VERSION=1`, identical to .env. The env only code path attaches the guardrail to all 5 agents. |
| PUBLIC networking, HTTP protocol, foundation execution role | PASS | `networkConfiguration.networkMode=PUBLIC`, `protocolConfiguration.serverProtocol=HTTP`, `roleArn=.../novamart-agentcore-agentcore-role` (the CloudFormation foundation role, no auto created role). |
| Set env vars AWS_REGION, PROJECT_NAME, KB IDs, AGENT_LOG_GROUP, GUARDRAIL_ID, GUARDRAIL_VERSION | PARTIAL | 5 of 8 set and matching .env. The 3 KB IDs are absent, see accepted item A. |
| Deploy via `agentcore_cli.deploy()` and read the deployed ARN | PASS | `deployed_runtime_arn()` returns arn:aws:bedrock-agentcore:us-east-1:067269469477:runtime/novamart_agentcore_runtime-KFKbdJ7XXQ |
| Done when: `.env` contains `AGENTCORE_RUNTIME_ARN` | PASS | present and equal to the live ARN |
| Done when: `python tests/test_agent.py task3` passes | FAIL | 13/20. Both the accepted KB item and defect 1 sit behind this one command. |

## Defects

### 1. HIGH, blocking: the staged runtime package is missing every project package

`stage_runtime_code()` in `src/agentcore_cli.py` copies a flat list of six files
(`RUNTIME_PROJECT_FILES`: agent_orchestrator.py, agent_utils.py,
agent_observability.py, bedrock_kb_retrieval.py, agentcore_cli.py, config.py).
Since the refactor into `src/agents/`, `src/workflow/`, `src/deploy/`, `src/serving/`
and `src/cli/`, the entry point imports all of them at module load
(`agent_orchestrator.py` lines 112 to 163). Those five packages are never staged, so
the container dies on the first import and the runtime never answers `/ping`.

Evidence (all four agree):
1. `invoke` fails 4 times with "Runtime initialization time exceeded".
2. Four separate CloudWatch log streams in the runtime log group, each ending in
   `ModuleNotFoundError: No module named 'workflow'` at line 112.
3. The deployed `deployment.zip` has no `workflow/`, `agents/`, `deploy/`, `serving/`
   or `cli/` entry.
4. The same entry point works from the full local tree: local `serve` returned 200 on
   `/ping` and a correct `/invocations` answer.

Fix: copy the whole `src/` package tree into `build/runtime/`, not a flat file list,
and redeploy. Then re run the invoke command above as the acceptance check. Note the
entry point already inserts its own directory onto `sys.path`, so once the packages
are staged the imports resolve with no other change.

### 2. MEDIUM, coverage gap: the task3 suite never invokes the runtime

`tests/test_agent.py` `test_3_4_agentcore_runtime_ready` only reads the control plane.
A runtime that is READY, PUBLIC, HTTP and fully configured still scores 13/20 and looks
like it is only waiting on Knowledge Bases. A single real `invoke_agent_runtime` call
would have caught defect 1 immediately. Worth adding as a permanent assertion (see
below), not a code change to the provided suite.

### 3. LOW: `.bedrock_agentcore.yaml` declares the wrong platform

The generated file has `platform: linux/amd64` while the packaged dependencies are all
aarch64 (`pydantic_core/_pydantic_core.cpython-312-aarch64-linux-gnu.so` and friends).
It works today because AgentCore runs an arm64 image, but `write_yaml_runtime_config()`
never sets `platform`, so it takes the toolkit default. If that field is ever honored,
the build would produce an x86 image that cannot load the aarch64 extensions.

### 4. LOW: stale documentation inside `src/agentcore_cli.py`

The module docstring still describes the Node CLI: it says `agentcore deploy -y`, says
the CLI writes `agentcore/.cli/deployed-state.json`, and tells the reader to uninstall
the Python toolkit. The header also says "do not modify", while the deployment now
depends on the modifications. `read_deployed_state()` and `reset_deployed_state()` are
dead paths, since the Python toolkit writes no state file.

Also, `deploy_to_agentcore_runtime()` (`src/deploy/runtime.py` lines 55 to 56) prints
`stack AgentCore-novamart-default`, but no such CloudFormation stack exists.
`describe_stacks` lists only `novamart-agentcore` and the lesson stacks. The Python
toolkit creates the runtime through the control plane, with no CDK stack.

### 5. LOW: the generated `.bedrock_agentcore/` state directory is not ignored by git

`git status` shows `?? .bedrock_agentcore/` and `?? .bedrock_agentcore.yaml` in this
project. `.gitignore` covers `agentcore/.cli/` but not the toolkit directory, so toolkit
state can end up committed.

### 6. Fragility for review: two config files must stay in step

`configure_runtime()` writes both `agentcore/agentcore.json` (the source the wrapper
reads env vars from, `yaml_runtime_env_vars()`) and `.bedrock_agentcore.yaml` (the
source the toolkit reads network mode, protocol and role from). They only agree
because they are written together in one function. Editing either by hand silently
desyncs them.

### 7. Risk to watch after the fix: initialization must finish inside 30 seconds

Locally, `/ping` answered within the first 2 second poll, and the one invocation took
38 seconds, almost all of it in Bedrock model calls. Initialization (imports plus
graph build) looks comfortable. Still, the first invoke after redeploying is the
check, and if it times out again, look at the new log stream before anything else.

## Accepted items, confirmed

**A. The three Knowledge Base IDs are the only reason task3 scores 13/20.** Confirmed
two ways. The test itself names exactly three problems, all of them empty KB ID
environment variables. An independent read of the runtime shows everything else is
correct: status READY, PUBLIC, HTTP, and `AWS_REGION`, `PROJECT_NAME`,
`AGENT_LOG_GROUP`, `GUARDRAIL_ID`, `GUARDRAIL_VERSION` all present and byte identical
to .env, with `GUARDRAIL_ID` matching. The same three IDs are empty in .env, and
scope feature 6 says the Knowledge Bases are created by hand in the console. So the
7 points come back as soon as Task 5 fills the IDs and the runtime is redeployed.

**B. The X-Ray trace segment warning.** Not a defect, and it has already cleared on
its own: `xray.get_trace_segment_destination()` now returns
`{"Destination": "CloudWatchLogs", "Status": "ACTIVE"}`, no ValidationException. The
runtime environment still carries only `AGENT_LOG_GROUP` (no `AGENT_LOG_LEVEL`, no
`AGENT_TRACE_SAMPLING_RATE`), so observability is untouched and stays in scope
feature 7.

## What /test should lock in

- A real invocation against `AGENTCORE_RUNTIME_ARN` that must return a `result` key.
  This is the assertion that would have caught defect 1.
- A guard on the staged package: every subpackage under `src/` that the entry point
  imports must be present in `build/runtime/` after `stage_runtime_code()`.
- An assert that the runtime environment variables are a superset of the eight keys
  `test_3_4` requires, so a new missing key is caught before the suite.
- An assert that `.bedrock_agentcore.yaml` `platform` matches the architecture of the
  wheels the toolkit actually installs.

## Closing gate

Nothing was ticked. The scope rows for feature 4 (`Build it`, the three milestones,
`Verify it`) stay unticked, and the feature stays `planned` in the At a glance table,
because the verdict is FAIL. There is no `docs/specs/` directory and no
`docs/specs/NNNN-agentcore-runtime-deployment/verify.md` for this feature, so there was
no per feature checklist to tick. The next step after the fix is to re run
`/check verify agentcore runtime deployment`.
