# 0167 — The prior-term benchmark world is a seeded calendar and a third seeder

> **Amended 2026-09-14 (E5-SEED).** The decision below is unchanged and the world
> it describes was built. Two sentences in it were wrong about what that world
> resolved to, and this says so rather than editing them out.
>
> Decision part 2 calls the three twelve-week prior-term sections
> "`BIOL-310-R7FF`'s own length and level and so its comparison set", and the last
> sentence of part 3 says the seeder's self-check "exits non-zero unless the
> comparison set clears both configured minimums". Neither was true when this was
> written. SPEC §5.1 draws a section's **default** comparison set from its
> course's Lead Faculty's courses, and `scripts/seed.py` mapped no lead to
> `BIOL 310` — so `app.services.benchmarks.resolve_default_set` answered an empty
> list for the hero section, and those three sections were in nobody's default
> set. Matching length and level is necessary and not sufficient.
>
> The self-check did not catch it because it never asked the service. It counts
> the sections and students the seeder wrote, narrowed to the section codes it was
> handed — the recount this ADR's own rejected alternative argues for — and that
> reports a full cohort whether or not any reader can resolve one.
> `docs/MISTAKES.md` entry 58 is the lesson.
>
> Closed by `scripts/seed.py` holding `BIOL 310` and `BIOL 215` as courses and
> mapping a lead faculty to `BIOL 310`. The hero's default set now holds the three
> prior-term sections, asserted through the service rather than through any
> recount. `BIOL 215` keeps no lead on purpose, so the suppressed direction is
> still demonstrable.

## Context

SPEC §5.1 compares a section against every section of its own length and level,
and SPEC §14.3's exit line for E5 says "benchmarked against prior terms". Nothing
in the demo world lived in a prior term: `scripts/seed.py` seeded Fall 2026 and
its start-letter map, the mock platform published four sections in that term, and
both story seeders (`scripts/seed_exit_story.py`, ADR 0160, and
`scripts/seed_demo_story.py`, ADR 0163) write into it. So a benchmark driven in
front of somebody had an empty comparison set, and the suppression rule — a
comparison set is shown only above a minimum number of sections and respondents
(SPEC §11, `app.config.Settings.benchmark_min_*`) — could be demonstrated only by
a unit test.

E5-12 asks for that world. SPEC is silent about demonstration data beyond naming
`scripts/seed.py` in §13, and where a prior term and its survey answers should
live is contestable, so this records the choice. ADR 0163 is the direct precedent
and this extends it backwards in time rather than inventing a third mechanism.

## Decision

**Three parts, each in the file that already owns that kind of thing.**

1. **The prior term is configuration in `scripts/seed.py`.** Spring 2026 — a
   term row, its eighteen week rows through `week_rows_for_term`, and its own
   twenty start-letter rows — seeded beside Fall 2026 by a parameterised
   `seed_term` that both terms now go through. Its dates are its own: every start
   date is a Monday of Spring's own calendar, and no date is shared with Fall's
   map. No migration: `term`, `week`, `start_letter_map` and `survey_window` are
   already per-term tables, so a second term is rows.
2. **The mock platform publishes four prior-term sections**, in
   `mock-lms/app/seed.py` beside the four current-term ones: three twelve-week
   undergraduate sections, which is `BIOL-310-R7FF`'s own length and level and so
   its comparison set, and one six-week section on its own, which is under the
   three-section minimum and exists to be suppressed. Two of the three start on
   the term's first Monday and the third three weeks later, because §5.1 aligns a
   cohort by course week rather than by calendar week and a set whose sections all
   began on one day cannot show that. The shared instructor teaches all four; the
   shared learner and the dean are in none of them.
3. **A third seeder, `scripts/seed_benchmark_history.py`**, modelled on the demo
   story's disciplines: the raw `ENVIRONMENT` refusal before any `app` import plus
   the `is_development` belt (ADR 0063), provisioning nothing, idempotent by
   natural key, deterministic per section label and course week, piped into the
   `api` container. It ends by recounting the cohorts it filled **from the
   database** — distinct sections and distinct students per cohort week — and
   exits non-zero unless the comparison set clears both configured minimums and
   the thin cohort sits under the section minimum.

**The drive is anchored, and the anchor is the load-bearing step.** The roster
sync stamps `enrollment.started_on` from the effective development clock and
never rewrites it, so each prior-term section is launched with the clock set to
its own first day, and only then synced and windowed. The runbook lives in the
new seeder's module docstring, and `scripts/seed_demo_story.py`'s docstring points
at it.

## Alternatives rejected

**Fatten `scripts/seed_demo_story.py`.** It is scoped to one section by
construction — its plan is seeded from `BIOL-310-R7FF`'s label, its roster is
found by that section's subject prefix, and its refusals name that section — so
"and also four other sections, in another term, anchored to a different clock"
would mean rewriting it rather than extending it. It also has a second reader:
its docstring is E4's demo runbook, and a runbook covering two drives with two
different clock anchors is one an operator gets wrong.

**Write into `scripts/seed_exit_story.py`'s world.** Forbidden by E5-12
criterion 5 and for a good reason: `tests/e2e/exit-instructor-report.spec.ts`
asserts that world's counts exactly, and a benchmark world reaching into it turns
E4's exit proof red.

**Seed the prior-term sections and enrollments directly into Pulse's database**,
rather than launching them from the mock platform. It would remove four manual
launches from the drive, and it is the defect `docs/MISTAKES.md` entry 48
records: a seeder that invents a section and its roster builds a world no launch
could have produced, and it makes "these rows arrived the way real ones do"
unfalsifiable. The sections are published by the platform and reach Pulse through
a staff launch and the roster sync, like every other section.

**Add the prior term as a migration.** There is nothing to migrate: every table
the calendar needs is already keyed by term. A migration would also make the demo
calendar part of the schema, which is the opposite of SPEC §6.3's position that
the map is admin-configured data.

**Let the seeder read E5-03's `benchmark_cohort_week` view for its self-check.**
The view is the thing the world is being built to feed; a check that read it
would agree with whatever the view says, including when the view is wrong. The
recount is a query of its own over the base tables, narrowed to the section codes
it is handed.

## Consequences

- The demo world now holds two terms. Anything that resolves a section by its
  §2.2 code alone is ambiguous across them in principle; the prior term's codes
  carry ordinals nothing else uses, and the new seeder resolves every section by
  `(course, term, code)`.
- `scripts/seed.py` seeds twenty more start-letter rows and eighteen more week
  rows. No section is seeded into the prior term, so nothing else in the demo
  world changes.
- The mock platform's seed grows by four sections and seventy-two students. The
  four current-term rosters, the launch-page cast and the two enrollment edge
  cases are untouched.
- The drive is longer: four anchored launches, four syncs, one window derivation
  and one seeder run, then clear the clock. The seeder's own self-check is what
  says whether the result demonstrates what it is for, rather than a person
  reading a report and hoping.
- Prior-term responses carry no comments, so no prior-term comment can reach a
  report; ratings therefore start at 3, which is what SPEC §3.2 requires of a
  response that says nothing. A benchmark figure is a workload statistic or a
  rating mean, so nothing a benchmark shows is missing.
