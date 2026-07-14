# Future Scope and Execution Planner

PR Grounding Gate already has the core verification loop:

```text
fetch PR -> propose claim -> run deterministic gates -> return verdict
```

The most important next step is making local test execution automatic and better classified.

## Current Gap

Today, `test_exec` works when a repo is manually adopted:

```text
clean clone
checkout base
apply PR diff
run pinned command
reverse patch
report result
```

The missing layer is an automatic planner that decides the correct clone, base commit, and test command for a new PR without manual setup.

## Why This Matters

Real open-source PRs are messy:

- some merged PRs are squash-merged or rebased, so the public PR diff may not apply to current `main`;
- some closed PRs are landed by internal tooling such as Copybara;
- some CI failures are unrelated to the PR claim;
- generated files and large build systems can make local reproduction too heavy;
- some tests are expected to fail in the external CI matrix even when the PR is valid.

So a failing local command must not automatically mean "bad PR." It may mean "not reproducible in this environment."

## Planned `auto-check` Flow

Future command:

```powershell
prgg auto-check https://github.com/owner/repo/pull/123
```

Planner steps:

```text
1. Fetch PR metadata, body, diff, CI state, and merge information.
2. Resolve the best base commit.
3. Create or reuse a clean local clone.
4. Detect changed language and package manager.
5. Parse "Tests run" from the PR body.
6. Inspect GitHub Actions and other CI config.
7. Pick the smallest relevant safe command.
8. Apply the patch.
9. Run the command with timeout and cleanup.
10. Classify the result.
```

## Better Result Taxonomy

`test_exec` should report more than pass/fail:

```text
passed
failed_claim_related
failed_environment
failed_unrelated_ci
diff_not_applicable
skipped_heavy_repo
skipped_internal_tooling
```

This lets the final verdict separate:

```text
claim contradicted
```

from:

```text
local reproduction unavailable
```

## GitHub Pages and Deployment

The live demo is deployed on Vercel:

```text
https://viteui-one.vercel.app
```

GitHub Pages is configured as a secondary static deployment target:

```text
https://abhinav-143x.github.io/codex-hackathon/
```

The workflow builds `vite_ui` and deploys `vite_ui/dist`. Pages must be enabled once at the repository settings/API level; after that, the workflow only deploys.

## Research Direction

The broader research direction is claim-grounded PR verification:

1. Let the LLM propose a structured claim.
2. Treat that claim as untrusted.
3. Verify it against changed code, test evidence, CI state, and repository context.
4. Route ambiguous or high-risk cases to maintainers.

The goal is not to replace human review. The goal is to protect maintainer attention by proving which claims are grounded and which need review.
