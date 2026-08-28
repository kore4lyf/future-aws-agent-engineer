"""
Text Helper Flow - Create and Deploy

This script creates a Bedrock Flow that:
1. Accepts a user message
2. Classifies the intent (summarize, rewrite, or other)
3. Routes to the appropriate specialist prompt
4. Returns the result

We use boto3 to interact with the Bedrock Agent API.
"""

import boto3
import json
import os
from dotenv import load_dotenv
from botocore.exceptions import ClientError

# Load environment variables from .env file
load_dotenv()

# Create a Bedrock Agent client
bedrock_agent = boto3.client('bedrock-agent', region_name='us-east-1')

# =============================================================================
# Flow Metadata
# =============================================================================

FLOW_NAME = "text-helper-flow"
FLOW_DESCRIPTION = "A flow that classifies user intent and routes to specialist prompts"

EXECUTION_ROLE_ARN = os.getenv('EXECUTION_ROLE_ARN')
if not EXECUTION_ROLE_ARN:
    raise ValueError("EXECUTION_ROLE_ARN not found in .env file")

print(f"Flow name: {FLOW_NAME}")
print(f"Execution role ARN: {EXECUTION_ROLE_ARN}")

# =============================================================================
# Flow Definition - Key fixes based on validation errors
# =============================================================================

# Key learnings:
# 1. FlowInput outputs 'document' (required by Bedrock)
# 2. Prompt nodes output 'modelCompletion' (required by Bedrock)
# 3. FlowOutput inputs 'document' (required by Bedrock)
# 4. Expressions use $.data.NodeName.outputName format
# 5. Condition expressions use input variable names directly
# 6. Condition node needs a default condition

CLASSIFIER_PROMPT = """You are an intent classifier. Your job is to analyze the user's message and determine what they want to do with their text.

Classify the user's intent into one of these three categories:
- summarize: The user wants a summary of their text
- rewrite: The user wants their text improved for clarity, grammar, or style
- other: The user's intent is unclear, or they want something else

Respond with ONLY one of these words:
summarize
rewrite
other

Do not include any other text, explanations, or formatting. Just the word.

User message:
{{input}}"""

SUMMARIZER_PROMPT = """You are a text summarization specialist. Your job is to create a clear, structured summary of the user's text.

Produce a summary with these sections:

## Key Points
- [Main point 1]
- [Main point 2]
- [Main point 3]

## Main Takeaway
[One sentence that captures the essence]

Be concise but comprehensive. Focus on the most important information.

User text:
{{input}}"""

REWRITER_PROMPT = """You are a text rewriting specialist. Your job is to improve the clarity, grammar, and flow of the user's text while preserving the original meaning.

Rewrite the text to be:
- Clear and easy to understand
- Grammatically correct
- Well-structured
- Professional in tone

Do not add new information or change the meaning. Only improve the writing quality.

Original text:
{{input}}"""

CLARIFIER_PROMPT = """You are a helpful assistant. The user's message was unclear about what they want to do with their text.

Acknowledge their message and help them understand their options:

1. Summarize - If they want a concise summary of their text
2. Rewrite - If they want their text improved for clarity and grammar

Ask them to specify which option they'd like, or provide more details about what they need.

Be friendly and helpful. Guide them toward a clear request.

User message:
{{input}}"""

