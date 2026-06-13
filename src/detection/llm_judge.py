import asyncio
import logging
from pathlib import Path
from typing import TypeVar, Type, Literal, Any

from pydantic import BaseModel, field_validator
from src.config import settings
from src.llm.base import LLMProvider
from src.models.claim import Claim
from src.models.contradiction import ContradictionPair, ContradictionType

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).resolve().parent.parent / "extraction" / "prompts" / "judge_prompt.txt"

class JudgeResponse(BaseModel):
    is_same_topic: bool
    is_contradiction: bool
    is_genuine: bool
    contradiction_type: ContradictionType | Literal["NONE"]
    explanation: str
    scope_note: str

    @field_validator("contradiction_type", mode="before")
    @classmethod
    def normalize_contradiction_type(cls, v: Any) -> Any:
        if isinstance(v, str):
            normalized = v.strip().upper().replace(" ", "_").replace("-", "_")
            if normalized == "NONE":
                return "NONE"
            try:
                return ContradictionType(normalized)
            except ValueError:
                logger.warning(
                    f"Unknown contradiction_type from LLM: '{v}'. "
                    f"Falling back to DIRECT_NEGATION."
                )
                return ContradictionType.DIRECT_NEGATION
        return v

_JUDGE_PROMPT = None

def load_prompt() -> str:
    """Load the judge prompt template from judge_prompt.txt."""
    global _JUDGE_PROMPT
    if _JUDGE_PROMPT is None:
        if not PROMPT_FILE.exists():
            # Minimal inline fallback if file doesn't exist for some reason
            _JUDGE_PROMPT = (
                "You are a scientific contradiction judge. Given two claims, determine if "
                "they discuss the same topic, contradict each other, and if it is genuine or "
                "a scope mismatch."
            )
        else:
            with open(PROMPT_FILE, "r", encoding="utf-8") as f:
                _JUDGE_PROMPT = f.read()
    return _JUDGE_PROMPT


def format_claim(claim: Claim) -> str:
    """Format claim details for LLM context."""
    authors_str = ", ".join(claim.authors) if claim.authors else "Unknown"
    return (
        f"- Text: {claim.text}\n"
        f"- Polarity: {claim.polarity}\n"
        f"- Population: {claim.population}\n"
        f"- Context: {claim.context}\n"
        f"- Quote Anchor: {claim.quote_anchor}\n"
        f"- Study Design: {claim.study_design}\n"
        f"- Authors: {authors_str}\n"
        f"- Year: {claim.year}"
    )

async def judge_contradiction_pair(
    claim_a: Claim,
    claim_b: Claim,
    llm: LLMProvider,
    score: float = 1.0,
) -> ContradictionPair | None:
    """Judge a single candidate pair.
    Returns ContradictionPair if genuine (or scope mismatch), None if not a contradiction.
    """
    prompt_template = load_prompt()
    query = (
        f"Please evaluate the following two claims:\n\n"
        f"=== Claim A ===\n{format_claim(claim_a)}\n\n"
        f"=== Claim B ===\n{format_claim(claim_b)}\n\n"
        f"Ensure you return a valid JSON object matching the required schema."
    )
    
    full_prompt = f"{prompt_template}\n\n{query}"
    
    try:
        response: JudgeResponse = await llm.generate_structured(
            prompt=full_prompt,
            response_schema=JudgeResponse,
            temperature=0.1
        )
    except Exception as e:
        logger.error(f"Error calling LLM judge: {e}")
        return None

    if not response.is_same_topic or not response.is_contradiction:
        return None

    # Parse and map the contradiction type to our enum
    c_type = response.contradiction_type
    if c_type == "NONE":
        if not response.is_genuine:
            c_type = ContradictionType.SCOPE_MISMATCH
        else:
            logger.warning(
                f"LLM returned is_genuine=True but contradiction_type=NONE for "
                f"pair ({claim_a.id}, {claim_b.id}). Skipping pair."
            )
            return None

    # Run programmatic temporal analysis check for genuine contradictions
    temporal_res = None
    if response.is_genuine:
        from src.detection.temporal import check_temporal_supersession
        is_superseded, temporal_explanation = check_temporal_supersession(claim_a, claim_b)
        if is_superseded:
            c_type = ContradictionType.TEMPORAL_SUPERSESSION
            temporal_res = temporal_explanation

    return ContradictionPair(
        claim_a=claim_a,
        claim_b=claim_b,
        contradiction_score=score,
        contradiction_type=c_type,
        explanation=response.explanation,
        scope_note=response.scope_note,
        temporal_resolution=temporal_res,
        is_genuine=response.is_genuine
    )

async def judge_batch(
    candidates: list[tuple[Claim, Claim, float]],
    llm: LLMProvider,
) -> list[ContradictionPair]:
    """Judge all candidates concurrently.
    Uses asyncio.Semaphore for rate limiting based on settings.llm_concurrency.
    """
    sem = asyncio.Semaphore(settings.llm_concurrency)
    
    async def limit_judge(claim_a: Claim, claim_b: Claim, score: float) -> ContradictionPair | None:
        async with sem:
            return await judge_contradiction_pair(claim_a, claim_b, llm, score)
            
    tasks = [
        limit_judge(c[0], c[1], c[2])
        for c in candidates
    ]
    
    results = await asyncio.gather(*tasks)
    # Filter out None results
    return [r for r in results if r is not None]
