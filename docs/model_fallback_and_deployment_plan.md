# Model Fallback and Deployment Plan

**Date:** July 14, 2026  
**Scope:** BYOK model routing, low-cost analysis model choice, OpenAI fallback addition, and deployment order.

---

## 1. Current Credential Access

Safe local check, without printing any secrets:

| Source | Current status |
|---|---|
| Environment variables | No supported key names visible |
| `~/.prgg/config.json` | File not present |
| OS keyring service `prgg` | No supported entries visible |

Supported key names:

```text
GEMINI_API_KEY_1
GEMINI_API_KEY_2
GEMINI_API_KEY_N
GEMINI_API_KEY
OPENROUTER_API_KEY
OPENROUTER_API_KEY_N
LLM_API_KEY
OPENAI_API_KEY
OPENAI_API_KEY_N
ANTHROPIC_API_KEY
ANTHROPIC_API_KEY_N
```

Supported keyring services use arbitrary provider pools:

```text
gemini_1
gemini_2
gemini_N
openrouter_1
openrouter_N
openai_1
openai_N
anthropic_1
anthropic_N
```

Interpretation:

- I cannot currently access a saved API key from this process.
- The app correctly falls back to offline mode.
- The user can enable live provider calls by running `prgg init` or setting one supported environment variable.
- Secrets should never be printed in terminal output, logs, docs, or run artifacts.

---

## 2. Previous BYOK Pattern

The original architecture in `New-Master.md` and `PR-Grounding-Gate-Master-Doc.md` favored:

1. BYOK only.
2. Local trust boundary.
3. Provider routing through OpenRouter or provider-native SDKs.
4. One fast model for claim extraction.
5. One strong model for hard cases.
6. Offline fallback for demos without keys.

The reviewer copy added a useful idea:

- detect available Gemini models from the Gemini model list endpoint,
- avoid hardcoded deprecated model names,
- rotate on quota or model failure,
- keep old/classic models as fallback only.

The active implementation now uses the same spirit, but avoids import-time network calls. It uses explicit fallback lists per provider and keeps old classic models as the last rung.

---

## 3. Active Fallback Order

Credential source order:

```text
environment -> ~/.prgg/config.json -> OS keyring -> offline mock
```

Provider order:

```text
Gemini key pool -> OpenRouter key pool -> Anthropic key pool -> OpenAI key pool -> offline mock
```

Within each provider, the active code round-robins keys, tries multiple models for that key, then rotates to the next key/provider on quota or provider failure.

Gemini fast:

```text
gemini-flash-lite-latest
gemini-2.0-flash-lite
gemini-2.0-flash-lite-001
gemini-2.5-flash
```

Gemini strong:

```text
gemini-flash-latest
gemini-3.5-flash
gemini-2.5-pro
gemini-2.5-flash
```

OpenRouter fast:

```text
openai/gpt-5.4-nano
openai/gpt-5.6-luna
openai/gpt-4o-mini
```

OpenRouter strong:

```text
openai/gpt-5.6-luna
openai/gpt-5.6-terra
openai/gpt-4o
```

OpenAI fast:

```text
gpt-5.4-nano
gpt-5.6-luna
gpt-4o-mini
```

OpenAI strong:

```text
gpt-5.6-luna
gpt-5.6-terra
gpt-4o
```

Override variables:

```text
GEMINI_MODELS_FAST
GEMINI_MODELS_STRONG
OPENROUTER_MODELS_FAST
OPENROUTER_MODELS_STRONG
OPENAI_MODELS_FAST
OPENAI_MODELS_STRONG
```

Each override is a comma-separated list.

---

## 4. Model Choice

### Best Low-Cost Default

Use `gemini-flash-lite-latest` as the default Proposer model when a Gemini key is available.

Reason:

- The imported event keys successfully called the Gemini OpenAI-compatible chat endpoint with this model.
- It keeps the demo on Google's current "latest" alias instead of a stale account-specific model rung.
- PR Grounding Gate's Proposer job is narrow structured extraction, not broad autonomous coding.

### Best Current Gemini Quality/Cost Escalation

Use `gemini-flash-latest`, then `gemini-3.5-flash`, as the stronger Gemini fallback.

Reason:

- Google exposes both aliases in the current model list for these event keys.
- `gemini-flash-latest` keeps the default strong path on a moving current alias, with `gemini-3.5-flash` as an explicit fallback.
- It keeps the same OpenAI SDK adapter path already used by `config.py`.

