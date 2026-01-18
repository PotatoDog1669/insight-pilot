"""L1 (direct) PDF download module."""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn

from insight_pilot.models import utc_now_iso


def safe_filename(text: str) -> str:
    """Create safe filename from text."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    return slug[:80] or "paper"


def build_filename(item: Dict[str, object], used: set[str]) -> str:
    """Build unique filename for item."""
    base = item.get("id") or ""
    if not base:
        title = safe_filename(str(item.get("title", "paper")))
        date = str(item.get("date") or "")[:4]
        base = f"{title}_{date}" if date else title

    candidate = f"{base}.pdf"
    counter = 1
    while candidate in used:
        candidate = f"{base}_{counter}.pdf"
        counter += 1
    used.add(candidate)
    return candidate


def is_pdf(path: Path) -> bool:
    """Check if file is a valid PDF."""
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"%PDF"
    except OSError:
        return False


def download_with_retry(url: str, path: Path, max_retries: int, progress: Optional[Progress] = None, task_id: Optional[object] = None) -> Optional[str]:
    """Download file with retry logic. Returns error message or None on success."""
    delay = 1.0
    headers = {"User-Agent": "Insight-Pilot/0.2"}

    for attempt in range(max_retries):
        try:
            response = requests.get(url, stream=True, timeout=90, headers=headers)
            if response.status_code != 200:
                raise requests.HTTPError(f"HTTP {response.status_code}")

            total_size = int(response.headers.get('content-length', 0))
            if progress and task_id and total_size:
                progress.update(task_id, total=total_size)

            downloaded = 0
            with open(path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress and task_id:
                            progress.update(task_id, completed=downloaded)

            if not is_pdf(path):
                raise ValueError("Downloaded file is not a PDF")

            return None
        except Exception as exc:  # noqa: BLE001
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
            if attempt == max_retries - 1:
                return str(exc)
            time.sleep(delay)
            delay *= 2

    return "Download failed"


def make_local_path(output_dir: Path, filename: str) -> str:
    """Create local path string."""
    path = output_dir / filename
    if output_dir.is_absolute():
        return str(path)
    rel = str(path)
    if not rel.startswith("."):
        rel = f"./{rel}"
    return rel


def build_pending_item(item: Dict[str, object], url: str, error: str) -> Dict[str, object]:
    """Build pending download item entry."""
    parsed = urlparse(url)
    urls = item.get("urls", {}) or {}
    alternatives = [u for u in [urls.get("abstract"), urls.get("publisher")] if u]

    return {
        "item_id": item.get("id", ""),
        "title": item.get("title", ""),
        "type": item.get("type", "paper"),
        "url": url,
        "domain": parsed.netloc,
        "l1_error": error,
        "alternative_urls": alternatives,
        "priority": "medium",
        "retry_count": 0,
    }


def download_pdfs(
    items: List[Dict[str, object]],
    output_dir: Path,
    max_retries: int = 3,
) -> Dict[str, object]:
    """Download PDFs for items.
    
    Args:
        items: List of items to download (modified in place)
        output_dir: Directory to save PDFs
        max_retries: Maximum retry attempts
        
    Returns:
        Dict with stats and pending items
        
    Note:
        Items with status="excluded" are skipped.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    used_names: set[str] = set()
    stats = {"total": len(items), "success": 0, "failed": 0, "unavailable": 0, "skipped": 0, "excluded": 0}
    pending_items: List[Dict[str, object]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        DownloadColumn(),
        TransferSpeedColumn(),
    ) as progress:
        overall_task = progress.add_task(f"[cyan]下载论文 PDF", total=len(items))
        
        for idx, item in enumerate(items, 1):
            # Skip excluded items (filtered out by agent review)
            if item.get("status") == "excluded":
                stats["excluded"] += 1
                progress.update(overall_task, advance=1)
                continue

            urls = item.get("urls", {}) or {}
            pdf_url = urls.get("pdf")

            # Skip already downloaded
            if item.get("download_status") == "success" and item.get("local_path"):
                stats["skipped"] += 1
                stats["success"] += 1
                progress.update(overall_task, advance=1)
                continue
                
            # No URL available
            if not pdf_url:
                item["download_status"] = "unavailable"
                item["download_error"] = "No PDF URL"
                stats["unavailable"] += 1
                progress.update(overall_task, advance=1)
                continue

            filename = build_filename(item, used_names)
            title = str(item.get("title", ""))[:50]
            
            # Create a task for this specific download
            download_task = progress.add_task(f"[green][{idx}/{len(items)}] {title}", total=None)
            
            target = output_dir / filename
            error = download_with_retry(pdf_url, target, max_retries, progress, download_task)

            progress.remove_task(download_task)
            
            if error:
                item["download_status"] = "failed"
                item["download_error"] = error
                stats["failed"] += 1
                pending_items.append(build_pending_item(item, pdf_url, error))
            else:
                item["download_status"] = "success"
                item["download_error"] = None
                item["local_path"] = make_local_path(output_dir, filename)
                stats["success"] += 1
            
            progress.update(overall_task, advance=1)

    return {
        "generated_at": utc_now_iso(),
        "l1_stats": stats,
        "pending_items": pending_items,
    }
