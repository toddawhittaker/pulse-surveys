# 0145 — The report schema has its own module, and a comment's moderation state begins as an absence

## Context

E4-02 adds four tables and one column before anything writes any of them, and
three questions had to be answered to do it. They are recorded together because
each is a construction choice the spec leaves open, and separating them would
have produced three records that only make sense read as one.

**Where the tables live.** SPEC §13's layout puts `summary` in `ai.py`, beside
`classification`. That is a real placement and this ticket departs from it, so
this record does not get to claim the spec was silent. What changed since §13
was written is that the reporting schema turned out to be four tables rather
than one: E4's breakdown settled a stored summary (decision 2), a moderation
status that lands in E4's schema (decision 3), and a stored release batch
(decision 7), and §13 names a home for the first, arguably names one for the
second under `loop.py`'s `moderation_action`, and names none at all for the
third. **§8 is out of step in the same way**: its core-table list has `summary`
and `moderation_action`, and this ticket ships `weekly_summary`,
`moderation_state`, `release_batch` and `release_batch_member`.

**Whether the moderation status is a column or a record.** The ticket puts the
choice plainly: a column on `answer`, or its own row beside `classification`.
§5.2's lifecycle has an undo in both directions and §8 requires both directions
logged.

**How `weekly_summary` reaches the week.** `response` carries a `term_id` and
two composite foreign keys so that a section in one term cannot be paired with a
week in another (E2-16, [0018](0018-a-cross-table-rule-a-check-cannot-express-is-a-composite-foreign-key.md)).
The same shape is available here and is not obviously worth its cost.

## Decision

**One: the four tables go in a new `backend/app/models/report.py`.** They are
what the weekly report stores, which is neither what a student submitted
(`survey.py`) nor what a model answered about one comment (`ai.py`); putting
three of them in `ai.py` would make that module the home of two unrelated
aggregates, and splitting them across `ai.py` and a second module would separate
tables that are only reviewable together — which is the whole reason E4-02
exists as a ticket.

**This is a departure from SPEC §13, not a gap in it, and the spec needs the
edit.** Three sentences are now false: §13's `ai.py # classification, summary`,
and §8's core-table list naming `summary` and `moderation_action`. This record
does not authorise that edit — a decision that contradicts the spec is not an
ADR's to make, and `docs/adr/README.md` says so in as many words. It is raised
in E4-02's pull request as an item for the owner, and the pull request names the
exact sentences. Until it lands, this file is the record of the divergence; the
sentence in `app/models/__init__.py` that promised the summary to `ai.py` was
corrected with the change rather than left standing.

**Two: moderation state is an append-only record, and the initial state is the
absence of a row.** `moderation_state` holds one row per decision — the comment,
the state, and when it was decided — and the latest row governs. A comment with
no row is published. That is what makes the breakdown's "exactly one value ever
written during E4" a count of **zero** writes: E4-04 builds its concealment
queries against the real table and writes nothing into it, and every writer is
E6's. The vocabulary the `CHECK` enumerates is §5.2's four —
`PUBLISHED`, `FLAGGED_COLLAPSED`, `EXCLUDED`, `KEPT` — so that E6 meets a
lifecycle it can walk rather than a constraint two states short.

**Three: `weekly_summary` takes a plain `week_id`, and the residual risk is
named rather than hidden.** A summary whose section and week belong to different
terms is accepted by insert. The only writer §5.1 admits is E4-06's Monday job,
which derives both keys from a `survey_window` row, and `survey_window` already
enforces the pairing — so the row this permits is one a hand-written `INSERT`
produces and nothing in the product does.

**And a fourth thing, small enough that it would be a footnote if it were not
irreversible in a running database: the backfill's placeholder.**
`question.stream` is filled by kind first — a workload question gets nothing,
whatever ordinal it sits at — then by §3.2's ordinals, 1 and 2 to `INSTRUCTOR`
and 3 and 4 to `COURSE`. Anything else gets `COURSE`. That fallback is a
decision and not a coin toss: `INSTRUCTOR` would file a question nobody has
placed under a heading about a named individual, and `COURSE` files it under one
about materials and activities. When in doubt, do not attribute it to the
instructor. At the moment the revision runs no such row exists anywhere —
`scripts/seed.py` writes exactly §3.2's five and nothing else in the system
writes a question — so no reader depends on the value it gives one.

