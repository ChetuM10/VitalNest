"""Who is calling: a verified Cognito bearer token (T1b).

Local development only: when app.local sets LOCAL_DEV_AUTH=1, the Vite proxy's fake identity header is
accepted instead. That switch is never set on Render.
"""
import json
import os

from fastapi import Header

from app.api.errors import api_error
from app.auth.cognito import TokenError, verify_token

DEV_HEADER = "x-amzn-request-context"


def _dev_identity(raw: str) -> dict:
    try:
        claims = json.loads(raw)["authorizer"]["claims"]
        return {"sub": claims["sub"], "email": claims.get("email")}
    except (ValueError, KeyError, TypeError):
        raise api_error(401, "unauthorized", "Invalid authentication.")


def current_user(
    authorization: str | None = Header(default=None),
    dev_context: str | None = Header(default=None, alias=DEV_HEADER),
) -> dict:
    if os.environ.get("LOCAL_DEV_AUTH") == "1" and dev_context:
        return _dev_identity(dev_context)
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise api_error(401, "unauthorized", "Missing or invalid sign-in token.")
    try:
        claims = verify_token(token.strip())
    except TokenError:
        raise api_error(401, "unauthorized", "Missing or invalid sign-in token.")
    return {"sub": claims["sub"], "email": claims.get("email")}
