# Research Synthesis & Contradiction Engine — Design Foundations

> [!NOTE]
> This document is the single source of truth for the project's design rationale. Every implementation decision should trace back here.

---

## 1. What problem are we solving?

**Primary:** Researchers cannot efficiently detect when two papers make contradictory factual claims about the same phenomenon — e.g., "Drug X reduces inflammation" vs. "Drug X has no effect on inflammation markers."

**Secondary:** Even when they find contradictions, they lack a structured way to *trace the provenance* of each claim (which paper, which section, with what confidence) to decide which claim to trust.

**Root cause:** Literature review is a manual, sequential, unstructured reading process. It doesn't scale beyond ~30–50 papers, yet modern fields have thousands. Existing tools (Semantic Scholar, Connected Papers, Elicit) help you *find* papers but don't *reason across* them.

---

## 2. Who has this problem?

| Persona | Pain point | Willingness to pay |
|---|---|---|
| **PhD students / postdocs** | Literature reviews for thesis; don't want to miss a prior contradicting their hypothesis | Low (institutional) |
| **Academic researchers** | Grant proposals, systematic reviews, meta-analyses | Medium |
| **Biotech / pharma scientists** | Competitive intelligence, target validation | **High** — missed contradiction = failed trial |
| **Financial analysts / quant researchers** | Contradictory findings in economic studies, market models | High |
| **AI/ML researchers** | Rapidly shifting SOTA claims, benchmark contradictions | Medium |

**Primary target for portfolio:** Biotech/pharma is the highest-value signal. Frame the demo around a concrete biomedical claim (e.g., "BRCA1 mutations increase breast cancer risk") with real PubMed papers.

---

## 3. Why is the current solution not enough?

| Tool | What it does | What it misses |
|---|---|---|
| **Google Scholar / PubMed search** | Finds papers by keyword | Cannot compare *claims within* papers |
| **Connected Papers / ResearchRabbit** | Citation graph visualization | No semantic understanding of content |
| **Elicit** | Structured extraction from papers | Answers one question at a time; no contradiction detection |
| **Semantic Scholar** | Relevance + influence scoring | No claim-level analysis |
| **ChatGPT / Perplexity** | Can summarize | Hallucination-prone; no structured claim graph; stale |
| **Traditional systematic review** | Rigorous | Takes 6–18 months and a team |

**Gap:** No tool today builds a *claim-level knowledge graph* with per-claim citations, contradiction links, and temporal weighting. That's the unique value.

---

## 4. What does success look like?

**For the portfolio demo:**
- Given a research topic (e.g., "Does intermittent fasting improve insulin sensitivity?"), the system ingests 20–50 papers, extracts ~100–300 claims, identifies 5–15 genuine contradictions with supporting evidence from both sides, and outputs a structured synthesis report with confidence scores and citations.
- A recruiter or engineer can run it themselves in under 2 minutes.

**For a real product:**
- Precision ≥ 75% on contradiction pairs (few false positives)
- Recall ≥ 60% on known contradictions in a curated benchmark
- Every output claim links back to ≥ 1 specific paper + section
- Time-to-insight: from topic query to synthesis report in < 5 minutes

---

## 5. What goes into the system (inputs)?

| Input type | Examples |
|---|---|
| **Research topic / query** | "Does aspirin reduce Alzheimer's risk?" |
| **Paper corpus** | arXiv IDs, PubMed IDs, DOIs, PDFs, raw text |
| **Corpus source** | arXiv API, PubMed API, Semantic Scholar API, user-uploaded PDFs |
| **Optional constraints** | Date range (e.g., 2015–2024), journals, sample size threshold |
| **Optional seed claims** | "I believe X is true — find contradicting evidence" |

---

## 6. What should come out (outputs)?

| Output | Description |
|---|---|
| **Claim-Evidence Graph** | Nodes = claims; edges = supports / contradicts / supersedes |
| **Contradiction Report** | Pairs of conflicting claims with citations, confidence, and explanation |
| **Grounded Summary** | Narrative synthesis where every sentence links to a claim node (with citation) |
| **Consensus Score** | Per-claim: what fraction of evidence supports vs. contradicts |
| **Temporal Analysis** | Is this contradiction resolved over time? (newer papers converge or diverge?) |
| **Knowledge Gaps** | Claims asserted but never tested or replicated |

---

## 7. What is the core entity / object?

