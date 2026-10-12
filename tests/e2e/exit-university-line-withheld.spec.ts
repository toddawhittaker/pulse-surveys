// A drill-down week in which the comparison line is drawn and the university
// line alone is withheld (SPEC §5.1, §4.1 item 7; ADR 0179 and ADR 0203).
//
// **The reader.** The mock world's lead faculty is given a LEAD_FACULTY seat over
// BIOL 310 for the run, so every BIOL 310 section, in either term, is in their
// purview and is something they can subtract. `BIOL-310-R7FF`'s default
// comparison set is BIOL 310's lead's courses at its length and level, which
// is the prior term's BIOL 310 sections: all inside the purview, so nothing is
// left for this reader to isolate and the comparison line is drawn. The
// university is every section of that length and level; less the purview it is
// the prior term's `BIOL-215-U8FF`, with at most `BIOL-215-R3WW` beside it. That
// is fewer sections than SPEC §11's section minimum and it is not empty, so the
// university line is withheld from this reader.
//
// **The world** is the one `instructor-report-benchmarks.spec.ts` builds: the
// prior term stood up and answered, `BIOL-310-R7FF` launched at its own start
// and given its demo story. Every instant comes from the seeded calendar: the
// reports are read an hour after `R7FF`'s sixth week's report opens, derived
// from that week's window. The seat is removed and the clock cleared afterwards;
// the world's rows are the seeders', which a second run rewrites in place.
//
// The payload is read and asserted first, then the page.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect, type Page } from '@playwright/test';

import { expectNoAxeViolations } from './support/axe';
import { seedTheBenchmarkHistory } from './support/benchmarkWorld';
import { clearTheClock, setTheClockTo } from './support/clock';
import { launchAs, placementInto, signInAs } from './support/doors';
import { databaseStatement, deriveSurveyWindows, seedTheDemoStory } from './support/stack';
import { INSTRUCTOR_SUBJECT, INSTRUCTOR_VIEW, sectionStartClock } from './support/survey';

const HERO = { label: 'BIOL-310-R7FF', code: 'R7FF', lengthWeeks: 12 };
const READ_WEEK = 6;

const LEAD_WEB_SUBJECT = 'mock-idp-user-lead-faculty';
const LEAD_PERSON = `(select id from person where identity_name = 'Demo Mock-World Lead Faculty')`;
const SECTION = `(select id from section where lms_section_code = '${HERO.code}')`;
const THE_COURSE = `(select course_id from section where lms_section_code = '${HERO.code}')`;
const INSTITUTION_ZONE = 'America/New_York';

const DRILL_DOWN = 'pulse-leadership-drill-down';
const COMPARISON_LINE = 'trend-line-comparison';
const UNIVERSITY_LINE = 'trend-line-university';
const COMPARISON_NOTICE = 'trend-suppression-comparison';
const UNIVERSITY_NOTICE = 'trend-suppression-university';
const COMPARISON_CELL = 'stat-cell-comparison';
const UNIVERSITY_CELL = 'stat-cell-university';

// Governed copy, transcribed from `frontend/src/copy/instructorReportTrendCopy.ts`
// and `frontend/src/copy/instructorReportStatCopy.ts`.
const UNIVERSITY_SUPPRESSED =
  'University: no line on this chart. The set behind it is too small to report on.';
const WITHHELD = 'Not shown';

const WORLD_TIMEOUT_MS = 600_000;
const CASE_TIMEOUT_MS = 120_000;

interface ComparisonFigure {
  readonly suppressed: boolean;
  readonly figure: number | null;
}

interface BenchmarkSeries {
  readonly points: readonly { readonly course_week: number; readonly mean: ComparisonFigure }[];
}

interface ReportPayload {
  readonly week: { readonly course_week: number };
  readonly streams: Record<
    string,
    { readonly benchmark?: { comparison: BenchmarkSeries; university: BenchmarkSeries } }
  >;
  readonly workload_benchmark?: {
    readonly comparison: { readonly mean: ComparisonFigure };
    readonly university: { readonly mean: ComparisonFigure };
  };
}

let sectionId = '';
let leadSeat = '';

test.describe.configure({ mode: 'serial' });

function reportable(figure: ComparisonFigure | undefined): boolean {
  return figure !== undefined && !figure.suppressed && typeof figure.figure === 'number';
}

function drawableWeeks(series: BenchmarkSeries | undefined): number {
  return (series?.points ?? []).filter((point) => reportable(point.mean)).length;
}

/** The minute an hour after one course week's report opens, from that week's window. */
function anHourAfterTheReportOpens(courseWeek: number): string {
  return databaseStatement(
    'select to_char(' +
      `date_trunc('week', closes_at at time zone '${INSTITUTION_ZONE}') ` +
      `+ interval '7 days 7 hours', 'YYYY-MM-DD"T"HH24:MI') ` +
      `from survey_window where section_id = ${SECTION} ` +
      `order by opens_at offset ${String(courseWeek - 1)} limit 1;`,
  );
}

