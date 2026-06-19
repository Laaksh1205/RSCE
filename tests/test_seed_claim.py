import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np

from src.models.claim import Claim, ClaimType, Polarity, StudyDesign
from src.detection.contradiction_detector import detect_contradictions
from src.detection.llm_judge import JudgeResponse

@pytest.fixture
def paper_claims():
    claims = [
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
            text="AMPK activation inhibits mTOR pathways.",
            paper_id="paper_2",
            authors=["Author B"],
            year=2019,
            confidence_score=1.0,
            claim_type=ClaimType.CAUSAL,
            polarity=Polarity.NEGATIVE,
            population="in vitro cells",
            context="AMPK activation",
            quote_anchor="inhibits mTOR",
            study_design=StudyDesign.IN_VITRO
        )
    ]
    return claims

@pytest.mark.asyncio
async def test_detect_contradictions_with_seed_claim(paper_claims):
    # Mock ClaimEmbedder to return constant vectors of 384 dimensions
    dummy_emb_paper_1 = np.ones(384, dtype=np.float32)
    dummy_emb_paper_1[0] = 5.0  # distinguish slightly
    dummy_emb_paper_2 = np.ones(384, dtype=np.float32)
    dummy_emb_paper_2[0] = -5.0
    dummy_emb_seed = np.ones(384, dtype=np.float32)
    dummy_emb_seed[0] = 4.8  # highly similar to paper_1

    # Normalize vectors so IndexFlatIP acts as cosine similarity
    dummy_emb_paper_1 /= np.linalg.norm(dummy_emb_paper_1)
    dummy_emb_paper_2 /= np.linalg.norm(dummy_emb_paper_2)
    dummy_emb_seed /= np.linalg.norm(dummy_emb_seed)

    mock_embeddings = [dummy_emb_paper_1, dummy_emb_paper_2]
    
    mock_embed_claims = MagicMock()
    mock_embed_claims.side_effect = lambda claims_list: (
        [dummy_emb_seed] if any(c.paper_id == "seed_claim_paper" for c in claims_list)
        else [mock_embeddings[i % len(mock_embeddings)] for i in range(len(claims_list))]
    )

    # Mock database save_claims to verify it does not save the seed claim
    mock_save_claims = MagicMock()

    # Mock LLM provider
    mock_llm = MagicMock()
    mock_llm.generate_structured = AsyncMock()
    mock_llm.generate_structured.return_value = JudgeResponse(
        is_same_topic=True,
        is_contradiction=True,
        is_genuine=True,
        contradiction_type="DIRECTION_REVERSAL",
        explanation="The user assertion conflicts with the paper finding.",
        scope_note=""
    )

    # Mock NLIScorer to let all pairs pass
    mock_nli_filtered = [
        # (idx_a, idx_b, similarity_score, contradiction_score)
        (0, 2, 0.95, 0.99)
    ]

    with patch("src.detection.contradiction_detector.ClaimEmbedder") as mock_embedder_class, \
         patch("src.storage.save_claims", mock_save_claims), \
         patch("src.detection.nli_scorer.NLIScorer.filter_contradictions", return_value=mock_nli_filtered), \
         patch("src.config.settings.faiss_index_path", "data/test_claims.faiss"):
        
        # Set up instance mock
        mock_embedder_inst = MagicMock()
        mock_embedder_inst.embed_claims = mock_embed_claims
        mock_embedder_class.return_value = mock_embedder_inst

        # Run detect_contradictions
        seed_text = "Metformin does not decrease cancer risk."
        contradictions = await detect_contradictions(
            claims=paper_claims,
            llm=mock_llm,
            seed_claim=seed_text
        )

        # Assertions
        assert len(contradictions) == 1
        contr = contradictions[0]
        
        # Verify one of the claims in the contradiction is the seed claim
        assert contr.claim_a.paper_id == "seed_claim_paper" or contr.claim_b.paper_id == "seed_claim_paper"
        
        # Verify that save_claims was NOT called on any seed claims
        for call_args in mock_save_claims.call_args_list:
            claims_arg = call_args[0][0]
            assert not any(c.paper_id == "seed_claim_paper" for c in claims_arg)
