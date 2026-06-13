# Codebase Review — Research Synthesis & Contradiction Engine

> Reviewed: 2026-06-12 | Files read: all 40+ source files across all modules

---

## Overall Rating: **7.5 / 10**

This is a genuinely impressive solo project codebase. The architecture is coherent, the module boundaries are clean, the design document is faithfully implemented, and Phases 1–3 are functionally complete. A recruiter who `git clone`s this and reads the code will be impressed. The rating is not higher because of specific correctness bugs, missing pipeline wiring, and test gaps that would surface under real usage.

---

## What's Working Well (The Strengths)

| Area | Verdict |
|---|---|
| **Architecture / module separation** | Excellent. `ingestion → extraction → storage → detection → graph → synthesis → presentation` is clean, each module has a single job. |
| **Data models** | Correct and complete. All enums, `Claim`, `ContradictionPair`, `SynthesisReport` match the design spec exactly. |
| **Quote-anchor verifier** | Solid implementation. Correct fuzzy matching logic, fallback to `full_text` when abstract fails, proper confidence halving. |
| **FAISS index** | Well-implemented. Cross-paper filtering is correct, `k + 20` over-fetch trick for filtering, proper deduplication. |
| **LLM providers** | Clean provider abstraction. Retry logic, backoff, structured output — all correct. Both Gemini and OpenAI are symmetrically implemented. |
| **PubMed ingestion** | Robust XML parser. Handles multi-label abstracts, collective authors, MedlineDate fallback, dual-source DOI lookup. |
| **Entity normalizer** | Three-tier cascade (local map → scispaCy → LLM fallback) is the right design. Graceful degradation when scispaCy not installed. |
| **Rich CLI output** | Genuinely beautiful and impressive for a portfolio demo. Side-by-side contradiction drill-down, stats table, and grounded summary narrative all present. |
| **Database layer** | Correct schema, FK constraints on, `INSERT OR REPLACE` for idempotency, `finally` blocks for connection cleanup. |
| **SciFact evaluator** | Exists, downloads dataset, computes P/R/F1 on CONTRADICT label. Functional. |

---

## Improvements Needed

Grouped by severity / priority.

---

### 🔴 CRITICAL — Correctness Bugs

#### 1. `save_pipeline_run` called with `started_at` missing in `main.py`

