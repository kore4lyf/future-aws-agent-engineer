# =============================================================================
# HR Onboarding — Multi-Agent Orchestration Demo
# =============================================================================
# Demonstrates three orchestration patterns in a single workflow:
#   Phase 1 (Sequential):   account must exist before manager assignment
#   Phase 2 (Parallel):     laptop, email, building access run concurrently
#   Phase 3 (Conditional): Python if/elif routes to engineering or sales
# ============================================================================

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from strands import Agent, tool
from strands.models import BedrockModel

load_dotenv()

# --- Bedrock configuration ---
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
NOVA_LITE_MODEL = os.environ.get("NOVA_LITE_MODEL", "amazon.nova-lite-v1:0")

# --- Test employee roster ---
# EMP-001 and EMP-002 exercise the Engineering/Sales conditional branches.
# EMP-003 (Carol) has simulate_failure=True to demonstrate retry/backoff.
EMPLOYEES = [
    {"id": "EMP-001", "name": "Alice", "department": "Engineering", "role": "Senior Backend Engineer"},
    {"id": "EMP-002", "name": "Bob", "department": "Sales", "role": "Account Executive"},
    {"id": "EMP-003", "name": "Carol", "department": "Engineering", "role": "DevOps Lead", "simulate_failure": True},
]

# --- Shared workflow state ---
# Each agent's tool writes its result here so downstream agents can read it.
workflow_state = {}


def clean_response(text: str) -> str:
    """Strip <thinking> tags from model output."""
    return re.sub(r"<thinking>.*?</thinking>", "", str(text), flags=re.DOTALL).strip()


def run_agent_with_retry(agent_builder, prompt: str, max_retries: int = 3) -> str:
    """Wrap an agent invocation with exponential backoff (1s, 2s, 4s).

    Catches transient Bedrock errors (e.g., ConnectionError on EMP-003's laptop)
    and retries without crashing the entire workflow.
    """
    for attempt in range(max_retries):
        try:
            agent = agent_builder()
            result = agent(prompt)
            return clean_response(result)
        except Exception as error:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"[Retry {attempt + 1}/{max_retries}] ({error.__class__.__name__}), waiting {wait}s...")
                time.sleep(wait)
                continue
            print(f"[Failed] ({error.__class__.__name__}) after {max_retries} attempts")
            raise


def _get_employee(employee_id: str) -> dict:
    """Look up an employee dict by ID from the EMPLOYEES roster."""
    return next(e for e in EMPLOYEES if e["id"] == employee_id)


# ============================================================================
# PHASE 1 — SEQUENTIAL AGENTS (account → manager, order matters)
# ============================================================================

def build_account_creator() -> Agent:
    """Create an employee account. Writes to workflow_state["account"].

    This runs first so the manager assigner can reference the account ID.
    """
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    system_prompt = """You are an account creation agent. Your ONLY job:
1. Call create_account with the employee_id
2. Report: Account created for <name> (ID: <employee_id>)
Do NOT add any other commentary."""

    @tool
    def create_account(employee_id: str) -> str:
        # Look up employee and build account record
        emp = _get_employee(employee_id)
        result = {"account_id": f"ACC-{employee_id}", "name": emp["name"], "employee_id": employee_id}
        # Write to shared state for downstream agents
        workflow_state["account"] = result
        return json.dumps(result, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[create_account])


def build_manager_assigner() -> Agent:
    """Assign a manager based on department. Writes to workflow_state["manager"].

    Depends on the account existing first (Phase 1 sequential dependency).
    """
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    system_prompt = """You are a manager assignment agent. Your ONLY job:
1. Call assign_manager with the employee_id
2. Report: Manager assigned to <name> (ID: <employee_id>)
Do NOT add any other commentary."""

    @tool
    def assign_manager(employee_id: str) -> str:
        emp = _get_employee(employee_id)
        # Department-based manager lookup
        manager_map = {"Engineering": "CTO", "Sales": "VP of Sales"}
        manager = manager_map.get(emp["department"], "HR Manager")
        result = {"manager": manager, "employee_id": employee_id, "name": emp["name"]}
        workflow_state["manager"] = result
        return json.dumps(result, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[assign_manager])


