import pytest
from unittest.mock import patch
from src.config import settings
from src.storage.database import init_db

@pytest.fixture(autouse=True, scope="session")
def mock_gemini_key():
    """Ensure GeminiProvider never sees a None or empty API key during tests."""
    with patch.object(settings, "gemini_api_key", "test-key-ci"):
        yield

@pytest.fixture(autouse=True, scope="session")
def setup_test_database():
    """Ensure that the default SQLite test database and tables are initialized."""
    import os
    db_dir = os.path.dirname(os.path.abspath(settings.db_path))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    init_db(settings.db_path)
    yield
