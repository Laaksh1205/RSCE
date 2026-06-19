import os
import json
import sqlite3
import uuid
import logging
from typing import Optional
from src.config import settings
from src.models.paper import Paper
from src.models.claim import Claim, Entity, ClaimType, Polarity, StudyDesign
from src.models.contradiction import ContradictionPair, ContradictionType

logger = logging.getLogger(__name__)

def validate_pmids(pmids: list[str]) -> None:
    """Validate that PMIDs contain only safe characters to prevent SQL injection."""
    for pmid in pmids:
        if not pmid or not isinstance(pmid, str):
            raise ValueError(f"Invalid PMID: {pmid}")
        # PMIDs should be alphanumeric with possible hyphens/underscores
        if not pmid.replace('-', '').replace('_', '').isalnum():
            raise ValueError(f"PMID contains invalid characters: {pmid}")

def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Establish a connection to the SQLite database and enable foreign keys."""
    if db_path is None:
        db_path = settings.db_path
    db_dir = os.path.dirname(os.path.abspath(db_path))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: Optional[str] = None) -> None:
    """Initialize the SQLite tables matching the schema."""
    if db_path is None:
        db_path = settings.db_path
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                pmid TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                authors TEXT NOT NULL,     -- JSON array of strings
                year INTEGER NOT NULL,
                journal TEXT,
                abstract_text TEXT NOT NULL,
                full_text TEXT,
                doi TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS claims (
                id TEXT PRIMARY KEY,       -- UUID string
                paper_id TEXT NOT NULL REFERENCES papers(pmid) ON DELETE CASCADE,
                text TEXT NOT NULL,
                normalized_text TEXT,
                polarity TEXT NOT NULL,
                population TEXT,
                context TEXT,
                section TEXT,              -- Section of the paper
                quote_anchor TEXT NOT NULL,
                claim_type TEXT NOT NULL,
                study_design TEXT,
                confidence_score REAL NOT NULL,
                is_primary_finding BOOLEAN DEFAULT TRUE,
                sample_size INTEGER,
                entities TEXT,             -- JSON array of Entity dicts
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contradictions (
                id TEXT PRIMARY KEY,       -- UUID string
                claim_a_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
                claim_b_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
                contradiction_score REAL NOT NULL,
                contradiction_type TEXT NOT NULL,
                explanation TEXT,
                scope_note TEXT,
                temporal_resolution TEXT,
                is_genuine BOOLEAN NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                status TEXT NOT NULL,       -- RUNNING | COMPLETED | FAILED
                papers_fetched INTEGER,
                claims_extracted INTEGER,
                contradictions_found INTEGER,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                pmids TEXT,                 -- JSON array of PMID strings
                report_json TEXT,           -- Serialized SynthesisReport
                status_message TEXT,
                total_papers INTEGER,
                papers_extracted INTEGER,
                nli_pairs_total INTEGER,
                nli_pairs_scored INTEGER,
                judge_pairs_total INTEGER,
                judge_pairs_scored INTEGER,
                seed_claim TEXT,
                date_from INTEGER,
                date_to INTEGER,
                journals TEXT
            );
        """)
    # Run automatic migrations for existing databases
    with conn:
        try:
            conn.execute("ALTER TABLE pipeline_runs ADD COLUMN pmids TEXT;")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE pipeline_runs ADD COLUMN report_json TEXT;")
        except sqlite3.OperationalError:
            pass
            
        # New columns for progress tracking and seed claims
        new_cols = [
            ("status_message", "TEXT"),
            ("total_papers", "INTEGER"),
            ("papers_extracted", "INTEGER"),
            ("nli_pairs_total", "INTEGER"),
            ("nli_pairs_scored", "INTEGER"),
            ("judge_pairs_total", "INTEGER"),
            ("judge_pairs_scored", "INTEGER"),
            ("seed_claim", "TEXT"),
            ("date_from", "INTEGER"),
            ("date_to", "INTEGER"),
            ("journals", "TEXT")
        ]
        for col_name, col_type in new_cols:
            try:
                conn.execute(f"ALTER TABLE pipeline_runs ADD COLUMN {col_name} {col_type};")
            except sqlite3.OperationalError:
                pass
        try:
            conn.execute("ALTER TABLE claims ADD COLUMN embedding BLOB;")
        except sqlite3.OperationalError:
            pass
    conn.close()
    logger.info(f"Database initialized at: {db_path}")