flow_definition = {
    'nodes': [
        # 1. Input Node - Entry point
        {
            'name': 'FlowInput',
            'type': 'Input',
            'configuration': {
                'input': {}
            },
            'inputs': [],
            'outputs': [
                {
                    'name': 'document',
                    'type': 'String'
                }
            ]
        },
        # 2. Classifier Prompt - Classify intent
        {
            'name': 'Classifier',
            'type': 'Prompt',
            'configuration': {
                'prompt': {
                    'sourceConfiguration': {
                        'inline': {
                            'templateType': 'TEXT',
                            'templateConfiguration': {
                                'text': {
                                    'text': CLASSIFIER_PROMPT,
                                    'inputVariables': [
                                        {
                                            'name': 'input'
                                        }
                                    ]
                                }
                            },
                            'modelId': 'amazon.nova-pro-v1:0'
                        }
                    }
                }
            },
            'inputs': [
                {
                    'name': 'input',
                    'type': 'String',
                    'expression': '$.data'
                }
            ],
            'outputs': [
                {
                    'name': 'modelCompletion',
                    'type': 'String'
                }
            ]
        },
        # 3. Condition Node - Route based on intent
        {
            'name': 'RouteByIntent',
            'type': 'Condition',
            'configuration': {
                'condition': {
                    'conditions': [
                        {
                            'name': 'summarize',
                            'expression': 'conditionInput == "summarize"'
                        },
                        {
                            'name': 'rewrite',
                            'expression': 'conditionInput == "rewrite"'
                        },
                        {
                            'name': 'default'
                        }
                    ]
                }
            },
            'inputs': [
                {
                    'name': 'conditionInput',
                    'type': 'String',
                    'expression': '$.data'
                }
            ],
            'outputs': []
        },
        # 4. Summarizer Prompt - Handle summarize intent
        {
            'name': 'Summarizer',
            'type': 'Prompt',
            'configuration': {
                'prompt': {
                    'sourceConfiguration': {
                        'inline': {
                            'templateType': 'TEXT',
                            'templateConfiguration': {
                                'text': {
                                    'text': SUMMARIZER_PROMPT,
                                    'inputVariables': [
                                        {
                                            'name': 'input'
                                        }
                                    ]
                                }
                            },
                            'modelId': 'amazon.nova-pro-v1:0'
                        }
                    }
                }
            },
            'inputs': [
                {
                    'name': 'input',
                    'type': 'String',
                    'expression': '$.data'
                }
            ],
            'outputs': [
                {
                    'name': 'modelCompletion',
                    'type': 'String'
                }
            ]
        },
        # 5. Rewriter Prompt - Handle rewrite intent
        {
            'name': 'Rewriter',
            'type': 'Prompt',
            'configuration': {
                'prompt': {
                    'sourceConfiguration': {
                        'inline': {
                            'templateType': 'TEXT',
                            'templateConfiguration': {
                                'text': {
                                    'text': REWRITER_PROMPT,
                                    'inputVariables': [
                                        {
                                            'name': 'input'
                                        }
                                    ]
                                }
                            },
                            'modelId': 'amazon.nova-pro-v1:0'
                        }
                    }
                }
            },
            'inputs': [
                {
                    'name': 'input',
                    'type': 'String',
                    'expression': '$.data'
                }
            ],
            'outputs': [
                {
                    'name': 'modelCompletion',
                    'type': 'String'
                }
            ]
        },
        # 6. Clarifier Prompt - Handle other/unclear intent
        {
            'name': 'Clarifier',
            'type': 'Prompt',
            'configuration': {
                'prompt': {
                    'sourceConfiguration': {
                        'inline': {
                            'templateType': 'TEXT',
                            'templateConfiguration': {
                                'text': {
                                    'text': CLARIFIER_PROMPT,
                                    'inputVariables': [
                                        {
                                            'name': 'input'
                                        }
                                    ]
                                }
                            },
                            'modelId': 'amazon.nova-pro-v1:0'
                        }
                    }
                }
            },
            'inputs': [
                {
                    'name': 'input',
                    'type': 'String',
                    'expression': '$.data'
                }
            ],
            'outputs': [
                {
                    'name': 'modelCompletion',
                    'type': 'String'
                }
            ]
        },
        # 7. Output Node for Summarizer
        {
            'name': 'SummarizerOutput',
            'type': 'Output',
            'configuration': {
                'output': {}
            },
            'inputs': [
                {
                    'name': 'document',
                    'type': 'String',
                    'expression': '$.data'
                }
            ],
            'outputs': []
        },
        # 8. Output Node for Rewriter
        {
            'name': 'RewriterOutput',
            'type': 'Output',
            'configuration': {
                'output': {}
            },
            'inputs': [
                {
                    'name': 'document',
                    'type': 'String',
                    'expression': '$.data'
                }
            ],
            'outputs': []
        },
        # 9. Output Node for Clarifier
        {
            'name': 'ClarifierOutput',
            'type': 'Output',
            'configuration': {
                'output': {}
            },
            'inputs': [
                {
                    'name': 'document',
                    'type': 'String',
                    'expression': '$.data'
                }
            ],
            'outputs': []
        }
    ],
    'connections': [
        # Input -> Classifier
        {
            'type': 'Data',
            'name': 'input_to_classifier',
            'source': 'FlowInput',
            'target': 'Classifier',
            'configuration': {
                'data': {
                    'sourceOutput': 'document',
                    'targetInput': 'input'
                }
            }
        },
        # Classifier -> Condition
        {
            'type': 'Data',
            'name': 'classifier_to_condition',
            'source': 'Classifier',
            'target': 'RouteByIntent',
            'configuration': {
                'data': {
                    'sourceOutput': 'modelCompletion',
                    'targetInput': 'conditionInput'
                }
            }
        },
        # Condition -> Summarizer (when summarize)
        {
            'type': 'Conditional',
            'name': 'route_to_summarizer',
            'source': 'RouteByIntent',
            'target': 'Summarizer',
            'configuration': {
                'conditional': {
                    'condition': 'summarize'
                }
            }
        },
        # Condition -> Rewriter (when rewrite)
        {
            'type': 'Conditional',
            'name': 'route_to_rewriter',
            'source': 'RouteByIntent',
            'target': 'Rewriter',
            'configuration': {
                'conditional': {
                    'condition': 'rewrite'
                }
            }
        },
        # Condition -> Clarifier (default)
        {
            'type': 'Conditional',
            'name': 'route_to_clarifier',
            'source': 'RouteByIntent',
            'target': 'Clarifier',
            'configuration': {
                'conditional': {
                    'condition': 'default'
                }
            }
        },
        # FlowInput -> Summarizer (data)
        {
            'type': 'Data',
            'name': 'input_to_summarizer',
            'source': 'FlowInput',
            'target': 'Summarizer',
            'configuration': {
                'data': {
                    'sourceOutput': 'document',
                    'targetInput': 'input'
                }
            }
        },
        # FlowInput -> Rewriter (data)
        {
            'type': 'Data',
            'name': 'input_to_rewriter',
            'source': 'FlowInput',
            'target': 'Rewriter',
            'configuration': {
                'data': {
                    'sourceOutput': 'document',
                    'targetInput': 'input'
                }
            }
        },
        # FlowInput -> Clarifier (data)
        {
            'type': 'Data',
            'name': 'input_to_clarifier',
            'source': 'FlowInput',
            'target': 'Clarifier',
            'configuration': {
                'data': {
                    'sourceOutput': 'document',
                    'targetInput': 'input'
                }
            }
        },
        # Summarizer -> SummarizerOutput
        {
            'type': 'Data',
            'name': 'summarizer_to_output',
            'source': 'Summarizer',
            'target': 'SummarizerOutput',
            'configuration': {
                'data': {
                    'sourceOutput': 'modelCompletion',
                    'targetInput': 'document'
                }
            }
        },
        # Rewriter -> RewriterOutput
        {
            'type': 'Data',
            'name': 'rewriter_to_output',
            'source': 'Rewriter',
            'target': 'RewriterOutput',
            'configuration': {
                'data': {
                    'sourceOutput': 'modelCompletion',
                    'targetInput': 'document'
                }
            }
        },
        # Clarifier -> ClarifierOutput
        {
            'type': 'Data',
            'name': 'clarifier_to_output',
            'source': 'Clarifier',
            'target': 'ClarifierOutput',
            'configuration': {
                'data': {
                    'sourceOutput': 'modelCompletion',
                    'targetInput': 'document'
                }
            }
        }
    ]
}

