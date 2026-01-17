"""LLM-based paper analysis module."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from insight_pilot.models import utc_now_iso


# Default analysis prompt template
DEFAULT_PROMPT = """You are a research paper analyst. Analyze the following paper and provide a comprehensive analysis.

**Title**: {title}
**Authors**: {authors}
**Date**: {date}
**Abstract**: {abstract}

{pdf_content}

Please provide a structured analysis in JSON format with the following fields:

1. **summary**: A one-sentence summary of the paper (max 50 words, same language as title)

2. **brief_analysis**: A concise 2-3 sentence analysis highlighting the core contribution and significance (max 100 words, same language as title)

3. **detailed_analysis**: A comprehensive analysis (300-500 words, same language as title) covering:
   - Research problem and motivation
   - Proposed approach/method
   - Key innovations and contributions
   - Experimental results and findings
   - Significance and impact

4. **contributions**: List of main contributions (3-5 items, concise bullet points)

5. **methodology**: Brief description of the methodology used (1-2 sentences)

6. **key_findings**: List of key findings/results (3-5 items)

7. **limitations**: List of limitations mentioned or apparent (1-3 items)

8. **future_work**: Potential future research directions (1-3 items)

9. **tags**: List of relevant tags/keywords (5-10 items)

10. **relevance_score**: Rate the paper's relevance to the research topic (1-10)

Respond with valid JSON only, no markdown formatting."""


def load_llm_config(config_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load LLM configuration from yaml file.
    
    Args:
        config_path: Path to config file. If None, searches in default locations.
        
    Returns:
        Config dict or None if not configured.
    """
    search_paths = []
    
    if config_path:
        search_paths.append(config_path)
    
    # Default search paths
    search_paths.extend([
        Path.home() / ".config" / "insight-pilot" / "llm.yaml",
        Path.cwd() / ".codex" / "skills" / "insight-pilot" / "llm.yaml",
        Path.cwd() / ".claude" / "skills" / "insight-pilot" / "llm.yaml",
    ])
    
    for path in search_paths:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                if config and config.get("provider"):
                    return config
    
    return None


def get_api_key(config: Dict[str, Any]) -> Optional[str]:
    """Get API key from config or environment."""
    # Check config first
    if config.get("api_key"):
        return config["api_key"]
    
    # Check environment variables
    provider = config.get("provider", "openai")
    env_vars = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "ollama": None,  # Ollama doesn't need API key
    }
    
    env_var = env_vars.get(provider)
    if env_var:
        return os.environ.get(env_var)
    
    return None


def analyze_with_openai(
    prompt: str,
    config: Dict[str, Any],
    api_key: str,
) -> Dict[str, Any]:
    """Analyze using OpenAI API."""
    import requests
    
    base_url = config.get("base_url") or "https://api.openai.com/v1"
    model = config.get("model", "gpt-4o-mini")
    
    response = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": config.get("max_tokens", 2000),
            "temperature": config.get("temperature", 0.3),
        },
        timeout=120,
    )
    response.raise_for_status()
    
    content = response.json()["choices"][0]["message"]["content"]
    # Parse JSON from response
    return json.loads(content)


