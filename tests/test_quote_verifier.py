import pytest
from src.models.paper import Paper
from src.models.claim import ExtractedClaim, ClaimType, Polarity, StudyDesign
from src.extraction.quote_verifier import normalize_text, verify_quote_anchor, verify_and_filter_claims

@pytest.fixture
def sample_paper():
    return Paper(
        pmid="12345",
        title="Sample Study",
        authors=["John Smith"],
        year=2023,
        journal="Journal",
        abstract_text="Metformin inhibits cell proliferation in MCF-7 breast cancer cells by activating AMPK."
    )

@pytest.fixture
def base_extracted_claim():
    return ExtractedClaim(
        text="Metformin inhibits proliferation.",
        polarity=Polarity.NEGATIVE,
        population="MCF-7 breast cancer cells",
        context="via AMPK activation",
        quote_anchor="",  # filled by tests
        claim_type=ClaimType.CAUSAL,
        study_design=StudyDesign.IN_VITRO,
        entities=[]
    )

def test_normalization():
    text = "Metformin, inhibits: proliferation... in MCF-7 cells!"
    expected = "metformin inhibits proliferation in mcf7 cells"
    assert normalize_text(text) == expected

def test_exact_match_passes(sample_paper):
    quote = "Metformin inhibits cell proliferation in MCF-7"
    status, score = verify_quote_anchor(quote, sample_paper.abstract_text)
    assert status == "PASS"
    assert score >= 85.0

def test_minor_variation_flags(sample_paper):
    # Slight variation/paraphrase
    quote = "Metformin prevents cell proliferation in breast cancer cells"
    status, score = verify_quote_anchor(quote, sample_paper.abstract_text)
    assert status == "FLAG"
    assert 70.0 <= score < 85.0

def test_fabricated_quote_rejects(sample_paper):
    quote = "Aspirin reduces headache and pain in adult humans"
    status, score = verify_quote_anchor(quote, sample_paper.abstract_text)
    assert status == "REJECT"
    assert score < 70.0

def test_verify_and_filter_claims(sample_paper, base_extracted_claim):
    # Create 3 claims: one pass, one flag, one reject
    claim_pass = base_extracted_claim.model_copy(update={"quote_anchor": "Metformin inhibits cell proliferation"})
    claim_flag = base_extracted_claim.model_copy(update={"quote_anchor": "Metformin prevents cell proliferation in breast cancer cells"})
    claim_reject = base_extracted_claim.model_copy(update={"quote_anchor": "Aspirin reduces pain"})
    
    claims = [claim_pass, claim_flag, claim_reject]
    verified, stats = verify_and_filter_claims(claims, sample_paper)
    
    assert len(verified) == 2  # Pass and Flag kept, Reject discarded
    assert stats["passed"] == 1
    assert stats["flagged"] == 1
    assert stats["rejected"] == 1
    assert stats["rejection_rate"] == pytest.approx(1/3)
    
    # Check that flagged claim has confidence score of 0.5 and passed has 1.0
    assert verified[0].confidence_score == 1.0  # claim_pass
    assert verified[1].confidence_score == 0.5  # claim_flag


def test_section_aware_abstract_background(base_extracted_claim):
    paper = Paper(
        pmid="11111",
        title="Background Test",
        authors=["Author"],
        year=2024,
        journal="Journal",
        abstract_text="BACKGROUND: Metformin has been investigated for decades.\nRESULTS: Metformin reduces cancer risk."
    )
    
    # Claim from background line
    claim_bg = base_extracted_claim.model_copy(update={"quote_anchor": "Metformin has been investigated for decades"})
    # Claim from results line
    claim_res = base_extracted_claim.model_copy(update={"quote_anchor": "Metformin reduces cancer risk"})
    
    verified, _ = verify_and_filter_claims([claim_bg, claim_res], paper)
    assert len(verified) == 2
    
    # Background match -> is_primary_finding = False
    assert verified[0].is_primary_finding is False
    assert verified[0].section == "Abstract"
    
    # Results match -> is_primary_finding = True
    assert verified[1].is_primary_finding is True
    assert verified[1].section == "Abstract"


def test_section_aware_full_text(base_extracted_claim):
    paper = Paper(
        pmid="22222",
        title="Full Text Test",
        authors=["Author"],
        year=2024,
        journal="Journal",
        abstract_text="Abstract text with no detail.",
        full_text="=== INTRODUCTION ===\nMetformin was first synthesized in 1922.\n\n=== MATERIALS AND METHODS ===\nWe treated cells with Metformin in vitro.\n\n=== EXPERIMENTAL PROCEDURES ===\nWe measured cell growth via assay.\n\n=== RESULTS ===\nMetformin significantly decreased MCF-7 tumor volume."
    )
    
    # 1. Quote from Introduction
    claim_intro = base_extracted_claim.model_copy(update={"quote_anchor": "Metformin was first synthesized in 1922"})
    # 2. Quote from Materials and Methods
    claim_methods = base_extracted_claim.model_copy(update={"quote_anchor": "We treated cells with Metformin in vitro"})
    # 3. Quote from Experimental Procedures
    claim_procedures = base_extracted_claim.model_copy(update={"quote_anchor": "We measured cell growth via assay"})
    # 4. Quote from Results
    claim_results = base_extracted_claim.model_copy(update={"quote_anchor": "Metformin significantly decreased MCF-7 tumor volume"})
    
    verified, _ = verify_and_filter_claims([claim_intro, claim_methods, claim_procedures, claim_results], paper)
    assert len(verified) == 4
    
    # Introduction match -> section = "Introduction", is_primary_finding = False
    assert verified[0].section == "Introduction"
    assert verified[0].is_primary_finding is False
    
    # Materials and Methods match -> section = "Materials And Methods", is_primary_finding = False
    assert verified[1].section == "Materials And Methods"
    assert verified[1].is_primary_finding is False
    
    # Experimental Procedures match -> section = "Experimental Procedures", is_primary_finding = False
    assert verified[2].section == "Experimental Procedures"
    assert verified[2].is_primary_finding is False
    
    # Results match -> section = "Results", is_primary_finding = True
    assert verified[3].section == "Results"
    assert verified[3].is_primary_finding is True

