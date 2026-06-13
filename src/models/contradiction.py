from enum import Enum
from pydantic import BaseModel
from src.models.claim import Claim

class ContradictionType(str, Enum):
    DIRECT_NEGATION = "DIRECT_NEGATION"
    QUANTITATIVE_CONFLICT = "QUANTITATIVE_CONFLICT"
    DIRECTION_REVERSAL = "DIRECTION_REVERSAL"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    TEMPORAL_SUPERSESSION = "TEMPORAL_SUPERSESSION"
    METHODOLOGICAL_CONFLICT = "METHODOLOGICAL_CONFLICT"

class ContradictionPair(BaseModel):
    claim_a: Claim
    claim_b: Claim
    contradiction_score: float
    contradiction_type: ContradictionType
    explanation: str
    scope_note: str
    temporal_resolution: str | None = None
    is_genuine: bool
