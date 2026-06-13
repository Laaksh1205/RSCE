import logging
import asyncio
import re
import xml.etree.ElementTree as ET
import aiohttp
import weakref
from src.config import settings
from src.models.paper import Paper

logger = logging.getLogger(__name__)

PUBMED_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Shared semaphores bound to event loops to enforce global rate limits safely
_search_semaphores = weakref.WeakKeyDictionary()
_fetch_semaphores = weakref.WeakKeyDictionary()

_pubmed_key_index = 0

def _apply_pubmed_credentials(params: dict):
    global _pubmed_key_index
    creds = settings.pubmed_credentials
    if not creds:
        return
    idx = _pubmed_key_index % len(creds)
    email, api_key = creds[idx]
    if email:
        params["email"] = email
    if api_key:
        params["api_key"] = api_key

def _rotate_pubmed_credentials():
    global _pubmed_key_index
    creds = settings.pubmed_credentials
    if not creds:
        return
    old_idx = _pubmed_key_index % len(creds)
    _pubmed_key_index = (_pubmed_key_index + 1) % len(creds)
    logger.info(f"PubMed credentials rotated from index {old_idx} to {_pubmed_key_index} (total credentials: {len(creds)}).")

def get_search_semaphore() -> asyncio.Semaphore:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.Semaphore(settings.pubmed_concurrency)

    if loop not in _search_semaphores:
        _search_semaphores[loop] = asyncio.Semaphore(settings.pubmed_concurrency)
    return _search_semaphores[loop]

def get_fetch_semaphore() -> asyncio.Semaphore:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.Semaphore(settings.pubmed_concurrency)

    if loop not in _fetch_semaphores:
        _fetch_semaphores[loop] = asyncio.Semaphore(settings.pubmed_concurrency)
    return _fetch_semaphores[loop]

async def search_pubmed(query: str, max_results: int = 25) -> list[str]:
    """Search PubMed using esearch.fcgi and return a list of PMIDs.
    
    Uses ESearch: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi
    Params: db=pubmed, retmax=max_results, sort=relevance, retmode=json
    Returns: list of PMID strings
    """
    url = f"{PUBMED_BASE_URL}/esearch.fcgi"
    base_params = {
        "db": "pubmed",
        "term": query,
        "retmax": str(max_results),
        "sort": "relevance",
        "retmode": "json"
    }

    sem = get_search_semaphore()
    async with sem:
        async with aiohttp.ClientSession() as session:
            creds = settings.pubmed_credentials
            max_attempts = max(2, len(creds) * 2) if creds else 2
            consecutive_rate_limits = 0
            
            for attempt in range(max_attempts):
                params = base_params.copy()
                _apply_pubmed_credentials(params)
                
                try:
                    async with session.get(url, params=params, timeout=15) as response:
                        if response.status == 429:
                            logger.warning(
                                f"PubMed rate limit (429) in esearch. "
                                f"Rotating credentials and retrying... (Attempt {attempt+1}/{max_attempts})"
                            )
                            _rotate_pubmed_credentials()
                            consecutive_rate_limits += 1
                            if not creds or consecutive_rate_limits >= len(creds):
                                await asyncio.sleep(2)
                            continue
                        response.raise_for_status()
                        data = await response.json()
                        pmids = data.get("esearchresult", {}).get("idlist", [])
                        return pmids
                except Exception as e:
                    if attempt == max_attempts - 1:
                        logger.error(f"PubMed esearch failed after {max_attempts} attempts: {e}")
                        raise
                    logger.warning(f"PubMed esearch attempt {attempt+1} failed, retrying: {e}")
                    await asyncio.sleep(2)
                    consecutive_rate_limits = 0
    return []

