"""
benchmark/cve_adapter.py — Adapter to run PR Grounding Gate against OpenSSF CVE Benchmark samples.

Maps the benchmark's question ("detect vulnerability in vulnerable commit") to our question
("is this PR's claimed fix grounded in its diff?") by treating each CVE's patch commit as
an incoming claimed-fix PR.

Methodology:
  - grounded  → detected/confirmed (Gate verified the fix is real)
  - ungrounded/needs-review → not confirmed (Gate couldn't verify the fix claim)

Run: python benchmark/cve_adapter.py
Output: benchmark/results.csv + benchmark/results.md
"""

from __future__ import annotations

import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add parent to path for project imports
sys.path.insert(0, str(Path(__file__).parent.parent))

SAMPLES_DIR = Path(__file__).parent / "cve_samples"
RESULTS_DIR = Path(__file__).parent
RESULTS_CSV  = RESULTS_DIR / "results.csv"
RESULTS_MD   = RESULTS_DIR / "results.md"


def run_cve_sample(cve_id: str, diff_text: str, pr_description: str) -> dict:
    """
    Run Proposer → Gate → Verdict on one CVE patch diff.
    Returns a result dict with verdict and per-check details.
    """
    import proposer as proposer_mod
    import verdict as verdict_mod
    from gate.coverage_check import coverage_check
    from gate.consistency_check import consistency_check
    from gate.test_exec_check import test_exec_check
    from gate.blind_spot_check import blind_spot_check
    from gate.invisible_unicode_check import invisible_unicode_check
    from gate.unicode_sanitize import sanitize_inputs
    from run_sample import safe_check
    import concurrent.futures

    # Sanitize inputs
    clean_diff, clean_desc, _ = sanitize_inputs(diff_text, pr_description)

    # Proposer
    try:
        claim = proposer_mod.propose_claim(clean_diff, clean_desc, tier="fast")
    except Exception as exc:
        return {
            "cve_id": cve_id,
            "verdict": "error",
            "error": str(exc)[:200],
            "gate_checks": {},
        }

    # Gate checks in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        f_cov   = pool.submit(safe_check, coverage_check, claim, clean_diff, check_name="coverage_check")
        f_cons  = pool.submit(safe_check, consistency_check, claim, clean_diff, clean_desc, check_name="consistency_check")
        f_tex   = pool.submit(safe_check, test_exec_check, claim, clean_diff, check_name="test_exec_check")
        f_blind = pool.submit(safe_check, blind_spot_check, diff_text, check_name="blind_spot_check")
        f_uni   = pool.submit(safe_check, invisible_unicode_check, diff_text, pr_description, check_name="unicode_check")

        cov_r  = f_cov.result()
        cons_r = f_cons.result()
        tex_r  = f_tex.result()
        blind_r = f_blind.result()
        uni_r  = f_uni.result()

    verdict_data = verdict_mod.compute_verdict(
        cov_r, cons_r, tex_r,
        claim=claim,
        sample_name=f"cve_{cve_id}",
        blind_spot_result=blind_r,
        unicode_result=uni_r,
    )

    # Map to benchmark question:
    # grounded → fix claim is verified → benchmark: correctly confirmed the fix
    # ungrounded/needs-review → fix claim not verified → benchmark: not confirmed
    bench_result = "confirmed" if verdict_data["verdict"] == "grounded" else "not_confirmed"

    return {
        "cve_id": cve_id,
        "verdict": verdict_data["verdict"],
        "bench_result": bench_result,
        "failing_checks": verdict_data.get("failing_checks", []),
        "gate_checks": {
            k: v.get("pass") for k, v in verdict_data.get("checks", {}).items()
        },
        "claim_bug_type": claim.get("bug_type", ""),
    }


def load_cve_samples() -> list[dict]:
    """Load all CVE samples from benchmark/cve_samples/."""
    samples = []
    if not SAMPLES_DIR.exists():
        print(f"[benchmark] No samples dir found at {SAMPLES_DIR}")
        print("[benchmark] Create benchmark/cve_samples/<cve_id>.diff + <cve_id>.meta.json files")
        return []

    for diff_file in sorted(SAMPLES_DIR.glob("*.diff")):
        cve_id = diff_file.stem
        meta_file = SAMPLES_DIR / f"{cve_id}.meta.json"

        diff_text = diff_file.read_text(encoding="utf-8", errors="replace")
        pr_description = f"Fix for {cve_id}"
        ground_truth = None

        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text())
                pr_description = meta.get("pr_description", pr_description)
                ground_truth = meta.get("ground_truth")  # "grounded" or "ungrounded"
            except Exception:
                pass

        samples.append({
            "cve_id": cve_id,
            "diff_text": diff_text,
            "pr_description": pr_description,
            "ground_truth": ground_truth,
        })

    return samples


