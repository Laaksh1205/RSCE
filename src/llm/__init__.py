from src.config import settings
from src.llm.base import LLMProvider
from src.llm.gemini import GeminiProvider
from src.llm.openai import OpenAIProvider

_LLM_CACHE = {}

def get_llm(model: str | None = None) -> LLMProvider:
    provider = settings.llm_provider
    model_name = model or settings.extraction_model
    cache_key = (provider, model_name)
    
    if cache_key not in _LLM_CACHE:
        if provider == "gemini":
            _LLM_CACHE[cache_key] = GeminiProvider(model_name)
        elif provider == "openai":
            _LLM_CACHE[cache_key] = OpenAIProvider(model_name)
        else:
            raise ValueError(f"Unknown LLM provider configured: {provider}")
            
    return _LLM_CACHE[cache_key]

__all__ = ["LLMProvider", "GeminiProvider", "OpenAIProvider", "get_llm"]
