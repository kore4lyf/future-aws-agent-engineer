# =============================================================================
# Contract Compliance — Parallel Multi-Agent System
# =============================================================================
# Runs 3 specialist agents in parallel, then synthesizes results
# with a deterministic Python decision (not an LLM).
# ============================================================================

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from dotenv import load_dotenv
from strands import Agent, tool
from strands.models import BedrockModel

load_dotenv()

# --- Bedrock model configuration ---
# Nova Lite for lightweight regulatory checks
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
NOVA_LITE_MODEL = os.environ.get("NOVA_LITE_MODEL", "amazon.nova-lite-v1:0")
# Claude for financial risk assessment (requires Anthropic Bedrock subscription)
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
# Nova Pro for IP clause analysis
NOVA_PRO_MODEL = os.environ.get("NOVA_PRO_MODEL", "amazon.nova-pro-v1:0")

# --- Test contracts ---
# CONTRACT-001: all LOW risk → APPROVE
# CONTRACT-002: all HIGH risk → REJECT
CONTRACTS = [
    {
        "id": "CONTRACT-001",
        "vendor": "TechCloud",
        "title": "Cloud vendor agreement",
        "value": 120000,
        "duration_months": 24,
        "notes": "SOC2 certified, US-only data residency, 30-day deletion clause.",
    },
    {
        "id": "CONTRACT-002",
        "vendor": "Global Def Solutions",
        "title": "Offshore outsourcing deal",
        "value": 500000,
        "duration_months": 36,
        "notes": "No SOC2 certifications, data processing in India and Philippines, joint IP ownership, six-month termination penalty.",
    },
]

# --- Hardcoded findings tables ---
# Each maps a contract_id to its domain-specific findings.
# These replace live agent calls in the deterministic tests.
REGULATORY_FINDINGS = {
    "CONTRACT-001": {
        "risk_level": "LOW", "violations": 0, "details": [],
        "recommendation": "Standard regulatory compliance, no issues found.",
    },
    "CONTRACT-002": {
        "risk_level": "HIGH", "violations": 3,
        "details": ["GDPR Article 28 violation", "CCPA non-compliance", "HIPAA gap"],
        "recommendation": "Requires immediate regulatory review before signing.",
    },
}

FINANCIAL_FINDINGS = {
    "CONTRACT-001": {
        "risk_level": "LOW", "unfavorable_terms": 1,
        "details": ["Auto-renewal clause with 30-day notice"],
        "recommendation": "Standard commercial terms, minor renewal clause to review.",
    },
    "CONTRACT-002": {
        "risk_level": "HIGH", "unfavorable_terms": 5,
        "details": ["Unlimited data usage rights", "Broad liability waiver", "Non-compete", "Hidden fees", "Arbitration clause"],
        "recommendation": "High financial risk, negotiate terms before proceeding.",
    },
}

IP_FINDINGS = {
    "CONTRACT-001": {
        "risk_level": "LOW", "ip_concerns": 1,
        "details": ["Vendor retains ownership of proprietary monitoring tools"],
        "recommendation": "Standard IP arrangement, ensure your IP is protected.",
    },
    "CONTRACT-002": {
        "risk_level": "HIGH", "ip_concerns": 4,
        "details": ["Vendor claims derived models", "Broad license", "No attribution", "Exclusive rights"],
        "recommendation": "Severe IP risks, comprehensive renegotiation required.",
    },
}

# --- Shared caches ---
# Each agent writes its finding to its cache on invocation.
regulatory_cache = {}
financial_cache = {}
ip_cache = {}


def clean_response(text: str) -> str:
    """Strip <thinking> tags from model output."""
    return re.sub(r"<thinking>.*?</thinking>", "", str(text), flags=re.DOTALL).strip()


