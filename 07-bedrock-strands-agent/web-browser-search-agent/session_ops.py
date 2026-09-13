import boto3
for svc in ['bedrock-agentcore', 'bedrock-agentcore-control']:
    c = boto3.client(svc, region_name='us-east-1')
    ops = [op for op in c.meta.service_model.operation_names if 'ession' in op]
    print(svc, ops)