```
Claim {
  id: UUID
  text: str                    # "Drug X reduces tumor size by 30%"
  normalized_text: str         # canonicalized for deduplication
  paper_id: str                # source paper
  section: str                 # Methods / Results / Discussion
  authors: List[str]
  year: int
  embedding: Vector[768]       # for similarity search (PubMedBERT-sized)
  confidence_score: float      # model's confidence in extraction (0–1)
  claim_type: Enum             # CAUSAL | CORRELATIONAL | QUANTITATIVE | DEFINITIONAL | MECHANISTIC
  polarity: Enum               # POSITIVE | NEGATIVE | NEUTRAL
                               # "X increases Y" = POSITIVE, "X does not affect Y" = NEUTRAL
  entities: List[Entity]       # extracted named entities (drugs, diseases, genes)
  population: str              # "mice", "human adults aged 40–60", "in vitro HeLa cells"
  context: str                 # conditions under which claim holds: dosage, duration, etc.
  sample_size: Optional[int]   # if extractable, critical for weighting
  study_design: Enum           # META_ANALYSIS | RCT | COHORT | CASE_CONTROL | IN_VITRO | CASE_REPORT | REVIEW
  is_primary_finding: bool     # true if from Results/Conclusions; false if background/intro citation
}

Entity {
  text: str                    # "aspirin"
  canonical_id: str            # MeSH:D001241 or CHEBI:15365
  entity_type: Enum            # DRUG | GENE | DISEASE | PROTEIN | PATHWAY | BIOMARKER
}

ContradictionPair {
  claim_a: Claim
  claim_b: Claim
  contradiction_score: float   # 0–1, higher = more clearly contradictory
  contradiction_type: Enum     # see taxonomy below
  explanation: str             # human-readable explanation of why these contradict
  scope_note: str              # e.g., "Claim A is about mice; Claim B is about humans"
  temporal_resolution: Optional[str]  # "Claim B (2023) supersedes Claim A (2018)" or null
  is_genuine: bool             # false if scope mismatch makes it a pseudo-contradiction
}
```

### Contradiction Taxonomy

| Type | Example | Is it a real contradiction? |
|---|---|---|
| **DIRECT_NEGATION** | "X causes Y" vs. "X does not cause Y" (same population, same conditions) | ✅ Always |
| **QUANTITATIVE_CONFLICT** | "X reduces Y by 30%" vs. "X reduces Y by 2% (not significant)" | ✅ Usually |
| **DIRECTION_REVERSAL** | "X increases Y" vs. "X decreases Y" | ✅ Always |
| **SCOPE_MISMATCH** | "X causes Y in mice" vs. "X does not cause Y in humans" | ⚠️ Not necessarily — flag but don't assert |
| **TEMPORAL_SUPERSESSION** | Older paper says X; newer, larger study refutes X | ✅ Likely resolved |
| **METHODOLOGICAL_CONFLICT** | Same question, opposite results due to different study designs (RCT vs. observational) | ⚠️ Context-dependent |

