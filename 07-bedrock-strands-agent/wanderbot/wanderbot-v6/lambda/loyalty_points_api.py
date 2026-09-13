import json

LOYALTY = {
    "hz-001": {"member_id": "hz-001", "name": "Alice Johnson", "tier": "Gold", "points": 45200, "status": "ACTIVE"},
    "hz-002": {"member_id": "hz-002", "name": "Bob Smith", "tier": "Silver", "points": 18750, "status": "ACTIVE"},
    "hz-003": {"member_id": "hz-003", "name": "Carol Lee", "tier": "Platinum", "points": 78900, "status": "ACTIVE"},
}


def lambda_handler(event, context):
    member_id = None
    try:
        member_id = event.get("pathParameters", {}).get("member_id") or event.get("member_id")
    except Exception:
        pass
    if not member_id:
        return {"statusCode": 400, "body": json.dumps({"error": "member_id required"})}
    member_id = member_id.lower()
    record = LOYALTY.get(member_id)
    if not record:
        return {"statusCode": 404, "body": json.dumps({"error": f"No loyalty record for {member_id}"})}
    return {"statusCode": 200, "headers": {"Content-Type": "application/json"}, "body": json.dumps(record)}
