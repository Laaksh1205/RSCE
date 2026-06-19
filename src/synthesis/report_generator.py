import re
import logging

from src.models.paper import Paper
from src.models.claim import Claim
from src.models.contradiction import ContradictionPair
from src.models.report import SynthesisReport
from src.graph.claim_graph import build_claim_graph, compute_consensus_scores
from src.llm.base import LLMProvider

logger = logging.getLogger(__name__)

def citation_matches_paper(cit_str: str, paper: Paper) -> bool:
    """Helper to check if a citation string matches a paper's author and year.
    
    Tolerates formats like 'Adams, 2024', 'Adams et al., 2024', and 'Adams et al. 2024'.
    """
    cit_clean = cit_str.replace("et al.", "").replace("et al", "").strip().lower()
    
    # Extract year from citation string (usually 4 digits)
    year_match = re.search(r"\b\d{4}\b", cit_clean)
    if not year_match:
        return False
    cit_year = int(year_match.group(0))
    if cit_year != paper.year:
        return False
        
    # Check if the author's name is present
    first_author = paper.authors[0] if paper.authors else "Unknown"
    author_last_name = first_author.split()[-1].lower() if first_author else "unknown"
    
    # Remove year from cit_clean to match author name
    cit_author_part = re.sub(r"\b\d{4}\b", "", cit_clean).strip().strip(",").strip()
    
    return author_last_name in cit_author_part or cit_author_part in author_last_name

def validate_and_clean_citations(summary_text: str, papers: list[Paper]) -> str:
    """Parse all [Author, Year] references in the text.
    
    Verifies that each matches a paper in the corpus.
    If it is valid, normalizes it to '[LastName, Year]'.
    If it is invalid, removes it.
    """
    pattern = r"\[([^\]]+)\]"
    
    def repl(match):
        cit_content = match.group(1)
        for paper in papers:
            if citation_matches_paper(cit_content, paper):
                first_author = paper.authors[0] if paper.authors else "Unknown"
                author_last_name = first_author.split()[-1] if first_author else "Unknown"
                return f"[{author_last_name}, {paper.year}]"
        # Citation did not match any paper, strip it
        logger.warning(f"Removing invalid / hallucinated citation: [{cit_content}]")
        return ""
        
    cleaned_text = re.sub(pattern, repl, summary_text)
    # Clean up double spaces that might result from stripping citations
    cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()
    # Clean up punctuation formatting issues near stripped citations
    cleaned_text = cleaned_text.replace(" .", ".").replace(" ,", ",").replace("()", "").replace("[]", "")
    return cleaned_text

def detect_knowledge_gaps(
    claims: list[Claim],
    contradictions: list[ContradictionPair],
    papers: list[Paper]
) -> list[str]:
    """Detect claims asserted by only 1 paper that have not been supported or contradicted."""
    from collections import defaultdict
    import itertools

    paper_by_pmid = {p.pmid: p for p in papers}
    
    # 1. Map entity IDs to their most complete text names
    entity_names = {}
    for claim in claims:
        for e in claim.entities:
            eid = e.canonical_id if e.canonical_id else e.text
            if eid not in entity_names or len(e.text) > len(entity_names[eid]):
                entity_names[eid] = e.text

    # 2. Group claims by topic: (sorted_entity_pair, claim_type)
    topic_to_claims = defaultdict(list)
    for claim in claims:
        ent_ids = []
        for e in claim.entities:
            eid = e.canonical_id if e.canonical_id else e.text
            if eid and eid not in ent_ids:
                ent_ids.append(eid)
        
        if len(ent_ids) >= 2:
            for ent_a, ent_b in itertools.combinations(ent_ids, 2):
                pair = (ent_a, ent_b) if ent_a < ent_b else (ent_b, ent_a)
                topic_key = (pair[0], pair[1], claim.claim_type)
                topic_to_claims[topic_key].append(claim)

    # 3. Identify contradiction claim IDs
    contradicted_claim_ids = set()
    for pair in contradictions:
        contradicted_claim_ids.add(str(pair.claim_a.id))
        contradicted_claim_ids.add(str(pair.claim_b.id))

    # 4. Scan topics for knowledge gaps
    knowledge_gaps = []
    for (ent_a, ent_b, claim_type), topic_claims in topic_to_claims.items():
        papers_for_topic = {c.paper_id for c in topic_claims}
        if len(papers_for_topic) == 1:
            # Check if any claim in this topic is contradicted
            is_contradicted = any(str(c.id) in contradicted_claim_ids for c in topic_claims)
            if not is_contradicted:
                name_a = entity_names.get(ent_a, ent_a)
                name_b = entity_names.get(ent_b, ent_b)
                pmid = list(papers_for_topic)[0]
                p = paper_by_pmid.get(pmid)
                if p:
                    first_author = p.authors[0] if p.authors else "Unknown"
                    author_last = first_author.split()[-1] if first_author else "Unknown"
                    paper_ref = f"{author_last} et al. ({p.year})"
                else:
                    paper_ref = f"PMID {pmid}"

                gap_desc = (
                    f"The {claim_type.value.lower()} relationship between {name_a} and {name_b} "
                    f"was asserted by {paper_ref} but has not been supported or contradicted by any other studies."
                )
                knowledge_gaps.append(gap_desc)

    return sorted(knowledge_gaps)

