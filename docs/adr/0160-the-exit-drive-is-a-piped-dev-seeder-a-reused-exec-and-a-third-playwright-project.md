# 0160 — The E4 exit drive is a piped development seeder, a reused `exec`, and a third Playwright project

## Context

SPEC §14.3's exit line for E4 is "an instructor opens a real Monday report for a
seeded section with a **diverging two-stream story**" — a section whose instructor
stream trends up across published weeks while its course stream trends down, with
a below-threshold week whose comments §4 conceals and a second one that together
with the first crosses §4's cumulative release threshold.

`scripts/seed.py` contains no such section, and it deliberately writes no
responses at all: it seeds an institution, a calendar, people and registrations,
and every response this system holds has come through E2-08's submit path. So the
exit drive needed a world nothing could build, and three construction questions
came with it, none of which SPEC answers:

1. **What writes the story**, given that a spec cannot ask a browser to submit
   thirty-nine responses across six weeks of pretended time without moving the
   clock into every one of those weeks in turn — and moving the clock before the
   roster sync mis-dates `enrollment.started_on` for every member of the section
   (ADR 0142, and `instructor-report.spec.ts` carries the measurement).
2. **How the two Monday jobs are run on demand**, since the summary walk and the
   release cutter are beat entries at 02:50 and 02:40 and a spec cannot wait for
   Monday.
3. **Where the drive runs in the suite**, since it rewrites everything one
   section holds and moves the one clock the stack has.

E4-06's own ticket left the second question open and *permitted* a `/dev` control
for it.

## Decision

**A development seeder, `scripts/seed_exit_story.py`, piped into the `api`
container.** It is argument-less and hardcoded to `BIOL-215-R3WW`; it is refused
outside a development environment through `app.config.is_development` before it
reads anything (ADR 0063's rule in a smaller shape, asked of the application's own
`Settings` rather than of a raw mapping, because this process *is* the
application); and it **provisions nothing** — a missing section, week, window,
question set or enrollment is a non-zero exit naming what is missing and whose job
it is, which is `docs/MISTAKES.md` entry 48's rule enforced rather than trusted.
It writes responses, answers and one `COMMENT_VALIDITY` verdict per comment, and
it writes **no `weekly_summary` and no `release_batch`**: those two are the only
things on §5.1's report that nothing but a scheduled job can produce, so a fixture
that wrote them would be a drive agreeing with itself about its own subject.

It is *piped* — `docker compose exec -T api python - < scripts/seed_exit_story.py`
— rather than executed by path, because `scripts/` is not in the `api` image:
`backend/Dockerfile` copies the application and `docker-compose.yml` mounts only
`scripts/db-init`. That is also why it cannot import `scripts/seed.py` and does
not try to; it imports `app.*`, the standard library, and SQLAlchemy, which the
image holds.

**It maintains `response.is_valid` through `app.services.validity`.** ADR 0147
makes `report_response_counts.valid_responses` a count of that column and never of
`classification`, because the verdict table is append-only and "the current
verdict" is an ordering question an aggregate cannot ask. A seeder that appended a
refusing verdict and stopped would leave a week reading a validity rate of 1.0
with the refusal sitting in the database.

**A planted verdict does not carry ADR 0054's floor pair.** That record makes
`("character-floor", "no-model")` the pair that says §3.3's character floor
decided rather than a model, and `reclassify_floored_comments` hunts exactly that
pair on an hourly beat. A seeder writing it would watch the mock provider
overwrite its own refusal within the hour. The pair written is
`("development-seed.exit-story", "no-model")`: no prompt file and no model
produced these, which is true, and outside the sweep's set.

**No new development HTTP control. The two Monday jobs run by `exec`**, through
two helpers in `tests/e2e/support/stack.ts` — `seedTheExitStory` and
`cutReleaseBatches` — beside `generateWeeklySummaries`, which E4-11 already built
that way. That is the currency this suite already uses for a job and for a SQL
statement.

