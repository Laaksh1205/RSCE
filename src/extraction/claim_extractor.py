import os
import json
import logging
import asyncio
import weakref
from src.config import settings
from src.models.paper import Paper
from src.models.claim import ExtractedClaim, ClaimExtractionResponse
from src.llm.base import LLMProvider

logger = logging.getLogger(__name__)

_section_semaphores = weakref.WeakKeyDictionary()

def get_section_semaphore() -> asyncio.Semaphore:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.Semaphore(settings.section_concurrency)
    if loop not in _section_semaphores:
        _section_semaphores[loop] = asyncio.Semaphore(settings.section_concurrency)
    return _section_semaphores[loop]

# Cache prompt templates to avoid repeated disk reads
_PROMPT_TEMPLATE = None
_FEW_SHOTS_DATA = None

def load_prompt_resources() -> tuple[str, str]:
    """Load prompt template and few-shot examples from files."""
    global _PROMPT_TEMPLATE, _FEW_SHOTS_DATA
    if _PROMPT_TEMPLATE is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
        prompt_path = os.path.join(base_dir, "prompts", "extraction_prompt.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            _PROMPT_TEMPLATE = f.read()
            
        few_shots_path = os.path.join(base_dir, "prompts", "extraction_few_shot.json")
        with open(few_shots_path, "r", encoding="utf-8") as f:
            raw_shots = json.load(f)
            shots_str = ""
            for idx, shot in enumerate(raw_shots):
                shots_str += f"### Example {idx+1}\n"
                shots_str += f"Abstract: {shot['abstract']}\n"
                formatted_claims = json.dumps({"claims": shot["claims"]}, indent=2)
                shots_str += f"Extracted Output:\n```json\n{formatted_claims}\n```\n\n"
            _FEW_SHOTS_DATA = shots_str
            
    return _PROMPT_TEMPLATE, _FEW_SHOTS_DATA

def build_extraction_prompt(text: str, is_full_text: bool = False, section_name: str | None = None) -> str:
    """Combine the base prompt template, formatted few-shot examples, and target text."""
    template, few_shots = load_prompt_resources()
    
    if section_name:
        text_type = f"Section '{section_name}'"
    else:
        text_type = "Full Text (including abstract)" if is_full_text else "Abstract"
    
    # Adapt template slightly if full text or section is used
    if is_full_text or section_name:
        template = template.replace("research paper abstract", "research paper text")
        template = template.replace("substring of the abstract", "substring of the text")
        template = template.replace("claims per abstract", "claims per paper")
        
    full_prompt = (
        f"{template}\n"
        f"Here are reference examples of the expected input/output mapping:\n\n"
        f"{few_shots}\n"
        f"Please extract claims for this target {text_type.lower()}:\n"
        f"{text_type}: {text}\n\n"
        f"Extracted Output (JSON format matching ClaimExtractionResponse schema):"
    )
    return full_prompt

async def extract_claims_from_paper(
    paper: Paper,
    llm: LLMProvider,
) -> list[ExtractedClaim]:
    """Extract claims from a single paper's text (full text if available, fallback to abstract).
    
    If full text is available:
    - Splits it into sections (Introduction, Methods, Results, Discussion).
    - Concurrently extracts claims from each non-empty section.
    - Caps claims per section to prevent any single section from dominating.
    - Merges results and caps final claims list at claims_per_abstract_cap.
    
    If no sections are found or full text is not available:
    - Falls back to extracting from abstract text / full text as a single string.
    """
    import re
    
    # Check if we have sections in full text to do section-by-section extraction
    sections_to_extract = []
    if paper.full_text:
        parts = re.split(r'===\s*([A-Z\s]+)\s*===', paper.full_text)
        for i in range((len(parts) - 1) // 2):
            sec_header = parts[i * 2 + 1].strip()
            sec_content = parts[i * 2 + 2].strip()
            if len(sec_content) > 100:
                sections_to_extract.append((sec_header, sec_content))
                
    if sections_to_extract:
        # Run section-based extraction concurrently
        async def extract_sec(sec_title, sec_body):
            prompt = build_extraction_prompt(sec_body, section_name=sec_title)
            sem = get_section_semaphore()
            async with sem:
                for attempt in range(2):
                    try:
                        response = await llm.generate_structured(
                            prompt=prompt,
                            response_schema=ClaimExtractionResponse,
                            temperature=0.1
                        )
                        sec_claims = response.claims
                        sec_cap = max(3, settings.claims_per_abstract_cap // 2)
                        if len(sec_claims) > sec_cap:
                            sec_claims = sec_claims[:sec_cap]
                        return sec_claims
                    except Exception as e:
                        if attempt == 0:
                            logger.warning(f"Attempt 1 failed to extract from section {sec_title} of paper {paper.pmid}, retrying: {e}")
                            await asyncio.sleep(1)
                        else:
                            logger.error(f"Failed to extract from section {sec_title} of paper {paper.pmid} after 2 attempts: {e}")
                return []
            
        tasks = [extract_sec(title, content) for title, content in sections_to_extract]
        results = await asyncio.gather(*tasks)
        
        merged_claims = []
        for sec_claims in results:
            merged_claims.extend(sec_claims)
            
        if len(merged_claims) > settings.claims_per_abstract_cap:
            logger.info(f"Merged claims count for full-text paper {paper.pmid} exceeded cap ({len(merged_claims)}). Capping at {settings.claims_per_abstract_cap}.")
            merged_claims = merged_claims[:settings.claims_per_abstract_cap]
            
        return merged_claims

    # Fallback to single-call abstract/full-text extraction
    source_text = paper.full_text or paper.abstract_text
    is_full_text = bool(paper.full_text)
    
    if not source_text or not source_text.strip():
        logger.warning(f"Paper {paper.pmid} has empty abstract and full text, skipping claim extraction.")
        return []
        
    prompt = build_extraction_prompt(source_text, is_full_text=is_full_text)
    
    for attempt in range(2):
        try:
            response = await llm.generate_structured(
                prompt=prompt,
                response_schema=ClaimExtractionResponse,
                temperature=0.1
            )
            claims = response.claims
            
            if len(claims) > settings.claims_per_abstract_cap:
                logger.info(f"Claims count for {paper.pmid} exceeded cap ({len(claims)}). Capping at {settings.claims_per_abstract_cap}.")
                claims = claims[:settings.claims_per_abstract_cap]
                
            return claims
        except Exception as e:
            if attempt == 0:
                logger.warning(f"Attempt 1 failed to extract claims from paper {paper.pmid}, retrying: {e}")
                await asyncio.sleep(1)
            else:
                logger.error(f"Failed to extract claims from paper {paper.pmid} after 2 attempts: {e}")
            
    return []

async def extract_claims_batch(
    papers: list[Paper],
    llm: LLMProvider,
) -> dict[str, list[ExtractedClaim]]:
    """Extract claims from all papers concurrently.
    
    Uses asyncio.Semaphore(settings.llm_concurrency) for rate limiting.
    Returns: {pmid: [claims]} mapping
    Logs: papers that failed extraction, papers with 0 claims
    """
    sem = asyncio.Semaphore(settings.llm_concurrency)
    
    async def process_paper(paper: Paper):
        async with sem:
            claims = await extract_claims_from_paper(paper, llm)
            return paper.pmid, claims
            
    tasks = [process_paper(p) for p in papers]
    results = await asyncio.gather(*tasks)
    
    extracted = {}
    total_claims = 0
    for pmid, claims in results:
        extracted[pmid] = claims
        total_claims += len(claims)
        if len(claims) == 0:
            logger.info(f"Paper {pmid} returned 0 claims during extraction.")
            
    logger.info(f"Batch extraction completed. Extracted {total_claims} claims from {len(papers)} papers.")
    return extracted
