import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock

from src.models.claim import Claim, ClaimType, Polarity, StudyDesign
from src.models.contradiction import ContradictionType
from src.detection.contradiction_detector import detect_contradictions
from src.detection.llm_judge import JudgeResponse

@pytest.fixture
def ten_claims():
    claims = [
        # Genuine Contradiction 1
        Claim(
            id=uuid.uuid4(),
            text="Metformin decreases cancer risk.",
            paper_id="paper_1",
            authors=["Author A"],
            year=2020,
            confidence_score=1.0,
            claim_type=ClaimType.CAUSAL,
            polarity=Polarity.NEGATIVE,
            population="humans",
            context="metformin 1000mg",
            quote_anchor="decreases risk",
            study_design=StudyDesign.RCT
        ),
        Claim(
            id=uuid.uuid4(),
            text="Metformin increases cancer risk.",
            paper_id="paper_2",
            authors=["Author B"],
            year=2021,
            confidence_score=1.0,
            claim_type=ClaimType.CAUSAL,
            polarity=Polarity.POSITIVE,
            population="humans",
            context="metformin 1000mg",
            quote_anchor="increases risk",
            study_design=StudyDesign.RCT
        ),
        
        # Genuine Contradiction 2
        Claim(
            id=uuid.uuid4(),
            text="AMPK activation inhibits mTOR pathways.",
            paper_id="paper_3",
            authors=["Author C"],
            year=2019,
            confidence_score=1.0,
            claim_type=ClaimType.CAUSAL,
            polarity=Polarity.NEGATIVE,
            population="in vitro cells",
            context="AMPK activation",
            quote_anchor="inhibits mTOR",
            study_design=StudyDesign.IN_VITRO
        ),
        Claim(
            id=uuid.uuid4(),
            text="AMPK activation stimulates mTOR pathways.",
            paper_id="paper_4",
            authors=["Author D"],
            year=2022,
            confidence_score=1.0,
            claim_type=ClaimType.CAUSAL,
            polarity=Polarity.POSITIVE,
            population="in vitro cells",
            context="AMPK activation",
            quote_anchor="stimulates mTOR",
            study_design=StudyDesign.IN_VITRO
        ),

        # Scope Mismatch
        Claim(
            id=uuid.uuid4(),
            text="Aspirin reduces mortality in cardiovascular disease in humans.",
            paper_id="paper_5",
            authors=["Author E"],
            year=2018,
            confidence_score=1.0,
            claim_type=ClaimType.CAUSAL,
            polarity=Polarity.NEGATIVE,
            population="humans",
            context="aspirin 81mg",
            quote_anchor="reduces mortality",
            study_design=StudyDesign.RCT
        ),
        Claim(
            id=uuid.uuid4(),
            text="Aspirin does not reduce mortality in cardiovascular disease in mice.",
            paper_id="paper_6",
            authors=["Author F"],
            year=2020,
            confidence_score=1.0,
            claim_type=ClaimType.CAUSAL,
            polarity=Polarity.NEUTRAL,
            population="mice",
            context="aspirin dosage",
            quote_anchor="does not reduce mortality",
            study_design=StudyDesign.RCT
        ),

        # 4 Unrelated Claims (to make up 10 claims)
        Claim(
            id=uuid.uuid4(),
            text="Paris is the capital of France.",
            paper_id="paper_7",
            authors=["Author G"],
            year=2015,
            confidence_score=1.0,
            claim_type=ClaimType.DEFINITIONAL,
            polarity=Polarity.POSITIVE,
            population="general",
            context="geography",
            quote_anchor="capital",
            study_design=StudyDesign.REVIEW
        ),
        Claim(
            id=uuid.uuid4(),
            text="Photosynthesis converts light energy into chemical energy.",
            paper_id="paper_8",
            authors=["Author H"],
            year=2016,
            confidence_score=1.0,
            claim_type=ClaimType.MECHANISTIC,
            polarity=Polarity.POSITIVE,
            population="plants",
            context="sunlight",
            quote_anchor="converts light",
            study_design=StudyDesign.REVIEW
        ),
        Claim(
            id=uuid.uuid4(),
            text="Water boils at 100 degrees Celsius under normal pressure.",
            paper_id="paper_9",
            authors=["Author I"],
            year=2017,
            confidence_score=1.0,
            claim_type=ClaimType.DEFINITIONAL,
            polarity=Polarity.POSITIVE,
            population="water",
            context="standard pressure",
            quote_anchor="boils",
            study_design=StudyDesign.REVIEW
        ),
        Claim(
            id=uuid.uuid4(),
            text="Sleep deprivation impairs cognitive performance in adults.",
            paper_id="paper_10",
            authors=["Author J"],
            year=2021,
            confidence_score=1.0,
            claim_type=ClaimType.CAUSAL,
            polarity=Polarity.NEGATIVE,
            population="adults",
            context="sleep deprivation",
            quote_anchor="impairs performance",
            study_design=StudyDesign.COHORT
        )
    ]
    return claims

