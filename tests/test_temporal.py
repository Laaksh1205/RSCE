import uuid
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
    # Newer Meta-Analysis should supersede older Cohort (gap = 5 >= 3, rank 3 > rank 1)
    older_claim = make_claim(year=2015, study_design=StudyDesign.COHORT)
    newer_claim = make_claim(year=2020, study_design=StudyDesign.META_ANALYSIS)
    
    is_superseded, explanation = check_temporal_supersession(older_claim, newer_claim)
    assert is_superseded is True
    assert explanation is not None
    assert "supersedes" in explanation
    assert "higher-ranked study design category" in explanation
    
    # Swapped inputs should still correctly identify newer superseding older
    is_superseded_swap, explanation_swap = check_temporal_supersession(newer_claim, older_claim)
    assert is_superseded_swap is True
    assert explanation_swap is not None
    assert "supersedes" in explanation_swap

def test_equal_study_design_rank_no_supersession():
    # Same study design (RCT vs RCT) with different sample sizes should NOT supersede
    older_claim = make_claim(year=2018, study_design=StudyDesign.RCT, sample_size=100)
    newer_claim = make_claim(year=2024, study_design=StudyDesign.RCT, sample_size=500)
    
    is_superseded, explanation = check_temporal_supersession(older_claim, newer_claim)
    assert is_superseded is False
    assert explanation is None

def test_insufficient_year_gap_no_supersession():
    # Newer has higher rank but year gap is less than 3 years (e.g. 2020 vs 2022)
    older_claim = make_claim(year=2020, study_design=StudyDesign.RCT)
    newer_claim = make_claim(year=2022, study_design=StudyDesign.META_ANALYSIS)
    
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

def test_missing_year_no_supersession():
    # Missing year (0) should not trigger supersession
    older_claim = make_claim(year=0, study_design=StudyDesign.RCT)
    newer_claim = make_claim(year=2020, study_design=StudyDesign.META_ANALYSIS)
    
    is_superseded, explanation = check_temporal_supersession(older_claim, newer_claim)
    assert is_superseded is False
    assert explanation is None

