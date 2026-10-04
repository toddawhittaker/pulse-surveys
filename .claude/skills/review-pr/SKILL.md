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

Every PR gets a security pass, whatever its lane: each security row below
that matches a changed path runs, so a diff matching both rows gets both
reviewers. When neither row matches, a generic pass runs: `app-security`
spawned with `model: sonnet`, told the diff matched no specialist row.
`spec-conformance` does not run per PR in either lane; spec drift is caught
at the epic boundary.

| Reviewer | Fires when a changed path matches |
|---|---|
| `privacy-authz` | `backend/app/views_sql/`, `backend/app/services/authz`, `backend/app/services/reporting.py`, `backend/app/services/benchmarks.py`, `backend/app/services/comparison_sets.py`, `backend/app/services/report_comments.py`, `backend/app/models/identity`, `backend/app/models/org`, `backend/migrations/`, `scripts/db-init/`, `scripts/seed.py`, `tests/conftest.py`, `tests/fixtures/`, `*audit*`, `*care*`, `*safety*`, or any test marked `invariant` |
| `app-security` | `backend/app/api/`, `backend/app/lti/`, `backend/app/models/lti.py`, `backend/app/config.py`, `backend/app/services/validity.py`, `backend/app/services/provisioning.py`, `backend/app/services/grading.py`, `backend/app/services/submissions.py`, `backend/app/services/survey_read.py`, `mock-lms/`, `mock-idp/`, `scripts/`, `Makefile`, `Dockerfile*`, `docker-compose*`, `pyproject.toml`, `frontend/package.json`, `.github/workflows/`, `tests/evals/`, `backend/app/ai/` |

`app-security`'s trigger reaches `tests/evals/` and `backend/app/ai/` because
its checklist now includes the eval-floor-decrease check, and a floor is only
diffable where it and its prompts live.

Some paths in these rows are light-lane code that still guards something:
the four services in the `privacy-authz` row apply n-threshold suppression
outside `views_sql/`; migrations carry grants; the test fixtures feed the
§4.1 suite; and the paths added to the `app-security` row hold LTI keys,
the development switch, the sanctioned fail-open, provisioning, grade
passback, and student reachability checks. A light ticket's security pass
must include the specialist who knows them.

`spec-conformance`, `data-model`, `lti-oidc`, `a11y-copy`, and `prompt-eval`
no longer run here — they run at the epic boundary alongside `epic-exit`, `invariant-coverage`,
`adr-docs-completeness`, `threat-model`, and `code-reviewer` (ADR 0004).
Exception: during an epic whose declared subject is a moved reviewer's specialty (an epic
integrating real LTI platforms re-lists `lti-oidc`, say), that reviewer runs
per-PR for that epic's tickets — the epic README says so at breakdown.

A docs-only diff gets the generic security pass alone. That is correct, not a
misconfiguration.

Tell the user which reviewers you are running and why **before** spawning them,
so a wrong gate is visible immediately rather than after the tokens are spent.

## 3. Run them

Run them **once, after the last code push**, against the final head SHA. A
review of an earlier head is stale: the merger refuses it, and so the work is
lost. Spawn the matching reviewers **in parallel, in the foreground** — one
message, multiple `Agent` calls. Foreground because background subagents lose
tools and you need their structured text back.

Give each: the PR number, the head SHA, the diff, the ticket the PR names, and
the list of changed files. The comment names the head SHA it covered.

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

`privacy-authz`, `app-security`

Then list every reviewer that did **not** run, with the reason. This includes
the five reviewers moved to the epic boundary (`spec-conformance`,
`data-model`, `lti-oidc`, `a11y-copy`, `prompt-eval`, unless step 2's
exception re-lists one for this epic) — a reviewer deleted from this file's table must never just vanish from
the silence accounting; it moved, and the comment says where.

```
_Not triggered: privacy-authz (no read-path or authz changes)._
_Not triggered: spec-conformance, data-model, lti-oidc, a11y-copy, prompt-eval
(run at the epic boundary, not per-PR)._
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

## 5. A fix round ends with one re-check

When findings come back and get fixed, the fix round runs only the targeted
tests locally and pushes once. Then the same reviewers run **one re-check
pass** on the new head, and the loop stops. **Verifying a fix yourself is not
the review** — it is the session that scoped the fix confirming the fix
matches the scope, which cannot notice a fix that is wrong in a way nobody
thought to scope. On PR #13, three consecutive rounds each found something in
the previous round's fixes, twice a defect *introduced by* a fix for that same
class of defect.

A HIGH found in the re-check is fixed, and that fix gets one more re-check on
its new head. Nothing else reopens the loop. The PR body records this stopping
rule, and every review it cites names the final head SHA. See
`docs/MISTAKES.md` entry 10.

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
