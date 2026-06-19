import logging
import asyncio
import xml.etree.ElementTree as ET
import aiohttp

from src.config import settings
from src.ingestion.pubmed import get_fetch_semaphore

from typing import Optional

logger = logging.getLogger(__name__)

async def fetch_full_text(pmid: str, session: Optional[aiohttp.ClientSession] = None) -> str | None:
    """Fetch full-text XML from PubMed Central (PMC) for open-access papers.
    
    1. Converts the PMID to a PMCID.
    2. If a PMCID is found, downloads the full XML from PMC EFetch.
    3. Returns the raw XML content, or None if not open-access or request fails.
    """
    if not pmid:
        return None

    if session is None:
        async with aiohttp.ClientSession() as local_session:
            return await _fetch_full_text_impl(pmid, local_session)
    else:
        return await _fetch_full_text_impl(pmid, session)

async def _fetch_full_text_impl(pmid: str, session: aiohttp.ClientSession) -> str | None:
    # 1. Convert PMID to PMCID
    conv_url = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
    params = {
        "ids": pmid,
        "format": "json",
        "tool": "rsce"
    }
    if settings.pubmed_email:
        params["email"] = settings.pubmed_email

    pmcid = None
    sem = get_fetch_semaphore()
    
    async def run_idconv(sess: aiohttp.ClientSession) -> str | None:
        for attempt in range(2):
            try:
                async with sess.get(conv_url, params=params, timeout=15) as resp:
                    if resp.status == 429:
                        logger.warning("PubMed rate limit (429) in ID conversion. Retrying in 2 seconds...")
                        await asyncio.sleep(2)
                        continue
                    resp.raise_for_status()
                    data = await resp.json()
                    records = data.get("records", [])
                    if records:
                        return records[0].get("pmcid")
                    return None
            except Exception as e:
                if attempt == 1:
                    logger.error(f"PMID to PMCID conversion failed after retries: {e}")
                else:
                    logger.warning(f"PMID to PMCID conversion attempt {attempt+1} failed, retrying: {e}")
                    await asyncio.sleep(2)
        return None

    async with sem:
        pmcid = await run_idconv(session)

    if not pmcid:
        logger.info(f"No PMCID found for PMID {pmid}. Paper is likely not open-access.")
        return None

    # 2. Fetch full-text XML using PMCID via PMC EFetch
    efetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    efetch_params = {
        "db": "pmc",
        "id": pmcid,
        "retmode": "xml",
        "tool": "rsce"
    }
    if settings.pubmed_email:
        efetch_params["email"] = settings.pubmed_email
    if settings.pubmed_api_key:
        efetch_params["api_key"] = settings.pubmed_api_key

    xml_content = None
    
    async def run_efetch(sess: aiohttp.ClientSession) -> str | None:
        for attempt in range(2):
            try:
                async with sess.get(efetch_url, params=efetch_params, timeout=30) as resp:
                    if resp.status == 429:
                        logger.warning("PMC rate limit (429) in efetch. Retrying in 2 seconds...")
                        await asyncio.sleep(2)
                        continue
                    resp.raise_for_status()
                    return await resp.text()
            except Exception as e:
                if attempt == 1:
                    logger.error(f"PMC XML fetch failed after retries: {e}")
                else:
                    logger.warning(f"PMC XML fetch attempt {attempt+1} failed, retrying: {e}")
                    await asyncio.sleep(2)
        return None

    async with sem:
        xml_content = await run_efetch(session)

    return xml_content

def parse_pmc_xml(xml_content: str) -> dict[str, str]:
    """Parse PMC XML text into sections: Introduction, Methods, Results, Discussion.
    
    Returns a dictionary mapping section names to their text content.
    """
    sections = {
        "Introduction": "",
        "Methods": "",
        "Results": "",
        "Discussion": ""
    }

    if not xml_content:
        return sections

    try:
        # We encode to utf-8 bytes first to satisfy ElementTree parsing behavior
        root = ET.fromstring(xml_content.encode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse PMC XML: {e}")
        return sections

    body = root.find(".//body")
    if body is None:
        logger.info("No body tag found in PMC XML.")
        return sections

    # Iterate through top-level section elements under body
    for sec in body.findall("./sec"):
        title_el = sec.find("title")
        title_text = "".join(title_el.itertext()).strip() if title_el is not None else ""

        # Categorize section based on keyword in title
        title_lower = title_text.lower()
        category = None

        if "introduction" in title_lower or "background" in title_lower:
            category = "Introduction"
        elif "method" in title_lower or "material" in title_lower or "procedure" in title_lower:
            category = "Methods"
        elif "result" in title_lower or "finding" in title_lower:
            category = "Results"
        elif "discussion" in title_lower or "conclusion" in title_lower:
            category = "Discussion"

        if category:
            # Extract text from all paragraphs in this section (and nested sections)
            paragraphs = []
            for p in sec.findall(".//p"):
                p_text = "".join(p.itertext()).strip()
                if p_text:
                    paragraphs.append(p_text)
            sec_text = "\n\n".join(paragraphs)

            if sections[category]:
                sections[category] += "\n\n" + sec_text
            else:
                sections[category] = sec_text

    return sections
