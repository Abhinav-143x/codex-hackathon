# PR Research Matrix

Generated: `2026-07-14`

This matrix is the demo truth source for PR status, PR body signal, and PRGG saved verdicts. GitHub state is kept separate from project-specific or internal landing signals.

## Status Caveat

TensorFlow PR [tensorflow/tensorflow #120484](https://github.com/tensorflow/tensorflow/pull/120484) is `OPEN` according to GitHub. Its PR body references a superseded PR, so the demo should say: "GitHub still shows open; the project may have internal or follow-up handling, but PRGG does not claim this is GitHub-merged."

## Saved PRGG Runs

| PR | Author | Lang | GitHub state | Size | PRGG verdict | Verdict match |
| --- | --- | --- | --- | ---: | --- | --- |
| [npm/cli #9473](https://github.com/npm/cli/pull/9473) | Abhinav-143x | JavaScript | `MERGED` | 3 files, +174/-5 | `needs-review` | Claim matches the security intent, but PRGG keeps it in review because repo-specific tests are not adopted yet and security claims need stronger proof. |
| [psf/requests #7520](https://github.com/psf/requests/pull/7520) | nyxst4ck | Python | `OPEN` | 2 files, +7/-1 | `needs-review` | Claim matches the `split("=", 1)` parsing fix; review remains because test execution is a stub for this repo. |
| [psf/requests #7543](https://github.com/psf/requests/pull/7543) | Flimm | Metadata | `OPEN` | 1 file, +3/-0 | `needs-review` | Claim matches metadata additions, but proposer output left `w_who` insufficient. This is a good 5W demo. |
| [python/cpython #153680](https://github.com/python/cpython/pull/153680) | tonghuaroot | Python | `OPEN` | 3 files, +25/-1 | `needs-review` | Claim matches invalid UTF-8 handling in `zipimport`; validation/security wording triggers review. |
| [tensorflow/tensorflow #120484](https://github.com/tensorflow/tensorflow/pull/120484) | Abhinav-143x | C++ | `OPEN` | 2 files, +32/-7 | `needs-review` | Claim matches index validation before output writes; GitHub is open despite internal/project caveat. |
| [protocolbuffers/protobuf #27848](https://github.com/protocolbuffers/protobuf/pull/27848) | Abhinav-143x | C/Ruby | `CLOSED` | 2 files, +7/-0 | `needs-review` | Claim matches null repeated enum handling; closed does not mean merged or rejected by PRGG. |
| [protocolbuffers/protobuf #27852](https://github.com/protocolbuffers/protobuf/pull/27852) | Abhinav-143x | C++/PHP | `OPEN` | 3 files, +145/-6 | `needs-review` | Claim matches PHP hardening; security-ish scope remains review-gated. |

## Connector-Fetched Backup PRs

These were fetched through the Codex GitHub integration after unauthenticated GitHub REST search hit rate limits.

| PR | Lang | GitHub state | Body / review signal | Demo use |
| --- | --- | --- | --- | --- |
| [pallets/flask #6013](https://github.com/pallets/flask/pull/6013) | Python | `MERGED` | Case-insensitive extension comparison for Jinja autoescape selection. | Tiny merged PR for a fast explanation. |
| [pallets/flask #6094](https://github.com/pallets/flask/pull/6094) | Python | `OPEN` | Body claims bracket-aware IPv6 host parsing and tests. | Clean open PR if we need a fresh live URL. |
| [vitejs/vite #22893](https://github.com/vitejs/vite/pull/22893) | TypeScript | `MERGED` | Scope walker fix for switch-case declarations, with review comments, approval, package preview, and ecosystem CI discussion. | Shows reviewer conversation and JS/TS coverage. |
| [django/django #21553](https://github.com/django/django/pull/21553) | Python | `MERGED` | Body includes an explicit AI-assistance disclosure and reviewer discussion. | Strong market signal: maintainers are already asking for AI disclosure and proof. |

## Grouping For The Demo Board

- `MERGED`: npm #9473, Flask #6013, Vite #22893, Django #21553.
- `OPEN`: Requests #7520, Requests #7543, CPython #153680, TensorFlow #120484, Protobuf #27852, Flask #6094.
- `CLOSED`: Protobuf #27848.
- Use saved PRGG runs for the live board and connector-fetched PRs as stage backup or market validation.

## What PRGG Should Claim

- PRGG verifies whether a generated claim is grounded in the diff and supporting evidence.
- PRGG does not infer maintainer intent from closed/open status.
- PRGG does not claim a PR is merged unless GitHub reports `merged_at`.
- PRGG routes security, validation, and incomplete 5W claims to human review until repo-specific tests are adopted.
