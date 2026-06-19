import uuid
import logging
import asyncio
import aiohttp
import time
from datetime import datetime, timezone
from typing import Any, Optional, Callable, Coroutine
from pydantic import BaseModel, Field

from src.config import settings
from src.models.paper import Paper
from src.models.claim import Claim
from src.models.contradiction import ContradictionPair
from src.models.report import SynthesisReport
from src.ingestion.pubmed import ingest_papers, search_pubmed, fetch_abstracts, reformulate_query_for_pubmed
from src.llm import get_llm
from src.extraction.claim_extractor import extract_claims_batch
from src.extraction.quote_verifier import verify_and_filter_claims
from src.storage import init_db, save_papers, save_claims, save_pipeline_run, save_contradictions

# Phase 3 imports
from src.ingestion.pmc_xml import fetch_full_text, parse_pmc_xml
from src.ingestion.pdf_fallback import fetch_pdf_url_from_unpaywall, download_and_extract_pdf_text
from src.entity.normalizer import EntityNormalizer

# Phase 2 imports
from src.detection import detect_contradictions

# Phase 3 report generator
from src.synthesis.report_generator import generate_synthesis_report

logger = logging.getLogger(__name__)

class PipelineState(BaseModel):
    run_id: str
    query: str
    status: str
    started_at: Optional[str] = None
    papers: list[Paper] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    contradictions: list[ContradictionPair] = Field(default_factory=list)
    report: Optional[SynthesisReport] = None
    verification_stats: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    status_message: Optional[str] = None
    total_papers: Optional[int] = None
    papers_fetched: Optional[int] = None
    claims_extracted: Optional[int] = None
    papers_extracted: Optional[int] = None
    contradictions_found: Optional[int] = None
    nli_pairs_total: Optional[int] = None
    nli_pairs_scored: Optional[int] = None
    judge_pairs_total: Optional[int] = None
    judge_pairs_scored: Optional[int] = None
    seed_claim: Optional[str] = None
    date_from: Optional[int] = None
    date_to: Optional[int] = None
    journals: Optional[list[str]] = None


async def enrich_papers_with_full_text(
    papers: list[Paper],
    on_paper_enriched: Optional[Callable[[Paper], Coroutine[Any, Any, None]]] = None
) -> None:
    """Concurrently fetch and populate full text for open-access papers."""
    async def enrich_single(paper: Paper, session: aiohttp.ClientSession):
        try:
            xml_content = await fetch_full_text(paper.pmid, session=session)
            if xml_content:
                sections = parse_pmc_xml(xml_content)
                full_text_parts = []
                for sec_name, text in sections.items():
                    if text:
                        full_text_parts.append(f"=== {sec_name.upper()} ===\n{text}")
                if full_text_parts:
                    paper.full_text = "\n\n".join(full_text_parts)
                    logger.info(f"Successfully loaded full text for PMID {paper.pmid} from PMC.")
            else:
                if paper.doi:
                    logger.info(f"PMC XML not found for PMID {paper.pmid}. Attempting PDF fallback via DOI {paper.doi}...")
                    pdf_url = await fetch_pdf_url_from_unpaywall(paper.doi, session)
                    if pdf_url:
                        logger.info(f"Found PDF URL for DOI {paper.doi}: {pdf_url}. Downloading...")
                        pdf_text = await download_and_extract_pdf_text(pdf_url, session)
                        if pdf_text:
                            paper.full_text = pdf_text
                            logger.info(f"Successfully loaded and structured PDF full text for PMID {paper.pmid} from Unpaywall.")
            if on_paper_enriched:
                await on_paper_enriched(paper)
        except Exception as e:
            logger.warning(f"Failed to enrich PMID {paper.pmid} with PMC full text or PDF: {e}")
            if on_paper_enriched:
                await on_paper_enriched(paper)
            
    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*(enrich_single(p, session) for p in papers))

