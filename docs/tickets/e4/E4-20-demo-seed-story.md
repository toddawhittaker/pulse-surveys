# E4-20 — A representative demo story for the Monday report

**ID:** E4-20
**Branch:** `e4/demo-seed-story`
**Depends on:** E4-15 (the exit story and its seeder are the precedent this
ticket copies, and must not be touched)
**Lane:** heavy — `scripts/` is a named row, and so is `mock-lms/`.
**Security-relevant:** only as far as any seeder is: it must refuse to run
outside development and must invent no people.

## Context

The exit story (`scripts/seed_exit_story.py`, E4-15) proves SPEC §14.3's
exit line with hand-planned numbers, and the exit e2e asserts those numbers
exactly — one comment per stream in each open week. Driven by hand, that
world reads as unrepresentatively thin: a real section's Monday report
carries a dozen or more comments a week, not one. The owner ruled on
2026-09-09 that a second, representative story should exist for demonstration
driving, with these parameters: **20 students; each week roughly 70–85% of
them submit comments, and not the same students every week.** The exit story
stays frozen — fattening it would break the exit proof.

## What this ticket builds

1. **A fourth mock LMS section, `BIOL-310-R7FF`,** in `mock-lms/app/seed.py`:
   a 12-week section starting 2026-09-07 (start letter `R` in Fall 2026's
   §2.2 start-letter map — the same calendar as the exit section, so one
   pretend clock serves both stories). It carries its own cast of 20 demo
   students, enrolled in it and nowhere else, plus the shared instructor
   teaching it. The shared learner and the dean are **not** enrolled — a new
   open section under the shared learner collides with the student-survey
   suites (docs/MISTAKES.md's NURS lesson), and the dean's one-section shape
   is load-bearing for the paging fixtures. A launch-page placement for the
   new section appears like the existing three. The section is inert in CI:
   no suite launches it, so no tool-side rows exist in any test world.

2. **`scripts/seed_demo_story.py`**, shaped exactly like the exit seeder:
   piped into the api container (`docker compose exec -T api python - <
   scripts/seed_demo_story.py`), refusing to run unless
   `app.config.is_development`, provisioning no person, section, enrollment,
   week or window — it reads them and exits non-zero naming what is missing
   (the staff launch and roster sync are the platform's job, done first). It
   writes responses, answers and comments for **every closed week at the
   effective clock**, maintains validity through
   `app.services.validity.record_verdict` and `recompute_response_validity`
   (the column's one writer), uses the exit seeder's non-floored
   `(prompt_version, model_id)` pair, and writes no `weekly_summary` and no
   `release_batch` — the real jobs produce those afterwards.

3. **The data shape, per the ruling:** each week a rotating 17–20 of the 20
   respond; a rotating 14–17 of the 20 (70–85%) leave comments, spread across
   both streams; ratings form plausible varied distributions with mild
   drift, workload hours vary; a small number of responses in some weeks are
   invalid (a too-brief comment refused through the real verdict path), so
   validity rates read realistically below 100%. Rotation and values come
   from a random generator seeded deterministically (section code + week
   number), so a re-run writes the same rows; idempotency is by natural key,
   the exit seeder's way.

4. **A drive runbook in the script's module docstring:** bring the stack up,
   migrate and seed; launch the new placement once as the instructor **at
   the real clock** (the first sync enrolls every member from the section's
   start — `app/services/enrollment_windows.py`'s tier rule); pipe the
   seeder; run `generate_weekly_summaries` and `cut_release_batches` the way
   `tests/e2e/support/stack.ts` runs jobs; set the pretend clock forward to
   read the report.

## Tests — the ruling

The owner ruled 2026-09-09 that no test asserts the generated data's
statistics: the seeder's numbers are demonstration material, not a contract.
What the red tests cover is the two guards, in pairs:

- run outside a development environment → refuses, non-zero, names the
  environment guard, writes nothing;
- run in development against a world missing the section (no staff launch
  yet) → refuses, non-zero, names the missing section, writes nothing — and
  this is also the green-direction control for the environment guard, since
  reaching the section check proves development was let through.

## Deliberately not built

- No change to `scripts/seed_exit_story.py` or the exit e2e — frozen.
- No Makefile target and no CI step — the runbook is manual by design.
- No moderation variety (flags, exclusions) — that surface is E6's.
- No engineered small-N week — the exit story already demonstrates
  suppression.
- No automation of the staff launch — the platform-first rule is the point.

## ADR

The spec is silent on demonstration data and the choice is contestable
(fatten the exit story; enrich an existing section; seed tool-side people
directly). ADR 0163 records the decision and the rejected alternatives in
this ticket's pull request.
