from pathlib import Path

import verdict
from gate.blind_spot_check import blind_spot_check
from gate.invisible_unicode_check import invisible_unicode_check
from run_sample import _load_sample


def test_stub_test_exec_routes_to_needs_review():
    result = verdict.compute_verdict(
        {"pass": True, "reason": "coverage ok"},
        {"pass": True, "reason": "consistency ok"},
        {"pass": True, "reason": "test_exec_check: stub pass for Python sample"},
        claim={"bug_type": "FIX"},
    )

    assert result["verdict"] == "needs-review"
    assert "test_exec" in result["failing_checks"]


def test_unadopted_test_exec_routes_to_needs_review():
    result = verdict.compute_verdict(
        {"pass": True, "reason": "coverage ok"},
        {"pass": True, "reason": "consistency ok"},
        {
            "pass": True,
            "reason": "test_exec_check: no repo-specific test runner is adopted for sample.diff. This check is a non-authoritative placeholder pass.",
        },
        claim={"bug_type": "FIX"},
    )

    assert result["verdict"] == "needs-review"
    assert "test_exec" in result["failing_checks"]


def test_ruby_mock_test_exec_routes_to_needs_review():
    result = verdict.compute_verdict(
        {"pass": True, "reason": "coverage ok"},
        {"pass": True, "reason": "consistency ok"},
        {
            "pass": True,
            "reason": "test_exec_check [RUBY/mock]: stub pass via Python verification harness",
        },
        claim={"bug_type": "FIX"},
    )

    assert result["verdict"] == "needs-review"
    assert "test_exec" in result["failing_checks"]


def test_stub_test_exec_with_security_signal_routes_to_needs_review():
    result = verdict.compute_verdict(
        {"pass": True, "reason": "coverage ok"},
        {"pass": True, "reason": "consistency ok"},
        {"pass": True, "reason": "test_exec_check: stub pass for Python sample"},
        claim={
            "bug_type": "LOGIC_ERROR",
            "w_impact": "An attacker can bypass the registry path validation.",
        },
    )

    assert result["verdict"] == "needs-review"
    assert result["failing_checks"] == ["test_exec", "proposer_escalation"]


def test_custom_non_security_bug_type_does_not_escalate():
    result = verdict.compute_verdict(
        {"pass": True, "reason": "coverage ok"},
        {"pass": True, "reason": "consistency ok"},
        {"pass": True, "reason": "test_exec_check: stub pass for Python sample"},
        claim={"bug_type": "MISSING_METADATA", "description": "Adds project links."},
    )

    assert result["verdict"] == "needs-review"
    assert result["failing_checks"] == ["test_exec"]
    assert result["checks"]["proposer_escalation"]["pass"] is True


def test_blind_spot_flags_binary_diff():
    result = blind_spot_check("Binary files a/image.png and b/image.png differ")

    assert result["pass"] is False


def test_invisible_unicode_flags_zero_width():
    result = invisible_unicode_check("print('x')\u200b", "")

    assert result["pass"] is False


def test_load_sample_accepts_local_diff_path():
    diff, description, meta = _load_sample(str(Path("samples") / "1_clean_grounded.diff"))

    assert "--- a/" in diff
    assert "safe_divide" in diff
    assert description
    assert isinstance(meta, dict)
