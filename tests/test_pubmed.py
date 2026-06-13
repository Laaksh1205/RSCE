import asyncio
import pytest
import aiohttp
from unittest.mock import patch
from src.ingestion.pubmed import search_pubmed, fetch_abstracts, ingest_papers
from src.config import settings

class MockResponse:
    def __init__(self, status, json_data=None, bytes_data=None, on_enter=None):
        self.status = status
        self._json_data = json_data
        self._bytes_data = bytes_data
        self._on_enter = on_enter

    async def __aenter__(self):
        if self._on_enter:
            await self._on_enter()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def json(self):
        return self._json_data

    async def read(self):
        return self._bytes_data

    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=None,
                history=None,
                status=self.status
            )

MOCK_EFETCH_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation Status="MEDLINE" Owner="NLM">
      <PMID Version="1">31234567</PMID>
      <Article PubModel="Print-Electronic">
        <Journal>
          <JournalIssue CitedMedium="Internet">
            <PubDate>
              <Year>2020</Year>
            </PubDate>
          </JournalIssue>
          <Title>Journal of Clinical Oncology</Title>
        </Journal>
        <ArticleTitle>Metformin and Cancer Risk: A Systematic Review</ArticleTitle>
        <AuthorList CompleteYN="Y">
          <Author ValidYN="Y">
            <LastName>Smith</LastName>
            <ForeName>John</ForeName>
          </Author>
          <Author ValidYN="Y">
            <LastName>Johnson</LastName>
            <ForeName>Alice</ForeName>
          </Author>
        </AuthorList>
        <Abstract>
          <AbstractText Label="BACKGROUND">Metformin has been shown to reduce cancer risk.</AbstractText>
          <AbstractText Label="METHODS">We conducted a systematic review.</AbstractText>
          <AbstractText Label="RESULTS">Metformin use was associated with a significant decrease in cancer incidence.</AbstractText>
          <AbstractText Label="CONCLUSIONS">Metformin shows promise.</AbstractText>
        </Abstract>
        <ELocationID EIdType="doi">10.1200/JCO.2020.12.345</ELocationID>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""

@pytest.mark.asyncio
async def test_search_returns_pmids():
    mock_json = {
        "esearchresult": {
            "idlist": ["31234567", "32345678"]
        }
    }
    mock_resp = MockResponse(200, json_data=mock_json)
    
    with patch("aiohttp.ClientSession.get", return_value=mock_resp):
        pmids = await search_pubmed("metformin cancer", max_results=2)
        assert pmids == ["31234567", "32345678"]

@pytest.mark.asyncio
async def test_fetch_parses_xml():
    mock_resp = MockResponse(200, bytes_data=MOCK_EFETCH_XML)
    
    with patch("aiohttp.ClientSession.get", return_value=mock_resp):
        papers = await fetch_abstracts(["31234567"])
        assert len(papers) == 1
        paper = papers[0]
        assert paper.pmid == "31234567"
        assert paper.title == "Metformin and Cancer Risk: A Systematic Review"
        assert paper.authors == ["John Smith", "Alice Johnson"]
        assert paper.year == 2020
        assert paper.journal == "Journal of Clinical Oncology"
        assert "BACKGROUND: Metformin has been shown to reduce cancer risk." in paper.abstract_text
        assert "CONCLUSIONS: Metformin shows promise." in paper.abstract_text
        assert paper.doi == "10.1200/JCO.2020.12.345"

@pytest.mark.asyncio
async def test_rate_limiting():
    active_requests = 0
    max_active_requests = 0
    
    async def on_enter_req():
        nonlocal active_requests, max_active_requests
        active_requests += 1
        max_active_requests = max(max_active_requests, active_requests)
        await asyncio.sleep(0.05)  # brief delay to allow overlap
        active_requests -= 1

    def mock_get(*args, **kwargs):
        return MockResponse(200, json_data={"esearchresult": {"idlist": []}}, on_enter=on_enter_req)
        
    with patch("aiohttp.ClientSession.get", side_effect=mock_get):
        # Trigger 5 concurrent calls
        tasks = [search_pubmed("test", max_results=1) for _ in range(5)]
        await asyncio.gather(*tasks)
        
    # Verify that the active requests at any time did not exceed Settings
    assert max_active_requests <= settings.pubmed_concurrency

