import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel
from src.llm.openai import OpenAIProvider

class DummyResponseModel(BaseModel):
    name: str
    score: int

@pytest.mark.asyncio
async def test_openai_generate_structured():
    # Set mock key in env so OpenAI client initializes without crashing
    with patch.dict("os.environ", {"OPENAI_API_KEY": "mock-key"}):
        provider = OpenAIProvider(model_name="gpt-4o-mini")
    
    mock_parsed = DummyResponseModel(name="test_name", score=42)
    mock_choice = MagicMock()
    mock_choice.message.parsed = mock_parsed
    
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    
    with patch.object(provider.client.beta.chat.completions, "parse", new_callable=AsyncMock) as mock_parse:
        mock_parse.return_value = mock_response
        
        result = await provider.generate_structured(
            prompt="Dummy prompt",
            response_schema=DummyResponseModel
        )
        
        assert isinstance(result, DummyResponseModel)
        assert result.name == "test_name"
        assert result.score == 42
        mock_parse.assert_called_once()

@pytest.mark.asyncio
async def test_openai_generate_text():
    with patch.dict("os.environ", {"OPENAI_API_KEY": "mock-key"}):
        provider = OpenAIProvider(model_name="gpt-4o-mini")
    
    mock_message = MagicMock()
    mock_message.content = "Hello, world!"
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    
    with patch.object(provider.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response
        
        result = await provider.generate_text(prompt="Say hello")
        
        assert result == "Hello, world!"
        mock_create.assert_called_once()
