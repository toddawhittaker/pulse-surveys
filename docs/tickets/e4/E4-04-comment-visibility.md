# E4-04 — Comment visibility under small-N

**ID:** E4-04
**Branch:** `e4/comment-visibility`
**Depends on:** E4-02
**Lane:** heavy ⚠ — line-by-line human review of the suppression queries, per
SPEC §14.3's E4 entry. The epic is unmarked; this diff is not.
**Security-relevant:** the whole diff. This is the epic's confidentiality
heart: the one place a wrong answer shows a student's words to someone §4
says must not see them, and a leak cannot be un-shown.

## Context

§4 and §5.2, made into one read path. Below the n-threshold
(`n_threshold_default`, `backend/app/config.py` — configurable, default 5),
instructors see distributions and the AI summary but no raw comments.
Under-threshold comments are not discarded: they feed the summary at
generation time, and they surface as raw text once the section's cumulative
comment volume for the term crosses the threshold — batched, so timing
cannot identify an author (breakdown decision 7: the batch is stored,
E4-02's state). Comment display order is randomized; timestamps are never
shown with comments; and below the threshold, flagged comments are concealed
from the instructor entirely — no chip, no count, no flag-type hint — which
is why E4-02 put the real moderation column under this ticket's queries.

This ticket also owes a written statement. The carried entry "Comment
de-anonymization by completion pattern" accepts (ADR 0125) that the AGS
ledger narrows comment-author candidate sets, and its done-when requires E4
to state in writing that its suppression holds against a reader who also has
the gradebook open — or to change what it suppresses. That statement is this
ticket's ADR, and it must engage the sharpest version of the problem: a
released under-threshold comment is grouped under a week, the ledger says
who completed that week's comment items, and the intersection can be small.
Whether the release preserves week attribution is therefore not a rendering
detail — it is the decision the statement stands on.

Read first: SPEC §4, §4.1 items 3 and 6, §5.1, §5.2; ADR 0125;
`carried-from-e3.md`'s de-anonymization entry; E4-02's ADR on the batch
state; `backend/app/services/survey_read.py`'s header for how a read module
carries its predicate.

## Scope

- The comment read path for the report: given a section, course week and
  stream, the comments an instructor may see right now — published-state
  text above threshold, nothing below it, released batches where the
  cumulative rule has crossed.
- The crossing-and-release logic: when the section's term-cumulative volume
  crosses the threshold, under-threshold comments become releasable as one
  stored batch. Where the crossing is evaluated (at read, or by the E4-06
  job) is a decision below.
- Flag concealment: a comment whose moderation state is not the published
  state is absent below threshold — absent from counts, absent from any
  trace — and above threshold appears per §5.2's chip rules (rendering is
  E4-10's; the *data* discipline is here).
- Randomized order, and no timestamp anywhere in what this path returns.
- The de-anonymization ADR.

## Acceptance criteria

1. Below threshold: zero raw comments cross the boundary, proven at the
   service's return value, with a planted week of four responses — and the
   count of what was withheld is not derivable from the response shape
   (§5.2: no count, no hint).
2. A planted flagged row below threshold is absent from everything —
   asserted as the forbidden state (`docs/MISTAKES.md` entry 2), and
   distinguishable from "no comments existed" by nothing the caller
   receives.
3. The cumulative crossing releases exactly the stored batch, atomically: a
   test drives volume across the threshold and every under-threshold comment
   surfaces in one batch or none do.
4. A released comment carries no timestamp, and the randomized order is
   real: the same read twice yields differing orders (seeded appropriately
   so the test is deterministic about randomness existing, not about a
   particular order).
5. The week-attribution decision, whichever way the ADR rules, is asserted:
   if releases drop week attribution, no released comment's payload or
   grouping names its week; if they keep it, the ADR's argument for why the
   ledger intersection is acceptable is recorded and the test pins the
   grouping.
6. The invariant suite grows: §4.1 item 3 (below the n-threshold, raw
   comments hidden from instructors and students alike) gets its
   instructor-side assertion in the isolated pass, marked `invariant`.
7. Nothing in this path can widen a student's visibility (§4.1 item 6) — the
   path takes no student-facing parameters, and a sweep proves no
   student-facing module imports it.

## Decisions this ticket settles

- **Whether the release preserves week attribution** — the ADR, with the
  gradebook-reader statement standing on it. The recommendation: released
  batches present without week grouping (they surface in the current week's
  report under a "from earlier weeks" heading), because that is the shape
  under which the ledger's per-week completion pattern gains nothing.
  Whatever wins, §4's "batched so that timing cannot identify an author"
  must hold in the argument, not just the schema.
- **Where the crossing is evaluated.** Read-time evaluation re-derives; a
  job evaluates once and writes the batch. The recommendation is the E4-06
  job cuts batches (it already runs at the only moment volume changes
  matter) and this path only reads them — one writer, and the read path
  stays pure.
- **What "cumulative comment volume" counts** — comments submitted, or
  comments surviving moderation. §4 says volume; the ADR picks and says why.

## Known traps

- **This is the diff a fixture bug breaks silently** — `tests/fixtures/` is
  a heavy row for exactly this reason. The planted-week fixtures must be
  provably below and above threshold by construction, both sides asserted.
- **A guard whose outcome a second layer also produces** — a below-threshold
  test that passes because the week had no comments proves nothing. Fixtures
  plant real comments that would leak.
- **The threshold is configuration** — tests drive the configured value,
  including a non-default one, so nothing hard-codes 5.
- **Randomization in SQL vs in Python** decides where the no-timestamp rule
  must be checked — wherever ordering happens, the timestamp must not be the
  order key in disguise.

## Out of scope

- Rendering — chips, collapsed states, notices — E4-10 and E4-11.
- The moderation lifecycle and anyone writing a non-initial state — E6.
- The summary's own handling of under-threshold comments — E4-05/E4-06 (they
  feed it at generation; nothing here re-opens that).
- Student-facing comment reads — E8.
