"""
deploy/guardrail.py
===================
Task 3a - Bedrock Guardrail creation.

Moved from agent_orchestrator.py lines ~306-443.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3
from botocore.exceptions import ClientError

import config


__all__ = ['create_guardrail']


def create_guardrail() -> tuple[str, str]:
    """
    Create a Bedrock Guardrail for enterprise safety enforcement.

    Blocks harmful content, PII exposure, off-topic subjects, and profanity.
    Returns (guardrail_id, guardrail_version).
    """
    bedrock_client = boto3.client('bedrock', region_name=config.AWS_REGION)

    # Check if guardrail already exists to avoid duplicates
    try:
        existing = bedrock_client.list_guardrails()
        for g in existing.get('guardrails', []):
            if g['name'] == config.GUARDRAIL_NAME:
                guardrail_id = g['id']
                versions = bedrock_client.list_guardrail_versions(guardrailIdentifier=guardrail_id)
                guardrail_version = 'DRAFT'
                for v in versions.get('guardrailVersions', []):
                    if v.get('version', 'DRAFT') != 'DRAFT':
                        guardrail_version = v['version']
                print(f"Guardrail already exists: {guardrail_id} (version: {guardrail_version})")
                return guardrail_id, guardrail_version
    except ClientError as exc:
        print(f"[Note] Could not check existing guardrails: {exc}")

    # Build the four policy blocks required by the rubric.
    content_policy = {
        'filtersConfig': [
            {'type': 'SEXUAL',    'inputStrength': 'HIGH',   'outputStrength': 'HIGH'},
            {'type': 'VIOLENCE',  'inputStrength': 'HIGH',   'outputStrength': 'HIGH'},
            {'type': 'HATE',      'inputStrength': 'HIGH',   'outputStrength': 'HIGH'},
            {'type': 'INSULTS',   'inputStrength': 'MEDIUM', 'outputStrength': 'MEDIUM'},
            {'type': 'MISCONDUCT','inputStrength': 'MEDIUM', 'outputStrength': 'MEDIUM'},
        ]
    }

    pii_policy = {
        'piiEntitiesConfig': [
            {'type': 'CREDIT_DEBIT_CARD_NUMBER', 'action': 'BLOCK'},
            {'type': 'US_SOCIAL_SECURITY_NUMBER', 'action': 'BLOCK'},
            {'type': 'EMAIL', 'action': 'ANONYMIZE'},
            {'type': 'PHONE', 'action': 'ANONYMIZE'},
        ]
    }

    topic_policy = {
        'topicsConfig': [
            {
                'type': 'DENY',
                'name': 'CompetitorProducts',
                'definition': (
                    'Mentions of competitor brands, products, or services, '
                    'or requests to compare NovaMart with competing retailers.'
                ),
                'examples': [
                    'Does Amazon have a better deal on headphones?',
                    'Compare your product with Best Buy',
                    'I want to buy from a competitor instead',
                ],
            },
            {
                'type': 'DENY',
                'name': 'PricingNegotiations',
                'definition': (
                    'Haggling, requests to change an advertised price, '
                    'or negotiations over discounts. Arithmetic using an already '
                    'specified price and discount is allowed.'
                ),
                'examples': [
                    'Can you give me a lower price than the listed amount?',
                    'I want to negotiate the price of this item',
                    'Match a competitor price for this product',
                ],
            },
            {
                'type': 'DENY',
                'name': 'LegalThreats',
                'definition': (
                    'Legal threats, lawsuits, attorney requests, or claims '
                    'of liability against NovaMart.'
                ),
                'examples': [
                    'I will sue if you do not process this return',
                    'I want to speak to a lawyer about your service',
                    'This is a legal threat against your company',
                ],
            },
        ],
        'tierConfig': {'tierName': 'STANDARD'},
    }

    word_policy = {
        'managedWordListsConfig': [
            {'type': 'PROFANITY'},
        ]
    }

    print("Creating Bedrock Guardrail...")
    try:
        response = bedrock_client.create_guardrail(
            name=config.GUARDRAIL_NAME,
            description=(
                'NovaMart customer support guardrail: content safety, PII protection, '
                'topic denial, and profanity filtering.'
            ),
            blockedInputMessaging=(
                'This request was blocked by the NovaMart safety guardrail.'
            ),
            blockedOutputsMessaging=(
                'This response was blocked by the NovaMart safety guardrail.'
            ),
            contentPolicyConfig=content_policy,
            sensitiveInformationPolicyConfig=pii_policy,
            topicPolicyConfig=topic_policy,
            wordPolicyConfig=word_policy,
            crossRegionConfig={'guardrailProfileIdentifier': 'us.guardrail.v1:0'},
        )
    except ClientError as exc:
        print(f"[Failed] create_guardrail: {exc}")
        raise

    guardrail_id = response['guardrailId']
    print(f"  Guardrail created: {guardrail_id}")

    # Promote from DRAFT to a numbered version.
    try:
        version_response = bedrock_client.create_guardrail_version(
            guardrailIdentifier=guardrail_id,
            description='Initial numbered version for NovaMart customer support.',
        )
    except ClientError as exc:
        print(f"[Failed] create_guardrail_version: {exc}")
        raise

    guardrail_version = version_response['version']
    print(f"  Guardrail version published: {guardrail_version}")

    return guardrail_id, guardrail_version