def analyze_with_anthropic(
    prompt: str,
    config: Dict[str, Any],
    api_key: str,
) -> Dict[str, Any]:
    """Analyze using Anthropic API."""
    import requests
    
    base_url = config.get("base_url") or "https://api.anthropic.com/v1"
    model = config.get("model", "claude-3-haiku-20240307")
    
    response = requests.post(
        f"{base_url}/messages",
        headers={
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": model,
            "max_tokens": config.get("max_tokens", 2000),
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    response.raise_for_status()
    
    content = response.json()["content"][0]["text"]
    return json.loads(content)


def analyze_with_ollama(
    prompt: str,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Analyze using Ollama (local)."""
    import requests
    
    base_url = config.get("base_url") or "http://localhost:11434"
    model = config.get("model", "llama3")
    
    response = requests.post(
        f"{base_url}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        },
        timeout=300,  # Local models can be slow
    )
    response.raise_for_status()
    
    content = response.json()["response"]
    return json.loads(content)


def extract_pdf_text(pdf_path: Path, max_chars: int = 15000) -> str:
    """Extract text from PDF file.
    
    Args:
        pdf_path: Path to PDF file
        max_chars: Maximum characters to extract
        
    Returns:
        Extracted text or empty string if extraction fails
    """
    try:
        import fitz  # PyMuPDF
        
        doc = fitz.open(pdf_path)
        text_parts = []
        total_chars = 0
        
        for page in doc:
            page_text = page.get_text()
            if total_chars + len(page_text) > max_chars:
                remaining = max_chars - total_chars
                text_parts.append(page_text[:remaining])
                break
            text_parts.append(page_text)
            total_chars += len(page_text)
        
        doc.close()
        return "\n".join(text_parts)
    except ImportError:
        return ""  # PyMuPDF not installed
    except Exception:
        return ""  # PDF extraction failed


def analyze_paper(
    item: Dict[str, Any],
    papers_dir: Path,
    config: Dict[str, Any],
    api_key: Optional[str] = None,
    markdown_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Analyze a single paper using LLM.
    
    Args:
        item: Paper item from items.json
        papers_dir: Directory containing PDFs
        config: LLM configuration
        api_key: API key (optional, will be looked up if not provided)
        markdown_dir: Directory containing converted markdown files
        
    Returns:
        Analysis result dict
    """
    # Get API key if not provided
    if not api_key:
        api_key = get_api_key(config)
    
    provider = config.get("provider", "openai")
    item_id = item.get("id", "")
    
    # Try to get content: prefer markdown, fallback to PDF extraction
    full_text = ""
    content_source = "none"
    
    # First try markdown (from marker conversion)
    if markdown_dir:
        from insight_pilot.convert import read_markdown_content
        md_content = read_markdown_content(item_id, markdown_dir)
        if md_content:
            full_text = md_content
            content_source = "markdown"
    
    # Fallback to PDF extraction if no markdown
    if not full_text:
        local_path = item.get("local_path")
        if local_path:
            # local_path can be absolute or relative
            pdf_path = Path(local_path)
            if not pdf_path.is_absolute():
                pdf_path = papers_dir.parent / local_path.lstrip("./")
            if pdf_path.exists():
                full_text = extract_pdf_text(pdf_path)
                if full_text:
                    content_source = "pdf"
    
    # Build content section for prompt
    pdf_content = ""
    if full_text:
        pdf_content = f"\n**Full Text (from {content_source})**:\n{full_text}"
    
    # Build prompt
    authors = item.get("authors", [])
    if isinstance(authors, list):
        authors = ", ".join(authors)
    
    prompt = DEFAULT_PROMPT.format(
        title=item.get("title", "Unknown"),
        authors=authors,
        date=item.get("date", "Unknown"),
        abstract=item.get("abstract", "Not available"),
        pdf_content=pdf_content,
    )
    
    # Call appropriate provider
    if provider == "openai":
        if not api_key:
            raise ValueError("OpenAI API key not configured")
        result = analyze_with_openai(prompt, config, api_key)
    elif provider == "anthropic":
        if not api_key:
            raise ValueError("Anthropic API key not configured")
        result = analyze_with_anthropic(prompt, config, api_key)
    elif provider == "ollama":
        result = analyze_with_ollama(prompt, config)
    else:
        raise ValueError(f"Unknown provider: {provider}")
    
    # Add metadata
    result["id"] = item.get("id", "")
    result["title"] = item.get("title", "")
    result["analyzed_at"] = utc_now_iso()
    result["analyzed_by"] = f"{provider}/{config.get('model', 'unknown')}"
    
    return result


def analyze_papers(
    items: List[Dict[str, Any]],
    papers_dir: Path,
    analysis_dir: Path,
    config: Optional[Dict[str, Any]] = None,
    skip_existing: bool = True,
    markdown_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Analyze multiple papers.
    
    Args:
        items: List of paper items
        papers_dir: Directory containing PDFs
        analysis_dir: Directory to save analysis results
        config: LLM configuration (if None, returns without analyzing)
        skip_existing: Skip papers that already have analysis
        markdown_dir: Directory containing converted markdown files
        
    Returns:
        Stats dict with success/failed/skipped counts
    """
    if not config:
        return {
            "status": "skipped",
            "reason": "no_llm_config",
            "message": "LLM not configured. Agent should analyze papers manually.",
        }
    
    api_key = get_api_key(config)
    provider = config.get("provider", "openai")
    
    if provider != "ollama" and not api_key:
        return {
            "status": "skipped",
            "reason": "no_api_key",
            "message": f"API key not found for {provider}. Agent should analyze papers manually.",
        }
    
    analysis_dir.mkdir(parents=True, exist_ok=True)
    
    stats = {"total": 0, "success": 0, "failed": 0, "skipped": 0, "not_downloaded": 0}
    errors: List[Dict[str, str]] = []
    
    for item in items:
        # Skip excluded items
        if item.get("status") == "excluded":
            continue
        
        item_id = item.get("id", "")
        if not item_id:
            continue
        
        stats["total"] += 1
        
        # Skip if not downloaded - must have PDF to analyze
        if item.get("download_status") != "success":
            stats["not_downloaded"] += 1
            continue
        
        # Skip if already analyzed
        analysis_path = analysis_dir / f"{item_id}.json"
        if skip_existing and analysis_path.exists():
            stats["skipped"] += 1
            continue
        
        try:
            result = analyze_paper(item, papers_dir, config, api_key, markdown_dir)
            
            with open(analysis_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            stats["success"] += 1
        except Exception as e:
            stats["failed"] += 1
            errors.append({
                "id": item_id,
                "title": item.get("title", ""),
                "error": str(e),
            })
    
    return {
        "status": "completed",
        "stats": stats,
        "errors": errors if errors else None,
        "provider": provider,
        "model": config.get("model"),
    }
