from typing import Any
from pydantic import BaseModel, Field
from src.models.contradiction import ContradictionPair

class SynthesisReport(BaseModel):
    summary: str
    contradictions: list[ContradictionPair] = Field(default_factory=list)
    consensus_scores: dict[str, Any] = Field(default_factory=dict)
    knowledge_gaps: list[str] = Field(default_factory=list)
    total_papers: int
    total_claims: int
    metadata: dict[str, Any] = Field(default_factory=dict)