# ============================================================================
# PHASE 2 — PARALLEL AGENTS (laptop, email, building — all independent)
# ============================================================================

def build_laptop_provisioner() -> Agent:
    """Provision a laptop. Writes to workflow_state["laptop"].

    For EMP-003, the first call raises ConnectionError to demonstrate
    run_agent_with_retry's exponential backoff recovery.
    """
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    system_prompt = """You are a laptop provisioning agent. Your ONLY job:
1. Call provision_laptop with the employee_id
2. Report: Laptop provisioned for <name> (ID: <employee_id>)
Do NOT add any other commentary."""

    @tool
    def provision_laptop(employee_id: str) -> str:
        emp = _get_employee(employee_id)
        # Simulate transient failure on first attempt for EMP-003
        if emp.get("simulate_failure") and "laptop_attempted" not in workflow_state:
            workflow_state["laptop_attempted"] = True
            raise ConnectionError("System currently unavailable")
        result = {"laptop_id": f"LAP-{employee_id}", "name": emp["name"], "employee_id": employee_id}
        workflow_state["laptop"] = result
        return json.dumps(result, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[provision_laptop])


def build_email_setup() -> Agent:
    """Set up email. Writes to workflow_state["email"].

    Independent of laptop and building access — runs in parallel.
    """
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    system_prompt = """You are an email setup agent. Your ONLY job:
1. Call setup_email with the employee_id
2. Report: Email set up for <name> (ID: <employee_id>)
Do NOT add any other commentary."""

    @tool
    def setup_email(employee_id: str) -> str:
        emp = _get_employee(employee_id)
        result = {"email": f"{emp['name'].lower()}@company.com", "employee_id": employee_id}
        workflow_state["email"] = result
        return json.dumps(result, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[setup_email])


def build_building_access() -> Agent:
    """Grant building access. Writes to workflow_state["building"].

    Independent of laptop and email — runs in parallel.
    """
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    system_prompt = """You are a building access agent. Your ONLY job:
1. Call grant_building_access with the employee_id
2. Report: Building access granted for <name> (ID: <employee_id>)
Do NOT add any other commentary."""

    @tool
    def grant_building_access(employee_id: str) -> str:
        emp = _get_employee(employee_id)
        result = {"badge_id": f"BDG-{employee_id}", "name": emp["name"], "employee_id": employee_id}
        workflow_state["building"] = result
        return json.dumps(result, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[grant_building_access])


# ============================================================================
# PHASE 3 — CONDITIONAL ROUTING (Python if/elif, not an LLM)
# ============================================================================

def build_engineering_onboarding() -> Agent:
    """Onboard an engineer with engineering-specific tools.

    Routes to this agent when emp["department"] == "Engineering".
    """
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    system_prompt = """You are an engineering onboarding agent. Your ONLY job:
1. Call onboard_engineering with the employee_id
2. Report: Engineering onboarding complete for <name> (ID: <employee_id>)
Do NOT add any other commentary."""

    @tool
    def onboard_engineering(employee_id: str) -> str:
        emp = _get_employee(employee_id)
        result = {"tools": ["GitHub", "Jira", "AWS Console", "PagerDuty"], "employee_id": employee_id, "name": emp["name"]}
        workflow_state["engineering_onboarding"] = result
        return json.dumps(result, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[onboard_engineering])


def build_sales_onboarding() -> Agent:
    """Onboard a salesperson with sales-specific tools.

    Routes to this agent when emp["department"] == "Sales".
    """
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    system_prompt = """You are a sales onboarding agent. Your ONLY job:
1. Call onboard_sales with the employee_id
2. Report: Sales onboarding complete for <name> (ID: <employee_id>)
Do NOT add any other commentary."""

    @tool
    def onboard_sales(employee_id: str) -> str:
        emp = _get_employee(employee_id)
        result = {"tools": ["Salesforce", "HubSpot", "Gong"], "employee_id": employee_id, "name": emp["name"]}
        workflow_state["sales_onboarding"] = result
        return json.dumps(result, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[onboard_sales])


