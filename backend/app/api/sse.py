import json


def sse(event: str, data: dict) -> str:
    """One Server-Sent Event, in the format the API contract defines."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
