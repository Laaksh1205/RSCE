import numpy as np
from typing import Optional, Callable
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
        on_batch_complete: Optional[Callable[[int, int], None]] = None
    ) -> list[NLIResult]:
        """Score claim pairs for entailment/neutral/contradiction.
        Returns list of NLIResult(entailment, neutral, contradiction scores).
        """
        if not pairs:
            return []

        batch_size = 32
        scores_list = []
        total_pairs = len(pairs)
        total_batches = (total_pairs + batch_size - 1) // batch_size
        
        for batch_idx in range(total_batches):
            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, total_pairs)
            batch_pairs = pairs[start_idx:end_idx]
            
            # Predict for batch
            batch_scores = self.model.predict(batch_pairs)
            
            # Ensure shape is 2D
            if len(batch_pairs) == 1 and len(batch_scores.shape) == 1:
                batch_scores = np.expand_dims(batch_scores, axis=0)
                
            scores_list.append(batch_scores)
            
            if on_batch_complete:
                on_batch_complete(batch_idx + 1, total_batches)
                
        scores = np.vstack(scores_list)

        # Convert raw logits to probabilities via Softmax
        exp_scores = np.exp(scores - np.max(scores, axis=-1, keepdims=True))
        scores = exp_scores / np.sum(exp_scores, axis=-1, keepdims=True)

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
        on_batch_complete: Optional[Callable[[int, int], None]] = None
    ) -> list[tuple[int, int, float, float]]:
        """Run NLI on candidate pairs, return those with contradiction score >= threshold.
        Returns: list of (idx_a, idx_b, similarity_score, contradiction_score)
        """
        if not pairs:
            return []

        # Extract text pairs for NLI cross-encoder
        text_pairs = [(claims[idx_a].text, claims[idx_b].text) for idx_a, idx_b, _ in pairs]
        
        # Run inference
        nli_results = self.score_pairs(text_pairs, on_batch_complete=on_batch_complete)

        filtered = []
        for (idx_a, idx_b, similarity_score), nli_res in zip(pairs, nli_results):
            if nli_res.contradiction >= threshold:
                filtered.append((idx_a, idx_b, similarity_score, nli_res.contradiction))

        return filtered
