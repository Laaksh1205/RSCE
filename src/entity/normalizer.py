import json
import logging

from src.config import settings
from src.models.claim import Claim
from src.llm import get_llm
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Try to detect if scispacy and its dependencies are available (compiled / installed)
SCISPACY_AVAILABLE = False
try:
    import spacy  # noqa: F401
    import scispacy  # noqa: F401
    from scispacy.linking import EntityLinker  # noqa: F401
    SCISPACY_AVAILABLE = True
except ImportError:
    pass

# Default synonym and canonical concept dictionary mapping (case-insensitive keys)
# Fast lookup for common synonyms to avoid calling external models
DEFAULT_SYNONYM_MAP = {
    "aspirin": ("Aspirin", "MeSH:D001241"),
    "asa": ("Aspirin", "MeSH:D001241"),
    "acetylsalicylic acid": ("Aspirin", "MeSH:D001241"),
    "metformin": ("Metformin", "MeSH:D008687"),
    "glucophage": ("Metformin", "MeSH:D008687"),
    "cancer": ("Neoplasms", "MeSH:D009369"),
    "tumor": ("Neoplasms", "MeSH:D009369"),
    "tumors": ("Neoplasms", "MeSH:D009369"),
    "neoplasm": ("Neoplasms", "MeSH:D009369"),
    "neoplasms": ("Neoplasms", "MeSH:D009369"),
    "breast cancer": ("Breast Neoplasms", "MeSH:D001943"),
    "breast tumors": ("Breast Neoplasms", "MeSH:D001943"),
    "ampk": ("AMP-activated Protein Kinases", "MeSH:D055372"),
    "mtor": ("TOR Serine-Threonine Kinases", "MeSH:D058570"),
}

class NormalizedEntity(BaseModel):
    """Pydantic model representing a single normalized entity resolved by the LLM."""
    original_text: str = Field(description="The original entity text mention to match back to")
    canonical_name: str = Field(description="The normalized canonical name of the entity concept")
    canonical_id: str | None = Field(default=None, description="Canonical database ID, e.g., 'MeSH:D001241' or 'UMLS:C0004057'")
    entity_type: str = Field(description="The biomedical entity type, e.g., 'DRUG', 'DISEASE', etc.")

class EntityNormalizationResponse(BaseModel):
    """Schema for the LLM structured response in entity normalization."""
    normalized_entities: list[NormalizedEntity]

