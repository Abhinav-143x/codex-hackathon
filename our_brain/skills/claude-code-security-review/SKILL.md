---
name: claude-code-security-review
description: "AI-powered security review of code changes (diffs or PRs). Performs structured vulnerability analysis — CWE classification, severity rating, data-flow tracing, business-logic review — and posts findings as structured output. Use when asked to run a security review, find vulnerabilities, check for injection issues, or review code for security risks."
---

# Claude Code Security Review

Source: https://github.com/anthropics/claude-code-security-review (MIT License, 5.2k+ stars)
Maintainer: Anthropic

An AI-powered security analysis tool that reviews code changes for vulnerabilities. Unlike traditional SAST tools that rely on pattern matching, this uses LLM reasoning to trace data flows and analyze business logic, which can uncover flaws like broken access control.

## What It Does

- Triggers on pull requests or explicit file/diff input
- Analyzes code changes (diffs) for potential security vulnerabilities
- Identifies: injection flaws, broken access control, cryptographic failures, insecure deserialization, missing validation, race conditions, and more
- Provides: **severity rating** (critical/high/medium/low), **CWE classification**, **affected code location**, and **suggested remediation**
- Posts structured findings as output (PR comments when used as a GitHub Action, structured text when used locally)

## Security Review Workflow

### Step 1: Scope the Review

- For a PR: review only the changed lines (diff), not the entire codebase
- For a file: review the entire file
- For a directory: review changed files only

### Step 2: Triage by Risk Surface

Prioritize analysis on:

1. Authentication / authorization boundaries
2. Input validation and sanitization paths
3. Data serialization / deserialization
4. Cryptographic operations
5. File system or shell interactions
6. Third-party API / data trust boundaries

### Step 3: For Each Finding, Output

```
SEVERITY: [CRITICAL | HIGH | MEDIUM | LOW]
CWE: [CWE-XXX: Name]
LOCATION: [file:line]
DESCRIPTION: [What the vulnerability is]
IMPACT: [What an attacker could do]
RECOMMENDATION: [How to fix it]
EVIDENCE: [Exact code quote from the diff]
```

### Step 4: Aggregate and Summarize

- Group by severity
- List blocking issues (CRITICAL/HIGH) first
- State explicitly if no significant issues were found

## Prior Art Note (relevant to PR Grounding Gate)

`claude-code-security-review` is a direct prior-art data point: it's an LLM analyzing code for security issues — the same category as Cursor Bugbot and CodeRabbit. Its 5.2k stars confirm strong market demand for AI-reviews-code tooling. But like all tools in this category, it judges the **narrative** of the code — what the code appears to do — rather than structurally verifying that the PR's own claim is grounded in the diff's structural facts (coverage, AST, real test execution). GhostCommit's disclosure (June 2026) shows exactly where this failure mode lives: an LLM reviewer inherits whatever blind spots its input pipeline creates. The deterministic Gate in PR Grounding Gate is the missing layer.

## Usage in This Workspace

Run this skill on any new code added to the PR Grounding Gate codebase before demo day to catch any introduced vulnerabilities, particularly around:
- The `config.py` API key handling (ensure no key leakage in logs)
- The `gate/test_exec_check.py` subprocess calls (shell injection risks)
- The `demo_ui/generator.py` HTML generation (XSS if run data is rendered unsanitized)
