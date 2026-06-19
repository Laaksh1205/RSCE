import pytest
import os
import uuid
import numpy as np
import tempfile
from unittest.mock import patch, MagicMock, AsyncMock
from src.models.claim import Claim, ClaimType, Polarity, StudyDesign
from src.config import settings
from src.detection.contradiction_detector import detect_contradictions
from src.detection.llm_judge import JudgeResponse
from src.detection.faiss_index import ClaimIndex

@pytest.mark.asyncio
async def test_faiss_persistence_and_embedding_caching():
    # 1. Prepare sample claims, some with embeddings, some without
    claim_a_id = uuid.uuid4()
    claim_b_id = uuid.uuid4()
    
    emb_dummy_a = [0.1] * 384
    emb_dummy_b = [0.2] * 384
    
    claim_a = Claim(
        id=claim_a_id,
        text="Aspirin reduces risk.",
        paper_id="paper_1",
        authors=["Author A"],
        year=2020,
        confidence_score=1.0,
        claim_type=ClaimType.CAUSAL,
        polarity=Polarity.NEGATIVE,
        population="humans",
        context="general",
        quote_anchor="reduces risk",
        study_design=StudyDesign.RCT,
        embedding=emb_dummy_a
    )
    
    claim_b = Claim(
        id=claim_b_id,
        text="Aspirin increases risk.",
        paper_id="paper_2",
        authors=["Author B"],
        year=2021,
        confidence_score=1.0,
        claim_type=ClaimType.CAUSAL,
        polarity=Polarity.POSITIVE,
        population="humans",
        context="general",
        quote_anchor="increases risk",
        study_design=StudyDesign.RCT,
        embedding=None  # Needs embedding!
    )
    
    claims = [claim_a, claim_b]
    
    # 2. Mock ClaimEmbedder so we can check if it gets called, and control its return value
    mock_embedder = MagicMock()
    mock_embedder.embed_claims.return_value = np.array([[0.2] * 384], dtype=np.float32)
    
    # Mock LLM provider to avoid calling the real LLM judge
    mock_llm = MagicMock()
    mock_llm.generate_structured = AsyncMock(return_value=JudgeResponse(
        is_same_topic=True,
        is_contradiction=True,
        is_genuine=True,
        contradiction_type="DIRECTION_REVERSAL",
        explanation="Opposing findings.",
        scope_note=""
    ))

    # Mock save_claims so we don't write to DB in test
    with patch("src.detection.contradiction_detector.ClaimEmbedder", return_value=mock_embedder), \
         patch("src.storage.save_claims") as mock_save_claims, \
         patch("src.detection.contradiction_detector.judge_batch", return_value=[]), \
         tempfile.TemporaryDirectory() as tmpdir:
         
        # Set temp index path
        temp_index_path = os.path.join(tmpdir, "test_claims.faiss")
        
        with patch.object(settings, "faiss_index_path", temp_index_path), \
             patch.object(settings, "nli_contradiction_threshold", 0.0):
            
            # RUN 1: One claim lacks embedding, so it should be embedded
            await detect_contradictions(claims, llm=mock_llm)
            
            # Verify embedder was called ONLY for claim_b (1 claim)
            mock_embedder.embed_claims.assert_called_once_with([claim_b])
            assert claim_b.embedding == pytest.approx(emb_dummy_b, abs=1e-5)
            mock_save_claims.assert_called_once_with([claim_b])
            
            # Verify FAISS index file was created
            assert os.path.exists(temp_index_path)
            
            # Reset mock
            mock_embedder.reset_mock()
            mock_save_claims.reset_mock()
            
            # RUN 2: Both claims now have embeddings, so embedder should NOT be called
            # We wrap load so we can assert it was called
            with patch("src.detection.faiss_index.ClaimIndex.load", wraps=ClaimIndex.load) as mock_load:
                await detect_contradictions(claims, llm=mock_llm)
                
                # Check that embedder was not called
                mock_embedder.embed_claims.assert_not_called()
                mock_save_claims.assert_not_called()
                
                # Check that loaded index from file was called
                mock_load.assert_called_once_with(temp_index_path)
