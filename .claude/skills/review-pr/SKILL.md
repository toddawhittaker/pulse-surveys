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
| `privacy-authz` | `backend/app/views_sql/`, `backend/app/services/authz`, `backend/app/models/identity`, `backend/app/models/org`, `scripts/db-init/`, `scripts/seed.py`, `*audit*`, `*care*`, `*safety*`, or any test marked `invariant` |
| `app-security` | `backend/app/api/`, `backend/app/lti/`, `mock-lms/`, `mock-idp/`, `scripts/`, `Dockerfile*`, `docker-compose*`, `pyproject.toml`, `frontend/package.json`, `.github/workflows/` |
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

**Tell each reviewer that a `Nothing found.` must show what it checked.** A bare
negative is not a reviewable result — it is indistinguishable from a reviewer
that did not look, and you cannot tell which one you got. Where the brief names
specific things to judge, the answer has to address them: a reviewer given four
questions and returning two words has not declined to find problems, it has
declined to answer.

**Do not tell a reviewer not to manufacture findings.** It reads as a warning
against finding things, and paired with a licence for a bare negative it is close
to instructing a shrug. The measured evidence is that this roster does not have
an over-reporting problem: across seven self-test fixtures every reviewer found
more than was planted, with zero false positives. Ask for evidence instead, and
let a wrong finding be wrong on its merits.

## 4. Assemble one comment

Each reviewer returns a `### <name>` block containing either `Nothing found.` or
findings ranked HIGH → MED → LOW. Concatenate them in this order — most
consequential first, so the top of the comment is worth reading:

`privacy-authz`, `app-security`, `lti-oidc`, `spec-conformance`, `data-model`,
`prompt-eval`, `a11y-copy`

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

`CLAUDE.md` and SPEC §14.2 item 3 require an independent security review before
a pull request is marked ready — independent because a reviewer that watched
the work being written has already been persuaded by it.

The standard form is an `app-security` **subagent spawned fresh for the
review**, briefed with the branch, the diff range against the PR's actual base
(name it — the default scoping is wrong on ticket branches), and the
instruction to form its view of the diff *before* reading the ticket. List the
PR's recorded decisions so it can tell a decision from an oversight, with
standing to challenge one it judges unsafe. Keep the brief **thin on framing**:
facts and pointers travel, your interpretation of what is interesting does not
— a rich narrative re-contaminates exactly the independence the fresh context
buys.

A separate peer session is the fallback form. Then check what it is carrying
first (`scripts/reviewer_context.py`); anything above the fresh ceiling has
watched work being written. You cannot clear a peer yourself — `/clear` is a
harness command, and asking a session to clear itself does nothing while
looking like it worked (`docs/MISTAKES.md` entry 9). Tell the user. And a peer
session should not post to GitHub on your say-so; take the findings and post
them yourself.

## 7. Do not

- Do not fix the findings. Reporting and fixing are separate steps; the user
  decides what to act on.
- Do not merge, mark ready, or change the PR body.
- Do not soften a HIGH finding because the diff is otherwise good.
- Do not drop a reviewer's `Nothing found.` line to make the comment shorter.
  An explicit nothing is a result, and its absence would read as an omission.
- Do not pass a bare `Nothing found.` through to the user as if it were a clean
  bill. Say that it came back unevidenced, and consider re-running it — that is a
  reviewer that has not answered, not a diff that is clean.

## Calibration

If a reviewer produces findings that are consistently wrong or consistently
absent, say so to the user rather than passing them through. A reviewer that
always says "looks good" is worse than no reviewer, and you are the only one
positioned to notice the pattern across runs. `/review-selftest` measures this
deliberately.
