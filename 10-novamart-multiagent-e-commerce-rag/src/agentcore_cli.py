"""
agentcore_cli.py
================
Helper around the **AgentCore CLI** (`agentcore`) that deploys the runtime.

Two implementations install a command with that name, and this wrapper drives
whichever is on PATH:

* **Python toolkit** - `pip install bedrock-agentcore-starter-toolkit`
  (the current default here). Reads `.bedrock_agentcore.yaml`, deploys with
  `agentcore deploy --auto-update-on-conflict --env K=V`, and records no local
  state, so the ARN comes from a paginated `list_agent_runtimes` lookup.
* **Node CLI** - `npm install -g @aws/agentcore` (the newer product). Reads
  `agentcore/agentcore.json`, deploys with `agentcore deploy -y`, and writes
  `agentcore/.cli/deployed-state.json`.

Both write `agentcore/agentcore.json` (via `configure_runtime`) so the project
config stays valid for either one.

How the project uses it
-----------------------
* `agentcore/agentcore.json`  - declarative description of the AgentCore
  Runtime (name, entry point, code location, network mode, protocol,
  environment variables, execution role). `configure_runtime` updates the
  runtime entry with the values the deploy passes in, and mirrors them into
  `.bedrock_agentcore.yaml` for the Python toolkit.
* `build/runtime/`            - the code the CLI packages: this project's
  `src/*.py` modules, the `agents/`, `workflow/`, `deploy/`, `serving/` and
  `cli/` packages, `config.py`, a `requirements.txt` / `pyproject.toml` listing
  the runtime dependencies, and the `.agentcore-runtime` marker
  (`stage_runtime_code`). The CLI downloads matching arm64 / Python 3.12 wheels
  with `uv`, zips everything and uploads it - AgentCore *direct code
  deployment*.
* `agentcore deploy`          - creates or updates the runtime
  (`deploy`). The first run also bootstraps in the account.

Why `requirements.txt` matters: with only a `pyproject.toml` the Python toolkit
runs `uv pip compile` on the *host* (Windows), which pins `pywin32` - a
strands-agents -> mcp dependency that is correctly marked
`sys_platform == 'win32'` - and the later Linux ARM64 install then fails with
"pywin32==312 has no wheels ... manylinux". A `requirements.txt` makes uv
evaluate markers against the target platform instead.

Prerequisites (see README): `uv`, the AgentCore CLI (Python toolkit or Node
CLI), and AWS credentials for the project region.
"""

import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

# ─────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────
SRC_DIR       = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT  = os.path.dirname(SRC_DIR)                       # starter/
AGENTCORE_DIR = os.path.join(PROJECT_ROOT, 'agentcore')        # CLI project config
CONFIG_PATH   = os.path.join(AGENTCORE_DIR, 'agentcore.json')
TARGETS_PATH  = os.path.join(AGENTCORE_DIR, 'aws-targets.json')
STATE_PATH    = os.path.join(AGENTCORE_DIR, '.cli', 'deployed-state.json')
RUNTIME_CODE_DIR = os.path.join(PROJECT_ROOT, 'build', 'runtime')   # codeLocation

# The Python toolkit (bedrock-agentcore-starter-toolkit) reads a different,
# project-root config file with the same "agents" shape as agentcore.json.
YAML_CONFIG_PATH = os.path.join(PROJECT_ROOT, '.bedrock_agentcore.yaml')

