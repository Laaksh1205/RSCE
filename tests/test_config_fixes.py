"""Unit tests for configuration bug fixes."""
import os
from src.config import Settings


def test_gemini_api_keys_includes_main_key():
    """Test that gemini_api_keys property includes the main key."""
    # Set main key only
    os.environ["GEMINI_API_KEY"] = "main_key"
    os.environ["GEMINI_API_KEY_1"] = ""
    os.environ["GEMINI_API_KEY_2"] = ""
    os.environ["GEMINI_API_KEY_3"] = ""
    
    settings = Settings(_env_file=None)
    keys = settings.gemini_api_keys
    assert len(keys) == 1
    assert keys[0] == "main_key"
    
    # Clean up
    del os.environ["GEMINI_API_KEY"]


def test_gemini_api_keys_includes_numbered_keys():
    """Test that gemini_api_keys property includes numbered keys."""
    os.environ["GEMINI_API_KEY"] = "main_key"
    os.environ["GEMINI_API_KEY_1"] = "key1"
    os.environ["GEMINI_API_KEY_2"] = "key2"
    os.environ["GEMINI_API_KEY_3"] = ""
    
    settings = Settings(_env_file=None)
    keys = settings.gemini_api_keys
    assert len(keys) == 3
    assert "main_key" in keys
    assert "key1" in keys
    assert "key2" in keys
    
    # Clean up
    del os.environ["GEMINI_API_KEY"]
    del os.environ["GEMINI_API_KEY_1"]
    del os.environ["GEMINI_API_KEY_2"]


def test_gemini_rate_limit_interval_from_env():
    """Test that gemini_rate_limit_interval can be set via environment variable."""
    os.environ["GEMINI_RATE_LIMIT_INTERVAL"] = "2.5"
    
    settings = Settings(_env_file=None)
    assert settings.gemini_rate_limit_interval == 2.5
    
    # Clean up
    del os.environ["GEMINI_RATE_LIMIT_INTERVAL"]


def test_gemini_rate_limit_interval_default():
    """Test that gemini_rate_limit_interval has correct default."""
    # Ensure env var is not set
    if "GEMINI_RATE_LIMIT_INTERVAL" in os.environ:
        del os.environ["GEMINI_RATE_LIMIT_INTERVAL"]
    
    settings = Settings(_env_file=None)
    assert settings.gemini_rate_limit_interval == 4.2
