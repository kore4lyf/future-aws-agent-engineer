"""
agents/inventory/tools.py
==========================
Tool functions for the Inventory Agent.
Each tool is a standalone @tool that can be imported independently.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from strands import tool
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

import config

dynamodb = __import__('boto3').resource('dynamodb', region_name=config.AWS_REGION)


@tool
def check_order_status(customer_id: str, order_id: str) -> dict:
    """
    Look up one order in DynamoDB and report its status, product, dates
    and amount. Reports facts only - it does NOT decide return eligibility.

    Args:
        customer_id: The customer's unique identifier (e.g. CUST-001)
        order_id: The order identifier (e.g. ORD-27176)

    Returns:
        Order record (order_id, status, product_name, order_date, price, ...)
        or a not-found message
    """
    table = dynamodb.Table(config.ORDERS_TABLE)
    try:
        response = table.get_item(Key={'customer_id': customer_id, 'order_id': order_id})
        item = response.get('Item')
        if not item:
            return {'found': False, 'message': f'Order {order_id} for {customer_id} not found.'}
        return {'found': True, 'order': {k: item[k] for k in item if k != 'ttl'}}
    except ClientError as exc:
        return {'found': False, 'error': str(exc)}


@tool
def get_customer_tier(customer_id: str) -> dict:
    """
    Retrieve a customer's tier (Standard or Premium) from DynamoDB.
    Standard customers have a 30-day return window; Premium customers have 60 days.

    Args:
        customer_id: The customer's unique identifier

    Returns:
        Customer profile including tier and account details
    """
    table = dynamodb.Table(config.CUSTOMERS_TABLE)
    try:
        response = table.get_item(Key={'customer_id': customer_id})
        item = response.get('Item')
        if not item:
            return {'found': False, 'message': f'Customer {customer_id} not found.'}
        return {'found': True, 'customer': {k: item[k] for k in item}}
    except ClientError as exc:
        return {'found': False, 'error': str(exc)}


@tool
def list_customer_orders(customer_id: str) -> dict:
    """
    Retrieve all orders for a customer from DynamoDB.

    Args:
        customer_id: The customer's unique identifier

    Returns:
        List of all orders with order_id, status, order_date, and amount
    """
    table = dynamodb.Table(config.ORDERS_TABLE)
    try:
        response = table.query(
            KeyConditionExpression=Key('customer_id').eq(customer_id)
        )
        orders = [{k: item[k] for k in item if k != 'ttl'} for item in response.get('Items', [])]
        return {'found': True, 'orders': orders, 'count': len(orders)}
    except ClientError as exc:
        return {'found': False, 'error': str(exc)}
