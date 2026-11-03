import os
import pytest

@pytest.fixture(autouse=True)
def default_test_env(monkeypatch):
    """
    Ensures unit tests run reliably in CI/CD and on fresh EC2 instances
    without requiring external API keys.
    """
    if not os.getenv("DIRECTOR_API_KEY"):
        monkeypatch.setenv("DIRECTOR_API_KEY", "mock-test-key")
    if not os.getenv("PRODUCER_API_KEY"):
        monkeypatch.setenv("PRODUCER_API_KEY", "mock-test-key")
    if not os.getenv("GROQ_API_KEY"):
        monkeypatch.setenv("GROQ_API_KEY", "mock-test-key")