class EntityNormalizer:
    def __init__(self, synonym_map_path: str | None = None):
        self.nlp = None
        self._scispacy_initialized = False
        self.synonym_map = self._load_synonym_map(synonym_map_path)

    def _load_synonym_map(self, synonym_map_path: str | None = None) -> dict[str, tuple[str, str | None]]:
        """Load the local synonym map from a JSON file, falling back to default map on error."""
        if synonym_map_path is None:
            synonym_map_path = settings.synonym_map_path

        if not synonym_map_path:
            logger.info("No synonym map path configured. Using default synonym map.")
            return DEFAULT_SYNONYM_MAP

        import os
        resolved_path = os.path.abspath(synonym_map_path)
        if not os.path.exists(resolved_path):
            logger.warning(f"Synonym map file not found at '{resolved_path}'. Falling back to default synonym map.")
            return DEFAULT_SYNONYM_MAP

        try:
            with open(resolved_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if not isinstance(data, dict):
                logger.warning(f"Synonym map file at '{resolved_path}' must contain a JSON object. Falling back to default synonym map.")
                return DEFAULT_SYNONYM_MAP

            loaded_map = {}
            for k, v in data.items():
                if isinstance(v, list) and len(v) >= 2:
                    loaded_map[k.lower()] = (v[0], v[1])
                elif isinstance(v, list) and len(v) == 1:
                    loaded_map[k.lower()] = (v[0], None)
                else:
                    logger.warning(f"Invalid value for synonym key '{k}': {v}. Expected a list of [canonical_name, canonical_id]. Skipping.")
            
            logger.info(f"Loaded {len(loaded_map)} synonyms from '{resolved_path}'.")
            return loaded_map

        except Exception as e:
            logger.warning(f"Failed to load synonym map from '{resolved_path}': {e}. Falling back to default synonym map.")
            return DEFAULT_SYNONYM_MAP

    def _init_scispacy(self) -> None:
        """Lazily initialize scispaCy pipeline to avoid import delays if unused."""
        if not SCISPACY_AVAILABLE or self._scispacy_initialized:
            return
        try:
            import spacy
            logger.info("Initializing scispaCy NLP pipeline and UMLS EntityLinker...")
            self.nlp = spacy.load("en_core_sci_sm")
            self.nlp.add_pipe(
                "scispacy_linker", 
                config={"resolve_abbreviations": True, "linker_name": "umls"}
            )
            self._scispacy_initialized = True
            logger.info("scispaCy pipeline successfully initialized.")
        except Exception as e:
            logger.warning(f"Failed to initialize scispaCy pipeline: {e}. Falling back to LLM / local map.")
            self._scispacy_initialized = False

    async def normalize_entities(self, claims: list[Claim]) -> list[Claim]:
        """Normalize the entities in a list of Claims.
        
        Updates the claims' entities in-place by assigning canonical names and IDs.
        Resolves synonyms using a local dictionary map, scispaCy (if available), 
        and falls back to LLM-based structured resolution.
        """
        # 1. Gather all unique entity mentions across claims to process in batch
        unique_entities = {}
        for claim in claims:
            for entity in claim.entities:
                text_clean = entity.text.strip()
                if not text_clean:
                    continue
                key = text_clean.lower()
                if key not in unique_entities:
                    unique_entities[key] = {
                        "text": text_clean,
                        "type": entity.entity_type
                    }
                    
        if not unique_entities:
            return claims
            
        resolved_map = {}  # key (lowercase original text) -> (canonical_name, canonical_id)
        unresolved_entities = []
        
        # 2. Check local fast-lookup synonym map
        for key, info in unique_entities.items():
            if key in self.synonym_map:
                resolved_map[key] = self.synonym_map[key]
            else:
                unresolved_entities.append(info)
                
        # 3. If scispaCy is available, attempt to resolve using the linker
        if unresolved_entities and SCISPACY_AVAILABLE:
            self._init_scispacy()
            if self._scispacy_initialized:
                still_unresolved = []
                for info in unresolved_entities:
                    text = info["text"]
                    try:
                        doc = self.nlp(text)
                        if doc.ents and doc.ents[0]._.kb_ents:
                            umls_ent_id, _ = doc.ents[0]._.kb_ents[0]
                            kb = self.nlp.get_pipe("scispacy_linker").kb
                            canonical_name = kb.cui_to_entity[umls_ent_id].canonical_name
                            canonical_id = f"UMLS:{umls_ent_id}"
                            resolved_map[text.lower()] = (canonical_name, canonical_id)
                        else:
                            still_unresolved.append(info)
                    except Exception as e:
                        logger.warning(f"scispaCy linking failed for '{text}': {e}")
                        still_unresolved.append(info)
                unresolved_entities = still_unresolved
                
        # 4. Fallback to LLM structured resolution for remaining unresolved concepts
        if unresolved_entities:
            try:
                llm = get_llm()
                # Prepare payload for LLM normalizer
                entities_to_resolve = [
                    {"text": info["text"], "type": info["type"].value}
                    for info in unresolved_entities
                ]
                
                logger.info(f"Resolving {len(entities_to_resolve)} entities via LLM ({llm.model_name})...")
                
                prompt = (
                    "You are a medical informatics expert. Normalize the following biomedical entity mentions to their canonical names "
                    "and standard database identifiers (preferably MeSH descriptors, e.g., 'MeSH:D001241', or UMLS CUIs, e.g., 'UMLS:C0004057').\n\n"
                    "Rules:\n"
                    "1. Identify the most specific canonical term/concept name for the given text.\n"
                    "2. Provide the canonical identifier in the format 'MeSH:ID' or 'UMLS:ID'. If no standard ID exists, return null for canonical_id.\n"
                    "3. Keep the original text exactly as provided to match back to the input.\n"
                    "4. Resolve synonyms to the same canonical concept. For example, 'ASA', 'acetylsalicylic acid', and 'aspirin' must all map to "
                    "canonical name 'Aspirin' and canonical ID 'MeSH:D001241'.\n\n"
                    f"Entities to normalize:\n{json.dumps(entities_to_resolve, indent=2)}\n\n"
                    "Please respond with the normalized entities in JSON format matching the schema."
                )
                
                response = await llm.generate_structured(
                    prompt=prompt,
                    response_schema=EntityNormalizationResponse,
                    temperature=0.1
                )
                
                for ent in response.normalized_entities:
                    key = ent.original_text.strip().lower()
                    resolved_map[key] = (ent.canonical_name, ent.canonical_id)
            except Exception as e:
                logger.error(f"LLM entity normalization failed: {e}. Keeping original names.")
                
        # 5. Apply the resolved mapping to update claims' entities in-place
        for claim in claims:
            for entity in claim.entities:
                key = entity.text.strip().lower()
                if key in resolved_map:
                    canonical_name, canonical_id = resolved_map[key]
                    entity.text = canonical_name
                    entity.canonical_id = canonical_id
                    
        return claims
