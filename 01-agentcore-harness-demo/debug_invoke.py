from dotenv import load_dotenv
import os
from pathlib import Path

root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / ".env")

import boto3
import json

config = json.load(open("demo_config.json"))

runtime = boto3.client("bedrock-agentcore", region_name=config["region"])

response = runtime.invoke_harness(
    harnessArn=config["harness_arn"],
    runtimeSessionId="debugsession1234567890abcdef1234567890ab",
    messages=[{"role": "user", "content": [{"text": "What is the weather in Paris today?"}]}]
)

stream = response["stream"]
print("STREAM TYPE:", type(stream))
count = 0
for event in stream:
    count += 1
    print(f"\n--- EVENT {count} keys: {list(event.keys())} ---")
    for k, v in event.items():
        print(f"  {k}: {json.dumps(v, default=str)[:400]}")
    if count >= 15:
        print("... (truncated)")
        break
print(f"\nTOTAL EVENTS READ: {count}")
