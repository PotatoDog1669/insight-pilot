"""Generate index.md from items."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError as exc:
    raise SystemExit(
        "Missing dependency 'Jinja2'. Install with: pip install insight-pilot"
    ) from exc


def parse_date(value: str) -> Optional[datetime]:
    """Parse date string to datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def group_by_date(items: List[Dict[str, object]]) -> Dict[str, List[Dict[str, object]]]:
    """Group items by publication date."""
    grouped: Dict[str, List[Dict[str, object]]] = {}
    for item in items:
        date = item.get("date") or "Unknown"
        grouped.setdefault(date, []).append(item)
    return grouped


def sort_dates(dates: List[str]) -> List[str]:
    """Sort dates in descending order."""
    known: List[Tuple[str, datetime]] = []
    unknown: List[str] = []
    for date in dates:
        parsed = parse_date(date)
        if parsed:
            known.append((date, parsed))
        else:
            unknown.append(date)
    known.sort(key=lambda x: x[1], reverse=True)
    return [date for date, _ in known] + sorted(unknown)


def short_text(text: Optional[str], limit: int = 240) -> Optional[str]:
    """Truncate text to limit."""
    if not text:
        return None
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def format_sources(item: Dict[str, object]) -> str:
    """Format source identifiers for display."""
    identifiers = item.get("identifiers", {}) or {}
    urls = item.get("urls", {}) or {}

    arxiv_id = identifiers.get("arxiv_id")
    if arxiv_id:
        url = urls.get("abstract") or f"https://arxiv.org/abs/{arxiv_id}"
        return f"[arXiv:{arxiv_id}]({url})"

    doi = identifiers.get("doi")
    if doi:
        url = f"https://doi.org/{doi}"
        return f"[DOI:{doi}]({url})"

    source = item.get("source", "")
    if isinstance(source, list):
        return ", ".join(source) if source else "Unknown"
    return source or "Unknown"


def format_authors(item: Dict[str, object]) -> Optional[str]:
    """Format authors for display."""
    authors = item.get("authors", []) or []
    if not authors:
        return None
    display = ", ".join(authors[:3])
    if len(authors) > 3:
        display += " et al."
    return display


def status_label(status: str) -> Tuple[str, str]:
    """Get status emoji and label."""
    mapping = {
        "success": ("✅", "downloaded"),
        "pending": ("⏳", "pending"),
        "failed": ("❌", "failed"),
        "unavailable": ("⚠️", "unavailable"),
    }
    return mapping.get(status, ("⏳", "pending"))


def build_sections(items: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Build sections for template rendering."""
    grouped = group_by_date(items)
    sections: List[Dict[str, object]] = []

    for date in sort_dates(list(grouped.keys())):
        group_items = grouped[date]
        group_items.sort(
            key=lambda item: (-(item.get("citation_count") or 0), item.get("title", ""))
        )
        formatted_items = []
        for item in group_items:
            status = item.get("download_status", "pending")
            marker, status_text = status_label(status)
            urls = item.get("urls", {}) or {}
            pdf_url = urls.get("pdf")
            local_path = item.get("local_path")

            pdf_line = None
            if status == "success" and (local_path or pdf_url):
                local_display = f"[Local]({local_path})" if local_path else ""
                online_display = f"[Online]({pdf_url})" if pdf_url else ""
                if local_display and online_display:
                    pdf_line = f"- **PDF**: {local_display} | {online_display}"
                elif local_display:
                    pdf_line = f"- **PDF**: {local_display}"
                elif online_display:
                    pdf_line = f"- **PDF**: {online_display}"
            elif status != "success":
                online = urls.get("abstract") or urls.get("publisher")
                if online:
                    pdf_line = f"- **Online**: [Link]({online})"

            formatted_items.append({
                "type_label": str(item.get("type", "paper")).title(),
                "type_emoji": {
                    "paper": "📄",
                    "blog": "📝",
                    "github": "💻",
                }.get(item.get("type", "paper"), "📄"),
                "title": item.get("title", "Untitled"),
                "source_display": format_sources(item),
                "authors_display": format_authors(item),
                "date": item.get("date"),
                "citation_count": item.get("citation_count"),
                "status_marker": marker,
                "status_text": status_text,
                "pdf_line": pdf_line,
                "abstract_short": short_text(item.get("abstract")),
            })

        sections.append({"date": date, "items": formatted_items})

    return sections


def build_stats(items: List[Dict[str, object]]) -> Dict[str, object]:
    """Build stats summary."""
    total = len(items)
    downloaded = sum(1 for item in items if item.get("download_status") == "success")
    unavailable = sum(1 for item in items if item.get("download_status") == "unavailable")

    def pct(value: int) -> str:
        if total == 0:
            return "0.0%"
        return f"{value / total * 100:.1f}%"

    return {
        "total": total,
        "downloaded": downloaded,
        "unavailable": unavailable,
        "downloaded_pct": pct(downloaded),
        "unavailable_pct": pct(unavailable),
    }


# Default template content
DEFAULT_TEMPLATE = '''# {{ topic }} Research Index

{% if keywords %}> **Keywords**: {{ keywords | join(", ") }}  
{% endif %}> **Generated**: {{ generated_at }}  
> **Total**: {{ stats.total }} items ({{ stats.downloaded }} downloaded, {{ stats.unavailable }} metadata only)

---

{% for section in sections %}## {{ section.date }} ({{ section["items"] | length }} items)

{% for item in section["items"] %}### {{ item.type_emoji }} [{{ item.type_label }}] {{ item.title }}
- **Source**: {{ item.source_display }}
{% if item.authors_display %}- **Authors**: {{ item.authors_display }}
{% endif %}{% if item.date %}- **Date**: {{ item.date }}
{% endif %}{% if item.citation_count is not none %}- **Citations**: {{ item.citation_count }}
{% endif %}- **Status**: {{ item.status_marker }} {{ item.status_text }}
{% if item.pdf_line %}{{ item.pdf_line }}
{% endif %}{% if item.abstract_short %}- **Abstract**: {{ item.abstract_short }}
{% endif %}

{% endfor %}{% endfor %}---

## Stats

| Category | Count | Percent |
| --- | --- | --- |
| Downloaded | {{ stats.downloaded }} | {{ stats.downloaded_pct }} |
| Unavailable | {{ stats.unavailable }} | {{ stats.unavailable_pct }} |
'''


def generate_index(
    items: List[Dict[str, object]],
    topic: str,
    keywords: Optional[List[str]] = None,
    template_path: Optional[Path] = None,
) -> str:
    """Generate index markdown content.
    
    Args:
        items: List of items
        topic: Research topic
        keywords: Optional list of keywords
        template_path: Optional custom template path
        
    Returns:
        Rendered markdown string
    """
    if template_path and template_path.exists():
        env = Environment(
            loader=FileSystemLoader(str(template_path.parent)),
            autoescape=select_autoescape(),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        template = env.get_template(template_path.name)
    else:
        from jinja2 import Template
        template = Template(DEFAULT_TEMPLATE)
        template.environment.trim_blocks = True
        template.environment.lstrip_blocks = True

    rendered = template.render(
        topic=topic,
        keywords=keywords or [],
        generated_at=datetime.now().strftime("%Y-%m-%d"),
        stats=build_stats(items),
        sections=build_sections(items),
    )

    return rendered.rstrip() + "\n"
