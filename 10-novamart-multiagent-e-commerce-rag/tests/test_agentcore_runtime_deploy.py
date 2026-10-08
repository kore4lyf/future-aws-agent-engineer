"""
test_agentcore_runtime_deploy.py
================================
Regression suite for the AgentCore Runtime deployment feature.

This suite is separate from `tests/test_agent.py`, which is the graded
capstone suite and is never modified. Everything here locks in the
behaviour of the deployment code:

  src/agentcore_cli.py    staging, project config, deploy, ARN lookup
  src/deploy/runtime.py   deploy_to_agentcore_runtime
  src/deploy/guardrail.py create_guardrail and its helpers
  src/agent_orchestrator.py the serve mode dispatch
  src/workflow/graph.py   guardrail attachment from the environment

Three defects that shipped broken before are now covered:

  1. `stage_runtime_code()` copied a flat list of six files, so the
     deployed package had no `workflow/`, `agents/`, `deploy/`,
     `serving/` or `cli/` package and every invoke died with
     `ModuleNotFoundError: No module named 'workflow'`.
  2. The entry point printed CLI usage text inside the runtime instead
     of serving HTTP, because nothing dispatched to `run_serve()`.
  3. `create_guardrail()` called the non existent
     `bedrock.list_guardrail_versions`, and it created a duplicate
     guardrail on every run.

Run everything (fast, no model calls):

    python -m unittest tests.test_agentcore_runtime_deploy -v

Run the one test that makes a real, paid model call through the
deployed runtime (about 30 seconds):

    $env:RUN_LIVE_INVOKE = "1"
    python -m unittest tests.test_agentcore_runtime_deploy -v
"""

import ast
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_DIR)
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
GRADED_SUITE = os.path.join(TESTS_DIR, 'test_agent.py')

# The graded suite cannot be edited, so the project modules are imported
# the same way it imports them.
for _p in (SRC_DIR, PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import agentcore_cli                                                    # noqa: E402
import config                                                           # noqa: E402
import deploy.guardrail as guardrail_deploy                             # noqa: E402
import deploy.runtime as runtime_deploy                                 # noqa: E402
from workflow.graph import _apply_guardrail                             # noqa: E402
from botocore.exceptions import ClientError                              # noqa: E402

# `test_3_4_agentcore_runtime_ready` in the graded suite requires these.
REQUIRED_RUNTIME_ENV_KEYS = (
    'AWS_REGION',
    'PROJECT_NAME',
    'RETURNS_KB_ID',
    'SHIPPING_KB_ID',
    'WARRANTY_KB_ID',
    'AGENT_LOG_GROUP',
    'GUARDRAIL_ID',
    'GUARDRAIL_VERSION',
)

# The three Knowledge Base IDs are legitimately empty today. They belong to
# the Knowledge Bases feature, which is manual console work. Every other key
# must be present on the runtime, so those three are checked separately and
# only reported, never failed on.
PENDING_KB_ENV_KEYS = ('RETURNS_KB_ID', 'SHIPPING_KB_ID', 'WARRANTY_KB_ID')

MUST_HAVE_ENV_KEYS = tuple(k for k in REQUIRED_RUNTIME_ENV_KEYS
                           if k not in PENDING_KB_ENV_KEYS)

PROJECT_PACKAGES = ('agents', 'workflow', 'deploy', 'serving', 'cli')

LIVE_INVOKE = os.environ.get('RUN_LIVE_INVOKE') == '1'

# The real project config files, captured before any test redirects them.
REAL_CONFIG_PATH = agentcore_cli.CONFIG_PATH
REAL_YAML_CONFIG_PATH = agentcore_cli.YAML_CONFIG_PATH

# Stand ins for the config values the deploy reads. config resolves most of
# them lazily from CloudFormation, which would make these tests call AWS.
SENTINEL_ACCOUNT_ID = '000000000000'
SENTINEL_LOG_GROUP = '/aws/bedrock/agentcore/test-project'
SENTINEL_ROLE_ARN = 'arn:aws:iam::000000000000:role/test-agentcore-role'
SENTINEL_KB_IDS = {
    'RETURNS_KB_ID': 'kb-returns-0000',
    'SHIPPING_KB_ID': 'kb-shipping-000',
    'WARRANTY_KB_ID': 'kb-warranty-000',
}

_MISSING = object()


@contextlib.contextmanager
def config_values(**overrides):
    """
    Set values straight into the config module namespace.

    mock.patch.object cannot be used on these, because config resolves most
    of them through a module __getattr__ that would call AWS while the
    patcher is being created.
    """
    saved = {name: config.__dict__.get(name, _MISSING) for name in overrides}
    config.__dict__.update(overrides)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is _MISSING:
                config.__dict__.pop(name, None)
            else:
                config.__dict__[name] = value


# ─────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────

def stage_into(directory):
    """Run stage_runtime_code() with its output redirected to `directory`."""
    with mock.patch.object(agentcore_cli, 'RUNTIME_CODE_DIR', directory):
        return agentcore_cli.stage_runtime_code()


def project_module_names():
    """Every top level module name the project ships under src/."""
    names = set()
    for entry in os.listdir(SRC_DIR):
        if entry.endswith('.py') and entry != '__init__.py':
            names.add(entry[:-3])
    for entry in os.listdir(SRC_DIR):
        if os.path.isfile(os.path.join(SRC_DIR, entry, '__init__.py')):
            names.add(entry)
    return names


def top_level_imports(path):
    """Return the first dotted component of every import in a Python file."""
    with open(path, encoding='utf-8') as fh:
        tree = ast.parse(fh.read(), path)
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.add(node.module.split('.')[0])
    return found


def graded_suite_env_keys():
    """Read the required env var keys straight out of the graded suite.

    The graded suite is never modified, so this parses `test_3_4` to find the
    keys it insists on. If somebody adds a key there, this suite fails
    instead of the deploy quietly missing it.
    """
    with open(GRADED_SUITE, encoding='utf-8') as fh:
        tree = ast.parse(fh.read(), GRADED_SUITE)
    keys = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name != 'test_3_4_agentcore_runtime_ready':
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.For) and isinstance(sub.iter, ast.Tuple):
                keys = [elt.value for elt in sub.iter.elts
                        if isinstance(elt, ast.Constant)]
    return tuple(keys)


