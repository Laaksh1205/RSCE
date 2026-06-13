import numpy as np
from pydantic import BaseModel
from sentence_transformers import CrossEncoder
from src.models.claim import Claim

class NLIResult(BaseModel):
    entailment: float
    neutral: float
    contradiction: float

_MODEL_CACHE = {}

class NLIScorer:
    def __init__(self, model_name: str = "cross-encoder/nli-deberta-v3-large"):
        if model_name not in _MODEL_CACHE:
            _MODEL_CACHE[model_name] = CrossEncoder(model_name)
        self.model = _MODEL_CACHE[model_name]

    def score_pairs(
        self,
        pairs: list[tuple[str, str]],
    ) -> list[NLIResult]:
        """Score claim pairs for entailment/neutral/contradiction.
        Returns list of NLIResult(entailment, neutral, contradiction scores).
        """
        if not pairs:
            return []

        # Predict returns probability scores (softmax output) by default for classifier models
        scores = self.model.predict(pairs)
        
        # Ensure scores is a 2D array even if a single pair was predicted
        if len(pairs) == 1 and len(scores.shape) == 1:
            scores = np.expand_dims(scores, axis=0)

        results = []
        for score in scores:
            # Map index to correct labels based on model configuration:
            # Index 0: contradiction, Index 1: entailment, Index 2: neutral
            results.append(NLIResult(
                contradiction=float(score[0]),
                entailment=float(score[1]),
                neutral=float(score[2])
            ))
        return results

    def filter_contradictions(
        self,
        pairs: list[tuple[int, int, float]],  # from FAISS: (idx_a, idx_b, similarity_score)
        claims: list[Claim],
        threshold: float = 0.7,
    ) -> list[tuple[int, int, float, float]]:
        """Run NLI on candidate pairs, return those with contradiction score >= threshold.
        Returns: list of (idx_a, idx_b, similarity_score, contradiction_score)
        """
        if not pairs:
            return []

        # Extract text pairs for NLI cross-encoder
        text_pairs = [(claims[idx_a].text, claims[idx_b].text) for idx_a, idx_b, _ in pairs]
        
        # Run inference
        nli_results = self.score_pairs(text_pairs)

        filtered = []
        for (idx_a, idx_b, similarity_score), nli_res in zip(pairs, nli_results):
            if nli_res.contradiction >= threshold:
                filtered.append((idx_a, idx_b, similarity_score, nli_res.contradiction))

        return filtered
