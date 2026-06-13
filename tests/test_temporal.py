import uuid
import pytest
from src.models.claim import Claim, ClaimType, Polarity, StudyDesign
from src.detection.temporal import check_temporal_supersession

def make_claim(year: int, study_design: StudyDesign, sample_size: int | None = None) -> Claim:
    return Claim(
        id=uuid.uuid4(),
        text="Sample claim text",
        paper_id="pmid123",
        section="Abstract",
        year=year,
        confidence_score=1.0,
        claim_type=ClaimType.CAUSAL,
        polarity=Polarity.POSITIVE,
        population="human patients",
        context="metformin 1000mg",
        quote_anchor="metformin reduces HbA1c",
        study_design=study_design,
        sample_size=sample_size
    )

def test_design_strength_promotion_supersedes():
    # Newer Meta-Analysis should supersede older Cohort
    older_claim = make_claim(year=2015, study_design=StudyDesign.COHORT)
    newer_claim = make_claim(year=2020, study_design=StudyDesign.META_ANALYSIS)
    
    is_superseded, explanation = check_temporal_supersession(older_claim, newer_claim)
    assert is_superseded is True
    assert explanation is not None
    assert "supersedes" in explanation
    assert "stronger study design" in explanation
    
    # Swapped inputs should still correctly identify Claim B as newer superseding Claim A
    is_superseded_swap, explanation_swap = check_temporal_supersession(newer_claim, older_claim)
    assert is_superseded_swap is True
    assert explanation_swap is not None
    assert "supersedes" in explanation_swap

def test_larger_sample_size_supersedes():
    # Newer RCT with larger sample size should supersede older RCT with smaller sample size
    older_claim = make_claim(year=2018, study_design=StudyDesign.RCT, sample_size=100)
    newer_claim = make_claim(year=2024, study_design=StudyDesign.RCT, sample_size=500)
    
    is_superseded, explanation = check_temporal_supersession(older_claim, newer_claim)
    assert is_superseded is True
    assert "larger sample size" in explanation
    assert "N=500 vs. N=100" in explanation

def test_equal_study_design_and_no_sample_size_no_supersession():
    # Newer RCT with unknown sample size should not supersede older RCT with unknown sample size
    older_claim = make_claim(year=2015, study_design=StudyDesign.RCT)
    newer_claim = make_claim(year=2020, study_design=StudyDesign.RCT)
    
    is_superseded, explanation = check_temporal_supersession(older_claim, newer_claim)
    assert is_superseded is False
    assert explanation is None

def test_same_year_no_supersession():
    # Claims from the same year should not supersede each other
    claim_a = make_claim(year=2020, study_design=StudyDesign.COHORT)
    claim_b = make_claim(year=2020, study_design=StudyDesign.RCT)
    
    is_superseded, explanation = check_temporal_supersession(claim_a, claim_b)
    assert is_superseded is False
    assert explanation is None

def test_weaker_study_design_no_supersession():
    # Newer but weaker study design (Review) should not supersede older stronger study design (RCT)
    older_claim = make_claim(year=2015, study_design=StudyDesign.RCT)
    newer_claim = make_claim(year=2020, study_design=StudyDesign.REVIEW)
    
    is_superseded, explanation = check_temporal_supersession(older_claim, newer_claim)
    assert is_superseded is False
    assert explanation is None
