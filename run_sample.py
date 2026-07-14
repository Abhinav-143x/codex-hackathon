"""
run_sample.py — CLI runner for PR Grounding Gate.

Usage:
    python run_sample.py --sample 1_clean_grounded
    python run_sample.py --sample 5_protobuf_ruby_real
    python run_sample.py --all

Runs: Proposer → Gate (5 parallel checks) → Verdict → Explainer
Prints: verdict + plain-English reason
Writes: runs/<sample_name>.json
Then regenerates demo_ui/index.html
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path

# ── project imports ───────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

import proposer as proposer_mod
import verdict as verdict_mod
import explainer as explainer_mod
from gate.coverage_check        import coverage_check
from gate.consistency_check     import consistency_check
from gate.test_exec_check       import test_exec_check
from gate.blind_spot_check      import blind_spot_check
from gate.invisible_unicode_check import invisible_unicode_check
from gate.unicode_sanitize      import sanitize_inputs

SAMPLES_DIR = Path(__file__).parent / "samples"
RUNS_DIR    = Path(__file__).parent / "runs"
RUNS_DIR.mkdir(exist_ok=True)

# ── ANSI colors ───────────────────────────────────────────────────────────────
_GREEN  = "\033[92m"
_RED    = "\033[91m"
_YELLOW = "\033[93m"
_BOLD   = "\033[1m"
_RESET  = "\033[0m"

VERDICT_COLORS = {
    "grounded":     _GREEN,
    "ungrounded":   _RED,
    "needs-review": _YELLOW,
    "error":        _RED,
}
VERDICT_DOTS = {
    "grounded":     "[+]",
    "ungrounded":   "[-]",
    "needs-review": "[?]",
    "error":        "[!]",
}


def _console_text(value: object) -> str:
    """Return text that can be printed by the active Windows console encoding."""
    text = str(value)
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def safe_check(check_fn, *args, check_name: str = "check", **kwargs) -> dict:
    """
    Fail-closed wrapper around all Gate check calls.
    Any exception → {"pass": False, "reason": "...error — unverified, not passed."}
    Never silently passes on error.
    """
    try:
        return check_fn(*args, **kwargs)
    except subprocess.TimeoutExpired:
        return {
            "pass": False,
            "reason": f"{check_name}: timed out — treated as unverified, not passed.",
        }
    except Exception as exc:
        return {
            "pass": False,
            "reason": (
                f"{check_name}: internal error ({type(exc).__name__}: "
                f"{str(exc)[:200]}) — treated as unverified, not passed."
            ),
        }


def _load_sample(sample_name: str) -> tuple[str, str, dict]:
    """Load the diff text, PR description, and meta for a sample. Returns (diff, desc, meta)."""
    candidate_path = Path(sample_name)
    if candidate_path.suffix == ".diff" or candidate_path.exists():
        diff_path = candidate_path
        if not diff_path.is_absolute():
            diff_path = (Path.cwd() / diff_path).resolve()
        if not diff_path.exists():
            raise FileNotFoundError(f"Diff not found: {diff_path}")

        meta_path = diff_path.with_suffix(".meta.json")
        diff_text = diff_path.read_text(encoding="utf-8")
        meta = {}
        pr_description = f"Local diff: {diff_path.name}"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            pr_description = meta.get("pr_description", pr_description)
        return diff_text, pr_description, meta

    if sample_name.startswith("https://github.com/"):
        import requests
        import re

        m = re.match(r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)", sample_name)
        if not m:
            raise ValueError(f"Invalid GitHub PR URL: {sample_name}")
        owner, repo, pr_num = m.groups()

        diff_url = f"{sample_name}.diff"
        diff_resp = requests.get(diff_url)
        diff_resp.raise_for_status()
        diff_text = diff_resp.text

        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_num}"
        api_resp = requests.get(api_url)
        meta = {"pr_url": sample_name}
        data = None
        if api_resp.status_code == 200:
            data = api_resp.json()
        else:
            try:
                gh = subprocess.run(
                    ["gh", "api", f"repos/{owner}/{repo}/pulls/{pr_num}"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    encoding="utf-8",
                    errors="replace",
                )
                if gh.returncode == 0 and gh.stdout.strip():
                    data = json.loads(gh.stdout)
            except Exception:
                data = None

        if data:
            title = data.get("title", "")
            body = data.get("body", "")
            pr_description = f"{title}\n\n{body}"
            meta.update({
                "pr_url": data.get("html_url", sample_name),
                "state": "MERGED" if data.get("merged_at") else str(data.get("state", "")).upper(),
                "title": title,
                "repo": f"{owner}/{repo}",
                "number": pr_num,
                "changed_files": data.get("changed_files"),
                "additions": data.get("additions"),
                "deletions": data.get("deletions"),
                "merged_at": data.get("merged_at"),
                "closed_at": data.get("closed_at"),
            })
        else:
            pr_description = f"GitHub PR {owner}/{repo}#{pr_num}"

        return diff_text, pr_description, meta

    diff_path = SAMPLES_DIR / f"{sample_name}.diff"
    meta_path = SAMPLES_DIR / f"{sample_name}.meta.json"

    if not diff_path.exists():
        raise FileNotFoundError(f"Diff not found: {diff_path}")

    diff_text = diff_path.read_text(encoding="utf-8")

    meta = {}
    pr_description = f"Sample: {sample_name}"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        pr_description = meta.get("pr_description", pr_description)

    return diff_text, pr_description, meta


def run_single(sample_name: str, tier: str = "fast") -> dict:
    """Run the full pipeline for one sample. Returns result dict."""
    print(f"\n{'='*60}")
    print(f"  Sample: {_BOLD}{sample_name}{_RESET}")
    print(f"{'='*60}")

    started = time.time()

    # ── 1. Load ───────────────────────────────────────────────────────────────
    diff_text, pr_description, meta = _load_sample(sample_name)
    print(f"[runner] Diff: {len(diff_text.splitlines())} lines | PR desc: {len(pr_description)} chars")

    # ── 1b. Unicode sanitization (BEFORE Proposer sees anything) ─────────────
    clean_diff, clean_desc, unicode_findings = sanitize_inputs(diff_text, pr_description)
    if unicode_findings:
        print(f"[runner] WARNING: {len(unicode_findings)} invisible Unicode chars stripped before Proposer")

    # ── 2. Proposer ───────────────────────────────────────────────────────────
    claim = proposer_mod.propose_claim(clean_diff, clean_desc, tier=tier)

    # ── 3. Gate — 5 checks in parallel (all fail-closed) ─────────────────────
    print("[runner] Running Gate checks in parallel ...")

    def _cov():
        return safe_check(coverage_check, claim, clean_diff, sample_dir=None, test_file=None,
                          check_name="coverage_check")

    def _cons():
        return safe_check(consistency_check, claim, clean_diff, pr_description=clean_desc,
                          check_name="consistency_check")

    def _tex():
        return safe_check(test_exec_check, claim, clean_diff, sample_name=sample_name,
                          check_name="test_exec_check")

    def _blind():
        return safe_check(blind_spot_check, diff_text,  # use ORIGINAL diff for image detection
                          check_name="blind_spot_check")

    def _uni():
        # If we found unicode, we already know the result — pass the findings in
        if unicode_findings:
            cats = {}
            for f in unicode_findings:
                cat = f.get("category", "unknown")
                cats[cat] = cats.get(cat, 0) + 1
            summary = ", ".join(f"{v}x {k}" for k, v in cats.items())
            cps = [f["codepoint"] for f in unicode_findings[:5]]
            return {
                "pass": False,
                "reason": (
                    f"invisible_unicode_check: {len(unicode_findings)} invisible Unicode "
                    f"character(s) detected ({summary}). Codepoints: {cps}. "
                    "Stripped before Proposer — flagging fail-closed."
                ),
            }
        return safe_check(invisible_unicode_check, diff_text, pr_description,
                          check_name="invisible_unicode_check")

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        fut_cov   = pool.submit(_cov)
        fut_cons  = pool.submit(_cons)
        fut_tex   = pool.submit(_tex)
        fut_blind = pool.submit(_blind)
        fut_uni   = pool.submit(_uni)
        cov_result   = fut_cov.result()
        cons_result  = fut_cons.result()
        tex_result   = fut_tex.result()
        blind_result = fut_blind.result()
        uni_result   = fut_uni.result()

    print(f"  coverage         : {'PASS' if cov_result['pass']   else 'FAIL'}")
    print(f"  consistency      : {'PASS' if cons_result['pass']  else 'FAIL'}")
    print(f"  test_exec        : {'PASS' if tex_result['pass']   else 'FAIL'}")
    print(f"  blind_spot       : {'PASS' if blind_result['pass'] else 'FAIL'}")
    print(f"  invisible_unicode: {'PASS' if uni_result['pass']   else 'FAIL'}")

    # ── 4. Verdict ────────────────────────────────────────────────────────────
    verdict_data = verdict_mod.compute_verdict(
        cov_result, cons_result, tex_result,
        claim=claim,
        sample_name=sample_name,
        blind_spot_result=blind_result,
        unicode_result=uni_result,
    )
    verdict = verdict_data["verdict"]

    # ── 5. Explainer ─────────────────────────────────────────────────────────
    explanation = explainer_mod.explain_verdict(verdict_data, claim=claim)

    elapsed = time.time() - started

    # ── 6. Print verdict ──────────────────────────────────────────────────────
    color = VERDICT_COLORS.get(verdict, _RESET)
    dot   = VERDICT_DOTS.get(verdict, "[?]")
    print(f"\n  {color}{dot} VERDICT: {verdict.upper()}{_RESET}")
    print(f"  {_BOLD}Explanation:{_RESET} {_console_text(explanation)}")
    if verdict_data["failing_checks"]:
        print(f"  Failing: {', '.join(verdict_data['failing_checks'])}")
        for r in verdict_data["reasons"]:
            print(f"    - {_console_text(r[:200])}")
    print(f"  [{elapsed:.1f}s]")

    # Safely convert URL to a valid filename if it's a URL
    safe_name = sample_name
    if safe_name.startswith("http"):
        safe_name = safe_name.split("/")[-3] + "_" + safe_name.split("/")[-1]
    elif Path(safe_name).suffix:
        safe_name = Path(safe_name).stem
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", safe_name)

    result = {
        "sample_name":    safe_name,
        "run_timestamp":  datetime.now(timezone.utc).isoformat(),
        "elapsed_s":      round(elapsed, 2),
        "pr_url":         meta.get("pr_url", ""),
        "state":          meta.get("state", ""),
        "pr_description": pr_description,
        "claim":          claim,
        "diff_text":      diff_text,
        "gate": {
            "coverage":         cov_result,
            "consistency":      cons_result,
            "test_exec":        tex_result,
            "blind_spot":       blind_result,
            "invisible_unicode": uni_result,
        },
        "verdict":     verdict_data,
        "explanation": explanation,
    }

    run_path = RUNS_DIR / f"{safe_name}.json"
    run_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"  -> Saved: {run_path}")

    return result


def _list_samples() -> list[str]:
    """Return sorted list of sample names from /samples/."""
    return sorted(p.stem for p in SAMPLES_DIR.glob("*.diff"))


def main():
    parser = argparse.ArgumentParser(
        description="PR Grounding Gate — run samples through Proposer → Gate → Verdict → Explainer"
    )
    parser.add_argument("--sample", help="Sample name (e.g. 1_clean_grounded)")
    parser.add_argument("--pr",     help="GitHub PR URL")
    parser.add_argument("--all",    action="store_true", help="Run all samples")
    parser.add_argument("--tier",   default="fast", choices=["fast", "strong"],
                        help="Proposer model tier (default: fast)")
    args = parser.parse_args()

    if not args.sample and not args.pr and not args.all:
        parser.print_help()
        print("\nAvailable samples:")
        for s in _list_samples():
            print(f"  {s}")
        sys.exit(0)

    if args.pr:
        samples = [args.pr]
    elif args.all:
        samples = _list_samples()
    else:
        samples = [args.sample]

    results = []

    for name in samples:
        try:
            r = run_single(name, tier=args.tier)
            results.append(r)
        except FileNotFoundError as e:
            print(f"\n[ERROR] {e}")
            sys.exit(1)

    # ── regenerate UI ─────────────────────────────────────────────────────────
    try:
        from demo_ui.generator import generate_html
        generate_html()
        print(f"\n[runner] demo_ui/index.html regenerated.")
    except Exception as exc:
        print(f"\n[runner] Warning: UI generation failed: {exc}")

    # Also export Vite data
    try:
        import export_runs
        export_runs  # triggers top-level export if structured as script
    except Exception:
        pass

    # ── summary ───────────────────────────────────────────────────────────────
    if len(results) > 1:
        print(f"\n{'='*60}")
        print("  SUMMARY")
        print(f"{'='*60}")
        for r in results:
            v = r["verdict"]["verdict"]
            color = VERDICT_COLORS.get(v, _RESET)
            dot = VERDICT_DOTS.get(v, "[?]")
            print(f"  {color}{dot} {r['sample_name']:35s} -> {v.upper()}{_RESET}")
        grounded   = sum(1 for r in results if r["verdict"]["verdict"] == "grounded")
        ungrounded = sum(1 for r in results if r["verdict"]["verdict"] == "ungrounded")
        review     = sum(1 for r in results if r["verdict"]["verdict"] == "needs-review")
        errors     = sum(1 for r in results if r["verdict"]["verdict"] == "error")
        print(
            f"\n  {_GREEN}Grounded: {grounded}{_RESET}  "
            f"{_RED}Ungrounded: {ungrounded}{_RESET}  "
            f"{_YELLOW}Needs-review: {review}{_RESET}  "
            f"{_RED}Errors: {errors}{_RESET}"
        )


if __name__ == "__main__":
    main()
