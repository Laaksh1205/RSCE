import pytest
from unittest.mock import patch
from src.llm import get_llm, GeminiProvider, OpenAIProvider
from src.config import settings

def test_get_llm_factory():
    # Test getting gemini provider (default model)
    with patch.object(settings, "llm_provider", "gemini"):
        with patch.object(settings, "extraction_model", "gemini-2.5-flash"):
            llm = get_llm()
            assert isinstance(llm, GeminiProvider)
            assert llm.model_name == "gemini-2.5-flash"
            
    # Test getting gemini provider with custom judge model
    with patch.object(settings, "llm_provider", "gemini"):
        with patch.object(settings, "judge_model", "gemini-2.5-pro"):
            llm = get_llm(settings.judge_model)
            assert isinstance(llm, GeminiProvider)
            assert llm.model_name == "gemini-2.5-pro"
            
    # Test getting openai provider (default model)
    with patch.object(settings, "llm_provider", "openai"):
        with patch.object(settings, "extraction_model", "gpt-4o-mini"):
            with patch.dict("os.environ", {"OPENAI_API_KEY": "mock-key"}):
                llm = get_llm()
                assert isinstance(llm, OpenAIProvider)
                assert llm.model_name == "gpt-4o-mini"

    # Test getting openai provider with custom judge model
    with patch.object(settings, "llm_provider", "openai"):
        with patch.object(settings, "judge_model", "gpt-4o"):
            with patch.dict("os.environ", {"OPENAI_API_KEY": "mock-key"}):
                llm = get_llm(settings.judge_model)
                assert isinstance(llm, OpenAIProvider)
                assert llm.model_name == "gpt-4o"
