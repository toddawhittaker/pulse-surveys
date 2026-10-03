// The prior term's benchmark world, stood up from a browser — ticket E5-10.
//
// **Why this module exists.** SPEC §5.1 compares a section against every section
// of its own length and level, and the exit line says "benchmarked against prior
// terms". Nothing a spec can reach has a populated prior term until E5-12's
// seeder has run, and that seeder cannot run on its own: it provisions nothing —
// no section, no enrollment, no week, no window — and refuses loudly instead
// (`docs/MISTAKES.md` entry 48). What it needs first is one staff launch per
// prior-term section, each made at that section's own start day, and the windows
// derived after them.
//
// **CI does not do any of that**, and this file is the reason a spec does not
// have to ask it to. The `e2e` job in `.github/workflows/ci.yml` runs
// `python scripts/seed.py` and nothing else, so `scripts/seed_benchmark_history.py`
// is a runbook script no gate invokes. Rather than add a step to the workflow —
// which would put a benchmark world under every spec in the suite, and is a
// change to a CI gate — the drive that needs the world builds it, the way
// `exit-instructor-report.spec.ts` builds its own.
//
// **The clock is global state on a shared stack.** `playwright.config.ts` pins
// `workers` to 1 for that reason, and the one exported function here clears the
// override in a `finally`: a clock left in February 2026 fails whatever runs
// next, pointing at everything except this file.
//
// **The dates come out of the database and are written nowhere here.** The prior
// term's start-letter map is a set of rows `scripts/seed.py` writes, and a date
// typed into a spec reads from nothing and drifts from the seed silently
// (`docs/MISTAKES.md` entry 19). `support/survey.ts`'s `sectionStartClock` is the
// same rule for the *current* term, where the map is transcribed with the seed's
// own rows quoted beside it; the prior term's rows are read live instead,
// because no spec has a reason to hold a second copy of a calendar the benchmark
// world is entirely in the past of.
//
// **New machinery ships with a control that must be green** (`doors.ts`'s rule,
// and `docs/MISTAKES.md` entry 3). Two here, and neither is optional:
//
//   - every staff launch is asserted to have landed on the instructor view,
//     because a refused launch provisions nothing and stores no roster address,
//     and everything after it would be waiting for work nobody asked for;
//   - the seeder's own recount is required to say that the passing cohort clears
//     both of SPEC §11's minimums. It counts sections and distinct students out
//     of the database, per cohort week, against the configured numbers — so a
//     world too thin to demonstrate anything fails here, with the counts in the
//     message, rather than three assertions later as a report full of
//     suppression notices that look exactly like the ones a *correct* thin
//     cohort produces.

import { expect, type Page } from '@playwright/test';

import { clearTheClock, setTheClockTo } from './clock';
import { launchAs, placementInto } from './doors';
import { databaseStatement, deriveSurveyWindows, seedThePriorTermBenchmarks } from './stack';
import { INSTRUCTOR_SUBJECT, INSTRUCTOR_VIEW, type SectionUnderTest } from './survey';

/**
 * The term the benchmark world lives in, by the name `scripts/seed.py` upserts it
 * under (`PRIOR_TERM_NAME`).
 *
 * A name rather than a pair of dates, and the copy is deliberate:
 * `scripts/seed_benchmark_history.py` holds the same one for the same reason —
 * the calendar is configuration and neither file may hold a copy of it, so the
 * term is found by the one thing about it that is not a date. The refusal below
 * names both files if the row is not there.
 */
export const PRIOR_TERM_NAME = 'Spring 2026';

/**
 * The five sections `mock-lms/app/seed.py` publishes in the prior term.
 *
 * Three twelve-week undergraduate `BIOL 310` sections, which is
 * `BIOL-310-R7FF`'s own length and level and — because `BIOL 310` is led by
 * `lead-biology` — its default comparison set; one six-week section on its own,
 * which is under the three-section minimum and exists to be suppressed; and
 * `BIOL-215-U8FF`, a twelve-week undergraduate `BIOL 215` section. `BIOL 215`
 * has no lead, so `U8FF` joins the hero's **university** population and not its
 * default set — which is what makes the university line differ from the
 * comparison line on the seeded world (E5-14's exit-demo fix: without it, the
 * freeze's earliest-close cutoff leaves the university holding exactly the
 * three default-set sections, and the two lines coincide at every week).
 * The labels are the platform's and the codes are SPEC §2.2's; both are the
 * spellings `scripts/seed_benchmark_history.py`'s `PRIOR_SECTIONS` carries.
 */
export const PRIOR_SECTIONS: readonly SectionUnderTest[] = [
  { label: 'BIOL-310-U5FF', code: 'U5FF' },
  { label: 'BIOL-310-U6WW', code: 'U6WW' },
  { label: 'BIOL-310-R5FF', code: 'R5FF' },
  { label: 'BIOL-215-E5WW', code: 'E5WW' },
  { label: 'BIOL-215-U8FF', code: 'U8FF' },
];

