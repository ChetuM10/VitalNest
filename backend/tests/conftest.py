"""Tests never use real keys or the network, even if a key is set in the shell or a key file exists."""
import pytest

SECRET_VARIABLES = ("PINECONE_API_KEY", "ANTHROPIC_API_KEY")


@pytest.fixture(autouse=True)
def no_real_secrets(request, monkeypatch):
    # Tests marked `live` are the only ones allowed to use real keys (run with: pytest -m live).
    if request.node.get_closest_marker("live"):
        return
    for name in SECRET_VARIABLES:
        monkeypatch.delenv(name, raising=False)


# --- Cognito: a locally generated key pair stands in for the user pool (no network) ---
import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

TEST_REGION, TEST_POOL, TEST_CLIENT = "ap-south-1", "ap-south-1_TESTPOOL", "test-client-id"
TEST_ISSUER = f"https://cognito-idp.{TEST_REGION}.amazonaws.com/{TEST_POOL}"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_token(key=None, **overrides) -> str:
    claims = {
        "sub": "u-1", "email": "a@example.com", "iss": TEST_ISSUER, "token_use": "access",
        "client_id": TEST_CLIENT, "exp": int(time.time()) + 600,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key or _KEY, algorithm="RS256", headers={"kid": "k1"})


def bearer(**overrides) -> dict:
    return {"Authorization": f"Bearer {make_token(**overrides)}"}


def wrong_key_token(**overrides) -> str:
    return make_token(key=_OTHER_KEY, **overrides)


@pytest.fixture(autouse=True)
def fake_cognito(monkeypatch):
    monkeypatch.setenv("COGNITO_REGION", TEST_REGION)
    monkeypatch.setenv("COGNITO_USER_POOL_ID", TEST_POOL)
    monkeypatch.setenv("COGNITO_CLIENT_ID", TEST_CLIENT)
    monkeypatch.delenv("LOCAL_DEV_AUTH", raising=False)
    monkeypatch.setattr("app.auth.cognito.signing_key", lambda token: _KEY.public_key())
