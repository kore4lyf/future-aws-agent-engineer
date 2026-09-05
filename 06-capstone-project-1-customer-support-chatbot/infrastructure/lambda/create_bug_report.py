import boto3
import json
import uuid
from datetime import datetime

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
table_name = "bug-report-tool-stack-bug-reports"
table = dynamodb.Table(table_name)


def lambda_handler(event, context):
    """Create a bug report in DynamoDB."""
    try:
        description = event.get("description", "")
        steps_to_reproduce = event.get("stepsToReproduce", "")
        environment = event.get("environment", "")

        ticket_id = f"BUG-{uuid.uuid4().hex[:8].upper()}"

        item = {
            "ticketId": ticket_id,
            "description": description,
            "stepsToReproduce": steps_to_reproduce,
            "environment": environment,
            "status": "OPEN",
            "createdAt": datetime.utcnow().isoformat()
        }

        table.put_item(Item=item)

        return {
            "ticketId": ticket_id,
            "status": "OPEN",
            "message": f"Bug report {ticket_id} has been filed successfully."
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to create bug report: {str(e)}"
        }