def save_papers(papers: list[Paper], db_path: Optional[str] = None) -> None:
    """Save a list of Paper objects to the database."""
    if db_path is None:
        db_path = settings.db_path
    conn = get_connection(db_path)
    with conn:
        for paper in papers:
            conn.execute("""
                INSERT OR REPLACE INTO papers (pmid, title, authors, year, journal, abstract_text, full_text, doi)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                paper.pmid,
                paper.title,
                json.dumps(paper.authors),
                paper.year,
                paper.journal,
                paper.abstract_text,
                paper.full_text,
                paper.doi
            ))
    conn.close()

def save_claims(claims: list[Claim], db_path: Optional[str] = None) -> None:
    """Save a list of Claim objects to the database."""
    if db_path is None:
        db_path = settings.db_path
    conn = get_connection(db_path)
    with conn:
        for claim in claims:
            emb_bytes = None
            if claim.embedding is not None:
                import numpy as np
                emb_bytes = np.asarray(claim.embedding, dtype=np.float32).tobytes()
            conn.execute("""
                INSERT OR REPLACE INTO claims (
                    id, paper_id, text, normalized_text, polarity, population, context, section,
                    quote_anchor, claim_type, study_design, confidence_score, is_primary_finding,
                    sample_size, entities, embedding
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(claim.id),
                claim.paper_id,
                claim.text,
                claim.normalized_text,
                claim.polarity.value,
                claim.population,
                claim.context,
                claim.section,
                claim.quote_anchor,
                claim.claim_type.value,
                claim.study_design.value,
                claim.confidence_score,
                1 if claim.is_primary_finding else 0,
                claim.sample_size,
                json.dumps([e.model_dump() for e in claim.entities]),
                emb_bytes
            ))
    conn.close()

def save_contradictions(contradictions: list[ContradictionPair], db_path: Optional[str] = None) -> list[str]:
    """Save a list of ContradictionPair objects to the database and return their assigned UUIDs."""
    if db_path is None:
        db_path = settings.db_path
    conn = get_connection(db_path)
    assigned_ids = []
    with conn:
        for pair in contradictions:
            pair_id = str(uuid.uuid4())
            assigned_ids.append(pair_id)
            conn.execute("""
                INSERT INTO contradictions (
                    id, claim_a_id, claim_b_id, contradiction_score, contradiction_type,
                    explanation, scope_note, temporal_resolution, is_genuine
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pair_id,
                str(pair.claim_a.id),
                str(pair.claim_b.id),
                pair.contradiction_score,
                pair.contradiction_type.value,
                pair.explanation,
                pair.scope_note,
                pair.temporal_resolution,
                1 if pair.is_genuine else 0
            ))
    conn.close()
    return assigned_ids

def save_pipeline_run(
    run_id: str,
    query: str,
    status: str,
    papers_fetched: Optional[int] = None,
    claims_extracted: Optional[int] = None,
    contradictions_found: Optional[int] = None,
    started_at: Optional[str] = None,
    completed_at: Optional[str] = None,
    error_message: Optional[str] = None,
    pmids: Optional[list[str]] = None,
    report_json: Optional[str] = None,
    status_message: Optional[str] = None,
    total_papers: Optional[int] = None,
    papers_extracted: Optional[int] = None,
    nli_pairs_total: Optional[int] = None,
    nli_pairs_scored: Optional[int] = None,
    judge_pairs_total: Optional[int] = None,
    judge_pairs_scored: Optional[int] = None,
    seed_claim: Optional[str] = None,
    date_from: Optional[int] = None,
    date_to: Optional[int] = None,
    journals: Optional[list[str]] = None,
    db_path: Optional[str] = None
) -> None:
    """Save or update a pipeline run status."""
    if db_path is None:
        db_path = settings.db_path
    conn = get_connection(db_path)
    with conn:
        row = conn.execute("SELECT 1 FROM pipeline_runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            conn.execute("""
                INSERT INTO pipeline_runs (
                    id, query, status, papers_fetched, claims_extracted, contradictions_found,
                    started_at, completed_at, error_message, pmids, report_json,
                    status_message, total_papers, papers_extracted, nli_pairs_total, nli_pairs_scored,
                    judge_pairs_total, judge_pairs_scored, seed_claim, date_from, date_to, journals
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id, query, status, papers_fetched, claims_extracted, contradictions_found,
                started_at, completed_at, error_message,
                json.dumps(pmids) if pmids is not None else None,
                report_json,
                status_message, total_papers, papers_extracted, nli_pairs_total, nli_pairs_scored,
                judge_pairs_total, judge_pairs_scored, seed_claim,
                date_from, date_to, json.dumps(journals) if journals is not None else None
            ))
        else:
            update_fields = []
            params = []
            
            update_fields.append("query = ?")
            params.append(query)
            update_fields.append("status = ?")
            params.append(status)
            
            if papers_fetched is not None:
                update_fields.append("papers_fetched = ?")
                params.append(papers_fetched)
            if claims_extracted is not None:
                update_fields.append("claims_extracted = ?")
                params.append(claims_extracted)
            if contradictions_found is not None:
                update_fields.append("contradictions_found = ?")
                params.append(contradictions_found)
            if started_at is not None:
                update_fields.append("started_at = ?")
                params.append(started_at)
            if completed_at is not None:
                update_fields.append("completed_at = ?")
                params.append(completed_at)
            if error_message is not None:
                update_fields.append("error_message = ?")
                params.append(error_message)
            if pmids is not None:
                update_fields.append("pmids = ?")
                params.append(json.dumps(pmids))
            if report_json is not None:
                update_fields.append("report_json = ?")
                params.append(report_json)
            if status_message is not None:
                update_fields.append("status_message = ?")
                params.append(status_message)
            if total_papers is not None:
                update_fields.append("total_papers = ?")
                params.append(total_papers)
            if papers_extracted is not None:
                update_fields.append("papers_extracted = ?")
                params.append(papers_extracted)
            if nli_pairs_total is not None:
                update_fields.append("nli_pairs_total = ?")
                params.append(nli_pairs_total)
            if nli_pairs_scored is not None:
                update_fields.append("nli_pairs_scored = ?")
                params.append(nli_pairs_scored)
            if judge_pairs_total is not None:
                update_fields.append("judge_pairs_total = ?")
                params.append(judge_pairs_total)
            if judge_pairs_scored is not None:
                update_fields.append("judge_pairs_scored = ?")
                params.append(judge_pairs_scored)
            if seed_claim is not None:
                update_fields.append("seed_claim = ?")
                params.append(seed_claim)
            if date_from is not None:
                update_fields.append("date_from = ?")
                params.append(date_from)
            if date_to is not None:
                update_fields.append("date_to = ?")
                params.append(date_to)
            if journals is not None:
                update_fields.append("journals = ?")
                params.append(json.dumps(journals))
                
            params.append(run_id)
            query_str = f"UPDATE pipeline_runs SET {', '.join(update_fields)} WHERE id = ?"
            conn.execute(query_str, tuple(params))
    conn.close()

