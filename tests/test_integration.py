import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.models.paper import Paper
from src.models.claim import ExtractedClaim, ClaimType, Polarity, StudyDesign, Entity, EntityType, ClaimExtractionResponse
from src.models.contradiction import ContradictionType
from src.pipeline import run_full_pipeline
from src.config import settings

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
async def test_end_to_end_pipeline_api_integration(temp_db, temp_faiss):
    """End-to-end integration test exercising the pipeline execution,
    database persistence, and API REST endpoints serving the results.
    """
    # Override settings.db_path and settings.faiss_index_path with temporary fixtures
    with patch.object(settings, "db_path", temp_db), \
         patch.object(settings, "faiss_index_path", temp_faiss):
         
        # Initialize the database
        from src.storage.database import init_db
        init_db(db_path=temp_db)

        # 1. Mock papers list
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

        # 2. Mock extracted claims
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

        # 3. Patch external pipeline modules
        with patch("src.pipeline.search_pubmed", new_callable=AsyncMock) as mock_search, \
             patch("src.pipeline.fetch_abstracts", new_callable=AsyncMock) as mock_fetch, \
             patch("src.pipeline.enrich_papers_with_full_text", new_callable=AsyncMock):
             
            mock_search.return_value = ["11111", "22222"]
            mock_fetch.return_value = mock_papers
            
            # Construct mock LLM responses
            from src.detection.llm_judge import JudgeResponse
            mock_llm = MagicMock()
            mock_llm.model_name = "mock-integration-llm"
            
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
            
            # Create a mock EntityNormalizer to decouple from scispaCy, synonym_map.json, and LLM fallbacks
            class MockEntityNormalizer:
                async def normalize_entities(self, claims):
                    for claim in claims:
                        for entity in claim.entities:
                            if entity.text.lower() == "metformin":
                                entity.text = "Metformin"
                                entity.canonical_id = "MeSH:D008687"
                    return claims

            # Patch get_llm to return our mock LLM and EntityNormalizer
            with patch("src.pipeline.get_llm", return_value=mock_llm), \
                 patch("src.detection.contradiction_detector.get_llm", return_value=mock_llm), \
                 patch("src.pipeline.EntityNormalizer", return_value=MockEntityNormalizer()):
                 
                # Execute full pipeline end-to-end (updates temporary database)
                state = await run_full_pipeline(
                    "metformin cancer",
                    max_papers=2
                )
                
                # Verify pipeline returned successfully
                assert state.status == "COMPLETED"
                assert len(state.papers) == 2
                assert len(state.claims) == 2
                assert len(state.contradictions) == 1
                
                # Now, test the REST API endpoints using FastAPI's TestClient
                from fastapi.testclient import TestClient
                from api.app import app
                
                # Initialize the TestClient
                client = TestClient(app)
                
                # Test 1: Get Status Endpoint
                status_res = client.get(f"/api/status/{state.run_id}")
                assert status_res.status_code == 200
                status_data = status_res.json()
                assert status_data["run_id"] == state.run_id
                assert status_data["status"] == "COMPLETED"
                assert status_data["papers_fetched"] == 2
                assert status_data["claims_extracted"] == 2
                assert status_data["contradictions_found"] == 1
                
                # Test 2: Get Results Endpoint
                results_res = client.get(f"/api/results/{state.run_id}")
                assert results_res.status_code == 200
                results_data = results_res.json()
                assert results_data["total_papers"] == 2
                assert results_data["total_claims"] == 2
                assert len(results_data["contradictions"]) == 1
                assert "Baker, 2023" in results_data["summary"]
                assert "Adams, 2020" in results_data["summary"]
                
                # Test 3: Get Claims Endpoint
                claims_res = client.get(f"/api/claims/{state.run_id}")
                assert claims_res.status_code == 200
                claims_data = claims_res.json()
                assert len(claims_data) == 2
                assert claims_data[0]["text"] == "Metformin reduces cancer risk in humans."
                assert claims_data[1]["text"] == "Metformin increases cancer risk in humans."
                
                # Test 4: Get Graph Endpoint
                graph_res = client.get(f"/api/graph/{state.run_id}")
                assert graph_res.status_code == 200
                graph_data = graph_res.json()
                assert "elements" in graph_data
                assert "nodes" in graph_data["elements"]
                assert "edges" in graph_data["elements"]
                # Verify nodes by checking types rather than a strict total count
                nodes = graph_data["elements"]["nodes"]
                assert len(nodes) >= 4
                node_types = [n["data"]["type"] for n in nodes]
                assert node_types.count("paper") == 2
                assert node_types.count("claim") == 2
                assert node_types.count("entity") >= 1

                # Test 5: WebSocket Endpoint (GET /api/ws/{run_id})
                # FastAPI TestClient websocket_connect context manager connects synchronously.
                # Since the test is async, we can await broadcast_status on the event loop,
                # which will push the message to the socket for TestClient to read.
                with client.websocket_connect(f"/api/ws/{state.run_id}") as websocket:
                    # Verify immediate state broadcast on connection
                    initial_data = websocket.receive_json()
                    assert initial_data["run_id"] == state.run_id
                    assert initial_data["status"] == "COMPLETED"
                    assert initial_data["papers_fetched"] == 2
                    assert initial_data["claims_extracted"] == 2
                    assert initial_data["contradictions_found"] == 1
                    
                    # Verify manager broadcast updates are received by active websocket connections
                    from api.routes.analysis import manager
                    test_payload = {
                        "run_id": state.run_id,
                        "status": "RUNNING",
                        "status_message": "WebSocket broadcast test",
                        "papers_fetched": 3,
                        "claims_extracted": 4,
                        "contradictions_found": 2
                    }
                    await manager.broadcast_status(state.run_id, test_payload)
                    
                    broadcast_data = websocket.receive_json()
                    assert broadcast_data["run_id"] == state.run_id
                    assert broadcast_data["status"] == "RUNNING"
                    assert broadcast_data["status_message"] == "WebSocket broadcast test"
                    assert broadcast_data["papers_fetched"] == 3
                    assert broadcast_data["claims_extracted"] == 4
                    assert broadcast_data["contradictions_found"] == 2


