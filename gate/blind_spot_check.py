"""
gate/blind_spot_check.py — Gate check: flag binary/image files in the diff.

Per GhostCommit (ASSET Research Group, June 2026): Cursor Bugbot and CodeRabbit both missed a
real prompt-injection attack hidden in a PNG image because neither tool reads images.
Our Gate doesn't stay silent about what it can't verify — it flags it.

Forces needs-review (not hard-ungrounded) since legitimate PRs also add real images.
Never lets an unreadable file default to invisible-therefore-safe.
"""

from __future__ import annotations

_UNVERIFIABLE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".pdf", ".zip", ".tar", ".gz", ".bz2",
    ".wasm", ".exe", ".dll", ".so", ".dylib",
    ".bin", ".dat",
}


def blind_spot_check(diff_text: str) -> dict:
    """
    Scan diff for binary files or image/archive references we cannot fully inspect.

    Returns {"pass": bool, "reason": str}
    Returns pass=False (needs-review) if any unverifiable content found.
    """
    flagged: list[str] = []

    for line in diff_text.splitlines():
        line_stripped = line.strip()

        # Git binary file marker
        if line_stripped.startswith("Binary files"):
            flagged.append(line_stripped[:120])
            continue

        # Check file path lines (diff header lines like +++ b/some/file.png)
        if line_stripped.startswith(("--- ", "+++ ")):
            path_part = line_stripped[4:].strip().lstrip("ab/")
            lower = path_part.lower()
            if any(lower.endswith(ext) for ext in _UNVERIFIABLE_EXTENSIONS):
                flagged.append(path_part[:120])

    if not flagged:
        return {
            "pass": True,
            "reason": "blind_spot_check: no unverifiable binary or image content in diff.",
        }

    shown = flagged[:3]
    more = f" (+{len(flagged) - 3} more)" if len(flagged) > 3 else ""
    return {
        "pass": False,
        "reason": (
            f"blind_spot_check: diff includes {len(flagged)} binary/image file(s) "
            f"that our checks cannot fully inspect: {shown}{more}. "
            "Per GhostCommit (ASSET Research Group, June 2026), exactly this blind spot allowed "
            "CodeRabbit and Cursor Bugbot to both miss a real exploit hidden in an image. "
            "Flagging as needs-review rather than staying silent — "
            "a maintainer must manually inspect these files."
        ),
    }
