import logging
from src.models.claim import Claim, StudyDesign

logger = logging.getLogger(__name__)

STUDY_DESIGN_STRENGTH = {
    StudyDesign.META_ANALYSIS: 7,
    StudyDesign.RCT: 6,
    StudyDesign.COHORT: 5,
    StudyDesign.CASE_CONTROL: 4,
    StudyDesign.REVIEW: 3,
    StudyDesign.CASE_REPORT: 2,
    StudyDesign.IN_VITRO: 1,
}

def check_temporal_supersession(claim_a: Claim, claim_b: Claim) -> tuple[bool, str | None]:
    """Check if one claim temporally supersedes the other.
    
    A newer claim supersedes an older claim if it has:
    1. A strictly stronger study design.
    2. An equal or stronger study design AND a strictly larger sample size.
    3. An equal study design AND equal or unknown sample sizes.

    Returns:
        tuple: (is_superseded, explanation_string or None)
    """
    if claim_a.year == claim_b.year:
        return False, None

    # Identify older and newer claims
    if claim_b.year > claim_a.year:
        older, newer = claim_a, claim_b
        newer_label, older_label = "Claim B", "Claim A"
    else:
        older, newer = claim_b, claim_a
        newer_label, older_label = "Claim A", "Claim B"

    # Get strengths
    strength_older = STUDY_DESIGN_STRENGTH.get(older.study_design, 0)
    strength_newer = STUDY_DESIGN_STRENGTH.get(newer.study_design, 0)

    # 1. Newer has strictly stronger study design
    has_stronger_design = strength_newer > strength_older
    has_equal_design = strength_newer == strength_older

    # 2. Newer has larger sample size
    has_larger_sample = False
    sample_info = ""
    if newer.sample_size is not None and older.sample_size is not None:
        if newer.sample_size > older.sample_size:
            has_larger_sample = True
        sample_info = f" (N={newer.sample_size} vs. N={older.sample_size})"
    elif newer.sample_size is not None:
        sample_info = f" (N={newer.sample_size} vs. unknown N)"
    elif older.sample_size is not None:
        sample_info = f" (unknown N vs. N={older.sample_size})"

    is_superseded = False
    reason = ""

    if has_stronger_design:
        is_superseded = True
        reason = f"it is newer and has a stronger study design ({newer.study_design.value} vs. {older.study_design.value})"
    elif has_larger_sample and strength_newer >= strength_older:
        is_superseded = True
        reason = f"it is newer, has a larger sample size{sample_info}, and an equal/stronger study design ({newer.study_design.value} vs. {older.study_design.value})"

    if is_superseded:
        explanation = f"{newer_label} ({newer.year}, {newer.study_design.value}{sample_info}) supersedes {older_label} ({older.year}, {older.study_design.value}) because {reason}."
        return True, explanation

    return False, None