def run_agent_with_retry(agent_builder, prompt: str, max_retries: int = 3) -> str:
    """Wrap an agent invocation with exponential backoff (1s, 2s, 4s).

    Catches transient Bedrock errors and retries without crashing the phase.
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


# ============================================================================
# SPECIALIST AGENTS — each reads its findings table and writes its cache
# ============================================================================

def build_regulatory_agent() -> Agent:
    """Regulatory compliance reviewer (Nova Lite, temperature 0.0).

    Calls check_regulatory → writes result to regulatory_cache.
    """
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    system_prompt = """You are a regulatory compliance reviewer. Your ONLY job:
1. Call check_regulatory with the contract_id
2. Report in exactly 3 lines:
   Risk Level: <HIGH|MEDIUM|LOW>
   Violations: <count or NONE>
   Recommendation: <one-sentence>"""

    @tool
    def check_regulatory(contract_id: str) -> str:
        # Look up findings and cache the result
        result = REGULATORY_FINDINGS.get(
            contract_id,
            {"risk_level": "UNKNOWN", "violations": 0, "details": [], "recommendation": "Review required"},
        )
        regulatory_cache[contract_id] = result
        return json.dumps(result, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[check_regulatory])


def build_financial_agent() -> Agent:
    """Financial risk reviewer (Claude, temperature 0.1).

    Calls assess_financial_risk → writes result to financial_cache.
    """
    model = BedrockModel(model_id=CLAUDE_MODEL, region_name=AWS_REGION, temperature=0.1)
    system_prompt = """You are a financial risk reviewer. Your ONLY job:
1. Call assess_financial_risk with the contract_id
2. Report in exactly 3 lines:
   Risk Level: <HIGH|MEDIUM|LOW>
   Unfavorable Terms: <count or NONE>
   Recommendation: <one-sentence>"""

    @tool
    def assess_financial_risk(contract_id: str) -> str:
        # Look up findings and cache the result
        result = FINANCIAL_FINDINGS.get(
            contract_id,
            {"risk_level": "UNKNOWN", "unfavorable_terms": 0, "details": [], "recommendation": "Review required"},
        )
        financial_cache[contract_id] = result
        return json.dumps(result, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[assess_financial_risk])


def build_ip_agent() -> Agent:
    """IP clause reviewer (Nova Pro, temperature 0.1).

    Calls review_ip_clauses → writes result to ip_cache.
    """
    model = BedrockModel(model_id=NOVA_PRO_MODEL, region_name=AWS_REGION, temperature=0.1)
    system_prompt = """You are an intellectual property reviewer. Your ONLY job:
1. Call review_ip_clauses with the contract_id
2. Report in exactly 3 lines:
   Risk Level: <HIGH|MEDIUM|LOW>
   IP Concerns: <count or NONE>
   Recommendation: <one-sentence>"""

    @tool
    def review_ip_clauses(contract_id: str) -> str:
        # Look up findings and cache the result
        result = IP_FINDINGS.get(
            contract_id,
            {"risk_level": "UNKNOWN", "ip_concerns": 0, "details": [], "recommendation": "Review required"},
        )
        ip_cache[contract_id] = result
        return json.dumps(result, indent=2)

    return Agent(model=model, system_prompt=system_prompt, tools=[review_ip_clauses])


# ============================================================================
# SYNTHESIS — deterministic Python decision, no LLM involved
# ============================================================================

def synthesize_compliance(contract_id: str) -> str:
    """Determine overall recommendation from cached specialist findings.

    Decision logic (pure code, not an LLM):
      ≥2 HIGH risk levels  → REJECT
      1 HIGH or max MEDIUM → APPROVE-WITH-CONDITIONS
      otherwise            → APPROVE
    """
    reg = regulatory_cache.get(contract_id, {})
    fin = financial_cache.get(contract_id, {})
    ip = ip_cache.get(contract_id, {})

    risk_levels = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}
    risks = [risk_levels.get(d.get("risk_level", "UNKNOWN"), 0) for d in (reg, fin, ip)]
    high_risk_count = sum(1 for risk in risks if risk == 3)

    # Conditional routing based on risk count — no LLM making this decision
    if high_risk_count >= 2:
        recommendation = "REJECT"
    elif high_risk_count == 1 or max(risks) == 2:
        recommendation = "APPROVE-WITH-CONDITIONS"
    else:
        recommendation = "APPROVE"

    return json.dumps(
        {
            "contract_id": contract_id,
            "overall_risk": "HIGH" if high_risk_count >= 2 else ("MEDIUM" if high_risk_count == 1 or max(risks) == 2 else "LOW"),
            "recommendation": recommendation,
            "regulatory_summary": reg.get("recommendation", "Review required"),
            "financial_summary": fin.get("recommendation", "Review required"),
            "ip_summary": ip.get("recommendation", "Review required"),
            "specialist_findings": {
                "regulatory": {"risk_level": reg.get("risk_level", "UNKNOWN"), "violations_count": reg.get("violations", 0)},
                "financial": {"risk_level": fin.get("risk_level", "UNKNOWN"), "unfavorable_terms_count": fin.get("unfavorable_terms", 0)},
                "ip": {"risk_level": ip.get("risk_level", "UNKNOWN"), "ip_concerns_count": ip.get("ip_concerns", 0)},
            },
        },
        indent=2,
    )


def build_synthesizer_agent() -> Agent:
    """Compliance synthesizer agent (Claude, temperature 0.2).

    Wraps synthesize_compliance() as a tool so the LLM can be invoked
    via the agent framework. The actual decision logic lives in
    synthesize_compliance(), not in the LLM prompt.
    """
    model = BedrockModel(model_id=CLAUDE_MODEL, region_name=AWS_REGION, temperature=0.2)
    system_prompt = """You are a compliance synthesizer. Your ONLY job:
