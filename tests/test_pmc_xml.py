import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.ingestion.pmc_xml import parse_pmc_xml, fetch_full_text


SAMPLE_PMC_XML = """<?xml version="1.0" encoding="UTF-8"?>
<article>
    <body>
        <sec>
            <title>Introduction</title>
            <p>This is the introduction text. It has some <bold>bold</bold> formatting.</p>
            <p>Another paragraph in intro.</p>
        </sec>
        <sec>
            <title>Study Methods</title>
            <p>We did a randomized trial.</p>
            <sec>
                <title>Statistical Analysis</title>
                <p>Data was analyzed using R.</p>
            </sec>
        </sec>
        <sec>
            <title>Results and Findings</title>
            <p>Results were extremely positive.</p>
        </sec>
        <sec>
            <title>Discussion</title>
            <p>Our findings are significant.</p>
        </sec>
        <sec>
            <title>Supporting Info</title>
            <p>Some extra info that should be skipped.</p>
        </sec>
    </body>
</article>
"""

def test_parse_pmc_xml():
    parsed = parse_pmc_xml(SAMPLE_PMC_XML)
    
    assert "This is the introduction text. It has some bold formatting.\n\nAnother paragraph in intro." in parsed["Introduction"]
    assert "We did a randomized trial.\n\nData was analyzed using R." in parsed["Methods"]
    assert parsed["Results"] == "Results were extremely positive."
    assert parsed["Discussion"] == "Our findings are significant."
    
    # Check that "Supporting Info" text is not categorised
    assert "Some extra info that should be skipped." not in parsed["Introduction"]
    assert "Some extra info that should be skipped." not in parsed["Methods"]
    assert "Some extra info that should be skipped." not in parsed["Results"]
    assert "Some extra info that should be skipped." not in parsed["Discussion"]


def test_parse_pmc_xml_malformed():
    parsed = parse_pmc_xml("<malformed><xml>")
    assert parsed["Introduction"] == ""
    assert parsed["Methods"] == ""
    assert parsed["Results"] == ""
    assert parsed["Discussion"] == ""


def test_parse_pmc_xml_empty():
    parsed = parse_pmc_xml("")
    assert parsed["Introduction"] == ""
    assert parsed["Methods"] == ""
    assert parsed["Results"] == ""
    assert parsed["Discussion"] == ""


@pytest.mark.asyncio
async def test_fetch_full_text_success():
    # Mock PMID -> PMCID response
    mock_idconv_data = {
        "status": "ok",
        "records": [{"pmcid": "PMC1234567", "pmid": "99999"}]
    }
    
    mock_xml_content = SAMPLE_PMC_XML

    # Patch aiohttp.ClientSession.get to mock responses
    with patch("aiohttp.ClientSession.get") as mock_get:
        # Create mock response objects
        mock_idconv_resp = MagicMock()
        mock_idconv_resp.status = 200
        mock_idconv_resp.json = AsyncMock(return_value=mock_idconv_data)
        
        mock_efetch_resp = MagicMock()
        mock_efetch_resp.status = 200
        mock_efetch_resp.text = AsyncMock(return_value=mock_xml_content)
        
        # Configure side effect for successive get calls
        mock_get.side_effect = [
            MagicMock(__aenter__=AsyncMock(return_value=mock_idconv_resp)),
            MagicMock(__aenter__=AsyncMock(return_value=mock_efetch_resp))
        ]
        
        result = await fetch_full_text("99999")
        assert result == SAMPLE_PMC_XML
        assert mock_get.call_count == 2


@pytest.mark.asyncio
async def test_fetch_full_text_not_open_access():
    mock_idconv_data = {
        "status": "ok",
        "records": [{"pmid": "99999"}] # No pmcid key
    }

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_idconv_resp = MagicMock()
        mock_idconv_resp.status = 200
        mock_idconv_resp.json = AsyncMock(return_value=mock_idconv_data)
        
        mock_get.return_value.__aenter__.return_value = mock_idconv_resp
        
        result = await fetch_full_text("99999")
        assert result is None
        assert mock_get.call_count == 1


@pytest.mark.asyncio
async def test_fetch_full_text_shared_session():
    import aiohttp
    mock_idconv_data = {
        "status": "ok",
        "records": [{"pmcid": "PMC1234567", "pmid": "99999"}]
    }
    mock_xml_content = SAMPLE_PMC_XML

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_idconv_resp = MagicMock()
        mock_idconv_resp.status = 200
        mock_idconv_resp.json = AsyncMock(return_value=mock_idconv_data)
        
        mock_efetch_resp = MagicMock()
        mock_efetch_resp.status = 200
        mock_efetch_resp.text = AsyncMock(return_value=mock_xml_content)
        
        mock_get.side_effect = [
            MagicMock(__aenter__=AsyncMock(return_value=mock_idconv_resp)),
            MagicMock(__aenter__=AsyncMock(return_value=mock_efetch_resp))
        ]
        
        async with aiohttp.ClientSession() as session:
            result = await fetch_full_text("99999", session=session)
            assert result == SAMPLE_PMC_XML
            assert mock_get.call_count == 2
