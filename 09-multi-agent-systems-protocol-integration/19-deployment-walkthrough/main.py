# AgentCore Runtime entrypoint for Lesson 10 demo.
# This file is packaged into deployment.zip and uploaded to S3.

def main(event: dict, context: Any) -> dict:
    """Minimal entrypoint for the insurance claims runtime."""
    return {
        "statusCode": 200,
        "body": "Insurance Claims Runtime is healthy.",
    }