### Best Low-Cost OpenAI Default

Use `gpt-5.4-nano` as the cheapest OpenAI extraction fallback.

Reason:

- OpenAI pricing lists `gpt-5.4-nano` below `gpt-5.4-mini` and below `gpt-5.6-luna` for short-context standard usage.
- The Proposer can run cheaply on narrow extraction tasks.

### Best OpenAI Quality/Cost Escalation

Use `gpt-5.6-luna`, then `gpt-5.6-terra`.

Reason:

- OpenAI docs describe Luna as the cost-sensitive high-volume GPT-5.6 option.
- Terra is the balance point between intelligence and cost.
- Sol should be reserved for rare hard cases, not default PR triage.

### Classic Fallback

Keep `gpt-4o-mini` and `gpt-4o` as legacy fallbacks.

Reason:

- They are useful if an account or gateway exposes classic model IDs but not the newest family yet.
- They should not be the first choice for new deployments.

---

## 5. Sources Checked

- Google Gemini model-list probe with the event keys returned `gemini-flash-lite-latest`, `gemini-flash-latest`, `gemini-2.5-flash`, `gemini-2.5-pro`, and `gemini-3.5-flash`.
- Live OpenAI-compatible Gemini call succeeded with `gemini-flash-lite-latest`.
- OpenAI models page: GPT-5.6 Sol is the flagship, Terra balances intelligence/cost, and Luna is for cost-sensitive high-volume workloads.
- OpenAI pricing page: `gpt-5.4-nano` is cheaper than `gpt-5.6-luna` on short-context standard pricing, while Luna is the low-cost GPT-5.6 frontier option.

---

## 6. Deployment Plan

### Phase 1: Local CLI

Status: mostly working.

Proof:

```powershell
.\.venv\Scripts\prgg.exe --help
.\.venv\Scripts\prgg.exe check samples\1_clean_grounded.diff
.\.venv\Scripts\prgg.exe check https://github.com/psf/requests/pull/7520
```

Remaining:

- user supplies key,
- verify provider path with a real LLM call,
- keep offline mode available for no-key demos.

### Phase 2: Vite Evaluator

Status: working as static evaluator over saved runs, with a browser-only BYOK config builder.

Proof:

```powershell
cd vite_ui
npm run build
npm run dev -- --host 127.0.0.1
```

BYOK proof:

```powershell
.\.venv\Scripts\prgg.exe config template --out prgg-byok-config.json
.\.venv\Scripts\prgg.exe config import .\prgg-byok-config.json
.\.venv\Scripts\prgg.exe config status
```

The current schema supports arbitrary-length arrays:

```json
{
  "keys": {
    "gemini": ["..."],
    "openai": ["..."],
    "openrouter": ["..."],
    "anthropic": ["..."]
  }
}
```

Remaining:

- add local API bridge so the browser can trigger `prgg check`,
- keep browser execution optional because the CLI path is already the trust boundary.

### Phase 3: Local API Bridge

Add:

```text
POST /api/check
body: { "target": "https://github.com/owner/repo/pull/123" }
```

Behavior:

- validate target is a GitHub PR URL or local diff path,
- run the same pipeline as CLI,
- save `runs/<name>.json`,
- return the result to the Vite UI.

This should run only on localhost by default.

### Phase 4: GitHub Action Dry Run

Add a workflow that:

- runs on PR open/synchronize,
- runs `prgg check`,
- uploads JSON artifact,
- optionally writes a dry-run comment body as an artifact,
- does not post comments until explicitly enabled.

### Phase 5: Adopted Repo Real Tests

Make `prgg adopt <repo-url>` useful:

- clone repo,
- detect test command,
- pin test command outside PR control,
- run pinned tests during `prgg check`,
- convert stub `needs-review` into real `grounded` only when tests execute.

This is the biggest product step.

### Phase 6: MCP / Hermes

Current state:

- FastMCP server imports and smoke test passes.
- Hermes plugin wrapper loads, but Hermes runtime is not installed.

Next:

- install Hermes in a separate environment,
- load `.hermes/plugins/pr_grounding_gate/plugin.py`,
- verify tool registration through Hermes itself,
- keep Gate verdict deterministic and outside Hermes learning.

### Phase 7: Hosted Service

Defer until local trust is proven.

Hosted service adds:

- accounts,
- billing,
- secret management,
- public-network risk,
- artifact retention policy.

The right wedge is local-first first.
