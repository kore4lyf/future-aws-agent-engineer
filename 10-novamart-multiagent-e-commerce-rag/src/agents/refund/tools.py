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
from pydantic import ValidationError

import config
import uuid
from agents.refund.schema import (
    GetInventoryContextInput,
    GetInventoryContextOutput,
    InitiateRefundInput,
    InitiateRefundOutput,
)

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
    input_data = GetInventoryContextInput(session_id=session_id)
    from agent_orchestrator import _read_workflow_state
    try:
        state = _read_workflow_state(input_data.session_id)
        if not state:
            output = GetInventoryContextOutput(error='WorkflowState not found for this session.')
            return output.model_dump()
        raw = state.get('inventory_agent')
        if raw is None:
            return GetInventoryContextOutput().model_dump()
        if isinstance(raw, str):
            return GetInventoryContextOutput(inventory_agent=raw).model_dump()
        try:
            validated = GetInventoryContextOutput.model_validate({'inventory_agent': raw})
            return validated.model_dump()
        except ValidationError:
            return GetInventoryContextOutput(inventory_agent=str(raw)).model_dump()
    except ClientError as exc:
        return GetInventoryContextOutput(error=str(exc)).model_dump()


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
    input_data = InitiateRefundInput(customer_id=customer_id, order_id=order_id, reason=reason)
    table = dynamodb.Table(config.ORDERS_TABLE)
    return_ref = f"RMA-{uuid.uuid4().hex[:8].upper()}"
    try:
        existing = table.get_item(Key={'customer_id': input_data.customer_id, 'order_id': input_data.order_id})
        if 'Item' not in existing:
            output = InitiateRefundOutput(
                success=False,
                error=f"Order {input_data.order_id} for customer {input_data.customer_id} not found.",
            )
            return output.model_dump()
        table.update_item(
            Key={'customer_id': input_data.customer_id, 'order_id': input_data.order_id},
            UpdateExpression='SET #s = :s, return_reason = :r, return_ref = :ref',
            ExpressionAttributeNames={'#s': 'status'},
            ConditionExpression='attribute_exists(customer_id)',
            ExpressionAttributeValues={
                ':s': 'returned',
                ':r': input_data.reason,
                ':ref': return_ref,
            },
        )
        output = InitiateRefundOutput(
            success=True,
            return_reference=return_ref,
            message=f'Return initiated for order {input_data.order_id}. Reference: {return_ref}',
        )
        return output.model_dump()
    except ClientError as exc:
        output = InitiateRefundOutput(success=False, error=str(exc))
        return output.model_dump()
