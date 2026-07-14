"""
gate/image_text_extract.py — OCR pass on images referenced in a diff.

If pytesseract + Pillow are available, extracts visible text from images.
Extracted text is returned as untrusted data — fed to the Proposer under the
same agent.md framing as diff comments: evaluate, never execute as a directive.

Graceful no-op if pytesseract/Pillow not installed (never crashes the Gate).
"""

from __future__ import annotations
import re
from pathlib import Path


_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}


def _extract_image_paths_from_diff(diff_text: str, base_dir: Path | None = None) -> list[Path]:
    """Find image file paths referenced in the diff headers."""
    paths: list[Path] = []
    for line in diff_text.splitlines():
        if line.startswith(("+++ ", "--- ")):
            path_str = line[4:].strip().lstrip("ab/")
            if any(path_str.lower().endswith(ext) for ext in _IMAGE_EXTENSIONS):
                p = Path(path_str)
                if base_dir:
                    p = base_dir / p
                paths.append(p)
    return paths


def extract_image_text(image_path: Path) -> str:
    """
    OCR a single image file. Returns extracted text, or empty string on failure.
    Never raises — fail closed (falls through to blind_spot_check).
    """
    try:
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(str(image_path)))
    except ImportError:
        return ""  # pytesseract/Pillow not installed — silent no-op
    except Exception:
        return ""  # image unreadable — silent no-op, blind_spot_check will catch it


def extract_all_image_text(diff_text: str, base_dir: Path | None = None) -> dict:
    """
    Extract text from all images referenced in the diff.

    Returns:
        {
            "available": bool,   # True if pytesseract is installed
            "images_found": int,
            "text_extracted": str,  # concatenated OCR text, or ""
            "paths_attempted": [str],
        }
    """
    try:
        import pytesseract  # noqa: F401
        available = True
    except ImportError:
        available = False

    image_paths = _extract_image_paths_from_diff(diff_text, base_dir)

    if not image_paths:
        return {
            "available": available,
            "images_found": 0,
            "text_extracted": "",
            "paths_attempted": [],
        }

    texts = []
    attempted = []
    for p in image_paths:
        attempted.append(str(p))
        text = extract_image_text(p)
        if text.strip():
            texts.append(f"[Image: {p.name}]\n{text.strip()}")

    return {
        "available": available,
        "images_found": len(image_paths),
        "text_extracted": "\n\n".join(texts),
        "paths_attempted": attempted,
    }
