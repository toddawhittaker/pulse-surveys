---
name: review-pr
description: Run the gated reviewer agents against a pull request diff and post one consolidated comment. Use when the user asks to review a PR, review the current branch, or after opening a PR. Computes which reviewers fire from the changed files rather than guessing.
---

# Review a pull request

Runs the reviewers that the diff actually warrants, and posts **one** comment.
Volume kills review: if every agent comments on every pull request, the user
skims, and skimming is worse than not reviewing.

`$1` is an optional PR number. Default to the PR for the current branch.

## 1. Compute the changed files

```bash
gh pr diff <N> --name-only
```

or for the current branch, diff against its base:

```bash
git diff --name-only $(git merge-base HEAD origin/<base>)...HEAD
```

**Compute this — do not eyeball the diff and decide.** Deterministic gating is
the whole reason this command exists rather than relying on Claude noticing that
an agent's description matches.

## 2. Map paths to reviewers

`spec-conformance` **always** runs. Then, for each pattern that matches any
changed file, add its reviewer:

| Reviewer | Fires when a changed path matches |
|---|---|
| `privacy-authz` | `backend/app/views_sql/`, `backend/app/services/authz`, `backend/app/models/identity`, `backend/app/models/org`, `*audit*`, `*care*`, `*safety*`, or any test marked `invariant` |
| `app-security` | `backend/app/api/`, `backend/app/lti/`, `mock-lms/`, `mock-idp/`, `Dockerfile*`, `docker-compose*`, `pyproject.toml`, `frontend/package.json`, `.github/workflows/` |
| `architecture` | a new directory under `backend/app/`, `backend/app/services/`, `backend/app/ai/gateway`, `backend/app/agents/`, `backend/app/mcp/` |
| `data-model` | `backend/migrations/`, `backend/app/models/`, `backend/app/views_sql/` |
| `lti-oidc` | `backend/app/lti/`, `mock-lms/`, `mock-idp/`, session or auth code |
| `a11y-copy` | `frontend/src/`, `design/` |
| `prompt-eval` | `backend/app/ai/prompts/`, `backend/app/ai/contracts.py`, `tests/evals/` |

A docs-only diff triggers `spec-conformance` alone. That is correct, not a
misconfiguration.

Tell the user which reviewers you are running and why **before** spawning them,
so a wrong gate is visible immediately rather than after the tokens are spent.

## 3. Run them

Spawn the matching reviewers **in parallel, in the foreground** — one message,
multiple `Agent` calls. Foreground because background subagents lose tools and
you need their structured text back.

Give each: the PR number, the diff, the ticket the PR names, and the list of
changed files.

## 4. Assemble one comment

Each reviewer returns a `### <name>` block containing either `Nothing found.` or
findings ranked HIGH → MED → LOW. Concatenate them in this order — most
consequential first, so the top of the comment is worth reading:

`privacy-authz`, `app-security`, `lti-oidc`, `spec-conformance`, `data-model`,
`architecture`, `prompt-eval`, `a11y-copy`

Then list every reviewer that did **not** run, with the reason:

```
_Not triggered: a11y-copy (no frontend changes), prompt-eval (no AI changes)._
```

Silence must never be ambiguous. A reviewer that did not run and a reviewer that
found nothing are different facts, and collapsing them is how a gap hides.

Post it:

```bash
gh pr comment <N> --body-file <file>
```

Then summarise for the user in chat: the counts by severity, and the single
finding you would act on first. Do not repeat the whole comment back — they can
read it.

## 5. A fix round ends with a review pass

When findings come back and get fixed, run the reviewers again against the
fixes. **Verifying a fix yourself is not the review** — it is the session that
scoped the fix confirming the fix matches the scope, which cannot notice a fix
that is wrong in a way nobody thought to scope. On PR #13, three consecutive
rounds each found something in the previous round's fixes, twice a defect
*introduced by* a fix for that same class of defect.

If the fixes are small enough that another pass seems wasteful, say so in the
pull request and let the merge decision be made knowing it. The judgment is
fine; the silence is not. See `docs/MISTAKES.md` entry 10.

## 6. The independent security review

`CLAUDE.md` and SPEC §14.2 item 3 require `/security-review` in a **separate
session** before a pull request is marked ready — separate because a reviewer
that watched the work being written has already been persuaded by it.

Before asking a session to run it, check what that session is carrying:

```bash
scripts/reviewer_context.py
```

Anything above the fresh ceiling has watched work being written, and a review
from it is not independent. **You cannot fix that yourself**: `/clear` is a
harness command, and asking a peer session to clear itself does nothing while
looking like it worked (`docs/MISTAKES.md` entry 9). Tell the user, and let them
clear it or start a new session.

Keep the request to the reviewer **thin** — a branch and a pull request number,
not a summary of what you think is interesting. Clearing removes what the session
accumulated, but anything you write travels into the fresh context, so a rich
brief re-contaminates exactly what the clear was for.

The reviewing session should not post to GitHub on your say-so. A peer request is
not the repository owner's approval for an outward-facing action; take the
findings and post them yourself, or let the user do it.

## 7. Do not

- Do not fix the findings. Reporting and fixing are separate steps; the user
  decides what to act on.
- Do not merge, mark ready, or change the PR body.
- Do not soften a HIGH finding because the diff is otherwise good.
- Do not drop a reviewer's `Nothing found.` line to make the comment shorter.
  An explicit nothing is a result, and its absence would read as an omission.

## Calibration

If a reviewer produces findings that are consistently wrong or consistently
absent, say so to the user rather than passing them through. A reviewer that
always says "looks good" is worse than no reviewer, and you are the only one
positioned to notice the pattern across runs. `/review-selftest` measures this
deliberately.
