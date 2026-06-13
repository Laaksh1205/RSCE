import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.config import settings
from src.models.paper import Paper
from src.models.claim import ExtractedClaim, ClaimExtractionResponse, ClaimType, Polarity, StudyDesign, Entity, EntityType
from src.extraction.claim_extractor import extract_claims_from_paper, extract_claims_batch

@pytest.fixture
def sample_paper():
    return Paper(
        pmid="12345",
        title="Sample Study on Metformin",
        authors=["John Smith"],
        year=2023,
        journal="Diabetes Care",
        abstract_text="OBJECTIVE: Test metformin. Daily 1000mg metformin for 3 months reduced HbA1c in human adults."
    )

@pytest.fixture
def mock_claims():
    return [
        ExtractedClaim(
            text="Metformin reduces HbA1c.",
            polarity=Polarity.POSITIVE,
            population="human adults",
            context="1000mg daily for 3 months",
            quote_anchor="reduced HbA1c in human adults",
            claim_type=ClaimType.QUANTITATIVE,
            study_design=StudyDesign.RCT,
            entities=[Entity(text="metformin", entity_type=EntityType.DRUG)]
        )
    ]

@pytest.mark.asyncio
async def test_extraction_returns_valid_claims(sample_paper, mock_claims):
    mock_llm = MagicMock()
    mock_llm.generate_structured = AsyncMock(
        return_value=ClaimExtractionResponse(claims=mock_claims)
    )
    
    claims = await extract_claims_from_paper(sample_paper, mock_llm)
    assert len(claims) == 1
    assert claims[0].text == "Metformin reduces HbA1c."
    assert claims[0].polarity == Polarity.POSITIVE
    mock_llm.generate_structured.assert_called_once()

@pytest.mark.asyncio
async def test_cap_at_max_claims(sample_paper, mock_claims):
    # Create 15 identical mock claims
    many_claims = mock_claims * 15
    mock_llm = MagicMock()
    mock_llm.generate_structured = AsyncMock(
        return_value=ClaimExtractionResponse(claims=many_claims)
    )
    
    claims = await extract_claims_from_paper(sample_paper, mock_llm)
    assert len(claims) == settings.claims_per_abstract_cap
    mock_llm.generate_structured.assert_called_once()

@pytest.mark.asyncio
async def test_retry_on_malformed_json(sample_paper, mock_claims):
    mock_llm = MagicMock()
    
    # First call raises an exception, second call succeeds
    mock_llm.generate_structured = AsyncMock(
        side_effect=[Exception("Malformed JSON"), ClaimExtractionResponse(claims=mock_claims)]
    )
    
    claims = await extract_claims_from_paper(sample_paper, mock_llm)
    assert len(claims) == 1
    assert claims[0].text == "Metformin reduces HbA1c."
    assert mock_llm.generate_structured.call_count == 2

@pytest.mark.asyncio
async def test_empty_abstract_returns_zero_claims():
    empty_paper = Paper(
        pmid="123",
        title="Empty",
        authors=[],
        year=2020,
        journal="Empty Journal",
        abstract_text=""
    )
    mock_llm = MagicMock()
    mock_llm.generate_structured = AsyncMock()
    
    claims = await extract_claims_from_paper(empty_paper, mock_llm)
    assert claims == []
    mock_llm.generate_structured.assert_not_called()


@pytest.mark.asyncio
async def test_extraction_uses_full_text_when_available(mock_claims):
    paper_with_full_text = Paper(
        pmid="12345",
        title="Sample Study on Metformin",
        authors=["John Smith"],
        year=2023,
        journal="Diabetes Care",
        abstract_text="OBJECTIVE: Test metformin.",
        full_text="=== ABSTRACT ===\nOBJECTIVE: Test metformin.\n=== RESULTS ===\nDaily 1000mg metformin for 3 months reduced HbA1c in human adults."
    )
    mock_llm = MagicMock()
    mock_llm.generate_structured = AsyncMock(
        return_value=ClaimExtractionResponse(claims=mock_claims)
    )
    
    claims = await extract_claims_from_paper(paper_with_full_text, mock_llm)
    assert len(claims) == 1
    assert claims[0].text == "Metformin reduces HbA1c."
    mock_llm.generate_structured.assert_called_once()
    
    # Verify the prompt contained the full text and adjusted headings
    call_args = mock_llm.generate_structured.call_args[1]
    prompt = call_args["prompt"]
    assert "Full Text (including abstract)" in prompt
    assert paper_with_full_text.full_text in prompt


@pytest.mark.asyncio
async def test_section_by_section_extraction_is_called_in_parallel(monkeypatch, mock_claims):
    # Disable primary-section filtering so both INTRODUCTION and RESULTS are extracted,
    # keeping this test focused purely on verifying parallel dispatch.
    monkeypatch.setattr(settings, "primary_sections_only", False)

    # Prepare a paper with substantial section lengths
    intro_text = "This is a very long introduction section with more than one hundred characters to trigger the section extraction logic. Metformin is used globally."
    results_text = "This is a very long results section with more than one hundred characters to trigger the section extraction logic. Metformin reduced risk."
    paper = Paper(
        pmid="54321",
        title="Full Study",
        authors=["Alice"],
        year=2025,
        journal="Journal",
        abstract_text="Abstract",
        full_text=f"=== INTRODUCTION ===\n{intro_text}\n=== RESULTS ===\n{results_text}"
    )
    
    mock_llm = MagicMock()
    # Mock return values for parallel calls
    mock_llm.generate_structured = AsyncMock()
    mock_llm.generate_structured.side_effect = [
        ClaimExtractionResponse(claims=mock_claims),
        ClaimExtractionResponse(claims=[])
    ]
    
    claims = await extract_claims_from_paper(paper, mock_llm)
    # It should have called generate_structured twice (one per section)
    assert mock_llm.generate_structured.call_count == 2
    assert len(claims) == 1
    
    # Check that prompts were built with section names
    calls = mock_llm.generate_structured.call_args_list
    prompt0 = calls[0][1]["prompt"]
    prompt1 = calls[1][1]["prompt"]
    
    # One of the calls was for INTRODUCTION and one for RESULTS
    has_intro = "Section 'INTRODUCTION'" in prompt0 or "Section 'INTRODUCTION'" in prompt1
    has_results = "Section 'RESULTS'" in prompt0 or "Section 'RESULTS'" in prompt1
    assert has_intro
    assert has_results


