"""arXiv search module."""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

import requests

from insight_pilot.errors import ErrorCode, SkillError, classify_request_error
from insight_pilot.models import utc_now_iso

BASE_URL = "https://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def normalize_submitted_date(value: str, label: str, end_of_day: bool) -> str:
    """Normalize date to arXiv format (YYYYMMDDHHMM)."""
    value = (value or "").strip()
    if not value:
        raise ValueError(f"{label} is required for submittedDate filtering")
    if not value.isdigit():
        raise ValueError(f"{label} must be digits in YYYYMMDD or YYYYMMDDHHMM format")
    if len(value) == 8:
        return value + ("2359" if end_of_day else "0000")
    if len(value) == 12:
        return value
    raise ValueError(f"{label} must be YYYYMMDD or YYYYMMDDHHMM")


def build_search_query(
    query: str,
    submitted_from: Optional[str],
    submitted_to: Optional[str],
) -> str:
    """Build arXiv search query string."""
    search_query = f"all:{query}"
    if submitted_from or submitted_to:
        if not (submitted_from and submitted_to):
            raise ValueError("Both submitted_from and submitted_to are required")
        start = normalize_submitted_date(submitted_from, "submitted_from", end_of_day=False)
        end = normalize_submitted_date(submitted_to, "submitted_to", end_of_day=True)
        search_query += f" AND submittedDate:[{start} TO {end}]"
    return search_query


def fetch(
    query: str,
    limit: int,
    start: int = 0,
    sort_by: str = "submittedDate",
    sort_order: str = "descending",
    submitted_from: Optional[str] = None,
    submitted_to: Optional[str] = None,
    max_retries: int = 3,
) -> str:
    """Fetch raw XML from arXiv API."""
    params = {
        "search_query": build_search_query(query, submitted_from, submitted_to),
        "start": start,
        "max_results": limit,
        "sortBy": sort_by,
        "sortOrder": sort_order,
    }
    delay = 1.0
    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            response = requests.get(BASE_URL, params=params, timeout=60)
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
            return response.text
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


def extract_arxiv_id(identifier: str) -> str:
    """Extract arXiv ID from full identifier URL."""
    arxiv_id = identifier.split("/abs/")[-1]
    return re.sub(r"v\d+$", "", arxiv_id)


def find_pdf_link(entry: ET.Element) -> Optional[str]:
    """Find PDF link in entry."""
    for link in entry.findall("atom:link", ATOM_NS):
        if link.attrib.get("type") == "application/pdf":
            return link.attrib.get("href")
    return None


def parse_entries(xml_content: str) -> List[Dict[str, object]]:
    """Parse arXiv XML response into items."""
    root = ET.fromstring(xml_content)
    items: List[Dict[str, object]] = []

    for entry in root.findall("atom:entry", ATOM_NS):
        arxiv_id_full = entry.findtext("atom:id", default="", namespaces=ATOM_NS)
        arxiv_id = extract_arxiv_id(arxiv_id_full)
        title = entry.findtext("atom:title", default="", namespaces=ATOM_NS).strip()
        title = " ".join(title.split())
        summary = entry.findtext("atom:summary", default="", namespaces=ATOM_NS).strip()
        published = entry.findtext("atom:published", default="", namespaces=ATOM_NS)[:10]

        authors = [
            author.findtext("atom:name", default="", namespaces=ATOM_NS)
            for author in entry.findall("atom:author", ATOM_NS)
        ]

        doi = entry.findtext("arxiv:doi", default="", namespaces=ATOM_NS).strip() or None
        if not doi and arxiv_id:
            doi = f"10.48550/arXiv.{arxiv_id}"

        pdf_url = find_pdf_link(entry) or (f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None)

        items.append({
            "type": "paper",
            "title": title,
            "authors": authors,
            "date": published or None,
            "abstract": summary or None,
            "identifiers": {"arxiv_id": arxiv_id, "doi": doi},
            "urls": {
                "abstract": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else None,
                "pdf": pdf_url,
            },
            "source": "arxiv",
            "download_status": "pending",
            "collected_at": utc_now_iso(),
        })

    return items


def search(
    query: str,
    limit: int = 50,
    submitted_from: Optional[str] = None,
    submitted_to: Optional[str] = None,
    max_retries: int = 3,
) -> List[Dict[str, object]]:
    """Search arXiv and return parsed results."""
    xml_content = fetch(
        query=query,
        limit=limit,
        submitted_from=submitted_from,
        submitted_to=submitted_to,
        max_retries=max_retries,
    )
    return parse_entries(xml_content)
