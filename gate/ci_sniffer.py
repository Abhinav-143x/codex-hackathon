"""
gate/ci_sniffer.py — Auto-detect a repo's real test command from CI config files.

Checks (in priority order):
  1. .github/workflows/*.yml — extracts `run:` steps that look like test commands
  2. package.json#scripts.test
  3. Makefile `test:` target
  4. pyproject.toml [tool.pytest.ini_options] or tox.ini
  5. Cargo.toml — infers `cargo test`
  6. Gemfile/Rakefile — infers `bundle exec rake test`

Returns (command_str, confidence_score, source_file) or ("", 0.0, "") if nothing found.
Command is pinned at adopt-time — never re-derived live from PR content.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def _sniff_github_workflows(repo_root: Path) -> tuple[str, float, str]:
    """Parse .github/workflows/*.yml for test-looking run: steps."""
    workflows_dir = repo_root / ".github" / "workflows"
    if not workflows_dir.exists():
        return "", 0.0, ""

    for yml_file in sorted(workflows_dir.glob("*.yml")):
        try:
            content = yml_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # Look for `run:` lines that contain test keywords
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("run:"):
                cmd = stripped[4:].strip().strip("|").strip()
                if any(kw in cmd.lower() for kw in ["test", "pytest", "jest", "rspec", "cargo test", "go test", "npm test"]):
                    return cmd, 0.90, str(yml_file.relative_to(repo_root))

    return "", 0.0, ""


def _sniff_package_json(repo_root: Path) -> tuple[str, float, str]:
    """Check package.json scripts.test."""
    pkg = repo_root / "package.json"
    if not pkg.exists():
        return "", 0.0, ""
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
        test_cmd = data.get("scripts", {}).get("test", "")
        if test_cmd and test_cmd != "echo \"Error: no test specified\" && exit 1":
            return f"npm test", 0.85, "package.json"
    except Exception:
        pass
    return "", 0.0, ""


def _sniff_makefile(repo_root: Path) -> tuple[str, float, str]:
    """Check Makefile for a `test:` target."""
    makefile = repo_root / "Makefile"
    if not makefile.exists():
        return "", 0.0, ""
    try:
        content = makefile.read_text(encoding="utf-8", errors="replace")
        in_test_target = False
        for line in content.splitlines():
            if re.match(r"^test\s*:", line):
                in_test_target = True
                continue
            if in_test_target and line.startswith("\t"):
                cmd = line.strip()
                if cmd:
                    return f"make test", 0.80, "Makefile"
            elif in_test_target:
                break
    except Exception:
        pass
    return "", 0.0, ""


def _sniff_pyproject(repo_root: Path) -> tuple[str, float, str]:
    """Check pyproject.toml or tox.ini for pytest config."""
    pyproject = repo_root / "pyproject.toml"
    tox_ini = repo_root / "tox.ini"

    if pyproject.exists():
        try:
            content = pyproject.read_text(encoding="utf-8")
            if "[tool.pytest" in content or "[tool.tox" in content:
                return "python -m pytest", 0.75, "pyproject.toml"
        except Exception:
            pass

    if tox_ini.exists():
        return "tox", 0.75, "tox.ini"

    if (repo_root / "pytest.ini").exists() or (repo_root / "setup.cfg").exists():
        return "python -m pytest", 0.70, "pytest.ini/setup.cfg"

    return "", 0.0, ""


def _sniff_cargo(repo_root: Path) -> tuple[str, float, str]:
    """Check Cargo.toml for Rust project."""
    if (repo_root / "Cargo.toml").exists():
        return "cargo test", 0.85, "Cargo.toml"
    return "", 0.0, ""


def _sniff_ruby(repo_root: Path) -> tuple[str, float, str]:
    """Check for Ruby test conventions."""
    if (repo_root / "Gemfile").exists():
        rakefile = repo_root / "Rakefile"
        if rakefile.exists():
            return "bundle exec rake test", 0.75, "Rakefile"
        return "bundle exec rspec", 0.65, "Gemfile"
    return "", 0.0, ""


def sniff_test_command(repo_root: Path | str) -> tuple[str, float, str]:
    """
    Sniff the repo's real test command from CI config files.

    Returns (command_str, confidence_score, source_file).
    confidence_score is 0.0–1.0. Returns ("", 0.0, "") if nothing found.
    """
    repo_root = Path(repo_root)

    sniffers = [
        _sniff_github_workflows,
        _sniff_package_json,
        _sniff_cargo,
        _sniff_makefile,
        _sniff_pyproject,
        _sniff_ruby,
    ]

    for sniffer in sniffers:
        cmd, confidence, source = sniffer(repo_root)
        if cmd:
            return cmd, confidence, source

    return "", 0.0, ""


if __name__ == "__main__":
    import sys
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    cmd, conf, src = sniff_test_command(root)
    if cmd:
        print(f"Detected: {cmd!r} (confidence: {conf:.0%}, source: {src})")
    else:
        print("No test command detected.")
