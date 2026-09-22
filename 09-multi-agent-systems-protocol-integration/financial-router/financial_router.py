# =============================================================================
# Financial Router — Hybrid Routing Demo
# =============================================================================
# A four-tier decision pipeline that routes financial requests to specialist
# agents using priority overrides, rule-based matching, LLM classification,
# and a fallback safety net.
#
# Architecture:
#   Tier 1 (Priority):  amount > $10,000 → SeniorReviewAgent
#   Tier 2 (Rules):     regex keyword matching → PaymentsAgent/FraudAgent/AccountAgent
#   Tier 3 (LLM):       Nova Lite classifier → specialist based on intent
#   Tier 4 (Fallback):  confidence < 0.6 → GeneralSupportAgent
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
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "routing-audit")
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
audit_table = dynamodb.Table(DYNAMODB_TABLE)

# --- Routing rules (Tier 2) ---
# Each tuple: (regex pattern, target agent name)
# Patterns are matched against lowercased request text.
ROUTING_RULES = [
    (r"\b(wire|transfer|send money|payment)\b", "PaymentsAgent"),
    (r"\b(fraud\w*|stolen|unauthorized|suspicious)\b", "FraudAgent"),
    (r"\b(balance|statement|account info|account history)\b", "AccountAgent"),
]

# --- LLM confidence threshold (Tier 3) ---
# If the classifier's confidence is below this, fall back to human review.
CONFIDENCE_THRESHOLD = 0.6


def clean_response(text: str) -> str:
    """Strip <thinking> tags and extract JSON from model output.

    The classifier agent may include prose around the JSON tool result,
    so we find the first valid JSON object in the text.
    If no JSON is found, return the cleaned text as-is.
    """
    text = re.sub(r"<thinking>.*?</thinking>", "", str(text), flags=re.DOTALL).strip()
    # Try to extract JSON object from the response
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
# CLASSIFIER AGENT (Tier 3)
# ============================================================================

def build_classifier_agent() -> Agent:
    """Nova Lite classifier that returns structured {intent, confidence}.

    Forced tool output means downstream code reads structured fields
    without parsing prose — no free-text responses allowed.
    """
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)

    # Shared dict that the tool writes to
    classification_result = {}

    system_prompt = """You are an intent classifier for a financial services platform.
Classify the customer request into ONE of: payments, fraud, account, general.
Confidence: 0.8-1.0 if clear, 0.5-0.7 if ambiguous, low if nonsensical.
Call classify_intent ONCE with the intent and confidence.
Return ONLY the JSON result from the tool. Do NOT add any commentary."""

    @tool
    def classify_intent(intent: str, confidence: float) -> str:
        # Clamp confidence to [0.0, 1.0] and normalize intent
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
    result = agent(f"Classify this request: {text}")
    result_str = str(result)
    # Try to extract JSON first (from tool output)
    start = result_str.find("{")
    if start != -1:
        end = result_str.rfind("}") + 1
        candidate = result_str[start:end]
        try:
            parsed = json.loads(candidate)
            return parsed.get("intent", "general"), parsed.get("confidence", 0.0), parsed
        except json.JSONDecodeError:
            pass
    # Fallback: extract intent and confidence from prose using regex
    # Search the full string including thinking tags
    intent_match = re.search(r"(payments|fraud|account|general)", result_str.lower())
    conf_match = re.search(r"confidence of (\d+\.?\d*)", result_str)
    intent = intent_match.group(1) if intent_match else "general"
    confidence = float(conf_match.group(1)) if conf_match else 0.5
    return intent, confidence, {"intent": intent, "confidence": confidence}


# ============================================================================
# HYBRID ROUTER — the load-bearing function
# ============================================================================