print(f"\nFlow definition assembled with {len(flow_definition['nodes'])} nodes and {len(flow_definition['connections'])} connections")

# =============================================================================
# Create the Flow
# =============================================================================

def create_flow():
    """Create the Bedrock Flow using the AWS API."""
    
    print(f"\n{'='*60}")
    print(f"Creating Bedrock Flow: {FLOW_NAME}")
    print(f"{'='*60}")
    
    # First, try to delete existing flow if it exists
    try:
        existing_flows = bedrock_agent.list_flows()
        for flow in existing_flows.get('flowSummaries', []):
            if flow['name'] == FLOW_NAME:
                print(f"Deleting existing flow: {flow['id']}")
                bedrock_agent.delete_flow(flowIdentifier=flow['id'])
                print(f"Flow deleted successfully")
                break
    except ClientError as e:
        print(f"Error listing flows: {e.response['Error']['Message']}")
    
    # Now create the flow
    try:
        response = bedrock_agent.create_flow(
            name=FLOW_NAME,
            description=FLOW_DESCRIPTION,
            executionRoleArn=EXECUTION_ROLE_ARN,
            definition=flow_definition
        )
        
        flow_id = response['id']
        flow_arn = response['arn']
        flow_status = response['status']
        
        print(f"Flow created successfully!")
        print(f"  - Flow ID: {flow_id}")
        print(f"  - Flow ARN: {flow_arn}")
        print(f"  - Status: {flow_status}")
        
        return flow_id, flow_arn
        
    except ClientError as e:
        print(f"Error creating flow: {e.response['Error']['Message']}")
        raise

# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    flow_id, flow_arn = create_flow()
    
    # Prepare the flow
    print(f"\n{'='*60}")
    print(f"Preparing Bedrock Flow: {flow_id}")
    print(f"{'='*60}")
    
    try:
        prepare_response = bedrock_agent.prepare_flow(flowIdentifier=flow_id)
        print(f"Flow prepared successfully!")
        print(f"  - Status: {prepare_response.get('status')}")
    except ClientError as e:
        print(f"Error preparing flow: {e.response['Error']['Message']}")
    
    # Create a flow alias
    print(f"\n{'='*60}")
    print(f"Creating Flow Alias: latest")
    print(f"{'='*60}")
    
    try:
        # First, create a version of the flow
        version_response = bedrock_agent.create_flow_version(
            flowIdentifier=flow_id,
            description='Initial version'
        )
        version = version_response['version']
        print(f"Created flow version: {version}")
        
        # Now create the alias pointing to this version
        alias_response = bedrock_agent.create_flow_alias(
            flowIdentifier=flow_id,
            name='latest',
            routingConfiguration=[
                {
                    'flowVersion': version
                }
            ]
        )
        alias_arn = alias_response['arn']
        print(f"Alias created successfully!")
        print(f"  - Alias ARN: {alias_arn}")
        
        # Save the alias ARN for the test script
        with open('.env', 'a') as f:
            f.write(f'\nFLOW_ALIAS_ARN={alias_arn}\n')
        print(f"  - Saved to .env file")
        
    except ClientError as e:
        print(f"Error creating alias: {e.response['Error']['Message']}")
    
    print(f"\n{'='*60}")
    print(f"Next Steps:")
    print(f"{'='*60}")
    print(f"1. Test the flow: Run test_flow.py")
    print(f"2. Clean up: Run cleanup.py to delete the flow")