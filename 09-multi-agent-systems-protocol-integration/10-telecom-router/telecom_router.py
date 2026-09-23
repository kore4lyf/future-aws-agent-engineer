# =============================================================================
# Telecom Router — Hybrid Routing Exercise Solution
# =============================================================================
# A four-tier decision pipeline that routes telecom support tickets to
# specialist agents using priority overrides, rule-based matching, LLM
# classification, and a fallback safety net.
#
# Architecture:
#   Tier 1 (Priority):  cancellation intent → RetentionAgent
#   Tier 2 (Rules):     regex keyword matching → BillingAgent/TechnicalAgent
#   Tier 3 (LLM):       Nova Lite classifier → specialist based on intent
#   Tier 4 (Fallback):  confidence < 0.6 → GeneralSupportAgent (human review)
# ============================================================================

import json
import os
import re
import time
import uuid
from decimal import Decimal
from datetime import datetime, timezone

import boto3
from dotenv import load_dotenv
from strands import Agent, tool
from strands.models import BedrockModel

load_dotenv()

# --- Bedrock configuration ---
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
NOVA_LITE_MODEL = os.environ.get("NOVA_LITE_MODEL", "amazon.nova-lite-v1:0")

# --- DynamoDB audit table ---
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "telecom-routing-audit")
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
audit_table = dynamodb.Table(DYNAMODB_TABLE)

# --- Priority patterns (Tier 1) ---
# Cancellations are business-critical: route straight to RetentionAgent.
PRIORITY_PATTERNS = [
    r"\b(cancel\w*|switch provider|terminate|discontinue|done with this company)\b",
    r"\bleave\b.*\b(provider|service|company|carrier|plan)\b",
]

# --- Routing rules (Tier 2) ---
# Each tuple: (regex pattern, target agent name)
# Patterns are matched against lowercased ticket text.
ROUTING_RULES = [
    (r"\b(bill\w*|charg\w*|payment\w*|invoice\w*|subscription\w*|rate\b|roaming)\b",
     "BillingAgent"),
    (r"\b(outage|no signal|slow\w*|drop\w*|disconnect\w*|no service|tower)\b",
     "TechnicalAgent"),
]

# --- LLM confidence threshold (Tier 3) ---
# If the classifier's confidence is below this, fall back to human review.
CONFIDENCE_THRESHOLD = 0.6

# --- Intent-to-agent mapping (Tier 3) ---
INTENT_TO_AGENT = {
    "billing": "BillingAgent",
    "technical": "TechnicalAgent",
    "cancellation": "RetentionAgent",
    "general": "GeneralSupportAgent",
}


def clean_response(text: str) -> str:
    """Strip <thinking> tags and extract JSON from model output.

    The classifier agent may include prose around the JSON tool result,
    so we find the first valid JSON object in the text.
    If no JSON is found, return the cleaned text as-is.
    """
    text = re.sub(r"<thinking>.*?</thinking>", "", str(text), flags=re.DOTALL).strip()
    start = text.find("{")
    if start != -1:
        end = text.rfind("}") + 1
        candidate = text[start:end]
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass
    return text


def run_agent_with_retry(agent_builder, prompt: str, max_retries: int = 3) -> str:
    """Wrap an agent invocation with exponential backoff (1s, 2s, 4s)."""
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
# PRIORITY AND RULE HELPERS (Tiers 1 and 2)
# ============================================================================

def priority_route(text: str) -> str | None:
    """Tier 1: detect cancellation intent and route to RetentionAgent."""
    lower = text.lower()
    for pattern in PRIORITY_PATTERNS:
        if re.search(pattern, lower):
            return "RetentionAgent"
    return None


def rule_based_route(text: str) -> str | None:
    """Tier 2: deterministic keyword matching for billing and technical."""
    lower = text.lower()
    for pattern, agent_name in ROUTING_RULES:
        if re.search(pattern, lower):
            return agent_name
    return None


# ============================================================================
# CLASSIFIER AGENT (Tier 3)
# ============================================================================

def build_classifier_agent() -> Agent:
    """Nova Lite classifier that returns structured {intent, confidence}.

    Forced tool output means downstream code reads structured fields
    without parsing prose — no free-text responses allowed.
    """
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)

    classification_result = {}

    system_prompt = """You are an intent classifier for a telecom customer support platform.
Classify the customer ticket into ONE of: billing, technical, cancellation, general.
Confidence: 0.8-1.0 if clear, 0.5-0.7 if ambiguous, low if nonsensical.
Call classify_intent ONCE with the intent and confidence.
Return ONLY the JSON result from the tool. Do NOT add any commentary."""

    @tool
    def classify_intent(intent: str, confidence: float) -> str:
        classification_result["intent"] = intent.lower().strip()
        classification_result["confidence"] = min(max(float(confidence), 0.0), 1.0)
        return json.dumps(classification_result)

    return Agent(model=model, system_prompt=system_prompt, tools=[classify_intent])


