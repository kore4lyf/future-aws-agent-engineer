import boto3
c = boto3.client('bedrock-agentcore-control', region_name='us-east-1')
ops = [op for op in c.meta.service_model.operation_names if 'rowser' in op]
print(ops)
