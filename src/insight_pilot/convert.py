"""PDF to Markdown conversion module.

Supports multiple conversion backends:
- pymupdf4llm: Fast, lightweight, good for most papers (default)
- marker: Higher quality, better table/equation support, but slower

Configuration via config.yaml:
    pdf_converter:
        backend: pymupdf4llm  # or "marker"
        # pymupdf4llm options
        page_chunks: false
        # marker options (only when backend=marker)
        use_llm: false
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


def load_convert_config(project_dir: Path) -> Dict[str, Any]:
    """Load PDF conversion config from project config.yaml.
    
    Args:
        project_dir: Project root directory
        
    Returns:
        Config dict with defaults applied
    """
    defaults = {
        "backend": "pymupdf4llm",  # default to faster option
        "page_chunks": False,
        "use_llm": False,
    }
    
    config_path = project_dir / ".insight" / "config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        
        pdf_config = config.get("pdf_converter", {})
        defaults.update(pdf_config)
    
    return defaults


def check_pymupdf4llm_available() -> bool:
    """Check if pymupdf4llm is installed."""
    try:
        import pymupdf4llm
        return True
    except ImportError:
        return False


def check_marker_available() -> bool:
    """Check if marker-pdf is installed."""
    try:
        from marker.converters.pdf import PdfConverter
        return True
    except ImportError:
        return False


def convert_with_pymupdf4llm(
    pdf_path: Path,
    page_chunks: bool = False,
) -> Dict[str, Any]:
    """Convert PDF to markdown using pymupdf4llm.
    
    Args:
        pdf_path: Path to PDF file
        page_chunks: Whether to return page-chunked output
        
    Returns:
        Dict with 'markdown', 'metadata', 'images' keys
    """
    import pymupdf4llm
    
    if page_chunks:
        # Return list of page contents
        result = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)
        markdown = "\n\n---\n\n".join(
            chunk.get("text", "") for chunk in result
        )
    else:
        markdown = pymupdf4llm.to_markdown(str(pdf_path))
    
    return {
        "markdown": markdown,
        "metadata": {"converter": "pymupdf4llm"},
        "images": {},  # pymupdf4llm doesn't extract images separately
    }


def convert_with_marker(
    pdf_path: Path,
    output_dir: Optional[Path] = None,
    save_images: bool = True,
    use_llm: bool = False,
) -> Dict[str, Any]:
    """Convert PDF to markdown using marker-pdf.
    
    Args:
        pdf_path: Path to PDF file
        output_dir: Directory to save images
        save_images: Whether to extract and save images
        use_llm: Whether to use LLM for better accuracy
        
    Returns:
        Dict with 'markdown', 'metadata', 'images' keys
    """
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.output import text_from_rendered
    
    # Create converter
    converter = PdfConverter(
        artifact_dict=create_model_dict(),
    )
    
    # Convert PDF
    rendered = converter(str(pdf_path))
    
    # Extract text and images
    markdown_text, _, images = text_from_rendered(rendered)
    
    # Save images if requested
    saved_images: Dict[str, str] = {}
    if save_images and images and output_dir:
        images_dir = output_dir / "images"
        images_dir.mkdir(exist_ok=True)
        
        for img_name, img_data in images.items():
            img_path = images_dir / img_name
            with open(img_path, "wb") as f:
                f.write(img_data)
            saved_images[img_name] = str(img_path.relative_to(output_dir))
    
    # Get metadata
    metadata = {"converter": "marker"}
    if hasattr(rendered, "metadata"):
        metadata["marker_metadata"] = rendered.metadata
    
    return {
        "markdown": markdown_text,
        "metadata": metadata,
        "images": saved_images,
    }


def convert_pdf_to_markdown(
    pdf_path: Path,
    output_dir: Optional[Path] = None,
    backend: str = "pymupdf4llm",
    save_images: bool = True,
    **kwargs,
) -> Dict[str, Any]:
    """Convert a single PDF to markdown.
    
    Args:
        pdf_path: Path to PDF file
        output_dir: Directory to save output (for marker images)
        backend: Conversion backend ("pymupdf4llm" or "marker")
        save_images: Whether to extract and save images (marker only)
        **kwargs: Additional backend-specific options
        
    Returns:
        Dict with 'markdown', 'metadata', 'images' keys
        
    Raises:
        ImportError: If required backend is not installed
        FileNotFoundError: If PDF doesn't exist
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    
    if backend == "pymupdf4llm":
        if not check_pymupdf4llm_available():
            raise ImportError(
                "pymupdf4llm is not installed. Install with: pip install pymupdf4llm"
            )
        return convert_with_pymupdf4llm(
            pdf_path,
            page_chunks=kwargs.get("page_chunks", False),
        )
    
    elif backend == "marker":
        if not check_marker_available():
            raise ImportError(
                "marker-pdf is not installed. Install with: pip install marker-pdf"
            )
        return convert_with_marker(
            pdf_path,
            output_dir=output_dir,
            save_images=save_images,
            use_llm=kwargs.get("use_llm", False),
        )
    
    else:
        raise ValueError(f"Unknown backend: {backend}. Use 'pymupdf4llm' or 'marker'")


