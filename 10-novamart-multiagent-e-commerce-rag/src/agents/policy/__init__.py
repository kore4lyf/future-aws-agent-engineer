"""
agents/policy/__init__.py
==========================
Policy Agent — multi-agent RAG coordinator.
Runs 3 specialized retriever sub-agents in parallel via ThreadPoolExecutor,
then synthesizes the combined results.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from strands import Agent, tool
from strands.models import BedrockModel
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from agents.policy.tools import _build_retrievers
from agent_orchestrator import trace


def build_policy_agent() -> Agent:
    """
    Build the Policy Agent - a multi-agent RAG system.

    Internally creates three specialized retriever sub-agents that run in
    PARALLEL, each querying its own Knowledge Base. The coordinator synthesizes
    the combined results into a complete, grounded policy answer.
    """
    returns_retriever, shipping_retriever, warranty_retriever = _build_retrievers()

    @tool
    def search_all_policies(query: str) -> str:
        """
        Query all three policy knowledge bases IN PARALLEL and return combined results.

        Runs ReturnsPolicyRetrieverAgent, ShippingPolicyRetrieverAgent, and
        WarrantyPolicyRetrieverAgent simultaneously, then combines their findings.

        Args:
            query: The customer's policy question

        Returns:
            Combined policy passages from all three knowledge bases
        """
        retrievers = {
            'Returns':  returns_retriever,
            'Shipping': shipping_retriever,
            'Warranty': warranty_retriever,
        }

        trace.kb_start({
            'Returns':  config.RETURNS_KB_ID,
            'Shipping': config.SHIPPING_KB_ID,
            'Warranty': config.WARRANTY_KB_ID,
        })

        def _run_retriever(domain: str, agent, query: str) -> tuple:
            result = agent(f"Retrieve policy information for: {query}")
            return domain, result

        results = {}
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(_run_retriever, domain, agent, query): domain
                for domain, agent in retrievers.items()
            }
            for future in as_completed(futures):
                domain, result = future.result()
                results[domain] = result

        trace.kb_done(len(results))
        for domain in ['Returns', 'Shipping', 'Warranty']:
            trace.kb_result(domain, results.get(domain, '[No results]'))

        return "\n\n".join(
            f"[{domain} Policy]\n{results.get(domain, 'No results')}"
            for domain in ['Returns', 'Shipping', 'Warranty']
        )

    model = BedrockModel(
        model_id=config.WORKER_MODEL_ID,
        region_name=config.AWS_REGION,
        temperature=0.2,
    )

    system_prompt = """You are the Policy Agent for NovaMart customer support.
You answer policy questions by running search_all_policies to retrieve
relevant passages from the Returns, Shipping, and Warranty knowledge bases,
then synthesizing them into a clear, grounded answer.

Always call search_all_policies FIRST before answering any policy question.
Quote specific policy details (time windows, conditions, exceptions) so the
Communication Agent can include them in the final customer response."""

    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[search_all_policies],
    )

