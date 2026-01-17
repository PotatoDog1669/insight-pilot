"""OpenAlex search module."""
from __future__ import annotations

import time
from typing import Dict, List, Optional

import requests

from insight_pilot.errors import ErrorCode, SkillError, classify_request_error
from insight_pilot.models import utc_now_iso

BASE_URL = "https://api.openalex.org/works"


def reconstruct_abstract(inverted_index: Optional[Dict[str, List[int]]]) -> Optional[str]:
    """Reconstruct abstract from OpenAlex inverted index format."""
    if not inverted_index:
        return None
    max_pos = max((max(positions) for positions in inverted_index.values()), default=-1)
    if max_pos < 0:
        return None
    words = [""] * (max_pos + 1)
    for word, positions in inverted_index.items():
        for pos in positions:
            if 0 <= pos < len(words):
                words[pos] = word
    return " ".join(words).strip() or None


def select_pdf_url(work: Dict[str, object]) -> Optional[str]:
    """Select best PDF URL from work object."""
    primary_location = work.get("primary_location") or {}
    if isinstance(primary_location, dict) and primary_location.get("pdf_url"):
        return primary_location["pdf_url"]

    best_oa = work.get("best_oa_location") or {}
    if isinstance(best_oa, dict) and best_oa.get("pdf_url"):
        return best_oa["pdf_url"]

    open_access = work.get("open_access") or {}
    if isinstance(open_access, dict) and open_access.get("oa_url"):
        return open_access["oa_url"]

    return None


def transform_work(work: Dict[str, object]) -> Dict[str, object]:
    """Transform OpenAlex work to standard item format."""
    ids = work.get("ids") or {}
    authors = []
    for authorship in work.get("authorships", []) or []:
        author = authorship.get("author", {}) or {}
        name = author.get("display_name")
        if name:
            authors.append(name)

    doi = ids.get("doi")
    if doi and doi.startswith("https://doi.org/"):
        doi = doi.replace("https://doi.org/", "")

    pdf_url = select_pdf_url(work)

    return {
        "type": "paper",
        "title": work.get("title", "") or "",
        "authors": authors,
        "date": work.get("publication_date"),
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "identifiers": {"doi": doi, "openalex_id": ids.get("openalex")},
        "urls": {
            "abstract": work.get("id"),
            "pdf": pdf_url,
            "publisher": ids.get("doi"),
        },
        "citation_count": work.get("cited_by_count"),
        "source": "openalex",
        "download_status": "pending" if pdf_url else "unavailable",
        "collected_at": utc_now_iso(),
    }


def request_with_backoff(
    url: str,
    params: Dict[str, str],
    max_retries: int,
) -> requests.Response:
    """Make request with exponential backoff."""
    delay = 1.0
    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
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


def fetch_page(
    query: str,
    per_page: int,
    cursor: str,
    since: Optional[str],
    until: Optional[str],
    mailto: str,
    title_only: bool,
    max_retries: int,
) -> Dict[str, object]:
    """Fetch a single page of results."""
    filters = []
    if title_only:
        filters.append(f"title.search:{query}")
    if since:
        filters.append(f"from_publication_date:{since}")
    if until:
        filters.append(f"to_publication_date:{until}")

    params = {
        "per-page": str(per_page),
        "cursor": cursor,
    }
    if filters:
        params["filter"] = ",".join(filters)
    if not title_only:
        params["search"] = query
    if mailto:
        params["mailto"] = mailto

    response = request_with_backoff(BASE_URL, params, max_retries)
    return response.json()


def search(
    query: str,
    limit: int = 50,
    since: Optional[str] = None,
    until: Optional[str] = None,
    mailto: str = "",
    title_only: bool = False,
    max_retries: int = 3,
) -> List[Dict[str, object]]:
    """Search OpenAlex and return parsed results."""
    per_page = min(limit, 200)
    cursor = "*"
    results: List[Dict[str, object]] = []

    while len(results) < limit:
        page = fetch_page(
            query,
            per_page,
            cursor,
            since,
            until,
            mailto,
            title_only,
            max_retries,
        )
        works = page.get("results", [])
        results.extend([transform_work(work) for work in works])
        cursor = page.get("meta", {}).get("next_cursor")
        if not cursor or not works:
            break
        if len(results) >= limit:
            break

    return results[:limit]
