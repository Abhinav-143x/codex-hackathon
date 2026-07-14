"""
verdict.py — Combines all Gate checks into a final verdict.

Rules:
  - ALL checks pass  → "grounded"
  - Contradictory evidence → "ungrounded"
  - Incomplete/review-needed evidence → "needs-review"
  - Any check errored (internal exception) → "error" (distinct from needs-review)

The verdict is ALWAYS accompanied by specific reasons, never a black-box score.
"""

from __future__ import annotations

import re


SECURITY_SIGNAL_TERMS = {
    "ATTACK",
    "ATTACKER",
    "BYPASS",
    "CVE",
    "CWE",
    "EXPLOIT",
    "INJECTION",
    "LEAK",
    "MALICIOUS",
    "OOB",
    "OUT_OF_BOUNDS",
    "OVERFLOW",
    "PRIVILEGE",
    "RCE",
    "SECRET",
    "SECURITY",
    "SSRF",
    "TRAVERSAL",
    "UNAUTHORIZED",
    "VALIDATION",
    "VULNERABILITY",
    "XSS",
}


def _claim_has_security_signal(claim: dict, bug_type: str) -> bool:
    if bug_type.startswith(("CVE", "CWE")):
        return True

    combined = " ".join(
        str(claim.get(field, ""))
        for field in ["bug_type", "description", "w_why", "w_impact", "w_who"]
    ).upper()

    tokens = set(re.findall(r"[A-Z0-9_]+", combined.replace("-", "_")))
    return any(term in tokens for term in SECURITY_SIGNAL_TERMS)


def compute_verdict(
    coverage_result: dict,
    consistency_result: dict,
    test_exec_result: dict,
    claim: dict = None,
    sample_name: str = "",
    blind_spot_result: dict = None,
    unicode_result: dict = None,
) -> dict:
    """
    Combine Gate check results into a final verdict.

    Parameters
    ----------
    coverage_result     : {"pass": bool, "reason": str}
    consistency_result  : {"pass": bool, "reason": str}
    test_exec_result    : {"pass": bool, "reason": str}
    claim               : Proposer claim dict (for 5W + escalation checks)
    sample_name         : sample identifier
    blind_spot_result   : optional {"pass": bool, "reason": str}
    unicode_result      : optional {"pass": bool, "reason": str}

    Returns
    -------
    {
      "verdict": "grounded" | "ungrounded" | "needs-review" | "error",
      "checks": {check_name: {"pass": bool, "reason": str}, ...},
      "failing_checks": [str],
      "reasons": [str],
    }
    """
    cov_pass  = coverage_result.get("pass", False)
    cons_pass = consistency_result.get("pass", False)
    tex_pass  = test_exec_result.get("pass", False)
    blind_pass = (blind_spot_result or {}).get("pass", True)
    uni_pass   = (unicode_result or {}).get("pass", True)

    test_reason = test_exec_result.get("reason", "").lower()
    is_unverified_test = (
        "stub pass" in test_reason
        or "no repo-specific test runner" in test_reason
        or "non-authoritative placeholder" in test_reason
    )
    has_error = any(
        "internal error" in r.get("reason", "").lower() or "timed out" in r.get("reason", "").lower()
        for r in [coverage_result, consistency_result, test_exec_result,
                  blind_spot_result or {}, unicode_result or {}]
    )

    failing = []
    reasons = []

    if not cov_pass:
        failing.append("coverage")
        reasons.append(coverage_result.get("reason", "coverage_check failed."))

    if not cons_pass:
        failing.append("consistency")
        reasons.append(consistency_result.get("reason", "consistency_check failed."))

    if not tex_pass:
        failing.append("test_exec")
        reasons.append(test_exec_result.get("reason", "test_exec_check failed."))
    elif is_unverified_test:
        failing.append("test_exec")
        reasons.append(
            test_exec_result.get(
                "reason",
                "test_exec_check did not run adopted repo tests; real local test execution was not verified.",
            )
        )

    if not blind_pass and blind_spot_result:
        failing.append("blind_spot")
        reasons.append(blind_spot_result.get("reason", "blind_spot_check failed."))

    if not uni_pass and unicode_result:
        failing.append("invisible_unicode")
        reasons.append(unicode_result.get("reason", "invisible_unicode_check failed."))

    # Check 5W fields for INSUFFICIENT EVIDENCE
    insufficient_fields = []
    bug_type = ""
    if claim:
        bug_type = claim.get("bug_type", "").upper()
        for field in ["w_what", "w_why", "w_impact", "w_evidence", "w_who"]:
            val = claim.get(field, "")
            if isinstance(val, str) and "INSUFFICIENT EVIDENCE" in val.upper():
                insufficient_fields.append(field)

    if insufficient_fields:
        failing.append("5w_evidence")
        reasons.append(f"Proposer found INSUFFICIENT EVIDENCE for: {', '.join(insufficient_fields)}.")

    # Check if Proposer flagged a security-sensitive risk. Custom bug_type
    # labels alone are not enough; the claim must contain vulnerability signals.
    is_escalation_flagged = False
    if claim and bug_type and _claim_has_security_signal(claim, bug_type):
        is_escalation_flagged = True
        failing.append("proposer_escalation")
        reasons.append(
            f"Proposer self-reported a risk category ({bug_type}). This is the "
            f"Proposer's own claim, NOT independently verified by the Gate — "
            f"routed to human review as a precaution, not a confirmed finding."
        )

    # --- Verdict logic ---
    if has_error and failing:
        verdict = "error"
    elif not failing:
        verdict = "grounded"
    else:
        contradictory_failures = set()
        if "coverage" in failing:
            contradictory_failures.add("coverage")
        if "consistency" in failing:
            contradictory_failures.add("consistency")
        if "test_exec" in failing and not is_unverified_test and not tex_pass:
            contradictory_failures.add("test_exec")

        verdict = "ungrounded" if contradictory_failures else "needs-review"

    # Build checks dict
    checks: dict = {
        "coverage":    coverage_result,
        "consistency": consistency_result,
        "test_exec":   test_exec_result,
        "5w_evidence": {
            "pass": len(insufficient_fields) == 0,
            "reason": (
                f"Proposer found INSUFFICIENT EVIDENCE for: {', '.join(insufficient_fields)}."
                if insufficient_fields
                else "All 5W fields were sufficiently answered by the LLM."
            ),
        },
        "proposer_escalation": {
            "pass": not is_escalation_flagged,
            "reason": (
                f"Proposer self-reported a risk category ({bug_type}). This is the "
                f"Proposer's own claim, NOT independently verified by the Gate — "
                f"routed to human review as a precaution, not a confirmed finding."
            ) if is_escalation_flagged else "No vulnerability detected by Proposer.",
        },
    }

    if blind_spot_result is not None:
        checks["blind_spot"] = blind_spot_result

    if unicode_result is not None:
        checks["invisible_unicode"] = unicode_result

    return {
        "verdict": verdict,
        "checks": checks,
        "failing_checks": failing,
        "reasons": reasons if reasons else ["All checks passed."],
    }
