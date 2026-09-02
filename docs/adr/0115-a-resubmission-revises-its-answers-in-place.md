# 0115 — A resubmission revises its answer rows in place, because a judged comment cannot be deleted

**Status:** Accepted
**Date:** 2026-09-01
**Tickets:** E2-08

## Context

SPEC §3.3 allows a student to resubmit inside the open window, and E2-08's scope
spells out what that means: "Resubmission within the window replaces the prior
answers and re-runs the gating." The obvious mechanism is to delete the response's
`answer` rows and insert the submitted set fresh — it is one statement, it cannot
leave a stale row behind, and it is what E2-08's own work order names.

The same ticket adds `classification.answer_id`, which is
[ADR 0055](0055-a-classification-row-names-its-task-and-no-comment.md)'s promised
reference: a verdict names the comment it judged. Every foreign key on these tables
is `ON DELETE RESTRICT`, for the reason `app.models.survey` gives — "nothing removes
a response's answers by removing something else", and what a retention policy
eventually deletes is the retention epic's decision to make out loud.

The two are incompatible, and the incompatibility is not hypothetical. A student
submits a comment; it is classified; the row `classification.answer_id` points at
is the row a delete-and-reinsert resubmission would remove; Postgres refuses it.
The first resubmission of any comment in the product would answer 500.

SPEC is silent on the mechanism — it says the prior answers are replaced, not how —
so this is a construction decision, and it is contestable enough that the work
order settled it the other way without noticing the conflict.

## Decision

**A resubmission brings the existing `answer` rows into line with what was
submitted, rather than replacing the set.**

- A question answered again has its row revised: the value column its kind names is
  written, and the other two are written `NULL`, so `holds_exactly_one_value` stays
  true whatever the row held before.
- A question answered for the first time gets a new row.
- A question answered before and not now has its row deleted — **unless a
  classification names it**, which is checked before anything is deleted. That case
  is refused with its own reason and its own sentence
  (`submit.comment_already_judged`, HTTP 409), rather than left to surface as a
  constraint error under a student.

`classification.answer_id` keeps `ON DELETE RESTRICT`. The verdicts of a revised
comment accumulate, which is what `classification` being append-only already means
(ADR 0055: "re-runs create new rows"), and `response.is_valid` is computed from the
*latest* verdict of each comment.

## Alternatives rejected

**Delete the answer rows and insert fresh ones**, as E2-08's work order says. It is
the mechanism this record replaces, and it cannot be made to work without giving
up one of the two things it collides with. Its real advantage — no chance of a
stale row — is bought back by writing all three value columns on every revision.

**`ON DELETE SET NULL` on `classification.answer_id`.** This makes the deletion
legal and is the change a reader will reach for first. Rejected on two grounds. It
rewrites an append-only audit row, and it does so through a path the grants cannot
see: `classification` is granted `SELECT, INSERT` precisely so that `pulse_app`
*structurally* cannot alter a stored verdict, and a referential action is performed
by the system rather than by the role, so this would be an `UPDATE` on that table
by a route with no `UPDATE` on it. A guarantee with a back door through a foreign
key is worse than no guarantee, because it still reads as one. Second, the row it
leaves is a verdict about nothing: prompt version, model id and verdict intact, and
no way to say what was judged.

**`ON DELETE CASCADE`.** Worse: a student revising a comment would delete the
record that a model judged their earlier one. §7.4 rests auditability on "a
specific prompt version and model ID produced a specific classification for a
specific comment", and a mechanism that erases those on an ordinary edit ends that.

**Let the withdrawal succeed by keeping the old comment row.** Silently retaining
words a student took out is the one outcome here with a confidentiality cost: the
comment reaches the instructor's report (§5.1) after the student removed it. A
refusal the student can read is worse ergonomics and better behaviour.

**Refuse resubmission entirely once a comment is classified.** Far too wide — it
would forbid revising a rating or a workload figure because a comment beside it had
been judged, and §3.3 permits resubmission inside the window without qualification.

## Consequences

**A comment cannot be withdrawn once it has been classified; it can only be
revised.** That is a real product rule this record creates, and it is stated to the
student in one sentence rather than discovered. It follows from the audit trail
being real: a verdict names a comment, so the comment stays as long as the verdict
does. What it costs is the case where a student writes something they regret and
wants it gone, and the answer available to them today is to replace the text — the
row is theirs to edit — rather than to empty it. A ticket that wants true
withdrawal is deciding what happens to the verdict, which is a decision about the
audit trail and belongs with the retention epic.

**Answer row identity survives a resubmission**, which nothing depended on before
and two things do now: a verdict's `answer_id` keeps pointing at the comment it
judged across a revision, and the re-classification sweep therefore finds a floored
comment whose text has since changed and judges the current text. That is the right
behaviour — the stored comment is the one the report will show.

**The uniqueness rule on `answer` is doing more work than it was.** `UNIQUE
(response_id, question_id)` is what makes "the row for this question" a
well-defined thing to revise; without it this mechanism would have to choose among
duplicates. E2-05 already has it, and this record is a second reason it is
load-bearing.

**E2-08's work order says the other thing.** It settles "in-window resubmit deletes
the response's answer rows, inserts fresh" and settles `RESTRICT` in the same
document, and the two cannot both be built. This record is the deviation, made
deliberately and in favour of the guarantee rather than the mechanism, and the pull
request says so plainly rather than leaving a reader to find it here.
