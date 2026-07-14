# BYOK CLI + Web Demo Flow

**Goal:** prove that PR Grounding Gate can be configured by a maintainer with their own model keys, without hosting secrets or adding a backend service.

---

## 1. What Works For Demo

The demo has two pieces:

1. **Web config builder** in the Vite app.
2. **CLI config import/status** in `prgg`.

The browser does not upload keys anywhere. It only creates a JSON file. The CLI imports that JSON and stores secrets in OS keyring when available.

Implemented CLI commands:

```powershell
.\.venv\Scripts\prgg.exe config template --out prgg-byok-config.json
.\.venv\Scripts\prgg.exe config import .\prgg-byok-config.json
.\.venv\Scripts\prgg.exe config status
```

---

## 2. Start The Web App

```powershell
cd vite_ui
npm run dev -- --host 127.0.0.1
```

Open:

```text
http://127.0.0.1:5174/
```

Use the `BYOK Config` tab.

---

## 3. Build A Config

In the browser:

1. Paste keys for the providers you want. Each provider has an add/remove key pool for demo rotation.
2. Adjust model fallback lists if needed.
3. Keep provider order as:

```text
gemini, openrouter, openai, anthropic
```

4. Download:

```text
prgg-byok-config.json
```

You can also drag/drop an existing config JSON back into the page.

---

## 4. Import Into CLI

From the repo root:

```powershell
.\.venv\Scripts\prgg.exe config import .\prgg-byok-config.json
```

The import command:

- reads provider key pools, including any number of Gemini/OpenAI/OpenRouter/Anthropic keys,
- stores keys in OS keyring when possible,
- stores model lists and provider order in `~/.prgg/config.json`,
- does not print secrets.

If OS keyring is unavailable and you intentionally accept local plaintext key storage:

```powershell
.\.venv\Scripts\prgg.exe config import .\prgg-byok-config.json --allow-plain-file
```

Do not use `--allow-plain-file` for a public demo unless you explain the tradeoff.

For isolated demo/testing without touching the real user config:

```powershell
$env:PRGG_HOME = "$PWD\scratch\prgg-home"
.\.venv\Scripts\prgg.exe config import .\prgg-byok-config.json
```

---

## 5. Check Config Status

```powershell
.\.venv\Scripts\prgg.exe config status
```

This prints:

- which key slots are present,
- provider order,
- fast and strong model fallback lists.

It does not print key values.

For the current demo, import event keys through this path. Avoid showing raw values on screen while recording.

---

## 6. Generate A Template From CLI

```powershell
.\.venv\Scripts\prgg.exe config template --out prgg-byok-config.json
```

This creates the same schema the browser builder uses.

---

## 7. Run A PR Check

```powershell
.\.venv\Scripts\prgg.exe check https://github.com/psf/requests/pull/7520
```

Expected behavior:

- If keys are configured, the Proposer uses the fallback router.
- Keys are tried round-robin inside each provider; quota errors move immediately to the next key/provider.
- If no keys are visible, the Proposer uses offline mock extraction.
- The Gate remains deterministic either way.

---

## 8. Ponytail Notes

What we deliberately did not build:

- hosted secret storage,
- OAuth,
- account system,
- browser-to-local command execution,
- a new backend server.

Those are unnecessary for the first demo. The minimum proof is:

```text
web generates config -> CLI imports config -> CLI runs PR check
```

That proves the BYOK path with the fewest moving parts.
