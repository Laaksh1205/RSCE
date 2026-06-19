import pytest
import uuid
import numpy as np
import tempfile
import os
from unittest.mock import MagicMock, AsyncMock, patch

from src.models.claim import Claim, ClaimType, Polarity, StudyDesign
from src.config import settings
from src.detection.contradiction_detector import detect_contradictions
from src.detection.llm_judge import JudgeResponse
from src.detection.nli_scorer import _MODEL_CACHE


@pytest.mark.asyncio
async def test_detect_contradictions_large_claims_stress():
    # 1. Generate 250 claims (50 papers, 5 claims each)
    claims = []
    
    # Generate 5 orthogonal template vectors of size 384 to guarantee
    # predictable high-similarity candidate pairs across papers
    templates = np.zeros((5, 384), dtype=np.float32)
    for t_idx in range(5):
        templates[t_idx, t_idx] = 1.0
        
    for i in range(250):
        paper_idx = i // 5
        template_idx = i % 5
        claim = Claim(
            id=uuid.uuid4(),
            text=f"Claim {i} from paper {paper_idx}",
            paper_id=f"paper_{paper_idx}",
            authors=[f"Author {paper_idx}"],
            year=2020 + (paper_idx % 5),
            confidence_score=0.9,
            claim_type=ClaimType.CAUSAL,
            polarity=Polarity.POSITIVE,
            population="human population",
            context="stress test context",
            quote_anchor=f"anchor {i}",
            study_design=StudyDesign.RCT,
            embedding=templates[template_idx].tolist()
        )
        claims.append(claim)
        
    # 2. Mock CrossEncoder so we don't load the heavy model in memory or run on CPU
    mock_cross_encoder_instance = MagicMock()
    
    def mock_predict(batch_pairs):
        # Return mock logits representing a high contradiction score for all pairs
        # index 0: contradiction, index 1: entailment, index 2: neutral.
        # Since we use softmax in score_pairs, putting a high value in index 0
        # will yield a contradiction probability close to 1.0.
        b_size = len(batch_pairs)
        mock_logits = np.zeros((b_size, 3), dtype=np.float32)
        mock_logits[:, 0] = 5.0  # High contradiction score
        return mock_logits

    mock_cross_encoder_instance.predict.side_effect = mock_predict

    # 3. Mock LLM provider to avoid actual LLM API calls during the test
    mock_llm = MagicMock()
    mock_llm.generate_structured = AsyncMock()
    mock_llm.generate_structured.return_value = JudgeResponse(
        is_same_topic=True,
        is_contradiction=True,
        is_genuine=True,
        contradiction_type="DIRECTION_REVERSAL",
        explanation="Synthetic contradiction explanation.",
        scope_note=""
    )

    # 4. Use a temporary directory for the FAISS index to avoid overwriting production data
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_faiss_path = os.path.join(tmpdir, "test_claims.faiss")
        
        # Patch settings to use temporary faiss_index_path, set faiss_top_k, and nli_threshold
        # We also patch _MODEL_CACHE to ensure our mock is picked up even if the real model has already been cached by other tests.
        with patch.object(settings, "faiss_index_path", temp_faiss_path), \
             patch.object(settings, "nli_contradiction_threshold", 0.7), \
             patch.object(settings, "faiss_top_k", 10), \
             patch("src.detection.nli_scorer.CrossEncoder", return_value=mock_cross_encoder_instance), \
             patch.dict(_MODEL_CACHE, {settings.nli_model: mock_cross_encoder_instance}, clear=False):
             
            # Track batch progress updates
            nli_batches = []
            def on_nli_batch(current, total):
                nli_batches.append((current, total))


            # Run contradiction detection
            contradictions = await detect_contradictions(
                claims=claims,
                llm=mock_llm,
                on_nli_batch=on_nli_batch
            )

            # 5. Assertions to verify correctness of pipeline execution under large load
            # Verify that the FAISS index was successfully built and saved
            assert os.path.exists(temp_faiss_path)

            # Verify batching callback was triggered correctly and reached completion
            assert len(nli_batches) > 0
            total_batches = nli_batches[0][1]
            assert mock_cross_encoder_instance.predict.call_count == total_batches
            assert len(nli_batches) == total_batches
            assert nli_batches[-1] == (total_batches, total_batches)
            
            # Verify that the final contradictions are correctly generated and capped at max_contradictions_displayed
            assert len(contradictions) <= settings.max_contradictions_displayed
            assert len(contradictions) > 0
            for c in contradictions:
                assert c.is_genuine is True
                assert c.contradiction_score >= 0.7
                assert c.contradiction_type.value == "DIRECTION_REVERSAL"

