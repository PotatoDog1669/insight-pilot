"""Individual paper report generation module."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from insight_pilot.models import ItemData, utc_now_iso


def format_list(items: List[str], numbered: bool = False) -> str:
    """Format a list as markdown bullet points or numbered list."""
    if not items:
        return "_Not available_"
    if numbered:
        return "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))
    return "\n".join(f"- {item}" for item in items)


def format_authors(authors: List[str], max_count: int = 10) -> str:
    """Format author list with truncation."""
    if not authors:
        return "_Unknown_"
    if len(authors) <= max_count:
        return ", ".join(authors)
    return ", ".join(authors[:max_count]) + f" et al. (+{len(authors) - max_count})"


def format_sources(item: ItemData, placeholder: bool = True) -> str:
    """Format source links."""
    links = []
    seen_urls = set()
    if item.arxiv_id:
        url = f"https://arxiv.org/abs/{item.arxiv_id}"
        links.append(f"[arXiv:{item.arxiv_id}]({url})")
        seen_urls.add(url)
    if item.doi:
        url = f"https://doi.org/{item.doi}"
        if url not in seen_urls:
            links.append(f"[DOI:{item.doi}]({url})")
            seen_urls.add(url)
    if item.openalex_id:
        url = f"https://openalex.org/works/{item.openalex_id}"
        if url not in seen_urls:
            links.append(f"[OpenAlex:{item.openalex_id}]({url})")
            seen_urls.add(url)

    urls = item.urls if isinstance(item.urls, dict) else {}
    abstract_url = urls.get("abstract")
    publisher_url = urls.get("publisher")
    pdf_url = urls.get("pdf")

    if abstract_url and abstract_url not in seen_urls:
        links.append(f"[Source]({abstract_url})")
        seen_urls.add(abstract_url)
    elif publisher_url and publisher_url not in seen_urls:
        links.append(f"[Publisher]({publisher_url})")
        seen_urls.add(publisher_url)
    if pdf_url and pdf_url not in seen_urls:
        links.append(f"[PDF]({pdf_url})")
        seen_urls.add(pdf_url)

    if links:
        return " | ".join(links)
    return "_No external links_" if placeholder else ""


def generate_report(item: ItemData, analysis: Dict[str, Any], topic: str) -> str:
    """Generate a detailed markdown report for a single paper.
    
    Args:
        item: The paper item data
        analysis: The analysis results from LLM
        topic: The research topic
        
    Returns:
        Markdown content for the report
    """
    # Extract analysis fields with defaults
    summary = analysis.get("summary", "_No summary available_")
    brief_analysis = analysis.get("brief_analysis", "_No analysis available_")
    detailed_analysis = analysis.get("detailed_analysis", "_No detailed analysis available_")
    contributions = analysis.get("contributions", [])
    methodology = analysis.get("methodology", "_Not specified_")
    key_findings = analysis.get("key_findings", [])
    limitations = analysis.get("limitations", [])
    future_work = analysis.get("future_work", [])
    tags = analysis.get("tags", [])
    relevance_score = analysis.get("relevance_score", "N/A")
    
    sources_str = format_sources(item)
    
    # Format date
    date_str = item.date or "_Unknown date_"
    
    # Build report content
    report = f"""# {item.title}

> **Research Topic**: {topic}

## 📋 Metadata

| Field | Value |
|-------|-------|
| **Authors** | {format_authors(item.authors)} |
| **Date** | {date_str} |
| **Sources** | {sources_str} |
| **Relevance Score** | {relevance_score}/10 |

## 📝 Summary

{summary}

## 🔍 Brief Analysis

{brief_analysis}

## 📖 Detailed Analysis

{detailed_analysis}

## 🎯 Main Contributions

{format_list(contributions)}

## 🔬 Methodology

{methodology}

## 📊 Key Findings

{format_list(key_findings)}

## ⚠️ Limitations

{format_list(limitations)}

## 🔮 Future Work

{format_list(future_work)}

## 🏷️ Tags

{', '.join(f'`{tag}`' for tag in tags) if tags else '_No tags_'}

## 📄 Abstract

{item.abstract or '_No abstract available_'}

---

_Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M')} | [Back to Index](../index.md)_
"""
    return report


def generate_failed_section(items: List[ItemData]) -> str:
    """Generate a section for papers that failed to download.
    
    Args:
        items: List of items that failed to download
        
    Returns:
        Markdown content for the failed section
    """
    if not items:
        return ""
    
    lines = [
        "## ⚠️ Papers Not Downloaded",
        "",
        "The following papers could not be downloaded or processed. Only abstracts are available.",
        "",
    ]
    
    for item in items:
        # Format sources
        sources_str = format_sources(item, placeholder=False)
        
        lines.append(f"### {item.title}")
        lines.append("")
        if item.authors:
            lines.append(f"**Authors**: {format_authors(item.authors, 5)}")
        if item.date:
            lines.append(f"**Date**: {item.date}")
        if sources_str:
            lines.append(f"**Links**: {sources_str}")
        lines.append("")
        if item.abstract:
            # Truncate long abstracts
            abstract = item.abstract
            if len(abstract) > 500:
                abstract = abstract[:500] + "..."
            lines.append(f"> {abstract}")
        else:
            lines.append("> _No abstract available_")
        lines.append("")
    
    return "\n".join(lines)


def save_report(
    item: ItemData,
    analysis: Dict[str, Any],
    topic: str,
    reports_dir: Path
) -> Path:
    """Save a paper report to the reports directory.
    
    Args:
        item: The paper item data
        analysis: The analysis results
        topic: Research topic
        reports_dir: Directory to save reports
        
    Returns:
        Path to the saved report
    """
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{item.id}.md"
    content = generate_report(item, analysis, topic)
    report_path.write_text(content, encoding="utf-8")
    return report_path
