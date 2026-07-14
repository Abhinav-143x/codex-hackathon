"""
config.py — Multi-provider, dual-key LLM adapter for PR Grounding Gate.

Key priority (checked in order):
  1. process/user env vars
  2. ~/.prgg/config.json written by `prgg init`
  3. OS keyring entries written by `prgg init`
  4. offline diff-parsing mock (no network)

Google AI Studio OpenAI-compatible endpoint (official docs):
  https://ai.google.dev/gemini-api/docs/openai
  Base URL: https://generativelanguage.googleapis.com/v1beta/openai/

Model selection (July 2026):
  Gemini fast:   gemini-flash-lite-latest  (lowest-cost structured extraction)
  Gemini strong: gemini-flash-latest       (stable current Gemini text model)
  OpenAI fast:   gpt-5.4-nano           (lowest-cost OpenAI extraction)
  OpenAI strong: gpt-5.6-luna           (cost-sensitive frontier reasoning)

Rate limits:
  Configure arbitrary key pools per provider for demo/key-pool rotation.
  Config rotates keys automatically on 429 — next key used immediately,
  no waiting.

See env.md for full environment variable documentation.
"""

import os
import json
import re
import time
import itertools
from pathlib import Path

# ── credential loading & fallback setup ─────────────────────────────────────────

def _load_prgg_config() -> dict:
    cfg_path = Path(os.environ.get("PRGG_HOME", str(Path.home() / ".prgg"))) / "config.json"
    try:
        if cfg_path.exists():
            return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _keyring_get(service: str) -> str:
    try:
        import keyring
        return (keyring.get_password("prgg", service) or "").strip()
    except Exception:
        return ""


def _first_secret(*names: str, config_key: str | None = None, keyring_service: str | None = None) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value

    cfg = _PRGG_CONFIG
    if config_key:
        value = str(cfg.get(config_key, "")).strip()
        if value:
            return value

    if keyring_service:
        value = _keyring_get(keyring_service)
        if value:
            return value

    return ""


_PRGG_CONFIG = _load_prgg_config()

KEY_PROVIDER_META = {
    "gemini": {
        "env": ["GEMINI_API_KEY"],
        "config": "gemini_key",
        "service": "gemini",
    },
    "openrouter": {
        "env": ["OPENROUTER_API_KEY", "LLM_API_KEY"],
        "config": "openrouter_key",
        "service": "openrouter",
    },
    "anthropic": {
        "env": ["ANTHROPIC_API_KEY"],
        "config": "anthropic_key",
        "service": "anthropic",
    },
    "openai": {
        "env": ["OPENAI_API_KEY"],
        "config": "openai_key",
        "service": "openai",
    },
}


