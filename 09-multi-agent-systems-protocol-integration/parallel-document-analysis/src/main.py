# =============================================================================
# Parallel Document Analysis — Multi-Agent System Demo
# =============================================================================
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

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
NOVA_LITE_MODEL = os.environ.get("NOVA_LITE_MODEL", "amazon.nova-lite-v1:0")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
NOVA_PRO_MODEL = os.environ.get("NOVA_PRO_MODEL", "amazon.nova-pro-v1:0")

# Sample documents
DOCUMENTS = [
    {"id": "DOC-001", "title": "Microservices Migration Plan", "description": "Plan to migrate monolith to microservices"},
    {"id": "DOC-002", "title": "Real-Time Analytics Platform", "description": "Real-time analytics for user behavior"},
    {"id": "DOC-003", "title": "AI-Powered Recommendation Engine", "description": "ML-powered product recommendations"},
]

# Sample findings tables
SECURITY_FINDINGS = {
    "DOC-001": {"risk_level": "MEDIUM", "critical_issues": ["API gateway needs mTLS", "No secrets management"], "recommendation": "Security review required"},
    "DOC-002": {"risk_level": "HIGH", "critical_issues": ["GDPR compliance challenges", "User data tracking needs consent"], "recommendation": "Privacy review mandatory"},
    "DOC-003": {"risk_level": "LOW", "critical_issues": ["Model bias concerns", "Rate limiting needed"], "recommendation": "Standard security review"},
}

SCALABILITY_FINDINGS = {
    "DOC-001": {"bottleneck_risk": "HIGH", "scaling_challenges": ["No DB sharding strategy", "Network bottlenecks likely"], "recommendation": "Design partitioning before migration"},
    "DOC-002": {"bottleneck_risk": "MEDIUM", "scaling_challenges": ["Kafka partition planning needed", "Flink parallelism tuning"], "recommendation": "Load test with production traffic"},
    "DOC-003": {"bottleneck_risk": "HIGH", "scaling_challenges": ["GPU clusters expensive", "Low-latency inference challenging"], "recommendation": "Consider model distillation"},
}

COST_FINDINGS = {
    "DOC-001": {"estimated_cost_tier": "MEDIUM", "cost_drivers": ["12 microservices", "Service mesh overhead"], "recommendation": "Est. $50-80K/month"},
    "DOC-002": {"estimated_cost_tier": "HIGH", "cost_drivers": ["Kafka cluster", "High-memory Flink", "ClickHouse storage"], "recommendation": "Budget $150-200K/month"},
    "DOC-003": {"estimated_cost_tier": "HIGH", "cost_drivers": ["GPU training clusters", "Real-time inference infra"], "recommendation": "Est. $120-180K/month"},
}

SYNTHESIS_TEMPLATES = {
    "APPROVE": "## Launch Readiness: APPROVED\n\nReady for implementation. All risks manageable.\n\nNext steps:\n- Proceed with implementation\n- Schedule review checkpoints",
    "APPROVE-WITH-CONDITIONS": "## Launch Readiness: APPROVED WITH CONDITIONS\n\nCan proceed with conditions:\n- Address security concerns\n- Plan scalability strategy\n\nNext steps:\n- Resolve conditions\n- Re-review after",
    "BLOCK": "## Launch Readiness: BLOCKED\n\nCannot proceed. Critical issues must be resolved:\n- [Blocker details]\n\nNext steps:\n- Address blockers\n- Submit revised document",
}

# Shared caches
security_cache = {}
scalability_cache = {}
cost_cache = {}


