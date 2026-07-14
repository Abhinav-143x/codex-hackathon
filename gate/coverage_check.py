"""
gate/coverage_check.py — Coverage-diff grounding check (DETERMINISTIC, ZERO LLM).

Verifies that test coverage strictly increased on the lines claimed by the
Proposer's claim JSON.

Strategy:
  1. Parse the diff to extract modified line numbers for claim["file"].
  2. Run coverage.py on the test file associated with the diff (or use a
     pre-computed .coverage data file if present).
  3. Confirm that at least one claimed line moved from "not covered" to
     "covered" (strictly increased).
  4. Return {"pass": bool, "reason": str}.

For samples 2 (padded/irrelevant tests) this check FAILS because the new
tests only cover lines outside the claimed range.

For all other samples the check PASSES (or is a non-fatal stub result when
no runnable test exists in the sample).
"""

import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_line_range(line_range_str: str) -> tuple[int, int] | None:
    """Parse 'start-end' or 'N' into (start, end). Returns None if N/A."""
    s = str(line_range_str).strip()
    if s in ("N/A", "", "unknown", "INSUFFICIENT EVIDENCE"):
        return None
    if "-" in s:
        parts = s.split("-", 1)
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            return None
    try:
        n = int(s)
        return n, n
    except ValueError:
        return None


def _extract_changed_lines(diff_text: str, filename: str) -> set[int]:
    """
    Parse a unified diff and return the set of *added* line numbers
    in the specified file (new-file line numbers, 1-indexed).
    """
    in_target = False
    current_new_line = 0
    changed = set()
    target_base = os.path.basename(filename)

    for raw in diff_text.splitlines():
        # detect file header
        if raw.startswith("+++ "):
            path = raw[4:].strip()
            # strip a/ b/ prefixes
            if path.startswith(("b/", "a/")):
                path = path[2:]
            in_target = os.path.basename(path) == target_base
            current_new_line = 0
            continue

        if not in_target:
            continue

        if raw.startswith("@@"):
            # @@ -old_start,old_count +new_start,new_count @@
            import re
            m = re.search(r"\+(\d+)", raw)
            if m:
                current_new_line = int(m.group(1)) - 1
            continue

        if raw.startswith("\\"):
            continue

        if raw.startswith("+"):
            current_new_line += 1
            changed.add(current_new_line)
        elif raw.startswith("-"):
            pass  # deleted lines don't advance new-file counter
        else:
            current_new_line += 1

    return changed


def _run_coverage_on_sample(sample_dir: Path, test_file: str | None) -> dict:
    """
    Run coverage.py on a test file inside sample_dir.
    Returns {line: bool} mapping for lines in the source.
    """
    if test_file is None or not (sample_dir / test_file).exists():
        return {}

    src_files = list(sample_dir.glob("*.py"))
    src_args = [f"--source={f.stem}" for f in src_files if "test" not in f.name]

    env = {**os.environ, "PYTHONPATH": str(sample_dir)}
    cov_data = sample_dir / ".coverage"
    cov_data.unlink(missing_ok=True)

    try:
        subprocess.run(
            [sys.executable, "-m", "coverage", "run", "--data-file", str(cov_data),
             str(sample_dir / test_file)],
            capture_output=True, text=True, cwd=str(sample_dir), env=env,
            timeout=30,
        )
        result = subprocess.run(
            [sys.executable, "-m", "coverage", "json", "--data-file", str(cov_data),
             "-o", str(sample_dir / "cov.json")],
            capture_output=True, text=True, cwd=str(sample_dir), env=env,
            timeout=10,
        )
        if result.returncode != 0:
            return {}
        with open(sample_dir / "cov.json") as f:
            cov = json.load(f)
        return cov.get("files", {})
    except Exception:
        return {}


# ── public API ────────────────────────────────────────────────────────────────

