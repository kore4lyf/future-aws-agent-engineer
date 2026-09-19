import argparse
import json

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from src.main import POSTS, run_moderation_pipeline

app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload, context=None):
    payload = payload or {}
    post_id = payload.get("post_id")
    if post_id:
        post = next((p for p in POSTS if p["id"] == post_id), None)
        if post is None:
            return {"error": f"Unknown post_id: {post_id}"}
        return run_moderation_pipeline(post)
    return [run_moderation_pipeline(p) for p in POSTS]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the content moderation pipeline")
    parser.add_argument("--post-id", default=None)
    args = parser.parse_args()
    if args.post_id:
        posts = [p for p in POSTS if p["id"] == args.post_id]
    else:
        posts = POSTS
    for post in posts:
        print(json.dumps(run_moderation_pipeline(post), indent=2))


if __name__ == "__main__":
    main()
