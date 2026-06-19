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

from typing import Callable, Coroutine, Any

logger = logging.getLogger(__name__)

async def detect_contradictions(
    claims: list[Claim],
    llm: Optional[LLMProvider] = None,
    on_nli_start: Optional[Callable[[int], None]] = None,
    on_nli_batch: Optional[Callable[[int, int], None]] = None,
    on_judge_start: Optional[Callable[[int], None]] = None,
    on_judge_pair: Optional[Callable[[ContradictionPair | None], Coroutine[Any, Any, None]]] = None,
    seed_claim: Optional[str] = None
) -> list[ContradictionPair]:
    """Full detection pipeline:
    1. Embed all claims (local, batch)
    2. Build FAISS index, retrieve top-K pairs (exclude same-paper)
    3. Score pairs with NLI model (local, batch)
    4. Filter by contradiction threshold
    5. Send ambiguous pairs to LLM judge (async, concurrent)
    6. Rank by contradiction_score, return top N
    """
    import os
    import numpy as np

    if not claims or len(claims) <= 1:
        if seed_claim and claims:
            # If we only have 1 paper claim but a seed claim exists, we can still run!
            pass
        else:
            logger.info("Not enough claims to perform contradiction detection.")
            return []

    logger.info("Step 1: Preparing embeddings for paper claims...")
    claims_to_embed = [c for c in claims if c.embedding is None]
    if claims_to_embed:
        logger.info(f"Embedding {len(claims_to_embed)} paper claims (cached: {len(claims) - len(claims_to_embed)})...")
        embedder = ClaimEmbedder()
        embeddings_new = embedder.embed_claims(claims_to_embed)
        # Assign embeddings back to claims
        for claim, emb in zip(claims_to_embed, embeddings_new):
            claim.embedding = emb.tolist()
        
        # Save newly embedded claims to update SQLite cache
        try:
            from src.storage import save_claims
            save_claims(claims_to_embed)
        except Exception as e:
            logger.warning(f"Could not cache claim embeddings in SQLite database: {e}")
    else:
        logger.info(f"All {len(claims)} paper claims loaded from cache (no new embeddings computed).")

    # Handle query-time optional seed claim (never save to SQLite or write to cached FAISS index on disk)
    seed_claim_obj = None
    if seed_claim:
        import uuid
        from datetime import datetime
        from src.models.claim import ClaimType, Polarity, StudyDesign
        
        logger.info(f"Creating seed claim object for assertion: '{seed_claim}'")
        seed_claim_obj = Claim(
            id=uuid.uuid4(),
            paper_id="seed_claim_paper",
            text=seed_claim,
            normalized_text=seed_claim,
            section="User Seed",
            authors=["User Seed Claim"],
            year=datetime.now().year,
            confidence_score=1.0,
            claim_type=ClaimType.CAUSAL,
            polarity=Polarity.POSITIVE,
            entities=[],
            population="General",
            context="",
            quote_anchor="",
            study_design=StudyDesign.RCT
        )
        
        # Embed the seed claim separately using ClaimEmbedder
        embedder = ClaimEmbedder()
        seed_emb = embedder.embed_claims([seed_claim_obj])
        seed_claim_obj.embedding = seed_emb[0].tolist()

    # Construct the embeddings array for paper claims only
    embeddings = np.array([c.embedding for c in claims], dtype=np.float32)

    logger.info("Step 2: Building/Loading FAISS index for paper claims...")
    index = ClaimIndex()
    index_path = settings.faiss_index_path
    
    loaded_index = False
    if os.path.exists(index_path):
        try:
            index.load(index_path)
            if index.index is not None and index.index.ntotal == len(claims):
                loaded_index = True
                logger.info(f"Successfully loaded matching FAISS index from {index_path} (size: {index.index.ntotal})")
            else:
                logger.info(f"Index size mismatch or empty index at {index_path} (expected {len(claims)}, got {index.index.ntotal if index.index else 'None'}). Rebuilding...")
        except Exception as e:
            logger.warning(f"Could not load FAISS index from {index_path}: {e}")
            
    if not loaded_index:
        index.build_index(embeddings)
        try:
            index.save(index_path)
            logger.info(f"Saved built FAISS index to {index_path}")
        except Exception as e:
            logger.warning(f"Could not save FAISS index to {index_path}: {e}")

    # 1. Query standard paper-paper candidate pairs
    candidate_pairs = index.find_candidate_pairs(
        embeddings=embeddings,
        claims=claims,
        top_k=settings.faiss_top_k,
        min_similarity=0.3
    )

    # 2. Query and inject seed-paper candidate pairs if seed_claim is provided
    if seed_claim_obj:
        logger.info("Querying FAISS index with seed claim embedding to bias search...")
        seed_emb_arr = np.asarray([seed_claim_obj.embedding], dtype=np.float32)
        k_seed = min(len(claims), 20)
        distances, indices = index.index.search(seed_emb_arr, k_seed)
        
        # Append seed claim object to the end of the claims list (index becomes seed_index)
        seed_index = len(claims)
        claims.append(seed_claim_obj)
        
        existing_pairs = {(a, b) for a, b, _ in candidate_pairs}
        for col in range(k_seed):
            j = int(indices[0, col])
            score = float(distances[0, col])
            if j == -1:
                continue
            # A lower similarity threshold (0.2) is allowed for seed claim comparisons to be permissive
            if score < 0.2:
                continue
            
            idx_a, idx_b = min(seed_index, j), max(seed_index, j)
            if (idx_a, idx_b) not in existing_pairs:
                candidate_pairs.append((idx_a, idx_b, score))
                existing_pairs.add((idx_a, idx_b))
    
    if not candidate_pairs:
        logger.info("No candidate pairs passed the similarity threshold.")
        return []

    if on_nli_start:
        on_nli_start(len(candidate_pairs))

    logger.info(f"Step 3: Scoring {len(candidate_pairs)} candidate pairs using local NLI model ({settings.nli_model})...")
    scorer = NLIScorer(model_name=settings.nli_model)
    import asyncio
    nli_filtered = await asyncio.to_thread(
        scorer.filter_contradictions,
        pairs=candidate_pairs,
        claims=claims,
        threshold=settings.nli_contradiction_threshold,
        on_batch_complete=on_nli_batch
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

    if on_judge_start:
        on_judge_start(len(judge_candidates))

    contradictions = await judge_batch(judge_candidates, llm, on_pair_complete=on_judge_pair)

    # Step 5: Rank by contradiction_score descending and return top N, prioritizing seed claims
    if seed_claim:
        # Sort such that any contradiction involving the seed claim is at the top
        contradictions.sort(
            key=lambda x: (
                1 if (x.claim_a.paper_id == "seed_claim_paper" or x.claim_b.paper_id == "seed_claim_paper") else 0,
                x.contradiction_score
            ),
            reverse=True
        )
    else:
        contradictions.sort(key=lambda x: x.contradiction_score, reverse=True)
    
    top_n = contradictions[:settings.max_contradictions_displayed]
    logger.info(f"Detected {len(top_n)} contradictions (capped at {settings.max_contradictions_displayed}).")
    
    return top_n
