import pytest
from unittest.mock import patch, MagicMock
from src.ingestion.pdf_fallback import (
    fetch_pdf_url_from_unpaywall,
    download_and_extract_pdf_text,
    structure_pdf_text,
)

class MockResponse:
    def __init__(self, status, json_data=None, bytes_data=None):
        self.status = status
        self._json_data = json_data
        self._bytes_data = bytes_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def json(self):
        return self._json_data

    async def read(self):
        return self._bytes_data

    def raise_for_status(self):
        if self.status >= 400:
            raise Exception("HTTP Error")


@pytest.mark.asyncio
async def test_fetch_pdf_url_from_unpaywall_success():
    mock_json = {
        "best_oa_location": {
            "url_for_pdf": "https://example.com/paper.pdf"
        }
    }
    mock_resp = MockResponse(200, json_data=mock_json)
    
    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp
    
    pdf_url = await fetch_pdf_url_from_unpaywall("10.1038/12345", mock_session)
    assert pdf_url == "https://example.com/paper.pdf"
    
    # Assert query clean logic with URL prefixes
    pdf_url_url = await fetch_pdf_url_from_unpaywall("https://doi.org/10.1038/12345", mock_session)
    assert pdf_url_url == "https://example.com/paper.pdf"


@pytest.mark.asyncio
async def test_fetch_pdf_url_from_unpaywall_missing_or_error():
    mock_session = MagicMock()
    
    # Test missing best_oa_location
    mock_session.get.return_value = MockResponse(200, json_data={"best_oa_location": None})
    pdf_url = await fetch_pdf_url_from_unpaywall("10.1038/12345", mock_session)
    assert pdf_url is None
    
    # Test error status
    mock_session.get.return_value = MockResponse(404)
    pdf_url = await fetch_pdf_url_from_unpaywall("10.1038/12345", mock_session)
    assert pdf_url is None


@pytest.mark.asyncio
async def test_download_and_extract_pdf_text():
    mock_resp = MockResponse(200, bytes_data=b"%PDF-1.4 mock bytes")
    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp
    
    # Mock PyMuPDF fitz module
    with patch("fitz.open") as mock_open:
        mock_doc = MagicMock()
        mock_page_1 = MagicMock()
        mock_page_1.get_text.return_value = "Introduction\nThis is background text."
        mock_page_2 = MagicMock()
        mock_page_2.get_text.return_value = "Methods\nWe performed some testing."
        
        mock_doc.__iter__.return_value = [mock_page_1, mock_page_2]
        mock_open.return_value = mock_doc
        
        structured_text = await download_and_extract_pdf_text("https://example.com/paper.pdf", mock_session)
        
        assert structured_text is not None
        assert "=== INTRODUCTION ===" in structured_text
        assert "=== METHODS ===" in structured_text
        assert "This is background text." in structured_text
        assert "We performed some testing." in structured_text


def test_structure_pdf_text_heuristics():
    raw_text = (
        "1. Introduction\n"
        "This is research\n"
        "background on metformin.\n\n"
        "Methods and Materials\n"
        "We randomized 500\n"
        "patients.\n\n"
        "Results\n"
        "Metformin significantly reduced risk.\n\n"
        "Discussion\n"
        "This aligns with prior trials."
    )
    
    structured = structure_pdf_text(raw_text)
    
    assert "=== INTRODUCTION ===" in structured
    assert "=== METHODS ===" in structured
    assert "=== RESULTS ===" in structured
    assert "=== DISCUSSION ===" in structured
    
    # Check that internal newlines in paragraph blocks are merged into spaces
    assert "This is research background on metformin." in structured
    assert "We randomized 500 patients." in structured
