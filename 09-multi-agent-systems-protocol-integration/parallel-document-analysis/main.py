import argparse
import json

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from src.main import DOCUMENTS, run_analysis_pipeline


app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload, context=None):
    payload = payload or {}
    document_id = payload.get("document_id")
    if document_id:
        document = next((d for d in DOCUMENTS if d["id"] == document_id), None)
        if document is None:
            return {"error": f"Unknown document_id: {document_id}"}
        return run_analysis_pipeline([document])
    return run_analysis_pipeline(DOCUMENTS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Parallel Document Analysis Pipeline")
    parser.add_argument("--document-id", default=None, help="Analyze specific document")
    args = parser.parse_args()
    
    if args.document_id:
        documents = [d for d in DOCUMENTS if d["id"] == args.document_id]
        if not documents:
            print(f"Error: Document {args.document_id} not found")
            return
    else:
        documents = DOCUMENTS
    
    results = run_analysis_pipeline(documents)
    for result in results:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
