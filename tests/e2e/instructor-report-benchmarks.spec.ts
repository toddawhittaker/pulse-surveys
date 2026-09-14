// E5-10 — the instructor's Monday report with its comparison lines, end to end.
// SPEC §5.1, §4.1 item 7, §9.2.
//
// **What this file proves.** E5-10's first two acceptance criteria, against a
// world it builds on the running stack:
//
//   - **criterion 1**, the three-line report: a section whose comparison set is
//     populated shows three lines per panel and six workload figures, driven
//     rather than mocked — the payload is read first, then the page;
//   - **criterion 2**, the suppressed report: a section whose comparison set is
//     below SPEC §11's section minimum shows the stated treatments instead, for
//     the series and for the workload columns. Both directions, one section
//     each, which is `docs/MISTAKES.md` entry 3's pairing: a page that rendered
//     the withheld sentence everywhere would satisfy the second on its own.
//
// **Every assertion about the page is made after an assertion about the
// payload, and that ordering is the whole design.** The DOM treatment for "the
// server withheld this" and the DOM treatment for "the world was never seeded"
// are the same treatment — a notice saying the set is too small — so a spec that
// asserted the notice first would be green over a stack where the prior term
// does not exist. So each case reads the report route with the instructor's own
// session, requires of the payload the fact the case is about, and only then
// says what the page must look like. The suppressed case goes further and
// derives its DOM expectation *from* the payload it just read: the claim under
// test is that the client renders what the server said, and the server's answer
// is the only honest statement of what that is.
//
// **The world, and why this file builds it.** `scripts/seed.py` seeds structure
// and no survey data, and `.github/workflows/ci.yml`'s `e2e` job runs that and
// nothing else — so the prior term E5-12 seeds is empty on a fresh stack, and
// `scripts/seed_benchmark_history.py` is a runbook script no gate invokes.
// `support/benchmarkWorld.ts` performs that runbook from the browser, and
// `support/stack.ts` pipes E4-20's demo story into `BIOL-310-R7FF` so the hero
// section has weeks of its own to draw a line from. Neither seeder provisions
// anything: both refuse loudly, and the launches below are what gives them a
// world to write into.
//
// **The clock moves, which is shared state.** `playwright.config.ts` pins
// `workers` to 1 and this file is serial. The override is cleared in `afterAll`
// inside a `finally`, so a failing assertion cannot leave the stack in October
// 2026 for whatever runs next.
//
// **Every expectation is a literal.** The section codes and the course weeks are
// transcribed from the seeded calendar, and the governed sentences from the copy
// modules they live in — none is computed by the code under test
// (`docs/MISTAKES.md` entry 19).
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect, type Locator, type Page } from '@playwright/test';

import { seedTheBenchmarkHistory } from './support/benchmarkWorld';
import { clearTheClock, setTheClockTo } from './support/clock';
import { launchAs, placementInto } from './support/doors';
import { deriveSurveyWindows, seedTheDemoStory } from './support/stack';
import { INSTRUCTOR_SUBJECT, sectionStartClock } from './support/survey';

// ---------------------------------------------------------------------------
// The two sections, and why each is the one it is.
// ---------------------------------------------------------------------------

// **The hero: the only section whose comparison set is populated.** SPEC §5.1
// compares a section against every section of its own length and level, and the
// three prior-term `BIOL-310` sections `mock-lms/app/seed.py` publishes are
// twelve-week undergraduate sections — `BIOL-310-R7FF`'s own length and level.
// It is also the section E4-20's demo story writes, which is what gives it weeks
// of its own; no other section in this repository has both halves.
const HERO = { label: 'BIOL-310-R7FF', code: 'R7FF', menuName: 'BIOL 310 R7FF', lengthWeeks: 12 };

// **The suppressed one: a section alone in its cohort.** `BIOL-215-R3WW` is a
// twelve-week level-200 section and the prior term's only other `BIOL-215` is
// six weeks long, so its comparison set holds too few sections to clear
// `benchmark_min_sections_default`. That is a property of the seeded world
// rather than of this file, which is why the payload is read before the page.
const ALONE = { label: 'BIOL-215-R3WW', code: 'R3WW', menuName: 'BIOL 215 R3WW', lengthWeeks: 12 };

