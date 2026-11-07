"""Rate limiting for POST /v1/chat: per user per minute, per user per day, and overall per day."""
import pytest
from conftest import bearer
from fastapi.testclient import TestClient

from app.api.chat import get_chat_service
from app.api.rate_limit import DAY, MINUTE, RateLimiter
from app.main import create_app


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def limiter(per_minute=3, per_day=5, global_per_day=100):
    clock = Clock()
    return RateLimiter(per_minute, per_day, global_per_day, clock=clock), clock


def test_allows_up_to_the_minute_limit_then_blocks_with_wait_time():
    rl, clock = limiter()
    assert [rl.check("a") for _ in range(3)] == [None, None, None]
    reason, wait = rl.check("a")
    assert reason == "minute" and wait == MINUTE


def test_minute_window_slides():
    rl, clock = limiter()
    for _ in range(3):
        rl.check("a")
    clock.now += MINUTE + 1
    assert rl.check("a") is None


def test_users_are_counted_separately():
    rl, _ = limiter(per_minute=1)
    assert rl.check("a") is None
    assert rl.check("b") is None
    assert rl.check("a")[0] == "minute"


def test_daily_limit_blocks_until_the_oldest_request_ages_out():
    rl, clock = limiter(per_minute=10, per_day=5)
    for _ in range(5):
        assert rl.check("a") is None
        clock.now += 1
    reason, wait = rl.check("a")
    assert reason == "day" and 0 < wait <= DAY
    clock.now += DAY
    assert rl.check("a") is None


def test_global_limit_applies_to_everyone():
    rl, _ = limiter(per_minute=10, per_day=10, global_per_day=2)
    assert rl.check("a") is None and rl.check("b") is None
    assert rl.check("c")[0] == "busy"


def test_blocked_requests_are_not_counted():
    rl, clock = limiter(per_minute=1, per_day=2)
    rl.check("a")
    for _ in range(20):
        rl.check("a")  # all blocked by the minute rule
    clock.now += MINUTE + 1
    assert rl.check("a") is None  # still has a second daily request


# --- through the real route ---

class StubService:
    async def prepare(self, body):
        raise RuntimeError("not reached in these tests")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    app = create_app()
    app.dependency_overrides[get_chat_service] = lambda: None  # 503 after the limiter has counted
    return TestClient(app)


def post(client, headers):
    return client.post("/v1/chat", json={"message": "What is asthma?", "history": []}, headers=headers)


def test_route_returns_429_with_retry_after_and_error_shape(client):
    headers = bearer()
    assert post(client, headers).status_code == 503
    assert post(client, headers).status_code == 503
    response = post(client, headers)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert int(response.headers["retry-after"]) >= 1


def test_route_limits_each_signed_in_user_separately(client):
    for _ in range(2):
        post(client, bearer(sub="u-1"))
    assert post(client, bearer(sub="u-1")).status_code == 429
    assert post(client, bearer(sub="u-2")).status_code == 503


def test_unauthenticated_requests_are_401_and_not_counted(client):
    for _ in range(5):
        assert post(client, {}).status_code == 401
    assert post(client, bearer()).status_code == 503


def test_health_is_never_limited(client):
    for _ in range(20):
        assert client.get("/v1/health").status_code == 200
