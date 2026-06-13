# RSCE Codebase Rating

> Assessed against: [research_synthesis_engine_design.md] · [implementation_plan.md] · [codebase_review.md (prior)] · current source

---

## Overall Score: **8.2 / 10** ⬆️ (was 7.5)

The codebase has **meaningfully advanced** since the last review. The #1 architectural gap from the prior review — the missing `run_full_pipeline()` orchestrator — is now **fixed and fully wired**. The Phase 4 API (FastAPI + WebSocket + Next.js frontend) is also **complete and functional**. This is a legitimately impressive solo project with a coherent, end-to-end working system.

---

## Scorecard by Dimension

| Dimension | Score | Notes |
|---|:---:|---|
| **Architecture & Module Design** | 9/10 | Clean sequential pipeline, excellent separation of concerns, provider abstraction is textbook |
| **Design Spec Adherence** | 8.5/10 | All 7 modules from the design doc are implemented; data models match spec exactly |
| **Core Pipeline Correctness** | 7.5/10 | 3 of the 5 critical bugs from prior review are still present |
| **API Layer** | 8/10 | REST + WebSocket real-time progress is well-done; minor CORS and auth gaps |
| **Frontend** | 7/10 | Functional; ClaimGraph.tsx is impressive; demo data not seeded |
| **Test Coverage** | 5/10 | Unit tests exist but integration test coverage is thin |
| **Code Quality** | 8/10 | Mostly clean; a few performance anti-patterns remain |
| **Portfolio Readiness** | 7.5/10 | README needs benchmark numbers + diagrams to be truly impressive |

---

## What Changed Since the Prior Review ✅

These issues from the previous 7.5/10 review have been **resolved**:

| Prior Issue | Status |
|---|---|
| #5: Pipeline not unified — `run_full_pipeline()` missing | ✅ **Fixed** — fully implemented in [pipeline.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/pipeline.py#L188) with `on_stage_complete` callback |
| #7: Wrong LLM model used for synthesis in `main.py` | ✅ **Fixed** — `pipeline.py` correctly calls `get_llm(settings.judge_model)` for report generation |
| #8: `LOCAL_SYNONYM_MAP` hardcoded | ✅ **Fixed** — now loaded from `data/synonym_map.json` via `settings.synonym_map_path` |
| #11: `storage/` missing `__init__.py` | ✅ **Fixed** — present |
| #4 (partial): `get_claims_for_run` N+1 query | ✅ **Fixed** — uses JOIN query: `SELECT c.*, p.authors, p.year FROM claims c JOIN papers p ON c.paper_id = p.pmid` |
| Phase 4 API + WebSocket real-time progress | ✅ **New** — `ConnectionManager`, `update_run_status()`, WS endpoint all working |
| Frontend (Next.js + Cytoscape.js) | ✅ **New** — `ClaimGraph.tsx`, results page, home page with live WS status all present |

---

## Remaining Issues

### 🔴 CRITICAL — Still Unresolved

#### 1. `SUPERSEDES` Edge Overwrites `CONTRADICTS` in `claim_graph.py`

