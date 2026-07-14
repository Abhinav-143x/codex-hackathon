---
name: dimillian-review-swarm
description: "Parallel read-only multi-agent review of a current git diff or explicit file scope to find behavioral regressions, security or privacy risks, performance or reliability issues, and contract or test coverage gaps. Use when asked for a review swarm, parallel review, diff review, regression review, security review, or high-signal issues plus a prioritized fix path without editing files."
---

# Review Swarm (Dimillian/Skills)

Source: https://github.com/Dimillian/Skills/tree/main/review-swarm (MIT License)

Review a diff with four read-only sub-agents in parallel, then have the main agent filter, order, and summarize only the issues that matter. This skill is **review-only**: sub-agents do not edit files, and the main agent does not apply fixes as part of this workflow.

## Step 1: Determine Scope and Intent

Prefer this scope order:

1. Files or paths explicitly named by the user
2. Current git changes
3. An explicit branch, commit, or PR diff requested by the user
4. Most recently modified tracked files, only if the user asked for a review and there is no clearer diff

If there is no clear review scope, stop and say so briefly.

When using git changes, choose the smallest correct diff command:

- unstaged work: `git diff`
- staged work: `git diff --cached`
- mixed staged and unstaged work: review both
- explicit branch or commit comparison: use exactly what the user requested

Before launching reviewers, read the closest local instructions and any relevant project docs for the touched area:

- `AGENTS.md`
- repo workflow docs
- architecture or contract docs for the touched module

Build a short **intent packet** for the reviewers:

1. What behavior is meant to change
2. What behavior should remain unchanged
3. Any stated or inferred constraints (compatibility, rollout, security, migration expectations)

If the user did not state the intent clearly, infer it from the diff and say that the inference may be incomplete.

## Step 2: Launch Four Read-Only Reviewers in Parallel

Launch four sub-agents when the scope is large enough for parallel review to help. For a tiny diff or one very small file, it is acceptable to review locally instead.

For every sub-agent:

- Give the same scope and the same intent packet
- State that the sub-agent is **read-only**
- Do not let the sub-agent edit files, run `apply_patch`, stage changes, commit, or perform any other state-mutating action
- Ask for concise findings only
- Ask for: file and line or symbol, issue, why it matters, recommended follow-up, and confidence
- Tell the sub-agent to avoid nits, style preferences, and speculative concerns without concrete impact
- Tell the sub-agent to send findings back to the main agent, not to the user

## Step 3: Aggregate, Deduplicate, and Prioritize

After all four sub-agents return:

1. Collect all findings into one list
2. Deduplicate findings that point to the same issue
3. Promote issues flagged by 2+ agents, or issues rated high-confidence by 1 agent
4. Discard nits, duplicates, and low-confidence findings from a single reviewer
5. Sort the remaining list by severity: blocking > high > medium > low
6. For each remaining issue, write: location, finding, why it matters, recommended action

## Step 4: Output

Produce a single, clean summary:

- **Pass / Needs-review / Blocked** verdict at the top
- Numbered list of issues (one per finding), sorted by severity
- Each issue: file + line, description, recommended follow-up
- If no meaningful issues were found, say so explicitly and briefly

Do **not** apply any changes. Do **not** open a follow-up task. Hand the prioritized list back to the user.

## Prior Art Note (relevant to PR Grounding Gate)

This skill is direct evidence for the PR Grounding Gate thesis: even a multi-agent, consensus-voting PR review system is still LLMs voting on LLMs — it catches narrative inconsistencies but cannot structurally verify that coverage increased on the claimed lines, or that the AST confirms what the description claims. The deterministic Gate in PR Grounding Gate closes exactly this gap.