async def run_ingestion_and_extraction(
    query: str, 
    max_papers: int = settings.max_papers,
    run_id: Optional[str] = None,
    date_from: Optional[int] = None,
    date_to: Optional[int] = None,
    journals: Optional[list[str]] = None
) -> PipelineState:
    """Run the Phase 1 & Phase 3 ingestion/extraction pipeline:
    
    Ingest papers -> Enrich with PMC full-text -> Save papers -> Extract claims -> Verify quotes -> Normalize entities -> Save claims -> Log run status.
    """
    init_db()
    
    if run_id is None:
        run_id = str(uuid.uuid4())

    started_at = datetime.now(timezone.utc).isoformat()
    
    save_pipeline_run(
        run_id=run_id,
        query=query,
        status="RUNNING",
        started_at=started_at,
        date_from=date_from,
        date_to=date_to,
        journals=journals
    )
    
    try:
        # 1. Ingestion
        logger.info(f"Pipeline {run_id}: Ingesting papers for query '{query}'")
        papers = await ingest_papers(query, max_results=max_papers, date_from=date_from, date_to=date_to, journals=journals)
        logger.info(f"Pipeline {run_id}: Fetched {len(papers)} papers")
        
        if not papers:
            empty_report = SynthesisReport(
                summary="No relevant scientific publications were found on PubMed for this query. As a result, no claims or contradictions could be extracted.",
                contradictions=[],
                consensus_scores={},
                total_papers=0,
                total_claims=0,
                metadata={
                    "run_id": run_id,
                    "time_elapsed": 0.0,
                    "cost_estimate": 0.0
                }
            )
            save_pipeline_run(
                run_id=run_id,
                query=query,
                status="COMPLETED",
                papers_fetched=0,
                claims_extracted=0,
                contradictions_found=0,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                report_json=empty_report.model_dump_json()
            )
            return PipelineState(run_id=run_id, query=query, status="COMPLETED", started_at=started_at, report=empty_report)
            
        # PMC Full-Text Enrichment
        logger.info(f"Pipeline {run_id}: Enriching papers with PMC full-text XML...")
        await enrich_papers_with_full_text(papers)
        
        save_papers(papers)
        
        # 2. Claim Extraction
        llm = get_llm()
        logger.info(f"Pipeline {run_id}: Extracting claims using provider '{settings.llm_provider}' ({llm.model_name})")
        extracted_batch = await extract_claims_batch(papers, llm)
        
        # 3. Verification & Filtering
        all_verified_claims = []
        overall_stats = {
            "passed": 0,
            "flagged": 0,
            "rejected": 0,
            "rejection_rate": 0.0
        }
        
        for paper in papers:
            extracted_claims = extracted_batch.get(paper.pmid, [])
            verified_claims, stats = verify_and_filter_claims(extracted_claims, paper)
            
            all_verified_claims.extend(verified_claims)
            overall_stats["passed"] += stats["passed"]
            overall_stats["flagged"] += stats["flagged"]
            overall_stats["rejected"] += stats["rejected"]
            
        total_extracted = overall_stats["passed"] + overall_stats["flagged"] + overall_stats["rejected"]
        if total_extracted > 0:
            overall_stats["rejection_rate"] = overall_stats["rejected"] / total_extracted
            
        # 4. Entity Normalization
        if all_verified_claims:
            logger.info(f"Pipeline {run_id}: Normalizing entity mentions...")
            normalizer = EntityNormalizer()
            all_verified_claims = await normalizer.normalize_entities(all_verified_claims)
            
        # Save verified and normalized claims to database
        save_claims(all_verified_claims)
        
        completed_at = datetime.now(timezone.utc).isoformat()
        save_pipeline_run(
            run_id=run_id,
            query=query,
            status="COMPLETED",
            papers_fetched=len(papers),
            claims_extracted=len(all_verified_claims),
            contradictions_found=0,
            started_at=started_at,
            completed_at=completed_at,
            pmids=[p.pmid for p in papers]
        )

        
        logger.info(f"Pipeline {run_id}: Completed successfully. Processed {len(papers)} papers, saved {len(all_verified_claims)} claims.")
        
        return PipelineState(
            run_id=run_id,
            query=query,
            status="COMPLETED",
            started_at=started_at,
            papers=papers,
            claims=all_verified_claims,
            verification_stats=overall_stats
        )
        
    except Exception as e:
        logger.error(f"Pipeline {run_id} failed: {e}")
        completed_at = datetime.now(timezone.utc).isoformat()
        save_pipeline_run(
            run_id=run_id,
            query=query,
            status="FAILED",
            started_at=started_at,
            completed_at=completed_at,
            error_message=str(e)
        )
        raise

