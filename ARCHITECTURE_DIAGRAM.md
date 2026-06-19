# Research Synthesis & Contradiction Engine (RSCE) - Architecture Diagram

## System Overview

RSCE is an AI-powered meta-research platform that ingests clinical literature, extracts claims with verbatim quote-level grounding, and maps conflicting findings into an interactive, visual claim-evidence network graph.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACE LAYER                                │
│  ┌──────────────────┐                    ┌──────────────────┐                  │
│  │   Next.js 15+    │                    │   CLI (Typer)    │                  │
│  │   Frontend App   │                    │   Terminal UI    │                  │
│  │  (localhost:3000)│                    │  (src/main.py)   │                  │
│  └────────┬─────────┘                    └────────┬─────────┘                  │
│           │                                       │                            │
│           │ HTTP/REST + WebSocket                 │ Direct Function Call      │
│           ▼                                       ▼                            │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              API LAYER (FastAPI)                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                         api/app.py                                        │  │
│  │  - CORS Middleware                                                        │  │
│  │  - Database Initialization                                                 │  │
│  │  - Route Mounting                                                          │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│           │                                                                       │
│           ├──► POST /api/analyze (api/routes/analysis.py)                        │
│           │    - Start background pipeline task                                 │
│           │    - Return run_id immediately                                      │
│           │                                                                       │
│           ├──► GET /api/status/{run_id} (api/routes/analysis.py)                │
│           │    - Retrieve pipeline status from SQLite                           │
│           │                                                                       │
│           ├──► WebSocket /api/ws/{run_id} (api/routes/analysis.py)              │
│           │    - Real-time progress updates                                      │
│           │                                                                       │
│           └──► GET /api/results/{run_id} (api/routes/results.py)                │
│                - Retrieve final report and graph data                           │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           PIPELINE ORCHESTRATION                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                    src/pipeline.py                                       │  │
│  │  - run_full_pipeline() - Main orchestrator                               │  │
│  │  - run_ingestion_and_extraction() - Phase 1 & 3                          │  │
│  │  - PipelineState - Tracks progress across stages                         │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────┐         ┌───────────────┐         ┌───────────────┐
│  INGESTION    │         │  EXTRACTION   │         │  DETECTION    │
│    LAYER      │         │    LAYER      │         │    LAYER      │
└───────────────┘         └───────────────┘         └───────────────┘
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────┐         ┌───────────────┐         ┌───────────────┐
│ PubMed/PMC    │         │ LLM Claim     │         │ Vector        │
│ XML Parsing   │         │ Extraction    │         │ Retrieval     │
└───────────────┘         └───────────────┘         └───────────────┘
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────┐         ┌───────────────┐         ┌───────────────┐
│ Paper Storage │         │ Quote         │         │ NLI Scoring   │
│ (SQLite)      │         │ Verification  │         │ (DeBERTa-v3)  │
└───────────────┘         └───────────────┘         └───────────────┘
                                                           │
                                                           ▼
                                                ┌───────────────┐
                                                │ LLM Judge     │
                                                │ (Gemini Pro)  │
                                                └───────────────┘
                                                           │
                                    ┌──────────────────────┼──────────────────────┐
                                    ▼                      ▼                      ▼
                            ┌───────────────┐    ┌───────────────┐    ┌───────────────┐
                            │  GRAPH        │    │  SYNTHESIS    │    │  STORAGE      │
                            │  CONSTRUCTION │    │  REPORT       │    │  LAYER        │
                            └───────────────┘    └───────────────┘    └───────────────┘
