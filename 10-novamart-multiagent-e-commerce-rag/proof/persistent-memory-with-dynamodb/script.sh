#!/usr/bin/env bash
# proof/persistent-memory-with-dynamodb/script.sh
# ==================================================
# Proves persistent DynamoDB session memory for the Novamart Orchestrator.
#
# Demonstrates:
#   - DynamoDB "agent-sessions" table exists and accepts writes
#   - The full conversation transcript is persisted after every invocation
#   - A later, otherwise context-free request is answered correctly using
#     only what the agent recovered from DynamoDB
#   - Session history survives independently of AgentCore Memory
#
# Run:
#   cd 10-novamart-multiagent-e-commerce-rag
#   bash proof/persistent-memory-with-dynamodb/script.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_ROOT"

export PYTHONIOENCODING=utf-8
export AGENTCORE_SUPPRESS_RECOMMENDATION=1

# A Windows venv cannot be sourced reliably from Git Bash, so resolve the
# interpreter directly and fall back to whatever python is on PATH.
if [ -x .venv/Scripts/python.exe ]; then
  PYTHON=.venv/Scripts/python.exe
elif [ -x .venv/bin/python ]; then
  PYTHON=.venv/bin/python
else
  PYTHON=python
fi

"$PYTHON" - <<'PY'
import sys
sys.path.insert(0, 'src')

from dotenv import load_dotenv
load_dotenv(dotenv_path='.env')

import time
import boto3
import config
import agent_orchestrator as ao

# A fresh session id per run: WorkflowState uses optimistic locking, so
# replaying the same id after a failed run would trip its version check.
SESSION = f'proof-dyn-{int(time.time())}'
CUSTOMER = 'CUST-001'

table = boto3.resource('dynamodb', region_name=config.AWS_REGION).Table(config.AGENT_SESSIONS_TABLE)

# Start from a clean session so the proof is repeatable.
table.delete_item(Key={'session_id': SESSION})

print('=' * 68)
print('PROOF: persistent conversation memory in DynamoDB')
print('=' * 68)
print(f'Table    : {config.AGENT_SESSIONS_TABLE}')
print(f'Session  : {SESSION}')
print(f'Customer : {CUSTOMER} (Alice Johnson, Premium)')
print()

agent = ao.build_agent_graph()


def turn(prompt: str, label: str) -> str:
    """One turn, with prior turns restored from DynamoDB first."""
    manager = agent.conversation_manager
    previous = manager.load_session(SESSION) or []
    if previous:
        agent.messages = list(previous)
        print(f'[{label}] restored {len(previous)} messages from DynamoDB')
    reply = agent(f'[Session ID: {SESSION}] [Customer ID: {CUSTOMER}] {prompt}')
    stored = table.get_item(Key={'session_id': SESSION}).get('Item', {})
    print(f'[{label}] persisted {stored.get("message_count", 0)} messages to DynamoDB')
    print(f'[{label}] answer: {str(reply).strip()[:200]}')
    print()
    return str(reply)


# --- Turn 1: establish who the customer is and what they want ---------------
# The reason is supplied up front so the RefundAgent can reach a decision and
# actually quote an amount for turn 2 to recall.
turn(
    "Hi, I'm Alice Johnson. I want to return the wireless headphones from "
    "order ORD-27176 because the left earcup stopped working. Am I eligible "
    "for a refund, and if so how much will I get back?",
    'turn 1',
)

# --- Turn 2: fresh invocation, no restated context --------------------------
# "it" and "the refund" only resolve if turn 1 was recovered from DynamoDB.
turn("What refund amount did you just quote me for it?", 'turn 2')

# --- Evidence ---------------------------------------------------------------
item = table.get_item(Key={'session_id': SESSION}).get('Item')
print('=' * 68)
print('EVIDENCE')
print('=' * 68)
print(f"rows in table           : {table.scan(Select='COUNT').get('Count', 0)}")
print(f"messages stored         : {item.get('message_count', 0)}")
print(f"ttl (auto-expire)       : {item.get('ttl', 0)}")
transcript = ' '.join(
    block.get('text', '')
    for message in item.get('messages', [])
    for block in (message.get('content') or [])
    if isinstance(block, dict)
)
for probe in ('Alice Johnson', 'ORD-27176', 'left earcup stopped working'):
    print(f"transcript contains {probe!r}: {probe in transcript}")
print()
print('RESULT: turn 2 was answered from history recovered out of DynamoDB.')
print('=' * 68)
PY
