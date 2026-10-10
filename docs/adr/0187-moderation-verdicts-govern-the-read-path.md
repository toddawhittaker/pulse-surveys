# 0187 — Moderation verdicts govern the read path, through one writer

**Status:** Accepted, amending [0144](0144-the-reveal-derives-its-subject-from-the-record-care-is-acting-on.md) and [0145](0145-the-report-schema-has-its-own-module-and-moderation-starts-by-absence.md); the close boundary amended by [0189](0189-an-instructor-decides-only-on-a-comment-their-report-returns.md)
**Date:** 2026-10-09
**Ticket:** [E6-01](../tickets/e6/E6-01-verdicts-below-the-read-path.md)

## Context

Until E6-01 nothing wrote a moderation verdict, and a comment with no
`moderation_state` row counted as published. So every comment reached the week
read, the release cut and the summary model unmoderated, and SPEC §6.2's threat
and self-harm class was suppressed nowhere (`../tickets/e4/deferred.md`). The
`moderation_state` ordering could not break a tie between two decisions written
in one transaction. SPEC §5.2 and §8 say what must hold; they do not say where
each rule lives or what a reader sees while a week's verdicts are still landing.

## Decision

**The view decides which comments exist for a reader.** `report_comment` v004
keeps v003's five columns and adds two conditions: the comment holds a
`MODERATION` classification, and no `MODERATION` classification of it, ever, is
`threat` or `self_harm`. "Ever", not the latest: a later `clear` does not bring a
comment back, because §6.2 has already routed it to Care. Every reader is built
on the view, so the rule is below all of them.

**A section-week is moderated or it is not, and that rule lives in one Python
function.** `app.services.report_comments.section_week_moderated` is true when
every comment of the section-week that the view would otherwise show (a comment
answer whose text is not blank) holds a verdict. The week read returns nothing
for a week that is not moderated, in the empty shape a suppressed stream already
answers; the release cut skips the week whole; the summary walk does not
summarize it. So before a week's last verdict lands a reader sees nothing of its
comments, and after it sees all of them: no read shows part of a week, which
would let a reader who keeps each report attribute the newest comment by
subtraction (`docs/MISTAKES.md` entry 51). Leaving a Care-class comment out also
leaves its author out of the commenter count, which is the conservative side of
entry 50. "Not blank" is `str.strip()` on the unverdicted texts: the write path's
own test, and the definition v003's code-point list copies.

