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
- The grants files: who writes summaries (the worker), who reads them, who
  writes moderation state (nothing yet — the grant can wait for E6 if the
  ADR says so), who writes release batches. Least privilege, stated
  per-column where that is what least privilege means.
- The `PERSON_TABLES` standing question, answered for every table this
  ticket adds, in the PR body.

## Acceptance criteria

1. `alembic upgrade head` and a full downgrade both succeed against a seeded
   database, and `alembic check` reports no drift.
2. The summary table cannot hold two rows for one section, course week and
   stream — a database constraint, proven by a refused insert, not an
   application promise.
3. The summary row requires `prompt_version` and `model_id` — a summary with
   no provenance is a refused insert.
4. The moderation status has a database-enforced value set matching §5.2's
   lifecycle vocabulary plus the initial state, and its default is the
   initial state. A planted out-of-vocabulary write is refused.
5. No table this ticket adds carries an identity column beyond what its ADR
   justifies, and the identity-column marker sweep still passes over the new
   surface.
6. The grants follow the E3-02 shape: version-numbered SQL in
   `backend/app/views_sql/`, applied by the migration, with a test asserting
   the runtime role holds exactly the declared privileges and nothing wider.
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