1. Call synthesize_compliance_tool with the contract_id
2. Return the final recommendation and per-domain summaries.
Use only the structured JSON from the specialists."""

    @tool
    def synthesize_compliance_tool(contract_id: str) -> str:
        return synthesize_compliance(contract_id)

    return Agent(model=model, system_prompt=system_prompt, tools=[synthesize_compliance_tool])


# ============================================================================
# EXECUTION — parallel vs sequential comparison
# ============================================================================

def run_specialists_parallel(contract_id: str) -> dict:
    """Run all 3 specialists concurrently using ThreadPoolExecutor.

    Returns a dict keyed by agent type: {"regulatory": ..., "financial": ..., "ip": ...}
    """
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(run_agent_with_retry, build_regulatory_agent, f"Check regulatory compliance for contract {contract_id}"): "regulatory",
            executor.submit(run_agent_with_retry, build_financial_agent, f"Assess financial risk for contract {contract_id}"): "financial",
            executor.submit(run_agent_with_retry, build_ip_agent, f"Review IP clauses for contract {contract_id}"): "ip",
        }
        return {futures[f]: f.result() for f in as_completed(futures)}


def run_specialists_sequential(contract_id: str) -> dict:
    """Run all 3 specialists one after another.

    Used for timing comparison against run_specialists_parallel.
    """
    return {
        "regulatory": run_agent_with_retry(build_regulatory_agent, f"Check regulatory compliance for contract {contract_id}"),
        "financial": run_agent_with_retry(build_financial_agent, f"Assess financial risk for contract {contract_id}"),
        "ip": run_agent_with_retry(build_ip_agent, f"Review IP clauses for contract {contract_id}"),
    }


def run_contract(contract: dict) -> None:
    """Execute parallel specialists, then sequential, then synthesize.

    Prints timing comparison and the final compliance report.
    """
    contract_id = contract["id"]
    print(f"\n=== Parallel Contract Compliance ===")
    print(f"Contract: {contract_id}")
    print(f"Vendor: {contract['vendor']}")
    print(f"Title: {contract['title']}")
    print(f"Value: ${contract['value']:,}")
    print(f"Duration: {contract['duration_months']} months")
    print(f"Notes: {contract['notes']}")
    print("Running three specialists in parallel...")

    # --- Phase A: parallel specialist execution ---
    parallel_start = time.perf_counter()
    parallel_results = run_specialists_parallel(contract_id)
    parallel_end = time.perf_counter()
    parallel_time = parallel_end - parallel_start

    # --- Phase B: sequential specialist execution (for timing comparison) ---
    sequential_start = time.perf_counter()
    sequential_results = run_specialists_sequential(contract_id)
    sequential_end = time.perf_counter()
    sequential_time = sequential_end - sequential_start

    speedup = sequential_time / parallel_time if parallel_time > 0 else 0.0

    # --- Phase C: synthesize results (deterministic, no LLM) ---
    build_synthesizer_agent()(f"Synthesize compliance for contract {contract_id}")
    synthesis = synthesize_compliance(contract_id)

    print(f"\nContract compliance report: {contract_id}")
    print(f"Parallel time: {parallel_time:.4f}s")
    print(f"Sequential time: {sequential_time:.4f}s")
    print(f"Speedup: {speedup:.2f}x")
    print(json.dumps(json.loads(synthesis), indent=2))


def main() -> None:
    """CLI entrypoint. Runs all contracts and prints a comparison table."""
    print("Parallel contract compliance")
    for contract in CONTRACTS:
        run_contract(contract)

    # --- Summary comparison table ---
    print("\n=== Comparison Table ===")
    for contract in CONTRACTS:
        build_synthesizer_agent()(f"Synthesize compliance for contract {contract['id']}")
        synthesis = synthesize_compliance(contract["id"])
        result = json.loads(synthesis)
        print(f"{contract['id']}: {result['recommendation']}")


if __name__ == "__main__":
    main()
