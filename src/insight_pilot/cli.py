"""
Insight-Pilot CLI.

Usage:
    insight-pilot <command> [options]

Commands:
    init        Initialize a research project
    search      Search, merge and deduplicate papers
    download    Download PDFs and convert to Markdown
    analyze     Analyze papers with LLM
    index       Generate index.md
    status      Show project status
    sources     Manage blog/RSS sources
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from insight_pilot.errors import ErrorCode, SkillError
from insight_pilot.models import utc_now_iso
from insight_pilot.project import ProjectContext, init_project

# Rich for better output (optional)
try:
    from rich.console import Console
    from rich.table import Table

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class OutputFormatter:
    """Handles structured output for both humans and agents."""

    def __init__(self, json_output: bool = False):
        self.json_output = json_output
        self.console = Console() if RICH_AVAILABLE and not json_output else None

    def success(self, message: str, data: Optional[Dict] = None) -> None:
        if self.json_output:
            print(json.dumps({"status": "success", "message": message, "data": data or {}}))
        elif self.console:
            self.console.print(f"[green]✓[/green] {message}")
        else:
            print(f"✓ {message}")

    def error(
        self, message: str, error_code: str = "UNKNOWN", retryable: bool = False
    ) -> None:
        if self.json_output:
            print(
                json.dumps({
                    "status": "error",
                    "message": message,
                    "error_code": error_code,
                    "retryable": retryable,
                })
            )
        elif self.console:
            self.console.print(f"[red]✗[/red] {message}")
        else:
            print(f"✗ {message}", file=sys.stderr)

    def info(self, message: str) -> None:
        if self.json_output:
            return
        elif self.console:
            self.console.print(f"[blue]ℹ[/blue] {message}")
        else:
            print(f"ℹ {message}")

    def progress(self, current: int, total: int, message: str = "") -> None:
        if self.json_output:
            print(
                json.dumps({
                    "type": "progress",
                    "current": current,
                    "total": total,
                    "message": message,
                })
            )
        elif self.console:
            self.console.print(f"  [{current}/{total}] {message}")
        else:
            print(f"  [{current}/{total}] {message}")

    def table(self, headers: List[str], rows: List[List[str]], title: str = "") -> None:
        if self.json_output:
            print(
                json.dumps({
                    "type": "table",
                    "title": title,
                    "headers": headers,
                    "rows": rows,
                })
            )
        elif self.console:
            table = Table(title=title) if title else Table()
            for header in headers:
                table.add_column(header)
            for row in rows:
                table.add_row(*row)
            self.console.print(table)
        else:
            if title:
                print(f"\n{title}")
            print(" | ".join(headers))
            print("-" * (sum(len(h) for h in headers) + 3 * (len(headers) - 1)))
            for row in rows:
                print(" | ".join(row))


def load_env_for_project(project_path: Path) -> None:
    """Load .env file from project or parent directories."""
    for parent in [project_path] + list(project_path.parents):
        env_path = parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            return
    load_dotenv()


def parse_keywords(value: Optional[str]) -> List[str]:
    """Parse comma-separated keywords."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


# ============ Commands ============