// The minute this file reads its reports at. **Transcribed from the seeded
// calendar** and chosen for one reason: E4-20's demo story writes a response for
// every week of `BIOL-310-R7FF` whose survey window has closed at the effective
// clock, and refuses when none has.
//
//   - `scripts/seed.py`'s `START_LETTER_MAP` gives start letter `R` twelve weeks
//     from Monday 7 September 2026, so `R7FF` and `R3WW` run the same weeks;
//   - SPEC §3.1 shuts each week's window on the Sunday at 23:59:59, so at
//     09:00 on Monday 19 October six of those twelve weeks have closed;
//   - which is the same clock `scripts/seed_demo_story.py`'s own runbook names.
const READ_CLOCK = '2026-10-19T09:00';

// Governed copy the report ships, transcribed from
// `frontend/src/copy/instructorReportTrendCopy.ts` and
// `frontend/src/copy/instructorReportStatCopy.ts`. Written out here rather than
// imported: a spec that asked the page what its own words were would pass
// against any words at all (`tests/e2e/landing-views.spec.ts` states the rule).
const COMPARISON_LEGEND = `Comparable ${String(HERO.lengthWeeks)}-week courses`;
const UNIVERSITY_LEGEND = 'University';
const COMPARISON_SUPPRESSED =
  `Comparable ${String(HERO.lengthWeeks)}-week courses: no line this week. ` +
  'The set behind it is too small to report on.';
const UNIVERSITY_SUPPRESSED =
  'University: no line this week. The set behind it is too small to report on.';
const WITHHELD = 'Not shown';
const TOO_SMALL = 'The set behind this figure is too small to report on.';

// The testids the report surface publishes (E4-11, E5-07, E5-08), and the
// landing every instructor launch reaches.
const INSTRUCTOR_LANDING = 'pulse-landing-instructor';
const REPORT = 'pulse-instructor-report';
const SECTIONS_MENU = 'pulse-instructor-sections';
const COMPARISON_LINE = 'trend-line-comparison';
const UNIVERSITY_LINE = 'trend-line-university';
const COMPARISON_NOTICE = 'trend-suppression-comparison';
const UNIVERSITY_NOTICE = 'trend-suppression-university';
const COMPARISON_CELL = 'stat-cell-comparison';
const UNIVERSITY_CELL = 'stat-cell-university';

// Budgets. The world is four prior-term launches, a roster sync each, two
// seeders and a window derivation — minutes rather than seconds, and a hook that
// ran out of harness rather than out of patience would read as a flake.
const WORLD_TIMEOUT_MS = 600_000;
const CASE_TIMEOUT_MS = 120_000;

/** The placement each section launches through, discovered in `beforeAll`. */
const placements: Record<string, string> = {};

// ---------------------------------------------------------------------------
// The payload, in the shape this file reads it.
//
// Typed as the wire types it — `app/schemas/report_benchmark.py`, and
// `frontend/src/api/instructor.ts` carries the same names — rather than as a
// shape of this spec's choosing, so a member renamed on the server is a
// compile-time change here and not a silently absent figure.
// ---------------------------------------------------------------------------

interface ComparisonFigure {
  readonly suppressed: boolean;
  readonly reason: string | null;
  readonly figure: number | null;
}

interface BenchmarkSeries {
  readonly points: readonly { readonly course_week: number; readonly mean: ComparisonFigure }[];
}

interface StreamBenchmark {
  readonly comparison: BenchmarkSeries;
  readonly university: BenchmarkSeries;
}

interface ReportPayload {
  readonly week: { readonly course_week: number };
  readonly section: { readonly length_weeks: number };
  readonly streams: Record<string, { readonly benchmark?: StreamBenchmark }>;
  readonly workload_benchmark?: {
    readonly comparison: { readonly mean: ComparisonFigure; readonly median: ComparisonFigure };
    readonly university: { readonly mean: ComparisonFigure; readonly median: ComparisonFigure };
  };
}

