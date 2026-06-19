import logging
from src.models.claim import Claim, StudyDesign

logger = logging.getLogger(__name__)

STUDY_DESIGN_CATEGORY_RANK = {
    StudyDesign.META_ANALYSIS: 3,
    StudyDesign.RCT: 2,
    StudyDesign.COHORT: 1,
    StudyDesign.CASE_CONTROL: 1,
    StudyDesign.REVIEW: 0,
    StudyDesign.CASE_REPORT: 0,
    StudyDesign.IN_VITRO: 0,
}

def check_temporal_supersession(claim_a: Claim, claim_b: Claim) -> tuple[bool, str | None]:
    """Check if one claim temporally supersedes the other.
    
    A newer claim supersedes an older claim if:
    1. It is published at least 3 years after the older claim (gap >= 3 years).
    2. It has a strictly higher-ranked study design category:
       META_ANALYSIS (3) > RCT (2) > Observational (1: COHORT, CASE_CONTROL) > Other/Weaker (0).

    Returns:
        tuple: (is_superseded, explanation_string or None)
    """
    # If years are missing or invalid
    if claim_a.year <= 0 or claim_b.year <= 0:
        return False, None

    if claim_a.year == claim_b.year:
        return False, None

    # Identify older and newer claims
    if claim_b.year > claim_a.year:
        older, newer = claim_a, claim_b
        newer_label, older_label = "Claim B", "Claim A"
    else:
        older, newer = claim_b, claim_a
        newer_label, older_label = "Claim A", "Claim B"

    # Enforce strictly >= 3 years gap
    year_gap = newer.year - older.year
    if year_gap < 3:
        return False, None

    # Get category ranks
    rank_older = STUDY_DESIGN_CATEGORY_RANK.get(older.study_design, 0)
    rank_newer = STUDY_DESIGN_CATEGORY_RANK.get(newer.study_design, 0)

    # Newer must be from a strictly higher-ranked category
    if rank_newer > rank_older:
        reason = f"it is newer by {year_gap} years and has a higher-ranked study design category ({newer.study_design.value} vs. {older.study_design.value})"
        explanation = f"{newer_label} ({newer.year}, {newer.study_design.value}) supersedes {older_label} ({older.year}, {older.study_design.value}) because {reason}."
        return True, explanation

    return False, None
