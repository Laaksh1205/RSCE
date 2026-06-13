import logging
from typing import Optional

from src.config import settings
from src.llm import get_llm, LLMProvider
from src.models.claim import Claim
from src.models.contradiction import ContradictionPair
from src.detection.embedder import ClaimEmbedder
from src.detection.faiss_index import ClaimIndex
from src.detection.nli_scorer import NLIScorer
from src.detection.llm_judge import judge_batch

logger = logging.getLogger(__name__)

async def detect_contradictions(
    claims: list[Claim],
    llm: Optional[LLMProvider] = None,
) -> list[ContradictionPair]:
    """Full detection pipeline:
    1. Embed all claims (local, batch)
    2. Build FAISS index, retrieve top-K pairs (exclude same-paper)
    3. Score pairs with NLI model (local, batch)
    4. Filter by contradiction threshold
    5. Send ambiguous pairs to LLM judge (async, concurrent)
    6. Rank by contradiction_score, return top N
    """
    if not claims or len(claims) <= 1:
        logger.info("Not enough claims to perform contradiction detection.")
        return []

    logger.info(f"Step 1: Embedding {len(claims)} claims...")
    embedder = ClaimEmbedder()
    embeddings = embedder.embed_claims(claims)

    logger.info("Step 2: Building FAISS index and querying candidate pairs...")
    index = ClaimIndex()
    index.build_index(embeddings)
    candidate_pairs = index.find_candidate_pairs(
        embeddings=embeddings,
        claims=claims,
        top_k=settings.faiss_top_k,
        min_similarity=0.3
    )
    
    if not candidate_pairs:
        logger.info("No candidate pairs passed the similarity threshold.")
        return []

    logger.info(f"Step 3: Scoring {len(candidate_pairs)} candidate pairs using local NLI model...")
    scorer = NLIScorer()
    nli_filtered = scorer.filter_contradictions(
        pairs=candidate_pairs,
        claims=claims,
        threshold=settings.nli_contradiction_threshold
    )

    if not nli_filtered:
        logger.info("No pairs passed the NLI contradiction threshold.")
        return []

    logger.info(f"Step 4: Judging {len(nli_filtered)} candidate contradictions using LLM...")
    if llm is None:
        llm = get_llm(settings.judge_model)

    # Convert NLI filtered pairs into the format expected by judge_batch
    # nli_filtered items: (idx_a, idx_b, similarity_score, contradiction_score)
    judge_candidates = [
        (claims[idx_a], claims[idx_b], float(contradiction_score))
        for idx_a, idx_b, _, contradiction_score in nli_filtered
    ]

    contradictions = await judge_batch(judge_candidates, llm)

    # Step 5: Rank by contradiction_score descending and return top N
    contradictions.sort(key=lambda x: x.contradiction_score, reverse=True)
    
    top_n = contradictions[:settings.max_contradictions_displayed]
    logger.info(f"Detected {len(top_n)} contradictions (capped at {settings.max_contradictions_displayed}).")
    
    return top_n