test.beforeAll(async ({ browser }) => {
  test.setTimeout(WORLD_TIMEOUT_MS);
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    await seedTheBenchmarkHistory(page);

    const placement = await placementInto(page, INSTRUCTOR_SUBJECT, HERO.label);
    await setTheClockTo(page, sectionStartClock(HERO.code));
    await launchAs(page, INSTRUCTOR_SUBJECT, placement);
    await expect(page.getByTestId(INSTRUCTOR_VIEW)).toBeVisible();
    deriveSurveyWindows();

    sectionId = databaseStatement(`select ${SECTION};`);
    expect(sectionId, `${HERO.label} was not provisioned by the staff launch.`).toMatch(
      /^[0-9a-f-]{36}$/,
    );
    const readAt = anHourAfterTheReportOpens(READ_WEEK);
    expect(readAt, 'The read minute could not be derived from the window.').toMatch(
      /^\d{4}-\d\d-\d\dT07:00$/,
    );
    await setTheClockTo(page, readAt);
    expect(seedTheDemoStory()).toContain(HERO.label);

    leadSeat = databaseStatement(
      'insert into role_assignment (person_id, role, course_id) ' +
        `select ${LEAD_PERSON}, 'LEAD_FACULTY', ${THE_COURSE} returning id;`,
    );
    expect(leadSeat, 'The lead seat over BIOL 310 was not written.').toMatch(/^[0-9a-f-]{36}$/);
  } finally {
    await context.close();
  }
});

test.afterAll(async ({ browser }) => {
  const context = await browser.newContext();
  try {
    try {
      if (leadSeat !== '') {
        databaseStatement(`delete from role_assignment where id = '${leadSeat}';`);
      }
    } finally {
      await clearTheClock(await context.newPage());
    }
  } finally {
    await context.close();
  }
});

/** The drill-down's report, read from its route with the page's own session. */
async function theDrillDownPayload(page: Page): Promise<ReportPayload> {
  const token = await page.evaluate(() => window.sessionStorage.getItem('pulse.session'));
  expect(token, 'The web login handed over no session.').not.toBeNull();
  const headers = { Authorization: `Bearer ${token ?? ''}`, Accept: 'application/json' };
  const weeks = await page.request.get(`/leadership/sections/${sectionId}/published-weeks`, {
    headers,
  });
  expect(weeks.status()).toBe(200);
  const published = ((await weeks.json()) as { published_weeks: number[] }).published_weeks;
  expect(published).toContain(READ_WEEK);
  const answer = await page.request.get(
    `/leadership/sections/${sectionId}/weeks/${String(READ_WEEK)}/report`,
    { headers },
  );
  expect(answer.status()).toBe(200);
  return (await answer.json()) as ReportPayload;
}

test('a lead reads a week whose comparison line is drawn and whose university line is withheld', async ({
  page,
}) => {
  test.setTimeout(CASE_TIMEOUT_MS);
  await signInAs(page, LEAD_WEB_SUBJECT);
  await expect(page.getByTestId('pulse-landing-leadership')).toBeVisible();

  const payload = await theDrillDownPayload(page);
  expect(payload.week.course_week).toBe(READ_WEEK);
  for (const stream of ['instructor', 'course']) {
    const benchmark = payload.streams[stream]?.benchmark;
    expect(
      drawableWeeks(benchmark?.comparison),
      `The ${stream} stream's comparison line is withheld from the lead.`,
    ).toBeGreaterThan(0);
    expect(
      benchmark?.university.points.length ?? 0,
      `The ${stream} stream carries no university series, so nothing was withheld.`,
    ).toBeGreaterThan(0);
    expect(
      drawableWeeks(benchmark?.university),
      `The ${stream} stream's university line reached the lead.`,
    ).toBe(0);
  }
  expect(reportable(payload.workload_benchmark?.comparison.mean)).toBe(true);
  expect(reportable(payload.workload_benchmark?.university.mean)).toBe(false);

  await page.goto(`/app/leadership/sections/${sectionId}?week=${String(READ_WEEK)}`);
  const report = page.getByTestId(DRILL_DOWN);
  await expect(report).toBeVisible();

  await expect(report.getByTestId(COMPARISON_LINE)).toHaveCount(2);
  await expect(report.getByTestId(COMPARISON_NOTICE)).toHaveCount(0);
  await expect(report.getByTestId(UNIVERSITY_LINE)).toHaveCount(0);
  await expect(report.getByTestId(UNIVERSITY_NOTICE)).toHaveCount(2);
  await expect(report.getByText(UNIVERSITY_SUPPRESSED).first()).toBeVisible();

  const comparisonCells = report.getByTestId(COMPARISON_CELL);
  const universityCells = report.getByTestId(UNIVERSITY_CELL);
  await expect(comparisonCells).toHaveCount(2);
  await expect(universityCells).toHaveCount(2);
  for (const cell of await comparisonCells.all()) {
    await expect(cell).toContainText(/\d+\.\d h/);
  }
  for (const cell of await universityCells.all()) {
    await expect(cell).toContainText(WITHHELD);
    await expect(cell).not.toContainText(/\d/);
  }

  await expectNoAxeViolations(page, 'The drill-down with the university line withheld');
});
