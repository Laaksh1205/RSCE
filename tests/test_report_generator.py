import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock

from src.models.paper import Paper
from src.models.claim import Claim, ClaimType, Polarity, StudyDesign, Entity, EntityType
from src.models.contradiction import ContradictionPair, ContradictionType
from src.models.report import SynthesisReport
from src.synthesis.report_generator import (
    citation_matches_paper,
    validate_and_clean_citations,
    generate_synthesis_report
)

@pytest.fixture
def sample_data():
    paper_1 = Paper(
        pmid="11111",
        title="Study 1 on Metformin",
        authors=["John Adams", "Co-Author One"],
        year=2020,
        journal="Journal of Diabetes",
        abstract_text="Metformin reduces cancer risk."
    )
    paper_2 = Paper(
        pmid="22222",
        title="Study 2 on Metformin",
        authors=["Alice Baker"],
        year=2023,
        journal="Cancer Letters",
        abstract_text="Metformin increases cancer risk."
    )
    
    entity_metformin = Entity(text="Metformin", canonical_id="MeSH:D001241", entity_type=EntityType.DRUG)
    entity_cancer = Entity(text="Cancer", canonical_id="MeSH:D009369", entity_type=EntityType.DISEASE)
    
    claim_1 = Claim(
        id=uuid.uuid4(),
        text="Metformin reduces breast cancer risk.",
        paper_id="11111",
        authors=["John Adams", "Co-Author One"],
        year=2020,
        confidence_score=1.0,
        claim_type=ClaimType.CAUSAL,
        polarity=Polarity.NEGATIVE,
        entities=[entity_metformin, entity_cancer],
        population="humans",
        context="general",
        quote_anchor="reduces risk",
        study_design=StudyDesign.RCT
    )
    
    claim_2 = Claim(
        id=uuid.uuid4(),
        text="Metformin increases breast cancer risk.",
        paper_id="22222",
        authors=["Alice Baker"],
        year=2023,
        confidence_score=1.0,
        claim_type=ClaimType.CAUSAL,
        polarity=Polarity.POSITIVE,
        entities=[entity_metformin, entity_cancer],
        population="humans",
        context="general",
        quote_anchor="increases risk",
        study_design=StudyDesign.RCT
    )

    contradiction = ContradictionPair(
        claim_a=claim_1,
        claim_b=claim_2,
        contradiction_score=0.95,
        contradiction_type=ContradictionType.DIRECTION_REVERSAL,
        explanation="Claim 1 reduces risk, Claim 2 increases risk.",
        scope_note="",
        is_genuine=True
    )
    
    return [claim_1, claim_2], [contradiction], [paper_1, paper_2]


def test_citation_matches_paper():
    paper = Paper(
        pmid="12345",
        title="Sample Title",
        authors=["John Adams", "Jane Smith"],
        year=2024,
        journal="Journal of Medicine",
        abstract_text="Abstract text"
    )
    
    # Matches
    assert citation_matches_paper("Adams, 2024", paper)
    assert citation_matches_paper("Adams et al., 2024", paper)
    assert citation_matches_paper("Adams et al. 2024", paper)
    
    # Fails
    assert not citation_matches_paper("Smith, 2024", paper) # Not the first author
    assert not citation_matches_paper("Adams, 2020", paper) # Wrong year
    assert not citation_matches_paper("Hallucinated, 2024", paper)


def test_validate_and_clean_citations():
    papers = [
        Paper(pmid="111", title="Title A", authors=["John Adams"], year=2020, journal="Journal A", abstract_text="A"),
        Paper(pmid="222", title="Title B", authors=["Alice Baker"], year=2023, journal="Journal B", abstract_text="B")
    ]

    raw_summary = "Metformin reduces risk [Adams et al., 2020], but Baker contradicts this [Baker, 2023]. Also, there is a fake reference [Fake, 2021]."
    expected_cleaned = "Metformin reduces risk [Adams, 2020], but Baker contradicts this [Baker, 2023]. Also, there is a fake reference."

    cleaned = validate_and_clean_citations(raw_summary, papers)
    assert cleaned == expected_cleaned

def test_validate_and_clean_citations_comprehensive():
    papers = [
        Paper(pmid="111", title="Title A", authors=["John Adams"], year=2020, journal="Journal A", abstract_text="A"),
        Paper(pmid="222", title="Title B", authors=["Alice Baker"], year=2023, journal="Journal B", abstract_text="B")
    ]
    
    # Test cases:
    # 1. Completely fake citation [Nonexistent, 2099] -> stripped.
    # 2. Author correct but wrong year [Adams, 2099] -> stripped.
    # 3. Year correct but wrong author [Nonexistent, 2020] -> stripped.
    raw_summary = (
        "We found that Metformin works [Adams, 2020]. "
        "However, some studies disagree [Nonexistent, 2099]. "
        "Other studies also show mixed results [Adams, 2099] and [Nonexistent, 2020]."
    )
    expected_cleaned = (
        "We found that Metformin works [Adams, 2020]. "
        "However, some studies disagree. "
        "Other studies also show mixed results and."
    )
    
    cleaned = validate_and_clean_citations(raw_summary, papers)
    assert cleaned == expected_cleaned


def test_hallucinated_citations_are_stripped():
    papers = [
        Paper(pmid="1", title="Title A", authors=["Smith"], year=2023, journal="Journal A", abstract_text="A")
    ]
    text = "X is true [Smith, 2023]. Y is also true [FakeAuthor, 2099]."
    cleaned = validate_and_clean_citations(text, papers)
    assert "[Smith, 2023]" in cleaned
    assert "[FakeAuthor, 2099]" not in cleaned
    assert "2099" not in cleaned


@pytest.mark.asyncio
async def test_generate_synthesis_report(sample_data):
    claims, contradictions, papers = sample_data
    
    mock_llm = MagicMock()
    mock_llm.model_name = "mock-llm"
    mock_llm.generate_text = AsyncMock(
        return_value="Metformin reduces breast cancer risk [Adams, 2020] but is contradicted by Baker [Baker et al., 2023]."
    )
    
    report = await generate_synthesis_report(contradictions, claims, papers, mock_llm)
    
    assert isinstance(report, SynthesisReport)
    assert "Metformin reduces breast cancer risk [Adams, 2020]" in report.summary
    assert "Baker, 2023" in report.summary
    
    # Verify that consensus scores were computed and populated in the report
    assert str(claims[0].id) in report.consensus_scores
    assert str(claims[1].id) in report.consensus_scores
    assert report.total_papers == 2
    assert report.total_claims == 2
    assert len(report.contradictions) == 1
    
    # Verify LLM call
    mock_llm.generate_text.assert_called_once()