# Probe run inside the staged tree. It replaces `run_serve` and the CLI entry
# point with recorders, then executes the real entry point file the way the
# interpreter would, so the `if __name__ == '__main__'` block under test is
# the one in the repository.
ENTRYPOINT_PROBE = '''
import os
import sys
import types

import cli.main as _cli_main
import serving.serve as _serve


def _serve_fn(*_a, **_k):
    print("CALLED:serve")


def _cli_fn(*_a, **_k):
    print("CALLED:cli")


_serve.run_serve = _serve_fn
_cli_main.main = _cli_fn

sys.argv = ["agent_orchestrator.py"] + sys.argv[1:]

_entry = os.path.abspath("agent_orchestrator.py")
_main = types.ModuleType("__main__")
_main.__file__ = _entry
sys.modules["__main__"] = _main
with open(_entry, encoding="utf-8") as _fh:
    exec(compile(_fh.read(), _entry, "exec"), _main.__dict__)

print("CALLED:none")
'''


def run_entrypoint(staged_dir, argv=(), timeout=300):
    """Execute the staged entry point and return the branch it took."""
    probe = os.path.join(staged_dir, '_entrypoint_probe.py')
    with open(probe, 'w', encoding='utf-8') as fh:
        fh.write(ENTRYPOINT_PROBE)
    env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
    env['PYTHONIOENCODING'] = 'utf-8'
    try:
        proc = subprocess.run(
            [sys.executable, '_entrypoint_probe.py', *argv],
            cwd=staged_dir, env=env, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=timeout,
        )
    finally:
        os.remove(probe)

    branches = [line.split(':', 1)[1] for line in proc.stdout.splitlines()
                if line.startswith('CALLED:')]
    branches = [b for b in branches if b != 'none']
    if not branches:
        raise AssertionError(
            'the entry point reached neither branch.\n'
            f'stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}'
        )
    return branches[0], proc


