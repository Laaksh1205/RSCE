import pytest
from unittest.mock import AsyncMock, patch
from typer.testing import CliRunner
import uuid

from src.config import settings
from src.main import app
from src.pipeline import PipelineState
from src.models.paper import Paper
from src.models.claim import Claim, ClaimType, Polarity, StudyDesign
from src.models.report import SynthesisReport

runner = CliRunner()

@pytest.fixture
def mock_pipeline_state():
    claim = Claim(
        id=uuid.uuid4(),
        text="Metformin reduces breast cancer risk.",
        paper_id="12345",
        authors=["John Smith"],
        year=2023,
        confidence_score=1.0,
        claim_type=ClaimType.CAUSAL,
        polarity=Polarity.NEGATIVE,
        population="humans",
        context="general",
        quote_anchor="reduced breast cancer risk",
        study_design=StudyDesign.RCT
    )
    paper = Paper(
        pmid="12345",
        title="Sample Study on Metformin",
        authors=["John Smith"],
        year=2023,
        journal="Diabetes Care",
        abstract_text="Metformin reduces breast cancer risk."
    )
    report = SynthesisReport(
        summary="Metformin reduces breast cancer risk.",
        contradictions=[],
        consensus_scores={},
        total_papers=1,
        total_claims=1,
        metadata={"time_elapsed": 1.5, "cost_estimate": 0.02}
    )
    return PipelineState(
        run_id="test-run-id",
        query="metformin cancer",
        status="COMPLETED",
        papers=[paper],
        claims=[claim],
        contradictions=[],
        report=report,
        verification_stats={"passed": 1, "flagged": 0, "rejected": 0, "rejection_rate": 0.0}
    )

@patch("src.main.run_full_pipeline", new_callable=AsyncMock)
def test_cli_analyze_command(
    mock_run_pipeline,
    mock_pipeline_state
):
    # Set up mocks
    mock_run_pipeline.return_value = mock_pipeline_state

    # Run CLI command
    with patch.object(settings, "gemini_api_key", "mock-key"):
        result = runner.invoke(app, ["Does metformin reduce cancer risk?"])

    # Assert success and outputs
    assert result.exit_code == 0
    assert "RESEARCH SYNTHESIS & CONTRADICTION ENGINE" in result.stdout
    assert "Pipeline Execution Statistics" in result.stdout

    mock_run_pipeline.assert_called_once_with("Does metformin reduce cancer risk?", max_papers=25, seed_claim=None, date_from=None, date_to=None, journals=None)


@patch("src.main.run_full_pipeline", new_callable=AsyncMock)
def test_cli_analyze_command_with_seed_claim(
    mock_run_pipeline,
    mock_pipeline_state
):
    # Set up mocks
    mock_run_pipeline.return_value = mock_pipeline_state

    # Run CLI command with seed claim
    with patch.object(settings, "gemini_api_key", "mock-key"):
        result = runner.invoke(app, ["Does metformin reduce cancer risk?", "--seed-claim", "Metformin increases risk"])

    # Assert success and outputs
    assert result.exit_code == 0
    assert "RESEARCH SYNTHESIS & CONTRADICTION ENGINE" in result.stdout
    assert "Pipeline Execution Statistics" in result.stdout

    # Verify mocks called correctly
    mock_run_pipeline.assert_called_once_with("Does metformin reduce cancer risk?", max_papers=25, seed_claim="Metformin increases risk", date_from=None, date_to=None, journals=None)


@patch("src.main.run_full_pipeline", new_callable=AsyncMock)
def test_cli_analyze_command_with_filters(
    mock_run_pipeline,
    mock_pipeline_state
):
    # Set up mocks
    mock_run_pipeline.return_value = mock_pipeline_state

    # Run CLI command with search filters
    with patch.object(settings, "gemini_api_key", "mock-key"):
        result = runner.invoke(app, [
            "Does metformin reduce cancer risk?",
            "--date-from", "2018",
            "--date-to", "2023",
            "--journal", "Nature",
            "--journal", "Science"
        ])

    # Assert success and outputs
    assert result.exit_code == 0
    assert "RESEARCH SYNTHESIS & CONTRADICTION ENGINE" in result.stdout

    # Verify mocks called correctly
    mock_run_pipeline.assert_called_once_with(
        "Does metformin reduce cancer risk?",
        max_papers=25,
        seed_claim=None,
        date_from=2018,
        date_to=2023,
        journals=["Nature", "Science"]
    )