In [claim_graph.py L88–94](file:///c:/Users/laaks/ZZ/Projects/P1/src/graph/claim_graph.py#L88-L94):

```python
G.add_edge(claim_a_id, claim_b_id, **edge_attrs)   # CONTRADICTS
G.add_edge(claim_b_id, claim_a_id, **edge_attrs)   # CONTRADICTS

if pair.claim_a.year > pair.claim_b.year:
    G.add_edge(claim_a_id, claim_b_id, type="SUPERSEDES")  # ← OVERWRITES CONTRADICTS!
```

`nx.DiGraph` stores exactly one edge per `(u, v)` pair. The `SUPERSEDES` call silently **replaces** the `CONTRADICTS` edge, losing `contradiction_score`, `explanation`, and `scope_note`. The graph is structurally wrong for any contradiction pair involving papers with different years.

**Fix (2 options):**

```python
# Option A: switch to MultiDiGraph (preferred — allows parallel edges)
G = nx.MultiDiGraph()

# Option B: encode both on the CONTRADICTS edge as an attribute
G.add_edge(claim_a_id, claim_b_id, **{
    **edge_attrs,
    "supersedes": pair.claim_a.year > pair.claim_b.year
})
```

---

#### 2. `JudgeResponse.contradiction_type` is `str`, Not the Enum

In [llm_judge.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/detection/llm_judge.py), the `JudgeResponse` Pydantic model has:

```python
contradiction_type: str   # ← should be ContradictionType
```

The downstream coercion `ContradictionType(response.contradiction_type.upper())` will silently fall back to `DIRECT_NEGATION` on any LLM variation like `"Quantitative Conflict"` vs `"QUANTITATIVE_CONFLICT"`. This masks misclassifications with zero error.

**Fix (5 min):**
```python
class JudgeResponse(BaseModel):
    contradiction_type: ContradictionType   # LLM structured output enforces valid enum values
```

---

#### 3. `started_at` Timestamp Lost on Final `save_pipeline_run` Call

`save_pipeline_run` uses `INSERT OR REPLACE`, which is a full row replacement. Any call without `started_at` NULLs out the original value. In [pipeline.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/pipeline.py), `save_pipeline_run` is called multiple times as the pipeline progresses. If any intermediate call omits `started_at`, the timestamp is overwritten with NULL.

The current code passes `started_at=started_at` in most calls, but the function signature allows it to be `None`. A refactor to use `UPDATE ... SET ... WHERE id = ?` for status updates (instead of `INSERT OR REPLACE`) would be safer.

---

### 🟠 ARCHITECTURE GAPS

#### 4. Claim Extraction Only Uses Abstracts — Full Text Not Fed to LLM

PMC full-text is fetched and stored in `paper.full_text`, but [claim_extractor.py L69](file:///c:/Users/laaks/ZZ/Projects/P1/src/extraction/claim_extractor.py#L69) passes only `paper.abstract_text` to `build_extraction_prompt`. The design doc and Phase 3 goal explicitly require full-text extraction for open-access papers.

```python
# Current — abstract only
prompt = build_extraction_prompt(paper.abstract_text)

# Should be — use full_text when available, fall back to abstract
source_text = paper.full_text or paper.abstract_text
prompt = build_extraction_prompt(source_text)
```

> [!IMPORTANT]
> This is the most impactful missing feature. Full-text extraction dramatically improves recall — Results and Discussion sections contain most of the high-value claims. The PMC fetching pipeline is already working; only the extraction step needs updating.

---

#### 5. `is_primary_finding` Always Set to `True`

In [quote_verifier.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/extraction/quote_verifier.py), every verified claim gets `is_primary_finding=True`. Now that full-text sections are being ingested, claims from `Introduction` or `Methods` should get `is_primary_finding=False`. The `section` field is available on `Claim` — this just needs to be wired.

```python
# quote_verifier.py: derive from section
is_primary_finding = claim.section.upper() in ("RESULTS", "CONCLUSIONS", "DISCUSSION", "ABSTRACT")
```

---

#### 6. Demo Data Not Pre-Seeded

`GET /api/demo/{topic}` in [results.py](file:///c:/Users/laaks/ZZ/Projects/P1/api/routes/results.py#L94) requires hard-coded run IDs (`demo_metformin`, `demo_fasting`, `demo_ssri`) to exist in the database. There's no seeding script — a fresh clone will return 404 on all demo routes. This breaks the "recruiter runs it and is impressed" use case.

**Fix:** A `scripts/seed_demo.py` that either:
- Runs the actual pipeline for 3 topics and saves the run IDs
- Or restores a pre-committed `data/demo.db` SQLite file

---

#### 7. CORS Wildcard in Production Code

[api/app.py L22](file:///c:/Users/laaks/ZZ/Projects/P1/api/app.py#L22):
```python
allow_origins=["*"]   # fine for dev, not for production
```

If this is ever deployed (the roadmap mentions Fly.io/Railway), this should be `allow_origins=["http://localhost:3000", "https://your-domain.com"]`.

---

### 🟡 CODE QUALITY

#### 8. Prompt Loaded From Disk on Every Judge Call

[llm_judge.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/detection/llm_judge.py) calls `load_prompt()` inside `judge_contradiction_pair()` which runs for each candidate pair (15–20 calls/run). Compare to [claim_extractor.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/extraction/claim_extractor.py) which correctly uses `_PROMPT_TEMPLATE` module-level caching. Apply the same pattern.

**Fix (10 min):**
```python
_JUDGE_PROMPT = None

def load_judge_prompt() -> str:
    global _JUDGE_PROMPT
    if _JUDGE_PROMPT is None:
        # ... load from file
    return _JUDGE_PROMPT
```

---

#### 9. Cost Estimate Constants Are Magic Numbers

[pipeline.py L329–333](file:///c:/Users/laaks/ZZ/Projects/P1/src/pipeline.py#L329-L333) has hardcoded multipliers. These are now in `settings` (`cost_per_paper`, `cost_per_contradiction`, `cost_synthesis`) — but the code already uses `settings.cost_per_paper` etc. ✅ *This is actually already fixed in pipeline.py.* However, verify `main.py` (CLI path) uses the same constants.

---

#### 10. SciFact Eval Sliced to 60 Pairs — Not Statistically Valid

[evaluation/scifact_eval.py](file:///c:/Users/laaks/ZZ/Projects/P1/evaluation/) limits evaluation to 60 pairs. The design doc explicitly calls out reporting SciFact P/R on the **full dataset** as a "portfolio power move." 60 samples gives high variance — a reviewer running it twice could get different numbers. Make the sample size a CLI argument defaulting to the full set.

---

### 🔵 TESTING GAPS

#### 11. No Test for Citation Hallucination Removal

`validate_and_clean_citations()` in [report_generator.py](file:///c:/Users/laaks/ZZ/Projects/P1/src/synthesis/report_generator.py#L38) is the **citation fidelity guarantee** (the "100%" metric in the design doc). It has no test. This is a 30-minute win:

```python
def test_hallucinated_citations_are_stripped():
    papers = [Paper(pmid="1", authors=["Smith"], year=2023, ...)]
    text = "X is true [Smith, 2023]. Y is also true [FakeAuthor, 2099]."
    cleaned = validate_and_clean_citations(text, papers)
    assert "[Smith, 2023]" in cleaned
    assert "[FakeAuthor, 2099]" not in cleaned
    assert "2099" not in cleaned
```

---

#### 12. No End-to-End Integration Test

There's no test exercising the full `run_full_pipeline()` → DB → API → response chain with fixture data. This is the most important test for portfolio credibility. Even a single test with a fixed 5-paper fixture and mocked LLM calls would catch regressions across all module boundaries.

---

### 🟢 PORTFOLIO POLISH

#### 13. README Missing Key Portfolio Elements

Per the design doc's "portfolio power move" checklist:

| Item | Status |
|---|---|
| Architecture diagram image | ✅ Referenced (`docs/architecture.png`) — verify file exists |
| SciFact benchmark table (P/R numbers) | ❌ Not in README |
| Cost-per-run breakdown | ✅ Present |
| GIF / demo video | ❌ Not present |
| Dockerfile | ❌ Not present |
| Live hosted demo URL | ❌ Not present |

---

#### 14. No `pytest.ini` / `asyncio_mode = "auto"`

`pytest-asyncio` without configuration requires `@pytest.mark.asyncio` on every async test. Add to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

---

## Priority Fix List

| # | Issue | Effort | Impact |
|---|---|:---:|---|
| 1 | `SUPERSEDES` overwrites `CONTRADICTS` edge | 15 min | 🔴 Graph is structurally wrong |
| 2 | `JudgeResponse.contradiction_type` should be enum | 5 min | 🔴 Silent misclassification |
| 3 | Feed `full_text` to claim extractor (not just abstract) | 30 min | 🟠 Major recall improvement |
| 4 | Seed demo data (`scripts/seed_demo.py`) | 1 hr | 🟠 Demo is broken for fresh clones |
| 5 | `is_primary_finding` derived from section | 20 min | 🟠 Correctness with full-text active |
| 6 | Citation hallucination unit test | 30 min | 🟠 Validates key guarantee |
| 7 | SciFact eval — configurable sample size | 20 min | 🟠 Portfolio credibility |
| 8 | Cache judge prompt (module-level) | 10 min | 🟡 Performance |
| 9 | `asyncio_mode = "auto"` in pyproject.toml | 2 min | 🟡 DX |
| 10 | CORS: restrict origins for deployment | 5 min | 🟡 Security |
| 11 | README: add SciFact numbers + GIF | 2 hrs | 🟢 Portfolio polish |
| 12 | Dockerfile | 1 hr | 🟢 Portfolio polish |

---

## What Would Push This to 9.5/10

1. **Fix the `SUPERSEDES`/`CONTRADICTS` edge bug** — it's a correctness issue that would show up immediately in anyone examining the graph output
2. **Feed `full_text` into extraction** — the PMC fetching is already working; this is a 1-line change that would dramatically improve claim recall
3. **Add SciFact P/R numbers to README** — the design doc says this is what separates the top 1% of portfolios; the evaluation code exists, just run it and paste the numbers
4. **Seed the demo data** — the demo route exists, the data doesn't; a recruiter clicking "try demo" and getting a 404 is a bad first impression
5. **One end-to-end integration test** — confidence that a refactor won't silently break the pipeline
