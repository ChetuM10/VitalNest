"""T1b: FastAPI verifies the Cognito JWT itself."""
import time

import pytest
from conftest import TEST_CLIENT, bearer, make_token, wrong_key_token
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def me(client, headers=None):
    return client.get("/v1/me", headers=headers or {})


def test_valid_access_token_is_accepted(client):
    response = me(client, bearer())
    assert response.status_code == 200
    assert response.json() == {"sub": "u-1", "email": "a@example.com"}


def test_valid_id_token_is_accepted(client):
    response = me(client, bearer(token_use="id", aud=TEST_CLIENT, client_id=None))
    assert response.status_code == 200


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": ""},
    {"Authorization": "Bearer"},
    {"Authorization": "Bearer not.a.jwt"},
    {"Authorization": "Basic abc"},
])
def test_missing_or_malformed_header_is_401(client, headers):
    response = me(client, headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("overrides", [
    {"exp": int(time.time()) - 3600},
    {"iss": "https://cognito-idp.ap-south-1.amazonaws.com/other-pool"},
    {"client_id": "someone-elses-client"},
    {"token_use": "refresh"},
    {"token_use": None},
    {"sub": None},
    {"exp": None},
])
def test_bad_claims_are_401(client, overrides):
    assert me(client, bearer(**overrides)).status_code == 401


def test_id_token_for_another_client_is_401(client):
    assert me(client, bearer(token_use="id", aud="other", client_id=None)).status_code == 401


def test_token_signed_by_another_key_is_401(client):
    assert me(client, {"Authorization": f"Bearer {wrong_key_token()}"}).status_code == 401


def test_unsigned_none_algorithm_token_is_401(client):
    import base64, json
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    forged = f"{enc({'alg': 'none', 'typ': 'JWT'})}.{enc({'sub': 'x', 'iss': 'y', 'exp': 9999999999})}."
    assert me(client, {"Authorization": f"Bearer {forged}"}).status_code == 401


def test_unconfigured_cognito_rejects_everything(client, monkeypatch):
    monkeypatch.delenv("COGNITO_CLIENT_ID")
    assert me(client, bearer()).status_code == 401


def test_key_fetch_failure_is_401_not_500(client, monkeypatch):
    def boom(token):
        raise RuntimeError("network down")
    monkeypatch.setattr("app.auth.cognito.signing_key", boom)
    assert me(client, bearer()).status_code == 401


def test_dev_header_is_ignored_unless_local_dev_auth_is_set(client):
    header = '{"authorizer": {"claims": {"sub": "x"}}}'
    assert me(client, {"x-amzn-request-context": header}).status_code == 401


def test_dev_header_works_when_local_dev_auth_is_set(client, monkeypatch):
    monkeypatch.setenv("LOCAL_DEV_AUTH", "1")
    header = '{"authorizer": {"claims": {"sub": "x"}}}'
    assert me(client, {"x-amzn-request-context": header}).status_code == 200


def test_health_stays_public(client):
    assert client.get("/v1/health").status_code == 200
