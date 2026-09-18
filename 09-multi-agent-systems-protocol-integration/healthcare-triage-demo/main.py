import argparse
import json

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from src.main import PATIENT_COMPLAINTS, run_triage_pipeline

app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload, context=None):
    payload = payload or {}
    patient_id = payload.get("patient_id")
    patient = next(
        (p for p in PATIENT_COMPLAINTS if p["patient_id"] == patient_id),
        PATIENT_COMPLAINTS[0],
    )
    return run_triage_pipeline(patient)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the healthcare triage pipeline")
    parser.add_argument("--patient-id", default=None)
    args = parser.parse_args()
    if args.patient_id:
        patients = [p for p in PATIENT_COMPLAINTS if p["patient_id"] == args.patient_id]
    else:
        patients = PATIENT_COMPLAINTS
    for patient in patients:
        print(json.dumps(run_triage_pipeline(patient), indent=2))


if __name__ == "__main__":
    main()