@pytest.mark.asyncio
async def test_detect_contradictions_integration(ten_claims):
    # Mock LLM provider to return specific responses for our candidate pairs
    mock_llm = MagicMock()
    mock_llm.generate_structured = AsyncMock()

    # The order of calling generate_structured is determined by nli_filtered sorting.
    # NLI results:
    # 1. Metformin claims (very strong contradiction)
    # 2. AMPK claims (very strong contradiction)
    # 3. Aspirin claims (strong contradiction)
    # Let's mock the responses. We will inspect the arguments or return them sequentially.
    # We will write a side_effect function that checks the prompt content to return the correct response.
    def llm_judge_side_effect(prompt, response_schema, temperature=0.1):
        if "Aspirin" in prompt:
            return JudgeResponse(
                is_same_topic=True,
                is_contradiction=True,
                is_genuine=False,
                contradiction_type="SCOPE_MISMATCH",
                explanation="Claim A is human study, Claim B is mouse study.",
                scope_note="Humans vs Mice"
            )
        elif "AMPK" in prompt:
            return JudgeResponse(
                is_same_topic=True,
                is_contradiction=True,
                is_genuine=True,
                contradiction_type="DIRECTION_REVERSAL",
                explanation="Claim A inhibits mTOR, Claim B stimulates mTOR.",
                scope_note=""
            )
        elif "Metformin" in prompt:
            return JudgeResponse(
                is_same_topic=True,
                is_contradiction=True,
                is_genuine=True,
                contradiction_type="DIRECTION_REVERSAL",
                explanation="Claim A decreases risk, Claim B increases risk.",
                scope_note=""
            )
        else:
            return JudgeResponse(
                is_same_topic=False,
                is_contradiction=False,
                is_genuine=False,
                contradiction_type="NONE",
                explanation="No relation.",
                scope_note=""
            )

    mock_llm.generate_structured.side_effect = llm_judge_side_effect

    # Run full detection with patched low threshold to let scope mismatch pass NLI
    from unittest.mock import patch
    from src.config import settings
    with patch.object(settings, "nli_contradiction_threshold", 0.1):
        contradictions = await detect_contradictions(ten_claims, llm=mock_llm)

    # We expect 3 contradictions (2 genuine, 1 scope mismatch)
    assert len(contradictions) == 3

    # Verify genuine contradictions
    genuine_pairs = [c for c in contradictions if c.is_genuine]
    assert len(genuine_pairs) == 2
    
    # Confirm Metformin pair is found
    metformin_pair = [c for c in genuine_pairs if "Metformin" in c.claim_a.text]
    assert len(metformin_pair) == 1
    assert metformin_pair[0].contradiction_type == ContradictionType.DIRECTION_REVERSAL

    # Confirm AMPK pair is found
    ampk_pair = [c for c in genuine_pairs if "AMPK" in c.claim_a.text]
    assert len(ampk_pair) == 1
    assert ampk_pair[0].contradiction_type == ContradictionType.DIRECTION_REVERSAL

    # Verify scope mismatch
    scope_mismatch_pairs = [c for c in contradictions if not c.is_genuine]
    assert len(scope_mismatch_pairs) == 1
    assert "Aspirin" in scope_mismatch_pairs[0].claim_a.text
    assert scope_mismatch_pairs[0].contradiction_type == ContradictionType.SCOPE_MISMATCH
    assert scope_mismatch_pairs[0].scope_note == "Humans vs Mice"