> [!IMPORTANT]
> The `population` and `context` fields on `Claim` are **critical**. Without them, the system will generate massive numbers of false contradictions ("X works in mice" vs. "X doesn't work in humans" is NOT a contradiction — it's a scope difference). This is the #1 reason similar projects fail.

This is your key differentiator — claim as a **first-class object**, not a paragraph.

---

## 8. What are the major subproblems / modules?

These modules mirror the architecture in Section 13. Each stage receives a defined data shape and produces a defined output.

```
┌──────────────────────────────────────────────────────────────┐
│  1. INGESTION                                                │
│     - PubMed E-utilities API (abstracts + metadata)          │
│     - Phase 3: PubMed Central OA XML (full text, structured) │
│     - Phase 3 fallback: PyMuPDF for non-OA PDFs             │
│                                                              │
│     Output: List[Paper]                                      │
│       Paper = { pmid, title, authors, year, journal,         │
│                 abstract_text, full_text? }                   │
└─────────────────┬────────────────────────────────────────────┘
                  │
┌─────────────────▼────────────────────────────────────────────┐
│  2. CLAIM EXTRACTION + VALIDATION                            │
│     - LLM prompt → structured JSON (Pydantic-validated)      │
│     - Quote-anchor verification (see Section 8a below)       │
│     - Confidence filtering (reject claims < threshold)       │
│     - Embedding generation (all-MiniLM-L6-v2, local)         │
│                                                              │
│     Output: List[Claim] (with embeddings populated)          │
└─────────────────┬────────────────────────────────────────────┘
                  │
┌─────────────────▼────────────────────────────────────────────┐
│  3. CLAIM STORE                                              │
│     - SQLite: paper metadata + claim records                 │
│     - FAISS: vector index over claim embeddings              │
│                                                              │
│     Output: FAISS index + SQLite DB (query interface)        │
└─────────────────┬────────────────────────────────────────────┘
                  │
┌─────────────────▼────────────────────────────────────────────┐
│  4. CONTRADICTION DETECTION                                  │
│     - Stage A: FAISS ANN → top-K similar pairs per claim     │
│     - Stage B: NLI cross-encoder (DeBERTa) → entail/contra   │
│     - Stage C: LLM judge for scope/genuineness assessment    │
│                                                              │
│     Output: List[ContradictionPair] (scored, typed, ranked)  │
└─────────────────┬────────────────────────────────────────────┘
                  │
┌─────────────────▼────────────────────────────────────────────┐
│  5. GRAPH CONSTRUCTION (Phase 3+)                            │
│     - Nodes: Claims, Papers, Entities                        │
│     - Edges: SUPPORTS, CONTRADICTS, CITES, SUPERSEDES        │
│     - Storage: NetworkX (MVP) → Neo4j (production story)     │
│                                                              │
│     Output: NetworkX DiGraph (serializable to JSON)          │
└─────────────────┬────────────────────────────────────────────┘
                  │
┌─────────────────▼────────────────────────────────────────────┐
│  6. SYNTHESIS & GENERATION                                   │
│     - RAG over claims (NOT raw paper text)                   │
│     - Citation-grounded generation: every sentence = claim   │
│     - Contradiction narrative with [Author, Year] inline     │
│                                                              │
│     Output: SynthesisReport { summary, contradictions,       │
│                                consensus_scores, citations } │
└─────────────────┬────────────────────────────────────────────┘
                  │
┌─────────────────▼────────────────────────────────────────────┐
│  7. PRESENTATION                                             │
│     - MVP: rich CLI terminal output                          │
│     - Full: Next.js + Cytoscape.js interactive graph         │
│     - Export: JSON graph, PDF report                         │
└──────────────────────────────────────────────────────────────┘
```

### 8a. Quote-Anchor Verification Algorithm

Every extracted claim must include a `quote_anchor` — a verbatim 10–20 word excerpt from the source text. Verification works as follows:

1. **Normalize** both the quote_anchor and source text (lowercase, strip punctuation, collapse whitespace)
2. **Fuzzy match** using `rapidfuzz.fuzz.partial_ratio(normalized_quote, normalized_source)`
3. **Threshold:** score ≥ 85 → PASS; score 70–84 → FLAG (keep claim but mark `confidence_score *= 0.5`); score < 70 → REJECT (discard claim)
4. **Log** all rejections for prompt debugging

> [!TIP]
> In practice, ~5–10% of claims will be rejected by quote-anchor verification. This is healthy — it means the mechanism is catching hallucinations. If rejection rate exceeds 20%, the extraction prompt needs iteration.

### 8b. Error Handling & Graceful Degradation

| Failure scenario | Symptom | System behavior |
|---|---|---|
| **PubMed returns < 10 papers** | Niche or misspelled query | Warn user: "Only N papers found. Results may be incomplete." Proceed if ≥ 5. Abort if < 5 with suggestion to broaden query. |
| **LLM extraction fails on some abstracts** | Malformed JSON, timeout, rate limit | Retry once with exponential backoff. If still fails, skip that paper. Log it. Proceed with remaining papers. Report "N/M papers successfully processed." |
| **LLM returns 0 claims for a paper** | Abstract is purely methodological or a review with no assertions | Skip paper silently. This is normal (~10% of abstracts). |
| **FAISS returns no candidates above similarity threshold** | No claims are semantically related enough | Report: "No contradictions detected. Papers in this corpus appear to be in consensus or discuss non-overlapping topics." This is a valid result, not an error. |
| **NLI model disagrees with LLM judge** | NLI says contradiction; judge says scope mismatch (or vice versa) | Trust the LLM judge (it has access to population/context metadata). Log disagreement for analysis. |
| **API rate limiting** | PubMed: 3 req/sec; Semantic Scholar: 100 req/5min | Built-in rate limiter with `asyncio.Semaphore`. Never exceed limits. Add exponential backoff on 429 responses. |
| **Total pipeline failure** | Unhandled exception anywhere | Catch at pipeline level. Save all intermediate results (claims extracted so far, papers fetched so far) to SQLite. User can resume from last successful stage. |

### 8c. Latency Budget & Concurrency Strategy

Target: **< 2 minutes** end-to-end for 25 papers.

| Stage | Sequential time | With concurrency | Strategy |
|---|---|---|---|
| 1. Ingestion (25 PubMed fetches) | ~8 sec | **~3 sec** | `asyncio.gather` with 3 concurrent requests (respects PubMed 3 req/sec limit) |
| 2. Claim extraction (25 LLM calls) | ~75 sec (3 sec/call) | **~15 sec** | `asyncio.gather` with 5 concurrent LLM calls (typical API concurrency limit) |
| 3. Embedding (25×5 = 125 claims) | ~2 sec | **~2 sec** | Local model, batch encode all at once (`model.encode(all_claims)`) |
| 4a. FAISS ANN search | ~0.1 sec | **~0.1 sec** | In-memory, trivial at this scale |
| 4b. NLI scoring (~50 candidate pairs) | ~10 sec | **~10 sec** | Local model, batch inference |
| 4c. LLM judge (~15 ambiguous pairs) | ~45 sec | **~10 sec** | `asyncio.gather` with 5 concurrent calls |
| 5. Graph construction | ~0.5 sec | **~0.5 sec** | NetworkX, in-memory |
| 6. Synthesis (1 LLM call) | ~5 sec | **~5 sec** | Single call, can't parallelize |
| **Total** | **~145 sec** | **~45 sec** | 3× speedup from concurrency |

> [!IMPORTANT]
> The concurrency bottleneck is **LLM API calls** (extraction + judge). Using `asyncio.gather` with a semaphore of 5 brings the total well under 2 minutes. If using Gemini, the concurrency limit is generous (up to 30 QPM on free tier); if using OpenAI, check your rate limit tier.

---

## 9. What is the riskiest / unknown part?

**Ranked by risk:**

| Risk | Why it's hard | Mitigation |
|---|---|---|
| **False contradictions from scope mismatch** | "X works in mice" vs. "X doesn't work in humans" gets flagged as contradiction but isn't one. This is the #1 failure mode. | Extract `population` and `context` per claim; add `is_genuine` flag to `ContradictionPair`; train the LLM judge to distinguish scope difference from real contradiction |
| **Claim extraction quality** | LLMs hallucinate claims, miss implicit ones, or extract too granularly | Use structured output + validation; few-shot prompt with hand-verified examples; score extraction confidence; reject claims below threshold |
| **Contradiction detection precision** | Two papers may use different terminology for the same effect | Multi-stage pipeline: embeddings → NLI → LLM judge; entity normalization to canonical IDs |
| **PDF parsing** | Academic PDFs have tables, figures, equations that break naive parsers | Start with abstracts (Phase 1); add full text via PubMed Central XML (not PDF) in Phase 3 |
| **Scalability of contradiction search** | O(n²) pairwise comparison blows up at 1000+ claims | Embedding-based ANN (FAISS) to prune candidates; only compare claims sharing ≥ 1 entity |
| **Evaluation without ground truth** | Hard to know if you're finding *real* contradictions | Use SciFact + HealthVer datasets as benchmarks (see Section 12) |
| **Entity grounding** | "aspirin", "ASA", "acetylsalicylic acid" are the same entity | Use biomedical NER (scispaCy, PubMedBERT) + ontology linking (MeSH, CHEBI) |

**The single riskiest assumption:** That LLM-extracted claims are consistent enough across papers to be compared. Test this first before building anything else.

### Failure Modes & What to Do About Them

| Failure mode | Symptom | Impact | Countermeasure |
|---|---|---|---|
| **Over-extraction** | 50 claims from a 3-sentence abstract | Noise drowns real contradictions | Cap at ~5 claims per abstract; require each claim to contain a subject-verb-object with an entity |
| **Under-extraction** | Key finding from Results section is missed | False sense of consensus | Cross-validate: run extraction twice with different prompt variations; union the results |
| **Hallucinated claims** | Claim states something the paper never said | Catastrophic — undermines entire system credibility | Require every claim to include a verbatim quote anchor from the source text; verify anchor exists |
| **Synonym blindness** | "aspirin" and "acetylsalicylic acid" treated as unrelated | Missed contradictions between papers using different nomenclature | Entity normalization to canonical IDs (MeSH, CHEBI) before contradiction search |
| **False contradiction from population difference** | Mouse study vs. human study flagged as contradictory | Noisy output, user loses trust | Extract `population` field; require matching populations for `is_genuine = true` |
| **Overwhelming output** | 200 contradiction pairs, user can't process | Useless product | Rank by `contradiction_score`; show top 10 by default; group by entity/topic |

---

## 10. What is the smallest MVP that proves the idea?

**MVP definition:** A Python CLI tool that:

1. Takes a research question as input (e.g., `python main.py "Does metformin reduce cancer risk?"`)
2. Fetches 15–25 relevant PubMed abstracts via E-utilities API
3. Extracts 3–5 atomic claims per abstract using an LLM with structured output
4. Embeds claims → FAISS index → retrieves top-K candidate pairs
5. Runs NLI (DeBERTa cross-encoder) on candidates to classify entailment/contradiction
6. Outputs a **rich terminal report** (using `rich` library) showing:
   - Total papers ingested, total claims extracted
   - Top contradiction pairs ranked by score, with inline citations
   - A one-paragraph grounded summary with [Author, Year] references
7. Also dumps structured JSON for downstream use

**Why CLI with rich output instead of bare JSON:** A recruiter or interviewer can run it in a terminal and be impressed in 30 seconds. A JSON dump requires them to open a file and squint. Same effort to build, 10× better impression.

**Success criteria for MVP:**
- At least 3 genuine, human-verified contradictions found with correct citations
- Zero hallucinated claims (every claim traceable to a source abstract)
- Runs end-to-end in < 2 minutes on a research question
- API cost per run < $0.50

**What MVP deliberately skips:**
- Full-text PDF parsing (abstracts only)
- Graph visualization (Phase 4)
- Web UI (Phase 4)
- Temporal analysis (Phase 5)
- Entity normalization to ontology IDs (Phase 3)
- Production database (SQLite only)

**Time to MVP:** 3–4 focused days.

---

## 11. What technology is actually needed?

### Core Stack

| Layer | Technology | Why |
|---|---|---|
| **Paper APIs** | PubMed E-utilities, Semantic Scholar API | Free, well-documented, no scraping |
| **Full-text (Phase 3)** | PubMed Central OA XML (not PDF) | Structured XML is 10× easier to parse than PDF; covers ~8M open-access papers |
| **PDF fallback** | PyMuPDF (`fitz`) + `pdfplumber` | Only for papers not in PMC OA |
| **LLM (extraction)** | Gemini 2.5 Flash (fast, cheap) or GPT-4.1 mini | Structured output mode; abstracts fit easily in context |
| **LLM (judge/synthesis)** | Gemini 2.5 Pro or GPT-4.1 | Higher reasoning for contradiction judgment and synthesis |
| **Claim extraction** | LLM with structured JSON output (Pydantic validation) | Reliability + parseable |
| **Embeddings** | `all-MiniLM-L6-v2` (free, local, fast) or Gemini embeddings | Semantic similarity; local = no cost for embeddings |
| **NLI** | `cross-encoder/nli-deberta-v3-large` (HuggingFace) | Best open NLI model; runs locally on CPU |
| **Vector search** | FAISS (all phases) | ANN for candidate pairs; no need for managed DB at this scale |
| **Graph** | NetworkX (MVP) → Neo4j (production story) | Claim-evidence relationships |
| **Orchestration** | Plain async Python (`asyncio` + `aiohttp`) | No framework dependency; easy to explain in interviews |
| **Backend** | FastAPI | Clean REST API for UI |
| **Frontend** | Next.js + Cytoscape.js | Interactive graph visualization + server-side rendering |
| **Database** | SQLite (all MVP phases) | Paper + claim metadata |
| **CLI output** | `rich` (Python) | Beautiful terminal reports for the MVP demo |

### Cost Estimate (Self-funded Portfolio Project)

| Item | Cost per run (25 papers) | Monthly (10 runs) |
|---|---|---|
| PubMed API | Free | Free |
| Semantic Scholar API | Free (100 req/5min) | Free |
| Gemini 2.5 Flash (extraction) | ~$0.02 (25 abstracts × ~200 tokens each) | $0.20 |
| Gemini 2.5 Pro (judge + synthesis) | ~$0.15 (10 contradiction pairs + 1 synthesis) | $1.50 |
| NLI model | Free (local CPU) | Free |
| Embeddings (local) | Free | Free |
| **Total** | **~$0.17/run** | **~$1.70/month** |

> [!TIP]
> Using a local sentence transformer for embeddings and local DeBERTa for NLI keeps the per-run cost under $0.20. The only paid component is the LLM for claim extraction and synthesis.

### What you don't need (yet):
- Kubernetes, Docker (add a Dockerfile in Phase 5 for portfolio polish, but don't orchestrate)
- Fine-tuned models (pre-trained NLI + LLM prompting is sufficient)
- A managed vector database (FAISS handles 50k+ claims easily)
- LangChain/LangGraph (plain Python is easier to debug and explain in interviews)

---

## 12. How will we evaluate whether it works?

### Existing Benchmark Datasets (Free Ground Truth)

You don't need to create evaluation data from scratch. These datasets give you labeled claim-evidence pairs:

| Dataset | What it provides | How to use it |
|---|---|---|
| **[SciFact](https://github.com/allenai/scifact)** | 1,409 scientific claims, each labeled SUPPORTS / REFUTES / NOT_ENOUGH_INFO against a corpus of 5,183 abstracts | Gold standard for your contradiction detection pipeline. Run your NLI stage on SciFact claims and measure precision/recall against their labels. |
| **[HealthVer](https://github.com/sarrouti/HealthVer)** | 14,330 health-related claim-evidence pairs from PubMed abstracts | Larger evaluation set, specifically biomedical. Good for stress-testing. |
| **[MultiVerS](https://github.com/dwadden/multivers)** | Multi-sentence scientific claim verification | Tests whether your system handles complex, multi-part claims. |

> [!TIP]
> **Portfolio power move:** Report your system's precision and recall on SciFact in the README. This puts hard numbers on your portfolio project, which 99% of candidates don't do.

### Automated Metrics

| Metric | Target | How to compute |
|---|---|---|
| **Claim extraction precision** | ≥ 85% | Of extracted claims, what % are real factual assertions? Sample 50, human-label. |
| **Claim extraction recall** | ≥ 70% | Manually annotate 5 papers with expected claims; measure what % are found. |
| **Contradiction detection precision** | ≥ 75% | Of detected pairs, what % are genuine contradictions? Use SciFact labels. |
| **Contradiction detection recall** | ≥ 60% | Of known contradictions in SciFact REFUTES set, what % are found? |
| **Citation fidelity** | 100% | Every output claim must trace to a specific paper. Hard constraint — no exceptions. |
| **False contradiction rate** | ≤ 15% | Of flagged contradictions, what % are actually scope mismatches? |

### Human Evaluation (for portfolio)
- Pick a domain you know: "Does intermittent fasting improve metabolic markers?"
- Read 15 papers yourself. Annotate 3–5 real contradictions.
- Run your system. Do you find them?
- Critically: check for **false contradictions** — this is what interviewers will probe.

### The Demo Test
- A non-expert (recruiter) runs it, sees the contradiction report, and says "oh wow, I would not have found that."
- A technical interviewer runs it and asks "how do you handle scope mismatches?" — you have a clear answer.

---

## 13. What architecture supports this?

```
                    ┌──────────────────────────────┐
                    │     User Query / CLI / API    │
                    │  "Does metformin reduce       │
                    │   cancer risk?"               │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │   1. INGESTION               │
                    │   PubMed API → abstracts     │
                    │   (Phase 3: PMC XML → full)  │
                    └──────────────┬───────────────┘
                                   │ raw text + metadata
                    ┌──────────────▼───────────────┐
                    │   2. CLAIM EXTRACTION         │
                    │   LLM (structured output)     │
                    │   → List[Claim] per paper     │
                    │   + quote anchors for verify  │
                    └──────────────┬───────────────┘
                                   │ claims + embeddings
                    ┌──────────────▼───────────────┐
                    │   3. CLAIM STORE              │
                    │   SQLite (metadata)            │
                    │   + FAISS (vector index)       │
                    └──────────────┬───────────────┘
                                   │ candidate pairs (ANN top-K)
                    ┌──────────────▼───────────────┐
                    │   4. CONTRADICTION DETECTION  │
                    │   Stage A: NLI classifier      │
                    │   Stage B: LLM judge (scope    │
                    │            + genuineness)      │
                    └──────────────┬───────────────┘
                                   │ scored ContradictionPairs
                    ┌──────────────▼───────────────┐
                    │   5. GRAPH CONSTRUCTION       │
                    │   NetworkX graph:              │
                    │   Nodes: Claims, Papers        │
                    │   Edges: SUPPORTS, CONTRADICTS │
                    │          CITES, SUPERSEDES     │
                    └──────────────┬───────────────┘
                                   │ graph + ranked contradictions
                    ┌──────────────▼───────────────┐
                    │   6. SYNTHESIS GENERATOR      │
                    │   RAG over claim graph         │
                    │   (NOT raw paper text)         │
                    │   → citation-grounded report   │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │   7. PRESENTATION             │
                    │   MVP: rich CLI output         │
                    │   Full: Next.js + Cytoscape.js │
                    └──────────────────────────────┘
```

**Key design decisions:**

1. **Sequential pipeline, not parallel services.** Ingestion → Extraction → Storage → Detection → Graph → Synthesis. Each stage depends on the prior stage's output. Don't over-engineer this into microservices — it's a pipeline.

2. **LLM reads claims, not raw text, during synthesis.** This keeps context windows small (~2K tokens for 50 claims vs. ~50K for 25 papers), hallucination rate low, and every output sentence traceable to a specific claim node.

3. **Two-model strategy.** Cheap/fast model (Gemini Flash / GPT-4.1 mini) for bulk extraction. Expensive/smart model (Gemini Pro / GPT-4.1) for the judge + synthesis steps that require nuanced reasoning. This keeps costs under $0.20/run.

4. **Quote anchors for verification.** Every extracted claim must include a verbatim short quote from the source text. Verified via fuzzy matching (rapidfuzz, threshold ≥ 85). Claims below 70 are rejected; 70–84 are kept at half confidence. See Section 8a for details.

---

## 14. What is the implementation order?

### Phase 1 — Data + Extraction (Days 1–4) ✅ Proves the core value
1. Set up project structure (Python, `pyproject.toml`, virtual env)
2. Build PubMed fetcher (E-utilities API → abstracts + metadata)
3. Design claim extraction prompt (see Section 15); iterate on 5 papers
4. Implement structured output with Pydantic validation
5. Add quote-anchor verification (extracted quote must exist in source)
6. Store claims in SQLite with paper metadata
7. **Checkpoint:** manually verify extraction on 10 abstracts before proceeding

### Phase 2 — Contradiction Detection (Days 5–8) ✅ The core differentiator
8. Embed all claims with `all-MiniLM-L6-v2` (local, free)
9. Build FAISS index; retrieve top-K similar claim pairs per claim
10. Run `cross-encoder/nli-deberta-v3-large` on candidate pairs
11. Add LLM judge for ambiguous pairs (scope mismatch detection)
12. Build rich CLI output using `rich` library
13. **Checkpoint:** run on SciFact dataset; measure precision/recall
14. Output contradiction pairs as JSON + terminal report

### Phase 3 — Graph + Synthesis + Full Text (Days 9–12)
15. Build claim-evidence graph (NetworkX)
16. Add entity normalization (scispaCy + MeSH linking)
17. Build synthesis generator (RAG over claims, not raw text)
18. Generate citation-grounded report with [Author, Year] inline
19. Add PubMed Central XML ingestion for full-text papers
20. **Checkpoint:** end-to-end run on a real research question; verify output quality

### Phase 4 — UI + Demo (Days 13–17)
21. FastAPI backend wrapping the pipeline
22. Next.js frontend with Cytoscape.js graph visualization
23. Contradiction report view with drill-down to source paper
24. Claim detail panel (show quote anchor, metadata, confidence)
25. Polish demo: pick a compelling topic, pre-load results for fast demo

### Phase 5 — Portfolio Polish (Days 18–20)
26. README with architecture diagram, SciFact benchmark results, cost analysis
27. 2-minute demo video / GIF (Loom or terminal recording with `asciinema`)
28. Dockerfile for easy local running
29. Live hosted demo (Fly.io or Railway, free tier)
30. Add temporal analysis (newer paper as higher authority)

### Go/No-Go Checkpoints

| After Phase | Question | If NO: |
|---|---|---|
| Phase 1 | Does the LLM extract consistent, non-hallucinated claims from 10+ abstracts? | Stop. Iterate on the extraction prompt. Do not proceed. |
| Phase 2 | Does the system find ≥ 3 genuine contradictions in a known-contradictory corpus? | Iterate on NLI threshold + LLM judge prompt. |
| Phase 3 | Is the grounded summary accurate and every citation verifiable? | Debug synthesis prompt; add chain-of-citation verification. |

---

## 15. Prompt Engineering Strategy

> [!IMPORTANT]
> The extraction prompt is the single most important engineering artifact in this project. Budget 1–2 days for prompt iteration alone.

### Claim Extraction Prompt (Core Structure)

```
You are a scientific claim extractor. Given a paper abstract, extract atomic factual claims.

Rules:
1. Each claim must be a single, self-contained factual assertion.
2. Each claim must contain at least one named entity (drug, gene, disease, etc.).
3. Do NOT extract background statements, methodology descriptions, or future work.
4. For each claim, extract:
   - text: the claim in a normalized, third-person form
   - polarity: POSITIVE (X increases/causes Y), NEGATIVE (X decreases/prevents Y), or NEUTRAL (X has no effect on Y)
   - population: who/what was studied ("mice", "human adults", "in vitro")
   - context: conditions (dosage, duration, co-treatments)
   - quote_anchor: a verbatim 10-20 word excerpt from the abstract that this claim is based on
   - claim_type: CAUSAL | CORRELATIONAL | QUANTITATIVE | DEFINITIONAL | MECHANISTIC
   - study_design: META_ANALYSIS | RCT | COHORT | CASE_CONTROL | IN_VITRO | CASE_REPORT | REVIEW
5. Extract 3-7 claims per abstract. Prefer quality over quantity.

[FEW-SHOT EXAMPLES HERE — at least 3 diverse examples]
```

### Contradiction Judge Prompt (Core Structure)

```
You are a scientific contradiction judge. Given two claims from different papers, determine:

1. Do they discuss the same phenomenon? (same entities, same relationship)
2. If yes, do they contradict each other?
3. Is the contradiction genuine, or is it a scope mismatch?

A SCOPE MISMATCH is NOT a real contradiction:
- Different populations (mice vs. humans)
- Different dosages or durations
- Different outcome measures

Output:
- is_same_topic: bool
- is_contradiction: bool
- is_genuine: bool (false if scope mismatch)
- contradiction_type: DIRECT_NEGATION | QUANTITATIVE_CONFLICT | DIRECTION_REVERSAL | SCOPE_MISMATCH | TEMPORAL_SUPERSESSION | METHODOLOGICAL_CONFLICT
- explanation: 1-2 sentences
- scope_note: what differs between the two claims' contexts
```

---

## 16. How to Talk About This in an Interview

This is a resume project. You need to be able to answer these questions fluently:

| Question | Your answer framework |
|---|---|
| "What's the hardest problem you solved?" | False contradiction filtering — scope mismatches (mice vs. humans) generated 60% of initial contradictions. I solved this by extracting population/context metadata per claim and adding an LLM judge stage that distinguishes genuine contradictions from scope differences. |
| "Why not just use ChatGPT?" | ChatGPT summarizes text — it doesn't build a structured claim graph. My system makes every output sentence traceable to a specific claim, which links to a specific paper. That citation fidelity is what makes it trustworthy for researchers. Also, ChatGPT has no way to systematically compare claims across 25 papers. |
| "How did you evaluate it?" | I benchmarked on SciFact (1,409 labeled scientific claims) and achieved X% precision / Y% recall on contradiction detection. I also manually verified on a real research question in [your domain]. |
| "What would you do differently?" | I'd add entity normalization earlier — synonym blindness was a bigger problem than I expected. I'd also explore fine-tuning DeBERTa on SciFact specifically rather than using the general NLI checkpoint. |
| "How does this scale?" | The O(n²) pairwise problem is handled by FAISS — embedding similarity pre-filters candidate pairs so the expensive NLI model only runs on top-K. For 1000 claims, that's ~50 NLI calls instead of 500K. |
| "What's the system architecture?" | Sequential pipeline: Ingest → Extract → Store → Detect → Graph → Synthesize. Two LLM tiers: cheap model for bulk extraction, smart model for judgment/synthesis. Local models for embeddings and NLI to keep costs at $0.17/run. |

---

## Key Decisions to Make Before Building

> [!IMPORTANT]
> **Abstracts-only vs. full text:** Start with abstracts. Upgrade to PubMed Central XML (not PDF!) in Phase 3. PMC XML gives you structured sections, which is far easier than PDF parsing.

> [!IMPORTANT]
> **LLM choice:** Use Gemini 2.5 Flash for extraction (cheap, fast), Gemini 2.5 Pro for judgment/synthesis (smart). Support swapping to OpenAI models via a provider abstraction.

> [!WARNING]
> **Scope creep risk:** The claim graph, temporal analysis, entity linking, and PDF parsing are each significant projects. Follow the go/no-go checkpoints — do not proceed to Phase N+1 until Phase N passes its checkpoint.

> [!CAUTION]
> **The #1 portfolio killer:** A project that "kind of works" but has obvious false positives in the demo. One hallucinated claim or one obviously-not-a-contradiction in your top results will undermine the entire project. Prioritize precision over recall.

