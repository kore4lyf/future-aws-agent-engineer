import boto3
import json
import uuid
from datetime import datetime

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
table_name = "customer-support-bugs"
table = dynamodb.Table(table_name)


def lambda_handler(event, context):
    """Create a bug report in DynamoDB."""
    try:
        # Extract tool input
        bug_description = event.get("bug_description", "")
        steps_to_reproduce = event.get("steps_to_reproduce", "")
        environment = event.get("environment", "")
        customer_id = event.get("customer_id", "anonymous")

        # Generate ticket ID
        ticket_id = f"BUG-{uuid.uuid4().hex[:8].upper()}"

        # Create item
        item = {
            "ticket_id": ticket_id,
            "bug_description": bug_description,
            "steps_to_reproduce": steps_to_reproduce,
            "environment": environment,
            "customer_id": customer_id,
            "status": "open",
            "created_at": datetime.utcnow().isoformat()
        }

        # Put item in DynamoDB
        table.put_item(Item=item)

        return {
            "ticket_id": ticket_id,
            "status": "created",
            "message": f"Bug report {ticket_id} has been filed successfully."
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to create bug report: {str(e)}"
        }
