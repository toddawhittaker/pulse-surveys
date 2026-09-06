# E4-02 — The report schema

**ID:** E4-02
**Branch:** `e4/report-schema`
**Depends on:** nothing
**Lane:** heavy
**Security-relevant:** a migration under every read-path guarantee the epic
makes, plus grants — `backend/migrations/`, `backend/app/models/` and
`backend/app/views_sql/` are all heavy rows, and `privacy-authz` fires on
the grants.

## Context

Everything E4 writes, before anything writes it — E3-02's pattern, for E3-02's
reason: the writers (the summary job, E6's moderation lifecycle, the release
logic) are separate tickets and epics, and the schema they share should be
reviewed once, whole, rather than accreted.

Three things need a home:

1. **The stored summary.** Decision 2 of the breakdown: one row per section,
   course week and stream, holding the text, the response count it drew from,
   `prompt_version` and `model_id` (§7.4: every model output stores both),
   and when it was generated. Nothing else aggregate is stored (decision 1).
2. **The moderation status.** Decision 3: the column lands now, with exactly
   one value ever written during E4, so E4-04's concealment queries are built
   against the real thing. E6 writes the lifecycle (§5.2: `published`,
   `flagged-collapsed`, `excluded`, `kept`); E4 writes only the initial
   state.
3. **The release-batch state.** Decision 7: the cumulative batched release is
   stored, not computed at read time — which batch a released comment belongs
   to, and when the batch was cut, without ever exposing a per-comment
   timestamp downstream.

Read first: SPEC §4, §5.1, §5.2, §8; `backend/app/models/ai.py` (the
classification rows the moderation lifecycle will sit beside, and the
comment-verdict vocabulary already shared between tasks);
`backend/app/models/survey.py` (where answers live); ADR 0124 (append-only
`grade_sync` — the precedent for choosing between a mutable column and an
append-only record); the `PERSON_TABLES` entry in `carried-from-e3.md`.

## Scope

- The migration (first chain slot off `c4a8e51db9f3` — E4-03 and E4-14 take
  the next two and re-point at merge, the E3-01 procedure).
