"""Data models for insight-pilot."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Return current UTC datetime as ISO string."""
    return utc_now().isoformat().replace("+00:00", "Z")


@dataclass
class ItemData:
    """Lightweight item data class for processing.
    
    This is a simpler alternative to the Pydantic Item model,
    useful for functions that don't need full validation.
    """
    id: str
    title: str
    authors: List[str] = field(default_factory=list)
    date: Optional[str] = None
    abstract: Optional[str] = None
    arxiv_id: Optional[str] = None
    doi: Optional[str] = None
    openalex_id: Optional[str] = None
    download_status: str = "pending"
    status: str = "active"
    local_path: Optional[str] = None
    source: List[str] = field(default_factory=list)
    urls: Dict[str, object] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ItemData":
        """Create from dictionary (items.json format)."""
        identifiers = data.get("identifiers", {}) or {}
        source_value = data.get("source", "")
        if isinstance(source_value, list):
            sources = [s for s in source_value if s]
        else:
            sources = [source_value] if source_value else []
        return cls(
            id=data.get("id", ""),
            title=data.get("title", "Untitled"),
            authors=data.get("authors", []),
            date=data.get("date"),
            abstract=data.get("abstract"),
            arxiv_id=identifiers.get("arxiv_id"),
            doi=identifiers.get("doi"),
            openalex_id=identifiers.get("openalex_id"),
            download_status=data.get("download_status", "pending"),
            status=data.get("status", "active"),
            local_path=data.get("local_path"),
            source=sources,
            urls=data.get("urls", {}) or {},
        )


class Identifiers(BaseModel):
    """Paper identifiers."""

    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    openalex_id: Optional[str] = None
    other: Dict[str, str] = Field(default_factory=dict)


class URLs(BaseModel):
    """Paper URLs."""

    abstract: Optional[str] = None
    pdf: Optional[str] = None
    publisher: Optional[str] = None
    other: Dict[str, str] = Field(default_factory=dict)


# Item status for agent review workflow
ItemStatus = Literal["active", "excluded", "pending_review"]


class Item(BaseModel):
    """A research item (paper, blog, etc.)."""

    id: Optional[str] = None
    type: Literal["paper", "blog", "github"] = "paper"
    title: str
    authors: List[str] = Field(default_factory=list)
    date: Optional[str] = None
    abstract: Optional[str] = None
    summary: Optional[str] = None
    identifiers: Identifiers = Field(default_factory=Identifiers)
    urls: URLs = Field(default_factory=URLs)
    local_path: Optional[str] = None
    download_status: Literal["pending", "success", "failed", "unavailable"] = "pending"
    download_error: Optional[str] = None
    access_note: Optional[str] = None
    citation_count: Optional[int] = None
    source: Union[str, List[str]] = ""
    report_path: Optional[str] = None
    collected_at: datetime = Field(default_factory=utc_now)
    # Agent review fields
    status: ItemStatus = "active"
    exclude_reason: Optional[str] = None
    reviewed_at: Optional[datetime] = None

    def dedup_key(self) -> str:
        """Generate a deduplication key."""
        doi = (self.identifiers.doi or "").strip()
        if doi:
            return f"doi:{doi.lower()}"
        arxiv_id = (self.identifiers.arxiv_id or "").strip()
        if arxiv_id:
            return f"arxiv:{arxiv_id}"
        return f"title:{self.title.lower().strip()}"


class SearchResult(BaseModel):
    """Search result from a source."""

    source: str
    query: str
    timestamp: datetime = Field(default_factory=utc_now)
    results: List[Item] = Field(default_factory=list)
    error: Optional[str] = None


class State(BaseModel):
    """Project state."""

    topic: str
    keywords: List[str] = Field(default_factory=list)
    sources_used: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    last_updated: datetime = Field(default_factory=utc_now)
    total_items: int = 0
    download_stats: Dict[str, int] = Field(default_factory=dict)


class PendingDownloadItem(BaseModel):
    """An item pending download."""

    item_id: str
    title: str
    type: str = "paper"
    url: str
    domain: str
    l1_error: Optional[str] = None


class DownloadFailedItem(BaseModel):
    """A failed download item for L2 processing."""

    id: str
    title: str
    url: str
    error: str
    domain: str
    alternative_urls: List[str] = Field(default_factory=list)
    retry_count: int = 0
    failed_at: datetime = Field(default_factory=utc_now)


class Analysis(BaseModel):
    """Paper analysis result (generated by agent)."""

    id: str
    title: str
    summary: str  # One-line summary
    contributions: List[str] = Field(default_factory=list)
    methodology: Optional[str] = None
    key_findings: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    related_to: List[str] = Field(default_factory=list)  # Related item IDs
    tags: List[str] = Field(default_factory=list)
    analyzed_at: datetime = Field(default_factory=utc_now)
    alternative_urls: List[str] = Field(default_factory=list)
    priority: str = "medium"
    retry_count: int = 0


class PendingDownload(BaseModel):
    """Pending downloads state."""

    generated_at: datetime = Field(default_factory=utc_now)
    l1_stats: Dict[str, int] = Field(default_factory=dict)
    pending_items: List[PendingDownloadItem] = Field(default_factory=list)
