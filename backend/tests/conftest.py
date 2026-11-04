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
