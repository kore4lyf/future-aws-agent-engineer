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
from pydantic import ValidationError

import config
from agents.inventory.schema import (
    CheckOrderStatusInput,
    CheckOrderStatusOutput,
    GetCustomerTierInput,
    GetCustomerTierOutput,
    ListCustomerOrdersInput,
    ListCustomerOrdersOutput,
    OrderItem,
    OrderSummary,
)

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
    input_data = CheckOrderStatusInput(customer_id=customer_id, order_id=order_id)
    table = dynamodb.Table(config.ORDERS_TABLE)
    try:
        response = table.get_item(Key={'customer_id': input_data.customer_id, 'order_id': input_data.order_id})
        item = response.get('Item')
        if not item:
            output = CheckOrderStatusOutput(found=False, message=f'Order {input_data.order_id} for {input_data.customer_id} not found.')
            return output.model_dump()
        order_data = {k: item[k] for k in item if k != 'ttl'}
        try:
            order = OrderItem.model_validate(order_data)
        except ValidationError as exc:
            output = CheckOrderStatusOutput(found=False, error=f"Order data validation failed: {exc}")
            return output.model_dump()
        output = CheckOrderStatusOutput(found=True, order=order)
        return output.model_dump()
    except ClientError as exc:
        output = CheckOrderStatusOutput(found=False, error=str(exc))
        return output.model_dump()


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
    input_data = GetCustomerTierInput(customer_id=customer_id)
    table = dynamodb.Table(config.CUSTOMERS_TABLE)
    try:
        response = table.get_item(Key={'customer_id': input_data.customer_id})
        item = response.get('Item')
        if not item:
            output = GetCustomerTierOutput(found=False, message=f'Customer {input_data.customer_id} not found.')
            return output.model_dump()
        try:
            customer = CustomerProfile.model_validate(item)
        except ValidationError as exc:
            output = GetCustomerTierOutput(found=False, error=f"Customer data validation failed: {exc}")
            return output.model_dump()
        output = GetCustomerTierOutput(found=True, customer=customer)
        return output.model_dump()
    except ClientError as exc:
        output = GetCustomerTierOutput(found=False, error=str(exc))
        return output.model_dump()


@tool
def list_customer_orders(customer_id: str) -> dict:
    """
    Retrieve all orders for a customer from DynamoDB.

    Args:
        customer_id: The customer's unique identifier

    Returns:
        List of all orders with order_id, status, order_date, and amount
    """
    input_data = ListCustomerOrdersInput(customer_id=customer_id)
    table = dynamodb.Table(config.ORDERS_TABLE)
    try:
        response = table.query(
            KeyConditionExpression=Key('customer_id').eq(input_data.customer_id)
        )
        orders = []
        for item in response.get('Items', []):
            try:
                order_data = {k: item[k] for k in item if k != 'ttl'}
                orders.append(OrderSummary.model_validate(order_data))
            except ValidationError:
                continue
        output = ListCustomerOrdersOutput(found=True, orders=orders, count=len(orders))
        return output.model_dump()
    except ClientError as exc:
        output = ListCustomerOrdersOutput(found=False, error=str(exc))
        return output.model_dump()
