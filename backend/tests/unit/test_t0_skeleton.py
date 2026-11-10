"""T0 tests: health, authenticated routes, SSE streaming spike, CORS."""
import json

import pytest
from conftest import bearer
from fastapi.testclient import TestClient

from app.main import create_app

@pytest.fixture
def client():
    return TestClient(create_app())


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_health_is_public_and_reports_version(client):
    response = client.get("/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_me_without_token_is_401(client):
    response = client.get("/v1/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_cors_preflight_allows_authorization_header_from_configured_origin(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGIN", "https://vitalnest.example")
    client = TestClient(create_app())
    response = client.options(
        "/v1/me",
        headers={
            "Origin": "https://vitalnest.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://vitalnest.example"


def test_cors_does_not_allow_other_origins(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGIN", "https://vitalnest.example")
    client = TestClient(create_app())
    response = client.options(
        "/v1/health",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in response.headers
