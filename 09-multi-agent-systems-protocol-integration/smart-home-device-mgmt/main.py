import argparse
import json

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from src.main import TEST_DEVICES, run_device_pipeline

app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload, context=None):
    payload = payload or {}
    device_id = payload.get("device_id", TEST_DEVICES[0])
    return run_device_pipeline(device_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the smart home device pipeline")
    parser.add_argument("--device-id", default=None)
    args = parser.parse_args()
    if args.device_id:
        devices = [args.device_id]
    else:
        devices = TEST_DEVICES
    for device_id in devices:
        print(json.dumps(run_device_pipeline(device_id), indent=2))


if __name__ == "__main__":
    main()
