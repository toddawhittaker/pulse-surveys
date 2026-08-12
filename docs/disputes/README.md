# Disputes

When the implementer believes a test is wrong, it does not change the test. It
writes an objection here and stops. A separate arbitrator session rules.

The objection is **always written to a file**, even when the implementer's
context survives in the session. Three reasons: the arbitrator is a fresh
session and reads only what is written down; the pull request record needs it;
and a dispute that turns out to be a spec ambiguity has to become an ADR, which
needs the argument in durable form.

## File name

`docs/disputes/<TICKET>-<NN>.md` — for example `E0-09-01.md`. Number within the
ticket, starting at 01.

## Required contents

An objection missing any of these gets sent back before arbitration. An
arbitrator ruling on a half-stated objection rules badly, and the ruling is
binding on the loop.

```markdown
# E0-09-01 — <one-line summary of the disagreement>

**Ticket:** E0-09
**Test:** `tests/unit/test_role_assignment.py::test_cycle_rejected_at_depth_three`

## The test

<quote it, in full>

## What I believe it asserts incorrectly

<specific. "It expects a ValueError where the spec calls for the write to be
rejected at the database level" — not "this test seems wrong".>

## The spec text I am relying on

<quote the section, with its number. Quote enough to include the sentence
before and after — objections often quote accurately and still miss the
paragraph that settles it.>

## What I tried

<the approaches already attempted and why each failed. If the honest answer is
"one approach, which the test rejected," say that — it is a weaker objection and
the arbitrator should be able to see that it is.>

## Why I believe the test rather than my code is at fault

<the actual argument>
```

## What happens next

The arbitrator reaches one of exactly three outcomes:

1. **The test is wrong** — the test author is re-invoked with the ruling.
2. **The implementer is wrong** — it resumes with an explanation, not an order.
3. **The spec is ambiguous** — this is not an implementation decision. It goes
   to Todd and produces a spec edit or an ADR.

Outcome 3 is why the loop exists. Most genuine disputes are spec ambiguities
surfacing; without arbitration, whichever side is more stubborn quietly wins and
the ambiguity stays buried until it costs something.

## After the ruling

Append the outcome to the objection file, so the file records the whole
exchange rather than only one side of it:

```markdown
## Ruling

**Outcome 2 — implementer wrong.** <the arbitrator's reasoning>
```

Objection files are committed with the ticket's branch. They are part of the
record, not scratch work — the reasoning in them is often the only place a
subtle reading of the spec is written down.
