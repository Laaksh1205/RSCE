import uuid
import logging
import json
import asyncio
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, BackgroundTasks, WebSocket, WebSocketDisconnect, HTTPException

from api.schemas import AnalyzeRequest, AnalyzeResponse, StatusResponse
from src.config import settings
from src.pipeline import run_full_pipeline, PipelineState
from src.storage import save_pipeline_run, get_pipeline_run

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# WebSocket Connection Manager for real-time progress broadcasts
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, List[WebSocket]] = {}

    async def connect(self, run_id: str, websocket: WebSocket):
        await websocket.accept()
        if run_id not in self.active_connections:
            self.active_connections[run_id] = []
        self.active_connections[run_id].append(websocket)

    def disconnect(self, run_id: str, websocket: WebSocket):
        if run_id in self.active_connections:
            self.active_connections[run_id].remove(websocket)
            if not self.active_connections[run_id]:
                del self.active_connections[run_id]

    async def broadcast_status(self, run_id: str, data: dict):
        if run_id in self.active_connections:
            for connection in self.active_connections[run_id]:
                try:
                    await connection.send_json(data)
                except Exception as e:
                    logger.warning(f"Failed to send websocket broadcast to connection: {e}")

manager = ConnectionManager()

async def update_run_status(
    run_id: str,
    query: str,
    status: str,
    papers_fetched: Optional[int] = None,
    claims_extracted: Optional[int] = None,
    contradictions_found: Optional[int] = None,
    error_message: Optional[str] = None,
    pmids: Optional[list[str]] = None,
    report_json: Optional[str] = None,
    started_at: Optional[str] = None,
    completed_at: Optional[str] = None
):
    """Helper to save the current run status in SQLite and broadcast it to WebSockets."""
    save_pipeline_run(
        run_id=run_id,
        query=query,
        status=status,
        papers_fetched=papers_fetched,
        claims_extracted=claims_extracted,
        contradictions_found=contradictions_found,
        error_message=error_message,
        pmids=pmids,
        report_json=report_json,
        started_at=started_at,
        completed_at=completed_at
    )
    
    await manager.broadcast_status(run_id, {
        "run_id": run_id,
        "query": query,
        "status": status,
        "papers_fetched": papers_fetched,
        "claims_extracted": claims_extracted,
        "contradictions_found": contradictions_found,
        "error_message": error_message,
        "completed_at": completed_at,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

async def run_analysis_background(run_id: str, query: str, max_papers: int):
    """The async background task executing all RSCE stages using the unified run_full_pipeline."""
    async def on_stage_complete(state: PipelineState):
        pmids = [p.pmid for p in state.papers]
        completed_at = datetime.now(timezone.utc).isoformat() if state.status in ("COMPLETED", "FAILED") else None
        await update_run_status(
            run_id=state.run_id,
            query=state.query,
            status=state.status,
            papers_fetched=len(state.papers),
            claims_extracted=len(state.claims),
            contradictions_found=len(state.contradictions),
            error_message=state.error_message,
            pmids=pmids,
            report_json=state.report.model_dump_json() if state.report else None,
            started_at=state.started_at,
            completed_at=completed_at
        )

    try:
        await run_full_pipeline(
            query=query,
            max_papers=max_papers,
            run_id=run_id,
            on_stage_complete=on_stage_complete
        )
    except Exception as e:
        logger.error(f"Background analysis task failed for run {run_id}: {e}")

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """Start the research synthesis pipeline for a query in the background."""
    run_id = str(uuid.uuid4())
    background_tasks.add_task(
        run_analysis_background,
        run_id=run_id,
        query=request.query,
        max_papers=request.max_papers
    )
    return AnalyzeResponse(
        run_id=run_id,
        query=request.query,
        status="RUNNING"
    )

@router.get("/status/{run_id}", response_model=StatusResponse)
async def get_status(run_id: str):
    """Retrieve the current processing status of an analysis run."""
    run = get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found.")
        
    return StatusResponse(
        run_id=run["id"],
        query=run["query"],
        status=run["status"],
        papers_fetched=run["papers_fetched"],
        claims_extracted=run["claims_extracted"],
        contradictions_found=run["contradictions_found"],
        started_at=run["started_at"],
        completed_at=run["completed_at"],
        error_message=run["error_message"]
    )

@router.websocket("/ws/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str):
    """WebSocket endpoint to subscribe to real-time analysis pipeline stage updates."""
    await manager.connect(run_id, websocket)
    # Immediately send current state if it exists
    run = get_pipeline_run(run_id)
    if run:
        try:
            await websocket.send_json({
                "run_id": run["id"],
                "query": run["query"],
                "status": run["status"],
                "papers_fetched": run["papers_fetched"],
                "claims_extracted": run["claims_extracted"],
                "contradictions_found": run["contradictions_found"],
                "error_message": run["error_message"],
                "completed_at": run["completed_at"],
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception:
            pass
            
    try:
        while True:
            # We must await receive_text to keep the connection alive and detect disconnects
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(run_id, websocket)