/** Whether one sealed figure is one the page may draw — the client's own rule. */
function reportable(figure: ComparisonFigure | undefined): boolean {
  return figure !== undefined && figure.suppressed === false && typeof figure.figure === 'number';
}

/** How many weeks of one series the server answered with a figure. */
function drawableWeeks(series: BenchmarkSeries | undefined): number {
  return (series?.points ?? []).filter((point) => reportable(point.mean)).length;
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  test.setTimeout(WORLD_TIMEOUT_MS);
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    // The prior term first, because it is the half that has to exist before any
    // comparison figure can. The helper anchors each launch to its own section's
    // first day, pipes E5-12's seeder, requires its recount to say both minimums
    // are cleared, and leaves the clock cleared.
    await seedTheBenchmarkHistory(page);

    // Then the two current-term sections, each launched at its own start day.
    // **The anchor rule, and it applies in this direction** (E4-22,
    // `tests/e2e/00-enrollment-anchor.spec.ts`): the roster sync stamps
    // `enrollment.started_on` from the effective clock and never rewrites it, so
    // a launch at the wall clock dates the roster the day CI happens to run.
    // Both of these sections began on 7 September 2026, which is in the past of
    // any clock this suite runs under — so this anchors backwards and cannot
    // produce the future-dated roster `instructor-report.spec.ts` measured when
    // it moved the clock forward before its own staff launches.
    for (const section of [HERO, ALONE]) {
      placements[section.label] = await placementInto(page, INSTRUCTOR_SUBJECT, section.label);
      await setTheClockTo(page, sectionStartClock(section.code));
      await launchAs(page, INSTRUCTOR_SUBJECT, placements[section.label] ?? '');
      await expect(
        page.getByTestId(INSTRUCTOR_LANDING),
        `The staff launch into ${section.label} did not land, so it provisioned nothing and ` +
          'stored no roster address — and the seeder below would refuse.',
      ).toBeVisible();
      deriveSurveyWindows();
    }

    // And the hero's own weeks. The clock goes forward first because the demo
    // story writes a response for every week whose window has **closed at the
    // effective clock** and refuses when none has; it is left there, because
    // that is the minute the reports below are read at.
    await setTheClockTo(page, READ_CLOCK);
    const wrote = seedTheDemoStory();
    expect(
      wrote,
      `E4-20's demo story wrote nothing into ${HERO.label}. Its output is above. Without a week ` +
        'of its own this section draws no line of its own, and "three lines per panel" would be ' +
        'asserted against a chart that has two.',
    ).toContain(HERO.label);
  } finally {
    await context.close();
  }
});

test.afterAll(async ({ browser }) => {
  const context = await browser.newContext();
  try {
    await clearTheClock(await context.newPage());
  } finally {
    await context.close();
  }
});

