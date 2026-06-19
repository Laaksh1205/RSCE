import pytest
from unittest.mock import patch
from src.config import settings

@pytest.fixture(autouse=True, scope="session")
def mock_gemini_key():
    """Ensure GeminiProvider never sees a None or empty API key during tests."""
    with patch.object(settings, "gemini_api_key", "test-key-ci"):
        yield