```

## Detailed Component Architecture

### 1. Ingestion Layer (`src/ingestion/`)

```
┌─────────────────────────────────────────────────────────────────┐
│                    src/ingestion/                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                  │
│  │   pubmed.py      │    │   pmc_xml.py     │                  │
│  │                  │    │                  │                  │
│  │ - search_pubmed()│    │ - fetch_full_    │                  │
│  │ - fetch_abstracts│    │   text()        │                  │
│  │ - ingest_papers()│    │ - parse_pmc_xml()│                  │
│  │ - reformulate_   │    │                  │                  │
│  │   query()        │    │                  │                  │
│  └──────────────────┘    └──────────────────┘                  │
│           │                        │                           │
│           └────────┬───────────────┘                           │
│                    ▼                                           │
│         ┌──────────────────┐                                   │
│         │  validate_       │                                   │
│         │  pubmed.py       │                                   │
│         │  (Validation)    │                                   │
│         └──────────────────┘                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
         ┌──────────────────┐
         │  Paper Model     │
         │  (src/models/    │
         │   paper.py)      │
         │                  │
         │ - pmid           │
         │ - title          │
         │ - authors        │
         │ - year           │
         │ - journal        │
         │ - abstract_text  │
         │ - full_text      │
         │ - doi            │
         └──────────────────┘
```

### 2. Extraction Layer (`src/extraction/`)

```
┌─────────────────────────────────────────────────────────────────┐
│                   src/extraction/                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                  │
│  │claim_extractor.py│    │quote_verifier.py│                  │
│  │                  │    │                  │                  │
│  │- extract_claims_ │    │- verify_and_    │                  │
│  │  batch()         │    │  filter_claims()│                  │
│  │                  │    │                  │                  │
│  │ Uses:            │    │ Uses:           │                  │
│  │ - Gemini 2.5     │    │ - RapidFuzz     │                  │
│  │   Flash          │    │   (Levenshtein) │                  │
│  │ - Prompts from   │    │                 │                  │
│  │   prompts/       │    │ Thresholds:     │                  │
│  │                  │    │ - ≥85%: Pass    │                  │
│  └──────────────────┘    │ - 70-85%: Flag  │                  │
│                          │ - <70%: Reject  │                  │
│                          └──────────────────┘                  │
│                                  │                              │
│                                  ▼                              │
│                          ┌──────────────────┐                  │
│                          │  Claim Model    │                  │
│                          │ (src/models/    │                  │
│                          │  claim.py)      │                  │
│                          │                 │                  │
│                          │ - id (UUID)     │                  │
│                          │ - text          │                  │
│                          │ - normalized_   │                  │
│                          │   text          │                  │
│                          │ - paper_id      │                  │
│                          │ - section       │                  │
│                          │ - authors       │                  │
│                          │ - year          │                  │
│                          │ - confidence_   │                  │
│                          │   score         │                  │
│                          │ - claim_type    │                  │
│                          │ - polarity      │                  │
│                          │ - entities[]    │                  │
│                          │ - population    │                  │
│                          │ - context       │                  │
│                          │ - quote_anchor  │                  │
│                          │ - sample_size   │                  │
│                          │ - study_design  │                  │
│                          └──────────────────┘                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3. Entity Normalization (`src/entity/`)