**A third Playwright project, `instructor-report-exit`, ordered last.** It matches
the exit spec by filename, depends on both `chromium` and `grade-passback-exit`,
and the main project's `testIgnore` names both exit specs. It goes after the E3
exit because that drive amends two rosters this one must not meet half-applied,
and after the main project because this one rewrites everything its section holds.

## Alternatives rejected

**A `/dev` route for the seeder and for each job**, which E4-06 permitted. It is
more attack surface and a wider diff for no capability the suite lacks: the
`exec` currency already reaches both, and every route that exists is a route that
has to be gated, tested and reviewed. `app/api/dev.py` grows for controls a
browser must reach — ADR 0142's roster-sync trigger is one, because the launch
trigger debounces against five *real* minutes — and nothing here needs a browser.

**The seeder as a `scripts/seed.py` subcommand.** It would share the connection
handling, the environment guard and the `upsert` helper, and it cannot be run
where it is needed: the module is not in the image, and mounting `scripts/` into
the `api` container to make it so would put a writable host directory inside the
application container for the benefit of one spec.

**The seeder clearing its own ground in foreign-key order down to `response`,
which E4-15's work order asked for.** Measured, and not available to a script that
runs where this one does: `pulse_app` holds `DELETE` on `answer` and on nothing
else it touches, and `docker-compose.yml`'s application-environment anchor blanks
`DB_SUPERUSER` and its password for every application container in as many words —
"No application container may hold it" — so the bootstrap-superuser route
`scripts/seed.py` takes does not exist there. **Widening the grant was rejected
outright**: it is a permanent widening of the connection every screen in the
product runs on, for a development fixture, and the privilege sets are held as
equalities by invariant-marked tests. So the seeder is idempotent by matching
natural keys — `response` on `(user_id, section_id, week_id)`, `answer` on
`(response_id, question_id)`, `classification` by append with the latest verdict
governing — and it **refuses loudly** on a response of its section that its plan
does not describe, naming `clearTheWeek` as the repair.

**Driving the story through the real submit path.** It is what a purist would
want and it is not reachable: thirty-nine submissions need the clock inside six
different windows, the roster sync must run before any of them at the real clock
or every member is mis-dated for the rest of the term, and each response needs its
student launched. The drive would take an order of magnitude longer and would test
E2-08 rather than §5.1. What is kept from that stance is the line about what the
seeder may write: inputs, never outputs.

## Consequences

- **A world the product's own write path would refuse is in the development
  database.** SPEC §3.2 requires the instructor comment when the instructor rating
  is 2 or lower, and the story's week 1 has a mean of 2.0 over eight responses,
  which is unreachable with integer ratings unless several are 2 or lower — while
  the plan puts one comment per stream in that week. Nothing E4 reads asks that
  question. It is written into the seeder's own docstring rather than left to be
  discovered, and the alternative was either abandoning the fixed weekly means the
  spec asserts or writing eight comments into that week, which would make its
  comment count equal its response count and weaken the drive's own assertion that
  a summary states responses rather than comments.
- **The suite is single-shot on one database in a second way.** The exit spec's
  header already says a re-run needs the database rebuilt, and attributes it to
  `enrollment.started_on`. The sharper reason is that once this drive's cutter has
  released a section's held comments, `release_batch_member.answer_id` and
  `moderation_state.answer_id` both reference `answer` with `RESTRICT`, so
  `clearTheWeek` can never clear that section again — six specs red on a foreign
  key. On a fresh database in one run the batch is cut in the last project and
  nothing clears afterwards, which is why CI does not see it.
- **The ordering claim is only ever proven by a run of the whole suite**, which is
  the same sentence ADR 0142 already carries for `grade-passback-exit`, and it now
  covers a three-project graph rather than a two-project one.
- **`app/api/dev.py` did not grow.** Whatever E5 needs on demand starts from the
  `exec` helpers rather than from a route, and a route is the thing to argue for
  when a browser has to reach it.
