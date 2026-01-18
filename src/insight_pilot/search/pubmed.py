"""PubMed search module."""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

import requests

from insight_pilot.errors import ErrorCode, SkillError, classify_request_error
from insight_pilot.models import utc_now_iso

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
MIN_INTERVAL = 1 / 3  # 3 requests per second

_LAST_REQUEST_AT = 0.0


def throttle() -> None:
    """Throttle requests to respect NCBI rate limits."""
    global _LAST_REQUEST_AT
    now = time.time()
    elapsed = now - _LAST_REQUEST_AT
    if elapsed < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - elapsed)
    _LAST_REQUEST_AT = time.time()


def request_with_backoff(
    url: str,
    params: Dict[str, str],
    max_retries: int,
) -> requests.Response:
    """Request with exponential backoff and throttling."""
    delay = 1.0
    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        throttle()
        try:
            response = requests.get(url, params=params, timeout=60)
            if response.status_code in {429, 500, 502, 503, 504}:
                if attempt == max_retries - 1:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    time.sleep(float(retry_after))
                else:
                    time.sleep(delay)
                    delay = min(delay * 2, 60)
                continue
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt == max_retries - 1:
                raise SkillError(
                    message=str(exc),
                    code=classify_request_error(exc),
                ) from exc
            time.sleep(delay)
            delay = min(delay * 2, 60)

    raise last_error or RuntimeError("Unreachable request retry state")


def esearch(query: str, limit: int, email: str, max_retries: int) -> List[str]:
    """Run ESearch to get PubMed IDs."""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": str(limit),
        "retmode": "json",
        "email": email,
    }
    response = request_with_backoff(f"{BASE_URL}/esearch.fcgi", params, max_retries)
    payload = response.json()
    return payload.get("esearchresult", {}).get("idlist", []) or []


def esummary(pmids: List[str], email: str, max_retries: int) -> Dict[str, object]:
    """Run ESummary to get metadata."""
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
        "email": email,
    }
    response = request_with_backoff(f"{BASE_URL}/esummary.fcgi", params, max_retries)
    return response.json()


def efetch(pmids: List[str], email: str, max_retries: int) -> str:
    """Run EFetch to get XML with abstracts."""
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "email": email,
    }
    response = request_with_backoff(f"{BASE_URL}/efetch.fcgi", params, max_retries)
    return response.text


def chunk_list(values: List[str], size: int) -> List[List[str]]:
    """Split list into chunks."""
    if size <= 0:
        return [values]
    return [values[i:i + size] for i in range(0, len(values), size)]


def normalize_pub_date(value: str) -> Optional[str]:
    """Normalize PubMed date strings to ISO-ish format."""
    if not value:
        return None
    value = value.strip()
    parts = value.replace(",", "").split()
    if not parts:
        return None
    year = parts[0]
    if not year.isdigit():
        return None
    month = None
    day = None
    if len(parts) >= 2:
        month_map = {
            "jan": "01",
            "feb": "02",
            "mar": "03",
            "apr": "04",
            "may": "05",
            "jun": "06",
            "jul": "07",
            "aug": "08",
            "sep": "09",
            "oct": "10",
            "nov": "11",
            "dec": "12",
        }
        month_value = parts[1][:3].lower()
        month = month_map.get(month_value)
    if len(parts) >= 3 and parts[2].isdigit():
        day = parts[2].zfill(2)
    if month and day:
        return f"{year}-{month}-{day}"
    if month:
        return f"{year}-{month}"
    return year


def parse_pubmed_xml(xml_text: str) -> Dict[str, Dict[str, object]]:
    """Parse PubMed XML to extract abstracts and metadata."""
    root = ET.fromstring(xml_text)
    records: Dict[str, Dict[str, object]] = {}

    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//MedlineCitation/PMID") or ""
        if not pmid:
            continue

        abstract_texts = []
        for abstract in article.findall(".//Abstract/AbstractText"):
            label = abstract.attrib.get("Label")
            text = (abstract.text or "").strip()
            if not text:
                continue
            if label:
                abstract_texts.append(f"{label}: {text}")
            else:
                abstract_texts.append(text)
        abstract = " ".join(abstract_texts).strip() or None

        keywords = [
            kw.text.strip()
            for kw in article.findall(".//KeywordList/Keyword")
            if kw.text
        ]
        mesh_terms = [
            mesh.text.strip()
            for mesh in article.findall(".//MeshHeading/DescriptorName")
            if mesh.text
        ]

        doi = None
        pmc = None
        for article_id in article.findall(".//ArticleIdList/ArticleId"):
            id_type = article_id.attrib.get("IdType")
            value = (article_id.text or "").strip()
            if id_type == "doi":
                doi = value
            elif id_type == "pmc":
                pmc = value

        records[pmid] = {
            "abstract": abstract,
            "keywords": keywords,
            "mesh_terms": mesh_terms,
            "doi": doi,
            "pmc": pmc,
        }

    return records


def build_item(summary: Dict[str, object], details: Dict[str, object]) -> Dict[str, object]:
    """Build standard item from PubMed summary and details."""
    pmid = str(summary.get("uid") or "")
    title = summary.get("title") or ""
    authors = [a.get("name") for a in summary.get("authors", []) if a.get("name")]
    pubdate = normalize_pub_date(summary.get("pubdate") or "")

    doi = details.get("doi") or summary.get("elocationid")
    if doi and doi.startswith("doi:"):
        doi = doi.replace("doi:", "").strip()

    pmc = details.get("pmc")
    pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc}/pdf/" if pmc else None

    tags = []
    tags.extend(details.get("keywords", []))
    tags.extend(details.get("mesh_terms", []))

    return {
        "type": "paper",
        "title": title,
        "authors": authors,
        "date": pubdate,
        "abstract": details.get("abstract"),
        "identifiers": {
            "doi": doi,
            "other": {
                "pmid": pmid,
                "pmc": pmc or "",
            },
        },
        "urls": {
            "abstract": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
            "pdf": pdf_url,
            "publisher": summary.get("source"),
        },
        "tags": tags,
        "source": "pubmed",
        "download_status": "pending" if pdf_url else "unavailable",
        "collected_at": utc_now_iso(),
    }


def search(
    query: str,
    limit: int = 50,
    email: str = "",
    include_abstract: bool = True,
    max_retries: int = 3,
) -> List[Dict[str, object]]:
    """Search PubMed and return parsed results."""
    if not email:
        raise SkillError(
            message="PUBMED_EMAIL is required for PubMed API requests",
            code=ErrorCode.MISSING_REQUIRED_ARG,
        )

    pmids = esearch(query, limit, email, max_retries)
    if not pmids:
        return []

    summaries: Dict[str, object] = {}
    for chunk in chunk_list(pmids, 200):
        summary_payload = esummary(chunk, email, max_retries)
        result = summary_payload.get("result", {}) or {}
        for uid in result.get("uids", []) or []:
            if uid in result:
                summaries[uid] = result[uid]

    details_by_id: Dict[str, Dict[str, object]] = {pid: {} for pid in pmids}
    if include_abstract:
        details_by_id = {}
        for chunk in chunk_list(pmids, 200):
            xml_text = efetch(chunk, email, max_retries)
            details_by_id.update(parse_pubmed_xml(xml_text))

    items: List[Dict[str, object]] = []
    for pmid in pmids:
        summary = summaries.get(pmid)
        if not summary:
            continue
        details = details_by_id.get(pmid, {})
        items.append(build_item(summary, details))

    return items
