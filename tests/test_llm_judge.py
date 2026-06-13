import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock

from src.models.claim import Claim, ClaimType, Polarity, StudyDesign, Entity, EntityType
from src.models.contradiction import ContradictionType
from src.detection.llm_judge import judge_contradiction_pair, judge_batch, JudgeResponse

@pytest.fixture
def claim_a():
    return Claim(
        id=uuid.uuid4(),
        text="Metformin reduces breast cancer risk.",
        paper_id="paper_1",
        authors=["Author A"],
        year=2020,
        confidence_score=1.0,
        claim_type=ClaimType.CAUSAL,
        polarity=Polarity.NEGATIVE,
        population="humans",
        context="general",
        quote_anchor="reduced risk",
        study_design=StudyDesign.RCT
    )

@pytest.fixture
def claim_b():
    return Claim(
        id=uuid.uuid4(),
        text="Metformin increases breast cancer risk.",
        paper_id="paper_2",
        authors=["Author B"],
        year=2021,
        confidence_score=1.0,
        claim_type=ClaimType.CAUSAL,
        polarity=Polarity.POSITIVE,
        population="humans",
        context="general",
        quote_anchor="increased risk",
        study_design=StudyDesign.RCT
    )

@pytest.mark.asyncio
async def test_judge_genuine_contradiction(claim_a, claim_b):
    mock_llm = MagicMock()
    mock_llm.generate_structured = AsyncMock(
        return_value=JudgeResponse(
            is_same_topic=True,
            is_contradiction=True,
            is_genuine=True,
            contradiction_type="DIRECTION_REVERSAL",
            explanation="Claim A decreases risk, Claim B increases risk.",
            scope_note=""
        )
    )
    
    pair = await judge_contradiction_pair(claim_a, claim_b, mock_llm, score=0.9)
    assert pair is not None
    assert pair.is_genuine is True
    assert pair.contradiction_type == ContradictionType.DIRECTION_REVERSAL
    assert pair.contradiction_score == 0.9
    assert pair.explanation == "Claim A decreases risk, Claim B increases risk."

@pytest.mark.asyncio
async def test_judge_scope_mismatch(claim_a, claim_b):
    mock_llm = MagicMock()
    mock_llm.generate_structured = AsyncMock(
        return_value=JudgeResponse(
            is_same_topic=True,
            is_contradiction=True,
            is_genuine=False,
            contradiction_type="SCOPE_MISMATCH",
            explanation="Different populations.",
            scope_note="Claim A is in vitro, Claim B is in vivo."
        )
    )
    
    pair = await judge_contradiction_pair(claim_a, claim_b, mock_llm, score=0.85)
    assert pair is not None
    assert pair.is_genuine is False
    assert pair.contradiction_type == ContradictionType.SCOPE_MISMATCH
    assert pair.scope_note == "Claim A is in vitro, Claim B is in vivo."

@pytest.mark.asyncio
async def test_judge_not_contradiction(claim_a, claim_b):
    mock_llm = MagicMock()
    mock_llm.generate_structured = AsyncMock(
        return_value=JudgeResponse(
            is_same_topic=False,
            is_contradiction=False,
            is_genuine=False,
            contradiction_type="NONE",
            explanation="Different topics entirely.",
            scope_note=""
        )
    )
    
    pair = await judge_contradiction_pair(claim_a, claim_b, mock_llm)
    assert pair is None

@pytest.mark.asyncio
async def test_judge_batch(claim_a, claim_b):
    mock_llm = MagicMock()
    
    # Return one genuine contradiction and one non-contradiction
    mock_llm.generate_structured = AsyncMock()
    mock_llm.generate_structured.side_effect = [
        JudgeResponse(
            is_same_topic=True,
            is_contradiction=True,
            is_genuine=True,
            contradiction_type="DIRECTION_REVERSAL",
            explanation="Contradiction",
            scope_note=""
        ),
        JudgeResponse(
            is_same_topic=False,
            is_contradiction=False,
            is_genuine=False,
            contradiction_type="NONE",
            explanation="Not same topic",
            scope_note=""
        )
    ]
    
    candidates = [
        (claim_a, claim_b, 0.9),
        (claim_a, claim_a, 0.5)
    ]
    
    pairs = await judge_batch(candidates, mock_llm)
    assert len(pairs) == 1
    assert pairs[0].contradiction_score == 0.9
    assert pairs[0].is_genuine is True
    assert pairs[0].contradiction_type == ContradictionType.DIRECTION_REVERSAL

