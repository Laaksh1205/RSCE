from src.config import settings
from src.llm.base import LLMProvider
from src.llm.gemini import GeminiProvider
from src.llm.openai import OpenAIProvider

def get_llm(model: str | None = None) -> LLMProvider:
    provider = settings.llm_provider
    if provider == "gemini":
        return GeminiProvider(model or settings.extraction_model)
    elif provider == "openai":
        return OpenAIProvider(model or settings.extraction_model)
    else:
        raise ValueError(f"Unknown LLM provider configured: {provider}")

__all__ = ["LLMProvider", "GeminiProvider", "OpenAIProvider", "get_llm"]