def hybrid_route(request: dict) -> dict:
    """Route a request to the correct specialist agent.

    Walks four tiers in priority order and returns the first match:
      1. Priority — amount > $10,000 bypasses everything → SeniorReviewAgent
      2. Rules    — regex keyword matching → PaymentsAgent/FraudAgent/AccountAgent
      3. LLM      — Nova Lite classifier → specialist based on intent
      4. Fallback — confidence < 0.6 → GeneralSupportAgent
    """
    text = request["text"]

    # --- Tier 1: Priority — business-critical override ---
    if request.get("amount", 0) > 10000:
        return {"target_agent": "SeniorReviewAgent", "method": "priority", "confidence": 1.0}

    # --- Tier 2: Rules — fast, free, deterministic ---
    for pattern, agent_name in ROUTING_RULES:
        if re.search(pattern, text.lower()):
            return {"target_agent": agent_name, "method": "rule", "confidence": 1.0}

    # --- Tier 3: LLM classification — flexible, handles ambiguity ---
    intent, confidence, _ = llm_classify(text)
    if confidence >= CONFIDENCE_THRESHOLD:
        # Map LLM intent to agent name
        intent_to_agent = {
            "payments": "PaymentsAgent",
            "fraud": "FraudAgent",
            "account": "AccountAgent",
        }
        agent_name = intent_to_agent.get(intent, "GeneralSupportAgent")
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
# REQUEST PROCESSING
# ============================================================================

def process_request(request: dict) -> dict:
    """Route a single request and log the decision.

    Returns the full routing result with timing and audit info.
    """
    request_id = request.get("id", str(uuid.uuid4()))

    # Time the routing decision
    start = time.perf_counter()
    result = hybrid_route(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

    # Log to DynamoDB audit table
    log_routing_decision(
        request_id=request_id,
        method=result["method"],
        target_agent=result["target_agent"],
        confidence=result["confidence"],
        latency_ms=elapsed_ms,
    )

    return {
        "request_id": request_id,
        "text": request["text"],
        "amount": request.get("amount", 0),
        "target_agent": result["target_agent"],
        "method": result["method"],
        "confidence": result["confidence"],
        "latency_ms": elapsed_ms,
    }


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    """CLI entrypoint. Routes sample requests and prints results."""
    # --- 10 test requests: 2 payments, 2 fraud, 2 account, 2 priority, 1 LLM, 1 fallback ---
    sample_requests = [
        # REQ-001, REQ-002: wire transfer keywords → PaymentsAgent (rule)
        {"id": "REQ-001", "text": "I need to send a wire transfer to my vendor", "amount": 5000},
        {"id": "REQ-002", "text": "Please process a payment to my supplier", "amount": 3000},
        # REQ-003, REQ-004: fraud keywords → FraudAgent (rule)
        {"id": "REQ-003", "text": "I noticed fraudulent charges on my account", "amount": 0},
        {"id": "REQ-004", "text": "There are unauthorized transactions on my card", "amount": 0},
        # REQ-005, REQ-006: account keywords → AccountAgent (rule)
        {"id": "REQ-005", "text": "Can you check my account balance?", "amount": 0},
        {"id": "REQ-006", "text": "I need a copy of my account statement", "amount": 0},
        # REQ-007, REQ-008: high value → SeniorReviewAgent (priority)
        {"id": "REQ-007", "text": "Send $50,000 wire to offshore account", "amount": 50000},
        {"id": "REQ-008", "text": "Transfer $25,000 to investment fund", "amount": 25000},
        # REQ-009: ambiguous → LLM classifier (high confidence)
        {"id": "REQ-009", "text": "I need help moving some funds around", "amount": 0},
        # REQ-010: nonsensical → GeneralSupportAgent (fallback)
        {"id": "REQ-010", "text": "purple elephant dancing on mars", "amount": 0},
    ]

    print("=" * 70)
    print("Financial Router — Hybrid Routing Demo")
    print("=" * 70)

    for request in sample_requests:
        result = process_request(request)
        print(f"\n--- {result['request_id']} ---")
        print(f"Text:     {result['text']}")
        print(f"Amount:   ${result['amount']:,}")
        print(f"Route:    {result['target_agent']}")
        print(f"Method:   {result['method']}")
        print(f"Confidence: {result['confidence']:.2f}")
        print(f"Latency:  {result['latency_ms']}ms")


if __name__ == "__main__":
    main()