```
┌─────────────────────────────────────────────────────────────────┐
│                   src/entity/normalizer.py                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  EntityNormalizer.normalize_entities()                          │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  scispaCy en_core_sci_sm Model                            │  │
│  │  - Named Entity Recognition (NER)                        │  │
│  │  - Entity Linking to MeSH IDs                             │  │
│  └──────────────────────────────────────────────────────────┘  │
│         │                                                        │
│         ▼                                                        │
│  Normalized Entity Types:                                        │
│  - DRUG, GENE, DISEASE, PROTEIN, PATHWAY, BIOMARKER            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4. Detection Layer (`src/detection/`)

```
┌─────────────────────────────────────────────────────────────────┐
│                    src/detection/                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                  │
│  │  embedder.py     │    │  faiss_index.py  │                  │
│  │                  │    │                  │                  │
│  │ClaimEmbedder     │    │ClaimIndex       │                  │
│  │- embed_claims()  │    │- build_index()   │                  │
│  │                  │    │- find_candidate_│                  │
│  │Uses:             │    │  pairs()        │                  │
│  │- Sentence-       │    │                  │                  │
│  │  Transformers    │    │Uses:            │                  │
│  │- all-MiniLM-L6-  │    │- FAISS-cpu      │                  │
│  │  v2              │    │- FLAT_IP index  │                  │
│  │                  │    │- Top-K retrieval│                  │
│  └──────────────────┘    └──────────────────┘                  │
│           │                        │                           │
│           └────────┬───────────────┘                           │
│                    ▼                                           │
│         ┌──────────────────┐                                   │
│         │  nli_scorer.py   │                                   │
│         │                  │                                   │
│         │NLIScorer         │                                   │
│         │- filter_         │                                   │
│         │  contradictions()│                                   │
│         │                  │                                   │
│         │Uses:             │                                   │
│         │- DeBERTa-v3-     │                                   │
│         │  large (Hugging   │                                   │
│         │  Face)           │                                   │
│         │- Cross-encoder   │                                   │
│         │- Threshold:      │                                   │
│         │  ≥0.70           │                                   │
│         └──────────────────┘                                   │
│                    │                                           │
│                    ▼                                           │
│         ┌──────────────────┐                                   │
│         │  llm_judge.py    │                                   │
│         │                  │                                   │
│         │judge_batch()     │                                   │
│         │                  │                                   │
│         │Uses:             │                                   │
│         │- Gemini 2.5 Pro │                                   │
│         │- Scope-aware    │                                   │
│         │  validation     │                                   │
│         │- Weeds out     │                                   │
│         │  false positives│                                   │
│         └──────────────────┘                                   │
│                    │                                           │
│                    ▼                                           │
│         ┌──────────────────┐                                   │
│         │contradiction_    │                                   │
│         │detector.py       │                                   │
│         │                  │                                   │
│         │detect_           │                                   │
│         │contradictions()  │                                   │
│         │- Orchestrates    │                                   │
│         │  full pipeline   │                                   │
│         └──────────────────┘                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
         ┌──────────────────┐
         │ContradictionPair │
         │(src/models/      │
         │ contradiction.py)│
         │                  │
         │ - claim_a_id      │
         │ - claim_b_id      │
         │ - contradiction_ │
         │   score          │
         │ - judge_verdict  │
         │ - explanation    │
         └──────────────────┘
```

### 5. Graph Construction (`src/graph/`)

```
┌─────────────────────────────────────────────────────────────────┐
│                      src/graph/                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                  │
│  │claim_graph.py    │    │graph_export.py  │                  │
│  │                  │    │                  │                  │
│  │build_claim_graph()│   │- export_to_     │                  │
│  │                  │    │  cytoscape_json()│                  │
│  │Uses:             │    │- export_to_gexf()│                  │
│  │- NetworkX        │    │                  │                  │
│  │- Force-directed  │    │Output formats:  │                  │
│  │  layout          │    │- JSON (Cytoscape)│                  │
│  │- Node types:     │    │- GEXF (Gephi)   │                  │
│  │  - Paper         │    │                  │                  │
│  │  - Claim         │    │                  │                  │
│  │  - Entity        │    │                  │
│  │- Edge types:     │    │                  │
│  │  - SUPPORT       │    │                  │
│  │  - CONTRADICT    │    │                  │
│  │  - MENTIONS      │    │                  │
│  └──────────────────┘    └──────────────────┘                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 6. Synthesis Layer (`src/synthesis/`)