# ─────────────────────────────────────────────────────
# RUNTIME PACKAGE SETTINGS
# ─────────────────────────────────────────────────────
RUNTIME_ENTRYPOINT = 'agent_orchestrator.py'   # started by the runtime with no arguments -> serve mode
RUNTIME_PYTHON     = 'PYTHON_3_12'             # agentcore.json runtimeVersion
RUNTIME_MARKER     = '.agentcore-runtime'      # tells agent_orchestrator.__main__ to serve HTTP
RUNTIME_REQUIREMENTS = [
    'strands-agents>=1.0',
    'bedrock-agentcore>=0.1',
    'boto3>=1.42',
    'python-dotenv>=1.0',
]
RUNTIME_PROJECT_FILES = [
    os.path.join(SRC_DIR, 'agent_orchestrator.py'),
    os.path.join(SRC_DIR, 'agent_utils.py'),
    os.path.join(SRC_DIR, 'agent_observability.py'),
    os.path.join(SRC_DIR, 'bedrock_kb_retrieval.py'),
    os.path.join(SRC_DIR, 'agentcore_cli.py'),
    os.path.join(PROJECT_ROOT, 'config.py'),
]
# agent_orchestrator.py is a thin facade: at import time it re-exports from these
# packages, so the deployed runtime cannot start without them. Staging only the
# flat file list above makes every invoke fail with
# `ModuleNotFoundError: No module named 'workflow'`.
RUNTIME_PACKAGE_DIRS = ['agents', 'workflow', 'deploy', 'serving', 'cli', 'session']
# Directories never worth shipping inside the runtime package.
RUNTIME_EXCLUDE_DIRS = {'__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache'}

INSTALL_HINT = (
    "The AgentCore CLI is not installed or not on PATH.\n"
    "  Install the Python toolkit:  pip install bedrock-agentcore-starter-toolkit\n"
    "  (the Node CLI `npm install -g @aws/agentcore` also works - this wrapper\n"
    "   drives whichever is on PATH)\n"
    "  Docs: https://github.com/aws/bedrock-agentcore-starter-toolkit\n"
)


# ─────────────────────────────────────────────────────
# CLI PROCESS
# ─────────────────────────────────────────────────────

def cli_path() -> str:
    """Return the path of the `agentcore` executable or raise with install instructions."""
    path = shutil.which('agentcore')
    if not path:
        raise RuntimeError(INSTALL_HINT)
    return path


def cli_version() -> str:
    """Return the installed CLI version string (e.g. '0.30.0')."""
    out = subprocess.run([cli_path(), '--version'], capture_output=True, text=True,
                         encoding='utf-8', errors='replace')
    text = ((out.stdout or '') + (out.stderr or '')).strip()
    if out.returncode == 0 and text:
        return text
    # The Python toolkit (bedrock-agentcore-starter-toolkit) has no top-level
    # --version flag. It may be installed in a different interpreter than this
    # one, so resolve its dist-info from the `agentcore` executable's own
    # site-packages rather than from importlib.metadata.
    import glob
    import re as _re
    exe = cli_path()
    for sp in glob.glob(os.path.join(os.path.dirname(os.path.dirname(exe)),
                                    'Lib', 'site-packages')) + \
             glob.glob(os.path.join(os.path.dirname(os.path.dirname(exe)),
                                    'lib', 'python*', 'site-packages')):
        for meta in glob.glob(os.path.join(
                sp, 'bedrock_agentcore_starter_toolkit-*.dist-info', 'METADATA')):
            with open(meta, encoding='utf-8', errors='replace') as fh:
                for line in fh:
                    if line.startswith('Version:'):
                        return f"{line.split(':', 1)[1].strip()} (python toolkit)"
    try:
        from importlib.metadata import version
        return f"{version('bedrock-agentcore-starter-toolkit')} (python toolkit)"
    except Exception:
        return 'unknown'


