"""
explainer.py — Verdict Explainer (ONE bounded LLM call).

Runs AFTER verdict.py has already decided the outcome.
Takes the final verdict + raw check results and writes exactly ONE plain-English
sentence explaining why.

CRITICAL CONSTRAINTS (enforced by design, not just docs):
  - The verdict is passed in as ALREADY-FINAL input. The LLM is told it cannot
    change it — it can only explain it.
  - The prompt explicitly states: "Do not re-evaluate or question the verdict."
  - The explainer output is a narration, not a decision.
  - Falls back to a deterministic template sentence if no API key is set.
"""

import json
import config


# ── prompt templates ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a verdict narrator. A deterministic, non-LLM Evidence Gate has
already made a final decision about a pull request. Your ONLY job is to write
exactly ONE plain-English sentence that explains WHY the Gate reached that verdict,
based on the check results provided.

Rules:
- Write exactly ONE sentence. No more.
- Do NOT re-evaluate, question, or soften the verdict.
- Do NOT add qualifiers like "appears to" or "seems to".
- Quote the specific failing check name and reason if the verdict is ungrounded.
- The verdict is final — you narrate it, you do not reconsider it.
- Output only the sentence. No preamble, no markdown."""

_USER_TEMPLATE = """Verdict: {verdict}
Claim: {claim_desc}
Failing checks: {failing}
Check reasons:
{reasons}

Write one sentence explaining why this PR received a '{verdict}' verdict, referring specifically to the claim above."""


# ── offline fallback ──────────────────────────────────────────────────────────

def _fallback_sentence(verdict_data: dict) -> str:
    """Deterministic fallback when no API key is set."""
    verdict = verdict_data.get("verdict", "unknown")
    failing = verdict_data.get("failing_checks", [])
    reasons = verdict_data.get("reasons", [])
    checks = verdict_data.get("checks", {})
    test_reason = checks.get("test_exec", {}).get("reason", "")
    stub_test = "stub pass" in test_reason.lower()

    if verdict == "grounded":
        if stub_test:
            return (
                "The structural Gate checks passed, but real test execution was not available "
                "for this sample, so the result should not be treated as fully execution-verified."
            )
        return (
            "All available deterministic Gate checks passed: coverage matched the claimed lines, "
            "the description matched the diff's syntax symbols, and no blind-spot or invisible-Unicode flags fired."
        )
    elif verdict == "ungrounded":
        first_reason = reasons[0] if reasons else "a Gate check failed."
        checks_str = " and ".join(failing) if failing else "a Gate check"
        return (
            f"This PR is ungrounded because {checks_str} failed: {first_reason.split(':')[-1].strip()[:200]}"
        )
    else:  # needs-review
        if reasons:
            checks_str = " and ".join(failing) if failing else "a Gate check"
            return (
                f"The PR needs human review because {checks_str} could not verify the claim: "
                f"{reasons[0][:180]}"
            )
        return (
            "The PR needs human review because the deterministic checks could not fully verify "
            "the claim from the available evidence."
        )


# ── public API ────────────────────────────────────────────────────────────────

def explain_verdict(verdict_data: dict, claim: dict = None) -> str:
    """
    Generate a single plain-English explanation sentence for the given verdict.

    The verdict_data is the output of verdict.compute_verdict() — it is
    treated as FINAL INPUT, never as something to reconsider.

    Parameters
    ----------
    verdict_data : output from verdict.compute_verdict()
    claim        : output from proposer.propose_claim()

    Returns
    -------
    str : one plain-English sentence
    """
    if config.PROVIDER == "offline":
        print("[explainer] No API key — using deterministic fallback sentence.")
        return _fallback_sentence(verdict_data)

    verdict  = verdict_data.get("verdict", "unknown")
    failing  = verdict_data.get("failing_checks", [])
    reasons  = verdict_data.get("reasons", [])

    user_content = _USER_TEMPLATE.format(
        verdict=verdict,
        claim_desc=claim.get("description", "Unknown claim") if claim else "Unknown claim",
        failing=", ".join(failing) if failing else "none",
        reasons="\n".join(f"- {r}" for r in reasons),
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]

    print(f"[explainer] Calling LLM to narrate verdict={verdict!r} …")
    # Use fast tier — this is a tiny, bounded call
    model = config.model_for_tier("fast")
    raw = config.call_llm(
        messages=messages,
        model=model,
        temperature=0.0,
    )

    # Clean up response
    sentence = raw.strip().strip('"').strip("'").rstrip(".")
    sentence += "."

    # Safety: if the LLM returned multiple sentences, take only the first
    if ". " in sentence:
        sentence = sentence.split(". ")[0] + "."

    return sentence
