"""
proposer.py — Single-shot LLM claim extractor.

Loads agent.md as the locked system prompt (read-only, never modified).
Formats the exact 5W user-turn template from the spec.
Calls config.call_llm() and parses the JSON claim.

DO NOT add multi-tool / self-critique loops here — those are reserved for the
on-site live build on July 14.

Usage:
    from proposer import propose_claim
    claim = propose_claim(diff_text, pr_description, tier="fast")
"""

import json
import re
import textwrap
from pathlib import Path

import config

# ── load the locked system prompt ─────────────────────────────────────────────
_AGENT_MD_PATH = Path(__file__).parent / "agent.md"

def _load_system_prompt() -> str:
    """Read agent.md at call-time (so runtime changes to the file are picked
    up, but the content is NEVER mutated by this code)."""
    return _AGENT_MD_PATH.read_text(encoding="utf-8")

# ── 5W user-turn template (verbatim from spec) ────────────────────────────────
_5W_TEMPLATE = textwrap.dedent("""\
    Given this diff, answer each explicitly — do not skip any, do not soften
    with qualifiers like 'likely' or 'should':
    1. WHAT changed, in the code, specifically (file, function, line range)?
    2. WHY is this change claimed to be needed (what failure does it prevent)?
    3. WHAT is the actual impact if this change is wrong or incomplete?
    4. WHERE is the evidence in the diff itself (quote the specific line)?
    5. WHO/WHAT would exploit or trigger this if unfixed (concrete trigger
    path, not a hypothetical)?
    If you cannot answer any of these with a specific reference to the diff,
    say 'INSUFFICIENT EVIDENCE' for that field rather than inferring one.

    PR DESCRIPTION:
    {pr_description}

    DIFF:
    {diff_text}
""")

# ── required claim fields ─────────────────────────────────────────────────────
_REQUIRED_FIELDS = {
    "bug_type", "file", "line_range", "description", "confidence",
    "w_what", "w_why", "w_impact", "w_evidence", "w_who",
}

def _parse_claim(raw: str) -> dict:
    """
    Extract JSON from the LLM response.
    Handles:
      - bare JSON
      - JSON wrapped in ```json ... ``` fences
      - JSON preceded by prose
    Falls back to a best-effort error claim if parsing fails.
    """
    # strip markdown fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw, flags=re.IGNORECASE).strip()
    cleaned = cleaned.replace("```", "").strip()

    # find the first {...} block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return _error_claim(f"No JSON object found in response: {raw[:200]}")

    try:
        obj = json.loads(match.group())
    except json.JSONDecodeError as exc:
        return _error_claim(f"JSON parse error: {exc} — raw: {raw[:200]}")

    # backfill any missing fields
    for field in _REQUIRED_FIELDS:
        if field not in obj:
            obj[field] = "INSUFFICIENT EVIDENCE"

    # normalise confidence to float
    try:
        obj["confidence"] = float(obj.get("confidence", 0.0))
    except (TypeError, ValueError):
        obj["confidence"] = 0.0

    return obj


def _error_claim(reason: str) -> dict:
    return {
        "bug_type": "PARSE_ERROR",
        "file": "unknown",
        "line_range": "N/A",
        "description": reason,
        "confidence": 0.0,
        "w_what": "INSUFFICIENT EVIDENCE",
        "w_why": "INSUFFICIENT EVIDENCE",
        "w_impact": "INSUFFICIENT EVIDENCE",
        "w_evidence": "INSUFFICIENT EVIDENCE",
        "w_who": "INSUFFICIENT EVIDENCE",
    }


# ── public API ────────────────────────────────────────────────────────────────
def propose_claim(
    diff_text: str,
    pr_description: str,
    tier: str = "fast",
) -> dict:
    """
    Run the single-shot Proposer.

    Parameters
    ----------
    diff_text       : raw unified diff string
    pr_description  : the PR title + body text
    tier            : "fast" (default) or "strong" — controls model selection

    Returns
    -------
    dict matching the claim JSON schema in agent.md
    """
    system_prompt = _load_system_prompt()
    user_content = _5W_TEMPLATE.format(
        pr_description=pr_description,
        diff_text=diff_text,
    )

    model = config.model_for_tier(tier)
    print(f"[proposer] Calling model={model} (tier={tier}) …")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_content},
    ]

    raw = config.call_llm(messages=messages, model=model, temperature=0.0)
    claim = _parse_claim(raw)

    print(f"[proposer] Claim: bug_type={claim['bug_type']!r}  "
          f"file={claim['file']!r}  confidence={claim['confidence']:.2f}")
    return claim


if __name__ == "__main__":
    # quick smoke-test
    sample_diff = """--- a/utils.py\n+++ b/utils.py\n@@ -10,6 +10,8 @@\n def process(value):\n+    if value is None:\n+        raise ValueError(\"value must not be None\")\n     return value * 2\n"""
    sample_desc = "Fix: add None guard to process() — raises ValueError instead of crashing"
    claim = propose_claim(sample_diff, sample_desc)
    print(json.dumps(claim, indent=2))
