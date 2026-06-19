from functools import lru_cache

from src.config import settings
from src.llm.base import LLMProvider
from src.llm.gemini import GeminiProvider
from src.llm.openai import OpenAIProvider

@lru_cache(maxsize=10)
def get_llm(model: str | None = None) -> LLMProvider:
    provider = settings.llm_provider
    model_name = model or settings.extraction_model

    if provider == "gemini":
        return GeminiProvider(model_name)
    elif provider == "openai":
        return OpenAIProvider(model_name)
    else:
        raise ValueError(f"Unknown LLM provider configured: {provider}")

__all__ = ["LLMProvider", "GeminiProvider", "OpenAIProvider", "get_llm"]
