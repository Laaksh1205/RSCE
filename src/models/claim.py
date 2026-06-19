from enum import Enum
from uuid import UUID
from pydantic import BaseModel, Field

class ClaimType(str, Enum):
    CAUSAL = "CAUSAL"
    CORRELATIONAL = "CORRELATIONAL"
    QUANTITATIVE = "QUANTITATIVE"
    DEFINITIONAL = "DEFINITIONAL"
    MECHANISTIC = "MECHANISTIC"

class Polarity(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"

class StudyDesign(str, Enum):
    META_ANALYSIS = "META_ANALYSIS"
    RCT = "RCT"
    COHORT = "COHORT"
    CASE_CONTROL = "CASE_CONTROL"
    IN_VITRO = "IN_VITRO"
    CASE_REPORT = "CASE_REPORT"
    REVIEW = "REVIEW"

class EntityType(str, Enum):
    DRUG = "DRUG"
    GENE = "GENE"
    DISEASE = "DISEASE"
    PROTEIN = "PROTEIN"
    PATHWAY = "PATHWAY"
    BIOMARKER = "BIOMARKER"

class Entity(BaseModel):
    text: str
    canonical_id: str | None = None
    entity_type: EntityType

class Claim(BaseModel):
    id: UUID
    text: str
    normalized_text: str | None = None
    paper_id: str
    section: str = "Abstract"
    authors: list[str] = Field(default_factory=list)
    year: int
    confidence_score: float
    claim_type: ClaimType
    polarity: Polarity
    entities: list[Entity] = Field(default_factory=list)
    population: str
    context: str
    quote_anchor: str
    sample_size: int | None = None
    study_design: StudyDesign
    is_primary_finding: bool = True
    embedding: list[float] | None = None

class ExtractedClaim(BaseModel):
    """Single claim as returned by the LLM (before validation and database mapping)."""
    text: str
    polarity: Polarity
    population: str
    context: str
    quote_anchor: str
    claim_type: ClaimType
    study_design: StudyDesign
    sample_size: int | None = None
    entities: list[Entity] = Field(default_factory=list)

class ClaimExtractionResponse(BaseModel):
    """LLM's complete response for one abstract."""
    claims: list[ExtractedClaim]