class StagedTreeCase(unittest.TestCase):
    """Stages the runtime code into a throwaway directory for each test."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='novamart-runtime-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.staged = os.path.join(self.tmp, 'runtime')
        stage_into(self.staged)

    def staged_path(self, *parts):
        return os.path.join(self.staged, *parts)


class TestRuntimeStaging(unittest.TestCase):
    """
    Lock in defect 1: the staged package must contain every project package
    the entry point imports, and nothing that does not belong in it.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='novamart-runtime-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.staged = os.path.join(self.tmp, 'runtime')
        stage_into(self.staged)

    def staged_path(self, *parts):
        return os.path.join(self.staged, *parts)

    def test_stage_copies_the_five_packages_the_entry_point_imports(self):
        """Each package the entry point imports is staged, with __init__.py."""
        for package in PROJECT_PACKAGES:
            with self.subTest(package=package):
                self.assertTrue(
                    os.path.isfile(self.staged_path(package, '__init__.py')),
                    f'{package}/ was not staged into build/runtime, so the '
                    f'deployed runtime cannot import it',
                )

    def test_stage_copies_every_package_listed_in_the_module_constants(self):
        """RUNTIME_PACKAGE_DIRS and the tree on disk cannot drift apart."""
        self.assertEqual(sorted(agentcore_cli.RUNTIME_PACKAGE_DIRS),
                         sorted(PROJECT_PACKAGES))
        for package in agentcore_cli.RUNTIME_PACKAGE_DIRS:
            self.assertTrue(os.path.isdir(os.path.join(SRC_DIR, package)),
                            f'{package} is staged but does not exist in src/')

    def test_stage_copies_every_project_module_the_entry_point_imports(self):
        """
        Every first level project import in the entry point, and in every
        staged module, resolves inside the staged tree.
        """
        known = project_module_names()
        unresolved = set()
        for root, _dirs, files in os.walk(self.staged):
            for name in files:
                if not name.endswith('.py'):
                    continue
                path = os.path.join(root, name)
                for imported in top_level_imports(path):
                    if imported not in known:
                        continue          # third party, resolved by pip
                    if not (
                        os.path.isfile(self.staged_path(imported + '.py'))
                        or os.path.isdir(self.staged_path(imported))
                    ):
                        unresolved.add(f'{name} imports {imported}')
        self.assertEqual(unresolved, set(),
                         'project modules imported by the runtime package are '
                         'missing from build/runtime')

    def test_staged_tree_imports_on_its_own(self):
        """
        The strongest form of the guard: a fresh interpreter started inside
        the staged directory, with no src/ on the path, can import the entry
        point. This is the assertion that would have caught the
        ModuleNotFoundError.
        """
        env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
        env['PYTHONIOENCODING'] = 'utf-8'
        script = 'import sys\nsys.path.insert(0, ".")\nimport agent_orchestrator\nprint("IMPORT OK")\n'
        proc = subprocess.run(
            [sys.executable, '-c', script], cwd=self.staged, env=env,
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=300,
        )
        self.assertIn('IMPORT OK', proc.stdout,
                      f'the staged package cannot be imported on its own.\n'
                      f'stderr:\n{proc.stderr}')

    def test_stage_writes_the_entry_point_and_the_serve_marker(self):
        """The runtime needs the entry point plus the marker beside it."""
        self.assertTrue(os.path.isfile(self.staged_path('agent_orchestrator.py')))
        self.assertTrue(os.path.isfile(self.staged_path(agentcore_cli.RUNTIME_MARKER)),
                        'the .agentcore-runtime marker is what switches the '
                        'entry point into serve mode')

    def test_stage_writes_every_declared_project_file(self):
        """Each file in RUNTIME_PROJECT_FILES lands in the staged directory."""
        for path in agentcore_cli.RUNTIME_PROJECT_FILES:
            with self.subTest(file=os.path.basename(path)):
                self.assertTrue(os.path.isfile(self.staged_path(os.path.basename(path))))

    def test_stage_excludes_pycache_and_compiled_files(self):
        """Stale bytecode from the host must not ship to the runtime."""
        offenders = []
        for root, dirs, files in os.walk(self.staged):
            for name in dirs + files:
                if name in agentcore_cli.RUNTIME_EXCLUDE_DIRS or name.endswith('.pyc'):
                    offenders.append(os.path.relpath(os.path.join(root, name), self.staged))
        self.assertEqual(offenders, [],
                         'cache directories must not be staged into the runtime')

    def test_stage_removes_stale_files_from_a_previous_stage(self):
        """Staging is a clean build, so an old file cannot survive in it."""
        stale = self.staged_path('left_over_from_last_deploy.py')
        with open(stale, 'w', encoding='utf-8') as fh:
            fh.write('# stale\n')
        cache = self.staged_path('workflow', '__pycache__')
        os.makedirs(cache, exist_ok=True)

        stage_into(self.staged)

        self.assertFalse(os.path.exists(stale),
                         'a leftover file from an earlier stage is still shipped')
        self.assertFalse(os.path.exists(cache),
                         'a leftover __pycache__ from an earlier stage is still shipped')

    def test_stage_writes_requirements_without_windows_only_pins(self):
        """
        requirements.txt is what the toolkit installs from. A pywin32 pin
        there has no manylinux wheel and the Linux build fails.
        """
        path = self.staged_path('requirements.txt')
        self.assertTrue(os.path.isfile(path),
                        'requirements.txt is required so uv resolves markers '
                        'against the target platform instead of the host')
        with open(path, encoding='utf-8') as fh:
            body = fh.read()
        for requirement in agentcore_cli.RUNTIME_REQUIREMENTS:
            self.assertIn(requirement, body)
        self.assertNotIn('pywin32', body.lower())

    def test_stage_raises_when_a_project_file_is_missing(self):
        """A missing input fails loudly instead of deploying a broken zip."""
        with mock.patch.object(agentcore_cli, 'RUNTIME_PROJECT_FILES',
                               [os.path.join(self.tmp, 'not_here.py')]):
            with self.assertRaises(FileNotFoundError) as caught:
                agentcore_cli.stage_runtime_code()
        self.assertIn('not_here.py', str(caught.exception))


class TestEntryPointServeDispatch(StagedTreeCase):
    """
    Lock in defect 2: the entry point must serve HTTP when AgentCore starts
    it with no arguments, and fall through to the CLI in every other case.
    """

    def test_serves_http_when_started_with_no_arguments(self):
        """No argv plus the marker present means serve mode."""
        branch, proc = run_entrypoint(self.staged)
        self.assertEqual(branch, 'serve',
                         f'the deployed runtime must serve, not print CLI usage.\n'
                         f'stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}')

    def test_falls_through_to_the_cli_when_the_marker_is_missing(self):
        """A bare local run has no marker, so the CLI usage text is right."""
        os.remove(self.staged_path(agentcore_cli.RUNTIME_MARKER))
        branch, proc = run_entrypoint(self.staged)
        self.assertEqual(branch, 'cli', f'stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}')

    def test_falls_through_to_the_cli_when_a_command_is_given(self):
        """Even inside the runtime package, an explicit command is a CLI run."""
        branch, proc = run_entrypoint(self.staged, argv=['deploy'])
        self.assertEqual(branch, 'cli', f'stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}')


