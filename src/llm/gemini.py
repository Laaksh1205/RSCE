import asyncio
import logging
from typing import Type, TypeVar
from pydantic import BaseModel
from google import genai
from google.genai import types

from src.config import settings
from src.llm.base import LLMProvider

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)

class GeminiProvider(LLMProvider):
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._key_index = 0
        keys = settings.gemini_api_keys
        if keys:
            self._clients = [genai.Client(api_key=key) for key in keys]
        else:
            api_key = settings.gemini_api_key if settings.gemini_api_key else None
            self._clients = [genai.Client(api_key=api_key)]

    @property
    def client(self) -> genai.Client:
        return self._clients[self._key_index]

    def _rotate_key(self):
        old_idx = self._key_index
        self._key_index = (self._key_index + 1) % len(self._clients)
        logger.info(f"Gemini API key rotated from index {old_idx} to {self._key_index} (total keys: {len(self._clients)}).")

    async def generate_text(self, prompt: str, temperature: float = 0.3) -> str:
        config = types.GenerateContentConfig(
            temperature=temperature
        )
        
        max_attempts = max(3, len(self._clients) * 2)
        consecutive_rate_limits = 0
        
        for attempt in range(max_attempts):
            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config
                )
                return response.text or ""
            except Exception as e:
                is_rate_limit = "429" in str(e) or "ResourceExhausted" in str(e)
                if attempt == max_attempts - 1:
                    logger.error(f"Gemini generate_text failed after {max_attempts} attempts: {e}")
                    raise
                
                if is_rate_limit:
                    self._rotate_key()
                    consecutive_rate_limits += 1
                    if consecutive_rate_limits >= len(self._clients):
                        backoff = (2 ** (consecutive_rate_limits - len(self._clients))) * 2
                        logger.warning(
                            f"Gemini generate_text hit rate limit on all keys. "
                            f"Retrying in {backoff}s... Error: {e}"
                        )
                        await asyncio.sleep(backoff)
                    else:
                        logger.warning(
                            f"Gemini generate_text hit rate limit. Rotated key and retrying immediately. Error: {e}"
                        )
                else:
                    backoff = (2 ** attempt) * 2
                    logger.error(f"Gemini generate_text attempt {attempt+1} failed: {e}. Retrying in {backoff}s...")
                    await asyncio.sleep(backoff)
                    consecutive_rate_limits = 0
        return ""

    async def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        temperature: float = 0.1,
    ) -> T:
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=temperature
        )
        
        max_attempts = max(3, len(self._clients) * 2)
        consecutive_rate_limits = 0
        
        for attempt in range(max_attempts):
            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config
                )
                json_str = response.text
                if not json_str:
                    raise ValueError("Received empty response text from Gemini API")
                return response_schema.model_validate_json(json_str)
            except Exception as e:
                is_rate_limit = "429" in str(e) or "ResourceExhausted" in str(e)
                if attempt == max_attempts - 1:
                    logger.error(f"Gemini generate_structured failed after {max_attempts} attempts: {e}")
                    raise
                
                if is_rate_limit:
                    self._rotate_key()
                    consecutive_rate_limits += 1
                    if consecutive_rate_limits >= len(self._clients):
                        backoff = (2 ** (consecutive_rate_limits - len(self._clients))) * 2
                        logger.warning(
                            f"Gemini generate_structured hit rate limit on all keys. "
                            f"Retrying in {backoff}s... Error: {e}"
                        )
                        await asyncio.sleep(backoff)
                    else:
                        logger.warning(
                            f"Gemini generate_structured hit rate limit. Rotated key and retrying immediately. Error: {e}"
                        )
                else:
                    backoff = (2 ** attempt) * 2
                    logger.error(f"Gemini generate_structured attempt {attempt+1} failed: {e}. Retrying in {backoff}s...")
                    await asyncio.sleep(backoff)
                    consecutive_rate_limits = 0
        raise RuntimeError("Gemini generate_structured failed execution")
