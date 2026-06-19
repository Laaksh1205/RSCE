import logging
import re
import aiohttp
from src.config import settings

logger = logging.getLogger(__name__)

async def fetch_pdf_url_from_unpaywall(doi: str, session: aiohttp.ClientSession) -> str | None:
    """Query the Unpaywall API to find an open-access PDF URL for a given DOI."""
    if not doi:
        return None
        
    # Standardize DOI formatting
    doi_clean = doi.strip()
    # If the DOI is inside a URL, extract it
    if doi_clean.lower().startswith("http"):
        # Match doi from URL e.g. doi.org/10.1038/...
        match = re.search(r'doi\.org/(10\.\d{4,9}/[-._;()/:A-Z0-9]+)', doi_clean, re.IGNORECASE)
        if match:
            doi_clean = match.group(1)
            
    url = f"https://api.unpaywall.org/v2/{doi_clean}"
    email = settings.pubmed_email or "rsce_agent@example.com"
    params = {"email": email}
    
    try:
        async with session.get(url, params=params, timeout=15) as resp:
            if resp.status == 200:
                data = await resp.json()
                best_oa = data.get("best_oa_location")
                if best_oa:
                    pdf_url = best_oa.get("url_for_pdf")
                    if pdf_url:
                        return pdf_url
            else:
                logger.debug(f"Unpaywall returned status {resp.status} for DOI {doi_clean}")
    except Exception as e:
        logger.warning(f"Unpaywall request failed for DOI {doi_clean}: {e}")
    return None

async def download_and_extract_pdf_text(pdf_url: str, session: aiohttp.ClientSession) -> str | None:
    """Download PDF from URL and extract text using PyMuPDF."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        async with session.get(pdf_url, headers=headers, timeout=30) as resp:
            resp.raise_for_status()
            pdf_bytes = await resp.read()
            
        import fitz  # PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text_parts = []
        for page in doc:
            page_text = page.get_text()
            if page_text:
                text_parts.append(page_text)
                
        raw_text = "\n\n".join(text_parts)
        if not raw_text.strip():
            return None
            
        return structure_pdf_text(raw_text)
    except Exception as e:
        logger.warning(f"Failed to download/parse PDF from {pdf_url}: {e}")
        return None

def structure_pdf_text(raw_text: str) -> str:
    """Structure raw text from PDF into pseudo-PMC-XML sections (Introduction, Methods, Results, Discussion)."""
    raw_text_clean = raw_text.replace("\r\n", "\n")
    lines = raw_text_clean.split("\n")
    
    structured_parts = []
    current_section = "INTRODUCTION"
    
    # Store paragraphs for the current section
    section_paragraphs = []
    # Store lines of the current paragraph block being built
    current_paragraph_lines = []
    
    # Heuristics for common section headers
    section_patterns = {
        "INTRODUCTION": re.compile(r'^(?:(?:[0-9]+\.?\s*)?(?:introduction|background))$', re.IGNORECASE),
        "METHODS": re.compile(r'^(?:(?:[0-9]+\.?\s*)?(?:methods|methodology|materials\s*and\s*methods|methods\s*and\s*materials|experimental\s*procedures?))$', re.IGNORECASE),
        "RESULTS": re.compile(r'^(?:(?:[0-9]+\.?\s*)?(?:results|findings))$', re.IGNORECASE),
        "DISCUSSION": re.compile(r'^(?:(?:[0-9]+\.?\s*)?(?:discussion|conclusions?|summary|discussion\s*and\s*conclusions?))$', re.IGNORECASE),
    }
    
    def flush_paragraph():
        if current_paragraph_lines:
            paragraph_text = " ".join([line_str.strip() for line_str in current_paragraph_lines if line_str.strip()])
            normalized_text = re.sub(r'\s+', ' ', paragraph_text)
            if normalized_text:
                section_paragraphs.append(normalized_text)
            current_paragraph_lines.clear()
            
    def flush_section(new_sec_name):
        nonlocal current_section
        flush_paragraph()
        if section_paragraphs:
            structured_parts.append(f"=== {current_section} ===\n" + "\n\n".join(section_paragraphs))
            section_paragraphs.clear()
        current_section = new_sec_name
        
    for line in lines:
        cleaned_line = line.strip()
        if not cleaned_line:
            flush_paragraph()
            continue
            
        # Check if the line is a section header
        found_new_sec = None
        if len(cleaned_line) < 60:
            match_text = re.sub(r'^[0-9\.\s\-]+', '', cleaned_line).strip()
            # Remove trailing/leading punctuation
            match_text = re.sub(r'^[\:\-\s\.]+|[\:\-\s\.]+$', '', match_text).strip()
            for sec_name, pattern in section_patterns.items():
                if pattern.match(match_text):
                    found_new_sec = sec_name
                    break
                    
        if found_new_sec:
            flush_section(found_new_sec)
        else:
            current_paragraph_lines.append(cleaned_line)
            
    # Flush remaining text
    flush_paragraph()
    if section_paragraphs:
        structured_parts.append(f"=== {current_section} ===\n" + "\n\n".join(section_paragraphs))
        
    return "\n\n".join(structured_parts)
