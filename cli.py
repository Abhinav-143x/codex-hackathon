"""
cli.py — Typer-based CLI for PR Grounding Gate.

Commands:
  prgg init              Pick LLM provider, store key in OS keyring
  prgg check <target>    Check a PR (GitHub URL or local .diff file)
  prgg adopt <repo-url>  Clone repo, sniff CI config, pin test command
  prgg dashboard         Open demo_ui/index.html in browser
  prgg status            Print rolling summary of all runs

Install: pip install -e .
Run:     prgg --help
"""

from __future__ import annotations

import json
import os
import sys
import webbrowser
from pathlib import Path

import typer
from typing import Optional

app = typer.Typer(
    name="prgg",
    help="PR Grounding Gate — verify AI-generated PR claims before they waste your review time.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
config_app = typer.Typer(help="Manage BYOK provider keys and model fallback lists.")
app.add_typer(config_app, name="config")

_CONFIG_DIR = Path(os.environ.get("PRGG_HOME", str(Path.home() / ".prgg")))
_CONFIG_FILE = _CONFIG_DIR / "config.json"
_REPO_PINS_FILE = _CONFIG_DIR / "repo_pins.json"

PROVIDERS = {
    "gemini": "Google Gemini API — low-cost Flash/Flash-Lite models",
    "openrouter": "OpenRouter — one OpenAI-compatible key for many model catalogs",
    "openai": "OpenAI API — direct GPT fallback chain",
    "anthropic": "Anthropic API — optional later fallback",
}

KEY_PROVIDERS = ["gemini", "openrouter", "openai", "anthropic"]
LEGACY_CONFIG_KEYS = {
    "gemini": "gemini_key",
    "openrouter": "openrouter_key",
    "openai": "openai_key",
    "anthropic": "anthropic_key",
}

DEFAULT_BYOK_CONFIG = {
    "version": 1,
    "provider_order": ["gemini", "openrouter", "openai", "anthropic"],
    "keys": {
        "gemini": [""],
        "openrouter": [""],
        "openai": [""],
        "anthropic": [""],
    },
    "models": {
        "gemini": {
            "fast": ["gemini-flash-lite-latest", "gemini-2.0-flash-lite", "gemini-2.0-flash-lite-001", "gemini-2.5-flash"],
            "strong": ["gemini-flash-latest", "gemini-3.5-flash", "gemini-2.5-pro", "gemini-2.5-flash"],
        },
        "openrouter": {
            "fast": ["openai/gpt-5.4-nano", "openai/gpt-5.6-luna", "openai/gpt-4o-mini"],
            "strong": ["openai/gpt-5.6-luna", "openai/gpt-5.6-terra", "openai/gpt-4o"],
        },
        "openai": {
            "fast": ["gpt-5.4-nano", "gpt-5.6-luna", "gpt-4o-mini"],
            "strong": ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-4o"],
        },
        "anthropic": {
            "fast": ["claude-3-haiku-20240307"],
            "strong": ["claude-3-5-sonnet-20241022"],
        },
    },
}


def _load_config() -> dict:
    if _CONFIG_FILE.exists():
        try:
            return json.loads(_CONFIG_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_config(cfg: dict) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def _public_config(src: dict) -> dict:
    cfg = _load_config()
    if isinstance(src.get("provider_order"), list):
        cfg["provider_order"] = [str(p) for p in src["provider_order"] if str(p) in PROVIDERS]
    if isinstance(src.get("models"), dict):
        cfg["models"] = src["models"]
    if src.get("provider") in PROVIDERS:
        cfg["provider"] = src["provider"]
    elif cfg.get("provider") not in PROVIDERS and cfg.get("provider_order"):
        cfg["provider"] = cfg["provider_order"][0]
    return cfg


def _clean_key(value: object) -> str:
    clean = str(value or "").strip()
    if clean and not (clean.startswith("<") and clean.endswith(">")):
        return clean
    return ""


def _append_key(values: dict[str, list[str]], provider: str, value: object) -> None:
    clean = _clean_key(value)
    if clean and clean not in values[provider]:
        values[provider].append(clean)


def _key_values(src: dict) -> dict[str, list[str]]:
    keys = src.get("keys", {})
    values = {provider: [] for provider in KEY_PROVIDERS}
    if isinstance(keys, dict):
        for provider in KEY_PROVIDERS:
            raw = keys.get(provider, [])
            if isinstance(raw, list):
                for value in raw:
                    _append_key(values, provider, value)
            else:
                _append_key(values, provider, raw)

            plural = keys.get(f"{provider}_keys", src.get(f"{provider}_keys", []))
            if isinstance(plural, list):
                for value in plural:
                    _append_key(values, provider, value)

            index = 1
            while f"{provider}_{index}" in keys:
                _append_key(values, provider, keys.get(f"{provider}_{index}"))
                index += 1

    for provider, legacy_config_key in LEGACY_CONFIG_KEYS.items():
        _append_key(values, provider, src.get(legacy_config_key, ""))
        index = 1
        while f"{legacy_config_key}_{index}" in src:
            _append_key(values, provider, src.get(f"{legacy_config_key}_{index}"))
            index += 1
    return values


def _store_key(service: str, key: str) -> bool:
    """Store API key in OS keyring. Returns True on success."""
    try:
        import keyring
        keyring.set_password("prgg", service, key)
        return True
    except Exception:
        return False


def _get_key(service: str) -> str | None:
    """Get API key from OS keyring."""
    try:
        import keyring
        return keyring.get_password("prgg", service)
    except Exception:
        return None


@config_app.command("template")
def config_template(
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Where to write the template JSON."),
):
    """Create a BYOK config template for browser or manual editing."""
    payload = json.dumps(DEFAULT_BYOK_CONFIG, indent=2)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
        typer.echo(f"Wrote BYOK template: {out}")
    else:
        typer.echo(payload)


@config_app.command("import")
def config_import(
    path: Path = typer.Argument(help="BYOK config JSON downloaded from the web builder."),
    allow_plain_file: bool = typer.Option(
        False,
        "--allow-plain-file",
        help="If keyring is unavailable, allow storing keys in ~/.prgg/config.json.",
    ),
):
    """Import BYOK provider keys and model fallback lists."""
    try:
        src = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        typer.echo(f"[red]Could not read config JSON: {exc}[/red]")
        raise typer.Exit(1)

    cfg = _public_config(src)
    key_counts = dict(cfg.get("key_counts", {})) if isinstance(cfg.get("key_counts"), dict) else {}
    key_pools = dict(cfg.get("key_pools", {})) if isinstance(cfg.get("key_pools"), dict) else {}
    plain_keys: dict[str, str] = {}
    stored = []
    failed = []
    for provider, values in _key_values(src).items():
        if not values:
            continue
        provider_plain: list[str] = []
        for index, value in enumerate(values, start=1):
            service = f"{provider}_{index}"
            if _store_key(service, value):
                stored.append(service)
            elif allow_plain_file:
                provider_plain.append(value)
                stored.append(f"{service} (plain file)")
            else:
                failed.append(service)
        key_counts[provider] = max(int(key_counts.get(provider, 0) or 0), len(values))
        if provider_plain:
            key_pools[provider] = provider_plain

    if failed:
        typer.echo(
            "[red]Keyring unavailable for: "
            + ", ".join(failed)
            + ". Re-run with --allow-plain-file only if you accept local plaintext key storage.[/red]"
        )
        raise typer.Exit(1)

    if key_counts:
        cfg["key_counts"] = key_counts
    if key_pools:
        cfg["key_pools"] = key_pools
    cfg.update(plain_keys)
    _save_config(cfg)
    typer.echo(f"[green]Imported BYOK config to {_CONFIG_FILE}[/green]")
    typer.echo(f"Stored keys: {', '.join(stored) if stored else 'none'}")
    typer.echo("Secrets were not printed.")


@config_app.command("status")
def config_status():
    """Show configured providers/models without revealing secrets."""
    cfg = _load_config()
    key_counts = cfg.get("key_counts", {}) if isinstance(cfg.get("key_counts"), dict) else {}
    key_pools = cfg.get("key_pools", {}) if isinstance(cfg.get("key_pools"), dict) else {}
    key_status: dict[str, list[bool]] = {}
    legacy_status: dict[str, bool] = {}
    for provider in KEY_PROVIDERS:
        count = 0
        try:
            count = int(key_counts.get(provider, 0))
        except Exception:
            count = 0
        plain_pool = key_pools.get(provider, [])
        if isinstance(plain_pool, list):
            count = max(count, len(plain_pool))
        elif isinstance(plain_pool, str) and plain_pool.strip():
            count = max(count, 1)
        statuses = []
        for index in range(1, max(count, 0) + 1):
            plain_present = isinstance(plain_pool, list) and index <= len(plain_pool) and bool(str(plain_pool[index - 1]).strip())
            statuses.append(bool(_get_key(f"{provider}_{index}") or plain_present))
        legacy_status[provider] = bool(_get_key(provider) or str(cfg.get(LEGACY_CONFIG_KEYS[provider], "")).strip())
        key_status[provider] = statuses

    typer.echo("\n[bold]PR Grounding Gate — BYOK Status[/bold]")
    typer.echo(f"  Config file: {_CONFIG_FILE} ({'present' if _CONFIG_FILE.exists() else 'missing'})")
    typer.echo("  Keys:")
    for provider in KEY_PROVIDERS:
        present = sum(1 for status in key_status[provider] if status)
        total = len(key_status[provider])
        legacy = " + legacy" if legacy_status[provider] else ""
        typer.echo(f"    {provider} pool: {present}/{total} present{legacy}")
        for index, slot_present in enumerate(key_status[provider], start=1):
            typer.echo(f"      {provider}_{index}: {'present' if slot_present else 'missing'}")

    typer.echo("  Provider order:")
    for provider in cfg.get("provider_order", DEFAULT_BYOK_CONFIG["provider_order"]):
        typer.echo(f"    - {provider}")

    typer.echo("  Model fallback lists:")
    models = cfg.get("models", DEFAULT_BYOK_CONFIG["models"])
    for provider, tiers in models.items():
        fast = ", ".join(tiers.get("fast", [])) if isinstance(tiers, dict) else ""
        strong = ", ".join(tiers.get("strong", [])) if isinstance(tiers, dict) else ""
        typer.echo(f"    {provider}.fast: {fast}")
        typer.echo(f"    {provider}.strong: {strong}")


@app.command()
def init():
    """
    One-time setup: pick your LLM provider and store the API key securely.

    The key is stored in your OS keyring (macOS Keychain / Windows Credential Manager /
    Linux Secret Service). It never leaves your machine and is never uploaded anywhere.
    Only the diff + PR description are ever sent to your configured provider.
    """
    typer.echo("\n[bold]PR Grounding Gate — Setup[/bold]\n")
    typer.echo("Available providers:")
    for name, desc in PROVIDERS.items():
        typer.echo(f"  [cyan]{name}[/cyan]: {desc}")

    provider = typer.prompt("\nProvider", default="gemini")
    if provider not in PROVIDERS:
        typer.echo(f"[red]Unknown provider '{provider}'. Choose from: {list(PROVIDERS.keys())}[/red]")
        raise typer.Exit(1)

    key = typer.prompt("API key", hide_input=True)
    if not key:
        typer.echo("[red]No key provided.[/red]")
        raise typer.Exit(1)

    # Try OS keyring first, fall back to config file
    if _store_key(f"{provider}_1", key):
        typer.echo(f"\n[green]Key stored in OS keyring for '{provider}'.[/green]")
    else:
        typer.echo(f"\n[yellow]OS keyring unavailable — storing in {_CONFIG_FILE} (chmod 600 recommended).[/yellow]")
        cfg = _load_config()
        key_pools = dict(cfg.get("key_pools", {})) if isinstance(cfg.get("key_pools"), dict) else {}
        key_pools[provider] = [key]
        cfg["key_pools"] = key_pools
        _save_config(cfg)

    # Save provider choice to config
    cfg = _load_config()
    cfg["provider"] = provider
    key_counts = dict(cfg.get("key_counts", {})) if isinstance(cfg.get("key_counts"), dict) else {}
    key_counts[provider] = max(int(key_counts.get(provider, 0) or 0), 1)
    cfg["key_counts"] = key_counts
    _save_config(cfg)

    typer.echo(f"Provider: [cyan]{provider}[/cyan]")
    typer.echo(
        "\n[dim]Zero telemetry. No account. No phone-home.\n"
        "Only diff + PR description leave your machine, sent to your configured provider.[/dim]"
    )


@app.command()
def check(
    target: str = typer.Argument(help="GitHub PR URL or local .diff file"),
    tier: str = typer.Option("fast", help="Proposer model tier: fast or strong"),
):
    """
    Run the full pipeline (Proposer, Gate, Verdict, Explainer) on a PR.
    Examples: prgg check https://github.com/npm/cli/pull/9473
    """
    typer.echo(f"\nChecking: {target}")

    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from run_sample import run_single
        result = run_single(target, tier=tier)
        verdict = result["verdict"]["verdict"]

        icons = {"grounded": "[+]", "ungrounded": "[-]", "needs-review": "[?]", "error": "[!]"}
        typer.echo(f"\n{icons.get(verdict, '[?]')} VERDICT: {verdict.upper()}")
        typer.echo(f"Explanation: {result.get('explanation', '')}")

        failing = result["verdict"].get("failing_checks", [])
        if failing:
            typer.echo(f"Failing checks: {', '.join(failing)}")

    except Exception as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1)


@app.command()
def adopt(
    repo_url: str = typer.Argument(help="GitHub repo URL to adopt (e.g. https://github.com/owner/repo)"),
    pin_dir: Optional[str] = typer.Option(None, help="Where to clone (default: ~/.prgg/repos/<repo_name>)"),
    test_command: Optional[str] = typer.Option(
        None,
        "--test-command",
        help="Pin an explicit deterministic test command instead of sniffing CI.",
    ),
):
    """
    Adopt a repo: clone it, sniff CI config, pin the test command.

    After adoption, every `prgg check` against that repo uses the repo's real
    test suite — not a stub. The test command is pinned at adopt-time and never
    re-derived from PR content (which could be malicious).
    """
    import subprocess
    import re

    # Derive repo name
    m = re.match(r"https?://github\.com/[^/]+/([^/]+?)(?:\.git)?$", repo_url)
    repo_name = m.group(1) if m else repo_url.rstrip("/").split("/")[-1]

    clone_dir = Path(pin_dir) if pin_dir else Path.home() / ".prgg" / "repos" / repo_name
    clone_dir = clone_dir.resolve()

    if clone_dir.exists():
        typer.echo(f"Already cloned at {clone_dir} — using existing clone.")
    else:
        typer.echo(f"Cloning {repo_url} to {clone_dir} …")
        try:
            subprocess.run(
                ["git", "clone", "--depth=1", repo_url, str(clone_dir)],
                check=True, capture_output=False
            )
        except subprocess.CalledProcessError as e:
            typer.echo(f"[red]Clone failed: {e}[/red]")
            raise typer.Exit(1)

    if test_command:
        cmd, confidence, source = test_command, 1.0, "user-pinned"
    else:
        # Sniff CI config
        sys.path.insert(0, str(Path(__file__).parent))
        from gate.ci_sniffer import sniff_test_command
        cmd, confidence, source = sniff_test_command(clone_dir)

    if cmd:
        typer.echo(f"\n[green]Test command detected:[/green] {cmd!r}")
        typer.echo(f"  Source: {source} (confidence: {confidence:.0%})")
    else:
        typer.echo("[yellow]No test command auto-detected. You can set one manually in ~/.prgg/repo_pins.json[/yellow]")

    # Pin the result
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    pins = {}
    if _REPO_PINS_FILE.exists():
        try:
            pins = json.loads(_REPO_PINS_FILE.read_text())
        except Exception:
            pass

    repo_full = repo_url.rstrip("/").removeprefix("https://github.com/").removesuffix(".git")
    pin_data = {
        "url": repo_url,
        "clone_dir": str(clone_dir),
        "test_command": cmd,
        "test_command_source": source,
        "test_command_confidence": confidence,
    }
    pins[repo_name] = pin_data
    if "/" in repo_full:
        pins[repo_full] = pin_data
    _REPO_PINS_FILE.write_text(json.dumps(pins, indent=2))
    typer.echo(f"\n[green]Pinned to {_REPO_PINS_FILE}[/green]")
    typer.echo("Run [bold]prgg check <pr-url>[/bold] to start verifying PRs against this repo.")


@app.command()
def dashboard():
    """
    Open the local git-log-style dashboard in your browser.
    No server required — it's a static HTML file.
    """
    dashboard_path = Path(__file__).parent / "demo_ui" / "index.html"
    if not dashboard_path.exists():
        typer.echo("[yellow]Dashboard not generated yet. Run: python run_sample.py --all[/yellow]")
        raise typer.Exit(1)

    url = dashboard_path.as_uri()
    typer.echo(f"Opening dashboard: {url}")
    webbrowser.open(url)


@app.command()
def status():
    """
    Print a rolling summary of all runs (total, grounded, ungrounded, needs-review, avg latency).
    """
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from logging_agent import summarize
        summary = summarize()
        typer.echo("\n[bold]PR Grounding Gate — Status[/bold]")
        typer.echo(f"  Total runs:     {summary['total']}")
        typer.echo(f"  [green]Grounded:[/green]       {summary['grounded']}")
        typer.echo(f"  [red]Ungrounded:[/red]     {summary['ungrounded']}")
        typer.echo(f"  [yellow]Needs review:[/yellow]   {summary['needs_review']}")
        if summary.get("errors"):
            typer.echo(f"  [red]Errors:[/red]         {summary['errors']}")
        typer.echo(f"  Avg latency:    {summary['avg_latency_s']}s")
        if summary.get("recent_errors"):
            typer.echo(f"  Recent errors:  {summary['recent_errors']}")
        typer.echo(f"\n  Log dir: {summary.get('log_dir', 'logs/')}")
    except Exception as exc:
        typer.echo(f"[red]Error reading status: {exc}[/red]")
        raise typer.Exit(1)


def main():
    app()


if __name__ == "__main__":
    main()
