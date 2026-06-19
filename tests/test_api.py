import json
import uuid
from unittest.mock import patch
from fastapi.testclient import TestClient

from api.app import app
from src.models.claim import Claim, ClaimType, Polarity, StudyDesign
from src.models.paper import Paper
from src.models.contradiction import ContradictionPair, ContradictionType
from src.models.report import SynthesisReport

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "rsce-api"}


@patch("api.routes.analysis.run_analysis_background")
def test_analyze_endpoint(mock_bg_task):
    payload = {"query": "metformin cancer risk", "max_papers": 10}
    response = client.post("/api/analyze", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert data["query"] == "metformin cancer risk"
    assert data["status"] == "RUNNING"
    
    # Verify UUID format of run_id
    val = uuid.UUID(data["run_id"])
    assert isinstance(val, uuid.UUID)
    
    mock_bg_task.assert_called_once()


@patch("api.routes.analysis.get_pipeline_run")
def test_status_endpoint_found(mock_get_run):
    mock_run_id = str(uuid.uuid4())
    mock_get_run.return_value = {
        "id": mock_run_id,
        "query": "dietary fasting",
        "status": "RUNNING",
        "papers_fetched": 5,
        "claims_extracted": 12,
        "contradictions_found": 0,
        "started_at": "2026-06-12T00:00:00",
        "completed_at": None,
        "error_message": None
    }
    
    response = client.get(f"/api/status/{mock_run_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == mock_run_id
    assert data["status"] == "RUNNING"
    assert data["papers_fetched"] == 5


@patch("api.routes.analysis.get_pipeline_run")
def test_status_endpoint_not_found(mock_get_run):
    mock_get_run.return_value = None
    response = client.get(f"/api/status/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Analysis run not found."


@patch("api.routes.results.get_pipeline_run")
def test_results_endpoint_completed(mock_get_run):
    mock_run_id = str(uuid.uuid4())
    
    mock_report = SynthesisReport(
        summary="Intermittent fasting reduces insulin resistance.",
        contradictions=[],
        consensus_scores={},
        total_papers=2,
        total_claims=5,
        metadata={"run_id": mock_run_id}
    )
    
    mock_get_run.return_value = {
        "id": mock_run_id,
        "query": "fasting metabolic health",
        "status": "COMPLETED",
        "report_json": mock_report.model_dump_json(),
        "error_message": None
    }
    
    response = client.get(f"/api/results/{mock_run_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["summary"] == "Intermittent fasting reduces insulin resistance."
    assert data["total_papers"] == 2


@patch("api.routes.results.get_pipeline_run")
def test_results_endpoint_running(mock_get_run):
    mock_run_id = str(uuid.uuid4())
    mock_get_run.return_value = {
        "id": mock_run_id,
        "query": "fasting metabolic health",
        "status": "RUNNING",
        "report_json": None,
        "error_message": None
    }
    
    response = client.get(f"/api/results/{mock_run_id}")
    assert response.status_code == 400
    assert "in progress" in response.json()["detail"]


@patch("api.routes.results.get_pipeline_run")
@patch("api.routes.results.get_claims_for_run")
def test_claims_endpoint(mock_get_claims, mock_get_run):
    mock_run_id = str(uuid.uuid4())
    mock_get_run.return_value = {
        "id": mock_run_id,
        "pmids": json.dumps(["11111", "22222"])
    }
    
    claim = Claim(
        id=uuid.uuid4(),
        text="Metformin reduces risk.",
        paper_id="11111",
        year=2020,
        confidence_score=1.0,
        claim_type=ClaimType.CAUSAL,
        polarity=Polarity.NEGATIVE,
        entities=[],
        population="humans",
        context="clinical trial",
        quote_anchor="reduces risk",
        study_design=StudyDesign.RCT
    )
    mock_get_claims.return_value = [claim]
    
    response = client.get(f"/api/claims/{mock_run_id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["text"] == "Metformin reduces risk."


@patch("api.routes.results.get_pipeline_run")
@patch("api.routes.results.get_papers_for_run")
@patch("api.routes.results.get_claims_for_run")
@patch("api.routes.results.get_contradictions_for_run")
def test_graph_endpoint(mock_get_contradictions, mock_get_claims, mock_get_papers, mock_get_run):
    mock_run_id = str(uuid.uuid4())
    mock_get_run.return_value = {
        "id": mock_run_id,
        "pmids": json.dumps(["11111", "22222"])
    }
    
    paper_1 = Paper(pmid="11111", title="Title 1", authors=["Author A"], year=2020, journal="Journal A", abstract_text="A")
    paper_2 = Paper(pmid="22222", title="Title 2", authors=["Author B"], year=2022, journal="Journal B", abstract_text="B")
    mock_get_papers.return_value = [paper_1, paper_2]
    
    claim_1 = Claim(
        id=uuid.uuid4(), text="Claim A.", paper_id="11111", year=2020, confidence_score=1.0,
        claim_type=ClaimType.CAUSAL, polarity=Polarity.NEGATIVE, entities=[], population="humans",
        context="general", quote_anchor="A", study_design=StudyDesign.RCT
    )
    claim_2 = Claim(
        id=uuid.uuid4(), text="Claim B.", paper_id="22222", year=2022, confidence_score=1.0,
        claim_type=ClaimType.CAUSAL, polarity=Polarity.POSITIVE, entities=[], population="humans",
        context="general", quote_anchor="B", study_design=StudyDesign.RCT
    )
    mock_get_claims.return_value = [claim_1, claim_2]
    
    contradiction = ContradictionPair(
        claim_a=claim_1, claim_b=claim_2, contradiction_score=0.9,
        contradiction_type=ContradictionType.DIRECTION_REVERSAL, explanation="Contradicts",
        scope_note="", is_genuine=True
    )
    mock_get_contradictions.return_value = [contradiction]
    
    response = client.get(f"/api/graph/{mock_run_id}")
    assert response.status_code == 200
    data = response.json()
    assert "elements" in data
    assert "nodes" in data["elements"]
    assert "edges" in data["elements"]
    
    # 2 papers + 2 claims = 4 nodes
    assert len(data["elements"]["nodes"]) == 4

@patch("api.routes.results.get_pipeline_run")
@patch("api.routes.results.get_papers_for_run")
@patch("api.routes.results.get_claims_for_run")
@patch("api.routes.results.get_contradictions_for_run")
def test_demo_endpoint(mock_get_contradictions, mock_get_claims, mock_get_papers, mock_get_run):
    mock_get_run.return_value = {
        "id": "demo_metformin",
        "query": "Does metformin reduce cancer risk?",
        "pmids": json.dumps(["11111"]),
        "report_json": json.dumps({
            "summary": "Metformin summary.",
            "contradictions": [],
            "consensus_scores": {},
            "total_papers": 1,
            "total_claims": 1,
            "metadata": {}
        })
    }
    mock_get_papers.return_value = [
        Paper(pmid="11111", title="Title 1", authors=["Author A"], year=2020, journal="Journal A", abstract_text="A")
    ]
    mock_get_claims.return_value = [
        Claim(
            id=uuid.uuid4(), text="Claim A.", paper_id="11111", year=2020, confidence_score=1.0,
            claim_type=ClaimType.CAUSAL, polarity=Polarity.NEGATIVE, entities=[], population="humans",
            context="general", quote_anchor="A", study_design=StudyDesign.RCT
        )
    ]
    mock_get_contradictions.return_value = []
    
    response = client.get("/api/demo/metformin")
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == "demo_metformin"
    assert data["query"] == "Does metformin reduce cancer risk?"
    assert data["report"]["summary"] == "Metformin summary."
    assert len(data["claims"]) == 1
    assert "elements" in data["graph"]

def test_demo_endpoint_not_found():
    response = client.get("/api/demo/unknown_topic")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_cors_headers():
    # Test allowed origin
    response = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"
    
    # Test disallowed origin
    response = client.get("/api/health", headers={"Origin": "http://malicious.com"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


