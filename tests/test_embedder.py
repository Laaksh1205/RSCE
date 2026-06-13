import pytest
import numpy as np
import uuid
from src.models.claim import Claim, ClaimType, Polarity, StudyDesign
from src.detection.embedder import ClaimEmbedder

def test_embedder_single():
    embedder = ClaimEmbedder(model_name="all-MiniLM-L6-v2")
    text = "Metformin reduces cancer incidence."
    
    embedding = embedder.embed_single(text)
    
    assert isinstance(embedding, np.ndarray)
    assert embedding.dtype == np.float32
    assert embedding.shape == (384,)
    
    # Check that embedding is normalized (L2 norm is approximately 1.0)
    norm = np.linalg.norm(embedding)
    assert pytest.approx(norm, abs=1e-5) == 1.0

def test_embedder_batch():
    embedder = ClaimEmbedder(model_name="all-MiniLM-L6-v2")
    
    claims = [
        Claim(
            id=uuid.uuid4(),
            text="Metformin reduces breast cancer cell growth.",
            paper_id="123",
            year=2024,
            confidence_score=1.0,
            claim_type=ClaimType.CAUSAL,
            polarity=Polarity.NEGATIVE,
            population="human cell lines",
            context="in vitro",
            quote_anchor="Metformin inhibits breast cancer cell growth",
            study_design=StudyDesign.IN_VITRO
        ),
        Claim(
            id=uuid.uuid4(),
            text="Metformin activates AMPK pathways.",
            paper_id="123",
            year=2024,
            confidence_score=1.0,
            claim_type=ClaimType.MECHANISTIC,
            polarity=Polarity.POSITIVE,
            population="human cell lines",
            context="in vitro",
            quote_anchor="AMPK activation",
            study_design=StudyDesign.IN_VITRO
        )
    ]
    
    embeddings = embedder.embed_claims(claims)
    
    assert isinstance(embeddings, np.ndarray)
    assert embeddings.dtype == np.float32
    assert embeddings.shape == (2, 384)
    
    # Check normalization for both vectors
    norm_1 = np.linalg.norm(embeddings[0])
    norm_2 = np.linalg.norm(embeddings[1])
    assert pytest.approx(norm_1, abs=1e-5) == 1.0
    assert pytest.approx(norm_2, abs=1e-5) == 1.0
