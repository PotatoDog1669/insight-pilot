"""RSS/Atom search module."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urljoin

import feedparser

from insight_pilot.models import utc_now_iso


def normalize_datetime(value: Optional[object]) -> Optional[str]:
    """Normalize feedparser date structures to ISO."""
    if not value:
        return None
    if isinstance(value, str):
        return value
    if hasattr(value, "tm_year"):
        dt = datetime(
            value.tm_year,
            value.tm_mon,
            value.tm_mday,
            value.tm_hour,
            value.tm_min,
            value.tm_sec,
            tzinfo=timezone.utc,
        )
        return dt.isoformat().replace("+00:00", "Z")
    return None


def extract_entry_content(entry: Dict[str, object]) -> str:
    """Extract content from RSS entry."""
    content = ""
    if entry.get("content"):
        content = entry["content"][0].get("value", "") if entry["content"] else ""
    if not content:
        content = entry.get("summary", "") or entry.get("description", "")
    return content.strip()


def matches_query(title: str, content: str, query: str) -> bool:
    """Check if query matches title or content."""
    if not query:
        return True
    query_lower = query.lower()
    return query_lower in (title or "").lower() or query_lower in (content or "").lower()


def search(
    feed_url: str,
    limit: int = 50,
    query: str = "",
    source_name: str = "",
) -> List[Dict[str, object]]:
    """Parse RSS/Atom feed into items."""
    parsed = feedparser.parse(feed_url)
    items: List[Dict[str, object]] = []

    for entry in parsed.entries:
        title = (entry.get("title") or "").strip()
        content = extract_entry_content(entry)
        if not matches_query(title, content, query):
            continue

        link = entry.get("link") or entry.get("id") or ""
        if link:
            link = urljoin(feed_url, link)

        authors = []
        if entry.get("author"):
            authors.append(entry.get("author"))
        if entry.get("authors"):
            authors.extend([a.get("name") for a in entry.get("authors") if a.get("name")])

        tags = [tag.get("term") for tag in entry.get("tags", []) if tag.get("term")]

        published = normalize_datetime(entry.get("published_parsed") or entry.get("updated_parsed"))

        items.append({
            "type": "blog",
            "title": title,
            "authors": [a for a in authors if a],
            "date": published[:10] if published else None,
            "summary": entry.get("summary") or None,
            "abstract": content or None,
            "identifiers": {
                "other": {
                    "rss_id": entry.get("id") or "",
                }
            },
            "urls": {
                "abstract": link,
            },
            "metadata": {
                "tags": tags,
                "source_name": source_name,
            },
            "source": "rss",
            "download_status": "unavailable",
            "collected_at": utc_now_iso(),
        })

        if len(items) >= limit:
            break

    return items
