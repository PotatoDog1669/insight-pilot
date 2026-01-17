"""Project management utilities."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from insight_pilot.models import utc_now_iso


class ProjectContext:
    """Manages project paths and state."""

    def __init__(self, project_root: Path):
        self.root = project_root.resolve()
        self.insight_dir = self.root / ".insight"
        self.config_path = self.insight_dir / "config.yaml"
        self.state_path = self.insight_dir / "state.json"
        self.items_path = self.insight_dir / "items.json"
        self.download_failed_path = self.insight_dir / "download_failed.json"
        self.analysis_dir = self.insight_dir / "analysis"
        self.papers_dir = self.root / "papers"
        self.reports_dir = self.root / "reports"
        self.index_path = self.root / "index.md"

    def exists(self) -> bool:
        """Check if project exists."""
        return self.insight_dir.exists() and self.state_path.exists()

    def load_state(self) -> Dict[str, Any]:
        """Load project state."""
        if not self.state_path.exists():
            return {}
        with open(self.state_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_state(self, state: Dict[str, Any]) -> None:
        """Save project state."""
        state["last_updated"] = utc_now_iso()
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def load_items(self) -> List[Dict[str, Any]]:
        """Load items from items.json."""
        if not self.items_path.exists():
            return []
        with open(self.items_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "items" in data:
            return data["items"]
        return data if isinstance(data, list) else []

    def save_items(self, items: List[Dict[str, Any]]) -> None:
        """Save items to items.json."""
        self.items_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.items_path, "w", encoding="utf-8") as f:
            json.dump({"items": items}, f, indent=2)

    def load_download_failed(self) -> List[Dict[str, Any]]:
        """Load download failed items."""
        if not self.download_failed_path.exists():
            return []
        with open(self.download_failed_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("items", []) if isinstance(data, dict) else data

    def save_download_failed(self, items: List[Dict[str, Any]]) -> None:
        """Save download failed items."""
        with open(self.download_failed_path, "w", encoding="utf-8") as f:
            json.dump({
                "generated_at": utc_now_iso(),
                "items": items,
            }, f, indent=2)

    def load_analysis(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Load analysis for a specific item."""
        path = self.analysis_dir / f"{item_id}.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_analysis(self, item_id: str, analysis: Dict[str, Any]) -> None:
        """Save analysis for a specific item."""
        self.analysis_dir.mkdir(parents=True, exist_ok=True)
        path = self.analysis_dir / f"{item_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(analysis, f, indent=2)

    def list_analyses(self) -> List[str]:
        """List all analyzed item IDs."""
        if not self.analysis_dir.exists():
            return []
        return [p.stem for p in self.analysis_dir.glob("*.json")]

    def get_raw_files(self) -> List[Path]:
        """Get list of raw search result files."""
        return list(self.insight_dir.glob("raw_*.json"))


def init_project(
    topic: str,
    output_dir: Path,
    keywords: Optional[List[str]] = None,
) -> ProjectContext:
    """Initialize a new research project.
    
    Args:
        topic: Research topic
        output_dir: Project directory
        keywords: Optional list of keywords
        
    Returns:
        ProjectContext for the new project
    """
    ctx = ProjectContext(output_dir)
    
    ctx.insight_dir.mkdir(parents=True, exist_ok=True)
    ctx.papers_dir.mkdir(exist_ok=True)
    ctx.reports_dir.mkdir(exist_ok=True)
    ctx.analysis_dir.mkdir(exist_ok=True)

    # Create config.yaml
    if not ctx.config_path.exists():
        config = {
            "topic": topic,
            "keywords": keywords or [topic.lower()],
            "time_range": {"start": None, "end": None},
            "sources": {"enabled": ["arxiv", "openalex"]},
        }
        with open(ctx.config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, sort_keys=False)

    now = utc_now_iso()

    # Create state.json
    if not ctx.state_path.exists():
        state = {
            "topic": topic,
            "keywords": keywords or [],
            "sources_used": [],
            "created_at": now,
            "last_updated": now,
            "total_items": 0,
            "download_stats": {"l1_success": 0, "l2_success": 0, "pending": 0},
        }
        with open(ctx.state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    # Create items.json
    if not ctx.items_path.exists():
        with open(ctx.items_path, "w", encoding="utf-8") as f:
            json.dump({"items": []}, f, indent=2)

    # Create index.md
    if not ctx.index_path.exists():
        from datetime import datetime
        with open(ctx.index_path, "w", encoding="utf-8") as f:
            f.write(f"# {topic} Research Index\n\n")
            f.write(f"> Created: {datetime.now().strftime('%Y-%m-%d')}\n\n")
            f.write("*No items collected yet.*\n")

    return ctx
