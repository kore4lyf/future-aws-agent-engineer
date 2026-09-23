import argparse
import json

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from src.main import run_incident_pipeline

app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload, context=None):
    payload = payload or {}
    return run_incident_pipeline(payload.get("incident_id"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the incident response pipeline")
    parser.add_argument("--incident-id", default=None)
    args = parser.parse_args()
    print(json.dumps(run_incident_pipeline(args.incident_id), indent=2))


if __name__ == "__main__":
    main()
