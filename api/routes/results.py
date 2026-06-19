import json
import logging
from typing import List

import networkx as nx

from fastapi import APIRouter, HTTPException

from src.models.claim import Claim
from src.models.report import SynthesisReport
from src.graph.claim_graph import build_claim_graph
from src.storage import (
    get_pipeline_run,
    get_claims_for_run,
    get_papers_for_run,
    get_contradictions_for_run
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

@router.get("/results/{run_id}", response_model=SynthesisReport)
async def get_results(run_id: str):
    """Retrieve the finalized synthesis report results for a completed run."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found.")
        
    if run["status"] == "RUNNING":
        raise HTTPException(status_code=400, detail="Analysis is still in progress.")
    elif run["status"] == "FAILED":
        raise HTTPException(
            status_code=400, 
            detail=f"Analysis run failed: {run['error_message'] or 'Unknown error'}"
        )
        
    if not run["report_json"]:
        raise HTTPException(status_code=500, detail="Report generation was not completed successfully.")
        
    try:
        report_data = json.loads(run["report_json"])
        # Reconstruct Pydantic model
        return SynthesisReport(**report_data)
    except Exception as e:
        logger.error(f"Failed to load or parse report JSON for run {run_id}: {e}")
        raise HTTPException(status_code=500, detail="Malformed synthesis report data.")

@router.get("/claims/{run_id}", response_model=List[Claim])
async def get_claims(run_id: str):
    """Retrieve all claims extracted and normalized during an analysis run."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found.")
        
    if not run["pmids"]:
        return []
        
    try:
        pmids = json.loads(run["pmids"])
        claims = get_claims_for_run(pmids)
        return claims
    except Exception as e:
        logger.error(f"Failed to retrieve claims for run {run_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve claims data.")

@router.get("/graph/{run_id}")
async def get_graph(run_id: str):
    """Retrieve the claim-evidence graph in Cytoscape.js compatible JSON format."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found.")
        
    if not run["pmids"]:
        return {"elements": {"nodes": [], "edges": []}}
        
    try:
        pmids = json.loads(run["pmids"])
        
        # Load elements associated with these pmids
        papers = get_papers_for_run(pmids)
        claims = get_claims_for_run(pmids)
        contradictions = get_contradictions_for_run(pmids)
        
        # Construct graph
        G = build_claim_graph(claims, contradictions, papers)
        
        # Export in cytoscape.js compatible JSON format
        cytoscape_data = nx.readwrite.json_graph.cytoscape_data(G)
        return cytoscape_data
    except Exception as e:
        logger.error(f"Failed to generate graph JSON for run {run_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to build claim graph data.")

@router.get("/demo/{topic}")
async def get_demo_results(topic: str):
    """Retrieve all data for a pre-loaded demo topic: report, claims, and graph."""
    # Validate and sanitize topic parameter
    if not topic or not isinstance(topic, str):
        raise HTTPException(status_code=400, detail="Invalid topic parameter")

    # Remove any potentially dangerous characters
    sanitized_topic = topic.lower().strip()
    if not sanitized_topic.replace('_', '').replace('-', '').isalnum():
        raise HTTPException(status_code=400, detail="Topic contains invalid characters")

    topic_map = {
        "metformin": "demo_metformin",
        "metformin_cancer_risk": "demo_metformin",
        "fasting": "demo_fasting",
        "intermittent_fasting_insulin_sensitivity": "demo_fasting",
        "ssri": "demo_ssri",
        "ssri_depression_adolescents": "demo_ssri",
    }

    run_id = topic_map.get(sanitized_topic)
    if not run_id:
        raise HTTPException(
            status_code=404,
            detail=f"Demo topic '{sanitized_topic}' not found. Available: metformin, fasting, ssri"
        )
        
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(
            status_code=404, 
            detail=f"Demo run '{run_id}' not initialized in database."
        )
        
    try:
        report_data = json.loads(run["report_json"]) if run["report_json"] else None
        pmids = json.loads(run["pmids"]) if run["pmids"] else []
        
        # Load claims and build graph
        claims = get_claims_for_run(pmids)
        papers = get_papers_for_run(pmids)
        contradictions = get_contradictions_for_run(pmids)
        G = build_claim_graph(claims, contradictions, papers)
        cytoscape_data = nx.readwrite.json_graph.cytoscape_data(G)
        
        return {
            "run_id": run_id,
            "query": run["query"],
            "report": report_data,
            "claims": claims,
            "graph": cytoscape_data
        }
    except Exception as e:
        logger.error(f"Failed to load demo results for {topic}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve demo results.")

