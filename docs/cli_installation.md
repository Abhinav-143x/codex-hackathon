# CLI Installation and Demo Flow

This page is the quick operator guide for PR Grounding Gate.

## Install from GitHub

```bash
pip install git+https://github.com/Abhinav-143x/codex-hackathon.git
```

After installation, the package exposes the `prgg` command:

```bash
prgg --help
```

## Configure BYOK

Interactive setup:

```bash
prgg init
```

Import a generated multi-provider config:

```bash
prgg config import ./prgg-byok-config.json
```

Supported providers are Gemini, OpenRouter, OpenAI, and Anthropic. Keys can be stored in OS keyring, environment variables, or `~/.prgg/config.json`.

## Analyze a PR

```bash
prgg check https://github.com/npm/cli/pull/9473
```

The CLI fetches the PR body and diff, asks the proposer model for a claim, and then runs deterministic gate checks. The LLM proposes; the Gate decides.

## Adopt a Local Repo for Real Tests

```bash
prgg adopt https://github.com/psf/requests --pin-dir C:\tmp\prgg_repos\requests --test-command "python -m pytest tests/test_utils.py::test_parse_header_links"
```

Then run:

```bash
prgg check https://github.com/psf/requests/pull/7520
```

Adopted mode clones or reuses a local checkout, applies the PR patch, runs the pinned test command, and reports whether local execution supports or contradicts the claim.

## Generate Dashboard Data

```bash
python run_sample.py --all
python export_runs.py
```

The Vite web demo reads `vite_ui/src/data.json`.

## GitHub Action Flow

The repository includes `.github/workflows/slopper.yml`.

It runs two separate signals:

- Slopper: contributor/reputation signal.
- PR Grounding Gate: diff/claim verification signal.

These should stay separate. Reputation is not proof that a PR claim is grounded.

## Current Demo Links

- GitHub: https://github.com/Abhinav-143x/codex-hackathon
- Live demo: https://viteui-one.vercel.app