- The models, in whichever module §13's layout supports — a new
  `models/report.py` needs the ADR to say why no existing module fits.
  *(Built as `models/report.py`. ADR 0145 argues it and records what this
  sentence assumed and should not have: §13 does not merely fail to support a
  reporting module, it places `summary` in `ai.py`, and §8's core-table list
  names `summary` and `moderation_action` where this ships four differently
  named tables. That was a spec edit rather than an ADR's to make, so it was
  raised — and ruled at E4-02, 2026-09-06: the spec follows the build, and this
  pull request carries the edits to §8's core-table list, §8's moderation
  sentence and §13's models block.)*
- **No grants.** This bullet asked which grants each writer needs; the
  settled design issues none, because this ticket writes no row into any of
  the four tables it creates and a privilege lands in the change that spends
  it. Criterion 6 below carries the correction and the reason.
- The `PERSON_TABLES` standing question, answered for every table this
  ticket adds, in the PR body.

## Acceptance criteria

1. `alembic upgrade head` and the **full downgrade of this ticket's revision**
   — as against a partial one — both succeed against a seeded database, and
   `alembic check` reports no drift. The trip is head → `c4a8e51db9f3` → head,
   made over rows.

   *(Corrected while building, per the ruling in
   [E4-02-01](../../disputes/E4-02-01.md). The criterion said "a full
   downgrade", which the test module first read as a walk to `base`. No ticket
   can satisfy that reading: revision `e046c1b23e54` refuses a downgrade against
   a seeded database by a design its own docstring argues for — it re-narrows
   the start-letter map's check to `^[A-Z]$`, which SPEC §2.2's 3-week cohorts,
   numbered 2 through 7, contradict. Measured byte-identical on a scratch
   database standing at `c4a8e51db9f3` with none of E4-02 applied, against a
   control with `start_letter_map` empty that completes. So the walk is bounded
   at the revision this one chains from, which keeps every defect the criterion
   is reaching for in range — a `CHECK` created over rows that contradict it, a
   column dropped from a populated table, and the
   `release_batch_member`-before-`release_batch` ordering that only a populated
   database can show. What a rollback should do with those six numbered start
   positions is a data question, and the ticket that answers it is where a walk
   to `base` belongs.)*
2. The summary table cannot hold two rows for one section, course week and
   stream — a database constraint, proven by a refused insert, not an
   application promise.
3. The summary row requires `prompt_version` and `model_id` — a summary with
   no provenance is a refused insert.
4. The moderation status has a database-enforced value set matching §5.2's
   lifecycle vocabulary, and the initial state is the **absence of a row**.
   A planted out-of-vocabulary write is refused.

   *(Corrected while building. This criterion asked for a column default —
   "its default is the initial state" — and the settled design records the
   status as an append-only record whose latest row governs, so there is no
   column and no default: a comment with no `moderation_state` row is
   published. That is what makes the breakdown's decision 3, "exactly one
   value ever written during E4", a count of zero writes, and it leaves every
   writer to E6.
   [ADR 0145](../../adr/0145-the-report-schema-has-its-own-module-and-moderation-starts-by-absence.md)
   weighs the mutable column this rejects. Corrected here rather than left to
   read as a criterion nobody met — `docs/MISTAKES.md` entry 1.)*
5. No table this ticket adds carries an identity column beyond what its ADR
   justifies, and the identity-column marker sweep still passes over the new
   surface.
6. **No grant is added**, and a test asserts that neither runtime role holds
   any privilege — at table grain and at column grain — on any of the four
   tables this ticket creates.

   *(Corrected while building. This criterion asked for the E3-02 shape:
   version-numbered SQL in `backend/app/views_sql/`, applied by the migration,
   with a test asserting the runtime role holds exactly the declared
   privileges. As written it cannot be satisfied, because the settled design
   spends nothing: E4-02 creates the schema E4 shares and writes no row into
   any of it, so there is no grants file to version and no privilege to
   declare. The writers grant what they spend — E4-06 for the summary, E4-04
   for the release, E6 for every moderation state — which is the rule every
   grants file in `backend/app/views_sql/` states and this ticket's own known
   trap: "a grant added 'for later' is scope". So the criterion is its own
   inverse, asserted in both currencies with a control on each probe
   (`docs/MISTAKES.md` entry 35), and the privilege-equality record in
   `tests/integration/test_identity_grants.py` gains the four tables at empty
   tuples.)*
7. The mutation battery for the schema rules runs against the migration, not
   the model (the memory of inert model-side mutations governs).

## Decisions this ticket settles

- **Where the moderation status lives** — a column on the answer row, or its
  own record beside `classification`. The recommendation is its own record:
  §5.2's lifecycle has undo in both directions and a logged decision trail,
  and E3's decision 4 (append-only, one row per event) is the precedent for
  state a later reader must be able to account for. The ADR weighs it; if a
  mutable column wins, the ADR says what the E6 log will hang off instead.
- **The release batch's grain** — a batch row that comments reference, or a
  batch label stamped onto comments. The constraint either way: E4-04 must
  be able to release a set atomically, and no per-comment release time may
  exist anywhere, because a stored timestamp nobody exposes today is a leak
  someone ships tomorrow.
- **Whether the summary references `survey_window`, the week, or the
  section-plus-course-week pair** — whichever it is must survive a question
  set change mid-term (§3.2 versioning) without ambiguity.

## Known traps

- **A late schema rule reaches every fixture** — the memory of the E0
  root-table constraint that failed 41 tests in their own seeding. New
  constraints on existing tables (the moderation initial state) get checked
  against the fixture builders before CI finds it.
- **`PERSON_TABLES` is a standing review question, not a formality** — the
  summary row's `response_count` is aggregate, but the release-batch state
  references comments, which reference answers, which reach a person. Walk
  it and write the answer down.
- **A grant added "for later" is scope** — if E6's writer needs a privilege,
  E6 adds it; granting it now widens the runtime role for a writer that does
  not exist.

## Out of scope

- Writing any summary row — E4-06.
- Reading or releasing anything — E4-04, E4-07.
- The moderation lifecycle and its log — E6.
- Any aggregate storage — decision 1 rules it out entirely.