async def run_full_pipeline(
    query: str,
    max_papers: int = settings.max_papers,
    run_id: Optional[str] = None,
    seed_claim: Optional[str] = None,
    date_from: Optional[int] = None,
    date_to: Optional[int] = None,
    journals: Optional[list[str]] = None,
    on_stage_complete: Optional[Callable[[PipelineState], Coroutine[Any, Any, None]]] = None
) -> PipelineState:
    """Run the complete end-to-end pipeline:
    Ingestion & Extraction -> Contradiction Detection -> Synthesis Report Generation.
    """
    init_db()
    
    if run_id is None:
        run_id = str(uuid.uuid4())
 
    start_time = time.time()
    started_at = datetime.now(timezone.utc).isoformat()
    state = PipelineState(
        run_id=run_id,
        query=query,
        status="RUNNING",
        started_at=started_at,
        status_message="Initializing literature search...",
        total_papers=0,
        papers_fetched=0,
        papers_extracted=0,
        nli_pairs_total=0,
        nli_pairs_scored=0,
        judge_pairs_total=0,
        judge_pairs_scored=0,
        seed_claim=seed_claim,
        date_from=date_from,
        date_to=date_to,
        journals=journals
    )
    
    # Init run in DB
    save_pipeline_run(
        run_id=run_id,
        query=query,
        status="RUNNING",
        started_at=started_at,
        status_message=state.status_message,
        total_papers=0,
        papers_fetched=0,
        papers_extracted=0,
        nli_pairs_total=0,
        nli_pairs_scored=0,
        judge_pairs_total=0,
        judge_pairs_scored=0,
        seed_claim=seed_claim,
        date_from=date_from,
        date_to=date_to,
        journals=journals
    )
    if on_stage_complete:
        await on_stage_complete(state)
        
    try:
        # 1. Ingestion
        state.status_message = "Searching PubMed database..."
        if on_stage_complete:
            await on_stage_complete(state)
            
        pmids = await search_pubmed(query, max_papers, date_from=date_from, date_to=date_to, journals=journals)
        target_min = min(max_papers, settings.min_papers)
        if len(pmids) < target_min:
            state.status_message = f"Found only {len(pmids)} papers. Attempting query reformulation..."
            if on_stage_complete:
                await on_stage_complete(state)
            reformulated = await reformulate_query_for_pubmed(query)
            if reformulated and reformulated.lower() != query.lower():
                reformulated_pmids = await search_pubmed(reformulated, max_papers, date_from=date_from, date_to=date_to, journals=journals)
                if len(reformulated_pmids) > len(pmids):
                    pmids = reformulated_pmids
                
        if not pmids:
            state.status = "COMPLETED"
            state.status_message = "No relevant publications found."
            completed_at = datetime.now(timezone.utc).isoformat()
            
            # Create a clean empty report indicating no papers found
            empty_report = SynthesisReport(
                summary="No relevant scientific publications were found on PubMed for this query. As a result, no claims or contradictions could be extracted.",
                contradictions=[],
                consensus_scores={},
                total_papers=0,
                total_claims=0,
                metadata={
                    "run_id": run_id,
                    "time_elapsed": time.time() - start_time,
                    "cost_estimate": 0.0
                }
            )
            state.report = empty_report
            
            save_pipeline_run(
                run_id=run_id,
                query=query,
                status="COMPLETED",
                papers_fetched=0,
                claims_extracted=0,
                contradictions_found=0,
                started_at=started_at,
                completed_at=completed_at,
                report_json=empty_report.model_dump_json(),
                status_message=state.status_message,
                total_papers=0
            )
            if on_stage_complete:
                await on_stage_complete(state)
            return state

        # Set total targets immediately so progress bars render dynamically
        state.total_papers = len(pmids)
        state.status_message = f"Found {len(pmids)} articles. Downloading abstracts..."
        if on_stage_complete:
            await on_stage_complete(state)

        papers = await fetch_abstracts(pmids)
        state.papers = papers
        state.papers_fetched = len(papers)
        state.status_message = f"Fetched {len(papers)} abstracts. Fetching PMC full-text XML..."
        if on_stage_complete:
            await on_stage_complete(state)
            
        # PMC Full-Text Enrichment progress callback
        enriched_count = 0
        async def on_paper_enriched(paper: Paper):
            nonlocal enriched_count
            enriched_count += 1
            state.status_message = f"Fetched PMC full text for paper {enriched_count} of {len(papers)}..."
            if on_stage_complete:
                await on_stage_complete(state)

        await enrich_papers_with_full_text(papers, on_paper_enriched=on_paper_enriched)
        save_papers(papers)
        
        # 2. Claim Extraction
        llm = get_llm()
        state.papers_extracted = 0
        state.claims_extracted = 0
        state.status_message = f"Extracting claims from {len(papers)} papers (0% complete)..."
        if on_stage_complete:
            await on_stage_complete(state)

        async def on_paper_extracted(paper: Paper, extracted_claims: list):
            state.papers_extracted += 1
            state.claims_extracted += len(extracted_claims)
            # Accumulate claims in state so UI tracks progress
            state.claims.extend(extracted_claims)
            pct = int((state.papers_extracted / len(papers)) * 100)
            state.status_message = f"Extracted claims from paper {state.papers_extracted} of {len(papers)} ({pct}% complete)..."
            if on_stage_complete:
                await on_stage_complete(state)

        extracted_batch = await extract_claims_batch(papers, llm, on_paper_complete=on_paper_extracted)
        
        # 3. Verification & Filtering
        state.status_message = "Verifying and filtering claims..."
        if on_stage_complete:
            await on_stage_complete(state)

        all_verified_claims = []
        overall_stats = {
            "passed": 0,
            "flagged": 0,
            "rejected": 0,
            "rejection_rate": 0.0
        }
        
        for paper in papers:
            extracted_claims = extracted_batch.get(paper.pmid, [])
            verified_claims, stats = verify_and_filter_claims(extracted_claims, paper)
            
            all_verified_claims.extend(verified_claims)
            overall_stats["passed"] += stats["passed"]
            overall_stats["flagged"] += stats["flagged"]
            overall_stats["rejected"] += stats["rejected"]
            
        total_extracted = overall_stats["passed"] + overall_stats["flagged"] + overall_stats["rejected"]
        if total_extracted > 0:
            overall_stats["rejection_rate"] = overall_stats["rejected"] / total_extracted
            
        state.verification_stats = overall_stats
        
        # 4. Entity Normalization
        if all_verified_claims:
            state.status_message = "Normalizing entity mentions..."
            if on_stage_complete:
                await on_stage_complete(state)
            normalizer = EntityNormalizer()
            all_verified_claims = await normalizer.normalize_entities(all_verified_claims)
            
        state.claims = all_verified_claims
        state.claims_extracted = len(all_verified_claims)
        save_claims(all_verified_claims)
        
        # Update run in DB with intermediate counts
        save_pipeline_run(
            run_id=run_id,
            query=query,
            status="RUNNING",
            papers_fetched=len(papers),
            claims_extracted=len(all_verified_claims),
            started_at=started_at,
            pmids=[p.pmid for p in papers]
        )
        if on_stage_complete:
            await on_stage_complete(state)

        # 5. Contradiction Detection
        if all_verified_claims:
            state.status_message = "Detecting contradiction candidate pairs..."
            if on_stage_complete:
                await on_stage_complete(state)

            def on_nli_start(total_pairs: int):
                state.nli_pairs_total = total_pairs
                state.nli_pairs_scored = 0

            def on_nli_batch(current_batch: int, total_batches: int):
                state.nli_pairs_scored = min(current_batch * 32, state.nli_pairs_total or 0)
                state.status_message = f"Scoring candidate pairs via NLI (batch {current_batch} of {total_batches})..."
                try:
                    loop = asyncio.get_running_loop()
                    if on_stage_complete:
                        asyncio.run_coroutine_threadsafe(on_stage_complete(state), loop)
                except Exception:
                    pass

            def on_judge_start(total_candidates: int):
                state.judge_pairs_total = total_candidates
                state.judge_pairs_scored = 0

            async def on_judge_pair(result: ContradictionPair | None):
                state.judge_pairs_scored += 1
                if result is not None:
                    state.contradictions.append(result)
                    state.contradictions_found = len(state.contradictions)
                state.status_message = f"Judging contradictions via LLM (pair {state.judge_pairs_scored} of {state.judge_pairs_total})..."
                if on_stage_complete:
                    await on_stage_complete(state)

            contradictions = await detect_contradictions(
                claims=all_verified_claims,
                llm=None,
                on_nli_start=on_nli_start,
                on_nli_batch=on_nli_batch,
                on_judge_start=on_judge_start,
                on_judge_pair=on_judge_pair,
                seed_claim=seed_claim
            )
            save_contradictions(contradictions)
            state.contradictions = contradictions
        else:
            contradictions = []
            
        # Update run in DB with contradiction count
        save_pipeline_run(
            run_id=run_id,
            query=query,
            status="RUNNING",
            papers_fetched=len(papers),
            claims_extracted=len(all_verified_claims),
            contradictions_found=len(contradictions),
            started_at=started_at,
            pmids=[p.pmid for p in papers]
        )
        if on_stage_complete:
            await on_stage_complete(state)
            
        # 6. Report Generation
        state.status_message = "Generating final narrative report..."
        if on_stage_complete:
            await on_stage_complete(state)

        report_llm = get_llm(settings.judge_model)
        
        time_elapsed = time.time() - start_time
        cost_estimate = (
            (len(papers) * settings.cost_per_paper)
            + (len(contradictions) * settings.cost_per_contradiction)
            + settings.cost_synthesis
        )
        
        report = await generate_synthesis_report(
            contradictions=contradictions,
            claims=all_verified_claims,
            papers=papers,
            llm=report_llm
        )
        report.metadata = {
            "run_id": run_id,
            "time_elapsed": time_elapsed,
            "cost_estimate": cost_estimate
        }
        state.report = report
        
        completed_at = datetime.now(timezone.utc).isoformat()
        state.status = "COMPLETED"
        state.status_message = "Synthesis completed successfully."
        
        save_pipeline_run(
            run_id=run_id,
            query=query,
            status="COMPLETED",
            papers_fetched=len(papers),
            claims_extracted=len(all_verified_claims),
            contradictions_found=len(contradictions),
            started_at=started_at,
            completed_at=completed_at,
            pmids=[p.pmid for p in papers],
            report_json=report.model_dump_json(),
            status_message=state.status_message
        )
        if on_stage_complete:
            await on_stage_complete(state)
            
        logger.info(f"Pipeline {run_id}: Full pipeline completed successfully.")
        return state
        
    except Exception as e:
        logger.error(f"Pipeline {run_id} failed: {e}")
        state.status = "FAILED"
        state.error_message = str(e)
        state.status_message = f"Failed: {str(e)}"
        completed_at = datetime.now(timezone.utc).isoformat()
        save_pipeline_run(
            run_id=run_id,
            query=query,
            status="FAILED",
            started_at=started_at,
            completed_at=completed_at,
            error_message=str(e),
            status_message=state.status_message
        )
        if on_stage_complete:
            await on_stage_complete(state)
        raise

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    
    query = sys.argv[1] if len(sys.argv) > 1 else "metformin cancer"
    print(f"Running pipeline for: '{query}'")
    
    if not settings.gemini_api_key and not settings.openai_api_key:
        print("Error: No LLM API keys configured. Set GEMINI_API_KEY or OPENAI_API_KEY in your .env file.")
        sys.exit(1)
        
    asyncio.run(run_ingestion_and_extraction(query, max_papers=5))