**One writer, and a wall beside it.** `public.route_moderation_verdict(answer_id,
verdict, prompt_version, model_id) RETURNS uuid` is a `SECURITY DEFINER` owned by
a NOLOGIN role of its own, `pulse_moderation_definer` (the
[0043](0043-the-reveal-function-has-an-owner-of-its-own.md) pattern). One call
writes the verdict and its route: a `FLAGGED_COLLAPSED` row for harmful or
privacy, a `threat_case` row for threat or self-harm (unique per comment; a
second Care-class verdict leaves the case alone), nothing more for clear or
nonsense. There is no exception handler, so a failed route takes the verdict with
it. `pulse_app` holds `EXECUTE` on it, only `SELECT` on `moderation_state`, and
nothing on `threat_case`. (Since [0189](0189-an-instructor-decides-only-on-a-comment-their-report-returns.md),
`pulse_app` also inserts a person's decision into `moderation_state`, on six
columns only, and a trigger keeps a row with no decider the definer's.) A `BEFORE INSERT OR UPDATE` trigger on `classification`
refuses a `MODERATION` row unless `current_user` is the owner, so `pulse_app`'s
existing `INSERT` cannot store a threat verdict with no case. Seeds and fixtures
plant verdicts through the same door, via `app.services.moderation.route_verdict`,
under the provenance `"seed"`, which no real prompt version can be.

**A verdict judges the text as it stood at close, so it is written only after
the close.** An answer is revised in place when a student resubmits
([0115](0115-a-resubmission-revises-its-answers-in-place.md)), and every rule
above keys "holds a verdict" on the answer id. A verdict written while the window
was open would vouch for text the student could still replace: `clear` on
Friday, a self-harm disclosure resubmitted into the same row on Sunday, shown as
moderated and routed to nobody. So `route_verdict` refuses an answer whose survey
window has not closed by the app clock (`now >= closes_at` is closed, ADR 0109),
raising `ModerationBeforeClose` before it writes anything.

> **Amended 2026-10-10 by [0189](0189-an-instructor-decides-only-on-a-comment-their-report-returns.md)
> (E6-03, from PR #292's re-check):** closed is `closes_at < now`, not
> `now >= closes_at`. The survey still accepts a resubmission at `closes_at`
> itself (`survey_windows._open_at` reads that instant as open), so a verdict
> written then could vouch for text the student can still replace.
> `route_verdict` now asks `survey_windows.closed_by`, which `_open_at` negates,
> so there is one definition. An answer whose
response has no survey window is refused the same way: with no close to judge
against, it is treated as open (fail closed). The definer does not repeat the
check, because the close is judged by the app clock, which the database cannot
read, and every writer, seeds and fixtures included, goes through
`route_verdict`. A seeder that meets an open window leaves that comment
unmoderated rather than failing.

**The verdict check is per task**: one disjunct per `ClassificationTask` member,
built from the two verdict enums, so each task holds only its own tokens.

**The summary gather reads the view.** Its own copy of the blank-comment class is
deleted, so the model is sent exactly what a reader may reach.

**Ordering is by insert.** `moderation_state.sequence` is a `GENERATED ALWAYS`
identity column and `reported_status_of` orders by it alone. Two decisions in one
transaction resolve to the second. An identity orders by insert, not by commit:
two concurrent writers are not a same-transaction pair, and the one that inserted
first is earlier even if it committed second.

**The reveal door narrows.** `reveal_subject_for_answer` v002 answers only for a
comment holding a threat or self-harm verdict, and NULL for any other, which the
service raises as `UnknownRevealSubjectError` before any audit row is written.

**Ruling 5, made by the owner on 2026-10-09.** No deployment reaches real
students until E10's Care queue exists, because before it a `threat_case` row has
no reader: a student at risk whose comment is held from every view would be read
by nobody. SPEC §12 carries the same sentence. The design above does not change
for it.

## Alternatives rejected

- **Filtering unverdicted comments one by one.** Each read would show part of a
  week, and the next read the difference.
- **The week rule in the view.** It is a statement about a set, and SQL that
  cannot see unverdicted rows cannot count them; a second view or a helper
  function would be another relation or another door for `pulse_app`.
- **A second copy of v003's regex in Python**, the copy this ticket deletes from
  the gather.
- **The Care-class rule over the latest verdict.** A re-run answering `clear`
  would show a self-harm disclosure to an instructor.
- **Grants on the two route tables instead of a door.** A grant cannot make two
  writes one.
- **A trigger keyed on `pulse_app`, or on `session_user`.** The first lets every
  other role write around the door; the second refuses the door itself.
- **Ordering by `decided_at` then `id`.** `id` is random, so the tie is a coin flip.

## Consequences

- A comment whose moderation never succeeds holds its whole week back from every
  reader. E6-02's attempt cap, counted over `moderation_attempt`, is what releases
  such a week; until it lands, the week waits.
- Every fixture, seed and end-to-end world plants verdicts, and only after the
  comment's window has closed; a world that forgets shows no comments.
- A caller holding the database role could still call the definer directly for
  an open window, since only `route_verdict` checks the close. `pulse_app` is the
  only role with `EXECUTE`, and no code path calls the function except
  `route_verdict`.
- Accepted residue: `test_the_cumulative_release_cuts_one_batch_when_volume_crosses.py`'s
  open-week case no longer kills "release from an open week" on its own, because
  a comment in an open week can no longer hold a verdict and so is never in the
  view the cut reads. The cut's own `closes_at < now` condition still stands; the
  case now passes for two reasons rather than one.
- `threat_case` has no reader until E10, which is why ruling 5 exists.
- The migration commits the `MODERATION` enum label before anything names it
  (PostgreSQL refuses a new label in the transaction that added it), and a
  downgrade leaves the label and any moderation rows in place.
