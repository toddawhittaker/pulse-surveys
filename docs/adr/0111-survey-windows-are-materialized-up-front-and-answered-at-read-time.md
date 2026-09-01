# 0111 — Survey windows are materialized up front and answered at read time

**Status:** Accepted
**Date:** 2026-09-01
**Tickets:** E2-06

## Context

[SPEC §3.1](../SPEC.md) gives the weekly rhythm — a survey window "opens Friday
18:00, closes Sunday 23:59:59" in the institution timezone — and §2.2 gives the
weeks it applies to. E2-05 shipped `survey_window` with its columns and its
cross-term rule and nothing that fills it. E2-06 is the code that fills it, and
the spec settles neither of the two questions that decision raises.

**When does a row exist?** The spec says a window opens on a Friday. It does not
say whether a row is written when the window opens, or written in advance and
compared against the clock when somebody asks. Both produce the same answer to
"is this section open right now" on a live deployment.

**Who calls the writer?** A section is discovered by a staff launch (SPEC §7.3)
and by nothing else, so sections appear at any hour of any day. Something has to
notice a section that has no windows yet.

The clock is what makes the first question sharp rather than a matter of taste.
[ADR 0109](0109-the-dev-clock-is-a-database-offset-not-a-freeze.md) puts the
development override on `app.services.clock` and lists the clocks it deliberately
does *not* reach — Celery beat's own firing schedule among them. Beat fires on
real time whatever a developer has pretended, and E2's whole reason for having a
clock control is that "what a student sees on a Friday evening has to be reachable
without waiting for one".

## Decision

**Every window a section's calendar implies is written up front, in one
idempotent pass, and open-or-closed is a comparison made when the question is
asked.** `app.services.survey_windows` holds both halves and is the only writer
of `survey_window` (ADR 0021's shape; the ticket's fourth criterion, swept by
`tests/unit/test_survey_windows_have_one_assignment_site.py`).

**The writer has two call sites, and both call the same function.**

1. A Celery task, `app.jobs.tasks.derive_survey_windows`, on a beat entry running
   `crontab(minute="30")` — minute 30 because minute 0 is E1-11's roster sync and
   the two each walk every section in the institution. It is a reconciler: a
   section that appeared mid-term gets its windows without anybody running
   anything, and staleness of up to an hour is accepted.
2. `scripts/seed.py`, after `seed_sections()`, so a freshly seeded development
   stack has windows immediately rather than at the next half past the hour.

**Both ends of a window are inclusive.** Open when
`opens_at <= instant <= closes_at`, so a section is open at exactly Friday
18:00:00 and still open at exactly Sunday 23:59:59 — the second §3.1 names. The
alternative readings differ from this one at exactly two instants in a week, and
an offset clock cannot stand on either of them, which is why
`open_window_for_section` takes an `at` a test can supply and every production
caller leaves `None`.

**A course week whose term has no `week` row yields no window, one warning and no
exception.** That is ADR 0018's lengthening gap, and repairing it — creating the
week row, or shifting the section's remaining weeks up — is E11's calendar
editor's decision, ruled at the E2 breakdown on 2026-08-31.

## Alternatives rejected

- **Materialize a window when it opens, from the beat entry.** The shape that
  writes least, and it is dead under the development clock: beat fires on real
  time (ADR 0109), so a stack pretending it is Friday 30 October would wait until
  the real Friday for its row. The clock control would appear to do nothing, which
  is the one failure E2-04 exists to prevent and the one E2-06 exists to make
  visible.
- **Write a section's windows from the flows that create sections** — the LTI
  launch and the roster sync. It is the shape with no scheduled job at all and no
  staleness. Rejected on cost, and the cost is named rather than implied: those
  are E2-02's ingestion surface, and E2-06's diff inside it would put window
  scheduling on the launch path that ticket is fixing. The price of not taking it
  is that a section can wait up to an hour for its windows.
- **Derive on read and store nothing.** No writer, no reconciler, no idempotence
  question. Rejected: it leaves E2-05's table empty in every environment forever,
  and E2-08's submissions and §3.4's participation denominator are both keyed to
  these rows — the read path would be computing a key the write path had to
  compute identically.
- **Rewriting a window that already exists** (an upsert rather than a skip). It
  looks harmless, and it takes E11's re-derivation decision every hour with
  nobody watching: a window an administrator set deliberately would be reset by a
  job nobody is looking at. The unique constraint over `(section_id, week_id)` is
  what makes the skip a guarantee rather than a convention.
- **Reading the section's code against the term's start-letter map to derive the
  windows**, rather than reading `section.length_weeks` and `section.start_date`.
  Rejected: those columns already *are* that reading — `apply_section_code` is the
  only thing that writes them (SPEC §8) — so it would ask the map a second time
  for an answer the row holds, and a window would disagree with the section it
  belongs to the first time E11 lets somebody edit a map.

## Consequences

- **A section can be up to an hour old before it has windows.** Nothing a student
  can reach is wrong in that hour — no window is open that should not be — but the
  `/dev` console reads `closed` for a section whose first Friday has passed, until
  the reconciler runs. E2-08's submit path and E2-09's read path both meet the same
  window, so neither can be more current than this job.
- **`pulse_app` needs `SELECT` and `INSERT` on `survey_window`.** The worker writes
  the rows on that connection and the console reads them on it; `UPDATE` and
  `DELETE` stay withheld, which is what makes "the writer skips, never rewrites"
  a property of the database rather than a rule the next writer has to remember.
  Like every base-table grant in this scheme, the verbs are recorded in
  `RUNTIME_BASE_TABLE_PRIVILEGES` in `tests/integration/test_identity_grants.py`.
- **The rhythm is four named constants in one module**, with §3.1 cited beside
  them. Making them editable is §6.3's configuration surface and E11's, which the
  E2 README's deliberately-not-done list records.
- **The daylight-saving conversion is per instant and not per window**, which is
  what `_instant` in that module exists to make structural: in Fall 2026 the week
  of Sunday 1 November opens on UTC-4 and closes on UTC-5, and an implementation
  resolving one offset per window is right for seventeen of the term's eighteen
  weeks.
- **One `Settings` is now constructed by `scripts/seed.py`.** It reads the
  institution timezone the way every caller of the service does; that script had
  read only its own three variables out of a resolved mapping until now.
