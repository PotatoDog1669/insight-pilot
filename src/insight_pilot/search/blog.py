"""Blog platform search module (Ghost/WordPress/RSS)."""
from __future__ import annotations

import re
import time
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests

from insight_pilot.errors import ErrorCode, SkillError, classify_request_error
from insight_pilot.models import utc_now_iso
from insight_pilot.search import rss as rss_search


def request_with_backoff(url: str, params: Dict[str, str], max_retries: int) -> requests.Response:
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


def detect_platform_from_html(html: str) -> Optional[str]:
    """Detect blog platform from HTML."""
    lower = html.lower()
    if "contentapikey" in lower or "content-api-key" in lower:
        return "ghost"
    if "ghost" in lower and "content-api-key" in lower:
        return "ghost"
    if "ghost" in lower and "ghost.org" in lower:
        return "ghost"
    if "wp-json" in lower or "wordpress" in lower or "wp-content" in lower:
        return "wordpress"
    return None


def discover_ghost_api_key(html: str) -> Optional[str]:
    """Discover Ghost Content API key from HTML."""
    patterns = [
        r"contentApiKey\":\"([a-f0-9]{24,})\"",
        r"content_api_key\":\"([a-f0-9]{24,})\"",
        r"data-ghost-api-key=\"([a-f0-9]{24,})\"",
        r"content-api-key\" content=\"([a-f0-9]{24,})\"",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def discover_rss_url(html: str, base_url: str) -> Optional[str]:
    """Discover RSS/Atom URL from HTML."""
    pattern = r'<link[^>]+type="application/(?:rss\+xml|atom\+xml)"[^>]+>'
    matches = re.findall(pattern, html, re.IGNORECASE)
    for match in matches:
        href_match = re.search(r'href="([^"]+)"', match, re.IGNORECASE)
        if href_match:
            return urljoin(base_url, href_match.group(1))
    return None


def normalize_base_url(url: str) -> str:
    """Normalize base URL for API discovery."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def search_ghost(
    base_url: str,
    api_key: str,
    query: str,
    limit: int,
    max_retries: int,
) -> List[Dict[str, object]]:
    """Search Ghost Content API."""
    api_url = urljoin(base_url, "/ghost/api/content/posts/")
    params = {
        "key": api_key,
        "limit": str(min(100, limit)),
        "include": "tags,authors",
    }
    if query:
        params["filter"] = f'title:~"{query}"'

    response = request_with_backoff(api_url, params, max_retries)
    payload = response.json()
    posts = payload.get("posts", []) or []
    items: List[Dict[str, object]] = []

    for post in posts[:limit]:
        authors = [a.get("name") for a in post.get("authors", []) if a.get("name")]
        tags = [t.get("name") for t in post.get("tags", []) if t.get("name")]
        items.append({
            "type": "blog",
            "title": post.get("title") or "",
            "authors": authors,
            "date": (post.get("published_at") or "")[:10] or None,
            "summary": post.get("excerpt") or None,
            "abstract": post.get("html") or post.get("plaintext"),
            "identifiers": {
                "other": {
                    "ghost_id": post.get("id") or "",
                    "slug": post.get("slug") or "",
                }
            },
            "urls": {
                "abstract": post.get("url"),
                "other": {
                    "feature_image": post.get("feature_image"),
                },
            },
            "metadata": {
                "tags": tags,
                "platform": "ghost",
            },
            "source": "blog",
            "download_status": "unavailable",
            "collected_at": utc_now_iso(),
        })

    return items


def search_wordpress(
    base_url: str,
    query: str,
    limit: int,
    categories: Optional[List[int]] = None,
    tags: Optional[List[int]] = None,
    max_retries: int = 3,
) -> List[Dict[str, object]]:
    """Search WordPress REST API."""
    api_url = urljoin(base_url, "/wp-json/wp/v2/posts")
    per_page = min(100, max(1, limit))
    page = 1
    items: List[Dict[str, object]] = []

    while len(items) < limit:
        params = {
            "search": query,
            "per_page": str(per_page),
            "page": str(page),
            "_embed": "1",
        }
        if categories:
            params["categories"] = ",".join(str(c) for c in categories)
        if tags:
            params["tags"] = ",".join(str(t) for t in tags)

        try:
            response = request_with_backoff(api_url, params, max_retries)
        except SkillError:
            break
        posts = response.json()
        if not isinstance(posts, list) or not posts:
            break

        for post in posts:
            title = (post.get("title", {}) or {}).get("rendered", "")
            content = (post.get("content", {}) or {}).get("rendered", "")
            excerpt = (post.get("excerpt", {}) or {}).get("rendered", "")
            authors = []
            embedded = post.get("_embedded", {}) or {}
            if embedded.get("author"):
                authors = [a.get("name") for a in embedded.get("author", []) if a.get("name")]

            items.append({
                "type": "blog",
                "title": title or "",
                "authors": authors,
                "date": (post.get("date") or "")[:10] or None,
                "summary": excerpt or None,
                "abstract": content or None,
                "identifiers": {
                    "other": {
                        "wordpress_id": str(post.get("id") or ""),
                        "slug": post.get("slug") or "",
                    }
                },
                "urls": {
                    "abstract": post.get("link"),
                },
                "metadata": {
                    "platform": "wordpress",
                    "tags": post.get("tags") or [],
                    "categories": post.get("categories") or [],
                    "featured_media": post.get("featured_media"),
                },
                "source": "blog",
                "download_status": "unavailable",
                "collected_at": utc_now_iso(),
            })

        if len(posts) < per_page:
            break
        page += 1

    return items[:limit]


def search_blog(
    url: str,
    query: str,
    limit: int,
    platform: str,
    api_key: Optional[str],
    max_retries: int,
) -> List[Dict[str, object]]:
    """Search a single blog source, with fallback to RSS."""
    base_url = normalize_base_url(url)
    fallback_reason = None
    try:
        if platform == "ghost":
            if not api_key or api_key == "auto":
                response = request_with_backoff(url, {}, max_retries)
                api_key = discover_ghost_api_key(response.text)
            if not api_key:
                raise SkillError("Ghost API key not found", ErrorCode.MISSING_REQUIRED_ARG)
            return search_ghost(base_url, api_key, query, limit, max_retries)
        if platform == "wordpress":
            return search_wordpress(base_url, query, limit, max_retries=max_retries)
    except SkillError as exc:
        if platform == "ghost":
            fallback_reason = (
                "ghost_api_key_missing"
                if exc.code == ErrorCode.MISSING_REQUIRED_ARG
                else "ghost_api_failed"
            )
        elif platform == "wordpress":
            fallback_reason = "wordpress_api_failed"
        else:
            fallback_reason = "api_failed"

    # Fallback to RSS
    try:
        response = request_with_backoff(url, {}, max_retries)
        rss_url = discover_rss_url(response.text, base_url)
        if rss_url:
            items = rss_search.search(rss_url, limit=limit, query=query, source_name=url)
            if fallback_reason:
                for item in items:
                    metadata = item.get("metadata", {}) or {}
                    metadata["fallback_reason"] = fallback_reason
                    item["metadata"] = metadata
            return items
    except SkillError:
        pass

    items = rss_search.search(url, limit=limit, query=query, source_name=url)
    if fallback_reason:
        for item in items:
            metadata = item.get("metadata", {}) or {}
            metadata["fallback_reason"] = fallback_reason
            item["metadata"] = metadata
    return items


def auto_detect_platform(url: str, max_retries: int) -> Optional[str]:
    """Auto detect blog platform."""
    try:
        response = request_with_backoff(url, {}, max_retries)
        return detect_platform_from_html(response.text)
    except SkillError:
        return None


def search(
    sources: List[Dict[str, object]],
    query: str,
    limit: int = 50,
    max_retries: int = 3,
    name_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
) -> List[Dict[str, object]]:
    """Search across multiple blog sources."""
    items: List[Dict[str, object]] = []
    per_source = max(1, limit // max(1, len(sources)))

    for source in sources:
        name = source.get("name") or ""
        if name_filter and name_filter.lower() not in name.lower():
            continue
        category = source.get("category") or ""
        if category_filter and category_filter.lower() != str(category).lower():
            continue

        platform = source.get("type") or "auto"
        url = source.get("url") or ""
        api_key = source.get("api_key")

        if platform == "auto":
            detected = auto_detect_platform(url, max_retries)
            platform = detected or "rss"

        results = search_blog(
            url=url,
            query=query,
            limit=per_source,
            platform=platform,
            api_key=api_key,
            max_retries=max_retries,
        )

        for item in results:
            metadata = item.get("metadata", {}) or {}
            metadata["source_name"] = name
            metadata["category"] = category
            metadata["source_url"] = url
            item["metadata"] = metadata
            item["source"] = "blog"
            items.append(item)

    return items[:limit]
