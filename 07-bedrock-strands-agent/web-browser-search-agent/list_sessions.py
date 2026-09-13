import boto3
c = boto3.client('bedrock-agentcore', region_name='us-east-1')
r = c.list_browser_sessions()
import json
print(json.dumps(r.get('sessions', r), indent=2, default=str)[:3000])