def llm_classify(text: str) -> tuple[str, float, dict]:
    """Run the classifier agent and extract intent + confidence.

    Returns (intent, confidence, raw_result_dict).
    Handles both structured JSON and prose responses from the model.
    """
    agent = build_classifier_agent()
    result = agent(f"Classify this ticket: {text}")
    result_str = str(result)
    start = result_str.find("{")
    if start != -1:
        end = result_str.rfind("}") + 1
        candidate = result_str[start:end]
        try:
            parsed = json.loads(candidate)
            return parsed.get("intent", "general"), parsed.get("confidence", 0.0), parsed
        except json.JSONDecodeError:
            pass
    # Fallback: extract intent and confidence from prose including thinking tags
    intent_match = re.search(r"(billing|technical|cancellation|general)", result_str.lower())
    conf_match = re.search(r"confidence of (\d+\.?\d*)", result_str)
    intent = intent_match.group(1) if intent_match else "general"
    confidence = float(conf_match.group(1)) if conf_match else 0.5
    return intent, confidence, {"intent": intent, "confidence": confidence}


# ============================================================================
# WORKER AGENTS
# ============================================================================

WORKER_SYSTEM_PROMPTS = {
    "BillingAgent": (
        "You are a billing specialist at a telecom company. "
        "Resolve the customer's billing query clearly and concisely. "
        "Reference specific charges or amounts when provided."
    ),
    "TechnicalAgent": (
        "You are a technical support specialist at a telecom company. "
        "Diagnose the technical problem and provide actionable steps to resolve it."
    ),
    "RetentionAgent": (
        "You are a retention specialist at a telecom company. "
        "The customer wants to cancel. Make a compelling retention offer "
        "(e.g., discount, free premium channels, plan upgrade) to keep them."
    ),
    "GeneralSupportAgent": (
        "You are a general support agent at a telecom company. "
        "Create a ticket for human review. Acknowledge the customer's issue "
        "and let them know a human agent will follow up."
    ),
}


def build_worker_agent(agent_name: str) -> Agent:
    """Build a Nova Lite worker agent for the given specialist role."""
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    system_prompt = WORKER_SYSTEM_PROMPTS.get(agent_name, WORKER_SYSTEM_PROMPTS["GeneralSupportAgent"])
    return Agent(model=model, system_prompt=system_prompt)


def run_worker_agent(agent_name: str, ticket_text: str) -> str:
    """Invoke the worker agent and return its resolution."""
    return run_agent_with_retry(
        lambda: build_worker_agent(agent_name),
        f"Customer ticket: {ticket_text}",
    )


# ============================================================================
# HYBRID ROUTER — the load-bearing function
# ============================================================================

def hybrid_route(ticket: dict) -> dict:
    """Route a ticket to the correct specialist agent.

    Walks four tiers in priority order and returns the first match:
      1. Priority — cancellation intent → RetentionAgent
      2. Rules    — regex keyword matching → BillingAgent/TechnicalAgent
      3. LLM      — Nova Lite classifier → specialist based on intent
      4. Fallback — confidence < 0.6 → GeneralSupportAgent
    """
    text = ticket["text"]

    # --- Tier 1: Priority — cancellation always reaches retention ---
    target = priority_route(text)
    if target:
        return {"target_agent": target, "method": "priority", "confidence": 1.0}

    # --- Tier 2: Rules — fast, free, deterministic ---
    target = rule_based_route(text)
    if target:
        return {"target_agent": target, "method": "rule", "confidence": 1.0}

    # --- Tier 3: LLM classification — flexible, handles ambiguity ---
    intent, confidence, _ = llm_classify(text)
    if confidence >= CONFIDENCE_THRESHOLD:
        agent_name = INTENT_TO_AGENT.get(intent, "GeneralSupportAgent")
        return {"target_agent": agent_name, "method": "llm", "confidence": confidence}

    # --- Tier 4: Fallback — flag for human review ---
    return {"target_agent": "GeneralSupportAgent", "method": "fallback", "confidence": confidence}


# ============================================================================
# AUDIT LOGGING — DynamoDB with 24-hour TTL
# ============================================================================

def log_routing_decision(request_id: str, method: str, target_agent: str, confidence: float, latency_ms: float) -> None:
    """Write routing decision to DynamoDB audit table.

    Every automated decision is logged for compliance and debugging.
    TTL is set to 24 hours from now.
    """
    now = datetime.now(timezone.utc)
    ttl_epoch = int(now.timestamp()) + 86400  # 24 hours

    audit_table.put_item(
        Item={
            "request_id": request_id,
            "timestamp": now.isoformat(),
            "method": method,
            "target_agent": target_agent,
            "confidence": Decimal(str(confidence)),
            "latency_ms": Decimal(str(latency_ms)),
            "ttl": ttl_epoch,
        }
    )