def get_pipeline_run(run_id: str, db_path: Optional[str] = None) -> Optional[dict]:
    """Retrieve a pipeline run record from the database by run_id."""
    if db_path is None:
        db_path = settings.db_path
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM pipeline_runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _row_to_paper(row: sqlite3.Row) -> Paper:
    return Paper(
        pmid=row["pmid"],
        title=row["title"],
        authors=json.loads(row["authors"]),
        year=row["year"],
        journal=row["journal"] or "",
        abstract_text=row["abstract_text"],
        full_text=row["full_text"],
        doi=row["doi"]
    )

def _row_to_claim(row: sqlite3.Row, conn: sqlite3.Connection) -> Claim:
    # Use pre-fetched authors and year if they exist in the Row (e.g. from JOIN query)
    if "authors" in row.keys() and "year" in row.keys():
        authors = json.loads(row["authors"]) if row["authors"] else []
        year = row["year"] if row["year"] is not None else None
    else:
        # Query paper to resolve authors/year since they are dynamic metadata on the Claim model
        paper_row = conn.execute("SELECT authors, year FROM papers WHERE pmid = ?", (row["paper_id"],)).fetchone()
        authors = json.loads(paper_row["authors"]) if paper_row else []
        year = paper_row["year"] if paper_row else None

    entities_data = json.loads(row["entities"]) if row["entities"] else []
    entities = [Entity(**e) for e in entities_data]

    embedding = None
    if "embedding" in row.keys() and row["embedding"] is not None:
        import numpy as np
        embedding = np.frombuffer(row["embedding"], dtype=np.float32).tolist()

    return Claim(
        id=uuid.UUID(row["id"]),
        text=row["text"],
        normalized_text=row["normalized_text"],
        paper_id=row["paper_id"],
        section=row["section"] or "Abstract",
        authors=authors,
        year=year if year is not None else 0,  # Default to 0 for Claim model compatibility
        confidence_score=row["confidence_score"],
        claim_type=ClaimType(row["claim_type"]),
        polarity=Polarity(row["polarity"]),
        entities=entities,
        population=row["population"] or "",
        context=row["context"] or "",
        quote_anchor=row["quote_anchor"],
        sample_size=row["sample_size"],
        study_design=StudyDesign(row["study_design"]),
        is_primary_finding=bool(row["is_primary_finding"]),
        embedding=embedding
    )

