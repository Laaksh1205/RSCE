import asyncio
import logging
import re
import time
import random
from typing import Type, TypeVar
from pydantic import BaseModel
from google import genai
from google.genai import types

from src.config import settings
from src.llm.base import LLMProvider

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)

class GeminiRateLimiter:
    _lock = asyncio.Lock()
    _last_request_time = 0.0

    @classmethod
    async def wait_if_needed(cls, interval: float):
        if interval <= 0:
            return
        async with cls._lock:
            now = time.time()
            elapsed = now - cls._last_request_time
            if elapsed < interval:
                sleep_time = interval - elapsed
                logger.info(f"Rate limiting: sleeping {sleep_time:.2f}s to respect Gemini API limits...")
                await asyncio.sleep(sleep_time)
            cls._last_request_time = time.time()

class GeminiProvider(LLMProvider):
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._key_index = 0
        keys = settings.gemini_api_keys
        try:
            if keys:
                self._clients = [genai.Client(api_key=key) for key in keys]
            else:
                api_key = settings.gemini_api_key if settings.gemini_api_key else None
                self._clients = [genai.Client(api_key=api_key)]
        except Exception as e:
            logger.warning(f"GeminiProvider: Could not initialize client: {e}. Using placeholder client.")
            try:
                self._clients = [genai.Client(api_key="placeholder")]
            except Exception:
                self._clients = []
        # Track cooldown expiration timestamp for each API key
        self._cooldown_until = [0.0] * len(self._clients)
        self._lock = asyncio.Lock()

    @property
    def client(self) -> genai.Client:
        return self._clients[self._key_index]

    def _rotate_key(self):
        old_idx = self._key_index
        self._key_index = (self._key_index + 1) % len(self._clients)
        logger.info(f"Gemini API key rotated from index {old_idx} to {self._key_index} (total keys: {len(self._clients)}).")

    async def _get_available_client(self) -> tuple[genai.Client, int]:
        """Find the next available client that is not on cooldown.
        
        If all clients are in cooldown, sleeps until the earliest cooldown expires.
        """
        while True:
            async with self._lock:
                now = time.time()
                for idx in range(len(self._clients)):
                    search_idx = (self._key_index + idx) % len(self._clients)
                    if now >= self._cooldown_until[search_idx]:
                        self._key_index = search_idx
                        return self._clients[search_idx], search_idx
                
                # All clients on cooldown, sleep until the earliest cools down
                min_cooldown = min(self._cooldown_until)
                sleep_time = min_cooldown - now + random.uniform(0.5, 2.0)
                sleep_time = max(sleep_time, 1.0)
            
            logger.warning(
                f"All Gemini keys are currently rate-limited. "
                f"Sleeping for {sleep_time:.2f}s before trying again..."
            )
            await asyncio.sleep(sleep_time)

    def _mark_cooldown(self, key_idx: int, delay: float):
        """Mark a specific key index as on cooldown for the specified delay."""
        now = time.time()
        self._cooldown_until[key_idx] = now + delay
        logger.warning(
            f"Gemini API key at index {key_idx} marked as rate-limited/cooldown "
            f"for {delay:.2f}s."
        )

    async def generate_text(self, prompt: str, temperature: float = 0.3) -> str:
        config = types.GenerateContentConfig(
            temperature=temperature
        )
        
        max_attempts = max(5, len(self._clients) * 3)
        
        for attempt in range(max_attempts):
            client, key_idx = await self._get_available_client()
            
            # Enforce rate limit spacing globally
            rate_limit_interval = getattr(settings, "gemini_rate_limit_interval", 4.2)
            await GeminiRateLimiter.wait_if_needed(rate_limit_interval)
            
            try:
                response = await client.aio.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config
                )
                return response.text or ""
            except Exception as e:
                err_str = str(e)
                is_rate_limit = "429" in err_str or "resource_exhausted" in err_str.lower() or "resourceexhausted" in err_str.lower()
                
                if attempt == max_attempts - 1:
                    logger.error(f"Gemini generate_text failed after {max_attempts} attempts: {e}")
                    raise
                
                if is_rate_limit:
                    delay_match = re.search(r"Please retry in (\d+(?:\.\d+)?)s", err_str)
                    delay = float(delay_match.group(1)) if delay_match else 60.0
                    
                    async with self._lock:
                        self._mark_cooldown(key_idx, delay)
                    
                    # Advance the key index so we try the next key in the pool next time
                    self._key_index = (key_idx + 1) % len(self._clients)
                else:
                    backoff = (2 ** attempt) * 2
                    logger.error(f"Gemini generate_text attempt {attempt+1} failed: {e}. Retrying in {backoff}s...")
                    await asyncio.sleep(backoff)
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
        
        max_attempts = max(5, len(self._clients) * 3)
        
        for attempt in range(max_attempts):
            client, key_idx = await self._get_available_client()
            
            # Enforce rate limit spacing globally
            rate_limit_interval = getattr(settings, "gemini_rate_limit_interval", 4.2)
            await GeminiRateLimiter.wait_if_needed(rate_limit_interval)
            
            try:
                response = await client.aio.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config
                )
                json_str = response.text
                if not json_str:
                    raise ValueError("Received empty response text from Gemini API")
                return response_schema.model_validate_json(json_str)
            except Exception as e:
                err_str = str(e)
                is_rate_limit = "429" in err_str or "resource_exhausted" in err_str.lower() or "resourceexhausted" in err_str.lower()
                
                if attempt == max_attempts - 1:
                    logger.error(f"Gemini generate_structured failed after {max_attempts} attempts: {e}")
                    raise
                
                if is_rate_limit:
                    delay_match = re.search(r"Please retry in (\d+(?:\.\d+)?)s", err_str)
                    delay = float(delay_match.group(1)) if delay_match else 60.0
                    
                    async with self._lock:
                        self._mark_cooldown(key_idx, delay)
                    
                    # Advance the key index so we try the next key in the pool next time
                    self._key_index = (key_idx + 1) % len(self._clients)
                else:
                    backoff = (2 ** attempt) * 2
                    logger.error(f"Gemini generate_structured attempt {attempt+1} failed: {e}. Retrying in {backoff}s...")
                    await asyncio.sleep(backoff)
        raise RuntimeError("Gemini generate_structured failed execution")
