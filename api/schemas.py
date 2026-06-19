from pydantic import BaseModel, Field
from typing import Optional

class AnalyzeRequest(BaseModel):
    query: str = Field(..., description="The research question or search terms to analyze")
    max_papers: int = Field(25, description="Maximum number of papers to fetch from PubMed")
    seed_claim: Optional[str] = Field(None, description="An optional user-asserted claim to find contradicting evidence for")
    date_from: Optional[int] = Field(None, description="Optional minimum publication year filter (inclusive)")
    date_to: Optional[int] = Field(None, description="Optional maximum publication year filter (inclusive)")
    journals: Optional[list[str]] = Field(None, description="Optional list of journals to restrict search to")

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
    status_message: Optional[str] = Field(None, description="Detailed sub-progress message")
    total_papers: Optional[int] = Field(None, description="Total number of papers to fetch")
    papers_extracted: Optional[int] = Field(None, description="Number of papers with completed claim extraction")
    nli_pairs_total: Optional[int] = Field(None, description="Total candidate pairs for NLI scoring")
    nli_pairs_scored: Optional[int] = Field(None, description="Number of candidate pairs scored via NLI")
    judge_pairs_total: Optional[int] = Field(None, description="Total pairs for LLM judging")
    judge_pairs_scored: Optional[int] = Field(None, description="Number of pairs judged via LLM")
    seed_claim: Optional[str] = Field(None, description="Optional seed claim used for biasing")
    date_from: Optional[int] = Field(None, description="Minimum publication year filter")
    date_to: Optional[int] = Field(None, description="Maximum publication year filter")
    journals: Optional[list[str]] = Field(None, description="List of journals filter")