def cmd_init(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Initialize a research project."""
    output_path = Path(args.output).resolve()
    keywords = parse_keywords(args.keywords)

    ctx = init_project(args.topic, output_path, keywords)

    formatter.success(f"Initialized project at {ctx.root}", {
        "project_root": str(ctx.root),
        "config": str(ctx.config_path),
        "state": str(ctx.state_path),
    })
    return 0


def cmd_search(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Search papers from sources, merge and deduplicate.
    
    This unified command replaces the separate search/merge/dedup workflow.
    Supports multiple sources with automatic merge and deduplication.
    """
    ctx = ProjectContext(Path(args.project))

    if not ctx.exists():
        formatter.error(
            f"Project not found at {args.project}. Run 'init' first.",
            ErrorCode.PROJECT_NOT_FOUND.value,
        )
        return 1

    load_env_for_project(ctx.root)

    # Normalize sources
    sources = args.source if isinstance(args.source, list) else [args.source]
    sources = [s.lower() for s in sources]
    
    # Handle 'all' keyword
    if "all" in sources:
        sources = ["arxiv", "openalex", "github", "pubmed", "devto", "blog"]
    
    # Validate sources
    valid_sources = {"arxiv", "openalex", "github", "pubmed", "devto", "blog"}
    for source in sources:
        if source not in valid_sources:
            formatter.error(
                f"Unknown source: {source}. Available: arxiv, openalex, github, pubmed, devto, blog, all",
                ErrorCode.INVALID_SOURCE.value,
            )
            return 1

    all_results = []
    
    try:
        # Search each source
        for source in sources:
            output_file = ctx.insight_dir / f"raw_{source}.json"
            formatter.info(f"Searching {source} for '{args.query}'...")

            if source == "arxiv":
                from insight_pilot.search.arxiv import search

                # Convert dates from YYYY-MM-DD to YYYYMMDD
                submitted_from = args.since.replace("-", "") if args.since else None
                submitted_to = args.until.replace("-", "") if args.until else None

                results = search(
                    query=args.query,
                    limit=args.limit,
                    submitted_from=submitted_from,
                    submitted_to=submitted_to,
                    max_retries=3,
                )
            elif source == "openalex":
                from insight_pilot.search.openalex import search

                mailto = os.getenv("OPENALEX_MAILTO", "")
                results = search(
                    query=args.query,
                    limit=args.limit,
                    since=args.since,
                    until=args.until,
                    mailto=mailto,
                    title_only=getattr(args, "title_only", False),
                    max_retries=3,
                )
            elif source == "github":
                from insight_pilot.search.github import search

                token = os.getenv("GITHUB_TOKEN")
                raw_types = args.github_types or "repositories,code,issues,discussions"
                types = [t.strip() for t in raw_types.split(",") if t.strip()]

                results = search(
                    query=args.query,
                    limit=args.limit,
                    types=types,
                    token=token,
                    max_retries=3,
                )
            elif source == "pubmed":
                from insight_pilot.search.pubmed import search

                email = args.pubmed_email or os.getenv("PUBMED_EMAIL", "")
                results = search(
                    query=args.query,
                    limit=args.limit,
                    email=email,
                    include_abstract=not args.pubmed_no_abstract,
                    max_retries=3,
                )
            elif source == "devto":
                from insight_pilot.search.devto import search

                results = search(
                    query=args.query,
                    limit=args.limit,
                    tag=args.devto_tag,
                    username=args.devto_username,
                    organization_id=args.devto_org,
                    max_retries=3,
                )
            elif source == "blog":
                from insight_pilot.search.blog import search
                from insight_pilot.sources import list_sources, resolve_sources_path

                sources_path = resolve_sources_path(ctx.root, args.sources_config)
                blog_sources = list_sources(sources_path)
                results = search(
                    sources=blog_sources,
                    query=args.query,
                    limit=args.limit,
                    max_retries=3,
                    name_filter=args.blog_name,
                    category_filter=args.blog_category,
                )

            # Save raw results
            payload = {
                "source": source,
                "query": args.query,
                "timestamp": utc_now_iso(),
                "results": results,
                "error": None,
            }
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)

            formatter.info(f"Found {len(results)} papers from {source}")
            all_results.extend(results)

            # Update state with source
            state = ctx.load_state()
            if source not in state.get("sources_used", []):
                state.setdefault("sources_used", []).append(source)
                ctx.save_state(state)

        # Merge results
        from insight_pilot.process.merge import merge_results, save_items

        raw_files = ctx.get_raw_files()
        if raw_files:
            formatter.info(f"Merging {len(raw_files)} result files...")
            items = merge_results(raw_files)
            save_items(items, ctx.items_path)

            # Update state
            state = ctx.load_state()
            state["total_items"] = len(items)
            ctx.save_state(state)

            # Deduplicate
            from insight_pilot.process.dedup import dedup

            deduped, stats = dedup(items, 0.9)  # Similarity threshold hardcoded
            ctx.save_items(deduped)

            # Update state
            state = ctx.load_state()
            state["total_items"] = len(deduped)
            ctx.save_state(state)

            formatter.success(
                f"Search complete: {len(all_results)} found → {len(items)} merged → {len(deduped)} after dedup",
                {
                    "sources": sources,
                    "raw_count": len(all_results),
                    "merged_count": len(items),
                    "final_count": len(deduped),
                    "duplicates_removed": stats["duplicates"],
                },
            )
        else:
            formatter.success(f"Search complete: {len(all_results)} papers found", {
                "sources": sources,
                "count": len(all_results),
            })

        return 0

    except SkillError as e:
        formatter.error(e.message, e.code.value, e.retryable)
        return 1
    except Exception as e:
        formatter.error(str(e), ErrorCode.UNKNOWN.value)
        return 1