## Alternatives rejected

**Put the four tables in `ai.py`, as §13 says.** It would keep the layout line
true and make the module the home of two aggregates that share nothing: a
release batch is not a model output, and neither is a moderation decision an
instructor made. The cost of the departure is one spec edit; the cost of the
obedience is a module whose name stops describing it, and a `report.py` that
gets created anyway the first time E4-06 needs somewhere to put a reader.

**Put them in `loop.py`, which §13 lists and nothing has yet created.** §13 gives
that module `instructor_response`, `moderation_action` and `exclusion_log` —
§5.3's response loop and §5.2's *log*. `moderation_state` would fit; the summary
and the release batch would not, and splitting the four across two modules
defeats the one thing this ticket is for.

**A mutable `moderation_state` column on `answer`.** The obvious shape, and it
holds the current state perfectly. It cannot hold the trail: §5.2's exclusion log
is the anti-cherry-picking mechanism, §8 requires both directions logged, and
under a column the second decision overwrites the first. E3's decision 4 and
[0124](0124-grade-sync-is-append-only-one-row-per-post.md) are the precedent —
state a later reader has to be able to account for is appended, not updated.

**A column on `answer` *beside* the record**, "so the read path has somewhere
cheap to look". Two sources of truth for one question, which disagree the first
time either is written alone, and E6's log then hangs off neither.

**A `DEFAULT 'PUBLISHED'` and a row written for every comment at submit time.**
It makes the initial state explicit, and it puts E4 in the business of writing
moderation rows — which is exactly the writer the breakdown assigns to E6. It
also makes every comment carry a decision nobody made, so the log cannot
distinguish "published because nothing happened" from "published because an
instructor kept it".

**A Postgres enum for the state and for the stream.** Rejected for the reason
`classification.verdict` gives, plus one this epic adds: three E4 tickets take
migration chain slots off one head and are re-pointed at merge, and a shared
enum *type* is an object the other two would have to know about. A `CHECK` is
local to its table.

**The composite `(week_id, term_id)` foreign key on `weekly_summary`.** Strictly
stronger, and it costs a `term_id` column on every summary row, a second unique
constraint to reference, and a third key for every writer to get right — to
refuse a row the only writer cannot produce. [0110](0110-answer-values-are-validated-by-the-write-path.md)
accepts the same trade on `answer` for the same reason. If a second writer ever
appears, this is the decision to revisit first.

**`INSTRUCTOR` as the backfill's fallback, or refusing to backfill rows outside
§3.2's five at all.** The first is the same arbitrary choice pointed at the more
harmful group. The second is worse than arbitrary: a `WHERE position IN
(1,2,3,4)` backfill is green against the shipped set and aborts the upgrade
against any database whose question set has ever changed, leaving an operator
below this revision with no way forward.

## Consequences

- **SPEC §13 and §8 are wrong until they are edited**, and this file is the only
  place that says so. That is a record nobody re-reads carrying a fact somebody
  will need, which is why the pull request raises it rather than leaving it here.
- **A reader of a comment's moderation state has to write a window function**, or
  its equivalent: "the latest `moderation_state` row for this answer, or
  published if there is none". That is E4-04's and E6's to write once, in
  `app.services`, not per call site. The alternative was a column, and the
  paragraph above is what it cost.
- **Absence-as-initial means a count of rows is never a count of comments.** A
  reader that joins `moderation_state` to `answer` inner-joined gets only the
  comments somebody decided about, which is almost never the question being
  asked. Every read of this table is a `LEFT JOIN` with a default.
- **A hand-written `INSERT` can store a summary whose section and week belong to
  different terms.** Nothing in the product does it, nothing checks it, and it
  would be caught by whoever noticed the report was reading a week its own
  section's calendar does not contain.
- **A question outside §3.2's five carries a stream nothing decided.** Any ticket
  that gives the instrument a sixth question owns choosing its stream properly,
  and the fallback exists so that the upgrade completes, not so that the choice
  can be skipped.
- **Nothing has any privilege on any of these four tables.** Every read and every
  write in E4-04, E4-06 and E6 fails at the connection until that ticket grants
  what it spends, which is the intended shape and will look like a defect to
  whoever meets it first.
