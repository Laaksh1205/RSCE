import pytest
import uuid
import json
from unittest.mock import AsyncMock, MagicMock, patch

from src.models.claim import Claim, ClaimType, Polarity, StudyDesign, Entity, EntityType
from src.entity.normalizer import EntityNormalizer, EntityNormalizationResponse, NormalizedEntity


@pytest.fixture
def sample_claims():
    entity_asa = Entity(text="ASA", entity_type=EntityType.DRUG)
    entity_acid = Entity(text="acetylsalicylic acid", entity_type=EntityType.DRUG)
    entity_aspirin = Entity(text="aspirin", entity_type=EntityType.DRUG)
    
    entity_metformin = Entity(text="glucophage", entity_type=EntityType.DRUG)
    entity_insulin = Entity(text="insulin", entity_type=EntityType.DRUG) # not in local map, will trigger LLM fallback
    
    claim_1 = Claim(
        id=uuid.uuid4(),
        text="ASA reduces headache.",
        paper_id="11111",
        year=2020,
        confidence_score=1.0,
        claim_type=ClaimType.CAUSAL,
        polarity=Polarity.NEGATIVE,
        entities=[entity_asa, entity_acid],
        population="humans",
        context="general",
        quote_anchor="reduces headache",
        study_design=StudyDesign.RCT
    )
    
    claim_2 = Claim(
        id=uuid.uuid4(),
        text="Aspirin and glucophage treatment.",
        paper_id="22222",
        year=2023,
        confidence_score=1.0,
        claim_type=ClaimType.CAUSAL,
        polarity=Polarity.POSITIVE,
        entities=[entity_aspirin, entity_metformin, entity_insulin],
        population="humans",
        context="general",
        quote_anchor="treatment",
        study_design=StudyDesign.RCT
    )
    
    return [claim_1, claim_2]


@pytest.mark.asyncio
async def test_normalize_entities_local_lookup(sample_claims):
    # Ensure that local lookup works and doesn't hit the LLM since we don't mock it here
    # (except for 'insulin', which we should mock or test separately. So let's temporarily mock the LLM
    # call to return a mock response for 'insulin')
    mock_llm = MagicMock()
    mock_llm.model_name = "mock-llm"
    mock_llm.generate_structured = AsyncMock(
        return_value=EntityNormalizationResponse(
            normalized_entities=[
                NormalizedEntity(
                    original_text="insulin",
                    canonical_name="Insulin",
                    canonical_id="MeSH:D007328",
                    entity_type="DRUG"
                )
            ]
        )
    )
    
    with patch("src.entity.normalizer.get_llm", return_value=mock_llm):
        normalizer = EntityNormalizer()
        normalized_claims = await normalizer.normalize_entities(sample_claims)
        
        # Verify claim 1 entities (ASA and acetylsalicylic acid) both resolved to Aspirin / MeSH:D001241
        assert normalized_claims[0].entities[0].text == "Aspirin"
        assert normalized_claims[0].entities[0].canonical_id == "MeSH:D001241"
        assert normalized_claims[0].entities[1].text == "Aspirin"
        assert normalized_claims[0].entities[1].canonical_id == "MeSH:D001241"
        
        # Verify claim 2 entities
        # aspirin -> Aspirin / MeSH:D001241
        assert normalized_claims[1].entities[0].text == "Aspirin"
        assert normalized_claims[1].entities[0].canonical_id == "MeSH:D001241"
        
        # glucophage -> Metformin / MeSH:D008687
        assert normalized_claims[1].entities[1].text == "Metformin"
        assert normalized_claims[1].entities[1].canonical_id == "MeSH:D008687"
        
        # insulin -> Insulin / MeSH:D007328 (from LLM)
        assert normalized_claims[1].entities[2].text == "Insulin"
        assert normalized_claims[1].entities[2].canonical_id == "MeSH:D007328"
        
        # Verify LLM was called exactly once for the single unresolved entity 'insulin'
        mock_llm.generate_structured.assert_called_once()
        call_kwargs = mock_llm.generate_structured.call_args[1]
        assert "insulin" in call_kwargs["prompt"]
        # And fast-lookup entities were NOT sent to the LLM as input
        assert "glucophage" not in call_kwargs["prompt"]



@pytest.mark.asyncio
async def test_normalize_entities_llm_fallback_failure(sample_claims):
    # Test that if the LLM fallback fails, original names are kept for unresolved entities
    mock_llm = MagicMock()
    mock_llm.model_name = "mock-llm"
    mock_llm.generate_structured = AsyncMock(side_effect=Exception("API failure"))
    
    with patch("src.entity.normalizer.get_llm", return_value=mock_llm):
        normalizer = EntityNormalizer()
        normalized_claims = await normalizer.normalize_entities(sample_claims)
        
        # Local lookup ones are still resolved
        assert normalized_claims[0].entities[0].text == "Aspirin"
        assert normalized_claims[1].entities[1].text == "Metformin"
        
        # Insulin (which failed LLM resolution) kept its original text and None canonical_id
        assert normalized_claims[1].entities[2].text == "insulin"
        assert normalized_claims[1].entities[2].canonical_id is None


@pytest.mark.asyncio
async def test_normalizer_loads_custom_synonym_map(tmp_path):
    # Create a custom synonym map file
    custom_map = {
        "advil": ["Ibuprofen", "MeSH:D007052"],
        "tylenol": ["Acetaminophen", "MeSH:D000082"]
    }
    custom_file = tmp_path / "custom_synonyms.json"
    custom_file.write_text(json.dumps(custom_map))

    normalizer = EntityNormalizer(synonym_map_path=str(custom_file))
    
    # Assert custom map loaded correctly
    assert normalizer.synonym_map["advil"] == ("Ibuprofen", "MeSH:D007052")
    assert normalizer.synonym_map["tylenol"] == ("Acetaminophen", "MeSH:D000082")

    # Assert fallback default items are NOT in custom map (since it loaded custom only)
    assert "aspirin" not in normalizer.synonym_map


def test_normalizer_fallback_on_missing_file():
    # Instantiate with non-existent path
    normalizer = EntityNormalizer(synonym_map_path="non_existent_file.json")
    
    # Should fall back to default map
    assert "aspirin" in normalizer.synonym_map
    assert normalizer.synonym_map["aspirin"] == ("Aspirin", "MeSH:D001241")


def test_normalizer_fallback_on_invalid_json(tmp_path):
    # Create an invalid JSON file
    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text("invalid json content {")

    normalizer = EntityNormalizer(synonym_map_path=str(invalid_file))
    
    # Should fall back to default map
    assert "aspirin" in normalizer.synonym_map
    assert normalizer.synonym_map["aspirin"] == ("Aspirin", "MeSH:D001241")

