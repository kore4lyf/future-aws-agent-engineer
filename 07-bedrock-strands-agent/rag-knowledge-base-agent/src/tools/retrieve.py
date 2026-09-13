import os
import boto3
from dotenv import load_dotenv
from strands import tool

load_dotenv()

KB_ID = os.getenv("KNOWLEDGE_BASE_ID", "")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

_bedrock_runtime = boto3.client("bedrock-agent-runtime", region_name=AWS_REGION)

@tool
def search_knowledge_base(query: str) -> str:
    """
    Search Horizon Travel's knowledge base for travel policies,
    destination guides, baggage rules, and loyalty programme details.
    Use this when a customer asks about policies, destinations, or travel tips.

    Args:
        query: The question or topic to search for
    Returns:
        Relevant information retrieved from the knowledge base
    """
    resp = _bedrock_runtime.retrieve(
        knowledgeBaseId=KB_ID,
        retrievalQuery={"text": query},
    )
    results = resp.get("retrievalResults", [])
    if not results:
        return f"No information found for: {query}"
    chunks = [r["content"]["text"] for r in results]
    return "\n---\n".join(chunks)

retrieve = search_knowledge_base