def cmd_sources(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Manage sources.yaml configuration."""
    ctx = ProjectContext(Path(args.project)) if args.project else None
    from insight_pilot.sources import (
        SUPPORTED_BLOG_TYPES,
        add_source,
        list_sources,
        remove_source,
        resolve_sources_path,
        save_sources_config,
    )

    sources_path = resolve_sources_path(ctx.root if ctx else None, args.config)

    if args.add:
        if not args.name or not args.type or not args.url:
            formatter.error("Adding a source requires --name, --type, --url", ErrorCode.MISSING_REQUIRED_ARG.value)
            return 1
        source_type = args.type.lower()
        if source_type not in SUPPORTED_BLOG_TYPES:
            formatter.error(
                f"Unsupported source type: {args.type}. Use: {', '.join(sorted(SUPPORTED_BLOG_TYPES))}",
                ErrorCode.INVALID_INPUT_FORMAT.value,
            )
            return 1
        entry = {
            "name": args.name,
            "type": source_type,
            "url": args.url,
            "category": args.category,
            "api_key": args.api_key,
        }
        add_source(sources_path, entry)
        formatter.success(f"Added source '{args.name}'", {"config": str(sources_path)})
        return 0

    if args.remove:
        if not args.name:
            formatter.error("Removing a source requires --name", ErrorCode.MISSING_REQUIRED_ARG.value)
            return 1
        removed = remove_source(sources_path, args.name)
        if removed:
            formatter.success(f"Removed source '{args.name}'", {"config": str(sources_path)})
            return 0
        formatter.error(f"Source '{args.name}' not found", ErrorCode.INVALID_INPUT_FORMAT.value)
        return 1

    if args.init:
        save_sources_config(sources_path, {"blogs": []})
        formatter.success(f"Initialized sources config at {sources_path}")
        return 0

    sources = list_sources(sources_path)
    if not sources:
        formatter.info(f"No sources configured at {sources_path}")
        return 0

    def status_for(source: Dict[str, object]) -> str:
        blog_type = (source.get("type") or "").lower()
        if blog_type not in SUPPORTED_BLOG_TYPES:
            return "invalid"
        if blog_type == "ghost":
            api_key = source.get("api_key")
            if api_key == "auto":
                return "auto"
            if api_key:
                return "ready"
            return "missing_api_key"
        return "ready"

    rows = []
    for source in sources:
        rows.append([
            str(source.get("name") or ""),
            str(source.get("type") or ""),
            str(source.get("url") or ""),
            str(source.get("category") or ""),
            status_for(source),
        ])

    formatter.table(
        ["Name", "Type", "URL", "Category", "Status"],
        rows,
        title=f"Sources ({len(rows)})",
    )
    return 0



def cmd_download(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Download PDFs and convert to Markdown.
    
    This unified command downloads PDFs and automatically converts them
    to Markdown format using pymupdf4llm.
    """
    ctx = ProjectContext(Path(args.project))

    if not ctx.items_path.exists():
        formatter.error("items.json not found. Run 'search' first.", ErrorCode.NO_ITEMS_FILE.value)
        return 1

    from insight_pilot.download.direct import download_pdfs

    items = ctx.load_items()
    active_count = sum(1 for it in items if it.get("status") != "excluded")
    formatter.info(f"Downloading PDFs for {active_count} items ({len(items) - active_count} excluded)...")

    result = download_pdfs(items, ctx.papers_dir)
    ctx.save_items(items)

    # Save failed downloads for L2 processing
    pending_items = result.get("pending_items", [])
    if pending_items:
        failed_items = [
            {
                "id": p.get("item_id", ""),
                "title": p.get("title", ""),
                "url": p.get("url", ""),
                "error": p.get("l1_error", ""),
                "domain": p.get("domain", ""),
                "alternative_urls": p.get("alternative_urls", []),
                "retry_count": 0,
                "failed_at": result.get("generated_at", ""),
            }
            for p in pending_items
        ]
        ctx.save_download_failed(failed_items)
        formatter.info(f"Saved {len(failed_items)} failed items to download_failed.json")

    # Update state
    state = ctx.load_state()
    state["download_stats"] = result["l1_stats"]
    ctx.save_state(state)

    dl_stats = result["l1_stats"]
    excluded = dl_stats.get("excluded", 0)
    formatter.info(
        f"Downloaded: {dl_stats['success']} success, {dl_stats['failed']} failed, {dl_stats['unavailable']} unavailable, {excluded} excluded"
    )

    # Convert PDFs to Markdown
    from insight_pilot.convert import convert_papers

    downloaded_count = sum(1 for it in items if it.get("download_status") == "success")
    if downloaded_count > 0:
        formatter.info(f"Converting {downloaded_count} PDFs to Markdown...")

        convert_result = convert_papers(
            items,
            ctx.root,
            ctx.markdown_dir,
            skip_existing=True,
        )

        if convert_result.get("status") == "failed":
            formatter.error(convert_result.get("message", "Conversion failed"), ErrorCode.CONVERSION_FAILED.value)
            return 1

        conv_stats = convert_result.get("stats", {})
        formatter.success(
            f"Complete: {dl_stats['success']} downloaded, {conv_stats.get('success', 0)} converted to Markdown",
            {
                "download": dl_stats,
                "convert": conv_stats,
            },
        )
    else:
        formatter.success(
            f"Download complete: {dl_stats['success']} success, {dl_stats['failed']} failed",
            dl_stats,
        )

    return 0


def cmd_index(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Generate index.md and individual reports."""
    ctx = ProjectContext(Path(args.project))

    if not ctx.items_path.exists():
        formatter.error("items.json not found. Run 'merge' first.", ErrorCode.NO_ITEMS_FILE.value)
        return 1

    from insight_pilot.output.index import generate_index, generate_index_with_reports
    from insight_pilot.models import ItemData

    items_data = ctx.load_items()
    state = ctx.load_state()
    topic = state.get("topic", "Research")
    keywords = state.get("keywords", [])

    # Convert to ItemData objects
    items = [ItemData.from_dict(item) for item in items_data]
    
    # Filter to active items only
    active_items = [item for item in items if item.status != "excluded"]

    # Check if we should use the new analysis-based format
    analysis_dir = ctx.insight_dir / "analysis"
    has_analyses = analysis_dir.exists() and any(analysis_dir.glob("*.json"))
    
    if has_analyses and not args.legacy:
        # Use new format with analysis integration
        reports_dir = ctx.root / "reports"
        content, report_paths = generate_index_with_reports(
            active_items, topic, ctx.insight_dir, reports_dir, keywords
        )
        
        with open(ctx.index_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        formatter.success(
            f"Generated index at {ctx.index_path}",
            {
                "index_path": str(ctx.index_path),
                "reports_generated": len(report_paths),
                "reports_dir": str(reports_dir),
            }
        )
    else:
        # Use legacy format (no analysis)
        # Filter to active items only for legacy format too
        active_items_data = [item for item in items_data if item.get("status") != "excluded"]
        template_path = Path(args.template) if args.template else None
        content = generate_index(active_items_data, topic, keywords, template_path)

        with open(ctx.index_path, "w", encoding="utf-8") as f:
            f.write(content)

        formatter.success(f"Generated index at {ctx.index_path}")
    
    return 0


def cmd_status(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Show project status."""
    ctx = ProjectContext(Path(args.project))

    if not ctx.exists():
        formatter.error(f"Project not found at {args.project}", ErrorCode.PROJECT_NOT_FOUND.value)
        return 1

    state = ctx.load_state()
    items = ctx.load_items()
    raw_files = ctx.get_raw_files()
    failed_downloads = ctx.load_download_failed()
    analyzed_ids = ctx.list_analyses()

    # Count by download_status
    by_download_status: Dict[str, int] = {}
    for item in items:
        status = item.get("download_status", "pending")
        by_download_status[status] = by_download_status.get(status, 0) + 1

    # Count by item status (active/excluded/pending_review)
    by_item_status: Dict[str, int] = {"active": 0, "excluded": 0, "pending_review": 0}
    for item in items:
        status = item.get("status", "active")
        by_item_status[status] = by_item_status.get(status, 0) + 1

    if formatter.json_output:
        print(
            json.dumps({
                "status": "success",
                "project": {
                    "root": str(ctx.root),
                    "topic": state.get("topic", "Unknown"),
                    "keywords": state.get("keywords", []),
                    "created_at": state.get("created_at"),
                    "last_updated": state.get("last_updated"),
                },
                "sources_used": state.get("sources_used", []),
                "raw_files": [str(f) for f in raw_files],
                "items": {
                    "total": len(items),
                    "by_download_status": by_download_status,
                    "by_item_status": by_item_status,
                },
                "download_failed": len(failed_downloads),
                "analyzed": len(analyzed_ids),
            })
        )
    else:
        formatter.info(f"Project: {ctx.root}")
        formatter.info(f"Topic: {state.get('topic', 'Unknown')}")
        formatter.info(f"Keywords: {', '.join(state.get('keywords', []))}")
        formatter.info(f"Sources used: {', '.join(state.get('sources_used', []))}")
        formatter.table(
            ["Item Status", "Count"],
            [[status, str(count)] for status, count in sorted(by_item_status.items())],
            title=f"Items ({len(items)} total)",
        )
        formatter.table(
            ["Download Status", "Count"],
            [[status, str(count)] for status, count in sorted(by_download_status.items())],
            title="Download Status",
        )
        formatter.info(f"Download failed (for L2): {len(failed_downloads)}")
        formatter.info(f"Analyzed: {len(analyzed_ids)}")

    return 0


def cmd_analyze(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Analyze papers with LLM."""
    ctx = ProjectContext(Path(args.project))

    if not ctx.exists():
        formatter.error(f"Project not found at {args.project}", ErrorCode.PROJECT_NOT_FOUND.value)
        return 1

    if not ctx.items_path.exists():
        formatter.error("items.json not found. Run 'merge' first.", ErrorCode.NO_ITEMS_FILE.value)
        return 1

    from insight_pilot.analyze import analyze_papers, load_llm_config

    # Load LLM config
    config_path = Path(args.config) if args.config else None
    config = load_llm_config(config_path)

    if not config:
        formatter.info("LLM not configured. Agent should analyze papers manually.")
        formatter.info("To configure LLM, create llm.yaml in .codex/skills/insight-pilot/")
        if formatter.json_output:
            print(json.dumps({
                "status": "skipped",
                "reason": "no_llm_config",
                "message": "LLM not configured. Agent should analyze papers manually.",
                "config_example_path": ".codex/skills/insight-pilot/llm.yaml.example",
            }))
        return 0

    items = ctx.load_items()
    active_items = [it for it in items if it.get("status") != "excluded"]
    formatter.info(f"Analyzing {len(active_items)} papers with {config.get('provider')}/{config.get('model')}...")

    result = analyze_papers(
        items,
        ctx.papers_dir,
        ctx.analysis_dir,
        config=config,
        skip_existing=not args.force,
        markdown_dir=ctx.markdown_dir,
    )

    if result.get("status") == "skipped":
        formatter.info(result.get("message", "Analysis skipped"))
        if formatter.json_output:
            print(json.dumps(result))
        return 0

    stats = result.get("stats", {})
    not_downloaded = stats.get('not_downloaded', 0)
    if not_downloaded > 0:
        formatter.info(f"Skipped {not_downloaded} papers without PDF. Run 'download' first.")
    no_content = stats.get("no_content", 0)
    if no_content > 0:
        formatter.info(f"Skipped {no_content} non-paper items without content.")
    formatter.success(
        f"Analysis complete: {stats.get('success', 0)} success, {stats.get('failed', 0)} failed, {stats.get('skipped', 0)} already analyzed",
        result,
    )
    return 0



def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Insight-Pilot: Literature research automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="Output in JSON format (for agents)")
    parser.add_argument("--version", action="version", version="%(prog)s 0.3.0")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Helper to add common args to all subparsers
    def add_common_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--json", action="store_true", help="Output in JSON format")

    # init
    p_init = subparsers.add_parser("init", help="Initialize a research project")
    p_init.add_argument("--topic", required=True, help="Research topic")
    p_init.add_argument("--keywords", help="Comma-separated keywords")
    p_init.add_argument("--output", required=True, help="Project directory")
    add_common_args(p_init)

    # search
    p_search = subparsers.add_parser("search", help="Search, merge and deduplicate papers")
    p_search.add_argument("--project", required=True, help="Project directory")
    p_search.add_argument(
        "--source",
        required=True,
        nargs="+",
        help="Source(s): arxiv, openalex, github, pubmed, devto, blog, or 'all'",
    )
    p_search.add_argument("--query", required=True, help="Search query")
    p_search.add_argument("--limit", type=int, default=50, help="Max results per source")
    p_search.add_argument("--since", help="Start date (YYYY-MM-DD)")
    p_search.add_argument("--until", help="End date (YYYY-MM-DD)")
    p_search.add_argument("--title-only", action="store_true", help="Search title only (OpenAlex)")
    p_search.add_argument("--github-types", help="GitHub search types (comma-separated)")
    p_search.add_argument("--pubmed-email", help="PubMed email (overrides PUBMED_EMAIL)")
    p_search.add_argument("--pubmed-no-abstract", action="store_true", help="Skip PubMed abstract fetch")
    p_search.add_argument("--devto-tag", help="Dev.to tag filter")
    p_search.add_argument("--devto-username", help="Dev.to username filter")
    p_search.add_argument("--devto-org", type=int, help="Dev.to organization ID")
    p_search.add_argument("--sources-config", help="Path to sources.yaml")
    p_search.add_argument("--blog-name", help="Filter blog sources by name")
    p_search.add_argument("--blog-category", help="Filter blog sources by category")
    add_common_args(p_search)


    # download
    p_download = subparsers.add_parser("download", help="Download PDFs and convert to Markdown")
    p_download.add_argument("--project", required=True, help="Project directory")
    add_common_args(p_download)
    # index
    p_index = subparsers.add_parser("index", help="Generate index.md and reports")
    p_index.add_argument("--project", required=True, help="Project directory")
    p_index.add_argument("--template", help="Custom Jinja2 template path (legacy mode only)")
    p_index.add_argument("--legacy", action="store_true", help="Use legacy format (no analysis integration)")
    add_common_args(p_index)

    # status
    p_status = subparsers.add_parser("status", help="Show project status")
    p_status.add_argument("--project", required=True, help="Project directory")
    add_common_args(p_status)

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="Analyze papers with LLM")
    p_analyze.add_argument("--project", required=True, help="Project directory")
    p_analyze.add_argument("--config", help="Path to LLM config file (llm.yaml)")
    p_analyze.add_argument("--force", action="store_true", help="Re-analyze even if already done")
    add_common_args(p_analyze)

    # sources
    p_sources = subparsers.add_parser("sources", help="Manage blog/RSS sources")
    p_sources.add_argument("--project", help="Project directory")
    p_sources.add_argument("--config", help="Path to sources.yaml")
    p_sources.add_argument("--init", action="store_true", help="Initialize an empty sources.yaml")
    p_sources.add_argument("--add", action="store_true", help="Add a source")
    p_sources.add_argument("--remove", action="store_true", help="Remove a source by name")
    p_sources.add_argument("--name", help="Source name")
    p_sources.add_argument("--type", help="Source type: ghost, wordpress, rss, auto")
    p_sources.add_argument("--url", help="Source URL")
    p_sources.add_argument("--category", help="Source category")
    p_sources.add_argument("--api-key", help="API key (for Ghost)")
    add_common_args(p_sources)

    args = parser.parse_args()
    # Support --json in both global and subcommand positions
    json_output = getattr(args, 'json', False)
    formatter = OutputFormatter(json_output=json_output)

    commands = {
        "init": cmd_init,
        "search": cmd_search,
        "download": cmd_download,
        "analyze": cmd_analyze,
        "index": cmd_index,
        "status": cmd_status,
        "sources": cmd_sources,
    }

    try:
        return commands[args.command](args, formatter)
    except KeyboardInterrupt:
        formatter.error("Interrupted", "INTERRUPTED")
        return 130
    except Exception as e:
        formatter.error(str(e), ErrorCode.UNKNOWN.value)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
