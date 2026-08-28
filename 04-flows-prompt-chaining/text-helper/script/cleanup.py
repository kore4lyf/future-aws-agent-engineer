"""
Text Helper Flow - Cleanup Script

This script deletes the Bedrock Flow and its alias.
Run this when you're done testing to avoid ongoing charges.
"""

import boto3
from dotenv import load_dotenv
from botocore.exceptions import ClientError

# Load environment variables
load_dotenv()

# Create Bedrock Agent client
bedrock_agent = boto3.client('bedrock-agent', region_name='us-east-1')

# Flow ID (from create_flow.py output)
FLOW_ID = '8MBRPPK7SU'

def cleanup():
    """Delete the Bedrock Flow and its alias."""
    
    print(f"Cleaning up Bedrock Flow: {FLOW_ID}")
    print(f"{'='*60}")
    
    # List and delete aliases
    try:
        aliases = bedrock_agent.list_flow_aliases(flowIdentifier=FLOW_ID)
        for alias in aliases.get('flowAliasSummaries', []):
            alias_id = alias['id']
            alias_name = alias['name']
            print(f"Deleting alias: {alias_name} ({alias_id})")
            bedrock_agent.delete_flow_alias(
                flowIdentifier=FLOW_ID,
                aliasIdentifier=alias_id
            )
            print(f"  - Alias deleted successfully")
    except ClientError as e:
        print(f"Error listing/deleting aliases: {e.response['Error']['Message']}")
    
    # Delete the flow
    try:
        print(f"\nDeleting flow: {FLOW_ID}")
        bedrock_agent.delete_flow(flowIdentifier=FLOW_ID)
        print(f"Flow deleted successfully!")
    except ClientError as e:
        print(f"Error deleting flow: {e.response['Error']['Message']}")
    
    print(f"\n{'='*60}")
    print(f"Cleanup complete!")
    print(f"{'='*60}")

if __name__ == "__main__":
    cleanup()