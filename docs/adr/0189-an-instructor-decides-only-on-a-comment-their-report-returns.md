# 0189 — An instructor decides only on a comment their report returns, and the record names the role

**Status:** Accepted, amending [0187](0187-moderation-verdicts-govern-the-read-path.md) (the close boundary)
**Date:** 2026-10-10
**Ticket:** [E6-03](../tickets/e6/E6-03-instructor-decisions.md)

## Context

SPEC §5.2 gives the instructor exclude and keep, each with an Undo, and asks for
a stated reason when the AI did not flag the comment. Nothing could name a
comment: `CommentView` had no handle. The owner's rulings for E6
(`../tickets/e6/README.md`) put the record on `moderation_state` (ruling 3),
and have the log show the decider's role rather than a name (ruling 4). The
spec does not say how the door finds a comment, how Undo behaves after
somebody else's decision, or where the handle may travel.

## Decision

**The handle is the answer id, carried on a card beside `ReportComment`.**
`CommentView` gains exactly `answer_id`, `flag` (harmful, privacy or null) and
`decided_by_you`. The id is random (`gen_random_uuid()`, ADR 0016), so it says
nothing about time. It is safe to hand over because of ADR 0187: the report never
returns a Care-class comment, and the reveal door answers only for one, so an
instructor never holds an id that door would answer for. `ReportComment` stays
three fields (ADR 0153's equality); `report_comments.visible_cards` and
`released_cards` answer a frozen `CommentCard` (the `ReportComment`, the id, the
flag, the latest decider), and `visible_comments`/`released_comments` are those
reads with the extras dropped, so the rule is written once. The decider is
reduced to a boolean about the reader in `reporting.comment_view`; **no card
carries a date, a time, a week, an author or a decider.**

**The strict visibility rule, in the door.** `reporting.comment_on_instructor_report`
walks what the report reads: the reader's taught sections (`authz`), each one's
published weeks, each week's two streams through `visible_cards`, and the release
through `released_cards`. Only an id found there is accepted. Every other case (a
held comment, another section's, a rating, a Care-class comment, an id nothing
holds) is the same 404 with the same sentence. The shared write,
`moderation._record_decision`, takes the card, the decider and the role from its
caller and nothing that widens what it accepts, so E6-05's Lead Faculty door
cannot loosen this one.

**The stored role, and the router's rows.** M2 adds `decided_by_person_id`
(`RESTRICT`), `decided_as` (`INSTRUCTOR`, `LEAD_FACULTY`, `CHAIR`), `reason` and
`is_undo`, with `CHECK`s pairing decider and role, making a decider-less row a
flag, and requiring a decider for a reason. A role read off today's assignments
would change when the assignments do, so it is stored. `pulse_app` gets `INSERT`
on the six columns a decision writes and nothing else; a trigger refuses a
decider-less row from any role but `pulse_moderation_definer`, because that
grant includes `answer_id` and `state`. A reason is non-blank by `str.strip()`'s
code points (the list `report_comment_v003.sql` uses) and at most 500 characters,
checked as sent; `btrim` alone would accept a tab.

**Undo has one rule.** It reads the comment's latest row only, and succeeds only
when that row is a non-undo decision by this person under this role; it appends
the state before that row with `is_undo`. Decisions on one comment are serialized
by a transaction-scoped advisory lock, so an undo is never judged against a row a
colleague is replacing.

**There is no participation note.** Ruling 2 had this ticket build one ("1
response held for review" per week); ruling 6 dropped it after review, because
a per-week held count read beside a released comment's chip tells the
instructor which week that comment came from (ADR 0153's channel), and in a
small week it says how many of the few respondents wrote something held, which
lowers the effective threshold. The week report carries no held count of any
kind, and SPEC §5.2 says "no count".

**The de-anonymization statement for instructor views** (read against ADRs 0153,
0162, 0178 and 0179). The handle, the flag class and `decided_by_you` carry no
week and no instant, and a chip appears only where the comment itself does. A
held stream contributes no comment, no chip and no count, so nothing on the week
report moves when a held comment is flagged, kept or excluded, and a reader
subtracting consecutive reports cannot tie a released comment to its week. An
earlier draft of this statement said a per-week held count could sit beside the
release without attributing it; that was wrong, which is why the note was
dropped. **The stated limit:** "no trace" means Pulse's surfaces; the LMS
gradebook can show that a student completed the survey with a comment that never
reached the report, and nothing in Pulse closes that without changing §3.4.

**Amending ADR 0187:** closed is `closes_at < now`, by
`survey_windows.closed_by`, which that module's "open" negates; the window is
still open at `closes_at` itself.

## Alternatives rejected

- **`answer_id` on `ReportComment`.** Widens every reader of E4-04's value and
  breaks ADR 0153's equality, for a handle only the instructor's report needs.
- **A looser rule: any comment in a taught section.** Lets an instructor act on
  a comment they cannot see.
- **The rule rebuilt from the answer's section, week and stream.** A second copy
  of the report's rule, wrong one level out (entries 35 and 53).
- **Undo as "the reader's latest decision".** Reverses past a colleague's later
  decision, or walks back through history one click at a time.
- **The participation note (ruling 2).** Built, then dropped by ruling 6: a
  per-week held count attributes a released comment to its week and lowers the
  effective small-N threshold.

## Consequences

- A decision costs a walk over the reader's published weeks, a few dozen reads.
- `tests/e2e/exit-instructor-report.spec.ts` pins a released comment's fields at
  E4's three; `../disputes/E6-03-01.md` asks for it to take the six.
- E6-05 writes `LEAD_FACULTY` and `CHAIR` rows with no migration, through its
  own door and the same write.
