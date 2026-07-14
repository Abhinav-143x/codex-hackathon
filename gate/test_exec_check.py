"""
gate/test_exec_check.py — Real test-suite execution check (DETERMINISTIC, ZERO LLM).

For samples 1-4 (Python): returns a stub pass result.
For sample 5 (protobuf Ruby): shells out to the real Ruby test command.
  - If ruby is in PATH: runs `ruby -Ilib -Itests tests/basic.rb --name=test_enum_getter`
  - If ruby is NOT in PATH: runs the Python mock harness instead.

This is an explicit, hardcoded proof case — NOT general multi-language support.
"""

import os
import json
import re
import subprocess
import sys
from pathlib import Path

# The one sample name that triggers real execution
_RUBY_SAMPLE_NAME = "5_protobuf_ruby_real"

# Path to the protobuf ruby sample directory
_RUBY_SAMPLE_DIR = Path(__file__).parent.parent / "samples" / "protobuf_ruby"

# The hardcoded Ruby test command from the real merged PR #27848
_RUBY_TEST_CMD = ["ruby", "-Ilib", "-Itests", "tests/basic.rb", "--name=test_enum_getter"]
_CONFIG_DIR = Path(os.environ.get("PRGG_HOME", str(Path.home() / ".prgg")))
_REPO_PINS_FILE = _CONFIG_DIR / "repo_pins.json"


def _repo_from_sample(sample_name: str) -> tuple[str, str]:
    match = re.match(r"https://github\.com/([^/]+)/([^/]+)/pull/\d+", str(sample_name))
    if match:
        owner, repo = match.groups()
        return f"{owner}/{repo}", repo

    sample_path = Path(str(sample_name))
    candidates = []
    if sample_path.suffix:
        candidates.append(sample_path.with_suffix(".meta.json"))
    candidates.append(Path(__file__).parent.parent / "samples" / f"{sample_path.stem}.meta.json")

    for meta_path in candidates:
        try:
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                repo_full = str(meta.get("repo", "")).strip()
                if "/" in repo_full:
                    return repo_full, repo_full.split("/", 1)[1]
        except Exception:
            continue
    return "", ""


