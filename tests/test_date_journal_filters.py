import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from api.app import app
from src.ingestion.pubmed import search_pubmed

client = TestClient(app)

class MockResponse:
    def __init__(self, status, json_data=None):
        self.status = status
        self._json_data = json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def json(self):
        return self._json_data

    def raise_for_status(self):
        pass

@pytest.mark.asyncio
async def test_search_pubmed_with_date_and_journal_filters():
    mock_json = {
        "esearchresult": {
            "idlist": ["12345"]
        }
    }
    mock_resp = MockResponse(200, json_data=mock_json)
    
    called_params = []
    
    def mock_get(url, params=None, **kwargs):
        called_params.append(params.copy() if params else {})
        return mock_resp

    with patch("aiohttp.ClientSession.get", side_effect=mock_get):
        pmids = await search_pubmed(
            query="metformin",
            max_results=5,
            date_from=2018,
            date_to=2023,
            journals=["Nature", "Science"]
        )
        assert pmids == ["12345"]
        
    assert len(called_params) == 1
    params = called_params[0]
    
    # Assert query-term includes journals formatted correctly
    assert '("Nature"[Journal] OR "Science"[Journal])' in params["term"]
    assert "metformin" in params["term"]
    
    # Assert date range parameters passed natively to esearch
    assert params["mindate"] == "2018"
    assert params["maxdate"] == "2023"
    assert params["datetype"] == "pdat"


@patch("api.routes.analysis.run_analysis_background")
def test_analyze_endpoint_with_filters(mock_bg_task):
    payload = {
        "query": "metformin cancer risk",
        "max_papers": 15,
        "date_from": 2016,
        "date_to": 2022,
        "journals": ["J Clin Oncol", "Breast Cancer Res"]
    }
    
    response = client.post("/api/analyze", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert data["query"] == "metformin cancer risk"
    assert data["status"] == "RUNNING"
    
    # Verify that run_analysis_background was invoked with the filters forwarded
    mock_bg_task.assert_called_once_with(
        run_id=data["run_id"],
        query="metformin cancer risk",
        max_papers=15,
        seed_claim=None,
        date_from=2016,
        date_to=2022,
        journals=["J Clin Oncol", "Breast Cancer Res"]
    )
