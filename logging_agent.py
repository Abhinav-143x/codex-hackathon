"""
logging_agent.py — Structured event logging + rolling summary for PR Grounding Gate.

Writes JSON-formatted events to logs/<date>.jsonl — one line per event.
Provides summarize() for the `prgg status` command.

Security: never logs raw API keys or .env contents. Key-shaped strings are redacted.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Pattern to catch anything that looks like an API key in error messages
_KEY_PATTERN = re.compile(
    r"(AIza|sk-or-|sk-|AQ\.|Bearer |api[_-]?key[=:]\s*)\S{8,}",
    re.IGNORECASE,
)


def _redact(text: str) -> str:
    """Redact API key patterns from any string before logging."""
    return _KEY_PATTERN.sub(r"\1[REDACTED]", text)


def _log_path() -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return LOGS_DIR / f"{today}.jsonl"


def log_event(event_type: str, data: dict) -> None:
    """
    Write a single structured event to today's log file.
    All string values are redacted before writing.
    """
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        **{k: _redact(str(v)) if isinstance(v, str) else v for k, v in data.items()},
    }
    try:
        with _log_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # logging must never crash the pipeline


def log_proposer_call(sample_name: str, model: str, tier: str, start_time: float) -> None:
    log_event("proposer_start", {
        "sample": sample_name,
        "model": model,
        "tier": tier,
        "wall_start": start_time,
    })


def log_proposer_result(sample_name: str, bug_type: str, confidence: float, elapsed_s: float) -> None:
    log_event("proposer_done", {
        "sample": sample_name,
        "bug_type": bug_type,
        "confidence": confidence,
        "elapsed_s": round(elapsed_s, 3),
    })


def log_gate_check(sample_name: str, check_name: str, passed: bool, elapsed_s: float, reason_snippet: str) -> None:
    log_event("gate_check", {
        "sample": sample_name,
        "check": check_name,
        "pass": passed,
        "elapsed_s": round(elapsed_s, 3),
        "reason_snippet": reason_snippet[:200],
    })


def log_verdict(sample_name: str, verdict: str, failing_checks: list, total_elapsed_s: float) -> None:
    log_event("verdict", {
        "sample": sample_name,
        "verdict": verdict,
        "failing_checks": failing_checks,
        "total_elapsed_s": round(total_elapsed_s, 3),
    })


def log_provider_rotation(from_key_index: int, to_key_index: int, reason: str) -> None:
    log_event("provider_rotation", {
        "from_key_index": from_key_index,
        "to_key_index": to_key_index,
        "reason": _redact(reason)[:300],
    })


def log_error(sample_name: str, error_type: str, message: str) -> None:
    log_event("error", {
        "sample": sample_name,
        "error_type": error_type,
        "message": _redact(message)[:500],
    })


def summarize() -> dict:
    """
    Rolling summary across all runs/*.json files.
    Used by `prgg status`.
    """
    runs_dir = Path(__file__).parent / "runs"
    runs = []
    for p in sorted(runs_dir.glob("*.json")):
        try:
            runs.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass

    if not runs:
        return {
            "total": 0,
            "grounded": 0,
            "ungrounded": 0,
            "needs_review": 0,
            "errors": 0,
            "avg_latency_s": 0.0,
            "recent_errors": [],
            "message": "No runs found. Run: python run_sample.py --all",
        }

    verdicts = [r.get("verdict", {}).get("verdict", "unknown") for r in runs]
    latencies = [r.get("elapsed_s", 0) for r in runs if r.get("elapsed_s") is not None]

    return {
        "total": len(runs),
        "grounded": verdicts.count("grounded"),
        "ungrounded": verdicts.count("ungrounded"),
        "needs_review": verdicts.count("needs-review"),
        "errors": verdicts.count("error"),
        "avg_latency_s": round(sum(latencies) / max(len(latencies), 1), 2),
        "recent_errors": [
            r["sample_name"] for r in runs if r.get("verdict", {}).get("verdict") == "error"
        ][-5:],
        "log_dir": str(LOGS_DIR),
    }


if __name__ == "__main__":
    import pprint
    pprint.pprint(summarize())