async def generate_synthesis_report(
    contradictions: list[ContradictionPair],
    claims: list[Claim],
    papers: list[Paper],
    llm: LLMProvider,
) -> SynthesisReport:
    """Generate a citation-grounded synthesis report based on the claims and contradictions.
    
    1. Builds the claim graph and computes consensus scores.
    2. Constructs a structured context of papers, claims, and contradictions.
    3. Prompts the LLM to write a paragraph with inline citations.
    4. Validates and normalizes citations, removing invalid ones.
    5. Returns a SynthesisReport object.
    """
    # 1. Build graph and compute consensus scores
    G = build_claim_graph(claims, contradictions, papers)
    consensus_scores = compute_consensus_scores(G)
    
    # 2. Build prompt context
    paper_by_pmid = {p.pmid: p for p in papers}

    def get_paper_ref(pmid: str) -> str:
        p = paper_by_pmid.get(pmid)
        if not p:
            return "Unknown"
        first_author = p.authors[0] if p.authors else "Unknown"
        author_last = first_author.split()[-1] if first_author else "Unknown"
        return f"{author_last}, {p.year}"

    papers_str = ""
    for idx, paper in enumerate(papers):
        authors_str = ", ".join(paper.authors) if paper.authors else "Unknown"
        papers_str += f"- [{idx + 1}] {authors_str} ({paper.year}). \"{paper.title}\". PMID: {paper.pmid}.\n"

    claims_str = ""
    for idx, claim in enumerate(claims):
        claim_id_str = str(claim.id)
        score = consensus_scores.get(claim_id_str, 1.0)
        
        # Find paper citation key
        paper_ref = get_paper_ref(claim.paper_id)
        claims_str += f"- Claim {idx + 1} (Source: [{paper_ref}]): \"{claim.text}\" (Polarity: {claim.polarity.value}, Consensus Score: {score:.2f})\n"

    contradictions_str = ""
    for idx, pair in enumerate(contradictions):
        c_a_ref = get_paper_ref(pair.claim_a.paper_id)
        c_b_ref = get_paper_ref(pair.claim_b.paper_id)
        
        contradictions_str += f"- Contradiction {idx + 1}: Claim from [{c_a_ref}] contradicts claim from [{c_b_ref}].\n"
        contradictions_str += f"  Type: {pair.contradiction_type.value}\n"
        contradictions_str += f"  Explanation: {pair.explanation}\n"
        if pair.scope_note:
            contradictions_str += f"  Scope Note: {pair.scope_note}\n"
        if pair.temporal_resolution:
            contradictions_str += f"  Temporal Resolution: {pair.temporal_resolution}\n"
            
    prompt = (
        "You are an expert biomedical synthesis assistant. Summarize the research findings below into a cohesive, scientific narrative summary paragraph.\n\n"
        "Input Data:\n"
        f"Papers:\n{papers_str}\n"
        f"Claims:\n{claims_str}\n"
        f"Contradictions:\n{contradictions_str}\n\n"
        "Instructions for Writing the Synthesis:\n"
        "1. Synthesize the findings into a single, cohesive, high-quality paragraph.\n"
        "2. Discuss the general consensus, highlighting claims with high consensus scores.\n"
        "3. Highlight critical contradictions/conflicts, detailing what the disagreement is about and quoting the explanation/type where relevant.\n"
        "4. Every assertion or statement you make MUST end with an inline citation in brackets matching the source paper (e.g., [LastName, Year]). You must cite the papers using this exact format.\n"
        "5. If a newer study contradicts or supersedes an older one, describe the temporal progression.\n"
        "6. Do NOT invent or include any references that are not present in the input papers above. Every citation must be real and match one of the papers.\n\n"
        "Paragraph Synthesis:"
    )
    
    # 3. Call LLM to generate summary
    try:
        raw_summary = await llm.generate_text(prompt, temperature=0.3)
    except Exception as e:
        logger.error(f"Failed to generate narrative summary: {e}")
        raw_summary = "Error generating narrative synthesis report."
        
    # 4. Clean and validate citations
    cleaned_summary = validate_and_clean_citations(raw_summary, papers)
    
    # 5. Detect knowledge gaps
    gaps = detect_knowledge_gaps(claims, contradictions, papers)
    
    # 6. Return SynthesisReport
    return SynthesisReport(
        summary=cleaned_summary,
        contradictions=contradictions,
        consensus_scores={str(cid): float(score) for cid, score in consensus_scores.items()},
        knowledge_gaps=gaps,
        total_papers=len(papers),
        total_claims=len(claims),
        metadata={}
    )
