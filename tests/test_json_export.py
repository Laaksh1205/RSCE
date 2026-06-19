import json
import os
import uuid

from src.models.claim import Claim, ClaimType, Polarity, StudyDesign
from src.models.contradiction import ContradictionPair, ContradictionType
from src.models.report import SynthesisReport
from src.presentation.json_export import export_report_to_json, generate_query_slug

def test_generate_query_slug():
    query = "Does metformin reduce breast cancer risk?"
    slug = generate_query_slug(query)
    assert slug == "does_metformin_reduce_breast_cancer_risk"

    query_with_special = "AMPK, mTOR & Cancer: A Review!"
    slug_special = generate_query_slug(query_with_special)
    assert slug_special == "ampk_mtor_cancer_a_review"

def test_export_report_to_json(tmp_path):
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

    # Export to temporary directory path
    saved_file_path = export_report_to_json(
        report=report,
        query="Does metformin reduce breast cancer risk?",
        output_dir=str(tmp_path)
    )

    # Verify file existence
    assert os.path.exists(saved_file_path)
    assert saved_file_path.endswith(".json")

    # Read back and parse JSON
    with open(saved_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Verify content
    assert data["total_papers"] == 2
    assert data["total_claims"] == 2
    assert data["summary"] == "Metformin has contradictory effects on breast cancer risk based on recent RCTs."
    assert len(data["contradictions"]) == 1
    
    saved_contradiction = data["contradictions"][0]
    assert saved_contradiction["contradiction_score"] == 0.95
    assert saved_contradiction["contradiction_type"] == "DIRECTION_REVERSAL"
    assert saved_contradiction["is_genuine"] is True
    assert saved_contradiction["claim_a"]["text"] == "Metformin reduces breast cancer risk."
    assert saved_contradiction["claim_b"]["text"] == "Metformin increases breast cancer risk."
