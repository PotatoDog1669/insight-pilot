"""Deduplicate items by DOI, arXiv ID, or title similarity."""
from __future__ import annotations

from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Dict, List, Tuple


def normalize_title(title: str) -> str:
    """Normalize title for comparison."""
    return " ".join((title or "").lower().split())


def normalize_doi(doi: str) -> str:
    """Normalize DOI for comparison."""
    doi = (doi or "").strip()
    if doi.startswith("https://doi.org/"):
        doi = doi.replace("https://doi.org/", "")
    return doi.lower()


def get_dedup_key(item: Dict[str, object]) -> str:
    """Get deduplication key for an item."""
    identifiers = item.get("identifiers", {}) or {}
    doi = normalize_doi(identifiers.get("doi", ""))
    if doi:
        return f"doi:{doi}"
    arxiv_id = (identifiers.get("arxiv_id") or "").strip()
    if arxiv_id:
        return f"arxiv:{arxiv_id}"
    return f"title:{normalize_title(item.get('title', ''))}"


def title_similarity(title_a: str, title_b: str) -> float:
    """Calculate title similarity ratio."""
    return SequenceMatcher(None, normalize_title(title_a), normalize_title(title_b)).ratio()


def merge_unique_list(primary: List[str], incoming: List[str]) -> List[str]:
    """Merge two lists preserving order and uniqueness."""
    seen = set()
    merged: List[str] = []
    for name in primary + incoming:
        if name and name not in seen:
            seen.add(name)
            merged.append(name)
    return merged


def status_priority(status: str) -> int:
    """Get priority for download status."""
    return {"success": 3, "pending": 2, "failed": 1, "unavailable": 0}.get(status, 0)


def min_timestamp(value_a: object, value_b: object) -> object:
    """Return the earlier of two timestamps."""
    def parse(value: object) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc)

    if not value_a:
        return value_b
    if not value_b:
        return value_a

    return value_a if parse(value_a) <= parse(value_b) else value_b


def merge_items(existing: Dict[str, object], new: Dict[str, object]) -> Dict[str, object]:
    """Merge two items, keeping the best data from each."""
    merged = dict(existing)

    # Merge sources
    sources = existing.get("source", [])
    if isinstance(sources, str):
        sources = [sources] if sources else []
    new_source = new.get("source")
    if isinstance(new_source, list):
        for src in new_source:
            if src and src not in sources:
                sources.append(src)
    elif new_source and new_source not in sources:
        sources.append(new_source)
    merged["source"] = sources

    # Merge authors
    merged["authors"] = merge_unique_list(existing.get("authors", []), new.get("authors", []))

    # Fill missing fields
    for field in ["abstract", "summary", "date", "access_note", "report_path"]:
        if not merged.get(field) and new.get(field):
            merged[field] = new[field]

    # Take max citation count
    if new.get("citation_count") is not None:
        existing_count = merged.get("citation_count") or 0
        merged["citation_count"] = max(existing_count, new.get("citation_count") or 0)

    # Merge identifiers
    merged_ids = merged.get("identifiers", {}) or {}
    new_ids = new.get("identifiers", {}) or {}
    for key in ["doi", "arxiv_id", "openalex_id"]:
        if not merged_ids.get(key) and new_ids.get(key):
            merged_ids[key] = new_ids[key]
    merged["identifiers"] = merged_ids

    # Merge URLs
    merged_urls = merged.get("urls", {}) or {}
    new_urls = new.get("urls", {}) or {}
    for key in ["pdf", "abstract", "publisher"]:
        if not merged_urls.get(key) and new_urls.get(key):
            merged_urls[key] = new_urls[key]
    merged["urls"] = merged_urls

    # Better download status wins
    existing_status = existing.get("download_status", "pending")
    new_status = new.get("download_status", "pending")
    if status_priority(new_status) > status_priority(existing_status):
        merged["download_status"] = new_status
    else:
        merged["download_status"] = existing_status

    # Keep local path if available
    if not merged.get("local_path") and new.get("local_path"):
        merged["local_path"] = new.get("local_path")

    # Keep error message
    if merged.get("download_status") == "failed" and not merged.get("download_error"):
        merged["download_error"] = new.get("download_error")

    # Keep earliest collected_at
    merged["collected_at"] = min_timestamp(
        existing.get("collected_at"), new.get("collected_at")
    )

    return merged


def dedup(
    items: List[Dict[str, object]],
    similarity_threshold: float = 0.9,
) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    """Deduplicate items by DOI, arXiv ID, or title similarity.
    
    Returns:
        Tuple of (deduplicated items, stats dict)
    """
    seen: Dict[str, Dict[str, object]] = {}
    stats: Dict[str, object] = {"original": len(items), "duplicates": 0, "merged": []}

    for item in items:
        key = get_dedup_key(item)
        if key in seen:
            seen[key] = merge_items(seen[key], item)
            stats["duplicates"] += 1
            stats["merged"].append({
                "title": item.get("title", "")[:80],
                "merged_with": seen[key].get("title", "")[:80],
            })
            continue

        found_similar = False
        for existing_key, existing_item in seen.items():
            if title_similarity(item.get("title", ""), existing_item.get("title", "")) >= similarity_threshold:
                seen[existing_key] = merge_items(existing_item, item)
                stats["duplicates"] += 1
                stats["merged"].append({
                    "title": item.get("title", "")[:80],
                    "merged_with": existing_item.get("title", "")[:80],
                })
                found_similar = True
                break

        if not found_similar:
            seen[key] = item

    stats["final"] = len(seen)
    return list(seen.values()), stats
