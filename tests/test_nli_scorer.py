import pytest
import uuid
from src.models.claim import Claim, ClaimType, Polarity, StudyDesign
from src.detection.nli_scorer import NLIScorer

@pytest.fixture(scope="module")
def scorer():
    # Share a single model instance across module tests to avoid loading it multiple times
    return NLIScorer(model_name="cross-encoder/nli-deberta-v3-large")

def test_direct_contradiction(scorer):
    pairs = [
        ("Metformin decreases cancer risk.", "Metformin increases cancer risk."),
        ("AMPK activation inhibits mTOR pathways.", "AMPK activation stimulates mTOR pathways.")
    ]
    results = scorer.score_pairs(pairs)
    
    assert len(results) == 2
    for res in results:
        # Contradiction score should be high
        assert res.contradiction > 0.7
        assert res.contradiction > res.entailment
        assert res.contradiction > res.neutral

def test_entailment(scorer):
    pairs = [
        ("Metformin reduces blood glucose levels.", "Metformin lowers blood sugar levels.")
    ]
    results = scorer.score_pairs(pairs)
    
    assert len(results) == 1
    res = results[0]
    # Entailment score should be high
    assert res.entailment > 0.7
    assert res.entailment > res.contradiction
    assert res.entailment > res.neutral

def test_unrelated(scorer):
    pairs = [
        ("Metformin reduces breast cancer cell growth.", "Paris is the capital of France.")
    ]
    results = scorer.score_pairs(pairs)
    
    assert len(results) == 1
    res = results[0]
    # Neutral score should be high
    assert res.neutral > 0.7
    assert res.neutral > res.contradiction
    assert res.neutral > res.entailment

def test_filter_contradictions(scorer):
    claims = [
        Claim(
            id=uuid.uuid4(),
            text="Metformin inhibits breast cancer progression.",
            paper_id="paper_1",
            year=2024,
            confidence_score=1.0,
            claim_type=ClaimType.CAUSAL,
            polarity=Polarity.NEGATIVE,
            population="humans",
            context="general",
            quote_anchor="inhibits breast cancer progression",
            study_design=StudyDesign.RCT
        ),
        Claim(
            id=uuid.uuid4(),
            text="Metformin promotes breast cancer progression.",
            paper_id="paper_2",
            year=2023,
            confidence_score=1.0,
            claim_type=ClaimType.CAUSAL,
            polarity=Polarity.POSITIVE,
            population="humans",
            context="general",
            quote_anchor="promotes breast cancer progression",
            study_design=StudyDesign.RCT
        ),
        Claim(
            id=uuid.uuid4(),
            text="Metformin is a safe treatment for diabetes.",
            paper_id="paper_3",
            year=2022,
            confidence_score=1.0,
            claim_type=ClaimType.CAUSAL,
            polarity=Polarity.POSITIVE,
            population="humans",
            context="general",
            quote_anchor="safe treatment",
            study_design=StudyDesign.RCT
        )
    ]
    
    # Candidate pairs from FAISS: (idx_a, idx_b, similarity_score)
    # Pair (0, 1) is a contradiction
    # Pair (0, 2) is not a contradiction
    candidate_pairs = [
        (0, 1, 0.9),
        (0, 2, 0.5)
    ]
    
    filtered = scorer.filter_contradictions(candidate_pairs, claims, threshold=0.7)
    
    assert len(filtered) == 1
    # Check that only the contradictory pair (0, 1) was returned
    assert filtered[0][0] == 0
    assert filtered[0][1] == 1
    assert filtered[0][2] == 0.9  # Similarity score
    assert filtered[0][3] > 0.7   # Contradiction score
