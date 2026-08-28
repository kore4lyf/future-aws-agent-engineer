"""
Text Helper Flow - Test Script

This script tests the Bedrock Flow by invoking it with sample inputs.
"""

import boto3
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create Bedrock Agent Runtime client
bedrock_runtime = boto3.client('bedrock-agent-runtime', region_name='us-east-1')

# Flow ID and Alias ARN (from create_flow.py output)
FLOW_ID = '8MBRPPK7SU'
FLOW_ALIAS_ARN = 'arn:aws:bedrock:us-east-1:708026873259:flow/8MBRPPK7SU/alias/EPW3X0W5CZ'

def invoke_flow(user_message):
    """Invoke the Bedrock Flow with a user message."""
    
    print(f"\n{'='*60}")
    print(f"Invoking flow with message: {user_message[:50]}...")
    print(f"{'='*60}")
    
    try:
        response = bedrock_runtime.invoke_flow(
            flowIdentifier=FLOW_ID,
            flowAliasIdentifier=FLOW_ALIAS_ARN,
            inputs=[
                {
                    'nodeName': 'FlowInput',
                    'nodeOutputName': 'document',
                    'content': {
                        'document': user_message
                    }
                }
            ]
        )
        
        # Process the streaming response
        print(f"\nResponse:")
        print(f"-" * 40)
        
        full_response = ""
        output_node = None
        for event in response['responseStream']:
            if 'flowOutputEvent' in event:
                output = event['flowOutputEvent']
                output_node = output.get('nodeName', 'Unknown')
                if 'content' in output and 'document' in output['content']:
                    full_response = output['content']['document']
                    print(full_response)
            elif 'flowErrorEvent' in event:
                print(f"\nError: {event['flowErrorEvent']['message']}")
                return None
        
        print(f"-" * 40)
        print(f"Output node: {output_node}")
        return full_response
        
    except Exception as e:
        print(f"Error invoking flow: {e}")
        return None

# Test cases
test_cases = [
    {
        "name": "Summarize request",
        "input": "Please summarize this article about climate change and its effects on coastal cities.",
        "expected": "summarize"
    },
    {
        "name": "Rewrite request",
        "input": "Can you rewrite this paragraph to make it clearer and more professional?",
        "expected": "rewrite"
    },
    {
        "name": "Other/unclear request",
        "input": "Hello, how are you today?",
        "expected": "other"
    }
]

if __name__ == "__main__":
    print(f"Text Helper Flow - Test Script")
    print(f"Flow ID: {FLOW_ID}")
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n\nTest {i}: {test['name']}")
        print(f"Input: {test['input']}")
        print(f"Expected intent: {test['expected']}")
        
        result = invoke_flow(test['input'])
        
        if result:
            # Check if the response matches expected intent
            if test['expected'] == 'summarize' and 'Key Points' in result:
                print(f"PASS - Response contains structured summary")
            elif test['expected'] == 'rewrite' and 'rewrite' in result.lower() or 'improve' in result.lower():
                print(f"PASS - Response appears to be a rewrite")
            elif test['expected'] == 'other' and ('summarize' in result.lower() or 'rewrite' in result.lower()):
                print(f"PASS - Response asks for clarification")
            else:
                print(f"? UNCERTAIN - Response received, manual verification needed")