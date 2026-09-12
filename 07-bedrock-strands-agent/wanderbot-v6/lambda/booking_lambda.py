import json

BOOKINGS = {
    "BK-1001": {
        "booking_ref": "BK-1001",
        "customer": "Alice Johnson",
        "email": "alice@example.com",
        "flight": "HZ-101",
        "route": "BCN → FCO",
        "date": "2026-03-20",
        "cabin": "Economy",
        "fare_usd": 189.00,
        "status": "CONFIRMED",
    },
    "BK-1002": {
        "booking_ref": "BK-1002",
        "customer": "Alice Johnson",
        "email": "alice@example.com",
        "flight": "HZ-450",
        "route": "BCN → FCO",
        "date": "2026-03-20",
        "cabin": "Economy Lite",
        "fare_usd": 145.90,
        "status": "CONFIRMED",
    },
    "BK-1003": {
        "booking_ref": "BK-1003",
        "customer": "Bob Smith",
        "email": "bob@example.com",
        "flight": "HZ-311",
        "route": "BCN → LHR",
        "date": "2026-03-20",
        "cabin": "Economy",
        "fare_usd": 210.00,
        "status": "CONFIRMED",
    },
}


def get_booking(booking_ref: str) -> str:
    booking = BOOKINGS.get(booking_ref.upper())
    if not booking:
        return f"No booking found with reference {booking_ref}."
    return json.dumps(booking, indent=2)


def list_bookings_by_email(email: str) -> str:
    matches = [b for b in BOOKINGS.values() if b["email"].lower() == email.lower()]
    if not matches:
        return f"No bookings found for {email}."
    return json.dumps({"email": email, "bookings": matches}, indent=2)


def lambda_handler(event: dict, context) -> dict:
    tool = None
    try:
        raw_tool = context.client_context.custom.get("bedrockAgentCoreToolName", "")
        tool = raw_tool.split("__", 1)[-1] if "__" in raw_tool else raw_tool
    except (AttributeError, TypeError):
        pass

    if not tool:
        if "booking_ref" in event:
            tool = "get_booking"
        elif "email" in event:
            tool = "list_bookings_by_email"

    if tool == "get_booking":
        result = get_booking(event.get("booking_ref", ""))
    elif tool == "list_bookings_by_email":
        result = list_bookings_by_email(event.get("email", ""))
    else:
        result = json.dumps({"error": f"Unknown tool: {tool}"})

    return {"statusCode": 200, "body": result}
