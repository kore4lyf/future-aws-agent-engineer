import boto3
import json
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Sample meeting notes
# ---------------------------------------------------------------------------
MEETING_NOTES = """\
Meeting – Q3 Product Review
Date: Thursday afternoon
Attendees: Sarah (PM), Jake (Eng Lead), Priya (Design), Tom (QA)

Started about 10 minutes late. Sarah opened by saying the search feature is running
roughly two weeks behind schedule because the ranking algorithm keeps failing QA.
Tom confirmed three test cases are still red.

Jake said the core indexing work is done and the delay is entirely on ranking.
He proposed cutting the fuzzy-match feature from v1 and shipping exact-match only
to hit the release date. Sarah agreed; fuzzy-match moves to the backlog.

Priya raised a concern: the empty-state illustration hasn't been reviewed yet.
Sarah asked Priya to share it in Slack by Friday EOD for async feedback.

Budget question came up: Jake mentioned the new search infrastructure will add
roughly $2000/month to the AWS bill. Sarah said she'd confirm with Finance
whether that fits Q3 budget before the next sprint.

Wrap-up: next sync same time next week.
"""


# ---------------------------------------------------------------------------
# InvokeModel with streaming
# ---------------------------------------------------------------------------
def summarize_notes_stream(notes: str) -> str:

    bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
    model_id = "amazon.nova-pro-v1:0"

    prompt = (
        "Summarize the following meeting notes into:\n"
        "1. Key decisions made\n"
        "2. Action items with owners\n\n"
        "Meeting notes:\n"
        "<notes>\n"
        f"{notes}\n"
        "/<notes>\n"
    )

    body = {
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": 512, "temperature": 0.0},
    }

    response = bedrock.invoke_model_with_response_stream(
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )

    for event in response["body"]:
        chunk = json.loads(event["chunk"]["bytes"])
        if "contentBlockDelta" in chunk:
            print(chunk["contentBlockDelta"]["delta"].get("text", ""), end="", flush=True)

    print()  # final newline


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== InvokeModelWithResponseStream ===\n")
    summarize_notes_stream(MEETING_NOTES)