def _unique_present(values: list[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value and value not in unique:
            unique.append(value)
    return unique


def _numbered_env_values(env_names: list[str]) -> list[str]:
    values: list[tuple[int, str]] = []
    exact_values: list[str] = []
    for env_name in env_names:
        exact = os.environ.get(env_name, "").strip()
        if exact:
            exact_values.append(exact)
        pattern = re.compile(rf"^{re.escape(env_name)}_(\d+)$")
        for name, value in os.environ.items():
            match = pattern.match(name)
            if match and value.strip():
                values.append((int(match.group(1)), value.strip()))
    return [value for _, value in sorted(values)] + exact_values


def _config_key_pool(provider: str, legacy_config_key: str) -> list[str]:
    values: list[str] = []
    pools = _PRGG_CONFIG.get("key_pools", {})
    if isinstance(pools, dict):
        configured = pools.get(provider, [])
        if isinstance(configured, str):
            values.append(configured.strip())
        elif isinstance(configured, list):
            values.extend(str(value).strip() for value in configured)

    legacy = str(_PRGG_CONFIG.get(legacy_config_key, "")).strip()
    if legacy:
        values.append(legacy)

    for name, value in _PRGG_CONFIG.items():
        match = re.match(rf"^{re.escape(legacy_config_key)}_(\d+)$", str(name))
        if match and str(value).strip():
            values.append(str(value).strip())
    return values


def _keyring_key_pool(provider: str, legacy_service: str) -> list[str]:
    values: list[str] = []
    key_counts = _PRGG_CONFIG.get("key_counts", {})
    count = 0
    if isinstance(key_counts, dict):
        try:
            count = int(key_counts.get(provider, 0))
        except Exception:
            count = 0
    for index in range(1, max(count, 0) + 1):
        value = _keyring_get(f"{provider}_{index}")
        if value:
            values.append(value)

    legacy = _keyring_get(legacy_service)
    if legacy:
        values.append(legacy)
    return values


def _provider_keys(provider: str) -> list[str]:
    meta = KEY_PROVIDER_META[provider]
    return _unique_present(
        _numbered_env_values(meta["env"])
        + _config_key_pool(provider, meta["config"])
        + _keyring_key_pool(provider, meta["service"])
    )


_PROVIDER_KEYS = {provider: _provider_keys(provider) for provider in KEY_PROVIDER_META}
_GEMINI_KEYS = _PROVIDER_KEYS["gemini"]
_OPENROUTER_KEYS = _PROVIDER_KEYS["openrouter"]
_CLAUDE_KEYS = _PROVIDER_KEYS["anthropic"]
_OPENAI_KEYS = _PROVIDER_KEYS["openai"]

# Build the fallback router list (tuples of provider, model, key)
# Priority: Gemini -> Claude -> OpenAI
FALLBACK_CHAIN = []


def _configured_models(provider: str, tier: str) -> list[str]:
    configured = _PRGG_CONFIG.get("models", {}).get(provider, {}).get(tier, [])
    if isinstance(configured, str):
        return [m.strip() for m in configured.split(",") if m.strip()]
    if isinstance(configured, list):
        return [str(m).strip() for m in configured if str(m).strip()]
    return []


def _model_list(env_name: str, defaults: list[str], provider: str, tier: str) -> list[str]:
    """Read env or config model fallback list, preserving unique order."""
    raw = os.environ.get(env_name, "").strip()
    candidates = [m.strip() for m in raw.split(",") if m.strip()]
    if not candidates:
        candidates = _configured_models(provider, tier)
    if not candidates:
        candidates = defaults
    unique: list[str] = []
    for model in candidates:
        if model not in unique:
            unique.append(model)
    return unique


_GEMINI_FAST_MODELS = _model_list(
    "GEMINI_MODELS_FAST",
    [
        os.environ.get("GEMINI_MODEL_FAST", "gemini-flash-lite-latest"),
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash-lite-001",
        "gemini-2.5-flash",
    ],
    "gemini",
    "fast",
)
_GEMINI_STRONG_MODELS = _model_list(
    "GEMINI_MODELS_STRONG",
    [
        os.environ.get("GEMINI_MODEL_STRONG", "gemini-flash-latest"),
        "gemini-3.5-flash",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
    ],
    "gemini",
    "strong",
)
_OPENROUTER_FAST_MODELS = _model_list(
    "OPENROUTER_MODELS_FAST",
    [
        os.environ.get("OPENROUTER_MODEL_FAST", os.environ.get("LLM_MODEL", "openai/gpt-5.4-nano")),
        "openai/gpt-5.6-luna",
        "openai/gpt-4o-mini",
    ],
    "openrouter",
    "fast",
)
_OPENROUTER_STRONG_MODELS = _model_list(
    "OPENROUTER_MODELS_STRONG",
    [
        os.environ.get("OPENROUTER_MODEL_STRONG", os.environ.get("LLM_MODEL_STRONG", "openai/gpt-5.6-luna")),
        "openai/gpt-5.6-terra",
        "openai/gpt-4o",
    ],
    "openrouter",
    "strong",
)
_OPENAI_FAST_MODELS = _model_list(
    "OPENAI_MODELS_FAST",
    [
        os.environ.get("OPENAI_MODEL_FAST", "gpt-5.4-nano"),
        "gpt-5.6-luna",
        "gpt-4o-mini",
    ],
    "openai",
    "fast",
)
_OPENAI_STRONG_MODELS = _model_list(
    "OPENAI_MODELS_STRONG",
    [
        os.environ.get("OPENAI_MODEL_STRONG", "gpt-5.6-luna"),
        "gpt-5.6-terra",
        "gpt-4o",
    ],
    "openai",
    "strong",
)

# 1. Gemini
for k in _GEMINI_KEYS:
    FALLBACK_CHAIN.append({
        "provider": "gemini",
        "models_fast": _GEMINI_FAST_MODELS,
        "models_strong": _GEMINI_STRONG_MODELS,
        "model_fast": _GEMINI_FAST_MODELS[0],
        "model_strong": _GEMINI_STRONG_MODELS[0],
        "key": k
    })

# 1.5 OpenRouter (Codex leverage)
for k in _OPENROUTER_KEYS:
    FALLBACK_CHAIN.append({
        "provider": "openrouter",
        "models_fast": _OPENROUTER_FAST_MODELS,
        "models_strong": _OPENROUTER_STRONG_MODELS,
        "model_fast": _OPENROUTER_FAST_MODELS[0],
        "model_strong": _OPENROUTER_STRONG_MODELS[0],
        "key": k,
    })

# 2. Claude
for k in _CLAUDE_KEYS:
    FALLBACK_CHAIN.append({
        "provider": "anthropic",
        "models_fast": [os.environ.get("ANTHROPIC_MODEL_FAST", "claude-3-haiku-20240307")],
        "models_strong": [os.environ.get("ANTHROPIC_MODEL_STRONG", "claude-3-5-sonnet-20241022")],
        "model_fast": os.environ.get("ANTHROPIC_MODEL_FAST", "claude-3-haiku-20240307"),
        "model_strong": os.environ.get("ANTHROPIC_MODEL_STRONG", "claude-3-5-sonnet-20241022"),
        "key": k
    })

# 3. OpenAI
for k in _OPENAI_KEYS:
    FALLBACK_CHAIN.append({
        "provider": "openai",
        "models_fast": _OPENAI_FAST_MODELS,
        "models_strong": _OPENAI_STRONG_MODELS,
        "model_fast": _OPENAI_FAST_MODELS[0],
        "model_strong": _OPENAI_STRONG_MODELS[0],
        "key": k
    })

_PROVIDER_ORDER = [
    provider.strip()
    for provider in os.environ.get("PRGG_PROVIDER_ORDER", "").split(",")
    if provider.strip()
] or _PRGG_CONFIG.get("provider_order", [])
if isinstance(_PROVIDER_ORDER, list) and _PROVIDER_ORDER:
    order_index = {str(provider): index for index, provider in enumerate(_PROVIDER_ORDER)}
    FALLBACK_CHAIN.sort(key=lambda cfg: order_index.get(cfg["provider"], len(order_index)))

if not FALLBACK_CHAIN:
    PROVIDER = "offline"
else:
    PROVIDER = "litellm-router"

print(f"[config] Provider: {PROVIDER}  Available Models in Fallback Chain: {len(FALLBACK_CHAIN)}")

# Cyclic iterators round-robin keys inside every provider pool.
_provider_cycles = {
    provider: itertools.cycle([cfg for cfg in FALLBACK_CHAIN if cfg["provider"] == provider])
    for provider in KEY_PROVIDER_META
    if any(cfg["provider"] == provider for cfg in FALLBACK_CHAIN)
}

MIN_INTERVAL = float(os.environ.get("LLM_DELAY_S", "13"))
PROVIDER_MIN_INTERVALS = {
    "gemini": float(os.environ.get("GEMINI_DELAY_S", str(MIN_INTERVAL))),
    "openrouter": float(os.environ.get("OPENROUTER_DELAY_S", "0")),
    "openai": float(os.environ.get("OPENAI_DELAY_S", "0")),
    "anthropic": float(os.environ.get("ANTHROPIC_DELAY_S", "0")),
}
_key_last_ts: dict[str, float] = {}


# ── offline diff-parsing mock ─────────────────────────────────────────────────

def _make_offline_claim(messages: list[dict]) -> dict:
    """
    Build a best-effort offline claim by parsing the diff and PR description
    embedded in the messages. Lets the Gate run on real diff content with no key.
    """
    diff_text = ""
    pr_desc = ""
    for msg in messages:
        content = msg.get("content", "")
        if "--- a/" in content or "+++ b/" in content:
            diff_text = content
        if "PR Description:" in content:
            lines = content.split("\n")
            in_desc = False
            desc_lines: list[str] = []
            for ln in lines:
                if ln.startswith("PR Description:"):
                    in_desc = True
                    desc_lines.append(ln.replace("PR Description:", "").strip())
                elif in_desc and ln.startswith("---"):
                    break
                elif in_desc:
                    desc_lines.append(ln)
            pr_desc = " ".join(desc_lines[:3]).strip()

    claimed_file = "unknown"
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            if path.startswith(("b/", "a/")):
                path = path[2:]
            if path != "/dev/null":
                claimed_file = path
                break

    line_range = "N/A"
    for line in diff_text.splitlines():
        if line.startswith("@@"):
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) else 1
                line_range = f"{start}-{start + count - 1}"
            break

    desc_short = pr_desc[:200] if pr_desc else f"offline mock for {claimed_file}"
    return {
        "bug_type":    "OFFLINE_PARSED",
        "file":        claimed_file,
        "line_range":  line_range,
        "description": desc_short,
        "confidence":  0.75,
        "w_what":      pr_desc[:150] or "Offline mock.",
        "w_why":       "Offline mode.",
        "w_impact":    "Offline mode.",
        "w_evidence":  f"Diff: {claimed_file} @ {line_range}",
        "w_who":       "Offline mode.",
    }


# ── LLM caller with dual-key rotation ────────────────────────────────────────

def call_llm(
    messages:        list[dict],
    model:           str | None = None,
    temperature:     float = 0.0,
    response_format: dict | None = None,
) -> str:
    """
    Call LLM using LiteLLM with robust BYOK fallback (Gemini -> Claude -> OpenAI).
    """
    if PROVIDER == "offline":
        print("[config] WARNING: No API key found — offline mock mode.")
        return json.dumps(_make_offline_claim(messages))

    tier = "strong" if "strong" in str(model) else "fast"
    
    # Build rotation list provider-by-provider. Each provider starts with the
    # next key in its own cycle, then falls through to the rest of that pool.
    rotation = []
    ordered_providers: list[str] = []
    for cfg in FALLBACK_CHAIN:
        if cfg["provider"] not in ordered_providers:
            ordered_providers.append(cfg["provider"])

    for provider in ordered_providers:
        provider_entries = [c for c in FALLBACK_CHAIN if c["provider"] == provider]
        cycle = _provider_cycles.get(provider)
        if cycle:
            primary = next(cycle)
            rotation.append(primary)
            rotation.extend([c for c in provider_entries if c != primary])
        else:
            rotation.extend(provider_entries)
    
    last_exc = None
    
    for cfg in rotation:
        api_key = cfg["key"]
        provider = cfg["provider"]
        target_models = cfg.get(f"models_{tier}") or [cfg[f"model_{tier}"]]
        
        # Optional per-provider pacing, useful for low free-tier Gemini quotas.
        min_interval = PROVIDER_MIN_INTERVALS.get(provider, 0.0)
        if min_interval > 0:
            since_last = time.monotonic() - _key_last_ts.get(api_key, 0.0)
            if since_last < min_interval and _key_last_ts.get(api_key, 0.0) > 0:
                wait = min_interval - since_last
                print(f"[config] Rate pacing ({provider}): {wait:.1f}s …", flush=True)
                time.sleep(wait)
        
        for target_model in target_models:
            try:
                _key_last_ts[api_key] = time.monotonic()

                if provider in {"openai", "openrouter", "gemini"}:
                    from openai import OpenAI

                    base_url = None
                    extra_headers = None
                    if provider == "openrouter":
                        base_url = "https://openrouter.ai/api/v1"
                        extra_headers = {
                            "HTTP-Referer": "https://github.com/Abhinav-143x/codex-hackathon",
                            "X-Title": "PR Grounding Gate",
                        }
                    elif provider == "gemini":
                        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

                    client = OpenAI(api_key=api_key, base_url=base_url)
                    kwargs = {
                        "model": target_model,
                        "messages": messages,
                        "temperature": temperature,
                    }
                    if response_format and provider == "openai":
                        kwargs["response_format"] = response_format
                    if extra_headers:
                        kwargs["extra_headers"] = extra_headers

                    response = client.chat.completions.create(**kwargs)
                    return response.choices[0].message.content or ""

                if provider == "anthropic":
                    import requests

                    system = "\n".join(
                        str(m.get("content", "")) for m in messages if m.get("role") == "system"
                    )
                    anthropic_messages = [
                        {"role": m.get("role", "user"), "content": str(m.get("content", ""))}
                        for m in messages
                        if m.get("role") != "system"
                    ]
                    payload = {
                        "model": target_model,
                        "max_tokens": 1200,
                        "temperature": temperature,
                        "system": system,
                        "messages": anthropic_messages,
                    }
                    response = requests.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": api_key,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        json=payload,
                        timeout=60,
                    )
                    response.raise_for_status()
                    data = response.json()
                    parts = data.get("content", [])
                    return "".join(part.get("text", "") for part in parts if part.get("type") == "text")

                raise RuntimeError(f"Unsupported provider: {provider}")
                
            except Exception as exc:
                last_exc = exc
                err_str = str(exc)
                
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                    print(f"[config] 429/Quota on {provider} ({target_model}) — rotating to fallback immediately …", flush=True)
                    _key_last_ts[api_key] = time.monotonic() + 60.0
                    break
                else:
                    print(f"[config] LLM call failed on {provider} ({target_model}): {exc}. Trying fallback...")
                    continue
                
    raise RuntimeError(
        f"[config] All {len(rotation)} key(s) in fallback chain exhausted! Last error: {last_exc}"
    ) from last_exc

def model_for_tier(tier: str) -> str:
    """Return the tier identifier, which the router will use."""
    return tier
