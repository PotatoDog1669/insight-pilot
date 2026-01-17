"""
Insight-Pilot CLI.

Usage:
    insight-pilot <command> [options]

Commands:
    init        Initialize a research project
    search      Search papers from sources
    merge       Merge search results
    dedup       Deduplicate items
    download    Download PDFs
    index       Generate index.md
    status      Show project status
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
    """Search papers from a source."""
    ctx = ProjectContext(Path(args.project))

    if not ctx.exists():
        formatter.error(
            f"Project not found at {args.project}. Run 'init' first.",
            ErrorCode.PROJECT_NOT_FOUND.value,
        )
        return 1

    load_env_for_project(ctx.root)

    source = args.source.lower()
    output_file = ctx.insight_dir / f"raw_{source}.json"

    formatter.info(f"Searching {source} for '{args.query}'...")

    try:
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
        else:
            formatter.error(
                f"Unknown source: {source}. Available: arxiv, openalex",
                ErrorCode.INVALID_SOURCE.value,
            )
            return 1

        # Save results
        payload = {
            "source": source,
            "query": args.query,
            "timestamp": utc_now_iso(),
            "results": results,
            "error": None,
        }
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        # Update state
        state = ctx.load_state()
        if source not in state.get("sources_used", []):
            state.setdefault("sources_used", []).append(source)
            ctx.save_state(state)

        formatter.success(f"Found {len(results)} papers from {source}", {
            "source": source,
            "count": len(results),
            "output_file": str(output_file),
        })
        return 0

    except SkillError as e:
        formatter.error(e.message, e.code.value, e.retryable)
        return 1
    except Exception as e:
        formatter.error(str(e), ErrorCode.UNKNOWN.value)
        return 1


def cmd_merge(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Merge search results into items.json."""
    ctx = ProjectContext(Path(args.project))

    if not ctx.exists():
        formatter.error(f"Project not found at {args.project}", ErrorCode.PROJECT_NOT_FOUND.value)
        return 1

    raw_files = ctx.get_raw_files()
    if not raw_files:
        formatter.error(
            "No raw_*.json files found. Run 'search' first.",
            ErrorCode.NO_INPUT_FILES.value,
        )
        return 1

    formatter.info(f"Merging {len(raw_files)} result files...")

    from insight_pilot.process.merge import merge_results, save_items

    items = merge_results(raw_files)
    save_items(items, ctx.items_path)

    # Update state
    state = ctx.load_state()
    state["total_items"] = len(items)
    ctx.save_state(state)

    formatter.success(f"Merged {len(items)} items", {"count": len(items)})
    return 0


def cmd_dedup(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Deduplicate items."""
    ctx = ProjectContext(Path(args.project))

    if not ctx.items_path.exists():
        formatter.error("items.json not found. Run 'merge' first.", ErrorCode.NO_ITEMS_FILE.value)
        return 1

    from insight_pilot.process.dedup import dedup

    items = ctx.load_items()
    deduped, stats = dedup(items, args.similarity)

    if args.dry_run:
        formatter.info(f"Dry run: would deduplicate {stats['original']} → {stats['final']} items")
        if formatter.json_output:
            print(json.dumps(stats, indent=2))
        return 0

    ctx.save_items(deduped)

    # Update state
    state = ctx.load_state()
    state["total_items"] = len(deduped)
    ctx.save_state(state)

    formatter.success(
        f"Deduplicated: {stats['original']} → {stats['final']} ({stats['duplicates']} removed)",
        stats,
    )
    return 0


def cmd_download(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Download PDFs."""
    ctx = ProjectContext(Path(args.project))

    if not ctx.items_path.exists():
        formatter.error("items.json not found. Run 'merge' first.", ErrorCode.NO_ITEMS_FILE.value)
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
        formatter.info(f"Saved {len(failed_items)} failed items to download_failed.json for L2 processing")

    # Update state
    state = ctx.load_state()
    state["download_stats"] = result["l1_stats"]
    ctx.save_state(state)

    stats = result["l1_stats"]
    excluded = stats.get("excluded", 0)
    formatter.success(
        f"Downloaded: {stats['success']} success, {stats['failed']} failed, {stats['unavailable']} unavailable, {excluded} excluded",
        stats,
    )
    return 0


def cmd_index(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Generate index.md."""
    ctx = ProjectContext(Path(args.project))

    if not ctx.items_path.exists():
        formatter.error("items.json not found. Run 'merge' first.", ErrorCode.NO_ITEMS_FILE.value)
        return 1

    from insight_pilot.output.index import generate_index

    items = ctx.load_items()
    state = ctx.load_state()
    topic = state.get("topic", "Research")
    keywords = state.get("keywords", [])

    template_path = Path(args.template) if args.template else None
    content = generate_index(items, topic, keywords, template_path)

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
    p_search = subparsers.add_parser("search", help="Search papers from a source")
    p_search.add_argument("--project", required=True, help="Project directory")
    p_search.add_argument("--source", required=True, choices=["arxiv", "openalex"])
    p_search.add_argument("--query", required=True, help="Search query")
    p_search.add_argument("--limit", type=int, default=50)
    p_search.add_argument("--since", help="Start date (YYYY-MM-DD)")
    p_search.add_argument("--until", help="End date (YYYY-MM-DD)")
    p_search.add_argument("--title-only", action="store_true", help="Search title only (OpenAlex)")
    add_common_args(p_search)

    # merge
    p_merge = subparsers.add_parser("merge", help="Merge search results")
    p_merge.add_argument("--project", required=True, help="Project directory")
    add_common_args(p_merge)

    # dedup
    p_dedup = subparsers.add_parser("dedup", help="Deduplicate items")
    p_dedup.add_argument("--project", required=True, help="Project directory")
    p_dedup.add_argument("--dry-run", action="store_true")
    p_dedup.add_argument("--similarity", type=float, default=0.9)
    add_common_args(p_dedup)

    # download
    p_download = subparsers.add_parser("download", help="Download PDFs")
    p_download.add_argument("--project", required=True, help="Project directory")
    add_common_args(p_download)

    # index
    p_index = subparsers.add_parser("index", help="Generate index.md")
    p_index.add_argument("--project", required=True, help="Project directory")
    p_index.add_argument("--template", help="Custom Jinja2 template path")
    add_common_args(p_index)

    # status
    p_status = subparsers.add_parser("status", help="Show project status")
    p_status.add_argument("--project", required=True, help="Project directory")
    add_common_args(p_status)

    args = parser.parse_args()
    # Support --json in both global and subcommand positions
    json_output = getattr(args, 'json', False)
    formatter = OutputFormatter(json_output=json_output)

    commands = {
        "init": cmd_init,
        "search": cmd_search,
        "merge": cmd_merge,
        "dedup": cmd_dedup,
        "download": cmd_download,
        "index": cmd_index,
        "status": cmd_status,
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
