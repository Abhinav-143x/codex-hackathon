# PR Grounding Gate

> **AI reviewers tell maintainers what they think. PR Grounding Gate shows what can actually be verified.**

PR Grounding Gate is a local-first evidence layer for pull requests. A Proposer extracts the PR's claim, but deterministic Gate checks decide what evidence exists, what is missing, and whether a human maintainer still needs to review the claim.

This is not another generic AI code reviewer. It is a trust boundary for AI-generated PRs.

---

## What It Does

```text
Diff + PR description
        |
        v
Proposer
  - LLM if a key is configured
  - offline mock parser otherwise
        |
        v
Evidence Gate
  - coverage / changed-line grounding
  - syntax consistency via tree-sitter
  - test-execution availability
  - binary/image blind-spot detection
  - invisible Unicode detection
        |
        v
Verdict
  - grounded
  - ungrounded
  - needs-review
  - error
```

The Gate is deterministic. LLM output is treated as a claim to verify, not proof.

---

## Current Status

| Capability | Status |
|---|---|
| Local sample runner | Works |
| Live GitHub PR URL via CLI | Works |
| GitHub CLI fetch path | Works |
| Local `.diff` path via CLI | Works |
| Dashboard generation | Works |
| Dry-run GitHub PR comment | Works, never posts |
| CVE adapter | Works on one seed CVE |
| OS keyring / `~/.prgg/config.json` credential loading | Implemented |
| Pytest smoke suite | 8 passing tests |
| Adopted repo test execution | Works for pinned local clones; unpinned PRs route to `needs-review` |

Current sample-suite behavior is intentionally conservative: if test execution is only a stub, the verdict is not `grounded`.

---

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install typer requests unidiff coverage fastmcp tree-sitter-language-pack keyring pytest pygments openai setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e . --no-build-isolation
```

The `--no-build-isolation` flag avoids a network build-dependency fetch in restricted environments once `setuptools` and `wheel` are already installed in the venv.

---

## Configure A Model Key

The tool works offline, but real Proposer/Explainer calls need a key.

Supported credential sources, in order:

1. Process/user environment variables
2. `~/.prgg/config.json`
3. OS keyring entries written by `prgg init`
4. Offline mock mode

Supported variables:

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

The BYOK web builder exposes arbitrary key pools for each provider and `prgg config import` stores them in OS keyring when available.

Interactive setup:

```powershell
.\.venv\Scripts\prgg.exe init
```

No API keys are stored in this repository.

---

## Run It

Run all samples:

```powershell
.\.venv\Scripts\python.exe run_sample.py --all
```

Run one sample:

```powershell
.\.venv\Scripts\prgg.exe check 1_clean_grounded
```

Run a local diff file:

```powershell
.\.venv\Scripts\prgg.exe check samples\1_clean_grounded.diff
```

Run a real GitHub PR URL:

```powershell
.\.venv\Scripts\prgg.exe check https://github.com/npm/cli/pull/9473
```

Fetch through GitHub CLI and save as a live sample:

```powershell
.\.venv\Scripts\python.exe fetch_pr.py --pr https://github.com/npm/cli/pull/9473
```

Print a dry-run GitHub comment:

```powershell
.\.venv\Scripts\python.exe github_commenter.py --pr https://github.com/npm/cli/pull/9473
```

Run the seed CVE adapter:

```powershell
.\.venv\Scripts\python.exe benchmark\cve_adapter.py
```

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

---

## Best Demo PR

Use npm/cli PR #9473:

```text
https://github.com/npm/cli/pull/9473
```

It is the best current proof because:

- it is a real merged PR,
- it has a security-adjacent registry path validation claim,
- the CLI PR URL path works,
- the GitHub CLI fetch path works,
- the dry-run PR comment path works.

Do not claim this proves real npm test-suite execution yet. The current runner routes stubbed test execution to `needs-review`.

---

## Documentation

- [Deployable Demo Plan](docs/deployable_demo_plan.md)
- [Online Demo Plan](docs/online_demo_plan.md)
- [PR Research Matrix](docs/pr_research_matrix.md)

---

## What Is Still Left

Most important next fixes:

1. Expand real project test execution beyond adopted/pinned repos.
2. Expand the CVE benchmark beyond one seed sample.
3. Make coverage grounding stricter than changed-line overlap.
4. Add a narrative-risk check for claims like "validated upstream" or "safe".
5. Add a GitHub Action that runs in dry-run comment mode by default.

The right product path is local CLI first, then GitHub Action, then adopted-repo mode, then MCP server integration, and only later a hosted service.
