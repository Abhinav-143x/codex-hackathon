"""
github_commenter.py — FORMAT verdict as a GitHub PR review comment (DRY-RUN ONLY).

⚠️  THIS TOOL NEVER POSTS TO GITHUB BY DEFAULT.
    It only prints what a comment would look like. No network calls to GitHub.
    All gh API/label/review calls are suppressed.

Usage:
    python github_commenter.py --repo tensorflow/tensorflow --number 120468
    python github_commenter.py --pr https://github.com/npm/cli/pull/9473

Output: formatted markdown to stdout ONLY. Nothing is sent to GitHub.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

RUNS_DIR = Path(__file__).parent / "runs"

VERDICT_EMOJI = {
    "grounded":     "✅",
    "ungrounded":   "❌",
    "needs-review": "⚠️",
}

LABEL_COLORS = {
    "grounded":     "22c55e",
    "ungrounded":   "ef4444",
    "needs-review": "f59e0b",
}


def _format_comment(run: dict) -> str:
    """Build the PR comment markdown body."""
    verdict   = run["verdict"]["verdict"]
    emoji     = VERDICT_EMOJI.get(verdict, "❓")
    explain   = run.get("explanation", "")
    sample    = run.get("sample_name", "unknown")
    gate      = run.get("gate", {})
    failing   = run["verdict"].get("failing_checks", [])

    cov  = gate.get("coverage",    {})
    cons = gate.get("consistency", {})
    tex  = gate.get("test_exec",   {})

    def _check_row(name, result):
        icon = "✅" if result.get("pass") else "❌"
        reason = result.get("reason", "")[:180]
        return f"| {icon} `{name}` | {reason} |"

    rows = "\n".join([
        _check_row("coverage_check",    cov),
        _check_row("consistency_check", cons),
        _check_row("test_exec_check",   tex),
    ])

    claim = run.get("claim", {})
    claim_file  = claim.get("file", "unknown")
    claim_range = claim.get("line_range", "N/A")
    claim_conf  = claim.get("confidence", 0)

    comment = f"""\
## {emoji} PR Grounding Gate — `{verdict.upper()}`

> {explain}

### Proposer claim
| Field | Value |
|-------|-------|
| File  | `{claim_file}` |
| Lines | `{claim_range}` |
| Confidence | `{claim_conf:.0%}` |

### Gate checks
| Check | Result |
|-------|--------|
{rows}

---
<sub>🤖 PR Grounding Gate · deterministic claim verification · [source](https://github.com/Abhinav-143x/codex-hackathon)</sub>
"""
    return comment.strip()


def post_verdict(repo: str, number: int, run: dict, block_if_ungrounded: bool = False):
    """Print the formatted verdict comment to stdout. NEVER posts to GitHub."""
    comment_body = _format_comment(run)
    verdict = run["verdict"]["verdict"]

    print("\n" + "=" * 70)
    print(f"  DRY-RUN: Gate verdict for {repo}#{number}")
    print("=" * 70)
    print(comment_body)
    print("=" * 70)
    print("[commenter] DRY-RUN mode — nothing posted to GitHub.")
    print(f"[commenter] Verdict: {verdict.upper()}")



def _find_run(repo: str, number: int) -> dict | None:
    """Find the most recent run JSON for this repo/number."""
    repo_slug = repo.replace("/", "_")
    # Check live sample name first
    live_path = RUNS_DIR / f"live_{repo_slug}_{number}.json"
    if live_path.exists():
        return json.loads(live_path.read_text())
    # Fall back to searching all runs
    for p in sorted(RUNS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        run = json.loads(p.read_text())
        if str(number) in run.get("sample_name", ""):
            return run
    return None


def main():
    parser = argparse.ArgumentParser(
        description="PR Grounding Gate — post verdict as GitHub PR comment"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pr",   help="PR URL or owner/repo#N")
    group.add_argument("--repo", help="owner/repo")
    parser.add_argument("--number", type=int)
    parser.add_argument("--block", action="store_true",
                        help="Request changes on ungrounded PRs")
    args = parser.parse_args()

    if args.pr:
        m = re.match(r"https?://github\.com/([^/]+/[^/]+)/pull/(\d+)", args.pr)
        if m:
            repo, number = m.group(1), int(m.group(2))
        else:
            m2 = re.match(r"([^#]+)#(\d+)", args.pr)
            if m2:
                repo, number = m2.group(1), int(m2.group(2))
            else:
                print(f"Cannot parse: {args.pr}")
                sys.exit(1)
    else:
        repo, number = args.repo, args.number

    run = _find_run(repo, number)
    if not run:
        print(f"No run found for {repo}#{number}. Run fetch_pr.py first.")
        sys.exit(1)

    post_verdict(repo, number, run, block_if_ungrounded=args.block)


if __name__ == "__main__":
    main()