@pytest.mark.asyncio
async def test_judge_prompt_construction(claim_a, claim_b):
    mock_llm = MagicMock()
    mock_llm.generate_structured = AsyncMock(
        return_value=JudgeResponse(
            is_same_topic=True,
            is_contradiction=True,
            is_genuine=True,
            contradiction_type="DIRECTION_REVERSAL",
            explanation="Claim A decreases risk, Claim B increases risk.",
            scope_note=""
        )
    )
    
    await judge_contradiction_pair(claim_a, claim_b, mock_llm)
    
    mock_llm.generate_structured.assert_called_once()
    call_args = mock_llm.generate_structured.call_args[1]
    prompt = call_args["prompt"]
    
    # Verify key details of claim_a are in the prompt
    assert claim_a.text in prompt
    assert claim_a.polarity in prompt
    assert claim_a.population in prompt
    assert claim_a.context in prompt
    assert claim_a.quote_anchor in prompt
    assert claim_a.study_design in prompt
    assert "Author A" in prompt
    assert str(claim_a.year) in prompt
    
    # Verify key details of claim_b are in the prompt
    assert claim_b.text in prompt
    assert claim_b.polarity in prompt
    assert claim_b.population in prompt
    assert claim_b.context in prompt
    assert claim_b.quote_anchor in prompt
    assert claim_b.study_design in prompt
    assert "Author B" in prompt
    assert str(claim_b.year) in prompt
    
    # Verify loaded judge prompt template is in the prompt
    from src.detection.llm_judge import load_prompt
    assert load_prompt() in prompt

@pytest.mark.asyncio
async def test_judge_none_contradiction_mapping_genuine(claim_a, claim_b):
    # Tests mapping c_type == "NONE" and is_genuine=True to returning None (skipping)
    mock_llm = MagicMock()
    mock_llm.generate_structured = AsyncMock(
        return_value=JudgeResponse(
            is_same_topic=True,
            is_contradiction=True,
            is_genuine=True,
            contradiction_type="NONE",
            explanation="Contradiction details",
            scope_note=""
        )
    )
    
    pair = await judge_contradiction_pair(claim_a, claim_b, mock_llm)
    assert pair is None

@pytest.mark.asyncio
async def test_judge_none_contradiction_mapping_mismatch(claim_a, claim_b):
    # Tests mapping c_type == "NONE" and is_genuine=False to ContradictionType.SCOPE_MISMATCH
    mock_llm = MagicMock()
    mock_llm.generate_structured = AsyncMock(
        return_value=JudgeResponse(
            is_same_topic=True,
            is_contradiction=True,
            is_genuine=False,
            contradiction_type="NONE",
            explanation="Different scope details",
            scope_note="different cells"
        )
    )
    
    pair = await judge_contradiction_pair(claim_a, claim_b, mock_llm)
    assert pair is not None
    assert pair.is_genuine is False
    assert pair.contradiction_type == ContradictionType.SCOPE_MISMATCH
    assert pair.scope_note == "different cells"


def test_judge_response_contradiction_type_normalization():
    # Test lowercase with spaces
    data_lower_space = (
        '{"is_same_topic": true, "is_contradiction": true, "is_genuine": true, '
        '"contradiction_type": "direction reversal", "explanation": "test", "scope_note": ""}'
    )
    res = JudgeResponse.model_validate_json(data_lower_space)
    assert res.contradiction_type == ContradictionType.DIRECTION_REVERSAL

    # Test lowercase "none"
    data_none = (
        '{"is_same_topic": false, "is_contradiction": false, "is_genuine": false, '
        '"contradiction_type": "none", "explanation": "test", "scope_note": ""}'
    )
    res = JudgeResponse.model_validate_json(data_none)
    assert res.contradiction_type == "NONE"

    # Test hyphenated and mixed casing
    data_hyphen = (
        '{"is_same_topic": true, "is_contradiction": true, "is_genuine": false, '
        '"contradiction_type": "Scope-Mismatch", "explanation": "test", "scope_note": "note"}'
    )
    res = JudgeResponse.model_validate_json(data_hyphen)
    assert res.contradiction_type == ContradictionType.SCOPE_MISMATCH


def test_judge_response_contradiction_type_fallback():
    # Test invalid / unexpected contradiction type fallback
    data_invalid = (
        '{"is_same_topic": true, "is_contradiction": true, "is_genuine": true, '
        '"contradiction_type": "FACTUAL_MISMATCH", "explanation": "test", "scope_note": ""}'
    )
    res = JudgeResponse.model_validate_json(data_invalid)
    assert res.contradiction_type == ContradictionType.DIRECT_NEGATION


