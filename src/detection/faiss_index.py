import os
import faiss
import numpy as np
from src.models.claim import Claim

class ClaimIndex:
    def __init__(self):
        self.index = None

    def build_index(self, embeddings: np.ndarray) -> None:
        """Build FAISS IndexFlatIP (inner product on normalized vectors = cosine)."""
        if len(embeddings) == 0:
            raise ValueError("Cannot build index with empty embeddings array.")
        
        d = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(d)
        # Ensure embeddings are float32 as required by FAISS
        embeddings_f32 = np.asarray(embeddings, dtype=np.float32)
        self.index.add(embeddings_f32)

    def find_candidate_pairs(
        self,
        embeddings: np.ndarray,
        claims: list[Claim],
        top_k: int = 10,
        min_similarity: float = 0.3,
    ) -> list[tuple[int, int, float]]:
        """For each claim, find top-K most similar claims (excluding self and same-paper).
        Returns: list of (idx_a, idx_b, similarity_score) tuples, deduplicated.
        """
        if self.index is None:
            raise ValueError("Index has not been built. Call build_index first.")
        
        n_claims = len(claims)
        if n_claims <= 1:
            return []

        # We query for more neighbors than top_k because we'll filter out self and same-paper matches
        k_query = min(n_claims, top_k + 20)
        embeddings_f32 = np.asarray(embeddings, dtype=np.float32)
        distances, indices = self.index.search(embeddings_f32, k_query)

        candidate_pairs = {}
        for i in range(n_claims):
            for col in range(k_query):
                j = int(indices[i, col])
                score = float(distances[i, col])
                
                # FAISS returns -1 if there are not enough items
                if j == -1:
                    continue
                # Skip self match
                if j == i:
                    continue
                # Skip same-paper matches
                if claims[i].paper_id == claims[j].paper_id:
                    continue
                # Filter by similarity threshold
                if score < min_similarity:
                    continue
                
                # Deduplicate by ordering indices
                idx_a, idx_b = min(i, j), max(i, j)
                candidate_pairs[(idx_a, idx_b)] = score

        # Return sorted by score descending
        sorted_pairs = [(idx_a, idx_b, score) for (idx_a, idx_b), score in candidate_pairs.items()]
        sorted_pairs.sort(key=lambda x: x[2], reverse=True)
        return sorted_pairs

    def save(self, path: str) -> None:
        """Save the index to a file."""
        if self.index is None:
            raise ValueError("No index to save.")
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        faiss.write_index(self.index, path)

    def load(self, path: str) -> None:
        """Load the index from a file."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"No FAISS index file found at: {path}")
        self.index = faiss.read_index(path)
