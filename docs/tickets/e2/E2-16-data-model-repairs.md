# E2-16 — The survey schema's migrations survive a round trip, and the sweep survives a term

**ID:** E2-16
**Branch:** `e2/data-model-repairs`
**Depends on:** E2-14, E2-15 (the boundary batch this ticket's review ran against)
**Lane:** heavy
**Security-relevant:** yes — item 2 governs what §3.4 counts and what the floored-comment sweep can see.

## Context

The epic-boundary data-model review (record: `docs/tickets/e2/boundary-review.md`,
second round) found the two E2 schema migrations irreversible in ways that
destroy or silently corrupt data that now exists, a query that collapses at one
term's volume, and three smaller gaps. Every claim below was adversarially
verified by execution on a throwaway database; the sweep-query finding came
back worse than reported and with a different cause.

## Scope

1. **The `3f6907349751` round trip stops stranding the database.** Its
   `downgrade()` drops `survey_window.term_id` unpreserved and drops `response`
   and `answer` whole; its `upgrade()` re-adds `term_id` NOT NULL with no
   backfill, so with 188 windows on dev the re-upgrade aborts with
   NotNullViolation and the database is stuck at `d2f6a913c47e`. Apply the
   house preserve-and-restore pattern (`b8c41f7d2e05` is the worked example) to
   the whole downgrade surface: preserve what the downgrade removes, restore on
   re-upgrade, and backfill `term_id` from `section.term_id` (verified: covers
   every row; `section.term_id` is NOT NULL). Correct the docstring premise
   ("`survey_window` is empty in every environment") that E2-06 falsified.
2. **The `f1a3c7d02b64` round trip stops corrupting silently.** Its
   `downgrade()` drops `classification.answer_id` and `response.is_valid`
   unpreserved; the re-upgrade backfills `is_valid = true` for every row and
   leaves `answer_id` NULL — verified: a nonsense-judged response reads valid
   after the trip, and the floored verdict becomes permanently invisible to
   `app/services/validity.py`'s sweep (both legs filter
   `Classification.answer_id.is_not(None)`, and `classification` takes no
   UPDATE, so nothing can ever repair it). Preserve and restore both columns.
3. **`response` gets the term-agreement constraint `survey_window` already
   has.** A response pairing a section in one term with a week in another is
   representable today (verified by insert) and refused on `survey_window` by
   its composite foreign keys. New migration chained on `f1a3c7d02b64`:
   `response.term_id` plus the two composite FK limbs, mirroring
   `uq_section_id_term_id` / `uq_week_id_term_id` usage, with the backfill from
   `section.term_id`. The single writer (`submissions.py`, the only
   `Response(...)` construction in the tree) supplies it.
4. **The floored-comment sweep survives a term's volume.** The
   `NOT IN`-shaped anti-join in `app/services/validity.py` (both the `judged`
   and `floored` legs, lines ~365-380) unhashes past `work_mem` at ~300k
   `classification` rows and was measured at 72 seconds, rescanning the table
   once per outer row; an index alone recovers ~35%. Rewrite the query shape
   (`NOT EXISTS` or `LEFT JOIN … IS NULL` — the anti-join form the planner can
   always run without a spillable hash), and add the supporting index on
   `classification (task, prompt_version)` in item 3's migration. The sweep is
   enqueued per floored submission and fires hardest during provider outages —
   exactly when floored rows accumulate.
5. **Window derivation goes set-based.** `derive_windows_for_all_sections`
   was measured at 5N+1 round trips (three queries per section — the term, the
   term's weeks, the existing windows — plus a savepoint pair each): 2,501
   per hour at 500 sections, most refetching the same term's rows. Batch the
   reads; keep the per-section write containment.
6. **The two speculative week-axis index comments stop claiming the
   present.** `ix_response_week_id` and `ix_survey_window_week_id` serve no
   query in the tree (verified by whole-tree grep); their model comments
   describe a §3.4 week-close read in the present tense. Keep the indexes (the
   anticipated read is spec-anchored, SPEC §3.4 "recomputed after each week
   closes"), retense the two comments to name the read as E3's.

## The docs bundle (rides this PR)

- Epic README: Merged cells for rows 13 (#151, 7f38009), 14 (#154, c2a83f1),
  15 (#153, 561dea4); rows 16, 17, 18 added for this batch.
- `docs/tickets/e2/boundary-review.md`: a second-round addendum recording the
  four always-run agents' findings, each verification verdict, and every
  disposition — including the record-only items: the floors history (ruled,
  carried to E10), the model-identifier finding (subsumed by the existing
  `carried-from-e2.md` entry), the dev-clock/roster LOW (carried), and the
  explanation that classifications with NULL `answer_id` written by the live
  stack are bounce verdicts, which store no answer by the 2026-09-03 ruling.
- `docs/tickets/e3/carried-from-e2.md`: the session-read sweep's two disclosed
  limits (`getattr` indirection; anything outside `backend/app/`), and the
  dev-clock/roster interaction.
- `docs/MISTAKES.md` entry 42 + `docs/mistakes/42-*.md`: a CI verdict was
  reported green from a stale check rollup read between two pushes; the rule
  is that only a completed run whose head SHA equals the final commit counts.
- `docs/SPEC.md` §7.3: the roster-sync sentence conditioned per the
  2026-09-03 ruling — an instructor launch syncs unconditionally; a leadership
  launch syncs only inside the launcher's own purview; an out-of-purview
  leadership launch records `context_outside_purview` and binds nothing
  (ADR 0108; assistant-dean-only launches fail closed until E9).

## Acceptance criteria

1. On a database with rows in every E2 table, `alembic downgrade
   d2f6a913c47e` then `alembic upgrade head` restores byte-identical
   `survey_window`, `response`, `answer`, `classification.answer_id`, and
   `response.is_valid` values — proven by a test that seeds, round-trips, and
   compares.
2. A cross-term `(section, week)` response insert is refused by the schema;
   the same-term insert is accepted (both directions).
3. The sweep's two legs contain no `NOT IN` anti-join; a plan-shape or
   statement-count test pins the rewrite, and the new index exists.
4. `derive_windows_for_all_sections` issues a bounded statement count
   (measured, not 5N+1) with behavior unchanged — same windows derived.
5. `alembic check` clean; the §4.1 isolated pass green and not shrunk.
6. The docs bundle lands with every disposition line pointing at this PR.

## Out of scope

- Everything in E2-17 and E2-18. The bounce verdict-row cap (its deferred
  entry stands). Any retention job (E13's).
