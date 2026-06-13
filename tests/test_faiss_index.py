import pytest
import numpy as np
import uuid
import tempfile
import os
from src.models.claim import Claim, ClaimType, Polarity, StudyDesign
from src.detection.faiss_index import ClaimIndex

@pytest.fixture
def sample_claims_and_embeddings():
    claims = [
        # Paper 1, Claim 0
        Claim(
            id=uuid.uuid4(),
            text="Metformin reduces breast cancer risk.",
            paper_id="paper_1",
            year=2024,
            confidence_score=1.0,
            claim_type=ClaimType.CAUSAL,
            polarity=Polarity.NEGATIVE,
            population="humans",
            context="general",
            quote_anchor="reduces breast cancer risk",
            study_design=StudyDesign.RCT
        ),
        # Paper 1, Claim 1 (same paper, should be excluded from candidate pairs with Claim 0)
        Claim(
            id=uuid.uuid4(),
            text="Metformin is safe and well-tolerated.",
            paper_id="paper_1",
            year=2024,
            confidence_score=1.0,
            claim_type=ClaimType.CAUSAL,
            polarity=Polarity.POSITIVE,
            population="humans",
            context="general",
            quote_anchor="safe and well-tolerated",
            study_design=StudyDesign.RCT
        ),
        # Paper 2, Claim 2 (different paper, highly similar text to Claim 0)
        Claim(
            id=uuid.uuid4(),
            text="Metformin decreases the risk of developing breast cancer.",
            paper_id="paper_2",
            year=2023,
            confidence_score=1.0,
            claim_type=ClaimType.CAUSAL,
            polarity=Polarity.NEGATIVE,
            population="women",
            context="general",
            quote_anchor="decreases the risk",
            study_design=StudyDesign.COHORT
        ),
        # Paper 3, Claim 3 (different paper, completely unrelated text)
        Claim(
            id=uuid.uuid4(),
            text="Aspirin usage correlates with gastrointestinal bleeding.",
            paper_id="paper_3",
            year=2022,
            confidence_score=1.0,
            claim_type=ClaimType.CORRELATIONAL,
            polarity=Polarity.POSITIVE,
            population="adults",
            context="long-term use",
            quote_anchor="gastrointestinal bleeding",
            study_design=StudyDesign.RCT
        )
    ]
    
    # Create mock normalized embeddings
    # Claim 0 and Claim 2 are very similar (dot product ~ 0.9)
    # Claim 1 is somewhat similar to Claim 0 (dot product ~ 0.5)
    # Claim 3 is orthogonal (dot product ~ 0.0)
    emb0 = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    emb1 = np.array([0.5, 0.866, 0.0, 0.0], dtype=np.float32) # Normalized (0.25 + 0.75 = 1.0)
    emb2 = np.array([0.9, 0.0, 0.436, 0.0], dtype=np.float32) # Normalized (0.81 + 0.19 = 1.0)
    emb3 = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
    
    embeddings = np.stack([emb0, emb1, emb2, emb3])
    return claims, embeddings

def test_claim_index_build_and_search(sample_claims_and_embeddings):
    claims, embeddings = sample_claims_and_embeddings
    
    index = ClaimIndex()
    index.build_index(embeddings)
    
    # Find candidate pairs with min_similarity = 0.3
    pairs = index.find_candidate_pairs(embeddings, claims, top_k=2, min_similarity=0.3)
    
    # Candidate pairs should be:
    # (0, 2) since they are different papers and similarity is 0.9 >= 0.3
    # Note that (0, 1) is excluded because they are from the same paper ('paper_1')
    # Note that (1, 2) has similarity: 0.5 * 0.9 = 0.45 >= 0.3, so it should be included!
    # No matches with Claim 3 (gastrointestinal bleeding) because similarity is 0.0 < 0.3
    
    assert len(pairs) == 2
    
    # First pair should be (0, 2) with highest similarity (~0.9)
    assert pairs[0][0] == 0
    assert pairs[0][1] == 2
    assert pytest.approx(pairs[0][2], abs=1e-5) == 0.9
    
    # Second pair should be (1, 2) with similarity 0.45
    assert pairs[1][0] == 1
    assert pairs[1][1] == 2
    assert pytest.approx(pairs[1][2], abs=1e-5) == 0.45

def test_claim_index_persistence(sample_claims_and_embeddings):
    claims, embeddings = sample_claims_and_embeddings
    
    index = ClaimIndex()
    index.build_index(embeddings)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = os.path.join(tmpdir, "index.faiss")
        index.save(index_path)
        
        assert os.path.exists(index_path)
        
        # Load into a new index
        new_index = ClaimIndex()
        new_index.load(index_path)
        
        # Search again and compare pairs
        pairs_orig = index.find_candidate_pairs(embeddings, claims, min_similarity=0.3)
        pairs_new = new_index.find_candidate_pairs(embeddings, claims, min_similarity=0.3)
        
        assert len(pairs_orig) == len(pairs_new)
        for p1, p2 in zip(pairs_orig, pairs_new):
            assert p1[0] == p2[0]
            assert p1[1] == p2[1]
            assert pytest.approx(p1[2], abs=1e-5) == p2[2]
