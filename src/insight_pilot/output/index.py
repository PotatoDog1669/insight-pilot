"""Generate index.md and individual reports from items."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from insight_pilot.models import ItemData


def parse_date(value: str) -> Optional[datetime]:
    """Parse date string to datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def sort_by_relevance(
    items: List[Tuple[ItemData, Dict[str, Any]]]
) -> List[Tuple[ItemData, Dict[str, Any]]]:
    """Sort items by relevance score (descending), then by date."""
    def sort_key(pair: Tuple[ItemData, Dict[str, Any]]) -> Tuple[int, str]:
        item, analysis = pair
        score = analysis.get("relevance_score", 0)
        if isinstance(score, str):
            try:
                score = int(score)
            except ValueError:
                score = 0
        date = item.date or "0000-00-00"
        return (-score, date)
    
    return sorted(items, key=sort_key)


def format_authors(authors: List[str], max_count: int = 3) -> str:
    """Format author list with truncation."""
    if not authors:
        return "_Unknown_"
    if len(authors) <= max_count:
        return ", ".join(authors)
    return ", ".join(authors[:max_count]) + " et al."


def format_sources(item: ItemData) -> str:
    """Format source links."""
    links = []
    if item.arxiv_id:
        links.append(f"[arXiv](https://arxiv.org/abs/{item.arxiv_id})")
    if item.doi:
        links.append(f"[DOI](https://doi.org/{item.doi})")
    return " | ".join(links) if links else ""


def format_tags(tags: List[str], max_count: int = 5) -> str:
    """Format tags as inline code."""
    if not tags:
        return ""
    display_tags = tags[:max_count]
    return " ".join(f"`{tag}`" for tag in display_tags)


