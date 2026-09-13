import boto3, json
ctl = boto3.client('bedrock-agentcore-control', region_name='us-east-1')
rt = boto3.client('bedrock-agentcore', region_name='us-east-1')
browsers = ctl.list_browsers()
print(json.dumps(browsers.get('browsers', browsers), indent=2, default=str)[:2000])
