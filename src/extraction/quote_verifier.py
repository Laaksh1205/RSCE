import string
import re
import uuid
import logging
from typing import Literal, Any
from rapidfuzz import fuzz

from src.config import settings
from src.models.claim import Claim, ExtractedClaim
from src.models.paper import Paper

logger = logging.getLogger(__name__)

def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation, and collapse whitespace."""
    if not text:
        return ""
    # Lowercase
    text = text.lower()
    # Strip punctuation
    text = text.translate(str.maketrans("", "", string.punctuation))
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def verify_quote_anchor(
    quote_anchor: str,
    source_text: str,
    pass_threshold: float = 85.0,
    flag_threshold: float = 70.0,
) -> tuple[Literal["PASS", "FLAG", "REJECT"], float]:
    """Verify a quote anchor against source text.
    
    Uses rapidfuzz.fuzz.partial_ratio.
    Returns: (status, score)
    """
    if not quote_anchor or not source_text:
        return "REJECT", 0.0
        
    norm_quote = normalize_text(quote_anchor)
    norm_source = normalize_text(source_text)
    
    # Calculate substring fuzzy similarity score (0 to 100)
    score = float(fuzz.partial_ratio(norm_quote, norm_source))
    
    if score >= pass_threshold:
        return "PASS", score
    elif score >= flag_threshold:
        return "FLAG", score
    else:
        return "REJECT", score

def verify_and_filter_claims(
    claims: list[ExtractedClaim],
    paper: Paper,
) -> tuple[list[Claim], dict[str, Any]]:
    """Verify all claims for a paper.
    
    - PASS: confidence_score unchanged (1.0)
    - FLAG: confidence_score *= 0.5 (0.5)
    - REJECT: claim discarded
    
    Returns: (verified_claims, stats)
    Stats: {"passed": int, "flagged": int, "rejected": int, "rejection_rate": float}
    """
    verified_claims = []
    stats = {
        "passed": 0,
        "flagged": 0,
        "rejected": 0,
        "rejection_rate": 0.0
    }
    
    total = len(claims)
    if total == 0:
        return [], stats
        
    for extracted in claims:
        section = "Abstract"
        is_primary_finding = True
        
        status, score = verify_quote_anchor(
            extracted.quote_anchor,
            paper.abstract_text,
            pass_threshold=settings.quote_anchor_pass_threshold,
            flag_threshold=settings.quote_anchor_flag_threshold
        )
        
        if status != "REJECT":
            if paper.abstract_text:
                lines = paper.abstract_text.split("\n")
                best_line_idx = -1
                best_line_score = -1.0
                for idx, line in enumerate(lines):
                    if not line.strip():
                        continue
                    norm_quote = normalize_text(extracted.quote_anchor)
                    norm_line = normalize_text(line)
                    line_score = float(fuzz.partial_ratio(norm_quote, norm_line))
                    if line_score > best_line_score:
                        best_line_score = line_score
                        best_line_idx = idx
                
                if best_line_idx != -1 and best_line_score >= settings.quote_anchor_flag_threshold:
                    matching_line = lines[best_line_idx].strip().lower()
                    non_primary_prefixes = ["background", "introduction", "intro", "method", "material", "procedure", "objective", "aim"]
                    for pref in non_primary_prefixes:
                        if matching_line.startswith(pref):
                            is_primary_finding = False
                            break
        elif paper.full_text:
            status, score = verify_quote_anchor(
                extracted.quote_anchor,
                paper.full_text,
                pass_threshold=settings.quote_anchor_pass_threshold,
                flag_threshold=settings.quote_anchor_flag_threshold
            )
            if status != "REJECT":
                import re
                parts = re.split(r'===\s*([A-Z\s]+)\s*===', paper.full_text)
                best_section = "Full Text"
                best_section_score = -1.0
                for i in range((len(parts) - 1) // 2):
                    sec_header = parts[i * 2 + 1].strip()
                    sec_content = parts[i * 2 + 2].strip()
                    if not sec_content:
                        continue
                    status_sec, score_sec = verify_quote_anchor(
                        extracted.quote_anchor,
                        sec_content,
                        pass_threshold=settings.quote_anchor_pass_threshold,
                        flag_threshold=settings.quote_anchor_flag_threshold
                    )
                    if status_sec != "REJECT" and score_sec > best_section_score:
                        best_section_score = score_sec
                        best_section = sec_header.title()
                
                section = best_section
                non_primary_sections = ["introduction", "methods", "background", "method", "material", "procedure", "objective", "aim"]
                if any(sec_term in section.lower() for sec_term in non_primary_sections):
                    is_primary_finding = False
            
        if status == "REJECT":
            stats["rejected"] += 1
            logger.warning(
                f"Claim rejected due to quote-anchor verification failure (score={score:.1f}%): "
                f"Quote: '{extracted.quote_anchor}' | Claim: '{extracted.text}' | Paper: {paper.pmid}"
            )
            continue
            
        confidence = 1.0
        if status == "FLAG":
            stats["flagged"] += 1
            confidence = 0.5
            logger.info(
                f"Claim flagged during quote-anchor verification (score={score:.1f}%, confidence halved): "
                f"Quote: '{extracted.quote_anchor}' | Paper: {paper.pmid}"
            )
        else:
            stats["passed"] += 1
            
        claim = Claim(
            id=uuid.uuid4(),
            text=extracted.text,
            normalized_text=normalize_text(extracted.text),
            paper_id=paper.pmid,
            section=section,
            authors=paper.authors,
            year=paper.year,
            confidence_score=confidence,
            claim_type=extracted.claim_type,
            polarity=extracted.polarity,
            entities=extracted.entities,
            population=extracted.population,
            context=extracted.context,
            quote_anchor=extracted.quote_anchor,
            study_design=extracted.study_design,
            is_primary_finding=is_primary_finding
        )
        verified_claims.append(claim)
        
    stats["rejection_rate"] = stats["rejected"] / total
    return verified_claims, stats
