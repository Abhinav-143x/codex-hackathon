# Environment Variables - PR Grounding Gate

> Never commit `.env` files or raw keys to git. This file is documentation only.

Keys can be supplied through:

1. Process or user environment variables
2. `~/.prgg/config.json`
3. OS keyring entries written by `prgg init`
4. Offline mock mode when no key is visible

Current safe check found no supported key visible to this process.

---

## Gemini

Supported key variables:

```powershell
setx GEMINI_API_KEY_1 "<key-1>"
setx GEMINI_API_KEY_2 "<key-2>"
setx GEMINI_API_KEY_3 "<key-3>"
setx GEMINI_API_KEY "<single-key-alias>"
setx LLM_DELAY_S "13"
```

Any numbered `GEMINI_API_KEY_N` variable is supported. The BYOK web builder also supports arbitrary-length key pools for every provider and the CLI imports them into OS keyring when available.

Config rotates visible Gemini keys round-robin and moves to the next available key on quota errors.

Gemini model fallback variables:

| Env Var | Default |
|---|---|
| `GEMINI_MODELS_FAST` | `gemini-flash-lite-latest,gemini-2.0-flash-lite,gemini-2.0-flash-lite-001,gemini-2.5-flash` |
| `GEMINI_MODELS_STRONG` | `gemini-flash-latest,gemini-3.5-flash,gemini-2.5-pro,gemini-2.5-flash` |

---

## OpenRouter

Set `OPENROUTER_API_KEY` to route through OpenRouter:

```powershell
setx OPENROUTER_API_KEY "<openrouter-key>"
setx OPENROUTER_API_KEY_1 "<openrouter-key-1>"
setx OPENROUTER_MODELS_FAST "openai/gpt-5.4-nano,openai/gpt-5.6-luna,openai/gpt-4o-mini"
setx OPENROUTER_MODELS_STRONG "openai/gpt-5.6-luna,openai/gpt-5.6-terra,openai/gpt-4o"
```

`LLM_API_KEY` is also accepted as an OpenRouter-compatible alias.

---

## OpenAI

Set `OPENAI_API_KEY` to use OpenAI directly:

```powershell
setx OPENAI_API_KEY "<openai-key>"
setx OPENAI_API_KEY_1 "<openai-key-1>"
setx OPENAI_MODELS_FAST "gpt-5.4-nano,gpt-5.6-luna,gpt-4o-mini"
setx OPENAI_MODELS_STRONG "gpt-5.6-luna,gpt-5.6-terra,gpt-4o"
```

The classic `gpt-4o-mini` and `gpt-4o` models are retained as final fallback rungs for older account or gateway availability.

---

## Anthropic

Set `ANTHROPIC_API_KEY` to use Anthropic as a later fallback:

```powershell
setx ANTHROPIC_API_KEY "<anthropic-key>"
```

Current defaults:

| Env Var | Default |
|---|---|
| `ANTHROPIC_MODEL_FAST` | `claude-3-haiku-20240307` |
| `ANTHROPIC_MODEL_STRONG` | `claude-3-5-sonnet-20241022` |

---

## GitHub CLI

GitHub CLI can be used for fetch/comment workflows separately from LLM keys.

To verify:

```powershell
gh auth status
```

---

## Running The Pipeline

```powershell
.\.venv\Scripts\prgg.exe --help
.\.venv\Scripts\prgg.exe check samples\1_clean_grounded.diff
.\.venv\Scripts\prgg.exe check https://github.com/psf/requests/pull/7520
```

## BYOK Config Commands

```powershell
.\.venv\Scripts\prgg.exe config template --out prgg-byok-config.json
.\.venv\Scripts\prgg.exe config import .\prgg-byok-config.json
.\.venv\Scripts\prgg.exe config status
```

Use `PRGG_HOME` to test without touching the normal user config:

```powershell
$env:PRGG_HOME = "$PWD\scratch\prgg-home"
```

For a live provider proof after setting a key:

```powershell
.\.venv\Scripts\python.exe -c "import config; print(config.PROVIDER, len(config.FALLBACK_CHAIN))"
```

Expected result after a key is visible: provider is not `offline` and fallback chain length is greater than `0`.