```
┌─────────────────────────────────────────────────────────────────┐
│                   src/synthesis/                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  report_generator.py                                       │  │
│  │                                                           │  │
│  │  generate_synthesis_report()                              │  │
│  │                                                           │  │
│  │  Uses:                                                    │  │
│  │  - Gemini 2.5 Pro                                         │  │
│  │  - RAG (Retrieval-Augmented Generation)                   │  │
│  │  - Contradiction context                                  │  │
│  │  - Claim evidence                                         │  │
│  │                                                           │  │
│  │  Output:                                                  │  │
│  │  - Narrative summary                                      │  │
│  │  - Consensus scores                                       │  │
│  │  - Key contradictions                                      │  │
│  │  - Citation-grounded findings                            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           │                                     │
│                           ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  SynthesisReport Model                                   │  │
│  │  (src/models/report.py)                                  │  │
│  │                                                           │  │
│  │  - summary: str                                          │  │
│  │  - contradictions: list[dict]                             │  │
│  │  - consensus_scores: dict[str, float]                     │  │
│  │  - total_papers: int                                      │  │
│  │  - total_claims: int                                      │  │
│  │  - metadata: dict (run_id, time_elapsed, cost_estimate)  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 7. Storage Layer (`src/storage/`)

```
┌─────────────────────────────────────────────────────────────────┐
│                    src/storage/database.py                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  SQLite Database (data/rsce.db)                                  │
│                                                                  │
│  Tables:                                                         │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ pipeline_runs                                            │  │
│  │ - id (run_id)                                            │  │
│  │ - query                                                  │  │
│  │ - status (RUNNING, COMPLETED, FAILED)                    │  │
│  │ - started_at, completed_at                               │  │
│  │ - papers_fetched, claims_extracted                       │  │
│  │ - contradictions_found                                   │  │
│  │ - status_message                                         │  │
│  │ - error_message                                          │  │
│  │ - report_json (TEXT)                                     │  │
│  │ - pmids (JSON)                                           │  │
│  │ - nli_pairs_total, nli_pairs_scored                      │  │
│  │ - judge_pairs_total, judge_pairs_scored                   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ papers                                                   │  │
│  │ - pmid (PK)                                              │  │
│  │ - title, authors, year, journal                          │  │
│  │ - abstract_text, full_text, doi                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ claims                                                   │  │
│  │ - id (PK, UUID)                                          │  │
│  │ - paper_id (FK)                                          │  │
│  │ - text, normalized_text                                  │  │
│  │ - section, authors, year                                 │  │
│  │ - confidence_score, claim_type, polarity                 │  │
│  │ - entities (JSON), population, context                    │  │
│  │ - quote_anchor, sample_size, study_design                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ contradictions                                           │  │
│  │ - id (PK)                                                │  │
│  │ - claim_a_id, claim_b_id (FK)                            │  │
│  │ - contradiction_score                                    │  │
│  │ - judge_verdict, explanation                             │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Functions:                                                      │
│  - init_db() - Initialize schema                                │
│  - save_pipeline_run(), get_pipeline_run()                     │
│  - save_papers(), get_papers()                                  │
│  - save_claims(), get_claims()                                  │
│  - save_contradictions(), get_contradictions()                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 8. LLM Abstraction Layer (`src/llm/`)

