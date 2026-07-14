# Online And Local Demo Plan

This plan replaces the temporary external note with the repo-owned demo path.

## Local Demo First

Use the local Vite app and CLI for the hackathon room demo.

```powershell
cd C:\Users\abhin\Projects\codex-hackathon
.\.venv\Scripts\prgg.exe config status
cd vite_ui
npm.cmd run dev -- --host 127.0.0.1 --port 5174
```

Open:

```text
http://127.0.0.1:5174/
```

Tabs:

- `Demo Board`: saved live PR runs, grouped by real GitHub state.
- `Analyze PR`: one PR URL box, one CLI command, saved-run detail view.
- `BYOK Config`: browser-side config builder; CLI imports secrets into OS keyring.

## Local Proof Path

`prgg adopt` can pin a deterministic test command for a local checkout.

Example already executed for Requests:

```powershell
.\.venv\Scripts\prgg.exe adopt https://github.com/psf/requests `
  --pin-dir C:\tmp\prgg_repos\requests `
  --test-command "C:\Users\abhin\Projects\codex-hackathon\.venv\Scripts\python.exe -m pytest tests/test_utils.py::test_parse_header_links"
```

Then:

```powershell
.\.venv\Scripts\prgg.exe check https://github.com/psf/requests/pull/7520
```

What happens:

1. PRGG fetches the PR diff/body.
2. The proposer creates the claim using live BYOK model fallback.
3. `test_exec_check` applies the PR diff to the adopted checkout.
4. The pinned test command runs.
5. PRGG reverses the patch and reports local proof pass/fail.

This is different from GitHub CI. GitHub CI is an upstream acceptance signal; adopted local tests are PRGG's reproducible evidence path.

## Hosted Demo Option

If judges need a URL without your machine:

- Use Streamlit Community Cloud as a temporary wrapper.
- Keep API keys in Streamlit Secrets, never in git.
- Add a short access code and expiry timestamp.
- Show preloaded `runs/*.json` by default.
- Allow live checks only after access-code entry and rate limiting.

Do not host provider keys in the frontend. Do not put API keys in nginx, static hosting, or browser storage.

## Streamlit Wrapper Shape

Files to add only for hosted demo:

```text
pitch/demo_app.py
pitch/requirements_demo.txt
```

Secrets in Streamlit settings:

```toml
GEMINI_API_KEY = "..."
OPENAI_API_KEY = "..."
DEMO_ACCESS_CODE = "..."
DEMO_EXPIRES_UTC = "2026-07-16T23:59:59Z"
```

The hosted app should call `run_single()` for live checks and read `runs/*.json` for the static board.

## Demo Story

- Merged PRs can still be `needs-review` if PRGG has not locally reproduced the proof.
- Open PRs can be `ungrounded` if the claim/body/diff/test evidence disagree.
- GitHub state is displayed separately from PRGG verdict.
- Local adopted tests are the strongest deterministic proof path.
- BYOK routing is local: browser config -> CLI import -> OS keyring -> model fallback.

## Retraction

After judging:

1. Revoke event keys.
2. Delete the hosted app if one exists.
3. Delete any demo branch.
4. Confirm no secrets were committed.