class DeployCase(unittest.TestCase):
    """deploy_to_agentcore_runtime with the CLI and AWS calls stubbed out."""

    def setUp(self):
        self.calls = []

        def _record(name, result=None):
            def _fn(*args, **kwargs):
                self.calls.append((name, args, kwargs))
                return result
            return _fn

        self.stage_stub = _record('stage_runtime_code')
        self.configure_stub = _record('configure_runtime', {'name': 'agentcore_runtime'})
        self.deploy_stub = _record('deploy')
        self.wait_stub = _record('wait_for_runtime_ready', 'READY')
        self.version_stub = _record('cli_version', '0.3.12 (python toolkit)')
        self.path_stub = _record('cli_path', 'agentcore')

        self.arn = 'arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/' \
                   'novamart_agentcore_runtime-ABCDEFGHIJ'

        self.patches = [
            mock.patch.object(agentcore_cli, 'stage_runtime_code', self.stage_stub),
            mock.patch.object(agentcore_cli, 'configure_runtime', self.configure_stub),
            mock.patch.object(agentcore_cli, 'deploy', self.deploy_stub),
            mock.patch.object(agentcore_cli, 'deployed_runtime_arn',
                              _record('deployed_runtime_arn', self.arn)),
            mock.patch.object(agentcore_cli, 'cli_version', self.version_stub),
            mock.patch.object(agentcore_cli, 'cli_path', self.path_stub),
            mock.patch.object(runtime_deploy, 'wait_for_runtime_ready', self.wait_stub),
            mock.patch('boto3.client', return_value=mock.Mock()),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.config_patch = config_values(
            ACCOUNT_ID=SENTINEL_ACCOUNT_ID,
            AGENT_LOG_GROUP=SENTINEL_LOG_GROUP,
            AGENTCORE_ROLE_ARN=SENTINEL_ROLE_ARN,
            **SENTINEL_KB_IDS,
        )
        self.config_patch.__enter__()
        self.addCleanup(self.config_patch.__exit__, None, None, None)

    def run_deploy(self, guardrail_id='gr-abc123', guardrail_version='3'):
        return runtime_deploy.deploy_to_agentcore_runtime(
            orchestrator_agent=mock.Mock(),
            guardrail_id=guardrail_id,
            guardrail_version=guardrail_version,
        )

    @property
    def configure_call(self):
        for name, _args, kwargs in self.calls:
            if name == 'configure_runtime':
                return kwargs
        self.fail('configure_runtime was never called')

    def call_names(self):
        return [name for name, _args, _kwargs in self.calls]


class TestDeployToAgentCoreRuntime(DeployCase):
    """
    The deploy pipeline: the runtime environment, the runtime settings, and
    the order the steps happen in.
    """

    def test_builds_the_env_vars_the_graded_suite_requires(self):
        """The runtime gets all eight keys, with the project's real values."""
        self.run_deploy(guardrail_id='gr-abc123', guardrail_version='3')
        env = self.configure_call['env_vars']
        self.assertEqual(
            set(env), set(REQUIRED_RUNTIME_ENV_KEYS),
            f'the runtime environment keys drifted from the graded suite: {sorted(env)}',
        )
        self.assertEqual(env['AWS_REGION'], config.AWS_REGION)
        self.assertEqual(env['PROJECT_NAME'], config.PROJECT_NAME)
        self.assertEqual(env['AGENT_LOG_GROUP'], SENTINEL_LOG_GROUP)
        self.assertEqual(env['GUARDRAIL_ID'], 'gr-abc123')
        self.assertEqual(env['GUARDRAIL_VERSION'], '3')
        for key, value in SENTINEL_KB_IDS.items():
            self.assertEqual(env[key], value,
                             f'{key} must be passed through from config')

    def test_env_var_keys_cover_every_key_the_graded_suite_checks(self):
        """
        Read the required keys out of the graded suite itself, so a key added
        there cannot be silently left out of the runtime.
        """
        required = graded_suite_env_keys()
        self.assertEqual(set(required), set(REQUIRED_RUNTIME_ENV_KEYS),
                         'this suite and the graded suite disagree about the '
                         'required runtime env vars; update one of them')
        self.run_deploy()
        missing = set(required) - set(self.configure_call['env_vars'])
        self.assertEqual(missing, set(),
                         f'the deploy does not set {sorted(missing)} on the runtime')

    def test_configures_public_networking_http_and_the_foundation_role(self):
        """PUBLIC, HTTP and the CloudFormation execution role, not a new one."""
        self.run_deploy()
        self.assertEqual(self.configure_call['network_mode'], 'PUBLIC')
        self.assertEqual(self.configure_call['protocol'], 'HTTP')
        self.assertEqual(self.configure_call['execution_role_arn'],
                         SENTINEL_ROLE_ARN)

    def test_returns_the_deployed_arn(self):
        """The function hands back the ARN the CLI reported."""
        self.assertEqual(self.run_deploy(), self.arn)

    def test_waits_for_the_runtime_to_be_ready(self):
        """The wait uses the runtime id from the deployed ARN."""
        self.run_deploy()
        waits = [args for name, args, _kwargs in self.calls
                 if name == 'wait_for_runtime_ready']
        self.assertEqual(len(waits), 1, 'the deploy must wait for READY once')
        self.assertEqual(waits[0][1], self.arn.split('/')[-1])

    def test_stages_then_configures_then_deploys(self):
        """The order matters: stage the code, write the config, then deploy."""
        self.run_deploy()
        order = [name for name, _a, _k in self.calls
                 if name in ('stage_runtime_code', 'configure_runtime', 'deploy',
                             'deployed_runtime_arn', 'wait_for_runtime_ready')]
        first = {name: order.index(name) for name in set(order)}
        self.assertLess(first['stage_runtime_code'], first['configure_runtime'],
                        'the code must be staged before the config is written')
        self.assertLess(first['configure_runtime'], first['deploy'],
                        'the config must be written before the CLI deploys')
        self.assertEqual(order[-1], 'wait_for_runtime_ready',
                         'the deploy must wait for READY after deploying')
        self.assertEqual(order[-2], 'deployed_runtime_arn',
                         'the ARN must be read back after the deploy')
        self.assertEqual(order[0], 'deployed_runtime_arn',
                         'the previous ARN is read before anything is changed')


class TestProjectConfigFiles(unittest.TestCase):
    """
    `configure_runtime()` writes two config files that must agree, and
    `yaml_runtime_env_vars()` is what the deploy hands to the CLI.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='novamart-config-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.json_path = os.path.join(self.tmp, 'agentcore.json')
        self.yaml_path = os.path.join(self.tmp, '.bedrock_agentcore.yaml')
        with open(self.json_path, 'w', encoding='utf-8') as fh:
            json.dump({'name': 'novamart', 'version': 1,
                       'runtimes': [{'name': config.AGENTCORE_AGENT_NAME,
                                     'build': 'CodeZip'}]}, fh, indent=2)
        self.patches = [
            mock.patch.object(agentcore_cli, 'CONFIG_PATH', self.json_path),
            mock.patch.object(agentcore_cli, 'YAML_CONFIG_PATH', self.yaml_path),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def read_yaml(self):
        import yaml
        with open(self.yaml_path, encoding='utf-8') as fh:
            return yaml.safe_load(fh)

    def read_json(self):
        with open(self.json_path, encoding='utf-8') as fh:
            return json.load(fh)

    def test_configure_runtime_sets_the_build_settings(self):
        """The CLI must package build/runtime/ with the entry point on top."""
        rt = agentcore_cli.configure_runtime(network_mode='PUBLIC', protocol='HTTP')
        self.assertEqual(rt['entrypoint'], agentcore_cli.RUNTIME_ENTRYPOINT)
        self.assertEqual(rt['codeLocation'], 'build/runtime/')
        self.assertEqual(rt['runtimeVersion'], agentcore_cli.RUNTIME_PYTHON)
        self.assertEqual(rt['build'], 'CodeZip')
        self.assertEqual(rt['instrumentation'], {'enableOtel': False})

    def test_configure_runtime_merges_env_vars_and_overwrites_by_name(self):
        """Existing keys are replaced, new keys are added, nothing is lost."""
        agentcore_cli.configure_runtime(env_vars={'PROJECT_NAME': 'first',
                                                   'GUARDRAIL_ID': 'gr-1'})
        agentcore_cli.configure_runtime(env_vars={'PROJECT_NAME': 'second',
                                                   'GUARDRAIL_VERSION': '1'})
        env = agentcore_cli.runtime_env_vars()
        self.assertEqual(env, {'PROJECT_NAME': 'second',
                               'GUARDRAIL_ID': 'gr-1',
                               'GUARDRAIL_VERSION': '1'})

    def test_yaml_runtime_env_vars_drops_empty_values(self):
        """
        The three Knowledge Base IDs are empty until the Knowledge Bases
        feature lands. Empty values are skipped so the CLI is not handed
        `--env RETURNS_KB_ID=` .
        """
        agentcore_cli.configure_runtime(env_vars={
            'AWS_REGION': config.AWS_REGION,
            'PROJECT_NAME': config.PROJECT_NAME,
            'RETURNS_KB_ID': '',
            'SHIPPING_KB_ID': '',
            'WARRANTY_KB_ID': '',
            'AGENT_LOG_GROUP': config.AGENT_LOG_GROUP,
            'GUARDRAIL_ID': 'gr-abc123',
            'GUARDRAIL_VERSION': '1',
        })
        env = agentcore_cli.yaml_runtime_env_vars()
        self.assertEqual(set(env), set(MUST_HAVE_ENV_KEYS),
                         'the CLI is being handed the wrong set of env vars')
        for value in env.values():
            self.assertNotEqual(value, '')
        for key in PENDING_KB_ENV_KEYS:
            self.assertNotIn(key, env,
                             f'{key} is still empty, so it must not be passed '
                             f'to the CLI until the Knowledge Bases exist')

    def test_the_two_config_files_agree(self):
        """
        `agentcore/agentcore.json` and `.bedrock_agentcore.yaml` only agree
        because configure_runtime() writes both. A setting that drifts between
        them is a silent break.
        """
        agentcore_cli.configure_runtime(
            env_vars={'GUARDRAIL_ID': 'gr-abc123', 'GUARDRAIL_VERSION': '1'},
            network_mode='PUBLIC', protocol='HTTP',
            execution_role_arn='arn:aws:iam::000000000000:role/test-role',
        )
        rt = self.read_json()['runtimes'][0]
        agent = self.read_yaml()['agents'][config.AGENTCORE_RUNTIME_NAME]
        aws = agent['aws']
        pairs = [
            ('entrypoint', rt['entrypoint'], agent['entrypoint']),
            ('runtime version', rt['runtimeVersion'], agent['runtime_type']),
            ('code location', rt['codeLocation'].rstrip('/'), agent['source_path'].rstrip('/')),
            ('network mode', rt['networkMode'], aws['network_configuration']['network_mode']),
            ('protocol', rt['protocol'], aws['protocol_configuration']['server_protocol']),
            ('execution role', rt['executionRoleArn'], aws['execution_role']),
        ]
        for label, from_json, from_yaml in pairs:
            with self.subTest(setting=label):
                self.assertEqual(from_json, from_yaml,
                                 f'{label} differs between agentcore.json and '
                                 f'.bedrock_agentcore.yaml')
        self.assertEqual(self.read_yaml()['default_agent'],
                         config.AGENTCORE_RUNTIME_NAME)

    def test_the_live_config_files_agree(self):
        """
        The same check against the files this project has actually deployed
        from, so a hand edit that desyncs them is caught.
        """
        if not os.path.isfile(REAL_CONFIG_PATH) or \
                not os.path.isfile(REAL_YAML_CONFIG_PATH):
            self.skipTest('the project config files have not been generated yet')
        with open(REAL_CONFIG_PATH, encoding='utf-8') as fh:
            spec = json.load(fh)
        import yaml
        with open(REAL_YAML_CONFIG_PATH, encoding='utf-8') as fh:
            yaml_spec = yaml.safe_load(fh)
        rt = agentcore_cli.runtime_spec(spec)
        agent = yaml_spec['agents'][config.AGENTCORE_RUNTIME_NAME]
        aws = agent['aws']
        self.assertEqual(rt['entrypoint'], agent['entrypoint'])
        self.assertEqual(rt['runtimeVersion'], agent['runtime_type'])
        self.assertEqual(rt['codeLocation'].rstrip('/'), agent['source_path'].rstrip('/'))
        self.assertEqual(rt['networkMode'], aws['network_configuration']['network_mode'])
        self.assertEqual(rt['protocol'], aws['protocol_configuration']['server_protocol'])
        self.assertEqual(rt['executionRoleArn'], aws['execution_role'])

    def test_run_reports_the_failing_command(self):
        """A non zero exit from the CLI raises with the command named."""
        failure = subprocess.CompletedProcess(args=['agentcore', 'deploy'],
                                              returncode=2, stdout='', stderr='boom')
        with mock.patch.object(agentcore_cli, 'cli_path', return_value='agentcore'), \
                mock.patch('subprocess.run', return_value=failure):
            with self.assertRaises(RuntimeError) as caught:
                agentcore_cli.run('deploy', capture=True)
        message = str(caught.exception)
        self.assertIn('agentcore deploy', message)
        self.assertIn('exit 2', message)
        self.assertIn('boom', message)

    def test_run_passes_the_project_region_to_the_cli(self):
        """The CLI must deploy into the project region."""
        captured = {}

        def _capture(cmd, **kwargs):
            captured['cmd'] = cmd
            captured['env'] = kwargs.get('env', {})
            return subprocess.CompletedProcess(args=cmd, returncode=0,
                                               stdout='', stderr='')

        with mock.patch.object(agentcore_cli, 'cli_path', return_value='agentcore'), \
                mock.patch('subprocess.run', _capture):
            agentcore_cli.run('deploy')
        self.assertEqual(captured['cmd'][:2], ['agentcore', 'deploy'])
        self.assertEqual(captured['env']['AWS_REGION'], config.AWS_REGION)
        self.assertEqual(captured['env']['AWS_DEFAULT_REGION'], config.AWS_REGION)
        self.assertEqual(captured['env']['AGENTCORE_SUPPRESS_RECOMMENDATION'], '1')


class _FakeBedrock:
    """A stand in for the Bedrock control plane, at the boto3 boundary."""

    def __init__(self, pages=None, versions=(), created_id='gr-new'):
        self.pages = list(pages or [[]])
        self.versions = set(versions)
        self.created_id = created_id
        self.calls = []
        self.create_kwargs = None
        self.publish_kwargs = None

    def get_paginator(self, operation):
        self.calls.append(('get_paginator', operation))
        pages = self.pages

        class _Paginator:
            def paginate(self, **_kwargs):
                for page in pages:
                    yield {'guardrails': page}

        return _Paginator()

    def get_guardrail(self, guardrailIdentifier, guardrailVersion):
        self.calls.append(('get_guardrail', guardrailVersion))
        if guardrailVersion.isdigit() and int(guardrailVersion) in self.versions:
            return {'id': guardrailIdentifier, 'version': guardrailVersion,
                    'status': 'READY'}
        raise ClientError(
            {'Error': {'Code': 'ResourceNotFoundException',
                       'Message': f'no version {guardrailVersion}'}},
            'GetGuardrail')

    def create_guardrail(self, **kwargs):
        self.calls.append(('create_guardrail',))
        self.create_kwargs = kwargs
        self.pages[-1].append({'name': kwargs['name'], 'id': self.created_id})
        return {'guardrailId': self.created_id, 'version': 'DRAFT'}

    def create_guardrail_version(self, **kwargs):
        self.calls.append(('create_guardrail_version',))
        self.publish_kwargs = kwargs
        number = (max(self.versions) + 1) if self.versions else 1
        self.versions.add(number)
        return {'version': str(number)}

    def names(self):
        return [call[0] for call in self.calls]


class TestCreateGuardrail(unittest.TestCase):
    """
    Lock in defect 3: create_guardrail() reuses an existing guardrail and
    reports its published version instead of failing or duplicating.
    """

    def run_with(self, bedrock):
        with mock.patch('boto3.client', return_value=bedrock):
            return guardrail_deploy.create_guardrail()

    def test_reuses_an_existing_guardrail_and_returns_its_published_version(self):
        """The newest published version is probed out, not assumed to be 1."""
        bedrock = _FakeBedrock(
            pages=[[{'name': 'someone-elses-guardrail', 'id': 'gr-other'}],
                   [{'name': config.GUARDRAIL_NAME, 'id': 'gr-abc123'}]],
            versions={1, 2, 3},
        )
        guardrail_id, version = self.run_with(bedrock)
        self.assertEqual(guardrail_id, 'gr-abc123')
        self.assertEqual(version, '3')
        self.assertNotIn('create_guardrail', bedrock.names(),
                         'an existing guardrail must not be created again')

    def test_finds_the_guardrail_across_every_page(self):
        """list_guardrails is paginated, so the search cannot stop at page 1."""
        bedrock = _FakeBedrock(
            pages=[[{'name': 'a', 'id': 'gr-a'}],
                   [{'name': 'b', 'id': 'gr-b'}],
                   [{'name': config.GUARDRAIL_NAME, 'id': 'gr-deep'}]],
            versions={1},
        )
        guardrail_id, _version = self.run_with(bedrock)
        self.assertEqual(guardrail_id, 'gr-deep')

    def test_publishes_the_draft_when_no_published_version_exists(self):
        """A guardrail that exists but was never versioned gets one version."""
        bedrock = _FakeBedrock(pages=[[{'name': config.GUARDRAIL_NAME, 'id': 'gr-abc'}]],
                               versions=set())
        guardrail_id, version = self.run_with(bedrock)
        self.assertEqual(guardrail_id, 'gr-abc')
        self.assertEqual(version, '1')
        self.assertNotIn('create_guardrail', bedrock.names())
        self.assertEqual(bedrock.publish_kwargs['guardrailIdentifier'], 'gr-abc')

    def test_creates_the_guardrail_with_all_four_policy_blocks(self):
        """A first run builds the rubric's content, PII, topic and word policy."""
        bedrock = _FakeBedrock(pages=[[{'name': 'unrelated', 'id': 'gr-other'}]])
        guardrail_id, version = self.run_with(bedrock)
        self.assertEqual(guardrail_id, 'gr-new')
        self.assertEqual(version, '1')

        kwargs = bedrock.create_kwargs
        self.assertEqual(kwargs['name'], config.GUARDRAIL_NAME)
        filters = {f['type']: f['inputStrength']
                   for f in kwargs['contentPolicyConfig']['filtersConfig']}
        self.assertEqual(filters, {'SEXUAL': 'HIGH', 'VIOLENCE': 'HIGH',
                                   'HATE': 'HIGH', 'INSULTS': 'MEDIUM',
                                   'MISCONDUCT': 'MEDIUM'})
        pii = {p['type']: p['action']
               for p in kwargs['sensitiveInformationPolicyConfig']['piiEntitiesConfig']}
        self.assertEqual(pii, {'CREDIT_DEBIT_CARD_NUMBER': 'BLOCK',
                               'US_SOCIAL_SECURITY_NUMBER': 'BLOCK',
                               'EMAIL': 'ANONYMIZE', 'PHONE': 'ANONYMIZE'})
        topics = {t['name'] for t in kwargs['topicPolicyConfig']['topicsConfig']}
        self.assertEqual(topics, {'CompetitorProducts', 'PricingNegotiations',
                                  'LegalThreats'})
        self.assertTrue(all(t['type'] == 'DENY'
                            for t in kwargs['topicPolicyConfig']['topicsConfig']))
        self.assertEqual(kwargs['wordPolicyConfig']['managedWordListsConfig'],
                         [{'type': 'PROFANITY'}])

    def test_a_second_run_creates_no_duplicate(self):
        """Running the deploy twice leaves exactly one guardrail."""
        bedrock = _FakeBedrock(pages=[[]])
        first_id, first_version = self.run_with(bedrock)
        second_id, second_version = self.run_with(bedrock)
        self.assertEqual(first_id, second_id)
        self.assertEqual(first_version, second_version)
        self.assertEqual(bedrock.names().count('create_guardrail'), 1,
                         'a duplicate guardrail was created on the second run')

    def test_latest_published_version_is_none_when_only_a_draft_exists(self):
        """No numbered version resolves, so there is nothing to report."""
        bedrock = _FakeBedrock()
        self.assertIsNone(guardrail_deploy._latest_published_version(bedrock, 'gr-abc'))

    def test_latest_published_version_returns_a_numeric_string(self):
        """The caller gets a string, because it goes into an env var."""
        bedrock = _FakeBedrock(versions={1, 2, 4})
        self.assertEqual(guardrail_deploy._latest_published_version(bedrock, 'gr-abc'), '2')

    def test_latest_published_version_stops_at_the_first_gap(self):
        """Version numbers are sequential, so the first gap ends the scan."""
        bedrock = _FakeBedrock(versions={1, 2, 4})
        guardrail_deploy._latest_published_version(bedrock, 'gr-abc', max_probe=10)
        probed = [arg for name, arg in bedrock.calls if name == 'get_guardrail']
        self.assertEqual(probed, ['1', '2', '3'])

    def test_find_guardrail_returns_none_when_it_is_absent(self):
        """No match is None, not an empty string and not an exception."""
        bedrock = _FakeBedrock(pages=[[{'name': 'other', 'id': 'gr-other'}]])
        self.assertIsNone(guardrail_deploy._find_guardrail(bedrock, 'missing'))


class TestGuardrailFromEnvironment(unittest.TestCase):
    """
    The acceptance criterion: inside the runtime the guardrail arrives only
    through environment variables.
    """

    class _FakeModel:
        def __init__(self):
            self.updates = []

        def update_config(self, **kwargs):
            self.updates.append(kwargs)

    class _FakeAgent:
        def __init__(self):
            self.model = TestGuardrailFromEnvironment._FakeModel()

    def test_the_env_guardrail_is_attached_to_every_agent(self):
        """GUARDRAIL_ID and GUARDRAIL_VERSION from the env reach all models."""
        agents = [self._FakeAgent() for _ in range(5)]
        with mock.patch.dict(os.environ,
                             {'GUARDRAIL_ID': 'gr-abc123', 'GUARDRAIL_VERSION': '4'}):
            _apply_guardrail(agents)
        for agent in agents:
            self.assertEqual(agent.model.updates,
                             [{'guardrail_id': 'gr-abc123',
                               'guardrail_version': '4'}])

    def test_nothing_is_attached_when_no_guardrail_is_configured(self):
        """A runtime without a guardrail leaves the models untouched."""
        agents = [self._FakeAgent() for _ in range(3)]
        with mock.patch.dict(os.environ, {'GUARDRAIL_ID': '', 'GUARDRAIL_VERSION': ''}):
            _apply_guardrail(agents)
        for agent in agents:
            self.assertEqual(agent.model.updates, [])


@unittest.skipUnless(config.AGENTCORE_RUNTIME_ARN,
                     'AGENTCORE_RUNTIME_ARN is not set in .env')
class TestDeployedRuntime(unittest.TestCase):
    """
    Control plane reads against the real deployed runtime. No model calls,
    so these are cheap.
    """

    def setUp(self):
        self.control = __import__('boto3').client(
            'bedrock-agentcore-control', region_name=config.AWS_REGION)
        self.runtime_id = config.AGENTCORE_RUNTIME_ARN.split('/')[-1]
        self.runtime = self.control.get_agent_runtime(agentRuntimeId=self.runtime_id)
        self.artifact = self.runtime['agentRuntimeArtifact']['codeConfiguration']

    def test_the_env_file_holds_a_real_runtime_arn(self):
        """Done when: `.env` contains AGENTCORE_RUNTIME_ARN."""
        self.assertRegex(
            config.AGENTCORE_RUNTIME_ARN,
            r'^arn:aws:bedrock-agentcore:[a-z0-9-]+:\d{12}:runtime/[A-Za-z0-9_-]+$',
        )
        self.assertEqual(self.runtime['agentRuntimeName'],
                         config.AGENTCORE_RUNTIME_NAME)

    def test_the_deployed_arn_lookup_finds_the_same_runtime(self):
        """deployed_runtime_arn() agrees with what is in .env."""
        self.assertEqual(agentcore_cli.deployed_runtime_arn(),
                         config.AGENTCORE_RUNTIME_ARN)

    def test_the_runtime_is_ready_public_and_http(self):
        """The same three facts the graded suite checks."""
        self.assertEqual(self.runtime['status'], 'READY')
        self.assertEqual(self.runtime['networkConfiguration']['networkMode'], 'PUBLIC')
        self.assertEqual(self.runtime['protocolConfiguration']['serverProtocol'], 'HTTP')

    def test_the_runtime_carries_the_required_env_vars(self):
        """
        Every required key except the three Knowledge Base IDs, which stay
        empty until that feature lands.
        """
        env = self.runtime.get('environmentVariables', {}) or {}
        missing = [k for k in MUST_HAVE_ENV_KEYS if not env.get(k)]
        self.assertEqual(missing, [],
                         f'the deployed runtime is missing {missing}')
        self.assertEqual(env['GUARDRAIL_ID'], config.GUARDRAIL_ID)
        self.assertEqual(env['GUARDRAIL_VERSION'], config.GUARDRAIL_VERSION)
        self.assertEqual(env['AWS_REGION'], config.AWS_REGION)
        self.assertEqual(env['PROJECT_NAME'], config.PROJECT_NAME)
        self.assertEqual(env['AGENT_LOG_GROUP'], config.AGENT_LOG_GROUP)

    def test_the_deployed_entry_point_is_the_staged_one(self):
        """The runtime is started from the staged entry point file."""
        self.assertEqual(self.artifact['entryPoint'],
                         [agentcore_cli.RUNTIME_ENTRYPOINT])

    def test_the_deployed_artifact_was_built_for_this_package(self):
        """
        The runtime runs the same Python version and the same entry point the
        staging step writes, so a change to either cannot slip through.
        """
        self.assertEqual(self.artifact['runtime'], agentcore_cli.RUNTIME_PYTHON)
        self.assertIn('s3', self.artifact['code'],
                      'the runtime should be a direct code deployment from S3')


@unittest.skipUnless(LIVE_INVOKE, 'set RUN_LIVE_INVOKE=1 to run the live invoke')
class TestLiveInvoke(unittest.TestCase):
    """
    The one assertion that catches a broken runtime: a real invocation must
    come back with a `result`. It costs a real model call and takes about
    30 seconds, so it is off by default.
    """

    def test_a_live_invoke_returns_a_result(self):
        """A real order status question is answered end to end."""
        from serving.invoke import invoke_agent

        response = invoke_agent(
            session_id='test-live-1',
            customer_id='CUST-001',
            user_message='Can you check the status of my order ORD-27176?',
        )
        self.assertIn('result', response,
                      f'the runtime answered without a result: {response}')
        self.assertIsInstance(response['result'], str)
        self.assertTrue(response['result'].strip(),
                        'the runtime returned an empty answer')
        self.assertEqual(response.get('session_id'), 'test-live-1')
        self.assertEqual(response.get('customer_id'), 'CUST-001')
        lowered = response['result'].lower()
        self.assertIn('delivered', lowered,
                      'the answer does not report the delivered order status')
        self.assertIn('149.99', response['result'],
                      'the answer does not include the order total')


class TestRuntimePackagingCompleteness(unittest.TestCase):
    """Every src/ package that staged code can import must be staged.

    Regression test for the cold-start outage where `telemetry/` was
    imported at module scope (agent_observability, serving.serve,
    workflow.graph) but absent from RUNTIME_PACKAGE_DIRS, so every
    invoke died with `ModuleNotFoundError: No module named 'telemetry'`
    before the 30s init budget. Runs offline.
    """

    def test_all_local_packages_are_staged(self):
        src_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
        discovered = sorted(
            name for name in os.listdir(src_dir)
            if os.path.isdir(os.path.join(src_dir, name))
            and os.path.isfile(os.path.join(src_dir, name, '__init__.py'))
        )
        missing = [p for p in discovered if p not in agentcore_cli.RUNTIME_PACKAGE_DIRS]
        self.assertEqual(
            missing, [],
            f"src/ packages missing from RUNTIME_PACKAGE_DIRS {agentcore_cli.RUNTIME_PACKAGE_DIRS}: "
            f"{missing} - the deployed runtime would fail at import with ModuleNotFoundError",
        )

    def test_staged_tree_imports_cleanly(self):
        staged = agentcore_cli.stage_runtime_code()
        for pkg in agentcore_cli.RUNTIME_PACKAGE_DIRS:
            self.assertTrue(
                os.path.isdir(os.path.join(staged, pkg)),
                f"staged package '{pkg}' missing under {staged}",
            )


if __name__ == '__main__':
    unittest.main(verbosity=2)