```
┌─────────────────────────────────────────────────────────────────┐
│                      src/llm/                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  LLMProvider Interface                                           │
│         │                                                        │
│         ├──► GeminiProvider                                      │
│         │    - gemini-2.5-flash (extraction)                     │
│         │    - gemini-2.5-pro (judgment, synthesis)              │
│         │                                                        │
│         └──► OpenAIProvider                                      │
│              - gpt-4o (alternative)                             │
│                                                                  │
│  Functions:                                                      │
│  - get_llm(model_name) - Factory function                        │
│  - generate() - Async text generation                           │
│  - stream() - Streaming responses                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow Diagram

```
USER QUERY
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. INGESTION STAGE                                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ Query → PubMed E-utilities Search → PMIDs                       │
│   │                                                              │
│   ├──► If insufficient results → Query Reformulation             │
│   │                                                              │
│   └──► Fetch abstracts from PubMed                              │
│         │                                                        │
│         └──► Fetch full-text XML from PMC (if open access)        │
│               │                                                  │
│               └──► Parse XML sections (Intro, Methods, Results)  │
│                     │                                            │
│                     ▼                                            │
│              Save Papers to SQLite                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. EXTRACTION STAGE                                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ For each paper:                                                  │
│   │                                                              │
│   ├──► Send abstract/full-text to LLM (Gemini 2.5 Flash)         │
│   │    - Extract structured claims                               │
│   │    - Include quote_anchor for verification                   │
│   │                                                              │
│   └──► Verify claims with RapidFuzz                              │
│        - Match quote_anchor against source text                  │
│        - ≥85%: Pass (verified)                                   │
│        - 70-85%: Flag (paraphrase, penalize confidence)          │
│        - <70%: Reject (hallucination)                            │
│         │                                                        │
│         ▼                                                        │
│  Save Verified Claims to SQLite                                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. ENTITY NORMALIZATION STAGE                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ For each claim:                                                  │
│   │                                                              │
│   └──► Extract entities using scispaCy NER                      │
│        - Link to MeSH IDs                                        │
│        - Normalize to canonical forms                            │
│         │                                                        │
│         ▼                                                        │
│  Update Claims with normalized entities                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. CONTRADICTION DETECTION STAGE                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ Step 4a: Vector Embedding                                        │
│   │                                                              │
│   └──► Embed all claims using Sentence-Transformers             │
│        - Model: all-MiniLM-L6-v2                                 │
│        - Output: 384-dimensional vectors                        │
│         │                                                        │
│         ▼                                                        │
│ Step 4b: FAISS Retrieval                                         │
│   │                                                              │
│   └──► Build FAISS index (FLAT_IP)                               │
│        - Query each claim against index                           │
│        - Retrieve top-K similar pairs (exclude same-paper)        │
│        - Filter by similarity threshold (≥0.3)                    │
│         │                                                        │
│         ▼                                                        │
│ Step 4c: NLI Screening                                            │
│   │                                                              │
│   └──► Score candidate pairs with DeBERTa-v3 NLI model            │
│        - Compute entailment, neutral, contradiction scores       │
│        - Filter pairs with contradiction ≥ 0.70                   │
│        - Batch processing for efficiency                          │
│         │                                                        │
│         ▼                                                        │
│ Step 4d: LLM Judgment                                             │
│   │                                                              │
│   └──► Send NLI-filtered pairs to Gemini 2.5 Pro                 │
│        - Scope-aware validation                                   │
│        - Check for study design mismatches                        │
│        - Weigh population differences                            │
│        - Provide explanation for verdict                         │
│         │                                                        │
│         ▼                                                        │
│  Save ContradictionPairs to SQLite                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. GRAPH CONSTRUCTION STAGE                                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ Build NetworkX Graph:                                            │
│   │                                                              │
│   ├──► Nodes:                                                   │
│   │    - Papers (PMID, title, journal)                          │
│   │    - Claims (text, polarity, confidence)                     │
│   │    - Entities (MeSH ID, type)                               │
│   │                                                              │
│   └──► Edges:                                                   │
│        - Paper → Claim (MENTIONS)                                │
│        - Claim → Entity (MENTIONS)                               │
│        - Claim → Claim (SUPPORT/CONTRADICT)                      │
│         │                                                        │
│         ▼                                                        │
│  Export Graph:                                                   │
│  - JSON format for Cytoscape.js frontend                         │
│  - GEXF format for Gephi analysis                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. SYNTHESIS REPORT STAGE                                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ Generate Narrative Report:                                       │
│   │                                                              │
│   └──► Send contradictions and claims to Gemini 2.5 Pro          │
│        - RAG with claim context                                  │
│        - Generate summary of findings                            │
│        - Calculate consensus scores                              │
│        - Highlight key contradictions                            │
│        - Provide citation-grounded narrative                     │
│         │                                                        │
│         ▼                                                        │
│  Save SynthesisReport to pipeline_runs table                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7. PRESENTATION STAGE                                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ API Response:                                                    │
│   │                                                              │
│   ├──► /api/results/{run_id}                                     │
│   │    - Return SynthesisReport JSON                             │
│   │    - Return Graph JSON                                       │
│   │                                                              │
│   └──► Frontend Display                                          │
│        - Next.js renders results page                            │
│        - Cytoscape.js visualizes claim network                   │
│        - Interactive claim detail panels                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Frontend Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    frontend/ (Next.js 15+)                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  app/                                                    │  │
│  │                                                           │  │
│  │  ├──► layout.tsx                                         │  │
│  │  │    - Root layout with global styles                   │  │
│  │  │                                                       │  │
│  │  ├──► page.tsx (Main Search Page)                       │  │
│  │  │    - Query input form                                 │  │
│  │  │    - Recent runs list                                 │  │
│  │  │    - WebSocket connection for real-time updates        │  │
│  │  │                                                       │  │
│  │  └──► results/[run_id]/page.tsx (Results Page)            │  │
│  │       - Synthesis report display                          │  │
│  │       - Cytoscape.js graph visualization                  │  │
│  │       - Claim detail sidebar                              │  │
│  │       - Progress tracking                                  │  │
│  │                                                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  components/                                             │  │
│  │  - UI components (buttons, cards, etc.)                   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  utils/                                                  │  │
│  │  - API client functions                                  │  │
│  │  - WebSocket management                                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  types/                                                  │  │
│  │  - TypeScript type definitions                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Tech Stack:                                                     │
│  - Next.js 15+ (App Router, Turbopack)                         │
│  - TypeScript                                                   │
│  - Tailwind CSS v4                                               │
│  - Cytoscape.js (graph visualization)                            │
│  - cytoscape-fcose (force-directed layout)                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Configuration and Settings