def run(*args: str, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess:
    """
    Run `agentcore <args>` from the project root with the project region.
    Output streams to the terminal unless capture=True.
    """
    env = dict(os.environ)
    env.setdefault('AWS_REGION', config.AWS_REGION)
    env.setdefault('AWS_DEFAULT_REGION', config.AWS_REGION)
    # Silence the Python toolkit's "no longer supported" banner and force UTF-8
    # so its rich/typer output does not raise UnicodeEncodeError on Windows.
    env.setdefault('AGENTCORE_SUPPRESS_RECOMMENDATION', '1')
    env.setdefault('PYTHONIOENCODING', 'utf-8')
    result = subprocess.run(
        [cli_path(), *args], cwd=PROJECT_ROOT, env=env,
        capture_output=capture, text=True, encoding='utf-8', errors='replace',
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or '').strip() if capture else ''
        raise RuntimeError(f"agentcore {' '.join(args)} failed (exit {result.returncode})"
                           + (f":\n{detail}" if detail else ''))
    return result


# ─────────────────────────────────────────────────────
# agentcore.json
# ─────────────────────────────────────────────────────

def read_project_config() -> dict:
    with open(CONFIG_PATH, encoding='utf-8') as fh:
        return json.load(fh)


def write_project_config(spec: dict) -> None:
    with open(CONFIG_PATH, 'w', encoding='utf-8') as fh:
        json.dump(spec, fh, indent=2)
        fh.write('\n')


def runtime_spec(spec: dict) -> dict:
    """Return the runtime entry for this project's agent, creating it if missing."""
    for rt in spec.setdefault('runtimes', []):
        if rt.get('name') == config.AGENTCORE_AGENT_NAME:
            return rt
    rt = {'name': config.AGENTCORE_AGENT_NAME, 'build': 'CodeZip'}
    spec['runtimes'].append(rt)
    return rt


def runtime_env_vars() -> dict:
    """Environment variables currently declared for the runtime in agentcore.json."""
    try:
        rt = runtime_spec(read_project_config())
    except FileNotFoundError:
        return {}
    return {e['name']: e['value'] for e in rt.get('envVars', []) if 'name' in e}


def configure_runtime(env_vars: dict = None, network_mode: str = None, protocol: str = None,
                      execution_role_arn: str = None) -> dict:
    """
    Update the runtime entry in agentcore/agentcore.json.

      env_vars           - merged into the runtime's `envVars` (existing keys are
                           overwritten, empty values are skipped)
      network_mode       - 'PUBLIC' or 'VPC'
      protocol           - 'HTTP', 'MCP' or 'A2A'
      execution_role_arn - IAM role the runtime assumes (config.AGENTCORE_ROLE_ARN,
                           created by the CloudFormation stack); the CLI then
                           does not create a role of its own

    The build settings (CodeZip, entry point, code location, Python version)
    are always (re)set so the CLI packages `build/runtime/`.
    Returns the updated runtime entry.
    """
    spec = read_project_config()
    rt = runtime_spec(spec)
    rt.update({
        'build':          'CodeZip',
        'entrypoint':     RUNTIME_ENTRYPOINT,
        'codeLocation':   os.path.relpath(RUNTIME_CODE_DIR, PROJECT_ROOT).replace(os.sep, '/') + '/',
        'runtimeVersion': RUNTIME_PYTHON,
        # The project ships its own X-Ray tracing (agent_observability.py); with
        # OTel auto-instrumentation off the entry point is started directly.
        'instrumentation': {'enableOtel': False},
    })
    if network_mode:
        rt['networkMode'] = network_mode
    if protocol:
        rt['protocol'] = protocol
    if execution_role_arn:
        rt['executionRoleArn'] = execution_role_arn
    if env_vars:
        merged = {e['name']: e['value'] for e in rt.get('envVars', []) if 'name' in e}
        # Empty values are skipped (e.g. KB IDs before Task 5) - re-running the
        # deploy pipeline after the KBs exist adds them.
        merged.update({k: str(v) for k, v in env_vars.items() if v not in (None, '')})
        rt['envVars'] = [{'name': k, 'value': v} for k, v in merged.items()]
    write_project_config(spec)
    # Keep the Python toolkit's .bedrock_agentcore.yaml in sync. It reads the
    # network/protocol/role from YAML and the env vars from `deploy --env`.
    write_yaml_runtime_config(env_vars=env_vars, network_mode=network_mode,
                              protocol=protocol, execution_role_arn=execution_role_arn)
    return rt


def stack_name() -> str:
    """CloudFormation stack the CLI deploys: AgentCore-<project>-<target>."""
    project = config.AGENTCORE_PROJECT_NAME
    try:
        project = read_project_config().get('name', project)
    except FileNotFoundError:
        pass
    return f"AgentCore-{project.replace('_', '-')}-default"


def write_yaml_runtime_config(env_vars: dict = None, network_mode: str = None,
                              protocol: str = None, execution_role_arn: str = None) -> dict:
    """
    Write the Python toolkit's project config (.bedrock_agentcore.yaml).

    Mirrors configure_runtime() for `bedrock-agentcore-starter-toolkit`, which
    reads a project-root YAML file keyed by agent name instead of
    agentcore/agentcore.json. Environment variables are NOT stored here - the
    Python toolkit takes them on the command line (`agentcore deploy --env K=V`).
    """
    import yaml

    agent = {
        'name': config.AGENTCORE_RUNTIME_NAME,
        'language': 'python',
        'entrypoint': RUNTIME_ENTRYPOINT,
        'deployment_type': 'direct_code_deploy',
        'runtime_type': RUNTIME_PYTHON,
        'source_path': os.path.relpath(RUNTIME_CODE_DIR, PROJECT_ROOT).replace(os.sep, '/'),
        # The toolkit's schema puts the execution role and the network /
        # protocol configuration under `aws`, not under `bedrock_agentcore`.
        'aws': {
            'execution_role': execution_role_arn,
            'execution_role_auto_create': False,
            'account': config.ACCOUNT_ID,
            'region': config.AWS_REGION,
            'network_configuration': {'network_mode': network_mode or 'PUBLIC'},
            'protocol_configuration': {'server_protocol': protocol or 'HTTP'},
        },
    }
    spec = {'default_agent': config.AGENTCORE_RUNTIME_NAME,
            'agents': {config.AGENTCORE_RUNTIME_NAME: agent}}
    with open(YAML_CONFIG_PATH, 'w', encoding='utf-8') as fh:
        yaml.safe_dump(spec, fh, sort_keys=False)
    return spec


def yaml_runtime_env_vars() -> dict:
    """Environment variables to pass to `agentcore deploy --env K=V`."""
    return {k: str(v) for k, v in runtime_env_vars().items() if v not in (None, '')}


# ─────────────────────────────────────────────────────
# RUNTIME CODE STAGING  (what the CLI packages)
# ─────────────────────────────────────────────────────

def stage_runtime_code() -> str:
    """
    Assemble build/runtime/ - the directory `agentcore deploy` packages:
    the src/ modules, config.py, a pyproject.toml with the runtime
    dependencies and the serve-mode marker file. Returns the directory.
    """
    missing = [p for p in RUNTIME_PROJECT_FILES if not os.path.exists(p)]
    if missing:
        raise FileNotFoundError(f"Cannot stage runtime code, missing: {missing}")

    if os.path.isdir(RUNTIME_CODE_DIR):
        shutil.rmtree(RUNTIME_CODE_DIR)
    os.makedirs(RUNTIME_CODE_DIR)

    for path in RUNTIME_PROJECT_FILES:
        shutil.copy2(path, os.path.join(RUNTIME_CODE_DIR, os.path.basename(path)))

    for pkg in RUNTIME_PACKAGE_DIRS:
        src_pkg = os.path.join(SRC_DIR, pkg)
        if not os.path.isdir(src_pkg):
            raise FileNotFoundError(f"Cannot stage runtime code, missing package dir: {src_pkg}")
        shutil.copytree(
            src_pkg,
            os.path.join(RUNTIME_CODE_DIR, pkg),
            ignore=shutil.ignore_patterns(*RUNTIME_EXCLUDE_DIRS, '*.pyc'),
        )

    deps = ',\n'.join(f'  "{req}"' for req in RUNTIME_REQUIREMENTS)

    # requirements.txt is what the Python toolkit actually installs from, and it
    # is preferred over pyproject.toml. It matters that it exists: with only a
    # pyproject.toml the toolkit runs `uv pip compile` on the *host* (Windows),
    # which pins pywin32 (a strands-agents -> mcp dependency, correctly marked
    # `sys_platform == 'win32'`) into a lock file, and the later Linux ARM64
    # install then fails with "pywin32==312 has no wheels ... manylinux". Going
    # straight to requirements.txt makes uv evaluate the markers against the
    # target platform instead, so pywin32 is skipped.
    with open(os.path.join(RUNTIME_CODE_DIR, 'requirements.txt'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(RUNTIME_REQUIREMENTS) + '\n')

    with open(os.path.join(RUNTIME_CODE_DIR, 'pyproject.toml'), 'w', encoding='utf-8') as fh:
        fh.write(
            '[project]\n'
            'name = "novamart-agentcore-runtime"\n'
            'version = "0.1.0"\n'
            'description = "NovaMart multi-agent support system - AgentCore Runtime package"\n'
            'requires-python = ">=3.12"\n'
            f'dependencies = [\n{deps},\n]\n'
            '\n'
            '[tool.uv]\n'
            # Same upstream issue as above, for any path that resolves the
            # pyproject: keep pywin32 off non-Windows targets.
            'override-dependencies = ["pywin32; sys_platform == \'win32\'"]\n'
        )
    with open(os.path.join(RUNTIME_CODE_DIR, RUNTIME_MARKER), 'w', encoding='utf-8') as fh:
        fh.write('agentcore runtime package\n')

    print(f"  Runtime code staged in {os.path.relpath(RUNTIME_CODE_DIR, PROJECT_ROOT)}/ "
          f"({len(RUNTIME_PROJECT_FILES)} files + {len(RUNTIME_PACKAGE_DIRS)} packages "
          f"({', '.join(RUNTIME_PACKAGE_DIRS)}) + requirements.txt/pyproject.toml, "
          f"entry point {RUNTIME_ENTRYPOINT})")
    return RUNTIME_CODE_DIR


# ─────────────────────────────────────────────────────
# DEPLOY / STATE
# ─────────────────────────────────────────────────────

def deploy(verbose: bool = False) -> None:
    """
    Deploy the staged build/runtime/ to AgentCore Runtime.

    Uses the Python toolkit's non-interactive interface:
      agentcore deploy --env K=V ... --auto-update-on-conflict
    (`-y` belongs to the Node CLI and is rejected by the Python toolkit, which
    is already non-interactive.)
    """
    if not os.path.isdir(RUNTIME_CODE_DIR):
        stage_runtime_code()

    args = ['deploy', '--auto-update-on-conflict']
    for name, value in yaml_runtime_env_vars().items():
        args += ['--env', f'{name}={value}']
    if verbose:
        args.append('--verbose')

    print(f"  Running: agentcore {' '.join(args[:2])} ...   "
          f"(CLI {cli_version()}, region {config.AWS_REGION})", flush=True)
    run(*args)


def read_deployed_state() -> dict:
    try:
        with open(STATE_PATH, encoding='utf-8') as fh:
            return json.load(fh)
    except (FileNotFoundError, ValueError):
        return {'targets': {}}


def deployed_runtime_arn() -> str:
    """
    ARN of the deployed runtime, or '' if it is not deployed.
    Read from agentcore/.cli/deployed-state.json (written by the Node CLI's
    `agentcore deploy`), falling back to a paginated lookup by name in AWS
    (the Python toolkit records no local state file).
    """
    for target in read_deployed_state().get('targets', {}).values():
        runtimes = (target.get('resources') or {}).get('runtimes') or {}
        rt = runtimes.get(config.AGENTCORE_AGENT_NAME)
        if rt and rt.get('runtimeArn'):
            return rt['runtimeArn']
    try:
        import boto3
        ctl = boto3.client('bedrock-agentcore-control', region_name=config.AWS_REGION)
        paginator = ctl.get_paginator('list_agent_runtimes')
        for page in paginator.paginate():
            for rt in page.get('agentRuntimes', []):
                if rt.get('agentRuntimeName') == config.AGENTCORE_RUNTIME_NAME:
                    return rt['agentRuntimeArn']
    except Exception:
        pass
    return ''


def reset_deployed_state() -> None:
    """Forget the deployed resources locally (used by infrastructure/cleanup.py)."""
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, 'w', encoding='utf-8') as fh:
        json.dump({'targets': {}}, fh, indent=2)
        fh.write('\n')


if __name__ == '__main__':
    print(f"agentcore CLI: {cli_path()} (version {cli_version()})")
    print(f"project config: {CONFIG_PATH}")
    print(f"runtime name:   {config.AGENTCORE_RUNTIME_NAME}")
    print(f"stack name:     {stack_name()}")
    print(f"deployed ARN:   {deployed_runtime_arn() or '(not deployed)'}")
