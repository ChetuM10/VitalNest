"""T0 tests: health, gateway-authenticated identity route, SSE streaming spike, CORS."""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

CONTEXT_HEADER = "x-amzn-request-context"


def make_context(claims: dict) -> str:
    return json.dumps({"authorizer": {"claims": claims}})


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


def test_me_without_gateway_claims_is_401(client):
    response = client.get("/v1/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_me_returns_identity_from_gateway_claims(client):
    header = make_context({"sub": "abc-123", "email": "a@example.com"})
    response = client.get("/v1/me", headers={CONTEXT_HEADER: header})
    assert response.status_code == 200
    assert response.json() == {"sub": "abc-123", "email": "a@example.com"}


def test_me_with_malformed_context_is_401(client):
    response = client.get("/v1/me", headers={CONTEXT_HEADER: "not-json"})
    assert response.status_code == 401


def test_stream_spike_requires_identity(client):
    assert client.get("/v1/stream-spike").status_code == 401


def test_stream_spike_emits_ordered_sse_events(client):
    header = make_context({"sub": "abc-123"})
    with client.stream(
        "GET",
        "/v1/stream-spike?count=3&delay_ms=0",
        headers={CONTEXT_HEADER: header},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
    events = parse_sse(body)
    assert [name for name, _ in events] == ["token", "token", "token", "done"]
    assert [data["index"] for name, data in events if name == "token"] == [0, 1, 2]


@pytest.mark.parametrize("query", ["count=0", "count=51", "delay_ms=-1", "delay_ms=2001"])
def test_stream_spike_rejects_out_of_range_parameters(client, query):
    header = make_context({"sub": "abc-123"})
    response = client.get(f"/v1/stream-spike?{query}", headers={CONTEXT_HEADER: header})
    assert response.status_code == 422


def test_cors_preflight_allows_authorization_header_from_configured_origin(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGIN", "https://vitalnest.example")
    client = TestClient(create_app())
    response = client.options(
        "/v1/stream-spike",
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