```
┌─────────────────────────────────────────────────────────────────┐
│                    src/config.py                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Environment Variables (.env):                                   │
│  - GEMINI_API_KEY                                                │
│  - OPENAI_API_KEY (optional)                                    │
│  - PUBMED_EMAIL                                                 │
│                                                                  │
│  Settings:                                                       │
│  - max_papers: 25 (default)                                      │
│  - min_papers: 10 (for query reformulation)                      │
│  - llm_provider: "gemini" or "openai"                            │
│  - extraction_model: "gemini-2.5-flash"                          │
│  - judge_model: "gemini-2.5-pro"                                 │
│  - nli_model: "cross-encoder/nli-deberta-v3-large"               │
│  - nli_contradiction_threshold: 0.70                             │
│  - faiss_top_k: 10                                               │
│  - max_contradictions_displayed: 20                              │
│  - Cost estimation parameters                                    │
│  - CORS allowed_origins                                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Key Design Patterns

1. **Pipeline Pattern**: Sequential processing stages with state tracking
2. **Repository Pattern**: SQLite database abstraction in storage layer
3. **Strategy Pattern**: Pluggable LLM providers (Gemini/OpenAI)
4. **Observer Pattern**: WebSocket broadcasts for real-time progress
5. **Factory Pattern**: LLM provider factory function
6. **Batch Processing**: Efficient NLI scoring and claim extraction
7. **Hybrid Screening**: Local models (FAISS/NLI) + LLM validation for cost efficiency

## Performance Optimizations

1. **Local Model Execution**: FAISS and NLI run locally to reduce API costs
2. **Async/Await**: Concurrent paper fetching and claim extraction
3. **Batch Processing**: NLI scoring in batches of 32 pairs
4. **Vector Indexing**: O(N log N) retrieval vs O(N²) brute force
5. **Progressive Enhancement**: PMC full-text enrichment is optional
6. **WebSocket Updates**: Real-time UI without polling

## Error Handling

- Pipeline state tracking with error messages
- Graceful degradation when PMC full-text unavailable
- Query reformulation fallback for insufficient results
- WebSocket disconnect handling
- Database transaction rollback on failures
