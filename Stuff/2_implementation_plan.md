# Research Synthesis & Contradiction Engine — Implementation Plan

> [!NOTE]
> This plan decomposes [research_synthesis_engine_design.md](file:///c:/Users/laaks/.gemini/antigravity-ide/brain/b814a22c-fa50-4d8e-bca0-1608bc43ed05/research_synthesis_engine_design.md) into executable tasks. Every task maps to a specific file, function, or deliverable.

---

## Project Location

```
c:\Users\laaks\ZZ\Projects\P1\
```

## Target Directory Tree (Final State)

```
P1/
├── pyproject.toml                    # Project metadata + dependencies
├── .env.example                      # API key template
├── .gitignore
├── README.md                         # Portfolio-grade README (Phase 5)
├── Dockerfile                        # (Phase 5)
├── Makefile                          # Common commands: run, test, eval, lint
│
├── src/
│   ├── __init__.py
│   ├── main.py                       # CLI entrypoint (click or typer)
│   ├── config.py                     # Settings, API keys, thresholds
│   ├── models/
│   │   ├── __init__.py
│   │   ├── paper.py                  # Paper dataclass
│   │   ├── claim.py                  # Claim, Entity, enums
│   │   ├── contradiction.py          # ContradictionPair, ContradictionType
│   │   └── report.py                 # SynthesisReport dataclass
│   │
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── pubmed.py                 # PubMed E-utilities fetcher
│   │   ├── semantic_scholar.py       # Semantic Scholar API (fallback/enrichment)
│   │   └── pmc_xml.py                # PubMed Central XML parser (Phase 3)
│   │
│   ├── extraction/
│   │   ├── __init__.py
│   │   ├── claim_extractor.py        # LLM-based claim extraction
│   │   ├── quote_verifier.py         # Quote-anchor fuzzy matching
│   │   └── prompts/
│   │       ├── extraction_prompt.txt  # Main extraction prompt
│   │       ├── extraction_few_shot.json  # Few-shot examples
│   │       └── judge_prompt.txt       # Contradiction judge prompt
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py                   # Abstract LLM provider interface
│   │   ├── gemini.py                 # Gemini API client
│   │   └── openai.py                 # OpenAI API client (swap-in)
│   │
│   ├── detection/
│   │   ├── __init__.py
│   │   ├── embedder.py               # Sentence transformer wrapper
│   │   ├── faiss_index.py            # FAISS index build + query
│   │   ├── nli_scorer.py             # DeBERTa NLI cross-encoder
│   │   ├── llm_judge.py              # LLM-based scope/genuineness judge
│   │   └── contradiction_detector.py # Orchestrates A → B → C pipeline
│   │
│   ├── graph/                         # (Phase 3)
│   │   ├── __init__.py
│   │   ├── claim_graph.py            # NetworkX graph construction
│   │   └── graph_export.py           # JSON/GEXF export
│   │
│   ├── synthesis/
│   │   ├── __init__.py
│   │   └── report_generator.py       # RAG over claims → grounded summary
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py               # SQLite schema + CRUD operations
│   │   └── faiss_store.py            # FAISS index persistence
│   │
│   ├── presentation/
│   │   ├── __init__.py
│   │   ├── cli_report.py             # Rich terminal output
│   │   └── json_export.py            # Structured JSON output
│   │
│   ├── entity/                        # (Phase 3)
│   │   ├── __init__.py
│   │   └── normalizer.py             # scispaCy + MeSH entity linking
│   │
│   └── pipeline.py                   # End-to-end orchestrator
│
├── api/                               # (Phase 4)
│   ├── __init__.py
│   ├── app.py                        # FastAPI application
│   ├── routes/
│   │   ├── analysis.py               # POST /analyze endpoint
│   │   └── results.py                # GET /results endpoint
│   └── schemas.py                    # API request/response models
│
├── frontend/                          # (Phase 4)
│   └── (Next.js app)
│
├── tests/
│   ├── __init__.py
│   ├── test_pubmed.py
│   ├── test_claim_extractor.py
│   ├── test_quote_verifier.py
│   ├── test_nli_scorer.py
│   ├── test_contradiction_detector.py
│   ├── test_pipeline.py
│   └── fixtures/
│       ├── sample_abstracts.json     # 10 hand-picked abstracts
│       └── expected_claims.json      # Manually annotated expected claims
│
├── evaluation/
│   ├── scifact_eval.py               # SciFact benchmark runner
│   ├── results/                      # Precision/recall outputs
│   └── gold_standard/                # Hand-curated contradiction pairs
│
├── data/
│   ├── scifact/                      # Downloaded SciFact dataset
│   └── sample_runs/                  # Cached sample outputs for demo
│
└── docs/
    ├── architecture.png              # Architecture diagram for README
    └── demo.gif                      # Terminal recording (Phase 5)
```

---

## Phase 0 — Project Scaffolding (Day 1, ~3 hours)

### 0.1 Initialize Project

- [ ] **Task:** Create project directory and initialize git repo
  - Create `c:\Users\laaks\ZZ\Projects\P1\` directory structure
  - `git init`
  - Create `.gitignore` (Python defaults + `.env`, `data/scifact/`, `*.faiss`, `__pycache__/`, `.venv/`)
  - Create `.env.example` with:
    ```
    GEMINI_API_KEY=your_key_here
    OPENAI_API_KEY=your_key_here  # optional
    PUBMED_EMAIL=your_email@example.com
    PUBMED_API_KEY=optional_ncbi_key
    ```
  - **Acceptance:** `git status` shows clean repo with `.gitignore` working

### 0.2 Create `pyproject.toml`

- [ ] **Task:** Define project metadata and all dependencies
  - **File:** [pyproject.toml](file:///c:/Users/laaks/ZZ/Projects/P1/pyproject.toml) `[NEW]`
  - Dependencies grouped by purpose:

    | Group | Packages | Purpose |
    |---|---|---|
    | Core | `pydantic>=2.0`, `python-dotenv`, `aiohttp`, `asyncio` | Data models, env config, async HTTP |
    | LLM | `google-genai>=1.0`, `openai>=1.0` | LLM API clients |
    | ML | `sentence-transformers`, `faiss-cpu`, `torch` | Embeddings, vector search |
    | NLI | `transformers`, `accelerate` | DeBERTa cross-encoder |
    | Verification | `rapidfuzz` | Quote-anchor fuzzy matching |
    | Storage | (stdlib `sqlite3`) | No extra dependency |
    | CLI | `rich`, `typer` | Terminal output, CLI framework |
    | Phase 3 | `networkx`, `scispacy`, `lxml` | Graph, entity NER, XML parsing |
    | Phase 4 | `fastapi`, `uvicorn` | REST API |
    | Dev | `pytest`, `pytest-asyncio`, `ruff` | Testing, linting |

  - **Acceptance:** `pip install -e .` succeeds with all dependencies

### 0.3 Create Config Module

- [ ] **Task:** Centralized configuration with sensible defaults
  - **File:** [src/config.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/config.py) `[NEW]`
  - Load from `.env` via `python-dotenv`
  - Settings (Pydantic `BaseSettings`):
    ```python
    class Settings(BaseSettings):
        # API Keys
        gemini_api_key: str
        openai_api_key: str = ""
        pubmed_email: str
        pubmed_api_key: str = ""

        # LLM Config
        extraction_model: str = "gemini-2.5-flash"
        judge_model: str = "gemini-2.5-pro"
        llm_provider: Literal["gemini", "openai"] = "gemini"

        # Pipeline Thresholds
        max_papers: int = 25
        min_papers: int = 5
        claims_per_abstract_cap: int = 7
        quote_anchor_pass_threshold: float = 85.0
        quote_anchor_flag_threshold: float = 70.0
        faiss_top_k: int = 10
        nli_contradiction_threshold: float = 0.7
        max_contradictions_displayed: int = 15

        # Concurrency
        pubmed_concurrency: int = 3
        llm_concurrency: int = 5

        # Paths
        db_path: str = "data/claims.db"
        faiss_index_path: str = "data/claims.faiss"
    ```
  - **Acceptance:** `from src.config import settings` loads values from `.env`

### 0.4 Create Core Data Models

- [ ] **Task:** Implement all Pydantic models matching the design doc's entity schema
  - **File:** [src/models/paper.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/models/paper.py) `[NEW]`
    ```python
    class Paper(BaseModel):
        pmid: str
        title: str
        authors: list[str]
        year: int
        journal: str
        abstract_text: str
        full_text: str | None = None
        doi: str | None = None
    ```
  - **File:** [src/models/claim.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/models/claim.py) `[NEW]`
    - `ClaimType` enum: `CAUSAL | CORRELATIONAL | QUANTITATIVE | DEFINITIONAL | MECHANISTIC`
    - `Polarity` enum: `POSITIVE | NEGATIVE | NEUTRAL`
    - `StudyDesign` enum: `META_ANALYSIS | RCT | COHORT | CASE_CONTROL | IN_VITRO | CASE_REPORT | REVIEW`
    - `EntityType` enum: `DRUG | GENE | DISEASE | PROTEIN | PATHWAY | BIOMARKER`
    - `Entity` model: `text`, `canonical_id`, `entity_type`
    - `Claim` model: all fields from design doc Section 7, including `quote_anchor: str`
    - `embedding` stored separately (numpy array, not in Pydantic)
  - **File:** [src/models/contradiction.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/models/contradiction.py) `[NEW]`
    - `ContradictionType` enum: `DIRECT_NEGATION | QUANTITATIVE_CONFLICT | DIRECTION_REVERSAL | SCOPE_MISMATCH | TEMPORAL_SUPERSESSION | METHODOLOGICAL_CONFLICT`
    - `ContradictionPair` model: all fields from design doc
  - **File:** [src/models/report.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/models/report.py) `[NEW]`
    - `SynthesisReport` model: `summary`, `contradictions: list[ContradictionPair]`, `consensus_scores: dict`, `total_papers`, `total_claims`, `metadata`
  - **Acceptance:** All models instantiate without errors, JSON serialization round-trips correctly

### 0.5 Create Makefile

- [ ] **Task:** Convenience commands
  - **File:** [Makefile](file:///c:/Users/laaks/ZZ/Projects/P1/Makefile) `[NEW]`
  - Commands: `make install`, `make run QUERY="..."`, `make test`, `make eval-scifact`, `make lint`
  - **Acceptance:** `make install` sets up the virtual env and installs dependencies

---

## Phase 1 — Ingestion + Claim Extraction (Days 1–4)

> **Goal:** Given a research question, fetch abstracts from PubMed and extract validated, structured claims.
>
> **Exit criteria:** LLM extracts consistent, non-hallucinated claims from 10+ abstracts. Quote-anchor rejection rate < 20%.

---

### 1.1 PubMed Ingestion

#### 1.1.1 PubMed E-utilities Client

- [ ] **Task:** Build async PubMed fetcher
  - **File:** [src/ingestion/pubmed.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/ingestion/pubmed.py) `[NEW]`
  - **Functions:**
    ```python
    async def search_pubmed(query: str, max_results: int = 25) -> list[str]:
        """Search PubMed, return list of PMIDs.
        Uses ESearch: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi
        Params: db=pubmed, retmax=max_results, sort=relevance
        Returns: list of PMID strings
        """

    async def fetch_abstracts(pmids: list[str]) -> list[Paper]:
        """Fetch abstract + metadata for a batch of PMIDs.
        Uses EFetch: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi
        Params: db=pubmed, rettype=xml
        Parses XML to extract: title, authors, year, journal, abstract
        Returns: list of Paper objects
        """

    async def ingest_papers(query: str, max_results: int = 25) -> list[Paper]:
        """End-to-end: query → PMIDs → Papers.
        Applies rate limiting (3 req/sec via asyncio.Semaphore).
        Handles < min_papers gracefully (warn or abort per config).
        """
    ```
  - **Rate limiting:** `asyncio.Semaphore(settings.pubmed_concurrency)` wrapping each request
  - **XML parsing:** Use `xml.etree.ElementTree` (stdlib) — PubMed XML is simple
  - **Error handling:** Retry once on HTTP 429/500 with 2s backoff; skip individual papers that fail
  - **Acceptance:** `await ingest_papers("metformin cancer")` returns 15+ `Paper` objects with populated `abstract_text`

#### 1.1.2 PubMed Unit Tests

- [ ] **Task:** Test ingestion with mocked responses
  - **File:** [tests/test_pubmed.py](file:///c:/Users/laaks/ZZ/Projects/P1/tests/test_pubmed.py) `[NEW]`
  - Test cases:
    1. `test_search_returns_pmids` — mock ESearch response, verify PMID list
    2. `test_fetch_parses_xml` — mock EFetch XML, verify Paper fields populated
    3. `test_rate_limiting` — verify concurrent calls don't exceed 3/sec
    4. `test_few_results_warning` — query returning < 5 papers raises appropriate warning
  - **Fixtures:** [tests/fixtures/sample_abstracts.json](file:///c:/Users/laaks/ZZ/Projects/P1/tests/fixtures/sample_abstracts.json) — 10 real PubMed abstracts on "metformin cancer"
  - **Acceptance:** `pytest tests/test_pubmed.py` — all pass

#### 1.1.3 Manual Validation: Fetch Real Abstracts

- [ ] **Task:** Run ingestion on 3 different research questions, inspect results
  - Queries: "metformin cancer risk", "intermittent fasting insulin sensitivity", "SSRI depression adolescents"
  - Verify: abstracts are complete, metadata is accurate, no truncation
  - Save sample outputs to `data/sample_runs/` for later testing
  - **Acceptance:** All 3 queries return 15+ papers with full abstracts

---

### 1.2 LLM Provider Abstraction

#### 1.2.1 Abstract LLM Interface

- [ ] **Task:** Create a provider-agnostic LLM interface
  - **File:** [src/llm/base.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/llm/base.py) `[NEW]`
  - **Interface:**
    ```python
    class LLMProvider(ABC):
        @abstractmethod
        async def generate_structured(
            self,
            prompt: str,
            response_schema: type[BaseModel],
            temperature: float = 0.1,
        ) -> BaseModel:
            """Generate structured output validated against a Pydantic schema."""

        @abstractmethod
        async def generate_text(
            self,
            prompt: str,
            temperature: float = 0.3,
        ) -> str:
            """Generate free-form text."""
    ```
  - **Acceptance:** Interface is importable and subclassable

#### 1.2.2 Gemini Client

- [ ] **Task:** Implement Gemini provider
  - **File:** [src/llm/gemini.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/llm/gemini.py) `[NEW]`
  - Uses `google-genai` SDK
  - Implements `generate_structured` using Gemini's JSON mode / structured output
  - Handles rate limits with retry + exponential backoff
  - Supports model switching (`gemini-2.5-flash` for extraction, `gemini-2.5-pro` for judge)
  - **Acceptance:** `await gemini.generate_structured(prompt, ClaimExtractionResponse)` returns valid Pydantic object

#### 1.2.3 OpenAI Client (Optional, same interface)

- [ ] **Task:** Implement OpenAI provider as a swap-in alternative
  - **File:** [src/llm/openai.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/llm/openai.py) `[NEW]`
  - Uses `openai` SDK with `response_format={"type": "json_schema", ...}`
  - Same interface as Gemini client
  - **Acceptance:** Same test passes with `llm_provider = "openai"` in config

#### 1.2.4 Provider Factory

- [ ] **Task:** Factory function to instantiate the configured provider
  - Add to [src/llm/__init__.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/llm/__init__.py):
    ```python
    def get_llm(model: str | None = None) -> LLMProvider:
        provider = settings.llm_provider
        if provider == "gemini":
            return GeminiProvider(model or settings.extraction_model)
        elif provider == "openai":
            return OpenAIProvider(model or settings.extraction_model)
    ```
  - **Acceptance:** `get_llm()` returns correct provider based on `.env`

---

### 1.3 Claim Extraction Pipeline

#### 1.3.1 Extraction Prompt Design

- [ ] **Task:** Create the claim extraction prompt with few-shot examples
  - **File:** [src/extraction/prompts/extraction_prompt.txt](file:///c:/Users/laaks/ZZ/Projects/P1/src/extraction/prompts/extraction_prompt.txt) `[NEW]`
    - System prompt from design doc Section 15
    - Must include: rules for what constitutes a claim, the structured output schema, and explicit negatives ("do NOT extract methodology, background, or future work")
  - **File:** [src/extraction/prompts/extraction_few_shot.json](file:///c:/Users/laaks/ZZ/Projects/P1/src/extraction/prompts/extraction_few_shot.json) `[NEW]`
    - 3 diverse examples:
      1. A biomedical RCT abstract → 4 claims with clear polarity and population
      2. An observational study → 3 claims including a NEUTRAL polarity ("no significant effect")
      3. A mechanistic in-vitro study → 3 claims with MECHANISTIC type
    - Each example includes correct `quote_anchor` from the abstract text
  - **Acceptance:** Prompt renders as a coherent, unambiguous instruction when combined with few-shots

#### 1.3.2 Claim Extraction Response Schema

- [ ] **Task:** Define the Pydantic model for the LLM's structured output
  - Add to [src/models/claim.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/models/claim.py):
    ```python
    class ExtractedClaim(BaseModel):
        """Single claim as returned by the LLM (before verification)."""
        text: str
        polarity: Polarity
        population: str
        context: str
        quote_anchor: str
        claim_type: ClaimType
        study_design: StudyDesign
        entities: list[ExtractedEntity]

    class ClaimExtractionResponse(BaseModel):
        """LLM's complete response for one abstract."""
        claims: list[ExtractedClaim]
    ```
  - **Acceptance:** Schema is compatible with Gemini/OpenAI structured output mode

#### 1.3.3 Claim Extractor

- [ ] **Task:** Implement the core extraction function
  - **File:** [src/extraction/claim_extractor.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/extraction/claim_extractor.py) `[NEW]`
  - **Functions:**
    ```python
    async def extract_claims_from_paper(
        paper: Paper,
        llm: LLMProvider,
    ) -> list[ExtractedClaim]:
        """Extract claims from a single paper's abstract.
        1. Load prompt template + few-shot examples
        2. Format prompt with abstract text
        3. Call LLM with structured output
        4. Validate response (cap at claims_per_abstract_cap)
        5. Return list of ExtractedClaim
        Handles: malformed JSON (retry once), timeout, empty response
        """

    async def extract_claims_batch(
        papers: list[Paper],
        llm: LLMProvider,
    ) -> dict[str, list[ExtractedClaim]]:
        """Extract claims from all papers concurrently.
        Uses asyncio.Semaphore(settings.llm_concurrency) for rate limiting.
        Returns: {pmid: [claims]} mapping
        Logs: papers that failed extraction, papers with 0 claims
        """
    ```
  - **Acceptance:** Given 10 abstracts, returns 30–50 claims total, each with populated fields

#### 1.3.4 Quote-Anchor Verifier

- [ ] **Task:** Implement fuzzy matching verification for extracted claims
  - **File:** [src/extraction/quote_verifier.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/extraction/quote_verifier.py) `[NEW]`
  - **Functions:**
    ```python
    def normalize_text(text: str) -> str:
        """Lowercase, strip punctuation, collapse whitespace."""

    def verify_quote_anchor(
        quote_anchor: str,
        source_text: str,
        pass_threshold: float = 85.0,
        flag_threshold: float = 70.0,
    ) -> tuple[Literal["PASS", "FLAG", "REJECT"], float]:
        """Verify a quote anchor against source text.
        Uses rapidfuzz.fuzz.partial_ratio.
        Returns: (status, score)
        """

    def verify_and_filter_claims(
        claims: list[ExtractedClaim],
        source_text: str,
    ) -> tuple[list[Claim], VerificationStats]:
        """Verify all claims for a paper.
        - PASS: confidence_score unchanged
        - FLAG: confidence_score *= 0.5
        - REJECT: claim discarded
        Returns: (verified_claims, stats)
        Stats: {passed: int, flagged: int, rejected: int, rejection_rate: float}
        """
    ```
  - **Acceptance:** Given a claim with a correct quote → PASS; fabricated quote → REJECT; paraphrased quote → FLAG

#### 1.3.5 Extraction Unit Tests

- [ ] **Task:** Test extraction + verification
  - **File:** [tests/test_claim_extractor.py](file:///c:/Users/laaks/ZZ/Projects/P1/tests/test_claim_extractor.py) `[NEW]`
  - Test cases:
    1. `test_extraction_returns_valid_claims` — mock LLM, verify Pydantic validation
    2. `test_cap_at_max_claims` — LLM returns 15 claims, verify only 7 kept
    3. `test_retry_on_malformed_json` — first LLM call returns bad JSON, second succeeds
    4. `test_empty_abstract_returns_zero_claims` — graceful handling
  - **File:** [tests/test_quote_verifier.py](file:///c:/Users/laaks/ZZ/Projects/P1/tests/test_quote_verifier.py) `[NEW]`
  - Test cases:
    1. `test_exact_match_passes` — verbatim quote → PASS with score ≥ 85
    2. `test_minor_variation_flags` — slight paraphrase → FLAG with 70 ≤ score < 85
    3. `test_fabricated_quote_rejects` — unrelated text → REJECT with score < 70
    4. `test_normalization` — different casing/punctuation still matches
  - **Acceptance:** `pytest tests/test_claim_extractor.py tests/test_quote_verifier.py` — all pass

---

### 1.4 Storage Layer

#### 1.4.1 SQLite Schema + CRUD

- [ ] **Task:** Design and implement the database layer
  - **File:** [src/storage/database.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/storage/database.py) `[NEW]`
  - **Schema:**
    ```sql
    CREATE TABLE papers (
        pmid TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        authors TEXT NOT NULL,     -- JSON array
        year INTEGER NOT NULL,
        journal TEXT,
        abstract_text TEXT NOT NULL,
        full_text TEXT,
        doi TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE claims (
        id TEXT PRIMARY KEY,       -- UUID
        paper_id TEXT NOT NULL REFERENCES papers(pmid),
        text TEXT NOT NULL,
        normalized_text TEXT,
        polarity TEXT NOT NULL,
        population TEXT,
        context TEXT,
        quote_anchor TEXT NOT NULL,
        claim_type TEXT NOT NULL,
        study_design TEXT,
        confidence_score REAL NOT NULL,
        is_primary_finding BOOLEAN DEFAULT TRUE,
        sample_size INTEGER,
        entities TEXT,             -- JSON array of Entity objects
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE contradictions (
        id TEXT PRIMARY KEY,
        claim_a_id TEXT NOT NULL REFERENCES claims(id),
        claim_b_id TEXT NOT NULL REFERENCES claims(id),
        contradiction_score REAL NOT NULL,
        contradiction_type TEXT NOT NULL,
        explanation TEXT,
        scope_note TEXT,
        temporal_resolution TEXT,
        is_genuine BOOLEAN NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE pipeline_runs (
        id TEXT PRIMARY KEY,
        query TEXT NOT NULL,
        status TEXT NOT NULL,       -- RUNNING | COMPLETED | FAILED
        papers_fetched INTEGER,
        claims_extracted INTEGER,
        contradictions_found INTEGER,
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        error_message TEXT
    );
    ```
  - **Functions:** `init_db()`, `save_papers()`, `save_claims()`, `save_contradictions()`, `save_pipeline_run()`, `get_claims_for_run()`, `get_contradictions_for_run()`
  - **Acceptance:** Can round-trip Paper → DB → Paper, Claim → DB → Claim

---

### 1.5 Phase 1 Integration + Checkpoint

#### 1.5.1 End-to-End: Query → Claims in DB

- [ ] **Task:** Wire ingestion → extraction → verification → storage
  - **File:** [src/pipeline.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/pipeline.py) `[NEW]` (partial — Phase 1 stages only)
  - **Function:**
    ```python
    async def run_ingestion_and_extraction(query: str) -> PipelineState:
        """Phase 1 pipeline: query → papers → claims → DB.
        Returns PipelineState with papers, claims, and verification stats.
        """
    ```
  - **Acceptance:** `python -m src.pipeline "metformin cancer"` fetches papers, extracts claims, stores in SQLite

#### 1.5.2 Manual Checkpoint: Validate Extraction Quality

- [ ] **Task:** Manually inspect extraction output for 10 abstracts
  - Pick 10 abstracts from the "metformin cancer" run
  - For each: read the abstract, read extracted claims, verify:
    1. Are all claims real assertions from the text? (no hallucinations)
    2. Are key findings captured? (no critical omissions)
    3. Are quote_anchors verifiable in the source? (no fabrications)
    4. Is polarity correct? (POSITIVE/NEGATIVE/NEUTRAL)
    5. Is population extracted? (not empty or generic)
  - **Create:** [tests/fixtures/expected_claims.json](file:///c:/Users/laaks/ZZ/Projects/P1/tests/fixtures/expected_claims.json) — hand-annotated expected claims for 5 abstracts
  - **Acceptance criteria:**
    - Extraction precision ≥ 85% (of extracted claims, ≥ 85% are real)
    - Quote-anchor rejection rate < 20%
    - Zero complete hallucinations (claims with no basis in the text)

> [!CAUTION]
> **GO/NO-GO:** If extraction quality does not meet the above criteria, STOP. Iterate on the extraction prompt (Section 15 of design doc). Do not proceed to Phase 2 until claims are reliable.

---

## Phase 2 — Contradiction Detection (Days 5–8)

> **Goal:** Detect contradictory claim pairs using embedding similarity → NLI scoring → LLM judge pipeline.
>
> **Exit criteria:** System finds ≥ 3 genuine contradictions in a known-contradictory corpus. SciFact precision ≥ 70%.

---

### 2.1 Embedding Pipeline

#### 2.1.1 Sentence Transformer Wrapper

- [ ] **Task:** Wrap sentence-transformers for claim embedding
  - **File:** [src/detection/embedder.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/detection/embedder.py) `[NEW]`
  - **Functions:**
    ```python
    class ClaimEmbedder:
        def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
            self.model = SentenceTransformer(model_name)

        def embed_claims(self, claims: list[Claim]) -> np.ndarray:
            """Batch encode claim texts. Returns (n_claims, 384) array."""
            texts = [c.text for c in claims]
            return self.model.encode(texts, normalize_embeddings=True)

        def embed_single(self, text: str) -> np.ndarray:
            """Embed a single text string."""
    ```
  - Note: `all-MiniLM-L6-v2` outputs 384-dim vectors (not 768 — update design doc's note)
  - **Acceptance:** 125 claims embedded in < 3 seconds

#### 2.1.2 FAISS Index

- [ ] **Task:** Build and query FAISS index for candidate pair retrieval
  - **File:** [src/detection/faiss_index.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/detection/faiss_index.py) `[NEW]`
  - **Functions:**
    ```python
    class ClaimIndex:
        def build_index(self, embeddings: np.ndarray) -> None:
            """Build FAISS IndexFlatIP (inner product on normalized vectors = cosine)."""

        def find_candidate_pairs(
            self,
            embeddings: np.ndarray,
            claims: list[Claim],
            top_k: int = 10,
            min_similarity: float = 0.3,
        ) -> list[tuple[int, int, float]]:
            """For each claim, find top-K most similar claims (excluding self and same-paper).
            Returns: list of (idx_a, idx_b, similarity_score) tuples, deduplicated.
            """

        def save(self, path: str) -> None
        def load(self, path: str) -> None
    ```
  - **Key filter:** Exclude pairs from the same paper (claims within one abstract aren't contradictions — they're context)
  - **Acceptance:** Given 125 claims, returns ~50–100 candidate pairs in < 0.5 seconds

---

### 2.2 NLI Scoring

#### 2.2.1 DeBERTa NLI Cross-Encoder

- [ ] **Task:** Wrap the NLI model for contradiction scoring
  - **File:** [src/detection/nli_scorer.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/detection/nli_scorer.py) `[NEW]`
  - **Functions:**
    ```python
    class NLIScorer:
        def __init__(self, model_name: str = "cross-encoder/nli-deberta-v3-large"):
            self.model = CrossEncoder(model_name)

        def score_pairs(
            self,
            pairs: list[tuple[str, str]],
        ) -> list[NLIResult]:
            """Score claim pairs for entailment/neutral/contradiction.
            Returns list of NLIResult(entailment, neutral, contradiction scores).
            """

        def filter_contradictions(
            self,
            pairs: list[tuple[int, int, float]],  # from FAISS
            claims: list[Claim],
            threshold: float = 0.7,
        ) -> list[tuple[int, int, float, float]]:
            """Run NLI on candidate pairs, return those with contradiction score ≥ threshold.
            Returns: (idx_a, idx_b, similarity_score, contradiction_score)
            """
    ```
  - **Acceptance:** Given 50 candidate pairs, returns ~10–20 with contradiction score ≥ 0.7, in < 15 seconds on CPU

#### 2.2.2 NLI Unit Tests

- [ ] **Task:** Test NLI scoring with known examples
  - **File:** [tests/test_nli_scorer.py](file:///c:/Users/laaks/ZZ/Projects/P1/tests/test_nli_scorer.py) `[NEW]`
  - Test cases:
    1. `test_direct_contradiction` — "X causes Y" vs "X does not cause Y" → high contradiction score
    2. `test_entailment` — "X causes Y" vs "X leads to Y" → high entailment score
    3. `test_unrelated` — "X causes Y" vs "A is found in B" → high neutral score
  - **Acceptance:** All pass, scores are in expected ranges

---

### 2.3 LLM Judge

#### 2.3.1 Contradiction Judge Prompt

- [ ] **Task:** Create the judge prompt from design doc Section 15
  - **File:** [src/extraction/prompts/judge_prompt.txt](file:///c:/Users/laaks/ZZ/Projects/P1/src/extraction/prompts/judge_prompt.txt) `[NEW]`
  - Must include: scope mismatch examples, structured output schema, explicit instruction that "different populations ≠ contradiction"
  - **Acceptance:** Prompt is clear, includes 2 few-shot examples (one genuine contradiction, one scope mismatch)

#### 2.3.2 LLM Judge Implementation

- [ ] **Task:** Implement the LLM-based scope and genuineness judge
  - **File:** [src/detection/llm_judge.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/detection/llm_judge.py) `[NEW]`
  - **Response schema:**
    ```python
    class JudgeResponse(BaseModel):
        is_same_topic: bool
        is_contradiction: bool
        is_genuine: bool
        contradiction_type: ContradictionType
        explanation: str
        scope_note: str
    ```
  - **Function:**
    ```python
    async def judge_contradiction_pair(
        claim_a: Claim,
        claim_b: Claim,
        llm: LLMProvider,
    ) -> ContradictionPair | None:
        """Judge a single candidate pair.
        Returns ContradictionPair if genuine, None if not a contradiction.
        Uses the expensive/smart model (gemini-2.5-pro).
        """

    async def judge_batch(
        candidates: list[tuple[Claim, Claim, float]],
        llm: LLMProvider,
    ) -> list[ContradictionPair]:
        """Judge all candidates concurrently.
        Uses asyncio.Semaphore for rate limiting.
        """
    ```
  - **Acceptance:** Given a scope mismatch pair (mice vs humans), returns `is_genuine = False`

---

### 2.4 Contradiction Detection Orchestrator

#### 2.4.1 Full Detection Pipeline

- [ ] **Task:** Orchestrate embedding → FAISS → NLI → judge
  - **File:** [src/detection/contradiction_detector.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/detection/contradiction_detector.py) `[NEW]`
  - **Function:**
    ```python
    async def detect_contradictions(
        claims: list[Claim],
    ) -> list[ContradictionPair]:
        """Full detection pipeline:
        1. Embed all claims (local, batch)
        2. Build FAISS index, retrieve top-K pairs (exclude same-paper)
        3. Score pairs with NLI model (local, batch)
        4. Filter by contradiction threshold
        5. Send ambiguous pairs to LLM judge (async, concurrent)
        6. Rank by contradiction_score, return top N
        """
    ```
  - **Acceptance:** Given 100+ claims, returns 5–15 `ContradictionPair` objects with `is_genuine` annotations

#### 2.4.2 Detection Integration Test

- [ ] **Task:** Test full detection on curated claim set
  - **File:** [tests/test_contradiction_detector.py](file:///c:/Users/laaks/ZZ/Projects/P1/tests/test_contradiction_detector.py) `[NEW]`
  - Create fixture with 10 claims: 2 genuine contradictions, 1 scope mismatch, 7 unrelated
  - Verify: both genuine contradictions detected, scope mismatch flagged as `is_genuine = False`
  - **Acceptance:** Test passes with correct classification

---

### 2.5 Rich CLI Output

#### 2.5.1 Terminal Report

- [ ] **Task:** Build a beautiful CLI report using `rich`
  - **File:** [src/presentation/cli_report.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/presentation/cli_report.py) `[NEW]`
  - **Sections displayed:**
    1. Header: "Research Synthesis & Contradiction Engine" + query
    2. Stats panel: papers ingested, claims extracted, contradictions found, time elapsed
    3. Contradiction table: ranked pairs with claim texts, authors/years, score, type
    4. For each top contradiction: side-by-side claim display with quote anchors
    5. Grounded summary paragraph (Phase 3 — placeholder for now)
    6. Footer: cost estimate, data sources
  - Use: `rich.console`, `rich.table`, `rich.panel`, `rich.columns`, `rich.progress` (for pipeline progress)
  - **Acceptance:** Running the CLI produces a visually impressive terminal output that a recruiter would be impressed by

#### 2.5.2 JSON Export

- [ ] **Task:** Export results as structured JSON
  - **File:** [src/presentation/json_export.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/presentation/json_export.py) `[NEW]`
  - Exports full `SynthesisReport` as JSON to `data/sample_runs/{query_slug}_{timestamp}.json`
  - **Acceptance:** JSON file is valid and contains all contradiction pairs with citations

---

### 2.6 CLI Entrypoint

- [ ] **Task:** Create the main CLI using `typer`
  - **File:** [src/main.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/main.py) `[NEW]`
  - **Commands:**
    ```python
    @app.command()
    def analyze(
        query: str = typer.Argument(..., help="Research question to analyze"),
        max_papers: int = typer.Option(25, help="Maximum papers to fetch"),
        output_json: bool = typer.Option(False, help="Also save JSON output"),
    ):
        """Analyze a research question for contradictory claims across papers."""
    ```
  - Shows `rich` progress bar during pipeline stages
  - **Acceptance:** `python -m src.main "Does metformin reduce cancer risk?"` runs full pipeline and displays report

---

### 2.7 Phase 2 Checkpoint: SciFact Benchmark

- [ ] **Task:** Evaluate contradiction detection on SciFact
  - **File:** [evaluation/scifact_eval.py](file:///c:/Users/laaks/ZZ/Projects/P1/evaluation/scifact_eval.py) `[NEW]`
  - Download SciFact dataset to `data/scifact/`
  - Run NLI stage on SciFact's claim-evidence pairs
  - Compute precision and recall for REFUTES labels
  - Save results to `evaluation/results/scifact_results.json`
  - **Acceptance:** Precision ≥ 70%, Recall ≥ 55% on REFUTES classification

> [!CAUTION]
> **GO/NO-GO:** If SciFact precision < 60%, iterate on NLI threshold and/or LLM judge prompt. If system finds 0 genuine contradictions on a real query, the pipeline has a fundamental issue.

---

## Phase 3 — Graph + Synthesis + Entity Normalization (Days 9–12)

> **Goal:** Build the claim-evidence graph, add entity normalization, generate citation-grounded summaries, and add full-text ingestion.
>
> **Exit criteria:** Grounded summary is accurate, every citation verifiable, and entity synonyms are resolved.

---

### 3.1 Claim-Evidence Graph

#### 3.1.1 Graph Construction

- [ ] **Task:** Build NetworkX graph from claims and contradictions
  - **File:** [src/graph/claim_graph.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/graph/claim_graph.py) `[NEW]`
  - **Functions:**
    ```python
    def build_claim_graph(
        claims: list[Claim],
        contradictions: list[ContradictionPair],
        papers: list[Paper],
    ) -> nx.DiGraph:
        """Build a directed graph:
        - Paper nodes (metadata)
        - Claim nodes (text, polarity, confidence)
        - Entity nodes (canonical_id, type)
        - Edges: EXTRACTED_FROM (paper→claim), CONTRADICTS (claim↔claim),
                 MENTIONS (claim→entity), SUPERSEDES (newer claim→older claim)
        """

    def compute_consensus_scores(graph: nx.DiGraph) -> dict[str, float]:
        """Per-entity pair: what fraction of claims support vs. contradict a relationship."""
    ```
  - **Acceptance:** Graph with 100+ nodes, correctly typed edges, exportable

#### 3.1.2 Graph Export

- [ ] **Task:** Export graph to JSON and GEXF for visualization
  - **File:** [src/graph/graph_export.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/graph/graph_export.py) `[NEW]`
  - Export to: JSON (for Cytoscape.js), GEXF (for Gephi, debug)
  - **Acceptance:** Exported JSON loadable in Cytoscape.js

---

### 3.2 Entity Normalization

#### 3.2.1 Entity Normalizer

- [ ] **Task:** Normalize entity mentions to canonical IDs
  - **File:** [src/entity/normalizer.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/entity/normalizer.py) `[NEW]`
  - **Strategy:**
    1. Run scispaCy NER (`en_core_sci_sm`) on claim text to identify entity spans
    2. Link to UMLS/MeSH IDs using scispaCy's `EntityLinker`
    3. Fallback: for entities not found in UMLS, use LLM to suggest canonical name
  - **Functions:**
    ```python
    class EntityNormalizer:
        def normalize_entities(self, claims: list[Claim]) -> list[Claim]:
            """Update claim.entities with canonical_ids.
            Resolves synonyms: aspirin/ASA/acetylsalicylic acid → MeSH:D001241
            """
    ```
  - **Acceptance:** "aspirin" and "acetylsalicylic acid" in different claims resolve to same canonical ID

---

### 3.3 Synthesis Generator

#### 3.3.1 Citation-Grounded Report Generator

- [ ] **Task:** Generate a narrative synthesis from the claim graph
  - **File:** [src/synthesis/report_generator.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/synthesis/report_generator.py) `[NEW]`
  - **Strategy:** RAG over claims, NOT raw paper text
    1. Collect top contradictions, supporting claims, and consensus claims
    2. Format as a structured context for the LLM
    3. Prompt LLM to write a synthesis paragraph where every sentence references [Author, Year]
    4. Post-validate: every [Author, Year] in the output must match a real paper in the corpus
  - **Functions:**
    ```python
    async def generate_synthesis_report(
        contradictions: list[ContradictionPair],
        claims: list[Claim],
        papers: list[Paper],
        llm: LLMProvider,
    ) -> SynthesisReport:
        """Generate a citation-grounded synthesis report.
        Returns SynthesisReport with verified citations.
        """
    ```
  - **Citation validation:** Parse all `[Author, Year]` references from the generated text; verify each exists in the paper corpus. Remove or flag any that don't match.
  - **Acceptance:** Generated summary contains 5+ inline citations, all verifiable

---

### 3.4 PubMed Central Full-Text Ingestion

#### 3.4.1 PMC XML Parser

- [ ] **Task:** Add full-text ingestion via PubMed Central Open Access XML
  - **File:** [src/ingestion/pmc_xml.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/ingestion/pmc_xml.py) `[NEW]`
  - Use PMC OA API: `https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi`
  - Parse XML sections: Introduction, Methods, Results, Discussion
  - **Functions:**
    ```python
    async def fetch_full_text(pmid: str) -> str | None:
        """Fetch full text from PMC OA if available. Returns None if not open-access."""

    def parse_pmc_xml(xml_content: str) -> dict[str, str]:
        """Parse PMC XML into sections: {section_name: text}."""
    ```
  - Integrate into ingestion pipeline: try PMC first, fall back to abstract-only
  - **Acceptance:** For a known OA paper, returns full text parsed into sections

---

### 3.5 Phase 3 Integration + Checkpoint

- [ ] **Task:** End-to-end run with graph, synthesis, and entity normalization
  - Update [src/pipeline.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/pipeline.py) with full pipeline
  - Run on: "Does intermittent fasting improve metabolic health?"
  - Verify:
    1. Synthesis report has ≥ 5 inline citations, all verifiable
    2. Entity normalization resolves ≥ 1 synonym pair
    3. Graph exports correctly to JSON
    4. No hallucinated citations in the summary
  - **Acceptance:** Full pipeline runs end-to-end, synthesis is factually accurate

> [!CAUTION]
> **GO/NO-GO:** If generated summary contains hallucinated citations, iterate on the synthesis prompt. Add chain-of-citation: require the LLM to first list the claims it will cite, then write the paragraph.

---

## Phase 4 — Web UI + Demo (Days 13–17)

> **Goal:** Build a web interface with interactive claim graph and contradiction report.
>
> **Exit criteria:** A non-technical user can enter a research question and explore contradictions visually.

---

### 4.1 FastAPI Backend

#### 4.1.1 API Application

- [ ] **Task:** Wrap the pipeline in a REST API
  - **File:** [api/app.py](file:///c:/Users/laaks/ZZ/Projects/P1/api/app.py) `[NEW]`
  - **Endpoints:**
    ```
    POST /api/analyze      — Start analysis (returns run_id)
    GET  /api/status/{id}  — Check pipeline status
    GET  /api/results/{id} — Get full results (contradictions, graph, summary)
    GET  /api/claims/{id}  — Get all claims for a run
    GET  /api/graph/{id}   — Get graph JSON for Cytoscape.js
    WS   /api/ws/{id}      — WebSocket for real-time progress updates
    ```
  - **File:** [api/schemas.py](file:///c:/Users/laaks/ZZ/Projects/P1/api/schemas.py) `[NEW]` — request/response Pydantic models
  - **File:** [api/routes/analysis.py](file:///c:/Users/laaks/ZZ/Projects/P1/api/routes/analysis.py) `[NEW]`
  - **File:** [api/routes/results.py](file:///c:/Users/laaks/ZZ/Projects/P1/api/routes/results.py) `[NEW]`
  - Pipeline runs as a background task; status polled or streamed via WebSocket
  - **Acceptance:** `POST /api/analyze` with `{"query": "metformin cancer"}` starts pipeline, `/api/results/{id}` returns full JSON

#### 4.1.2 Pre-loaded Demo Results

- [ ] **Task:** Cache results for 2–3 compelling topics for instant demo
  - Run full pipeline on:
    1. "Does metformin reduce cancer risk?"
    2. "Does intermittent fasting improve insulin sensitivity?"
    3. "Do SSRIs increase suicide risk in adolescents?"
  - Save to `data/sample_runs/` and serve via a `/api/demo/{topic}` endpoint
  - **Acceptance:** Demo results load in < 1 second

---

### 4.2 Next.js Frontend

#### 4.2.1 Initialize Next.js App

- [ ] **Task:** Scaffold Next.js application
  - `npx -y create-next-app@latest ./frontend --typescript --tailwind --eslint --app --no-src-dir --import-alias "@/*"`
  - Install: `cytoscape`, `cytoscape-fcose` (layout), `@types/cytoscape`
  - **Acceptance:** `npm run dev` in `frontend/` serves on localhost:3000

#### 4.2.2 Landing Page

- [ ] **Task:** Build the query input page
  - Search bar with research question input
  - Pre-loaded topic buttons for instant demo
  - Brief explainer of what the system does
  - **Acceptance:** User can enter a query or click a demo topic

#### 4.2.3 Results Page — Contradiction Report

- [ ] **Task:** Build the main results view
  - **Components:**
    1. **Summary Panel** — Grounded synthesis text with clickable [Author, Year] citations
    2. **Contradiction Cards** — Each card shows: Claim A vs Claim B, score, type badge, explanation, source papers
    3. **Stats Bar** — Papers analyzed, claims extracted, contradictions found, time elapsed
    4. **Filter/Sort** — By contradiction type, by score, by genuineness
  - **Acceptance:** All contradictions display with correct citations and type badges

#### 4.2.4 Results Page — Interactive Claim Graph

- [ ] **Task:** Build Cytoscape.js graph visualization
  - **Node types:** Claims (color by polarity), Papers (gray), Entities (by type)
  - **Edge types:** CONTRADICTS (red, dashed), SUPPORTS (green), EXTRACTED_FROM (gray, thin)
  - **Interactions:**
    - Click node → side panel shows full claim text, quote anchor, paper metadata
    - Hover edge → tooltip shows contradiction explanation
    - Filter: show only contradictions, show only a specific entity's subgraph
  - **Layout:** `fcose` (force-directed, compound) for readable clusters
  - **Acceptance:** Graph renders with 50+ nodes, is interactive, and loads in < 2 seconds

#### 4.2.5 Claim Detail Panel

- [ ] **Task:** Side panel shown on node click
  - Shows: full claim text, quote anchor (highlighted), paper title, authors, year, journal, DOI link
  - For contradiction edges: shows both claims side-by-side with explanation
  - **Acceptance:** Clicking a claim node reveals its full metadata and source

---

### 4.3 Phase 4 Polish

- [ ] **Task:** UI polish and responsiveness
  - Dark mode theme (premium feel)
  - Loading states with skeleton screens
  - Mobile-responsive layout
  - Error states (no contradictions found, API failure)
  - **Acceptance:** App looks premium, no broken layouts, handles edge cases gracefully

---

## Phase 5 — Portfolio Polish (Days 18–20)

> **Goal:** Make this portfolio-ready: README, demo video, Docker, deployment.

---

### 5.1 README

- [ ] **Task:** Write a portfolio-grade README
  - **File:** [README.md](file:///c:/Users/laaks/ZZ/Projects/P1/README.md) `[NEW]`
  - **Sections:**
    1. Hero: project name, tagline, screenshot/GIF
    2. What it does (2 paragraphs, non-technical)
    3. Architecture diagram (embedded image from `docs/architecture.png`)
    4. Key technical decisions (claim-as-first-class-object, two-model strategy, quote-anchor verification)
    5. Benchmark results (SciFact precision/recall table)
    6. Cost analysis ($0.17/run breakdown)
    7. Quick start (`git clone`, `pip install`, `python -m src.main "..."`)
    8. Tech stack table
    9. Roadmap (what's next)
  - **Acceptance:** A senior engineer reads it in 2 minutes and understands the system's value and sophistication

### 5.2 Architecture Diagram

- [ ] **Task:** Create a clean architecture diagram
  - **File:** [docs/architecture.png](file:///c:/Users/laaks/ZZ/Projects/P1/docs/architecture.png) `[NEW]`
  - Based on Section 13 of design doc
  - Clean, professional style (draw.io or Excalidraw)
  - **Acceptance:** Diagram is clear, labeled, and embeddable in README

### 5.3 Demo Video

- [ ] **Task:** Record a 2-minute demo
  - **File:** [docs/demo.gif](file:///c:/Users/laaks/ZZ/Projects/P1/docs/demo.gif) `[NEW]`
  - Options: `asciinema` for terminal recording, Loom for full-screen with narration
  - Show: enter query → progress bar → contradiction report → graph visualization
  - **Acceptance:** Demo is under 2 minutes and shows the full workflow

### 5.4 Dockerfile

- [ ] **Task:** Containerize the application
  - **File:** [Dockerfile](file:///c:/Users/laaks/ZZ/Projects/P1/Dockerfile) `[NEW]`
  - Multi-stage build: dependencies → application
  - Include model downloads in build stage (sentence-transformers, DeBERTa)
  - Expose port 8000 (FastAPI) and 3000 (Next.js) — or use a combined entrypoint
  - **Acceptance:** `docker build -t rsce . && docker run -p 8000:8000 rsce` works

### 5.5 Deployment

- [ ] **Task:** Deploy to free-tier hosting
  - Backend: Railway or Fly.io (free tier — FastAPI + SQLite)
  - Frontend: Vercel (free tier — Next.js)
  - Note: Local models (sentence-transformers, DeBERTa) may require a machine with ~2GB RAM
  - **Acceptance:** Live URL accessible, demo topics load in < 5 seconds

### 5.6 Temporal Analysis (Stretch)

- [ ] **Task:** Add temporal supersession detection
  - When two claims contradict, check if one is significantly newer (≥ 3 years)
  - If the newer claim comes from a study with larger sample size or stronger design (meta-analysis > RCT > observational), mark as `TEMPORAL_SUPERSESSION`
  - Update `ContradictionPair.temporal_resolution` with explanation
  - **Acceptance:** At least 1 contradiction pair in the demo has temporal resolution annotation

---

## Verification Plan

### Automated Tests

```bash
# Run all unit tests
make test
# equivalently: pytest tests/ -v

# Run SciFact benchmark
make eval-scifact
# equivalently: python evaluation/scifact_eval.py

# Lint
make lint
# equivalently: ruff check src/ tests/
```

### Manual Verification

| Check | How | When |
|---|---|---|
| Extraction quality | Read 10 abstracts + their extracted claims | End of Phase 1 |
| Quote-anchor verification | Check rejection rate < 20% | End of Phase 1 |
| Contradiction genuineness | Manually verify top 10 contradictions | End of Phase 2 |
| SciFact benchmark | Run eval script, check P/R | End of Phase 2 |
| Citation fidelity | Verify every [Author, Year] in synthesis | End of Phase 3 |
| End-to-end demo | Run 3 topics, check output quality | End of Phase 4 |
| Recruiter test | Have a non-expert run it and react | End of Phase 5 |

### Target Metrics

| Metric | Target | Measured when |
|---|---|---|
| Claim extraction precision | ≥ 85% | Phase 1 checkpoint |
| Quote-anchor rejection rate | < 20% | Phase 1 checkpoint |
| SciFact contradiction precision | ≥ 70% | Phase 2 checkpoint |
| SciFact contradiction recall | ≥ 55% | Phase 2 checkpoint |
| Citation fidelity | 100% | Phase 3 checkpoint |
| False contradiction rate | ≤ 15% | Phase 3 checkpoint |
| End-to-end latency (25 papers) | < 2 minutes | Phase 2 onward |
| Cost per run | < $0.50 | Phase 2 onward |
