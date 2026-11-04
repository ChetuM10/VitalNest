"""Gateway-authenticated identity.

T0 only: API Gateway's Cognito authorizer has already validated the token, and the
Lambda Web Adapter forwards the authorizer result in the x-amzn-request-context header.
T1b replaces this with FastAPI verifying the JWT itself (signature, issuer, audience, expiry).
"""
import json

from fastapi import Header

from app.api.errors import api_error

CONTEXT_HEADER = "x-amzn-request-context"


def gateway_identity(
    request_context: str | None = Header(default=None, alias=CONTEXT_HEADER),
) -> dict:
    if not request_context:
        raise api_error(401, "unauthorized", "Missing authentication context.")
    try:
        claims = json.loads(request_context)["authorizer"]["claims"]
        return {"sub": claims["sub"], "email": claims.get("email")}
    except (ValueError, KeyError, TypeError):
        raise api_error(401, "unauthorized", "Invalid authentication context.")
