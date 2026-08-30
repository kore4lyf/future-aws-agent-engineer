import boto3
from pathlib import Path
from dotenv import load_dotenv

root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / ".env")

bedrock = boto3.client('bedrock-agentcore-control', region_name='us-east-1')

# Check gateways and targets
gateways = bedrock.list_gateways()
for g in gateways.get('items', []):
    print(f"Gateway: {g['name']} ({g['gatewayId']})")
    targets = bedrock.list_gateway_targets(gatewayIdentifier=g['gatewayId'])
    for t in targets.get('items', []):
        print(f"  Target: {t['name']} ({t['targetId']})")
        print(f"  Status: {t.get('status')}")
        print(f"  Config: {t.get('targetConfiguration')}")

# Check Lambda permissions
lambda_client = boto3.client('lambda', region_name='us-east-1')
try:
    fn = lambda_client.get_function(FunctionName='bug-report-tool-stack-create-bug-report')
    print(f"\nLambda ARN: {fn['Configuration']['FunctionArn']}")
    print(f"Runtime: {fn['Configuration']['Runtime']}")
    print(f"Handler: {fn['Configuration']['Handler']}")
    
    # Check Lambda policy
    try:
        policy = lambda_client.get_policy(FunctionName='bug-report-tool-stack-create-bug-report')
        import json
        print(f"Policy: {policy['Policy']}")
    except:
        print("No policy attached")
except Exception as e:
    print(f"Lambda error: {e}")
