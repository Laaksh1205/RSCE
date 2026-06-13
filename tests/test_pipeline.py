import pytest
import uuid
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock, patch
from src.models.paper import Paper
from src.models.claim import ExtractedClaim, ClaimType, Polarity, StudyDesign, Entity, EntityType, ClaimExtractionResponse
from src.pipeline import run_ingestion_and_extraction, run_full_pipeline, PipelineState
from src.storage.database import get_paper, get_claim, get_connection, get_contradictions_for_run

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)

@pytest.fixture
def temp_faiss():
    fd, path = tempfile.mkstemp(suffix=".faiss")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)

@pytest.mark.asyncio
async def test_pipeline_end_to_end_mocked(temp_db):
    # Mock settings.db_path to use the temporary database
    with patch("src.storage.database.settings.db_path", temp_db):
        
        # 1. Mock papers list
        mock_paper = Paper(
            pmid="11111",
            title="Metformin Trial",
            authors=["Dr. Adams"],
            year=2024,
            journal="New England Journal of Medicine",
            abstract_text="Metformin inhibits tumor progression in human adults."
        )
        
        # 2. Mock extracted claim
        mock_extracted = ExtractedClaim(
            text="Metformin inhibits tumor progression.",
            polarity=Polarity.NEGATIVE,
            population="human adults",
            context="clinical trial",
            quote_anchor="Metformin inhibits tumor progression",
            claim_type=ClaimType.CAUSAL,
            study_design=StudyDesign.RCT,
            entities=[Entity(text="metformin", entity_type=EntityType.DRUG)]
        )
        
        # 3. Patch external dependencies
        with patch("src.pipeline.ingest_papers", new_callable=AsyncMock) as mock_ingest:
            mock_ingest.return_value = [mock_paper]
            
            mock_llm = MagicMock()
            mock_llm.model_name = "mock-llm-model"
            mock_llm.generate_structured = AsyncMock(
                return_value=ClaimExtractionResponse(claims=[mock_extracted])
            )
            
            with patch("src.pipeline.get_llm", return_value=mock_llm):
                
                # Execute pipeline (cap papers at 1)
                state = await run_ingestion_and_extraction("metformin tumor", max_papers=1)
                
                # Assertions on returned state
                assert isinstance(state, PipelineState)
                assert state.status == "COMPLETED"
                assert len(state.papers) == 1
                assert len(state.claims) == 1
                assert state.claims[0].text == "Metformin inhibits tumor progression."
                assert state.verification_stats["passed"] == 1
                assert state.verification_stats["rejected"] == 0
                
                # Verify DB writes
                paper_db = get_paper("11111", db_path=temp_db)
                assert paper_db is not None
                assert paper_db.title == "Metformin Trial"
                
                claim_db = get_claim(str(state.claims[0].id), db_path=temp_db)
                assert claim_db is not None
                assert claim_db.text == "Metformin inhibits tumor progression."
                
                # Verify pipeline run was logged in SQLite
                conn = get_connection(temp_db)
                row = conn.execute("SELECT * FROM pipeline_runs WHERE id = ?", (state.run_id,)).fetchone()
                assert row is not None
                assert row["query"] == "metformin tumor"
                assert row["status"] == "COMPLETED"
                assert row["papers_fetched"] == 1
                assert row["claims_extracted"] == 1
                conn.close()