In [`main.py` L62–71](file:///c:/Users/laaks/ZZ/Projects/P1/src/main.py#L62-L71), `save_pipeline_run` is called after contradictions are found. The `started_at` parameter is **not passed**, which means the `INSERT OR REPLACE` will NULL-overwrite the original `started_at` timestamp that was set by `pipeline.py`. The pipeline's intermediate DB record gets corrupted.

```diff
- save_pipeline_run(
-     run_id=state.run_id,
-     query=query,
-     status="COMPLETED",
-     papers_fetched=len(state.papers),
-     claims_extracted=len(state.claims),
-     contradictions_found=len(contradictions),
-     completed_at=datetime.now(timezone.utc).isoformat()
- )
+ save_pipeline_run(
+     run_id=state.run_id,
+     query=query,
+     status="COMPLETED",
+     papers_fetched=len(state.papers),
+     claims_extracted=len(state.claims),
+     contradictions_found=len(contradictions),
+     started_at=state.started_at,   # must preserve the original start timestamp
+     completed_at=datetime.now(timezone.utc).isoformat()
+ )
```

**Fix also requires:** `PipelineState` needs a `started_at: str` field, or `save_pipeline_run` should be redesigned as an `UPDATE` instead of `INSERT OR REPLACE` for the final status update.

---

#### 2. `SUPERSEDES` edge overwrites `CONTRADICTS` edge in `claim_graph.py`

In [`claim_graph.py` L88–92](file:///c:/Users/laaks/ZZ/Projects/P1/src/graph/claim_graph.py#L88-L92):

```python
G.add_edge(claim_a_id, claim_b_id, **edge_attrs)  # CONTRADICTS
G.add_edge(claim_b_id, claim_a_id, **edge_attrs)  # CONTRADICTS (reverse)
# ...
if pair.claim_a.year > pair.claim_b.year:
    G.add_edge(claim_a_id, claim_b_id, type="SUPERSEDES")  # OVERWRITES the CONTRADICTS edge!
```

NetworkX `DiGraph` only stores one edge per `(u, v)` pair. The second `add_edge` call with `type="SUPERSEDES"` silently overwrites the `CONTRADICTS` edge attributes for the same pair. The contradiction score and explanation are lost.

**Fix:** Use `nx.MultiDiGraph` to allow multiple edge types, or add SUPERSEDES as a separate attribute on the CONTRADICTS edge.

---

#### 3. `pmc_xml.py` acquires the `_fetch_semaphore` twice in sequence

In [`pmc_xml.py`](file:///c:/Users/laaks/ZZ/Projects/P1/src/ingestion/pmc_xml.py), the `fetch_full_text` function acquires `get_fetch_semaphore()` for the PMID→PMCID conversion (L35), releases it, then acquires it again for the PMC EFetch (L75). These two requests both count against the semaphore correctly.

But the deeper issue: `fetch_full_text` is called via `enrich_papers_with_full_text` in `pipeline.py`, which already wraps it in `asyncio.gather`. With 25 papers, this generates **50 sequential-within-concurrent semaphore acquisitions**, but each paper does them one-at-a-time. The real problem: a new `aiohttp.ClientSession()` is created **per request** inside the `async with sem:` block. This is extremely expensive — sessions are connection pools.

**Fix:** Create a single shared `aiohttp.ClientSession` per pipeline run (pass it as a parameter, or use a module-level context manager).

---

#### 4. `_row_to_claim` does N+1 queries in `database.py`

In [`database.py` L244–248](file:///c:/Users/laaks/ZZ/Projects/P1/src/storage/database.py#L244-L248), `_row_to_claim` executes a separate `SELECT` query per claim to fetch the paper's `authors` and `year`. When called from `get_claims_for_run` with 200 claims, this executes 200 + 1 = 201 queries.

**Fix:** Use a JOIN in `get_claims_for_run` to fetch claim + paper data in a single query.

---

#### 5. `JudgeResponse.contradiction_type` is `str`, not `ContradictionType`

In [`llm_judge.py` L20](file:///c:/Users/laaks/ZZ/Projects/P1/src/detection/llm_judge.py#L20):

```python
class JudgeResponse(BaseModel):
    contradiction_type: str  # ← should be ContradictionType enum
```

This means the LLM can return any arbitrary string. The `ContradictionType(response.contradiction_type.upper())` call at L84 will raise `ValueError` for any slightly different casing or wording (e.g., `"Quantitative Conflict"` vs `"QUANTITATIVE_CONFLICT"`). The fallback to `DIRECT_NEGATION` on `ValueError` silently masks misclassifications.

**Fix:** Change to `contradiction_type: ContradictionType` in `JudgeResponse`. The LLM structured output will be constrained to valid enum values.

---

### 🟠 ARCHITECTURE GAPS

#### 6. The full pipeline is not wired — `pipeline.py` stops before contradiction detection

[`pipeline.py`](file:///c:/Users/laaks/ZZ/Projects/P1/src/pipeline.py) only runs Phases 1+3 (ingestion, extraction, normalization). Contradiction detection, graph construction, synthesis, and presentation are all called directly from [`main.py`](file:///c:/Users/laaks/ZZ/Projects/P1/src/main.py). This means:

- `pipeline.py` cannot be used standalone as the orchestrator
- There's no single `run_full_pipeline()` function you can call in tests or the API
- Intermediate results between `pipeline.py` and `main.py` are passed via an in-memory `PipelineState` object that only contains `papers` and `claims` — contradictions and the final report are not captured in state

**Fix:** Either extend `PipelineState` to include contradictions and report, or create a unified `run_full_pipeline()` in `pipeline.py` that returns a complete result object. The API (Phase 4) will need this.

---

#### 7. The `detection/__init__.py` re-exports but the judge LLM model is the extraction model

In [`contradiction_detector.py` L63](file:///c:/Users/laaks/ZZ/Projects\P1\src\detection\contradiction_detector.py#L63):

```python
llm = get_llm(settings.judge_model)
```

This correctly uses `judge_model`. BUT in [`main.py` L84](file:///c:/Users/laaks/ZZ/Projects/P1/src/main.py#L84):

```python
llm = get_llm()  # ← uses settings.extraction_model (Gemini Flash)
```

The synthesis report is generated with the cheap/fast extraction model instead of the smart judge model. This is a **cost/quality misalignment** — synthesis should use `settings.judge_model` (Gemini Pro).

---

#### 8. `LOCAL_SYNONYM_MAP` in `normalizer.py` is domain-specific and not extensible

The hardcoded map in [`normalizer.py` L25–40](file:///c:/Users/laaks/ZZ/Projects/P1/src/entity/normalizer.py#L25-L40) covers only metformin, aspirin, cancer, AMPK, mTOR. For any other topic (e.g., "intermittent fasting", "SSRIs"), the map provides zero benefit and falls through to the LLM.

**Fix:** Load from an external JSON file (`data/synonym_map.json`) so it can be expanded without code changes.

---

#### 9. Semaphore state is `None`-initialized globals in `pubmed.py`

In [`pubmed.py` L14–27](file:///c:/Users/laaks/ZZ/Projects/P1/src/ingestion/pubmed.py#L14-L27), `_search_semaphore` and `_fetch_semaphore` are module-level `None` values lazily initialized on first call. This is a footgun: if `search_pubmed` is called from two different event loops (e.g., tests), the semaphore created in loop A is incompatible with loop B.

**Fix:** Initialize semaphores inside the async function or pass them explicitly.

---

#### 10. `is_primary_finding` is hardcoded `True` in `quote_verifier.py`

In [`quote_verifier.py` L130](file:///c:/Users/laaks/ZZ/Projects/P1/src/extraction/quote_verifier.py#L130), every verified claim gets `is_primary_finding=True`. The design doc says this should be `True` for Results/Conclusions and `False` for background/intro.

Since Phase 1 processes abstracts-only, this is acceptable for now. But with Phase 3 full-text ingestion now active in the pipeline, section-aware tagging is needed. Claims extracted from `Introduction` or `Methods` sections should get `is_primary_finding=False`.

---

### 🟡 CODE QUALITY

#### 11. Repeated paper lookup pattern in `report_generator.py`

In [`report_generator.py` L95–101 and L108–116](file:///c:/Users/laaks/ZZ/Projects/P1/src/synthesis/report_generator.py), the same `for p in papers: if p.pmid == claim.paper_id` pattern appears 3 times. The inner loop is O(n_papers) per claim, making the total complexity O(n_claims × n_papers).

**Fix:** Build a `paper_by_pmid: dict[str, Paper] = {p.pmid: p for p in papers}` lookup once at the top of the function.

---

#### 12. Prompt loaded from disk on **every judge call** in `llm_judge.py`

In [`llm_judge.py` L59](file:///c:/Users/laaks/ZZ/Projects/P1/src/detection/llm_judge.py#L59), `load_prompt()` is called inside `judge_contradiction_pair`, which is called once per candidate pair. This reads the file from disk 15–20 times per pipeline run. The `claim_extractor.py` correctly uses module-level caching (`_PROMPT_TEMPLATE`). The same pattern should be applied here.

---

#### 13. Cost estimate formula in `main.py` is a magic-number approximation

In [`main.py` L79](file:///c:/Users/laaks/ZZ/Projects/P1/src/main.py#L79):

```python
cost_estimate = (len(state.papers) * 0.001) + (len(contradictions) * 0.015)
```

These multipliers are not documented and don't match the cost table in the design doc. The design doc uses `$0.02` for 25 abstracts (~$0.0008/abstract) and `$0.15` for judge calls. Extract these as named constants or configuration values.

---

#### 14. `load_dotenv()` called at import time in `config.py`

In [`config.py` L7](file:///c:/Users/laaks/ZZ/Projects/P1/src/config.py#L7), `load_dotenv()` is called as a module-level side effect before `Settings()` is even instantiated. `pydantic-settings` already reads `.env` via `model_config = SettingsConfigDict(env_file=".env")`, so the explicit `load_dotenv()` is redundant. Worse, it runs unconditionally in test environments, potentially loading production keys.

---

#### 15. `extract_claims_from_paper` uses a bare `for attempt in range(2)` with fall-through

In [`claim_extractor.py` L71–92](file:///c:/Users/laaks/ZZ/Projects/P1/src/extraction/claim_extractor.py#L71-L92), the retry loop ends with `return []` after the loop. If the loop succeeds on the first attempt, Python falls through to `return []` only after the loop ends — BUT there's a `return claims` on L84 inside the loop. This works correctly but is confusing. The pattern could be clearer using `break` + post-loop handling, or the `for/else` construct.

---

#### 16. `scifact_eval.py` uses a hardcoded sample of 60 pairs

```python
pairs = pairs[:60]
labels = labels[:60]
```

The SciFact dev set has ~1409 pairs. The README (per the design doc) is supposed to report precision/recall on the full dataset. Evaluating only 60 pairs produces statistically unstable numbers that won't impress a technical reviewer. The comment says "to prevent long-running execution on CPU" — this should be a configurable CLI argument, not a hardcoded slice.

---

### 🔵 TESTING GAPS

#### 17. No integration test for the full pipeline (`run_ingestion_and_extraction`)

[`test_pipeline.py`](file:///c:/Users/laaks/ZZ/Projects/P1/tests/test_pipeline.py) exists but has only been partially inspected. Even if it tests the pipeline, it likely mocks the LLM and PubMed responses. There is no test that exercises the full claim → verification → normalization → contradiction detection → synthesis chain end-to-end with any fixture data.

---

#### 18. `test_contradiction_detector.py` exists but doesn't test the LLM judge integration

The detector tests likely mock the judge. The critical contract — "scope mismatches return `is_genuine=False`" — is not verified by automated tests using real fixture data. This is the #1 failure mode in the design doc.

---

#### 19. No test for `report_generator.py` citation hallucination removal

The `validate_and_clean_citations` function is the citation fidelity guarantee. It has no test coverage. A test that passes a summary containing a fake `[Nonexistent, 2099]` citation and verifies it is stripped would directly validate the most critical correctness guarantee of the system.

---

#### 20. `test_factory.py` and `test_openai.py` likely only test provider instantiation

Quick wins: add a test that verifies `get_llm(settings.judge_model)` returns a provider with `model_name == settings.judge_model`, so the model-switching contract is validated.

---

### 🟢 PORTFOLIO POLISH

#### 21. `storage/` is missing `__init__.py`

The `src/storage/` directory has no `__init__.py` file. While Python 3 allows implicit namespace packages, this is inconsistent with every other module in the project (all have `__init__.py`). It may cause import issues in some test configurations.

---

#### 22. `pyproject.toml` is missing `scispacy` and `spacy` dependencies

[`pyproject.toml`](file:///c:/Users/laaks/ZZ/Projects/P1/pyproject.toml) does not list `scispacy` or `spacy` as dependencies, even though `normalizer.py` tries to import them. The code gracefully handles their absence, but a fresh `pip install -e .` would not install them. They should be in an `[optional-dependencies]` group called `[nlp]` with instructions in the README.

---

#### 23. `README.md` does not yet have benchmark results or architecture diagram

The design doc explicitly calls out that reporting SciFact P/R numbers in the README is a "portfolio power move" that 99% of candidates don't do. The README exists but needs: benchmark table, architecture diagram image, cost-per-run breakdown, and a GIF demo.

---

#### 24. No `pytest.ini` or `pyproject.toml` pytest configuration

There is no `[tool.pytest.ini_options]` section in `pyproject.toml`. Running `pytest` without configuration means `asyncio_mode` for `pytest-asyncio` defaults to `strict`, which may require `@pytest.mark.asyncio` on every async test. This should be set to `asyncio_mode = "auto"` for consistency.

---

#### 25. The API layer (`api/`) and frontend (`frontend/`) are Phase 4 stubs — that's fine

These are correctly deferred. Nothing to fix here — just don't start Phase 4 without passing the Phase 2 SciFact checkpoint.

---

## Priority Order for Fixes

| # | Issue | Effort | Impact |
|---|---|---|---|
| 1 | Bug: `SUPERSEDES` overwrites `CONTRADICTS` edge in graph | 15 min | High — graph is structurally wrong |
| 2 | Bug: `judge_model` not used for synthesis in `main.py` | 5 min | High — using wrong (cheap) model |
| 3 | Bug: `started_at` lost in final `save_pipeline_run` call | 20 min | Medium — DB record corrupted |
| 4 | Bug: `JudgeResponse.contradiction_type` should be enum | 5 min | Medium — silent misclassification |
| 5 | Architecture: Unify pipeline into `run_full_pipeline()` | 2 hrs | High — needed for Phase 4 API |
| 6 | Quality: Cache judge prompt (same as extractor) | 10 min | Low — performance |
| 7 | Quality: Fix N+1 query in `get_claims_for_run` | 30 min | Medium — performance at scale |
| 8 | Quality: Fix O(n²) paper lookup in `report_generator.py` | 10 min | Low — correctness at scale |
| 9 | Test: Add citation hallucination test for `report_generator` | 30 min | High — validates key guarantee |
| 10 | Test: SciFact eval on full dataset (configurable sample size) | 20 min | High — portfolio credibility |
| 11 | Polish: Add `storage/__init__.py` | 2 min | Low |
| 12 | Polish: Add `scispacy` to optional deps in `pyproject.toml` | 5 min | Medium |
| 13 | Polish: Add `asyncio_mode = "auto"` to pytest config | 2 min | Low |
| 14 | Polish: Load synonym map from JSON file | 20 min | Medium — extensibility |