test('a section with a populated comparison set shows three lines and six figures', async ({
  page,
}) => {
  // **Criterion 1.** Read the payload, require the figures to be in it, and only
  // then say what the page draws.
  test.setTimeout(CASE_TIMEOUT_MS);

  const report = await openTheReport(page, HERO);
  const payload = await theReportPayload(page);

  // The canary (`docs/MISTAKES.md` entry 3), one per thing asserted below: a
  // payload whose comparison members are all withheld satisfies every "the line
  // is drawn" assertion vacuously by failing it in the wrong place, and says
  // nothing about the page.
  for (const stream of ['instructor', 'course']) {
    const benchmark = payload.streams[stream]?.benchmark;
    expect(
      drawableWeeks(benchmark?.comparison),
      `The payload carries no drawable comparison week for the ${stream} stream of ` +
        `${HERO.label}, so the prior term's cohort is empty or below a minimum and the page ` +
        'below cannot be showing three lines whatever it renders.',
    ).toBeGreaterThan(0);
    expect(
      drawableWeeks(benchmark?.university),
      `The payload carries no drawable university week for the ${stream} stream.`,
    ).toBeGreaterThan(0);
  }
  expect(
    reportable(payload.workload_benchmark?.comparison.mean),
    "The payload's workload comparison mean is withheld, so the columns below cannot carry a " +
      'figure.',
  ).toBe(true);

  // Three lines per panel: the section's own, drawn by every report since E4,
  // and the two the payload just answered with. Two panels, so two of each
  // overlay testid.
  await expect(report.getByTestId(COMPARISON_LINE)).toHaveCount(2);
  await expect(report.getByTestId(UNIVERSITY_LINE)).toHaveCount(2);
  await expect(report.locator('.pulse-trend-line')).toHaveCount(2);

  // The legend names them, once for the pair (SPEC §5.1's one legend).
  await expect(report.getByText(COMPARISON_LEGEND, { exact: true })).toHaveCount(1);
  await expect(report.getByText(UNIVERSITY_LEGEND, { exact: true })).toHaveCount(1);

  // And no notice anywhere: a series that is drawn does not also say it is not
  // there.
  await expect(report.getByTestId(COMPARISON_NOTICE)).toHaveCount(0);
  await expect(report.getByTestId(UNIVERSITY_NOTICE)).toHaveCount(0);

  // Six workload figures, each with the unit the pair writes. The two comparison
  // columns are two cells each — a median and a mean — and none of them says the
  // figure is withheld.
  const comparisonCells = report.getByTestId(COMPARISON_CELL);
  const universityCells = report.getByTestId(UNIVERSITY_CELL);
  await expect(comparisonCells).toHaveCount(2);
  await expect(universityCells).toHaveCount(2);
  for (const cells of [comparisonCells, universityCells]) {
    for (const cell of await cells.all()) {
      await expect(cell).toContainText(/\d+\.\d h/);
      await expect(cell).not.toContainText(WITHHELD);
    }
  }
});

test('a section alone in its cohort shows the withheld treatments instead', async ({ page }) => {
  // **Criterion 2**, and the other half of entry 3's pair. The same page, the
  // same members, a section whose comparison set cannot clear SPEC §11's section
  // minimum — and the treatments SPEC §4.1 item 7 asks for, in the copy modules'
  // own words.
  test.setTimeout(CASE_TIMEOUT_MS);

  const report = await openTheReport(page, ALONE);
  const payload = await theReportPayload(page);

  // The canary, in this direction: the member has to be **there** and have weeks
  // in it. A payload with no `benchmark` member at all renders E4's page, which
  // carries no notice either, and would satisfy a bare "no line is drawn"
  // assertion perfectly.
  const instructor = payload.streams.instructor?.benchmark;
  expect(
    instructor?.comparison.points.length ?? 0,
    `The payload carries no comparison series for ${ALONE.label}, so there is nothing for the ` +
      'page to have withheld and the assertions below would be about an absent member rather ' +
      'than a suppressed one.',
  ).toBeGreaterThan(0);
  expect(
    drawableWeeks(instructor?.comparison),
    `The payload answered a drawable comparison week for ${ALONE.label}. Its cohort holds one ` +
      "section — its own — and SPEC §11's section minimum is above that, so a figure here is a " +
      'suppression that did not fire rather than a page that rendered wrongly.',
  ).toBe(0);

  // The page says so, once per panel: no line, and the notice in its place.
  await expect(report.getByTestId(COMPARISON_LINE)).toHaveCount(0);
  await expect(report.getByTestId(COMPARISON_NOTICE)).toHaveCount(2);
  await expect(report.getByText(COMPARISON_SUPPRESSED).first()).toBeVisible();

  // The university series is asserted against **what the payload said about
  // it**, because this world does not fix which way it goes: a university
  // population is every section of this length and level institution-wide, and
  // whether it clears the minimums depends on how many of them a previous spec
  // has answered. The claim under test is that the page renders the server's
  // decision, so the server's decision is what the expectation comes from.
  if (drawableWeeks(instructor?.university) > 0) {
    await expect(report.getByTestId(UNIVERSITY_LINE)).toHaveCount(2);
    await expect(report.getByTestId(UNIVERSITY_NOTICE)).toHaveCount(0);
  } else {
    await expect(report.getByTestId(UNIVERSITY_LINE)).toHaveCount(0);
    await expect(report.getByTestId(UNIVERSITY_NOTICE)).toHaveCount(2);
    await expect(report.getByText(UNIVERSITY_SUPPRESSED).first()).toBeVisible();
  }

  // The workload columns take the same treatment, cell by cell: the words, and
  // nothing number-shaped. A dash in a column of hours reads as "no hours" and a
  // "0.0" reads as "this course took nobody any time" — E5-08's named trap, and
  // neither is what a suppression says.
  expect(
    reportable(payload.workload_benchmark?.comparison.mean),
    `The payload's workload comparison mean is not withheld for ${ALONE.label}.`,
  ).toBe(false);
  const comparisonCells = report.getByTestId(COMPARISON_CELL);
  await expect(comparisonCells).toHaveCount(2);
  for (const cell of await comparisonCells.all()) {
    await expect(cell).toContainText(WITHHELD);
    await expect(cell).toContainText(TOO_SMALL);
    await expect(cell).not.toContainText(/\d/);
    await expect(cell).not.toContainText('—');
  }
});