/** The sentence the seeder prints when its recount clears both minimums. */
const BOTH_MINIMUMS_CLEARED = 'clears both minimums';

/**
 * The prior term's start-letter map, read out of the rows that hold it.
 *
 * One statement rather than one per section: the map is four rows and a round
 * trip to the database is a `docker compose exec`.
 */
function priorTermStartDates(): Map<string, string> {
  const rows = databaseStatement(
    "select m.letter || '|' || m.start_date from start_letter_map m " +
      'join term t on t.id = m.term_id ' +
      `where t.name = '${PRIOR_TERM_NAME}' order by m.letter;`,
  );
  const found = new Map<string, string>();
  for (const row of rows.split('\n')) {
    const [letter, date] = row.trim().split('|');
    if (letter === undefined || date === undefined || letter === '') continue;
    found.set(letter, date);
  }
  return found;
}

/**
 * The dev-console clock value that stands the stack on one prior-term section's
 * own first day.
 *
 * The same rule `support/survey.ts`'s `sectionStartClock` states for the current
 * term, and for the same reason: the roster sync stamps `enrollment.started_on`
 * from the effective clock the moment it first sees a member and never rewrites
 * it, so a staff launch left at the wall clock dates a prior term's students
 * today — after their term ended — and every windowed figure for the cohort is
 * then silently wrong while every row looks plausible. That is E4-22's anchor
 * rule, and `scripts/seed_benchmark_history.py`'s runbook repeats it as the one
 * step of its drive that cannot be moved.
 *
 * Noon, so the day is unambiguous in the institution's zone at any offset.
 */
function priorSectionStartClock(code: string, dates: ReadonlyMap<string, string>): string {
  const letter = code.charAt(0);
  const start = dates.get(letter);
  if (start === undefined) {
    throw new Error(
      `The ${PRIOR_TERM_NAME} term holds no start-letter row for ${JSON.stringify(letter)}, so ` +
        `there is no day to anchor ${JSON.stringify(code)}'s launch to. That term and its map are ` +
        "`scripts/seed.py`'s (E5-12), and `scripts/seed_benchmark_history.py` names the same term: " +
        'run `make migrate` and `make seed` against this stack before driving a benchmark world.',
    );
  }
  return `${start}T12:00`;
}

/**
 * Stand up the prior term's benchmark world, and answer what the seeder printed.
 *
 * E5-12's runbook, performed: for each of the five prior-term sections, stand the
 * clock on that section's own first day, launch the instructor persona into it —
 * which is what provisions the section and stores its roster address (SPEC §7.3)
 * — and derive its windows; then pipe the seeder once, which writes a term of
 * answers for every section it finds.
 *
 * **Safe to call from every spec that needs the world.** The seeder is
 * idempotent by natural key — a response is matched on `(user_id, section_id,
 * week_id)` — and a launch into a section that already exists adopts it rather
 * than provisioning a second, so a second call rewrites the same rows.
 *
 * **It leaves the clock cleared**, whatever happened, including the case where an
 * assertion inside it failed.
 *
 * The page is the caller's, so the caller owns the context this drives in. The
 * signature is one argument on purpose: E5-11 consumes this helper for the
 * student proof and has no world of its own to describe to it.
 */
export async function seedTheBenchmarkHistory(page: Page): Promise<string> {
  const dates = priorTermStartDates();
  try {
    for (const section of PRIOR_SECTIONS) {
      const placement = await placementInto(page, INSTRUCTOR_SUBJECT, section.label);
      // The clock moves **before** the launch, so the sync the launch triggers
      // judges the enrollment against the day the section began.
      await setTheClockTo(page, priorSectionStartClock(section.code, dates));
      await launchAs(page, INSTRUCTOR_SUBJECT, placement);
      await expect(
        page.getByTestId(INSTRUCTOR_VIEW),
        `The staff launch into ${section.label} did not land on the instructor view, so it ` +
          'provisioned nothing and stored no roster address. Everything after this would be ' +
          'waiting for a sync nobody asked for.',
      ).toBeVisible();
      // The windows are a scheduled job's output (ADR 0111), invoked rather than
      // waited for. Per section, because a section provisioned a moment ago has
      // none at all and the seeder reads each response's submission moment off
      // its own week's window row.
      deriveSurveyWindows();
    }

    const printed = seedThePriorTermBenchmarks();
    expect(
      printed,
      'The prior-term seeder ran and its own recount did not say the comparison set clears both ' +
        'of SPEC §11’s minimums. Its output is above: it counts sections and distinct students ' +
        'per cohort week out of the database, so this is the world that exists rather than the ' +
        'world it meant to write. A benchmark assertion made against it would be asserting a ' +
        'suppression that is real and not the one under test.',
    ).toContain(BOTH_MINIMUMS_CLEARED);
    return printed;
  } finally {
    await clearTheClock(page);
  }
}
