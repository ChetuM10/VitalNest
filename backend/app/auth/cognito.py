"""Verify a Cognito JWT inside FastAPI: signature (cached JWKS), issuer, client, expiry, token use.

Nothing about the token is trusted until the signature has been checked against the user pool's own
public keys. Any failure raises TokenError; the caller turns that into a 401 without revealing why.
"""
from functools import lru_cache

import jwt
from jwt import PyJWKClient

from app.config import settings


class TokenError(Exception):
    pass


def issuer() -> str:
    return f"https://cognito-idp.{settings.cognito_region()}.amazonaws.com/{settings.cognito_user_pool_id()}"


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> PyJWKClient:
    # Keys are cached in memory for an hour; an unknown key id triggers one refresh.
    return PyJWKClient(url, cache_keys=True, lifespan=3600, timeout=5)


def signing_key(token: str):
    """The public key that signed `token`. Replaced by a local key in tests."""
    return _jwks_client(issuer() + "/.well-known/jwks.json").get_signing_key_from_jwt(token).key


def verify_token(token: str) -> dict:
    client_id = settings.cognito_client_id()
    if not client_id or not settings.cognito_user_pool_id():
        raise TokenError("Cognito is not configured")
    try:
        claims = jwt.decode(
            token,
            signing_key(token),
            algorithms=["RS256"],
            issuer=issuer(),
            options={"require": ["exp", "iss", "sub"], "verify_aud": False},
            leeway=10,
        )
    except Exception as error:  # bad signature, expired, wrong issuer, malformed, key fetch failed
        raise TokenError(type(error).__name__) from error
    use = claims.get("token_use")
    # Access tokens carry client_id; ID tokens carry aud. Either must name this app client.
    if use == "access":
        ok = claims.get("client_id") == client_id
    elif use == "id":
        ok = claims.get("aud") == client_id
    else:
        ok = False
    if not ok:
        raise TokenError("wrong token use or client")
    return claims