@pytest.mark.asyncio
async def test_run_full_pipeline_end_to_end(temp_db):
    # Mock settings.db_path to use the temporary database
    with patch("src.storage.database.settings.db_path", temp_db), \
         patch("src.pipeline.settings.db_path", temp_db):
        
        # 1. Mock papers list
        mock_paper = Paper(
            pmid="11111",
            title="Metformin Trial",
            authors=["Dr. Adams"],
            year=2024,
            journal="New England Journal of Medicine",
            abstract_text="Metformin inhibits tumor progression in human adults."
        )
        
        # 2. Mock extracted claim
        mock_extracted = ExtractedClaim(
            text="Metformin inhibits tumor progression.",
            polarity=Polarity.NEGATIVE,
            population="human adults",
            context="clinical trial",
            quote_anchor="Metformin inhibits tumor progression",
            claim_type=ClaimType.CAUSAL,
            study_design=StudyDesign.RCT,
            entities=[Entity(text="metformin", entity_type=EntityType.DRUG)]
        )
        
        # 3. Patch external dependencies
        with patch("src.pipeline.ingest_papers", new_callable=AsyncMock) as mock_ingest:
            mock_ingest.return_value = [mock_paper]
            
            from src.models.claim import Claim
            from src.models.contradiction import ContradictionType, ContradictionPair
            
            async def mock_detect_side_effect(claims, llm=None):
                c = claims[0]
                return [
                    ContradictionPair(
                        claim_a=c,
                        claim_b=c,
                        contradiction_score=0.95,
                        contradiction_type=ContradictionType.DIRECT_NEGATION,
                        explanation="Opposite effects.",
                        scope_note="",
                        is_genuine=True
                    )
                ]
            
            with patch("src.pipeline.detect_contradictions", side_effect=mock_detect_side_effect) as mock_detect:
                
                # Mock LLM for claim extraction (Phase 1) and report generation (Phase 3)
                mock_llm = MagicMock()
                mock_llm.model_name = "mock-llm-model"
                mock_llm.generate_structured = AsyncMock(
                    return_value=ClaimExtractionResponse(claims=[mock_extracted])
                )
                mock_llm.generate_text = AsyncMock(
                    return_value="Metformin inhibits tumor progression [Adams, 2024]."
                )
                
                with patch("src.pipeline.get_llm", return_value=mock_llm):
                    
                    # Track stage callbacks
                    callback_states = []
                    async def on_stage_complete(s):
                        callback_states.append(s.status)
                    
                    # Execute full pipeline
                    state = await run_full_pipeline(
                        "metformin tumor",
                        max_papers=1,
                        on_stage_complete=on_stage_complete
                    )
                    
                    # Assertions on returned state
                    assert isinstance(state, PipelineState)
                    assert state.status == "COMPLETED"
                    assert len(state.papers) == 1
                    assert len(state.claims) == 1
                    assert len(state.contradictions) == 1
                    assert state.report is not None
                    assert state.report.summary == "Metformin inhibits tumor progression [Adams, 2024]."
                    
                    # Check callback triggered
                    assert "RUNNING" in callback_states
                    assert "COMPLETED" in callback_states
                    
                    # Verify DB writes
                    paper_db = get_paper("11111", db_path=temp_db)
                    assert paper_db is not None
                    
                    claim_db = get_claim(str(state.claims[0].id), db_path=temp_db)
                    assert claim_db is not None
                    
                    contradictions_db = get_contradictions_for_run(["11111"], db_path=temp_db)
                    assert len(contradictions_db) == 1
                    
                    # Verify pipeline run was logged in SQLite
                    conn = get_connection(temp_db)
                    row = conn.execute("SELECT * FROM pipeline_runs WHERE id = ?", (state.run_id,)).fetchone()
                    assert row is not None
                    assert row["query"] == "metformin tumor"
                    assert row["status"] == "COMPLETED"
                    assert row["papers_fetched"] == 1
                    assert row["claims_extracted"] == 1
                    assert row["contradictions_found"] == 1
                    assert row["report_json"] is not None
                    conn.close()

