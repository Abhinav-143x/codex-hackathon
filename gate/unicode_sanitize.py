"""
gate/unicode_sanitize.py — Strip and detect invisible Unicode before the Proposer sees anything.

Strips:
  - Unicode tag block (U+E0000–U+E007F): used by some prompt injection attacks
  - Zero-width chars: ZWSP (U+200B), ZWJ (U+200D), ZWNJ (U+200C), BOM (U+FEFF)
  - Bidi override chars: U+202A–U+202E, U+2066–U+2069 (can reorder displayed text)

Returns:
  (clean_text: str, findings: list[dict])
  findings = [{"codepoint": "U+E0041", "name": "TAG LATIN SMALL LETTER A", "count": 3}, ...]
"""

import re
import unicodedata
from typing import Tuple, List

# --- Character ranges to strip and flag ---

# Unicode tag block (U+E0000–U+E007F) — often used for invisible prompt injection
_TAG_BLOCK_RE = re.compile(r"[\U000E0000-\U000E007F]+")

# Zero-width / BOM
_ZERO_WIDTH_CHARS = {
    "\u200B": "ZERO WIDTH SPACE",
    "\u200C": "ZERO WIDTH NON-JOINER",
    "\u200D": "ZERO WIDTH JOINER",
    "\uFEFF": "ZERO WIDTH NO-BREAK SPACE (BOM)",
    "\u2060": "WORD JOINER",
}

# Bidi override characters (can visually reorder code)
_BIDI_CHARS = {
    "\u202A": "LEFT-TO-RIGHT EMBEDDING",
    "\u202B": "RIGHT-TO-LEFT EMBEDDING",
    "\u202C": "POP DIRECTIONAL FORMATTING",
    "\u202D": "LEFT-TO-RIGHT OVERRIDE",
    "\u202E": "RIGHT-TO-LEFT OVERRIDE",
    "\u2066": "LEFT-TO-RIGHT ISOLATE",
    "\u2067": "RIGHT-TO-LEFT ISOLATE",
    "\u2068": "FIRST STRONG ISOLATE",
    "\u2069": "POP DIRECTIONAL ISOLATE",
}

_ALL_INVISIBLE = {**_ZERO_WIDTH_CHARS, **_BIDI_CHARS}


def sanitize(text: str) -> Tuple[str, List[dict]]:
    """
    Strip invisible Unicode from text. Return (clean_text, findings).
    findings is empty if text was clean.
    """
    findings: List[dict] = []
    clean = text

    # 1. Tag block
    tag_matches = _TAG_BLOCK_RE.findall(text)
    if tag_matches:
        for match in tag_matches:
            for ch in match:
                cp = f"U+{ord(ch):04X}"
                try:
                    name = unicodedata.name(ch, f"TAG CHAR {cp}")
                except Exception:
                    name = f"TAG CHAR {cp}"
                findings.append({"codepoint": cp, "name": name, "category": "tag_block"})
        clean = _TAG_BLOCK_RE.sub("", clean)

    # 2. Zero-width + bidi
    for ch, name in _ALL_INVISIBLE.items():
        count = clean.count(ch)
        if count > 0:
            cp = f"U+{ord(ch):04X}"
            findings.append({
                "codepoint": cp,
                "name": name,
                "count": count,
                "category": "bidi" if ch in _BIDI_CHARS else "zero_width",
            })
            clean = clean.replace(ch, "")

    return clean, findings


def sanitize_inputs(diff_text: str, pr_description: str) -> Tuple[str, str, List[dict]]:
    """
    Sanitize both diff_text and pr_description. Returns (clean_diff, clean_desc, all_findings).
    """
    clean_diff, diff_findings = sanitize(diff_text)
    clean_desc, desc_findings = sanitize(pr_description)

    all_findings = (
        [{"source": "diff", **f} for f in diff_findings]
        + [{"source": "description", **f} for f in desc_findings]
    )
    return clean_diff, clean_desc, all_findings
