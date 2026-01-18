"""Dev.to (Forem) search module."""
from __future__ import annotations

import time
from typing import Dict, List, Optional

import requests

from insight_pilot.errors import SkillError, classify_request_error
from insight_pilot.models import utc_now_iso

BASE_URL = "https://dev.to/api"


def request_with_backoff(
    url: str,
    params: Dict[str, str],
    max_retries: int,
) -> requests.Response:
    """Request with exponential backoff."""
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


def fetch_article_detail(article_id: int, max_retries: int) -> Dict[str, object]:
    """Fetch full article detail including body_markdown."""
    response = request_with_backoff(f"{BASE_URL}/articles/{article_id}", {}, max_retries)
    return response.json()


def search(
    query: str,
    limit: int = 50,
    tag: Optional[str] = None,
    username: Optional[str] = None,
    organization_id: Optional[int] = None,
    max_retries: int = 3,
) -> List[Dict[str, object]]:
    """Search Dev.to articles and return standardized items."""
    per_page = min(100, max(1, limit))
    page = 1
    results: List[Dict[str, object]] = []

    while len(results) < limit:
        params: Dict[str, str] = {
            "per_page": str(per_page),
            "page": str(page),
        }
        if query:
            params["search"] = query
        if tag:
            params["tag"] = tag
        if username:
            params["username"] = username
        if organization_id is not None:
            params["organization_id"] = str(organization_id)

        response = request_with_backoff(f"{BASE_URL}/articles", params, max_retries)
        articles = response.json()
        if not isinstance(articles, list) or not articles:
            break

        results.extend(articles)
        if len(articles) < per_page:
            break
        page += 1

    items: List[Dict[str, object]] = []
    detail_limit = min(len(results), 10)
    for idx, article in enumerate(results[:limit]):
        article_id = article.get("id")
        detail = article
        if article_id and idx < detail_limit:
            detail = fetch_article_detail(int(article_id), max_retries)

        author = detail.get("user", {}) or {}
        title = detail.get("title") or ""
        description = detail.get("description") or ""
        body_markdown = detail.get("body_markdown") or ""

        items.append({
            "type": "blog",
            "title": title,
            "authors": [author.get("name")] if author.get("name") else [],
            "date": (detail.get("published_at") or detail.get("created_at"))[:10]
            if detail.get("published_at") or detail.get("created_at") else None,
            "summary": description or None,
            "abstract": body_markdown.strip() or None,
            "identifiers": {
                "other": {
                    "devto_id": str(detail.get("id") or ""),
                    "slug": detail.get("slug") or "",
                }
            },
            "urls": {
                "abstract": detail.get("url"),
                "publisher": detail.get("canonical_url"),
                "other": {
                    "cover_image": detail.get("cover_image"),
                },
            },
            "metadata": {
                "tags": detail.get("tag_list") or [],
                "reading_time_minutes": detail.get("reading_time_minutes"),
                "positive_reactions": detail.get("positive_reactions_count"),
                "comments_count": detail.get("comments_count"),
            },
            "source": "devto",
            "download_status": "unavailable",
            "collected_at": utc_now_iso(),
        })

    return items