def write_results(results: list[dict], ground_truths: dict) -> None:
    """Write per-CVE results to CSV and Markdown."""
    # CSV
    fieldnames = ["cve_id", "verdict", "bench_result", "failing_checks", "claim_bug_type",
                  "coverage", "consistency", "test_exec", "blind_spot", "invisible_unicode",
                  "ground_truth", "correct"]
    rows = []
    tp = fp = tn = fn = 0  # true/false positives/negatives

    for r in results:
        gt = ground_truths.get(r["cve_id"])
        predicted = r.get("bench_result", "not_confirmed")
        correct = None
        if gt:
            correct = (predicted == gt)
            if gt == "confirmed" and correct: tp += 1
            elif gt == "confirmed" and not correct: fn += 1
            elif gt == "not_confirmed" and correct: tn += 1
            elif gt == "not_confirmed" and not correct: fp += 1

        rows.append({
            "cve_id": r["cve_id"],
            "verdict": r.get("verdict", ""),
            "bench_result": predicted,
            "failing_checks": ",".join(r.get("failing_checks", [])),
            "claim_bug_type": r.get("claim_bug_type", ""),
            "coverage":    r.get("gate_checks", {}).get("coverage", ""),
            "consistency": r.get("gate_checks", {}).get("consistency", ""),
            "test_exec":   r.get("gate_checks", {}).get("test_exec", ""),
            "blind_spot":  r.get("gate_checks", {}).get("blind_spot", ""),
            "invisible_unicode": r.get("gate_checks", {}).get("invisible_unicode", ""),
            "ground_truth": gt or "",
            "correct": correct if correct is not None else "",
        })

    with RESULTS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Markdown
    total = len(results)
    with_gt = tp + fp + tn + fn
    accuracy = (tp + tn) / max(with_gt, 1)
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 0.0001)

    lines = [
        "# PR Grounding Gate — CVE Benchmark Results",
        f"\n**Run date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        f"**Total CVEs evaluated:** {total}",
        f"**With ground truth:** {with_gt}",
        "",
        "## Summary (CVEs with ground truth)",
        f"| Metric | Score |",
        f"|--------|-------|",
        f"| Accuracy | {accuracy:.1%} |",
        f"| Precision | {precision:.1%} |",
        f"| Recall (sensitivity) | {recall:.1%} |",
        f"| F1 | {f1:.1%} |",
        f"| True positives | {tp} |",
        f"| False positives | {fp} |",
        f"| True negatives | {tn} |",
        f"| False negatives | {fn} |",
        "",
        "> **Methodology:** Each CVE's patch commit diff + description is treated as an incoming",
        "> claimed-fix PR. `grounded` verdict = fix claim verified (confirmed). All other verdicts",
        "> = not confirmed. Mapping stated explicitly — not a forced fit.",
        "",
        "## Per-CVE Results",
        "",
        "| CVE ID | Verdict | Bench Result | Failing Checks | Ground Truth | Correct |",
        "|--------|---------|-------------|----------------|--------------|---------|",
    ]

    for row in rows:
        correct_str = "✓" if row["correct"] is True else ("✗" if row["correct"] is False else "—")
        lines.append(
            f"| {row['cve_id']} | {row['verdict']} | {row['bench_result']} "
            f"| {row['failing_checks'] or '—'} | {row['ground_truth'] or '—'} | {correct_str} |"
        )

    lines += [
        "",
        "---",
        "*Full per-check data in [results.csv](results.csv).*",
        "*Raw results are published alongside this summary — not just the headline score.*",
    ]

    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"[benchmark] Written: {RESULTS_CSV}")
    print(f"[benchmark] Written: {RESULTS_MD}")


def main():
    print("[benchmark] Loading CVE samples ...")
    samples = load_cve_samples()
    if not samples:
        sys.exit(0)

    print(f"[benchmark] Running {len(samples)} CVE samples through Proposer → Gate → Verdict ...")
    results = []
    ground_truths = {}

    for s in samples:
        print(f"  {s['cve_id']} ...", end="", flush=True)
        t0 = time.time()
        result = run_cve_sample(s["cve_id"], s["diff_text"], s["pr_description"])
        elapsed = time.time() - t0
        results.append(result)
        if s.get("ground_truth"):
            ground_truths[s["cve_id"]] = s["ground_truth"]
        print(f" {result.get('verdict', 'error')} ({elapsed:.1f}s)")

    write_results(results, ground_truths)
    print(f"\n[benchmark] Done. Results: {RESULTS_MD}")


if __name__ == "__main__":
    main()
