# 0163 — The representative demo story is a fourth mock section and a second seeder

## Context

E4's exit story (`scripts/seed_exit_story.py`, ADR 0160) writes a hand-planned
world into `BIOL-215-R3WW`: six course weeks, eight respondents in the open ones,
one comment per stream. `tests/e2e/exit-instructor-report.spec.ts` asserts those
numbers exactly, which is what makes it a proof of SPEC §14.3's exit line.

Driven in front of somebody, that world reads as a screenshot rather than as a
section. A real Monday report carries a dozen or more comments in a week, a
response rate that is not the same every week, and a validity rate a little under
100%. The owner asked on 2026-09-09 for a second, representative story for
demonstration driving, with the parameters written into E4-20: twenty students,
and roughly 70% to 85% of them commenting each week, not the same ones every
time.

SPEC is silent on demonstration data — §13 names `seed.py` and nothing else — and
where such a story should live is genuinely contestable, so this records the
choice.

## Decision

**A fourth section in the mock platform, `BIOL-310-R7FF`, and a second seeder
beside the exit story's.**

`mock-lms/app/seed.py` gains one `MockContext`, the placement the existing
comprehension builds from it, and twenty students of the section's own, with the
shared instructor teaching it. The start letter is `R`, so the section runs the
same twelve weeks from 2026-09-07 that `BIOL-215-R3WW` does and one pretended
clock serves both stories; `310` is a course number SPEC §8's undergraduate band
admits, under the `BIOL` prefix `scripts/seed.py` already seeds. The context is
appended last, so the launch page's first offer is unmoved.

**The shared learner and the dean are not members.** A fourth open section under
the learner puts a fourth survey in front of the two student-survey specs, and
the dean's single-section shape is what `NURS-8100-Q2FF`'s five-member roster and
E1-15's launch-page fixtures rest on. Her launch-page label names the exception
rather than leaving a reader to find it in the enrollments.

`scripts/seed_demo_story.py` fills it, on the exit seeder's terms: piped into the
api container, provisioning no person, user, section, enrollment, week or survey
window and refusing by name where one is missing, writing no `weekly_summary` and
no `release_batch`, maintaining `response.is_valid` only through
`app.services.validity`, and stamping a `(prompt_version, model_id)` pair outside
ADR 0054's floor. What it does differently is that its numbers are generated
rather than planned: a generator seeded from the section code and the course week
decides who answers, who comments, on which stream, and how the ratings wobble,
so a re-run writes the same rows and no test asserts any of them — the owner's
ruling of 2026-09-09 is that this data is demonstration material and not a
contract.

**Its environment guard reads the raw `ENVIRONMENT` before any `app` import**,
where the exit seeder builds a `Settings` and asks `is_development` of it: under a
deployment environment carrying a development stack's own values, `Settings`
refuses during validation and `app.db` builds one at import (ADR 0013), so the
exit seeder's shape would meet an operator with a traceback about the AI provider
instead of a refusal about the environment. The validated field is asked as well,
once it exists.

## Alternatives rejected

**Fatten the exit story.** One story, one seeder, no new mock section. Rejected
because `tests/e2e/exit-instructor-report.spec.ts` asserts that story's counts
exactly — eight respondents, one comment per stream, seven held comments across
two quiet weeks — so adding respondents or comments turns E4's own exit proof
red. Loosening those assertions to make room would spend the proof to improve a
demonstration.

**Enrich one of the three existing mock sections.** No new context, no new
placement. Rejected for the collision `docs/MISTAKES.md` records around
`NURS-8100-Q2FF`: each of the three carries a fixture somebody depends on — the
five-member single-page roster, the add and the drop, the exit story itself — and
twenty new members in any of them moves a boundary a test is written against.

**Seed the people tool-side, straight into Pulse's database.** No mock platform
change at all: write the `user` and `enrollment` rows the story needs. Rejected
as `docs/MISTAKES.md` entry 48's defect class. A platform that offers a launch is
what says the platform holds the section; a fixture that invents the rows a
launch and a roster sync would have written builds a world no launch could have
produced, and makes "this reached the product's own database" unfalsifiable.

## Consequences

- The mock platform has four sections and forty-one people. Roster sizes are 12,
  8, 5 and 21, so the new one adds a paging case — four full pages and a last
  page of one — at no cost to the three that existed.
- The demo story is inert for every existing suite: no spec launches the new
  placement, so no tool-side row for it exists in any test world. The whole
  unit and integration suite was run to confirm it (3407 passed).
- The drive is manual and stays that way: no Makefile target and no CI step. The
  runbook is the seeder's module docstring, and it puts the development clock
  move *before* the seeder, because the seeder writes a response for every week
  whose window has closed at the effective clock and at the real clock in
  September none of this section's has.
- Two seeders now hold near-identical `one_response` and `one_answer` helpers.
  That duplication is deliberate: the exit story is frozen, `scripts/` is not a
  package, and neither file can import the other in the container they are piped
  into — so a shared helper would have to become a third thing inside `app/`,
  which is application code carrying a fixture's concerns.
- Nothing asserts the generated data. A future change to the generator can make
  the demo world implausible without any gate saying so; what the tests hold is
  the two refusals, which is where the risk of a seeder actually is.