def load_analysis(analysis_dir: Path, item_id: str) -> Optional[Dict[str, Any]]:
    """Load analysis JSON for an item."""
    analysis_file = analysis_dir / f"{item_id}.json"
    if not analysis_file.exists():
        return None
    try:
        return json.loads(analysis_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return None


def generate_analyzed_index(
    analyzed_items: List[Tuple[ItemData, Dict[str, Any]]],
    failed_items: List[ItemData],
    topic: str,
    keywords: Optional[List[str]] = None,
) -> str:
    """Generate index markdown showing only analyzed papers.
    
    Args:
        analyzed_items: List of (item, analysis) tuples for analyzed papers
        failed_items: List of items that failed to download
        topic: Research topic
        keywords: Optional search keywords
        
    Returns:
        Markdown content for index
    """
    # Sort by relevance
    sorted_items = sort_by_relevance(analyzed_items)
    
    lines = [
        f"# {topic}",
        "",
        f"> **Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]
    
    if keywords:
        lines.append(f"> **Keywords**: {', '.join(keywords)}")
    
    lines.extend([
        f"> **Analyzed**: {len(analyzed_items)} papers",
        "",
        "---",
        "",
        "## 📚 Analyzed Papers",
        "",
    ])
    
    # Generate entry for each analyzed paper
    for item, analysis in sorted_items:
        # Extract analysis fields
        summary = analysis.get("summary", "_No summary_")
        brief_analysis = analysis.get("brief_analysis", "")
        tags = analysis.get("tags", [])
        relevance_score = analysis.get("relevance_score", "N/A")
        
        # Paper header with link to detailed report
        lines.append(f"### [{item.title}](reports/{item.id}.md)")
        lines.append("")
        
        # Metadata line
        meta_parts = []
        if item.authors:
            meta_parts.append(f"**Authors**: {format_authors(item.authors)}")
        if item.date:
            meta_parts.append(f"**Date**: {item.date}")
        source_links = format_sources(item)
        if source_links:
            meta_parts.append(f"**Links**: {source_links}")
        meta_parts.append(f"**Relevance**: {relevance_score}/10")
        
        lines.append(" | ".join(meta_parts))
        lines.append("")
        
        # Summary
        lines.append(f"**Summary**: {summary}")
        lines.append("")
        
        # Brief analysis (if available)
        if brief_analysis:
            lines.append(f"> {brief_analysis}")
            lines.append("")
        
        # Tags
        tag_str = format_tags(tags)
        if tag_str:
            lines.append(f"**Tags**: {tag_str}")
            lines.append("")
        
        lines.append("---")
        lines.append("")
    
    # Section for failed downloads
    if failed_items:
        lines.extend([
            "## ⚠️ Papers Not Available",
            "",
            "_The following papers could not be downloaded. Only abstracts are shown._",
            "",
        ])
        
        for item in failed_items:
            lines.append(f"### {item.title}")
            lines.append("")
            
            meta_parts = []
            if item.authors:
                meta_parts.append(f"**Authors**: {format_authors(item.authors, 5)}")
            if item.date:
                meta_parts.append(f"**Date**: {item.date}")
            source_links = format_sources(item)
            if source_links:
                meta_parts.append(f"**Links**: {source_links}")
            
            if meta_parts:
                lines.append(" | ".join(meta_parts))
                lines.append("")
            
            if item.abstract:
                # Truncate long abstracts
                abstract = item.abstract
                if len(abstract) > 400:
                    abstract = abstract[:400] + "..."
                lines.append(f"> {abstract}")
                lines.append("")
            
            lines.append("---")
            lines.append("")
    
    # Stats section
    lines.extend([
        "## 📊 Statistics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Papers Analyzed | {len(analyzed_items)} |",
        f"| Download Failed | {len(failed_items)} |",
        f"| Total Processed | {len(analyzed_items) + len(failed_items)} |",
        "",
    ])
    
    return "\n".join(lines)


def generate_index_with_reports(
    items: List[ItemData],
    topic: str,
    insight_dir: Path,
    reports_dir: Path,
    keywords: Optional[List[str]] = None,
) -> Tuple[str, List[Path]]:
    """Generate index and individual reports for all analyzed papers.
    
    Args:
        items: All items (filtered to active only)
        topic: Research topic
        insight_dir: Path to .insight directory
        reports_dir: Path to reports directory
        keywords: Optional search keywords
        
    Returns:
        Tuple of (index_content, list of generated report paths)
    """
    from insight_pilot.output.report import save_report
    
    analysis_dir = insight_dir / "analysis"
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    analyzed_items: List[Tuple[ItemData, Dict[str, Any]]] = []
    failed_items: List[ItemData] = []
    generated_reports: List[Path] = []
    
    for item in items:
        # Skip excluded items
        if item.status == "excluded":
            continue
            
        # Check if analysis exists
        analysis = load_analysis(analysis_dir, item.id)
        
        if analysis:
            analyzed_items.append((item, analysis))
            # Generate individual report
            report_path = save_report(item, analysis, topic, reports_dir)
            generated_reports.append(report_path)
        elif item.download_status == "failed":
            failed_items.append(item)
    
    # Generate index
    index_content = generate_analyzed_index(
        analyzed_items, failed_items, topic, keywords
    )
    
    return index_content, generated_reports


# Legacy function for backward compatibility
def generate_index(
    items: List[Dict[str, object]],
    topic: str,
    keywords: Optional[List[str]] = None,
    template_path: Optional[Path] = None,
) -> str:
    """Generate index markdown content (legacy format).
    
    This is kept for backward compatibility. For the new format with
    analysis integration, use generate_index_with_reports().
    """
    # Convert dicts to ItemData if needed
    item_objects = []
    for item in items:
        if isinstance(item, dict):
            item_objects.append(ItemData.from_dict(item))
        else:
            item_objects.append(item)
    
    # Use simple format without analysis
    lines = [
        f"# {topic}",
        "",
        f"> **Generated**: {datetime.now().strftime('%Y-%m-%d')}",
        f"> **Total**: {len(items)} items",
        "",
    ]
    
    if keywords:
        lines.append(f"> **Keywords**: {', '.join(keywords)}")
        lines.append("")
    
    lines.append("---")
    lines.append("")
    
    for item in item_objects:
        lines.append(f"### {item.title}")
        if item.authors:
            lines.append(f"- **Authors**: {format_authors(item.authors)}")
        if item.date:
            lines.append(f"- **Date**: {item.date}")
        lines.append(f"- **Status**: {item.download_status or 'pending'}")
        if item.abstract:
            abstract = item.abstract[:200] + "..." if len(item.abstract) > 200 else item.abstract
            lines.append(f"- **Abstract**: {abstract}")
        lines.append("")
    
    return "\n".join(lines)
