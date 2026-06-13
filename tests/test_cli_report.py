import pytest
import uuid
from src.models.claim import Claim, ClaimType, Polarity, StudyDesign
from src.models.contradiction import ContradictionPair, ContradictionType
from src.models.report import SynthesisReport
from src.presentation.cli_report import print_cli_report

@pytest.fixture
def dummy_report():
    claim_a = Claim(
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

    claim_b = Claim(
        id=uuid.uuid4(),
        text="Metformin increases breast cancer risk.",
        paper_id="67890",
        authors=["Jane Doe"],
        year=2024,
        confidence_score=1.0,
        claim_type=ClaimType.CAUSAL,
        polarity=Polarity.POSITIVE,
        population="humans",
        context="general",
        quote_anchor="increased breast cancer risk",
        study_design=StudyDesign.RCT
    )

    contradiction = ContradictionPair(
        claim_a=claim_a,
        claim_b=claim_b,
        contradiction_score=0.95,
        contradiction_type=ContradictionType.DIRECTION_REVERSAL,
        explanation="Claim A decreases risk, Claim B increases risk.",
        scope_note="No scope mismatch, both human populations.",
        is_genuine=True
    )

    report = SynthesisReport(
        summary="Metformin has contradictory effects on breast cancer risk based on recent RCTs.",
        contradictions=[contradiction],
        consensus_scores={},
        total_papers=2,
        total_claims=2,
        metadata={"time_elapsed": 4.5, "cost_estimate": 0.05}
    )
    return report

def test_print_cli_report(capsys, dummy_report):
    print_cli_report(
        report=dummy_report,
        query="Does metformin reduce breast cancer risk?",
        time_elapsed=4.5,
        cost_estimate=0.05
    )
    captured = capsys.readouterr()
    
    # Check that key sections and text are printed
    assert "🔬 RESEARCH SYNTHESIS & CONTRADICTION ENGINE" in captured.out
    assert "Does metformin reduce breast cancer risk?" in captured.out
    assert "Pipeline Execution Statistics" in captured.out
    assert "Grounded Synthesis Narrative" in captured.out
    assert "Metformin has contradictory effects" in captured.out
    assert "Ranked Contradictions Overview" in captured.out
    assert "DIRECTION_REVERSAL" in captured.out
    assert "GENUINE CONTRADICTION" in captured.out
    assert "John Smith" in captured.out
    assert "Jane Doe" in captured.out
    assert "Claim A decreases risk, Claim B increases risk." in captured.out
