"""Sources configuration utilities."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from insight_pilot.errors import ErrorCode, SkillError

SUPPORTED_BLOG_TYPES = {"ghost", "wordpress", "rss", "auto"}


def default_config() -> Dict[str, object]:
    """Default sources configuration."""
    return {"blogs": []}


def resolve_sources_path(project_root: Optional[Path], config_path: Optional[str]) -> Path:
    """Resolve sources.yaml path."""
    if config_path:
        return Path(config_path).expanduser().resolve()
    env_path = os.getenv("INSIGHT_PILOT_SOURCES")
    if env_path:
        return Path(env_path).expanduser().resolve()
    if project_root:
        return (project_root / "sources.yaml").resolve()
    return Path("sources.yaml").resolve()


def _name_to_env(name: str) -> str:
    """Convert a source name into an env var-friendly key."""
    safe = "".join(ch if ch.isalnum() else "_" for ch in name.upper())
    return safe.strip("_")


def apply_env_overrides(sources: List[Dict[str, object]]) -> None:
    """Apply environment variable overrides to sources."""
    for source in sources:
        name = source.get("name") or ""
        if not name:
            continue
        env_key = _name_to_env(str(name))
        url_override = os.getenv(f"INSIGHT_PILOT_SOURCE_URL_{env_key}")
        type_override = os.getenv(f"INSIGHT_PILOT_SOURCE_TYPE_{env_key}")
        api_key_override = os.getenv(f"INSIGHT_PILOT_SOURCE_API_KEY_{env_key}")

        if url_override:
            source["url"] = url_override
        if type_override:
            source["type"] = type_override
        if api_key_override:
            source["api_key"] = api_key_override


def validate_sources_config(config: Dict[str, object]) -> List[Dict[str, object]]:
    """Validate and normalize sources config."""
    blogs = config.get("blogs", [])
    if blogs is None:
        return []
    if not isinstance(blogs, list):
        raise SkillError(
            message="sources.yaml 'blogs' must be a list",
            code=ErrorCode.INVALID_INPUT_FORMAT,
        )

    normalized: List[Dict[str, object]] = []
    for entry in blogs:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or ""
        url = entry.get("url") or ""
        blog_type = (entry.get("type") or "auto").lower()
        if not name or not url:
            continue
        if blog_type not in SUPPORTED_BLOG_TYPES:
            raise SkillError(
                message=f"Unsupported blog type: {blog_type}",
                code=ErrorCode.INVALID_INPUT_FORMAT,
            )
        normalized.append({
            "name": name,
            "type": blog_type,
            "url": url,
            "category": entry.get("category"),
            "api_key": entry.get("api_key"),
        })
    return normalized


def load_sources_config(path: Path) -> Dict[str, object]:
    """Load sources configuration from YAML."""
    if not path.exists():
        return default_config()
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise SkillError(
            message="sources.yaml must contain a mapping at top level",
            code=ErrorCode.INVALID_INPUT_FORMAT,
        )
    return data


def save_sources_config(path: Path, config: Dict[str, object]) -> None:
    """Save sources configuration to YAML."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False, allow_unicode=False)


def list_sources(path: Path) -> List[Dict[str, object]]:
    """Load, validate, and apply env overrides."""
    config = load_sources_config(path)
    sources = validate_sources_config(config)
    apply_env_overrides(sources)
    for source in sources:
        blog_type = (source.get("type") or "").lower()
        if blog_type and blog_type not in SUPPORTED_BLOG_TYPES:
            raise SkillError(
                message=f"Unsupported blog type after env override: {blog_type}",
                code=ErrorCode.INVALID_INPUT_FORMAT,
            )
    return sources


def add_source(path: Path, entry: Dict[str, object]) -> None:
    """Add a source to sources.yaml."""
    config = load_sources_config(path)
    sources = config.get("blogs") or []
    if not isinstance(sources, list):
        sources = []
    sources.append(entry)
    config["blogs"] = sources
    save_sources_config(path, config)


def remove_source(path: Path, name: str) -> bool:
    """Remove a source by name."""
    config = load_sources_config(path)
    sources = config.get("blogs") or []
    if not isinstance(sources, list):
        return False
    remaining = [s for s in sources if (s.get("name") or "") != name]
    config["blogs"] = remaining
    save_sources_config(path, config)
    return len(remaining) != len(sources)