@pytest.mark.asyncio
async def test_section_concurrency_limits_parallel_calls(monkeypatch, mock_claims):
    # Set section_concurrency to 2 for this test
    monkeypatch.setattr(settings, "section_concurrency", 2)
    
    # Paper with 4 sections, each > 100 characters
    sec1 = "Introduction section text that is long enough to trigger extraction. " * 3
    sec2 = "Methods section text that is long enough to trigger extraction. " * 3
    sec3 = "Results section text that is long enough to trigger extraction. " * 3
    sec4 = "Discussion section text that is long enough to trigger extraction. " * 3
    
    paper = Paper(
        pmid="99999",
        title="Testing Concurrency",
        authors=["Alice"],
        year=2026,
        journal="Journal",
        abstract_text="Abstract",
        full_text=f"=== INTRODUCTION ===\n{sec1}\n=== METHODS ===\n{sec2}\n=== RESULTS ===\n{sec3}\n=== DISCUSSION ===\n{sec4}"
    )
    
    active_calls = 0
    max_active_calls = 0
    lock = asyncio.Lock()
    
    async def mock_generate_structured(*args, **kwargs):
        nonlocal active_calls, max_active_calls
        async with lock:
            active_calls += 1
            if active_calls > max_active_calls:
                max_active_calls = active_calls
        
        # Simulate some work / delay to allow overlap
        await asyncio.sleep(0.05)
        
        async with lock:
            active_calls -= 1
            
        return ClaimExtractionResponse(claims=[])
        
    mock_llm = MagicMock()
    mock_llm.generate_structured = mock_generate_structured
    
    await extract_claims_from_paper(paper, mock_llm)
    
    # Max active concurrent calls must not exceed section_concurrency (which is 2)
    assert max_active_calls == 2


@pytest.mark.asyncio
async def test_primary_sections_only_filters_intro_and_methods(monkeypatch, mock_claims):
    """When primary_sections_only=True, Introduction and Methods sections must be skipped
    and only primary sections (e.g. Results) should trigger LLM calls."""
    monkeypatch.setattr(settings, "primary_sections_only", True)
    monkeypatch.setattr(settings, "primary_section_names", ["results", "discussion"])

    sec_intro = "Introduction text " * 10   # > 100 chars
    sec_methods = "Methods text " * 10
    sec_results = "Results text " * 10

    paper = Paper(
        pmid="77777",
        title="Filtering Test",
        authors=["Alice"],
        year=2025,
        journal="Journal",
        abstract_text="Abstract",
        full_text=(
            f"=== INTRODUCTION ===\n{sec_intro}\n"
            f"=== METHODS ===\n{sec_methods}\n"
            f"=== RESULTS ===\n{sec_results}"
        ),
    )
    mock_llm = MagicMock()
    mock_llm.generate_structured = AsyncMock(
        return_value=ClaimExtractionResponse(claims=mock_claims)
    )

    claims = await extract_claims_from_paper(paper, mock_llm)

    # Only RESULTS qualifies — exactly 1 LLM call, not 3
    assert mock_llm.generate_structured.call_count == 1
    call_prompt = mock_llm.generate_structured.call_args[1]["prompt"]
    assert "Section 'RESULTS'" in call_prompt
    assert "Section 'INTRODUCTION'" not in call_prompt
    assert "Section 'METHODS'" not in call_prompt
    assert len(claims) == 1


@pytest.mark.asyncio
async def test_primary_sections_only_false_extracts_all_sections(monkeypatch, mock_claims):
    """When primary_sections_only=False, all sections with len > 100 chars are extracted,
    including Introduction and Methods."""
    monkeypatch.setattr(settings, "primary_sections_only", False)

    sec_intro = "Introduction text " * 10   # > 100 chars
    sec_methods = "Methods text " * 10
    sec_results = "Results text " * 10

    paper = Paper(
        pmid="88888",
        title="All-Sections Test",
        authors=["Bob"],
        year=2025,
        journal="Journal",
        abstract_text="Abstract",
        full_text=(
            f"=== INTRODUCTION ===\n{sec_intro}\n"
            f"=== METHODS ===\n{sec_methods}\n"
            f"=== RESULTS ===\n{sec_results}"
        ),
    )
    mock_llm = MagicMock()
    mock_llm.generate_structured = AsyncMock(
        return_value=ClaimExtractionResponse(claims=[])
    )

    await extract_claims_from_paper(paper, mock_llm)

    # All 3 sections should trigger an LLM call when filtering is disabled
    assert mock_llm.generate_structured.call_count == 3




