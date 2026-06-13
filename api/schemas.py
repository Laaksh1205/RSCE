from pydantic import BaseModel, Field
from typing import Any, Optional

class AnalyzeRequest(BaseModel):
    query: str = Field(..., description="The research question or search terms to analyze")
    max_papers: int = Field(25, description="Maximum number of papers to fetch from PubMed")

class AnalyzeResponse(BaseModel):
    run_id: str = Field(..., description="Unique UUID for this analysis run")
    query: str = Field(..., description="The query being processed")
    status: str = Field(..., description="Current status of the run (e.g. RUNNING)")

class StatusResponse(BaseModel):
    run_id: str = Field(..., description="Unique UUID for this analysis run")
    query: str = Field(..., description="The query being processed")
    status: str = Field(..., description="Current status of the run (RUNNING, COMPLETED, FAILED)")
    papers_fetched: Optional[int] = Field(None, description="Number of papers fetched so far")
    claims_extracted: Optional[int] = Field(None, description="Number of claims extracted so far")
    contradictions_found: Optional[int] = Field(None, description="Number of contradictions detected")
    started_at: Optional[str] = Field(None, description="ISO timestamp of when the run started")
    completed_at: Optional[str] = Field(None, description="ISO timestamp of when the run finished")
    error_message: Optional[str] = Field(None, description="Details of failure if the run failed")