# ============================================================================
# ORCHESTRATOR — ties all phases together
# ============================================================================

def orchestrate_onboarding(employee_id: str) -> dict:
    """Run the full onboarding workflow for a single employee.

    Phase 1 (Sequential):   account creator → manager assigner
    Phase 2 (Parallel):     laptop, email, building access via ThreadPoolExecutor
    Phase 3 (Conditional):  Python if/elif on department, no LLM involved
    """
    emp = _get_employee(employee_id)

    # Clear state from any previous run
    workflow_state.clear()

    # --- PHASE 1 (SEQUENTIAL): account must exist before manager assignment ---
    run_agent_with_retry(build_account_creator, f"Create account for {employee_id}")
    run_agent_with_retry(build_manager_assigner, f"Assign manager for {employee_id}")

    # --- PHASE 2 (PARALLEL): laptop, email, building access are independent ---
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(run_agent_with_retry, build_laptop_provisioner, f"Provision laptop for {employee_id}"): "laptop",
            executor.submit(run_agent_with_retry, build_email_setup, f"Set up email for {employee_id}"): "email",
            executor.submit(run_agent_with_retry, build_building_access, f"Grant building access for {employee_id}"): "building",
        }
        for f in as_completed(futures):
            f.result()

    # --- PHASE 3 (CONDITIONAL): code decision, not an LLM decision ---
    if emp["department"] == "Engineering":
        run_agent_with_retry(build_engineering_onboarding, f"Onboard engineer {employee_id}")
    elif emp["department"] == "Sales":
        run_agent_with_retry(build_sales_onboarding, f"Onboard sales {employee_id}")

    return build_onboarding_summary(employee_id)


def build_onboarding_summary(employee_id: str) -> dict:
    """Assemble all workflow_state entries into a single summary dict."""
    emp = _get_employee(employee_id)
    # Read each slice of workflow_state populated by the agents above
    account = workflow_state.get("account", {})
    manager = workflow_state.get("manager", {})
    laptop = workflow_state.get("laptop", {})
    email = workflow_state.get("email", {})
    building = workflow_state.get("building", {})
    # Pick the department-specific onboarding result
    onboarding = workflow_state.get("engineering_onboarding") or workflow_state.get("sales_onboarding", {})

    return {
        "employee": {"id": employee_id, "name": emp["name"], "department": emp["department"], "role": emp["role"]},
        "account": account,
        "manager": manager,
        "laptop": laptop,
        "email": email,
        "building": building,
        "onboarding_path": onboarding,
    }


def main() -> None:
    """CLI entrypoint. Onboards all employees (or a single one via --employee-id)."""
    import argparse
    parser = argparse.ArgumentParser(description="HR Onboarding Orchestrator")
    parser.add_argument("--employee-id", default=None, help="Onboard specific employee")
    args = parser.parse_args()

    # Filter to single employee if --employee-id is provided
    if args.employee_id:
        employees = [e for e in EMPLOYEES if e["id"] == args.employee_id]
        if not employees:
            print(f"Error: Employee {args.employee_id} not found")
            return
    else:
        employees = EMPLOYEES

    # Run the orchestrator for each employee and print the summary
    for emp in employees:
        summary = orchestrate_onboarding(emp["id"])
        print(f"\n{'=' * 70}")
        print(f"ONBOARDING: {summary['employee']['name']} ({summary['employee']['id']})")
        print(f"Department: {summary['employee']['department']} | Role: {summary['employee']['role']}")
        print(f"{'=' * 70}")
        print(f"Account: {summary['account']}")
        print(f"Manager: {summary['manager']}")
        print(f"Laptop: {summary['laptop']}")
        print(f"Email: {summary['email']}")
        print(f"Building: {summary['building']}")
        print(f"Onboarding Path: {summary['onboarding_path']}")
        print(f"Workflow State: {json.dumps(workflow_state, indent=2)}")


if __name__ == "__main__":
    main()
