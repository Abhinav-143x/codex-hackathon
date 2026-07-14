# PR Grounding Gate — CVE Benchmark Results

**Run date:** 2026-07-14
**Total CVEs evaluated:** 1
**With ground truth:** 1

## Summary (CVEs with ground truth)
| Metric | Score |
|--------|-------|
| Accuracy | 100.0% |
| Precision | 100.0% |
| Recall (sensitivity) | 100.0% |
| F1 | 100.0% |
| True positives | 1 |
| False positives | 0 |
| True negatives | 0 |
| False negatives | 0 |

> **Methodology:** Each CVE's patch commit diff + description is treated as an incoming
> claimed-fix PR. `grounded` verdict = fix claim verified (confirmed). All other verdicts
> = not confirmed. Mapping stated explicitly — not a forced fit.

## Per-CVE Results

| CVE ID | Verdict | Bench Result | Failing Checks | Ground Truth | Correct |
|--------|---------|-------------|----------------|--------------|---------|
| CVE-2023-32681 | grounded | confirmed | — | confirmed | ✓ |

---
*Full per-check data in [results.csv](results.csv).*
*Raw results are published alongside this summary — not just the headline score.*