def convert_paper(
    item: Dict[str, Any],
    project_dir: Path,
    markdown_dir: Path,
    backend: str = "pymupdf4llm",
    save_images: bool = True,
    **kwargs,
) -> Dict[str, Any]:
    """Convert a downloaded paper's PDF to markdown.
    
    Args:
        item: Paper item from items.json
        project_dir: Base project directory
        markdown_dir: Directory to save markdown files
        backend: Conversion backend
        save_images: Whether to extract images (marker only)
        **kwargs: Additional backend options
        
    Returns:
        Result dict with status and paths
    """
    item_id = item.get("id", "")
    local_path = item.get("local_path")
    
    if not local_path:
        return {
            "status": "skipped",
            "reason": "no_local_path",
            "id": item_id,
        }
    
    # local_path can be absolute or relative
    pdf_path = Path(local_path)
    if not pdf_path.is_absolute():
        pdf_path = project_dir / local_path.lstrip("./")
    
    if not pdf_path.exists():
        return {
            "status": "skipped",
            "reason": "pdf_not_found",
            "id": item_id,
            "path": str(pdf_path),
        }
    
    # Create output directory for this paper's markdown
    output_dir = markdown_dir / item_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        result = convert_pdf_to_markdown(
            pdf_path,
            output_dir=output_dir,
            backend=backend,
            save_images=save_images,
            **kwargs,
        )
        
        # Save markdown file
        md_path = output_dir / f"{item_id}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            # Add paper metadata header
            f.write(f"# {item.get('title', 'Untitled')}\n\n")
            authors = item.get('authors', [])
            if isinstance(authors, list):
                authors = ', '.join(authors)
            f.write(f"**Authors**: {authors}\n")
            f.write(f"**Date**: {item.get('date', 'Unknown')}\n")
            if item.get("url"):
                f.write(f"**URL**: {item.get('url')}\n")
            f.write("\n---\n\n")
            f.write(result["markdown"])
        
        # Save conversion metadata
        meta_path = output_dir / "metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({
                "id": item_id,
                "title": item.get("title"),
                "source_pdf": str(local_path),
                "markdown_path": str(md_path),
                "backend": backend,
                "images": result["images"],
                "converter_metadata": result["metadata"],
            }, f, indent=2, ensure_ascii=False)
        
        return {
            "status": "success",
            "id": item_id,
            "markdown_path": str(md_path),
            "metadata_path": str(meta_path),
            "backend": backend,
            "images_count": len(result["images"]),
        }
        
    except ImportError as e:
        return {
            "status": "failed",
            "reason": "missing_dependency",
            "id": item_id,
            "error": str(e),
        }
    except Exception as e:
        return {
            "status": "failed",
            "reason": "conversion_error",
            "id": item_id,
            "error": str(e),
        }


def convert_papers(
    items: List[Dict[str, Any]],
    project_dir: Path,
    markdown_dir: Path,
    skip_existing: bool = True,
    backend: Optional[str] = None,
    save_images: bool = True,
    **kwargs,
) -> Dict[str, Any]:
    """Convert multiple papers to markdown.
    
    Args:
        items: List of paper items from items.json
        project_dir: Base project directory
        markdown_dir: Directory to save markdown files
        skip_existing: Skip papers that already have markdown
        backend: Conversion backend (None = use config or default)
        save_images: Whether to extract images
        **kwargs: Additional backend options
        
    Returns:
        Stats dict with conversion results
    """
    # Load config if backend not specified
    if backend is None:
        config = load_convert_config(project_dir)
        backend = config.get("backend", "pymupdf4llm")
        kwargs.setdefault("page_chunks", config.get("page_chunks", False))
        kwargs.setdefault("use_llm", config.get("use_llm", False))
    
    # Check backend availability
    if backend == "pymupdf4llm" and not check_pymupdf4llm_available():
        return {
            "status": "failed",
            "reason": "missing_dependency",
            "message": "pymupdf4llm is not installed. Install with: pip install pymupdf4llm",
        }
    elif backend == "marker" and not check_marker_available():
        return {
            "status": "failed",
            "reason": "missing_dependency",
            "message": "marker-pdf is not installed. Install with: pip install 'insight-pilot[marker]'",
        }
    
    markdown_dir.mkdir(parents=True, exist_ok=True)
    
    stats = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "not_downloaded": 0,
    }
    results: List[Dict[str, Any]] = []
    
    for item in items:
        # Skip excluded items
        if item.get("status") == "excluded":
            continue
        
        item_id = item.get("id", "")
        if not item_id:
            continue
        
        stats["total"] += 1
        
        # Check if downloaded
        if item.get("download_status") != "success":
            stats["not_downloaded"] += 1
            continue
        
        # Check if already converted
        md_path = markdown_dir / item_id / f"{item_id}.md"
        if skip_existing and md_path.exists():
            stats["skipped"] += 1
            results.append({
                "status": "skipped",
                "reason": "already_exists",
                "id": item_id,
                "path": str(md_path),
            })
            continue
        
        # Convert
        result = convert_paper(
            item,
            project_dir,
            markdown_dir,
            backend=backend,
            save_images=save_images,
            **kwargs,
        )
        results.append(result)
        
        if result["status"] == "success":
            stats["success"] += 1
        else:
            stats["failed"] += 1
    
    return {
        "status": "completed",
        "backend": backend,
        "stats": stats,
        "results": results,
    }


def read_markdown_content(
    item_id: str,
    markdown_dir: Path,
    max_chars: int = 30000,
) -> Optional[str]:
    """Read converted markdown content for a paper.
    
    Args:
        item_id: Paper ID
        markdown_dir: Directory containing markdown files
        max_chars: Maximum characters to return
        
    Returns:
        Markdown content or None if not found
    """
    md_path = markdown_dir / item_id / f"{item_id}.md"
    
    if not md_path.exists():
        return None
    
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[... truncated ...]"
        
        return content
    except Exception:
        return None
