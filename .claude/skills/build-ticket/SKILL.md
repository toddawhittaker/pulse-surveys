---
name: build-ticket
description: Build one ticket through the test-author → implementer → arbitrator loop. Use when the user says "build E0-05", "build ticket 3", or asks to implement a ticket from docs/tickets/. Cuts the seam branch, runs tests-first, and stops at a PR without merging.
---

# Build a ticket

Drives one ticket from `docs/tickets/` to an open pull request. You orchestrate;
the subagents do the work.

`$1` is the ticket ID (`E0-05`) or an ordinal the user gave loosely ("ticket 3"
means `E0-03`). If it is ambiguous, ask rather than guess — building the wrong
ticket wastes a whole loop.

## 1. Set up

Read the ticket file and `docs/tickets/e0/README.md` for its dependencies.

**Check its dependencies actually landed.** If the ticket depends on E0-04 and
E0-04 is not merged into the epic branch, stop and say so. Building against a
missing dependency produces work that has to be redone.

Confirm the epic branch exists and is current, then cut the seam branch named in
the ticket's `**Branch:**` field:

```bash
git checkout epic/e0-foundations && git pull
git checkout -b e0/<slug>
```

## 2. Test author

Spawn `test-author` with: the ticket's full text, the spec sections it names,
and the instruction to write failing tests for the acceptance criteria.

It cannot read `backend/app/**` or `frontend/src/**` — a hook denies it. That is
deliberate. If it reports that the ticket does not tell it enough to write a
test without guessing at an interface, **that is a defect in the ticket**. Stop,
tell the user, and fix the ticket first.

**Verify the tests fail for the right reason.** Run them. A test that errors on
import is not red, it is broken — send it back. A test that fails on an
assertion, or on a symbol the ticket says should exist, is correctly red.

Commit the tests alone:

```
e0/<slug>: failing tests for <ticket> acceptance criteria
```

## 3. Implementer

Spawn `implementer` **once**, with the ticket, the failing tests, and the path
to `docs/tickets/e0/.attempts/<TICKET>.md` if it exists.

For every subsequent attempt, **re-address the same agent by name with
`SendMessage`** rather than spawning a new one. That is what keeps it warm — it
remembers what it already tried, which is the whole point. Spawning a second
implementer throws that away and it will re-propose rejected approaches.

It cannot write to `tests/**`; a hook denies it.

Loop until the suite is green, or until it escalates.

## 4. Dispute, if one happens

The implementer writes `docs/disputes/<TICKET>-NN.md` and stops. Read
`docs/disputes/README.md` for what the file must contain; if it is missing
something, send it back before arbitrating — an arbitrator ruling on a
half-stated objection rules badly.

Spawn `arbitrator` **fresh**. Never the implementer's own session, and never
reuse a previous arbitrator — each dispute gets clean eyes.

Three outcomes:

1. **Test is wrong** → re-invoke `test-author` with the ruling. It fixes the
   test. The implementer resumes.
2. **Implementer is wrong** → `SendMessage` the warm implementer the
   arbitrator's *reasoning*, not an order. Reasoning is what stops it repeating
   the class of mistake.
3. **Spec is ambiguous** → **stop the whole loop and surface it to the user.**
   Do not proceed, do not pick a reading, do not let the implementer decide.
   This produces a spec edit or an ADR, and it is the reason the loop exists.
   Most genuine disputes are spec ambiguities surfacing; without this, whichever
   side is more stubborn quietly wins.

## 5. Finish

- `make ci` green locally.
- Remove any CI tolerance this ticket is responsible for — the ticket's
  acceptance criteria say which. A ticket that adds tests but leaves the test
  gate tolerant has not finished.
- Commit behavior changes and refactors separately, never in the same commit.
- Check whether the ticket made a construction decision the spec does not
  answer. If so, write the ADR **in this pull request** — that is the policy.
- Open the pull request into the epic branch with the template filled in: the
  seam, the §14.2 items that apply, security review findings, and anything
  deliberately deferred.
- Run `/review-pr` on it.

**Then stop.** Do not merge. Todd approves and merges; his written approval is
the trigger, never your own judgment that the work looks done.

## Throughout

The implementer appends every attempt to `docs/tickets/e0/.attempts/<TICKET>.md`
as it goes. If it does not, remind it.

**If a ticket spans two sittings, resume the session rather than starting a new
one.** Subagent transcripts persist with their session, so `claude --resume`
brings the warm implementer back with its reasoning intact — including why it
abandoned each approach. A *new* session cannot reach it, and falls back to the
attempt log, which carries the conclusions but not the reasoning. Tell the user
this if you notice a ticket is going to span a break.