@pytest.mark.asyncio
async def test_full_pipeline_integration_no_mock_detection(temp_db, temp_faiss):
    # Mock settings.db_path and settings.faiss_index_path
    from src.config import settings
    with patch.object(settings, "db_path", temp_db), \
         patch.object(settings, "faiss_index_path", temp_faiss):
        
        # 1. Mock papers list (two papers with contradictory abstracts)
        mock_papers = [
            Paper(
                pmid="11111",
                title="Study 1 on Metformin",
                authors=["John Adams", "Co-Author One"],
                year=2020,
                journal="Journal of Diabetes",
                abstract_text="A clinical trial showed that Metformin reduces cancer risk in humans."
            ),
            Paper(
                pmid="22222",
                title="Study 2 on Metformin",
                authors=["Alice Baker"],
                year=2023,
                journal="Cancer Letters",
                abstract_text="Another trial showed that Metformin increases cancer risk in humans."
            )
        ]
        
        # 2. Mock claims to return for each paper during extraction phase
        claim_1 = ExtractedClaim(
            text="Metformin reduces cancer risk in humans.",
            polarity=Polarity.NEGATIVE,
            population="humans",
            context="clinical trial",
            quote_anchor="Metformin reduces cancer risk in humans",
            claim_type=ClaimType.CAUSAL,
            study_design=StudyDesign.RCT,
            entities=[Entity(text="Metformin", entity_type=EntityType.DRUG)]
        )
        
        claim_2 = ExtractedClaim(
            text="Metformin increases cancer risk in humans.",
            polarity=Polarity.POSITIVE,
            population="humans",
            context="clinical trial",
            quote_anchor="Metformin increases cancer risk in humans",
            claim_type=ClaimType.CAUSAL,
            study_design=StudyDesign.RCT,
            entities=[Entity(text="Metformin", entity_type=EntityType.DRUG)]
        )
        
        # 3. Patch ingest_papers and enrich_papers_with_full_text to avoid network calls
        with patch("src.pipeline.ingest_papers", new_callable=AsyncMock) as mock_ingest, \
             patch("src.pipeline.enrich_papers_with_full_text", new_callable=AsyncMock) as mock_enrich:
             
            mock_ingest.return_value = mock_papers
            
            # 4. Construct a mock LLM that generates extracted claims, judge responses, and report summary
            from src.detection.llm_judge import JudgeResponse
            from src.models.contradiction import ContradictionType
            
            mock_llm = MagicMock()
            mock_llm.model_name = "mock-pipeline-llm"
            
            async def generate_structured_side_effect(prompt, response_schema, temperature=0.1):
                if response_schema == ClaimExtractionResponse:
                    if "Study 1 on Metformin" in prompt or "reduces cancer risk" in prompt:
                        return ClaimExtractionResponse(claims=[claim_1])
                    else:
                        return ClaimExtractionResponse(claims=[claim_2])
                elif response_schema == JudgeResponse:
                    return JudgeResponse(
                        is_same_topic=True,
                        is_contradiction=True,
                        is_genuine=True,
                        contradiction_type=ContradictionType.DIRECTION_REVERSAL,
                        explanation="Opposing findings on cancer risk.",
                        scope_note=""
                    )
                else:
                    raise ValueError(f"Unexpected response_schema in test: {response_schema}")
                    
            mock_llm.generate_structured = AsyncMock(side_effect=generate_structured_side_effect)
            mock_llm.generate_text = AsyncMock(
                return_value="Metformin reduces cancer risk in humans [Adams et al., 2020], but Baker contradicts this [Baker, 2023]."
            )
            
            # Patch get_llm to return our mock LLM
            with patch("src.pipeline.get_llm", return_value=mock_llm), \
                 patch("src.detection.contradiction_detector.get_llm", return_value=mock_llm):
                 
                # Execute full pipeline end-to-end (which calls actual detect_contradictions, normalizer, etc.)
                state = await run_full_pipeline(
                    "metformin cancer",
                    max_papers=2
                )
                
                # Verify pipeline finished successfully
                assert isinstance(state, PipelineState)
                assert state.status == "COMPLETED"
                assert len(state.papers) == 2
                assert len(state.claims) == 2
                
                # Verify quote anchoring verified the claims
                assert state.verification_stats["passed"] == 2
                assert state.verification_stats["rejected"] == 0
                
                # Verify NLI cross-encoder screening & LLM judge actually ran and detected 1 contradiction
                assert len(state.contradictions) == 1
                contradiction = state.contradictions[0]
                assert contradiction.is_genuine is True
                assert contradiction.contradiction_type == ContradictionType.DIRECTION_REVERSAL
                assert contradiction.explanation == "Opposing findings on cancer risk."
                
                # Verify MeSH Entity Normalization ran (mapping metformin -> Metformin / MeSH:D008687)
                assert state.claims[0].entities[0].text == "Metformin"
                assert state.claims[0].entities[0].canonical_id == "MeSH:D008687"
                assert state.claims[1].entities[0].text == "Metformin"
                assert state.claims[1].entities[0].canonical_id == "MeSH:D008687"
                
                # Verify synthesis report was generated and clean citation was used
                assert state.report is not None
                assert "Baker, 2023" in state.report.summary
                assert "Adams, 2020" in state.report.summary
                
                # Verify SQLite Database records
                paper_1_db = get_paper("11111", db_path=temp_db)
                assert paper_1_db is not None
                assert paper_1_db.title == "Study 1 on Metformin"
                
                paper_2_db = get_paper("22222", db_path=temp_db)
                assert paper_2_db is not None
                assert paper_2_db.title == "Study 2 on Metformin"
                
                claim_1_db = get_claim(str(state.claims[0].id), db_path=temp_db)
                assert claim_1_db is not None
                assert claim_1_db.text == "Metformin reduces cancer risk in humans."
                
                contradictions_db = get_contradictions_for_run(["11111", "22222"], db_path=temp_db)
                assert len(contradictions_db) == 1
                
                # Verify SQLite database log for pipeline run
                conn = get_connection(temp_db)
                row = conn.execute("SELECT * FROM pipeline_runs WHERE id = ?", (state.run_id,)).fetchone()
                assert row is not None
                assert row["query"] == "metformin cancer"
                assert row["status"] == "COMPLETED"
                assert row["papers_fetched"] == 2
                assert row["claims_extracted"] == 2
                assert row["contradictions_found"] == 1
                assert row["report_json"] is not None
                conn.close()
