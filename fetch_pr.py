"""
fetch_pr.py — Agentic PR fetcher: pull a real GitHub PR diff + description
and run it through the full PR Grounding Gate pipeline.

This is the AGENTIC extension point — it turns the Gate from a batch sample
tool into a live PR verifier:

    python fetch_pr.py --pr https://github.com/owner/repo/pull/123
    python fetch_pr.py --pr owner/repo#123
    python fetch_pr.py --repo tensorflow/tensorflow --number 120468

Uses `gh` CLI (already authenticated as Abhinav-143x) to fetch:
  - PR title + body  →  pr_description for the Proposer
  - PR unified diff  →  diff_text for the Gate

Then runs: Proposer → Gate → Verdict → Explainer
Saves to: runs/<repo_slug>_<number>.json
Opens:    demo_ui/index.html  (auto-regenerated)

WHERE THIS FITS IN THE AGENTIC ARCHITECTURE
============================================
The full agentic loop we're building toward:

  GitHub Webhook / gh CLI
       │
       ▼
  fetch_pr.py        ← HERE (live PR input)
       │
       ▼
  Proposer (Gemini 2.5 Flash)   ← structured claim extraction
       │
       ▼
  Evidence Gate (deterministic) ← coverage + AST + test exec
       │
       ▼
  Verdict + Explainer            ← final decision + narration
       │
       ▼
  GitHub PR comment / label      ← (next: github_commenter.py)
  Dashboard update               ← demo_ui/index.html

NEXT AGENTIC TOOLS TO ADD
==========================
  github_commenter.py  — post verdict as PR review comment via gh api
  webhook_server.py    — FastAPI server receiving GitHub PR webhook events
  batch_audit.py       — run Gate on ALL open PRs in a repo
  osv_check.py         — cross-reference CVE/OSV for the changed file
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import run_sample as runner_mod

SAMPLES_DIR = Path(__file__).parent / "samples"
RUNS_DIR    = Path(__file__).parent / "runs"


def _parse_pr_url(pr_str: str) -> tuple[str, int]:
    """
    Parse a PR reference into (owner/repo, number).
    Accepts:
      https://github.com/owner/repo/pull/123
      owner/repo#123
      owner/repo 123   (with --number)
    """
    # Full URL
    m = re.match(r"https?://github\.com/([^/]+/[^/]+)/pull/(\d+)", pr_str)
    if m:
        return m.group(1), int(m.group(2))
    # owner/repo#number
    m = re.match(r"([^/]+/[^#]+)#(\d+)", pr_str)
    if m:
        return m.group(1), int(m.group(2))
    raise ValueError(f"Cannot parse PR reference: {pr_str!r}. "
                     "Use https://github.com/owner/repo/pull/N or owner/repo#N")


def fetch_pr(repo: str, number: int, tier: str = "fast") -> dict:
    """
    Fetch a real GitHub PR diff + description via gh CLI and run the Gate.

    Parameters
    ----------
    repo   : 'owner/repo' e.g. 'tensorflow/tensorflow'
    number : PR number
    tier   : 'fast' or 'strong' for the Proposer model

    Returns
    -------
    Full result dict (same schema as run_sample)
    """
    import os
    # Ensure GITHUB_TOKEN doesn't override the keyring token
    env = {**os.environ, "GITHUB_TOKEN": ""}

    print(f"\n[fetch_pr] Fetching PR #{number} from {repo} ...")

    # ── 1. PR metadata (title + body) ────────────────────────────────────────
    meta_result = subprocess.run(
        ["gh", "pr", "view", str(number), "-R", repo, "--json", "title,body,url,state"],
        capture_output=True, text=True, env=env, encoding="utf-8", errors="replace",
    )
    if meta_result.returncode != 0:
        raise RuntimeError(f"gh pr view failed: {meta_result.stderr.strip()}")
    meta = json.loads(meta_result.stdout)

    title       = meta.get("title", "")
    body        = meta.get("body", "")
    pr_url      = meta.get("url", f"https://github.com/{repo}/pull/{number}")
    pr_state    = meta.get("state", "unknown")
    pr_description = f"{title}. {body[:2000]}".strip()

    print(f"[fetch_pr] Title: {title}")
    print(f"[fetch_pr] State: {pr_state}  URL: {pr_url}")

    # ── 2. Diff ───────────────────────────────────────────────────────────────
    diff_result = subprocess.run(
        ["gh", "pr", "diff", str(number), "-R", repo],
        capture_output=True, text=True, env=env, encoding="utf-8", errors="replace",
        timeout=60,
    )
    if diff_result.returncode != 0 or not diff_result.stdout.strip():
        raise RuntimeError(
            f"gh pr diff failed (exit {diff_result.returncode}): "
            f"{diff_result.stderr.strip()[:300]}"
        )
    diff_text = diff_result.stdout

    print(f"[fetch_pr] Diff: {len(diff_text.splitlines())} lines")

    # ── 3. Save as a sample file so run_sample.run_single() can load it ──────
    repo_slug   = repo.replace("/", "_")
    sample_name = f"live_{repo_slug}_{number}"
    diff_path   = SAMPLES_DIR / f"{sample_name}.diff"
    meta_path   = SAMPLES_DIR / f"{sample_name}.meta.json"

    diff_path.write_text(diff_text, encoding="utf-8")
    meta_obj = {
        "sample_name":    sample_name,
        "pr_description": pr_description,
        "ground_truth":   "unknown",
        "pr_url":         pr_url,
        "pr_number":      number,
        "repo":           repo,
        "state":          pr_state,
    }
    meta_path.write_text(json.dumps(meta_obj, indent=2), encoding="utf-8")
    print(f"[fetch_pr] Saved to samples/{sample_name}.diff")

    # ── 4. Run the full Gate pipeline ────────────────────────────────────────
    result = runner_mod.run_single(sample_name, tier=tier)

    # ── 5. Regenerate dashboard ───────────────────────────────────────────────
    try:
        from demo_ui.generator import generate_html
        generate_html()
    except Exception:
        pass

    return result


def main():
    parser = argparse.ArgumentParser(
        description="PR Grounding Gate — live PR fetcher via gh CLI"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pr",  help="PR URL or owner/repo#N")
    group.add_argument("--repo", help="owner/repo (pair with --number)")
    parser.add_argument("--number", type=int, help="PR number (with --repo)")
    parser.add_argument("--tier", default="fast", choices=["fast", "strong"])
    args = parser.parse_args()

    if args.pr:
        repo, number = _parse_pr_url(args.pr)
    else:
        if not args.number:
            parser.error("--number required with --repo")
        repo, number = args.repo, args.number

    fetch_pr(repo, number, tier=args.tier)


if __name__ == "__main__":
    main()