/**
 * Launch the instructor, open one section's report from the menu, and answer the
 * report region.
 *
 * The menu is the page an instructor who teaches more than one section lands on,
 * and the seed gives this persona every section in both terms — including the
 * four prior-term ones this file's own world stood up — so the report is reached
 * by the link naming this section in full.
 */
async function openTheReport(page: Page, section: typeof HERO): Promise<Locator> {
  await launchAs(page, INSTRUCTOR_SUBJECT, placements[section.label] ?? '');
  await expect(page.getByTestId(INSTRUCTOR_LANDING)).toBeVisible();
  const menu = page.getByTestId(SECTIONS_MENU);
  await expect(
    menu,
    'The instructor did not land on the section menu, so there is no link to open a report from. ' +
      'This persona teaches every seeded section, so a redirect straight to a report means the ' +
      'section list answered with one — which is a section-list read rather than a menu bug.',
  ).toBeVisible();
  // **Named by prefix, number and §2.2 code, which is what makes it one link.**
  // The menu writes the server's governed label ("BIOL 310 R7FF — Molecular
  // Genetics, Fall 2026"), and this persona now teaches four `BIOL 310` sections
  // and two `BIOL 215` ones — the prior term's, which this file's own world
  // provisions. A locator naming only the course resolves to several links and
  // Playwright's strict mode refuses it.
  await menu.getByRole('link', { name: new RegExp(section.menuName) }).click();
  const report = page.getByTestId(REPORT);
  await expect(report).toBeVisible();
  return report;
}

/**
 * The report the page is showing, read from the route with the page's own
 * session.
 *
 * The same address, the same session and the same week the page asked for: the
 * section key comes off the report's own URL and the week off the payload the
 * route answers for the latest published one, which is what the page opens at
 * when the address names no week.
 */
async function theReportPayload(page: Page): Promise<ReportPayload> {
  const token = await page.evaluate(() => window.sessionStorage.getItem('pulse.session'));
  expect(
    token,
    'The instructor launch handed over no session, so nothing below is a read of the report.',
  ).not.toBeNull();
  const headers = { Authorization: `Bearer ${token ?? ''}`, Accept: 'application/json' };

  const found = /\/instructor\/sections\/([0-9a-f-]+)/.exec(page.url());
  expect(found, `The report's address does not carry a section key: ${page.url()}`).not.toBeNull();
  const sectionId = found?.[1] ?? '';

  const weeks = await page.request.get(`/instructor/sections/${sectionId}/published-weeks`, {
    headers,
  });
  expect(weeks.status()).toBe(200);
  const published = ((await weeks.json()) as { published_weeks: number[] }).published_weeks;
  expect(
    published.length,
    'The published-weeks route answered an empty list, so this section has no report to read and ' +
      'the page above cannot have rendered one.',
  ).toBeGreaterThan(0);
  const latest = published[published.length - 1] ?? 0;

  const answer = await page.request.get(
    `/instructor/sections/${sectionId}/report/${String(latest)}`,
    { headers },
  );
  expect(answer.status()).toBe(200);
  const payload = (await answer.json()) as ReportPayload;
  expect(
    payload.week.course_week,
    'The report route answered for a week other than the one that was asked for.',
  ).toBe(latest);
  return payload;
}