def run_agent_with_retry(agent_builder, prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            agent = agent_builder()
            result = agent(prompt)
            return clean_response(result)
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise

def build_security_agent():
    model = BedrockModel(model_id=NOVA_LITE_MODEL, region_name=AWS_REGION, temperature=0.0)
    
    @tool
    def review_security(document_id):
        result = SECURITY_FINDINGS.get(document_id, {"risk_level": "UNKNOWN", "critical_issues": [], "recommendation": "Review required"})
        security_cache[document_id] = result
        return json.dumps(result, indent=2)
    
    system_prompt = "You are a Security Specialist. Call review_security with document_id, then report: Risk Level, Critical Issues count, Recommendation"
    return Agent(model=model, system_prompt=system_prompt, tools=[review_security])

def build_scalability_agent():
    model = BedrockModel(model_id=CLAUDE_MODEL, region_name=AWS_REGION, temperature=0.1)
    
    @tool
    def review_scalability(document_id):
        result = SCALABILITY_FINDINGS.get(document_id, {"bottleneck_risk": "UNKNOWN", "scaling_challenges": [], "recommendation": "Review required"})
        scalability_cache[document_id] = result
        return json.dumps(result, indent=2)
    
    system_prompt = "You are a Scalability Specialist. Call review_scalability with document_id, then report: Bottleneck Risk, Scaling Challenges count, Recommendation"
    return Agent(model=model, system_prompt=system_prompt, tools=[review_scalability])

def build_cost_agent():
    model = BedrockModel(model_id=NOVA_PRO_MODEL, region_name=AWS_REGION, temperature=0.1)
    
    @tool
    def review_cost(document_id):
        result = COST_FINDINGS.get(document_id, {"cost_tier": "UNKNOWN", "cost_drivers": [], "recommendation": "Review required"})
        cost_cache[document_id] = result
        return json.dumps(result, indent=2)
    
    system_prompt = "You are a Cost Specialist. Call review_cost with document_id, then report: Cost Tier, Cost Drivers count, Recommendation"
    return Agent(model=model, system_prompt=system_prompt, tools=[review_cost])

def run_specialists_parallel(doc_id):
    """Run all three specialists in parallel using ThreadPoolExecutor."""
    timings = {}
    
    def run_security():
        return run_agent_with_retry(build_security_agent, f"Review security for document {doc_id}")
    
    def run_scalability():
        return run_agent_with_retry(build_scalability_agent, f"Review scalability for document {doc_id}")
    
    def run_cost():
        return run_agent_with_retry(build_cost_agent, f"Review cost for document {doc_id}")
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(run_security): "security",
            executor.submit(run_scalability): "scalability",
            executor.submit(run_cost): "cost",
        }
        for future in as_completed(futures):
            timings[futures[future]] = future.result()
    
    return timings

def analyze_document(document):
    """Analyze a single document using parallel specialists + synthesizer."""
    doc_id = document["id"]
    security_cache.clear()
    scalability_cache.clear()
    cost_cache.clear()
    
    start_time = time.time()
    specialist_results = run_specialists_parallel(doc_id)
    parallel_duration = time.time() - start_time
    
    synthesizer = build_synthesizer_agent()
    synthesis_result = synthesizer(f"Synthesize findings for {doc_id}: {document['title']}")
    synthesis_json = json.loads(clean_response(synthesis_result))
    
    total_duration = time.time() - start_time
    
    return {
        "document": {
            "id": document["id"],
            "title": document["title"],
            "description": document["description"],
        },
        "specialist_reports": specialist_results,
        "synthesis": synthesis_json,
        "timings": {
            "parallel_phase_seconds": round(parallel_duration, 2),
            "total_duration_seconds": round(total_duration, 2),
        },
    }

def run_analysis_pipeline(documents=None):
    """Run analysis pipeline for all documents."""
    documents = documents or DOCUMENTS
    results = []
    
    for doc in documents:
        result = analyze_document(doc)
        results.append(result)
        
        print(f"\n{'='*70}")
        print(f"DOCUMENT: {result['document']['title']} ({doc['id']})")
        print(f"{'='*70}")
        print(f"Decision: {result['synthesis']['decision']}")
        print(f"\nSpecialist Results:")
        for specialist, report in result['specialist_reports'].items():
            print(f"  - {specialist.title()}: {report[:100]}...")
        print(f"\nTimings:")
        print(f"  - Parallel phase: {result['timings']['parallel_phase_seconds']}s")
        print(f"  - Total: {result['timings']['total_duration_seconds']}s")
    
    return results

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Parallel Document Analysis Pipeline")
    parser.add_argument("--document-id", default=None, help="Analyze specific document")
    args = parser.parse_args()
    
    if args.document_id:
        docs = [d for d in DOCUMENTS if d["id"] == args.document_id]
        if not docs:
            print(f"Error: Document {args.document_id} not found")
            exit(1)
    else:
        docs = DOCUMENTS
    
    run_analysis_pipeline(docs)

if __name__ == "__main__":
    main()
