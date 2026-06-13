import asyncio
import logging
from typing import Type, TypeVar
from pydantic import BaseModel
from openai import AsyncOpenAI

from src.config import settings
from src.llm.base import LLMProvider

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)

class OpenAIProvider(LLMProvider):
    def __init__(self, model_name: str):
        self.model_name = model_name
        api_key = settings.openai_api_key if settings.openai_api_key else None
        self.client = AsyncOpenAI(api_key=api_key)

    async def generate_text(self, prompt: str, temperature: float = 0.3) -> str:
        for attempt in range(3):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                is_rate_limit = "429" in str(e) or "rate_limit" in str(e).lower()
                if attempt == 2:
                    logger.error(f"OpenAI generate_text failed after 3 attempts: {e}")
                    raise
                
                backoff = (2 ** attempt) * 2
                level = logging.WARNING if is_rate_limit else logging.ERROR
                logger.log(level, f"OpenAI generate_text attempt {attempt+1} failed: {e}. Retrying in {backoff}s...")
                await asyncio.sleep(backoff)
        return ""

    async def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        temperature: float = 0.1,
    ) -> T:
        for attempt in range(3):
            try:
                # Utilize OpenAI's beta structured outputs parsing interface
                response = await self.client.beta.chat.completions.parse(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    response_format=response_schema,
                    temperature=temperature
                )
                result = response.choices[0].message.parsed
                if result is None:
                    # Fallback to manual validation if parsing is not populated
                    content = response.choices[0].message.content
                    if not content:
                        raise ValueError("Received empty content from OpenAI API")
                    return response_schema.model_validate_json(content)
                return result
            except Exception as e:
                is_rate_limit = "429" in str(e) or "rate_limit" in str(e).lower()
                if attempt == 2:
                    logger.error(f"OpenAI generate_structured failed after 3 attempts: {e}")
                    raise
                
                backoff = (2 ** attempt) * 2
                level = logging.WARNING if is_rate_limit else logging.ERROR
                logger.log(level, f"OpenAI generate_structured attempt {attempt+1} failed: {e}. Retrying in {backoff}s...")
                await asyncio.sleep(backoff)
        raise RuntimeError("OpenAI generate_structured failed execution")
