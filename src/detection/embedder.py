import numpy as np
from sentence_transformers import SentenceTransformer
from src.models.claim import Claim

class ClaimEmbedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)

    def embed_claims(self, claims: list[Claim]) -> np.ndarray:
        """Batch encode claim texts. Returns (n_claims, 384) array."""
        texts = [c.text for c in claims]
        # Ensure we return a numpy array
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return np.asarray(embeddings, dtype=np.float32)

    def embed_single(self, text: str) -> np.ndarray:
        """Embed a single text string."""
        embedding = self.model.encode(text, normalize_embeddings=True)
        return np.asarray(embedding, dtype=np.float32)
