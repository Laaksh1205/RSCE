import uuid
from src.models.paper import Paper
from src.models.claim import Claim, ClaimType, Polarity, StudyDesign, Entity, EntityType
from src.models.contradiction import ContradictionPair, ContradictionType
from src.synthesis.report_generator import detect_knowledge_gaps

def make_paper(pmid: str, author: str, year: int) -> Paper:
    return Paper(
        pmid=pmid,
        title="Sample Paper Title",
        authors=[author],
        year=year,
        journal="Sample Journal",
        abstract_text="Abstract content",
        full_text=None,
        doi="10.1000/xyz"
    )

def make_claim(id_str: str, pmid: str, year: int, entities: list[Entity], claim_type: ClaimType = ClaimType.CAUSAL) -> Claim:
    return Claim(
        id=uuid.UUID(id_str),
        text="Sample claim text",
        paper_id=pmid,
        section="Abstract",
        year=year,
        confidence_score=1.0,
        claim_type=claim_type,
        polarity=Polarity.POSITIVE,
        population="humans",
        context="general",
        quote_anchor="anchor",
        study_design=StudyDesign.RCT,
        sample_size=100,
        entities=entities
    )

def test_detect_knowledge_gaps():
    # Setup papers
    paper_1 = make_paper("pmid1", "Author One", 2020)
    paper_2 = make_paper("pmid2", "Author Two", 2021)
    papers = [paper_1, paper_2]

    # Setup entities
    ent_a = Entity(text="Metformin", canonical_id="MeSH:D001241", entity_type=EntityType.DRUG)
    ent_b = Entity(text="Breast Cancer", canonical_id="MeSH:D001943", entity_type=EntityType.DISEASE)
    ent_c = Entity(text="Aspirin", canonical_id="MeSH:D001242", entity_type=EntityType.DRUG)
    ent_d = Entity(text="Alzheimer", canonical_id="MeSH:D000544", entity_type=EntityType.DISEASE)

    # Claim 1 in paper 1 (Metformin vs Breast Cancer)
    claim_1 = make_claim("11111111-1111-1111-1111-111111111111", "pmid1", 2020, [ent_a, ent_b])
    # Claim 2 in paper 2 (Aspirin vs Alzheimer)
    claim_2 = make_claim("22222222-2222-2222-2222-222222222222", "pmid2", 2021, [ent_c, ent_d])
    claims = [claim_1, claim_2]

    # No contradictions initially
    contradictions = []

    gaps = detect_knowledge_gaps(claims, contradictions, papers)
    assert len(gaps) == 2
    assert any("Metformin" in g and "Breast Cancer" in g for g in gaps)
    assert any("Aspirin" in g and "Alzheimer" in g for g in gaps)

    # 1. Test replication: add claim 3 in paper 2 discussing the same topic (Metformin vs Breast Cancer)
    claim_3 = make_claim("33333333-3333-3333-3333-333333333333", "pmid2", 2021, [ent_a, ent_b])
    claims_replicated = [claim_1, claim_2, claim_3]
    gaps_replicated = detect_knowledge_gaps(claims_replicated, contradictions, papers)
    
    # Metformin vs Breast Cancer is now replicated (in pmid1 and pmid2), so only Aspirin vs Alzheimer remains as gap
    assert len(gaps_replicated) == 1
    assert "Aspirin" in gaps_replicated[0]
    assert "Metformin" not in gaps_replicated[0]

    # 2. Test contradiction: add contradiction pair involving claim 2
    claim_4 = make_claim("44444444-4444-4444-4444-444444444444", "pmid1", 2020, [ent_c, ent_d])
    pair = ContradictionPair(
        claim_a=claim_2,
        claim_b=claim_4,
        contradiction_score=0.9,
        contradiction_type=ContradictionType.DIRECT_NEGATION,
        explanation="Opposing findings",
        scope_note="",
        temporal_resolution=None,
        is_genuine=True
    )
    
    # Aspirin vs Alzheimer is now contradicted, so it shouldn't be a gap
    gaps_contradicted = detect_knowledge_gaps([claim_2, claim_4], [pair], papers)
    assert len(gaps_contradicted) == 0