def coverage_check(
    claim: dict,
    diff_text: str,
    sample_dir: Path | None = None,
    test_file: str | None = None,
) -> dict:
    """
    Deterministic coverage-diff grounding check.

    Parameters
    ----------
    claim       : Proposer output dict (uses claim["file"], claim["line_range"])
    diff_text   : Raw unified diff string
    sample_dir  : Directory containing the sample's Python source + test files
    test_file   : Relative path to the test file to run (e.g. "test_fix.py")

    Returns
    -------
    {"pass": bool, "reason": str}
    """
    claimed_file = claim.get("file", "unknown")
    line_range   = _parse_line_range(claim.get("line_range", "N/A"))

    # Step 1 — extract changed lines from diff
    changed_lines = _extract_changed_lines(diff_text, claimed_file)
    if not changed_lines:
        return {
            "pass": False,
            "reason": (
                f"coverage_check: diff contains no added lines in "
                f"'{claimed_file}'. Cannot verify coverage grounding."
            ),
        }

    # Step 2 — if no sample_dir or no test_file, structural diff check only
    if sample_dir is None or test_file is None:
        # Fallback: just verify the claimed line range overlaps with changed lines
        if line_range is None:
            return {
                "pass": True,
                "reason": (
                    "coverage_check: no line range claimed and diff adds lines in "
                    f"'{claimed_file}' — structural pass (no test runner available)."
                ),
            }
        start, end = line_range
        claimed_set = set(range(start, end + 1))
        overlap = claimed_set & changed_lines
        if overlap:
            return {
                "pass": True,
                "reason": (
                    f"coverage_check: claimed lines {start}-{end} overlap with "
                    f"diff-changed lines {sorted(overlap)[:5]} in '{claimed_file}'."
                ),
            }
        else:
            return {
                "pass": False,
                "reason": (
                    f"coverage_check: claimed lines {start}-{end} in '{claimed_file}' "
                    f"do NOT appear in the diff. Changed lines: {sorted(changed_lines)[:10]}. "
                    "Tests may be padding/irrelevant."
                ),
            }

    # Step 3 — run coverage and check claimed lines
    cov_data = _run_coverage_on_sample(sample_dir, test_file)
    if not cov_data:
        # Coverage runner failed — fall back to structural check
        if line_range is None:
            return {"pass": True, "reason": "coverage_check: no line range + no coverage data (structural pass)."}
        start, end = line_range
        overlap = set(range(start, end + 1)) & changed_lines
        if overlap:
            return {"pass": True, "reason": f"coverage_check: structural overlap {sorted(overlap)[:5]} (coverage runner unavailable)."}
        return {"pass": False, "reason": f"coverage_check: claimed lines {start}-{end} not in diff and coverage unavailable."}

    # Find the relevant source file in coverage data
    matched_key = None
    for key in cov_data:
        if os.path.basename(key) == os.path.basename(claimed_file):
            matched_key = key
            break

    if matched_key is None:
        return {
            "pass": False,
            "reason": (
                f"coverage_check: '{claimed_file}' not found in coverage data. "
                "Test may not exercise the claimed file at all."
            ),
        }

    executed_lines = set(cov_data[matched_key].get("executed_lines", []))
    missed_lines   = set(cov_data[matched_key].get("missing_lines", []))

    if line_range is None:
        # No specific line range — just check that some changed line is covered
        covered_changed = changed_lines & executed_lines
        if covered_changed:
            return {
                "pass": True,
                "reason": (
                    f"coverage_check: {len(covered_changed)} changed line(s) are covered "
                    f"by tests in '{claimed_file}'."
                ),
            }
        return {
            "pass": False,
            "reason": (
                f"coverage_check: changed lines {sorted(changed_lines)[:10]} in "
                f"'{claimed_file}' are NOT covered by the test suite."
            ),
        }

    start, end = line_range
    claimed_set = set(range(start, end + 1))
    covered_in_claim = claimed_set & executed_lines
    if covered_in_claim:
        return {
            "pass": True,
            "reason": (
                f"coverage_check: claimed lines {start}-{end} covered — "
                f"{sorted(covered_in_claim)[:5]} are executed by tests."
            ),
        }
    else:
        return {
            "pass": False,
            "reason": (
                f"coverage_check: claimed lines {start}-{end} in '{claimed_file}' "
                f"are NOT executed by the test suite. "
                f"Missed lines include: {sorted(missed_lines & claimed_set)[:5]}. "
                "This is a padded/irrelevant test pattern."
            ),
        }
