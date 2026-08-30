import boto3
import json
from pathlib import Path
from dotenv import load_dotenv

root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / ".env")

bedrock = boto3.client('bedrock-agentcore-control', region_name='us-east-1')

# Get full target details
targets = bedrock.list_gateway_targets(gatewayIdentifier='customer-support-gateway-nbqvvptr1i')
for t in targets.get('items', []):
    print(f"Target: {t['name']}")
    print(json.dumps(t, indent=2, default=str))