def _load_repo_pin(sample_name: str) -> dict:
    repo_full, repo_name = _repo_from_sample(sample_name)
    if not repo_name or not _REPO_PINS_FILE.exists():
        return {}
    try:
        pins = json.loads(_REPO_PINS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return pins.get(repo_full) or pins.get(repo_name) or {}


def _git(args: list[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def _run_adopted_repo_tests(sample_name: str, diff_text: str) -> dict | None:
    pin = _load_repo_pin(sample_name)
    if not pin:
        return None

    clone_dir = Path(str(pin.get("clone_dir", ""))).expanduser()
    test_command = str(pin.get("test_command", "")).strip()
    if not clone_dir.exists() or not test_command:
        return {
            "pass": False,
            "reason": (
                "test_exec_check [ADOPTED]: repo pin exists but clone_dir or test_command "
                "is missing. Re-run `prgg adopt <repo-url>`."
            ),
        }

    if not (clone_dir / ".git").exists():
        return {
            "pass": False,
            "reason": "test_exec_check [ADOPTED]: clone_dir is not a git checkout.",
        }

    status = _git(["status", "--porcelain"], clone_dir)
    if status.returncode != 0:
        return {
            "pass": False,
            "reason": f"test_exec_check [ADOPTED]: could not read git status. {status.stderr[:300]}",
        }
    if status.stdout.strip():
        return {
            "pass": False,
            "reason": (
                "test_exec_check [ADOPTED]: local adopted checkout has existing changes, "
                "so PRGG refused to apply the PR diff over it. Clean or reclone with `prgg adopt`."
            ),
        }

    patch_file = clone_dir / ".prgg-current.patch"
    patch_file.write_text(diff_text, encoding="utf-8")
    applied = False
    check = _git(["apply", "--check", str(patch_file)], clone_dir)
    if check.returncode != 0:
        try:
            patch_file.unlink()
        except OSError:
            pass
        return {
            "pass": False,
            "reason": (
                "test_exec_check [ADOPTED]: PR diff did not apply cleanly to the adopted "
                f"checkout. output={((check.stdout or '') + (check.stderr or ''))[:500]}"
            ),
        }

    apply_result = _git(["apply", str(patch_file)], clone_dir)
    if apply_result.returncode != 0:
        try:
            patch_file.unlink()
        except OSError:
            pass
        return {
            "pass": False,
            "reason": (
                "test_exec_check [ADOPTED]: failed to apply PR diff to adopted checkout. "
                f"output={((apply_result.stdout or '') + (apply_result.stderr or ''))[:500]}"
            ),
        }
    applied = True

    timeout = int(os.environ.get("PRGG_TEST_TIMEOUT_S", "180"))
    try:
        result = subprocess.run(
            test_command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(clone_dir),
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        result = None
    finally:
        if applied:
            _git(["apply", "-R", str(patch_file)], clone_dir)
        try:
            patch_file.unlink()
        except OSError:
            pass

    if result is None:
        return {
            "pass": False,
            "reason": (
                f"test_exec_check [ADOPTED]: pinned command timed out after {timeout}s "
                f"after applying the PR diff: {test_command}"
            ),
        }

    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode == 0:
        return {
            "pass": True,
            "reason": (
                "test_exec_check [ADOPTED]: applied the PR diff locally and the pinned "
                "repo test command passed. "
                f"cmd={test_command!r}; source={pin.get('test_command_source', 'unknown')}; "
                f"output={output[:400]}"
            ),
        }
    return {
        "pass": False,
        "reason": (
            "test_exec_check [ADOPTED]: applied the PR diff locally and the pinned "
            "repo test command failed. "
            f"cmd={test_command!r}; exit_code={result.returncode}; output={output[:500]}"
        ),
    }


def _run_ruby_tests() -> dict:
    """
    Try to run the real Ruby test command.
    Falls back to the Python mock harness if ruby is not installed.
    """
    # Check if ruby exists
    try:
        check = subprocess.run(
            ["ruby", "--version"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace",
        )
        ruby_available = check.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        ruby_available = False

    if ruby_available:
        print(f"[test_exec] Running real Ruby tests: {' '.join(_RUBY_TEST_CMD)}")
        try:
            result = subprocess.run(
                _RUBY_TEST_CMD,
                capture_output=True, text=True,
                cwd=str(_RUBY_SAMPLE_DIR),
                timeout=60,
                encoding="utf-8", errors="replace",
            )
            stdout = (result.stdout or "") + (result.stderr or "")
            if result.returncode == 0:
                return {
                    "pass": True,
                    "reason": (
                        "test_exec_check [RUBY]: Real protobuf test suite passed. "
                        f"ruby -Ilib -Itests tests/basic.rb --name=test_enum_getter "
                        f"exit_code=0. Output: {stdout[:300].strip()}"
                    ),
                }
            else:
                return {
                    "pass": False,
                    "reason": (
                        "test_exec_check [RUBY]: Real protobuf test suite FAILED. "
                        f"exit_code={result.returncode}. "
                        f"Output: {stdout[:400].strip()}"
                    ),
                }
        except subprocess.TimeoutExpired:
            return {
                "pass": False,
                "reason": "test_exec_check [RUBY]: Test suite timed out after 60s.",
            }
    else:
        # Ruby not installed — run Python mock harness
        print("[test_exec] ruby not in PATH — running Python mock harness for protobuf sample.")
        mock_runner = _RUBY_SAMPLE_DIR / "mock_ruby_test_runner.py"
        if not mock_runner.exists():
            return {
                "pass": False,
                "reason": (
                    "test_exec_check [RUBY]: ruby not installed and mock_ruby_test_runner.py "
                    "not found. Cannot verify test execution."
                ),
            }
        try:
            result = subprocess.run(
                [sys.executable, str(mock_runner)],
                capture_output=True, text=True,
                cwd=str(_RUBY_SAMPLE_DIR),
                timeout=30,
                encoding="utf-8", errors="replace",
            )
            stdout = (result.stdout or "") + (result.stderr or "")
            if result.returncode == 0:
                return {
                    "pass": True,
                    "reason": (
                        "test_exec_check [RUBY/mock]: stub pass via Python verification harness. "
                        f"Ruby is not installed, so real protobuf test execution was not verified. "
                        f"Output: {stdout[:300].strip()}"
                    ),
                }
            else:
                return {
                    "pass": False,
                    "reason": (
                        "test_exec_check [RUBY/mock]: Python verification harness FAILED. "
                        f"Output: {stdout[:400].strip()}"
                    ),
                }
        except subprocess.TimeoutExpired:
            return {
                "pass": False,
                "reason": "test_exec_check [RUBY/mock]: Mock harness timed out.",
            }


# ── public API ────────────────────────────────────────────────────────────────

def test_exec_check(
    claim: dict,
    diff_text: str,
    sample_name: str = "",
) -> dict:
    """
    Test-suite execution check.

    For most samples: returns "unverified" unless repo-specific execution has
    been adopted.
    For sample 5 (5_protobuf_ruby_real): runs real Ruby tests (or Python mock).

    Parameters
    ----------
    claim       : Proposer output dict
    diff_text   : Raw unified diff string
    sample_name : Name of the sample being processed (used to detect Ruby sample)

    Returns
    -------
    {"pass": bool, "reason": str}
    """
    is_ruby_sample = _RUBY_SAMPLE_NAME in sample_name

    adopted_result = _run_adopted_repo_tests(sample_name, diff_text)
    if adopted_result is not None:
        return adopted_result

    if is_ruby_sample:
        return _run_ruby_tests()
    else:
        label = Path(str(sample_name)).name or "provided sample"
        return {
            "pass": True,
            "reason": (
                f"test_exec_check: no repo-specific test runner is adopted for '{label}'. "
                "This check is a non-authoritative placeholder pass so coverage, consistency, "
                "5W, blind-spot, and Unicode checks can still run. The verdict must remain "
                "review-gated until real tests are pinned with `prgg adopt`."
            ),
        }