def parse_pubmed_xml(xml_content: bytes) -> list[Paper]:
    """Parse PubMed EFetch XML into a list of Paper objects."""
    papers = []
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        logger.error(f"Error parsing PubMed XML: {e}")
        return []

    for article in root.findall('.//PubmedArticle'):
        try:
            # 1. PMID
            pmid_elem = article.find('.//MedlineCitation/PMID')
            pmid = pmid_elem.text if (pmid_elem is not None and pmid_elem.text) else ""
            if not pmid:
                continue

            # 2. Title
            title_elem = article.find('.//ArticleTitle')
            title = "".join(title_elem.itertext()).strip() if title_elem is not None else ""

            # 3. Authors
            authors = []
            author_list = article.findall('.//AuthorList/Author')
            for author in author_list:
                last_name = author.find('LastName')
                fore_name = author.find('ForeName')
                if fore_name is None:
                    fore_name = author.find('Initials')
                
                if last_name is not None and last_name.text:
                    name = f"{fore_name.text} {last_name.text}" if (fore_name is not None and fore_name.text) else last_name.text
                    authors.append(name)
                else:
                    collective = author.find('CollectiveName')
                    if collective is not None and collective.text:
                        authors.append(collective.text)

            # 4. Year
            year = 0
            year_elem = article.find('.//JournalIssue/PubDate/Year')
            if year_elem is not None and year_elem.text:
                try:
                    year = int(year_elem.text[:4])
                except ValueError:
                    pass
            else:
                medline_date = article.find('.//JournalIssue/PubDate/MedlineDate')
                if medline_date is not None and medline_date.text:
                    match = re.search(r'\b(19|20)\d{2}\b', medline_date.text)
                    if match:
                        year = int(match.group(0))

            # 5. Journal
            journal_elem = article.find('.//Journal/Title')
            if journal_elem is None:
                journal_elem = article.find('.//Journal/ISOAbbreviation')
            journal = journal_elem.text if (journal_elem is not None and journal_elem.text) else ""

            # 6. Abstract
            abstract_elems = article.findall('.//AbstractText')
            abstract_parts = []
            for elem in abstract_elems:
                label = elem.get('Label')
                text = "".join(elem.itertext()).strip()
                if text:
                    if label:
                        abstract_parts.append(f"{label}: {text}")
                    else:
                        abstract_parts.append(text)
            abstract_text = "\n".join(abstract_parts)

            # 7. DOI
            doi = None
            eloc = article.find('.//ELocationID[@EIdType="doi"]')
            if eloc is not None and eloc.text:
                doi = eloc.text
            else:
                for article_id in article.findall('.//ArticleIdList/ArticleId'):
                    if article_id.get('IdType') == 'doi' and article_id.text:
                        doi = article_id.text
                        break

            paper = Paper(
                pmid=pmid,
                title=title,
                authors=authors,
                year=year,
                journal=journal,
                abstract_text=abstract_text,
                doi=doi
            )
            papers.append(paper)
        except Exception as e:
            logger.warning(f"Error parsing individual PubMed article XML: {e}")
            continue

    return papers

async def fetch_abstracts(pmids: list[str]) -> list[Paper]:
    """Fetch abstract + metadata for a batch of PMIDs.
    
    Uses EFetch: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi
    Params: db=pubmed, rettype=xml
    Parses XML to extract: title, authors, year, journal, abstract
    Returns: list of Paper objects
    """
    if not pmids:
        return []

    url = f"{PUBMED_BASE_URL}/efetch.fcgi"
    base_params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": "xml",
        "retmode": "xml"
    }

    sem = get_fetch_semaphore()
    xml_content = None

    async with sem:
        async with aiohttp.ClientSession() as session:
            creds = settings.pubmed_credentials
            max_attempts = max(2, len(creds) * 2) if creds else 2
            consecutive_rate_limits = 0
            
            for attempt in range(max_attempts):
                params = base_params.copy()
                _apply_pubmed_credentials(params)
                
                try:
                    async with session.get(url, params=params, timeout=30) as response:
                        if response.status == 429:
                            logger.warning(
                                f"PubMed rate limit (429) in efetch. "
                                f"Rotating credentials and retrying... (Attempt {attempt+1}/{max_attempts})"
                            )
                            _rotate_pubmed_credentials()
                            consecutive_rate_limits += 1
                            if not creds or consecutive_rate_limits >= len(creds):
                                await asyncio.sleep(2)
                            continue
                        response.raise_for_status()
                        xml_content = await response.read()
                        break
                except Exception as e:
                    if attempt == max_attempts - 1:
                        logger.error(f"PubMed efetch failed after {max_attempts} attempts: {e}")
                        raise
                    logger.warning(f"PubMed efetch attempt {attempt+1} failed, retrying: {e}")
                    await asyncio.sleep(2)
                    consecutive_rate_limits = 0

    if not xml_content:
        return []

    return parse_pubmed_xml(xml_content)

async def ingest_papers(query: str, max_results: int = 25) -> list[Paper]:
    """End-to-end: query → PMIDs → Papers.
    
    Applies rate limiting (3 req/sec via asyncio.Semaphore).
    Handles < min_papers gracefully (warns).
    """
    pmids = await search_pubmed(query, max_results)
    if not pmids:
        logger.warning(f"No papers found for query: '{query}'")
        return []

    if len(pmids) < settings.min_papers:
        logger.warning(f"Only {len(pmids)} papers found for query '{query}'. Minimum threshold is {settings.min_papers}.")

    papers = await fetch_abstracts(pmids)
    return papers