def _get_claim_with_conn(claim_id: str, conn: sqlite3.Connection) -> Optional[Claim]:
    """Retrieve a single Claim using an existing connection, using a JOIN to get paper metadata."""
    row = conn.execute("""
        SELECT c.*, p.authors, p.year FROM claims c
        JOIN papers p ON c.paper_id = p.pmid
        WHERE c.id = ?
    """, (claim_id,)).fetchone()
    if row:
        return _row_to_claim(row, conn)
    return None

def get_paper(pmid: str, db_path: Optional[str] = None) -> Optional[Paper]:
    """Retrieve a single Paper from the database by PMID."""
    if db_path is None:
        db_path = settings.db_path
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM papers WHERE pmid = ?", (pmid,)).fetchone()
        return _row_to_paper(row) if row else None
    finally:
        conn.close()

def get_claim(claim_id: str, db_path: Optional[str] = None) -> Optional[Claim]:
    """Retrieve a single Claim from the database by its ID."""
    if db_path is None:
        db_path = settings.db_path
    conn = get_connection(db_path)
    try:
        return _get_claim_with_conn(claim_id, conn)
    finally:
        conn.close()

def get_claims_for_run(paper_ids: list[str], db_path: Optional[str] = None) -> list[Claim]:
    """Retrieve all claims associated with a list of PMIDs using a JOIN to fetch paper metadata in one query."""
    if not paper_ids:
        return []
    validate_pmids(paper_ids)
    if db_path is None:
        db_path = settings.db_path
    conn = get_connection(db_path)
    try:
        placeholders = ",".join("?" for _ in paper_ids)
        rows = conn.execute(f"""
            SELECT c.*, p.authors, p.year FROM claims c
            JOIN papers p ON c.paper_id = p.pmid
            WHERE c.paper_id IN ({placeholders})
        """, paper_ids).fetchall()
        return [_row_to_claim(r, conn) for r in rows]
    finally:
        conn.close()

def get_papers_for_run(paper_ids: list[str], db_path: Optional[str] = None) -> list[Paper]:
    """Retrieve all papers associated with a list of PMIDs."""
    if not paper_ids:
        return []
    validate_pmids(paper_ids)
    if db_path is None:
        db_path = settings.db_path
    conn = get_connection(db_path)
    try:
        placeholders = ",".join("?" for _ in paper_ids)
        rows = conn.execute(f"SELECT * FROM papers WHERE pmid IN ({placeholders})", paper_ids).fetchall()
        return [_row_to_paper(r) for r in rows]
    finally:
        conn.close()

def get_contradictions_for_run(paper_ids: list[str], db_path: Optional[str] = None) -> list[ContradictionPair]:
    """Retrieve all contradiction pairs where both claims belong to the set of paper PMIDs."""
    if not paper_ids:
        return []
    validate_pmids(paper_ids)
    if db_path is None:
        db_path = settings.db_path
    conn = get_connection(db_path)
    try:
        placeholders = ",".join("?" for _ in paper_ids)
        query = f"""
            SELECT c.* FROM contradictions c
            JOIN claims ca ON c.claim_a_id = ca.id
            JOIN claims cb ON c.claim_b_id = cb.id
            WHERE ca.paper_id IN ({placeholders}) AND cb.paper_id IN ({placeholders})
        """
        params = paper_ids + paper_ids
        rows = conn.execute(query, params).fetchall()

        contradictions = []
        for r in rows:
            claim_a = _get_claim_with_conn(r["claim_a_id"], conn)
            claim_b = _get_claim_with_conn(r["claim_b_id"], conn)
            if claim_a and claim_b:
                contradictions.append(
                    ContradictionPair(
                        claim_a=claim_a,
                        claim_b=claim_b,
                        contradiction_score=r["contradiction_score"],
                        contradiction_type=ContradictionType(r["contradiction_type"]),
                        explanation=r["explanation"],
                        scope_note=r["scope_note"],
                        temporal_resolution=r["temporal_resolution"],
                        is_genuine=bool(r["is_genuine"])
                    )
                )
        return contradictions
    finally:
        conn.close()

