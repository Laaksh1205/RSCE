import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel
from src.config import settings
from src.llm.gemini import GeminiProvider

class DummyResponseModel(BaseModel):
    name: str
    score: int

@pytest.mark.asyncio
async def test_gemini_generate_structured():
    provider = GeminiProvider(model_name="gemini-2.5-flash")
    
    # Mock response object returned by the client
    mock_response = MagicMock()
    mock_response.text = '{"name": "test_name", "score": 42}'
    
    # client.aio.models.generate_content is an async method
    with patch.object(provider.client.aio.models, "generate_content", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_response
        
        result = await provider.generate_structured(
            prompt="Dummy prompt",
            response_schema=DummyResponseModel
        )
        
        assert isinstance(result, DummyResponseModel)
        assert result.name == "test_name"
        assert result.score == 42
        mock_gen.assert_called_once()

@pytest.mark.asyncio
async def test_gemini_generate_text():
    provider = GeminiProvider(model_name="gemini-2.5-flash")
    
    mock_response = MagicMock()
    mock_response.text = "Hello, world!"
    
    with patch.object(provider.client.aio.models, "generate_content", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_response
        
        result = await provider.generate_text(prompt="Say hello")
        
        assert result == "Hello, world!"
        mock_gen.assert_called_once()


@pytest.mark.asyncio
async def test_gemini_key_rotation_on_429(monkeypatch):
    # Mock settings to return three keys
    monkeypatch.setattr(settings, "gemini_api_key_1", "key1")
    monkeypatch.setattr(settings, "gemini_api_key_2", "key2")
    monkeypatch.setattr(settings, "gemini_api_key_3", "key3")
    
    provider = GeminiProvider(model_name="gemini-2.5-flash")
    
    assert len(provider._clients) == 3
    assert provider._key_index == 0
    
    mock_responses = [MagicMock() for _ in range(3)]
    mock_responses[1].text = "Hello from rotated key!"
    
    # Mock first client to raise a 429 rate limit error
    mock_gen_0 = AsyncMock(side_effect=Exception("429 ResourceExhausted"))
    mock_gen_1 = AsyncMock(return_value=mock_responses[1])
    mock_gen_2 = AsyncMock()
    
    with patch.object(provider._clients[0].aio.models, "generate_content", mock_gen_0), \
         patch.object(provider._clients[1].aio.models, "generate_content", mock_gen_1), \
         patch.object(provider._clients[2].aio.models, "generate_content", mock_gen_2):
         
         result = await provider.generate_text(prompt="Say hello")
         
         assert result == "Hello from rotated key!"
         mock_gen_0.assert_called_once()
         mock_gen_1.assert_called_once()
         mock_gen_2.assert_not_called()
         
         assert provider._key_index == 1

