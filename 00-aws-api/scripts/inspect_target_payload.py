"""
Inspect the actual API constraint for create_gateway_target toolSchema.
Read the service model to see if 2 tools is really required.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import client

control = client("bedrock-agentcore-control")
sm = control._service_model
op = sm.operation_model("CreateGatewayTarget")

# Walk to: targetConfiguration.mcp.lambda.toolSchema.inlinePayload
mcp = op.input_shape.members["targetConfiguration"].members["mcp"]
lambda_cfg = mcp.members["lambda"]
tool_schema = lambda_cfg.members["toolSchema"]
inline = tool_schema.members["inlinePayload"]

print("inlinePayload:")
print(f"  type: {inline.type_name}")
print(f"  flattened: {inline.metadata.get('flattened', False)}")
print(f"  min length: {inline.metadata.get('min', 'not set')}")
print(f"  max length: {inline.metadata.get('max', 'not set')}")
print(f"  required: {op.input_shape.metadata.get('required', [])}")
print(f"  full metadata: {dict(inline.metadata)}")
