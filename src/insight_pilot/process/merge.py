"""Merge search results from multiple sources."""
from __future__ import annotations

import glob
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

from insight_pilot.models import utc_now_iso


def load_items_from_file(path: Path) -> List[dict]:
    """Load items from a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        if "items" in data:
            return data["items"]
        if "results" in data:
            results = data.get("results", [])
            source = data.get("source")
            timestamp = data.get("timestamp")
            for item in results:
                if source and not item.get("source"):
                    item["source"] = source
                if timestamp and not item.get("collected_at"):
                    item["collected_at"] = timestamp
            return results

    return []


def ensure_fields(item: dict) -> None:
    """Ensure required fields exist in item."""
    item.setdefault("identifiers", {})
    item.setdefault("urls", {})
    item.setdefault("download_status", "pending")
    item.setdefault("collected_at", utc_now_iso())


def assign_ids(items: List[dict]) -> None:
    """Assign unique IDs to items without one."""
    used = {item.get("id") for item in items if item.get("id")}
    counter = 1
    for item in items:
        if item.get("id"):
            continue
        while f"i{counter:04d}" in used:
            counter += 1
        item["id"] = f"i{counter:04d}"
        used.add(item["id"])
        counter += 1


def expand_inputs(inputs: Iterable[str]) -> List[Path]:
    """Expand glob patterns to file paths."""
    paths: List[Path] = []
    for pattern in inputs:
        matches = glob.glob(pattern)
        if matches:
            paths.extend(Path(match) for match in matches)
        else:
            paths.append(Path(pattern))
    return paths


def merge_results(input_files: List[Path]) -> List[dict]:
    """Merge results from multiple input files."""
    items: List[dict] = []

    for path in input_files:
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")
        items.extend(load_items_from_file(path))

    for item in items:
        ensure_fields(item)

    assign_ids(items)
    return items


def save_items(items: List[dict], output_path: Path) -> None:
    """Save items to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, indent=2)
