"""
agents/refund/tools.py
=======================
Tool functions for the Refund Agent.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from strands import tool
from botocore.exceptions import ClientError

import config
import uuid

dynamodb = __import__('boto3').resource('dynamodb', region_name=config.AWS_REGION)


@tool
def get_inventory_context(session_id: str) -> dict:
    """
    Read the WorkflowState to access facts gathered by the InventoryAgent.

    Args:
        session_id: The current session identifier

    Returns:
        The inventory_agent field from WorkflowState, or empty dict if not yet set
    """
    from agent_orchestrator import _read_workflow_state
    state = _read_workflow_state(session_id)
    if not state:
        return {'error': 'WorkflowState not found for this session.'}
    return state.get('inventory_agent', {})


@tool
def initiate_refund(customer_id: str, order_id: str, reason: str) -> dict:
    """
    Initiate a return by updating the order record in DynamoDB.

    Args:
        customer_id: The customer's unique identifier
        order_id: The order to return
        reason: Customer-provided reason for the return

    Returns:
        Confirmation dict with return_reference number and instructions
    """
    table = dynamodb.Table(config.ORDERS_TABLE)
    return_ref = f"RMA-{uuid.uuid4().hex[:8].upper()}"
    try:
        table.update_item(
            Key={'customer_id': customer_id, 'order_id': order_id},
            UpdateExpression='SET #s = :s, return_reason = :r, return_ref = :ref',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':s': 'returned',
                ':r': reason,
                ':ref': return_ref,
            },
        )
        return {
            'success': True,
            'return_reference': return_ref,
            'message': f'Return initiated for order {order_id}. Reference: {return_ref}',
        }
    except ClientError as exc:
        return {'success': False, 'error': str(exc)}
