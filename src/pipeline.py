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
from src.ingestion.pubmed import ingest_papers
from src.llm import get_llm
from src.extraction.claim_extractor import extract_claims_batch
from src.extraction.quote_verifier import verify_and_filter_claims
from src.storage import init_db, save_papers, save_claims, save_pipeline_run, save_contradictions

# Phase 3 imports
from src.ingestion.pmc_xml import fetch_full_text, parse_pmc_xml
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

async def enrich_papers_with_full_text(papers: list[Paper]) -> None:
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
        except Exception as e:
            logger.warning(f"Failed to enrich PMID {paper.pmid} with PMC full text: {e}")
            
    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*(enrich_single(p, session) for p in papers))

async def run_ingestion_and_extraction(
    query: str, 
    max_papers: int = settings.max_papers,
    run_id: Optional[str] = None
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
        started_at=started_at
    )
    
    try:
        # 1. Ingestion
        logger.info(f"Pipeline {run_id}: Ingesting papers for query '{query}'")
        papers = await ingest_papers(query, max_results=max_papers)
        logger.info(f"Pipeline {run_id}: Fetched {len(papers)} papers")
        
        if not papers:
            save_pipeline_run(
                run_id=run_id,
                query=query,
                status="COMPLETED",
                papers_fetched=0,
                claims_extracted=0,
                contradictions_found=0,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat()
            )
            return PipelineState(run_id=run_id, query=query, status="COMPLETED", started_at=started_at)
            
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
        started_at=started_at
    )
    
    # Init run in DB
    save_pipeline_run(
        run_id=run_id,
        query=query,
        status="RUNNING",
        started_at=started_at
    )
    if on_stage_complete:
        await on_stage_complete(state)
        
    try:
        # 1. Ingestion
        logger.info(f"Pipeline {run_id}: Ingesting papers for query '{query}'")
        papers = await ingest_papers(query, max_results=max_papers)
        logger.info(f"Pipeline {run_id}: Fetched {len(papers)} papers")
        state.papers = papers
        
        if not papers:
            state.status = "COMPLETED"
            completed_at = datetime.now(timezone.utc).isoformat()
            save_pipeline_run(
                run_id=run_id,
                query=query,
                status="COMPLETED",
                papers_fetched=0,
                claims_extracted=0,
                contradictions_found=0,
                started_at=started_at,
                completed_at=completed_at
            )
            if on_stage_complete:
                await on_stage_complete(state)
            return state
            
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
            
        state.verification_stats = overall_stats
        
        # 4. Entity Normalization
        if all_verified_claims:
            logger.info(f"Pipeline {run_id}: Normalizing entity mentions...")
            normalizer = EntityNormalizer()
            all_verified_claims = await normalizer.normalize_entities(all_verified_claims)
            
        state.claims = all_verified_claims
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
            logger.info(f"Pipeline {run_id}: Detecting contradictions...")
            contradictions = await detect_contradictions(all_verified_claims)
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
        logger.info(f"Pipeline {run_id}: Generating synthesis report...")
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
            report_json=report.model_dump_json()
        )
        if on_stage_complete:
            await on_stage_complete(state)
            
        logger.info(f"Pipeline {run_id}: Full pipeline completed successfully.")
        return state
        
    except Exception as e:
        logger.error(f"Pipeline {run_id} failed: {e}")
        state.status = "FAILED"
        state.error_message = str(e)
        completed_at = datetime.now(timezone.utc).isoformat()
        save_pipeline_run(
            run_id=run_id,
            query=query,
            status="FAILED",
            started_at=started_at,
            completed_at=completed_at,
            error_message=str(e)
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
