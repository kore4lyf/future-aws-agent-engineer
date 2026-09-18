import json
import logging
import os
import re
import time

from dotenv import load_dotenv
from strands import Agent, tool
from strands.models import BedrockModel

load_dotenv()

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
NOVA_LITE_MODEL = os.environ.get("NOVA_LITE_MODEL", "amazon.nova-lite-v1:0")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
NOVA_PRO_MODEL = os.environ.get("NOVA_PRO_MODEL", "amazon.nova-pro-v1:0")

classification_cache = {}


def clean_response(text: str) -> str:
    return re.sub(r"<thinking>.*?</thinking>", "", str(text), flags=re.DOTALL).strip()


def run_agent_with_retry(agent_builder, prompt: str, max_retries: int = 3) -> str:
    for attempt in range(max_retries):
        try:
            agent = agent_builder()
            result = agent(prompt)
            return clean_response(result)
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2**attempt
                print(f"[Retry ({attempt + 1})/{max_retries}] ({e.__class__.__name__}), waiting ({wait}s...)")
                time.sleep(wait)
            else:
                print(f"[Failed] ({e.__class__.__name__}) after ({max_retries}) attempts")
                raise
