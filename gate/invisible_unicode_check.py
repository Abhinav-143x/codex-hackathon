"""
gate/invisible_unicode_check.py — Gate check: fail-closed if invisible Unicode is found.

This is the DETERMINISTIC Gate enforcement of unicode_sanitize.
If the sanitizer found anything, this check fails — regardless of what the
characters decoded to. We never let "maybe it was harmless" override fail-closed.
"""

from __future__ import annotations
from gate.unicode_sanitize import sanitize_inputs


def invisible_unicode_check(diff_text: str, pr_description: str = "") -> dict:
    """
    Gate check: detect invisible Unicode in diff_text or pr_description.

    Returns {"pass": bool, "reason": str}
    Fails (pass=False) if ANY invisible Unicode is detected — fail-closed.
    """
    _, _, findings = sanitize_inputs(diff_text, pr_description)

    if not findings:
        return {
            "pass": True,
            "reason": "invisible_unicode_check: no invisible Unicode detected in diff or description.",
        }

    # Summarise findings for the reason string
    categories = {}
    for f in findings:
        cat = f.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    summary = ", ".join(f"{count}× {cat}" for cat, count in categories.items())
    first_few = [f["codepoint"] for f in findings[:5]]

    return {
        "pass": False,
        "reason": (
            f"invisible_unicode_check: {len(findings)} invisible Unicode character(s) detected "
            f"({summary}). First findings: {first_few}. "
            "This is a known prompt-injection vector (e.g. Unicode tag block used to embed hidden "
            "instructions). Stripping and flagging — fail-closed regardless of content. "
            "Routed to needs-review, not silently passed."
        ),
    }