@pytest.mark.asyncio
async def test_few_results_warning(caplog):
    mock_search_json = {
        "esearchresult": {
            "idlist": ["31234567"]
        }
    }
    mock_search_resp = MockResponse(200, json_data=mock_search_json)
    mock_fetch_resp = MockResponse(200, bytes_data=MOCK_EFETCH_XML)
    
    def mock_get(*args, **kwargs):
        if not hasattr(mock_get, "responses"):
            mock_get.responses = [mock_search_resp, mock_fetch_resp]
        return mock_get.responses.pop(0)

    with patch("aiohttp.ClientSession.get", side_effect=mock_get):
        papers = await ingest_papers("rare query", max_results=5)
        assert len(papers) == 1
        # Check warning log was triggered
        warning_messages = [record.message for record in caplog.records if record.levelno == 30]  # 30 is WARNING
        assert any(f"Only 1 papers found" in msg for msg in warning_messages)


def test_pubmed_semaphores_different_loops():
    # Verify that get_search_semaphore() and get_fetch_semaphore() return 
    # different semaphore instances when run inside two different loops.
    from src.ingestion.pubmed import get_search_semaphore, get_fetch_semaphore
    
    # 1. Get semaphore in event loop 1
    sem_search_1 = None
    sem_fetch_1 = None
    
    async def run_1():
        nonlocal sem_search_1, sem_fetch_1
        sem_search_1 = get_search_semaphore()
        sem_fetch_1 = get_fetch_semaphore()
        
    asyncio.run(run_1())
    
    # 2. Get semaphore in event loop 2
    sem_search_2 = None
    sem_fetch_2 = None
    
    async def run_2():
        nonlocal sem_search_2, sem_fetch_2
        sem_search_2 = get_search_semaphore()
        sem_fetch_2 = get_fetch_semaphore()
        
    asyncio.run(run_2())
        
    # Verify both loops had their own independent semaphores
    assert sem_search_1 is not sem_search_2
    assert sem_fetch_1 is not sem_fetch_2


@pytest.mark.asyncio
async def test_pubmed_key_rotation_on_429(monkeypatch):
    monkeypatch.setattr(settings, "pubmed_email_1", "email1@example.com")
    monkeypatch.setattr(settings, "pubmed_api_key_1", "key1")
    monkeypatch.setattr(settings, "pubmed_email_2", "email2@example.com")
    monkeypatch.setattr(settings, "pubmed_api_key_2", "key2")
    
    monkeypatch.setattr(settings, "pubmed_email", "")
    monkeypatch.setattr(settings, "pubmed_api_key", "")
    
    import src.ingestion.pubmed as pubmed_module
    pubmed_module._pubmed_key_index = 0
    
    called_params = []
    
    def mock_get(url, params=None, **kwargs):
        called_params.append(params.copy() if params else {})
        if len(called_params) == 1:
            return MockResponse(429)
        else:
            return MockResponse(200, json_data={"esearchresult": {"idlist": ["123"]}})
            
    with patch("aiohttp.ClientSession.get", side_effect=mock_get):
        pmids = await search_pubmed("metformin", max_results=1)
        assert pmids == ["123"]
        
    assert len(called_params) == 2
    assert called_params[0].get("email") == "email1@example.com"
    assert called_params[0].get("api_key") == "key1"
    assert called_params[1].get("email") == "email2@example.com"
    assert called_params[1].get("api_key") == "key2"
    assert pubmed_module._pubmed_key_index == 1