# ============================================================================
# TICKET PROCESSING
# ============================================================================

def process_ticket(ticket: dict) -> dict:
    """Route a single ticket, run the worker agent, and log the decision.

    Returns the full routing result with timing, resolution, and audit info.
    """
    ticket_id = ticket.get("id", str(uuid.uuid4()))

    # Time the routing decision
    start = time.perf_counter()
    result = hybrid_route(ticket)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

    # Run the worker agent to produce a resolution
    resolution = run_worker_agent(result["target_agent"], ticket["text"])

    # Log to DynamoDB audit table
    log_routing_decision(
        request_id=ticket_id,
        method=result["method"],
        target_agent=result["target_agent"],
        confidence=result["confidence"],
        latency_ms=elapsed_ms,
    )

    return {
        "ticket_id": ticket_id,
        "text": ticket["text"],
        "target_agent": result["target_agent"],
        "method": result["method"],
        "confidence": result["confidence"],
        "latency_ms": elapsed_ms,
        "resolution": resolution,
    }


# ============================================================================
# MAIN
# ============================================================================

SAMPLE_TICKETS = [
    # Tickets 1-8: billing (40%) — overcharges, roaming fees, subscription questions
    {"id": "TKT-001", "text": "I was overcharged on my bill this month"},
    {"id": "TKT-002", "text": "There's an incorrect charge on my invoice"},
    {"id": "TKT-003", "text": "Why was my payment not applied to my account?"},
    {"id": "TKT-004", "text": "I need to dispute a roaming charge on my bill"},
    {"id": "TKT-005", "text": "My subscription rate seems too high"},
    {"id": "TKT-006", "text": "Please explain this charge on my latest invoice"},
    {"id": "TKT-007", "text": "I want to update my payment method for the bill"},
    {"id": "TKT-008", "text": "There's a double charge on my billing statement"},
    # Tickets 9-14: technical (~30%) — outages, slow data, dropped calls
    {"id": "TKT-009", "text": "There's an outage in my area"},
    {"id": "TKT-010", "text": "I have no signal on my phone"},
    {"id": "TKT-011", "text": "My internet is slow since yesterday"},
    {"id": "TKT-012", "text": "My calls keep getting dropped"},
    {"id": "TKT-013", "text": "The service keeps disconnecting"},
    {"id": "TKT-014", "text": "There's no service at my location"},
    # Tickets 15-16: cancellation — priority → RetentionAgent
    {"id": "TKT-015", "text": "I want to cancel my service"},
    {"id": "TKT-016", "text": "I'm switching to another provider, terminate my plan"},
    # Tickets 17-19: ambiguous — LLM classifier (confidence >= 0.6)
    {"id": "TKT-017", "text": "Something weird is happening with my account"},
    {"id": "TKT-018", "text": "I'm not happy with how things are going"},
    {"id": "TKT-019", "text": "Can someone help me with my recent experience?"},
    # Ticket 20: nonsensical — fallback to GeneralSupportAgent
    {"id": "TKT-020", "text": "purple elephant dancing on mars"},
]


def main() -> None:
    """CLI entrypoint. Routes sample tickets and prints results."""
    print("=" * 70)
    print("Telecom Router — Hybrid Routing Exercise Solution")
    print("=" * 70)

    method_counts = {"priority": 0, "rule": 0, "llm": 0, "fallback": 0}
    total_latency = 0.0

    for ticket in SAMPLE_TICKETS:
        result = process_ticket(ticket)
        method_counts[result["method"]] += 1
        total_latency += result["latency_ms"]

        print(f"\n--- {result['ticket_id']} ---")
        print(f"Text:       {result['text']}")
        print(f"Route:      {result['target_agent']}")
        print(f"Method:     {result['method']}")
        print(f"Confidence: {result['confidence']:.2f}")
        print(f"Latency:    {result['latency_ms']}ms")
        print(f"Resolution: {result['resolution'][:120]}...")

    # --- Effectiveness report ---
    print("\n" + "=" * 70)
    print("Method Distribution")
    print("=" * 70)
    for method, count in method_counts.items():
        print(f"  {method:10s}: {count}")
    llm_touched = method_counts["llm"] + method_counts["fallback"]
    no_llm = len(SAMPLE_TICKETS) - llm_touched
    print(f"\n  Routed without LLM: {no_llm}/{len(SAMPLE_TICKETS)} ({100 * no_llm // len(SAMPLE_TICKETS)}%)")
    print(f"  Average routing latency: {total_latency / len(SAMPLE_TICKETS):.2f}ms")


if __name__ == "__main__":
    main()
