// E5-14 — E5's exit drive: three lines benchmarked against prior terms, on
// consecutive weeks, and a student seat that carries none of it. SPEC §14.3
// (E5's exit line), §5.1, §4.1 items 1 and 7, §9.2.
//
// **What this file proves.** E5-14's first acceptance criterion, against a world
// it builds on the running stack:
//
//   - **three lines, and prior-term reach shown by value.** `BIOL-310-R7FF`'s
//     report is walked from course week 6 down to course week 1 with the week
//     navigation, and at every stop the payload's default-set comparison is
//     required to equal a literal measured off the seeded world, and the page to
//     draw three lines per panel. The reach is proved by those values, not by the
//     legend: the default set is exactly the three Spring 2026 `BIOL-310`
//     sections, and its current-term part is **empty** — so with the prior term
//     excluded, SPEC §5.1's default set would hold 0 sections, every figure below
//     would be withheld, and none of these literals could be served. **Three
//     lines means three different lines**: at every stop the university point
//     and the university workload mean are also required to differ from the
//     comparison ones, because a university line drawn exactly on top of the
//     comparison line is counted as a line and read as two (the epic-exit
//     review on bf729fc measured that collapse on the seeded world; the seed's
//     `BIOL-215-U8FF` is the repair);
//   - **every suppression treatment**, on `BIOL-215-R3WW`, whose default set is
//     empty: every default-set point and both workload figures are withheld in
//     the payload, and then the page shows the withheld treatments;
//   - **the student half, per breakdown decision 9.** E8's TrendDuo has not
//     merged, so the literal two-line walk is not here and is named in the
//     hand-off as E8's first obligation. What is here is the student-seat walk
//     of every surface that exists — landing and survey read, submit, and the
//     read after it — on two consecutive weeks, with every network response the
//     student's page receives swept for a benchmark-shaped key and every
//     rendered document swept for comparison vocabulary. The instructor's own
//     report, in the same world, is the canary that reads three lines.
//
// **Consecutive weeks on both seats, and that is `docs/MISTAKES.md` entry 51.**
// A confidentiality property proven over one payload is a property of one
// payload; a reader who keeps last Monday's report is subtracting. So the
// instructor seat is walked across six weeks and each stop is tied to its own
// week's figures — a page that kept week 6's numbers on screen while the address
// said week 5 fails — and the student seat is driven at course week 4 and then
// course week 5 of the section she answers.
//
// **Every assertion about the page is made after an assertion about the
// payload.** A withheld notice and an unseeded world render the same way, and a
// clean student screen and a blind sweep read the same way; the payload (or, on
// the student seat, the captured network responses) is what tells them apart,
// so it is read first every time.
//
// **What this file does not touch.** E4's exit story is `BIOL-215-R3WW`'s term
// of responses, written by `scripts/seed_exit_story.py` and asserted to the
// digit by `exit-instructor-report.spec.ts`. This file reads R3WW's report and
// nothing else of it: the student here answers `MATH-140-E1FF`, never R3WW, and
// the only rows this file deletes are E1FF's, which it put there. A submission
// into R3WW would also land in `BIOL-310-R7FF`'s university population — R3WW is
// twelve-week undergraduate too — and move a figure this file reads.
//
// **The clock moves, which is shared state.** `playwright.config.ts` pins
// `workers` to 1 and this file is serial. The override is cleared in `afterAll`
// inside a `finally`, so a failing assertion cannot leave the stack in October
// 2026 for whatever runs next.
//
// **Every expectation is a literal** (`docs/MISTAKES.md` entry 19). **How the
// default-set literals were derived:** independently of the code under test, by
// a measurement pass that ran SQL over the raw `answer` rows of the three Spring
// 2026 sections (`BIOL-310-U5FF`, `-U6WW`, `-R5FF`) on the seeded stack at the
// epic tip — not through the benchmark views, the set functions or the report
// API — and they are transcribed here (the E5-14 boundary ledger's
// measurements). **The university literals** were derived the same way, on the
// seed at cb5f05f: SQL over the raw `answer`, `response` and `survey_window`
// rows of the four Spring 2026 twelve-week undergraduate sections (`U5FF`,
// `U6WW`, `R5FF` and `BIOL-215-U8FF`), taking each section's course week as the
// order of its own windows, independent of the views, the set functions and the
// API. They hold only while the freeze's earliest-close cutoff admits no
// current-term answer on the seeded world, which `beforeAll`'s premise guards.
// The section codes, weeks and clocks are transcribed from the
// seeded calendar; the governed words from the copy modules, as
// `instructor-report-benchmarks.spec.ts` transcribes them.
//
// **Reach is proved by value, not by the legend.** A legend reading "Comparable
// 12-week courses" is drawn whatever the set holds; a served figure equal to a
// number computed from prior-term rows alone can only come from a set that
// reaches the prior term, because the set's current-term part is empty.
//
// **What the thin-cohort drive covers, and what it does not.** `BIOL-215-R3WW`'s
// drive exercises the **default-set** treatments only — the trend notices and the
// withheld workload cells. Its university population clears the minimums in this
// world, so the university-withheld treatment is not driven here; it is asserted
// by E5-10's `instructor-report-benchmarks.spec.ts` only in whichever direction
// the stack happens to go, and the exit record names the gap.
//
// **The university premise.** Test 1 reads the hero's university member as
// present. Under E5-14's sealing rule that holds only while the university
// complement holds no answers in course weeks 1 to 6, so `beforeAll` asserts
// that premise by name and a dirty stack fails there, not as a missing line.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect, type APIResponse, type Locator, type Page } from '@playwright/test';

import { seedTheBenchmarkHistory } from './support/benchmarkWorld';
import { clearTheClock, setTheClockTo } from './support/clock';
import { TOOL_ORIGIN, launchAs, placementInto } from './support/doors';
import { databaseStatement, deriveSurveyWindows, seedTheDemoStory } from './support/stack';
import {
  INSTRUCTOR_SUBJECT,
  LEARNER_SUBJECT,
  STUDENT_VIEW,
  SUBMIT,
  chooseRating,
  clearTheWeek,
  expectTheFormIsShowing,
  landOnTheSurvey,
  sectionBlock,
  sectionStartClock,
  setSlider,
} from './support/survey';

// ---------------------------------------------------------------------------
// The sections, and why each is the one it is.
// ---------------------------------------------------------------------------

// **The hero.** Its course, `BIOL 310`, is led by `lead-biology`
// (`scripts/seed.py`'s `LEAD_FACULTY_MAPPINGS`), so SPEC §5.1's default set —
// "the same Lead Faculty's courses filtered to matching length+level" — resolves
// to the three Spring 2026 `BIOL-310` sections `mock-lms/app/seed.py` publishes:
// `U5FF`, `U6WW` and `R5FF`, twelve-week undergraduate like this one. No
// current-term section joins them. It is also the section E4-20's demo story
// writes, which is what gives it a line of its own.
const HERO = { label: 'BIOL-310-R7FF', code: 'R7FF', menuName: 'BIOL 310 R7FF', lengthWeeks: 12 };

// **The thin cohort.** `BIOL 215` is one of the nine courses `scripts/seed.py`
// deliberately maps to no lead ("it deliberately gets no lead"), so this
// section's default set holds 0 sections, below SPEC §11's section minimum
// whatever that minimum is. Its report is read here and nothing else of it is
// touched (see the header).
const THIN = { label: 'BIOL-215-R3WW', code: 'R3WW', menuName: 'BIOL 215 R3WW', lengthWeeks: 12 };

// **The section the student answers.** The seeded learner is enrolled in it and
// in R3WW; it is a six-week section (start letter `E`), so a response in it
// reaches neither the hero's default set nor its university population.
const ANSWERED = { label: 'MATH-140-E1FF', code: 'E1FF' };

// The minute the instructor's reports are read at, transcribed from
// `instructor-report-benchmarks.spec.ts`, which transcribes it from the seeded
// calendar: start letter `R` runs twelve weeks from Monday 7 September 2026, and
// SPEC §3.1 shuts each week's window on the Sunday at 23:59:59, so at 09:00 on
// Monday 19 October course weeks 1 to 6 have closed. E4-20's demo story writes
// a response for every week whose window has closed at the effective clock.
const READ_CLOCK = '2026-10-19T09:00';

// The weeks `BIOL-310-R7FF` has published at `READ_CLOCK`, for the reason above,
// and the order the walk visits them in.
const PUBLISHED_AT_READ_CLOCK = [1, 2, 3, 4, 5, 6];
const THE_WALK = [6, 5, 4, 3, 2, 1];

// The student's two consecutive weeks. The seeded term begins Monday 17 August
// 2026 and start letter `E` runs six weeks from that day, so `MATH-140-E1FF`'s
// course week 4 runs 7–13 September and course week 5 runs 14–20 September;
// SPEC §3.1 opens each week's survey on the Friday at 18:00. So at 19:00 on
// Friday 11 September course week 4's window is open, and at 19:00 on Friday 18
// September course week 5's is. The first minute is the one
// `student-survey-confidentiality.spec.ts` and
// `student-benchmark-exclusion.spec.ts` already stand the learner on.
const STUDENT_WEEKS = [
  { courseWeek: 4, clock: '2026-09-11T19:00' },
  { courseWeek: 5, clock: '2026-09-18T19:00' },
];

// The hours the student reports. Not a figure any benchmark on the hero's report
// carries (the table below), so a screen showing it is showing her own answer.
const STUDENT_HOURS = '2.5';

// ---------------------------------------------------------------------------
// The default set's figures, measured.
// ---------------------------------------------------------------------------

/**
 * `BIOL-310-R7FF`'s default-set figures at `READ_CLOCK`, by course week.
 *
 * **Measured off the seeded world on the epic tip, not computed here or by the
 * code under test.** They derive only from the three prior-term sections, whose
 * rows `scripts/seed_benchmark_history.py` writes deterministically, and every
 * response behind them was fixed in Spring 2026 — so neither the E5-14 freeze
 * ruling (a figure counts only responses fixed by the reported section's own
 * week-*w* close) nor the university sealing ruling moves any of them. The
 * trend means are rounded to four places, so they are compared to four places
 * (`toBeCloseTo(x, 4)` is |difference| < 5e-5).
 *
 * `workloadOnPage` is the pair of strings the comparison workload cells carry,
 * hand-rounded to the one decimal place the report writes hours in
 * (`\d+\.\d h`, as `instructor-report-benchmarks.spec.ts` reads them): the
 * median, then the mean. None of the means sits on a half-tenth, so the rounding
 * direction is not in question: 8.8448 → 8.8, 8.9818 → 9.0, 9.2818 → 9.3,
 * 9.1695 → 9.2, 9.375 → 9.4. **Consecutive weeks never share a pair**, which is
 * what lets a stale page fail: 6 (9.5, 9.4), 5 (9.5, 9.2), 4 (8.5, 8.8),
 * 3 (9.5, 9.3), 2 (9.0, 9.0), 1 (9.0, 8.8).
 */
const DEFAULT_SET: Readonly<
  Record<
    number,
    {
      readonly instructor: number;
      readonly course: number;
      readonly workloadMean: number;
      readonly workloadMedian: number;
      readonly workloadOnPage: readonly [string, string];
    }
  >
> = {
  1: {
    instructor: 4.0862,
    course: 4.0345,
    workloadMean: 8.8448,
    workloadMedian: 9,
    workloadOnPage: ['9.0 h', '8.8 h'],
  },
  2: {
    instructor: 3.9455,
    course: 3.8,
    workloadMean: 8.9818,
    workloadMedian: 9,
    workloadOnPage: ['9.0 h', '9.0 h'],
  },
  3: {
    instructor: 4.2545,
    course: 4.0909,
    workloadMean: 9.2818,
    workloadMedian: 9.5,
    workloadOnPage: ['9.5 h', '9.3 h'],
  },
  4: {
    instructor: 4.0,
    course: 4.1379,
    workloadMean: 8.8448,
    workloadMedian: 8.5,
    workloadOnPage: ['8.5 h', '8.8 h'],
  },
  5: {
    instructor: 3.9492,
    course: 3.8136,
    workloadMean: 9.1695,
    workloadMedian: 9.5,
    workloadOnPage: ['9.5 h', '9.2 h'],
  },
  6: {
    instructor: 3.9286,
    course: 3.8214,
    workloadMean: 9.375,
    workloadMedian: 9.5,
    workloadOnPage: ['9.5 h', '9.4 h'],
  },
};

/**
 * `BIOL-310-R7FF`'s **university** figures at `READ_CLOCK`, by course week.
 *
 * **Measured, not computed here or by the code under test**, on the seed at
 * cb5f05f: SQL over the raw `answer`, `response` and `survey_window` rows of the
 * four Spring 2026 twelve-week undergraduate sections `BIOL-310-U5FF`, `-U6WW`,
 * `-R5FF` and `BIOL-215-U8FF` (4 sections, 73 to 77 people each week), with the
 * course week taken as the order of each section's own windows — independent of
 * the benchmark views, the set functions and the report API. That population is
 * the whole university on the seeded world only because the freeze's
 * earliest-close cutoff admits no current-term answer there, which `beforeAll`'s
 * premise guards. Rounded to four places and compared to four places, like the
 * default set.
 */
const UNIVERSITY: Readonly<
  Record<
    number,
    {
      readonly instructor: number;
      readonly course: number;
      readonly workloadMean: number;
      readonly workloadMedian: number;
    }
  >
> = {
  1: { instructor: 4.1316, course: 3.9737, workloadMean: 8.7632, workloadMedian: 9 },
  2: { instructor: 4.0, course: 3.8219, workloadMean: 9.274, workloadMedian: 9.5 },
  3: { instructor: 4.2329, course: 4.0548, workloadMean: 9.2603, workloadMedian: 9.5 },
  4: { instructor: 4.0667, course: 4.1467, workloadMean: 8.94, workloadMedian: 9 },
  5: { instructor: 3.961, course: 3.8052, workloadMean: 8.974, workloadMedian: 9.5 },
  6: { instructor: 3.9474, course: 3.8816, workloadMean: 9.4276, workloadMedian: 9.5 },
};

// Four decimal places: the precision the figures above were measured to.
const MEASURED_PLACES = 4;

// ---------------------------------------------------------------------------
// Governed words and testids.
// ---------------------------------------------------------------------------

// Transcribed from `frontend/src/copy/instructorReportTrendCopy.ts` and
// `frontend/src/copy/instructorReportStatCopy.ts` the way
// `instructor-report-benchmarks.spec.ts` transcribes them. The trend notice is
// the wording E5-14's accessibility fix settles for a series with no line at
// all ("no line on this chart", replacing "no line this week").
const COMPARISON_LEGEND = `Comparable ${String(HERO.lengthWeeks)}-week courses`;
const UNIVERSITY_LEGEND = 'University';
const COMPARISON_SUPPRESSED =
  `Comparable ${String(THIN.lengthWeeks)}-week courses: no line on this chart. ` +
  'The set behind it is too small to report on.';
const WITHHELD = 'Not shown';
const CELL_TOO_SMALL = 'The set behind this figure is too small to report on.';

// The governed heading of the submitted state, transcribed from
// `frontend/src/copy/studentSurvey.ts` as `exit-weekly-survey.spec.ts` does.
const SUBMITTED_TITLE = 'Your pulse is in';

// The testids the report surface publishes (E4-11, E5-07, E5-08).
const INSTRUCTOR_LANDING = 'pulse-landing-instructor';
const REPORT = 'pulse-instructor-report';
const SECTIONS_MENU = 'pulse-instructor-sections';
const COMPARISON_LINE = 'trend-line-comparison';
const UNIVERSITY_LINE = 'trend-line-university';
const HERO_LINE_CLASS = '.pulse-trend-line';
const COMPARISON_NOTICE = 'trend-suppression-comparison';
const UNIVERSITY_NOTICE = 'trend-suppression-university';
const COMPARISON_CELL = 'stat-cell-comparison';
const UNIVERSITY_CELL = 'stat-cell-university';

// Two panels — instructor stream above, course stream below (SPEC §5.1) — so
// "three lines per panel" is two of each overlay and two hero lines.
const PANELS = 2;

// The two cells a workload population is shown as: a median and a mean.
const CELLS_PER_POPULATION = 2;

// The stems a benchmark member's key is spelled with, as
// `tests/integration/test_every_student_route_carries_nothing_of_a_benchmark.py`
// sweeps payload keys with them: a class of names rather than an enumeration, so
// a member spelled some new way is still caught (`docs/MISTAKES.md` entry 53).
const BENCHMARK_KEY_STEMS: readonly string[] = ['benchmark', 'compar', 'cohort', 'university'];

// The keys the instructor's own report must carry, found by the same walk, or
// the walk is blind.
const KEYS_THE_CANARY_MUST_FIND: readonly string[] = [
  'benchmark',
  'workload_benchmark',
  'comparison',
  'university',
];

// Every word, testid and class stem a benchmark reaches a screen as — the list
// `student-benchmark-exclusion.spec.ts` sweeps with and documents, copied
// rather than imported because a spec module is a drive, not machinery.
const SWEPT_TERMS: readonly string[] = [
  COMPARISON_LEGEND,
  'no line on this chart',
  'The set behind it is too small to report on',
  'comparable courses',
  'Mean hours, university',
  'Median hours, university',
  WITHHELD,
  'The set behind this figure is too small to report on',
  COMPARISON_LINE,
  UNIVERSITY_LINE,
  COMPARISON_NOTICE,
  UNIVERSITY_NOTICE,
  COMPARISON_CELL,
  UNIVERSITY_CELL,
  '--benchmark',
  'benchmark',
  'compar',
  'cohort',
  'university',
];

// What the hero's report must render, or the document sweep is blind. The
// withheld vocabulary is not on it — a populated set renders none — and is the
// thin-cohort test's to show.
const CANARY_ON_THE_HERO: readonly string[] = [
  COMPARISON_LEGEND,
  UNIVERSITY_LEGEND,
  'comparable courses',
  'Mean hours, university',
  COMPARISON_LINE,
  UNIVERSITY_LINE,
  COMPARISON_CELL,
  UNIVERSITY_CELL,
];

// Budgets. The world is five prior-term launches, two current-term launches, two
// seeders and a window derivation; the student case adds two instructor reads,
// two student landings, two submissions and two reloads.
const WORLD_TIMEOUT_MS = 600_000;
const CASE_TIMEOUT_MS = 240_000;

// How long one captured response body may take to be handed over before the
// sweep records it as unread, and how long the submission's own response is
// waited for. Both bounded, so no read in this file can outlast the case budget.
const BODY_READ_MS = 5_000;
const SUBMIT_WAIT_MS = 30_000;

/** The placement each section launches through, discovered in `beforeAll`. */
const placements: Record<string, string> = {};

/** The placement the learner lands through — one launch shows every section. */
let learnerPlacement = '';

// ---------------------------------------------------------------------------
// The payload, typed as the wire types it (`app/schemas/report_benchmark.py`),
// as `instructor-report-benchmarks.spec.ts` types it.
// ---------------------------------------------------------------------------

interface ComparisonFigure {
  readonly suppressed: boolean;
  readonly reason: string | null;
  readonly figure: number | null;
}

interface BenchmarkPoint {
  readonly course_week: number;
  readonly mean: ComparisonFigure;
}

interface BenchmarkSeries {
  readonly points: readonly BenchmarkPoint[];
}

interface StreamBenchmark {
  readonly comparison: BenchmarkSeries;
  readonly university: BenchmarkSeries;
}

interface WorkloadPopulation {
  readonly mean: ComparisonFigure;
  readonly median: ComparisonFigure;
}

interface ReportPayload {
  readonly week: { readonly course_week: number };
  readonly streams: Record<string, { readonly benchmark?: StreamBenchmark }>;
  readonly workload_benchmark?: {
    readonly comparison: WorkloadPopulation;
    readonly university: WorkloadPopulation;
  };
}

type Stream = 'instructor' | 'course';
const STREAMS: readonly Stream[] = ['instructor', 'course'];

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  test.setTimeout(WORLD_TIMEOUT_MS);
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    // E5-10's construction, copied rather than re-invented: the prior term
    // first, then the two current-term sections at their own start days (E4-22's
    // anchor rule — the roster sync stamps `enrollment.started_on` from the
    // effective clock and never rewrites it), then the hero's own weeks with the
    // clock forward. Every step is idempotent, so a world another spec already
    // built is rewritten to the same rows.
    await seedTheBenchmarkHistory(page);

    for (const section of [HERO, THIN]) {
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

    await setTheClockTo(page, READ_CLOCK);
    const wrote = seedTheDemoStory();
    expect(
      wrote,
      `E4-20's demo story wrote nothing into ${HERO.label}. Its output is above. Without weeks of ` +
        'its own the hero draws no line of its own, and "three lines per panel" would be asserted ' +
        'against a chart that has two.',
    ).toContain(HERO.label);

    // **The university premise, stated rather than discovered as a missing
    // line.** Under E5-14's sealing rule (ADR 0179) the hero's
    // university figure is shown only if, among other conditions, the complement
    // — the university population minus R minus the default set, where R is
    // every section, in any term, taught by any instructor of `BIOL-310-R7FF` —
    // is empty or itself clears both minimums. The default set is all Spring
    // 2026 and R takes every section the hero's instructor teaches, which in the
    // seeded world is all of them this persona launches into (`BIOL-215-R3WW`,
    // `NURS-8100-Q2FF` and the three Spring 2026 sections among them, measured).
    // So the complement's part that can hold answers is the current term's other
    // sections of the hero's length and level that **no instructor of the hero
    // teaches**. A response in one of those, in a window that closed by the
    // hero's course-week-6 close (the latest cutoff this file reads), makes the
    // complement one or two thin sections and correctly withholds the university
    // line on every week test 1 walks. E4's exit story in R3WW no longer bears on
    // this: R3WW is in R. This names that premise before any test reads a
    // report, so a stack that breaks it fails here and not as a missing line.
    //
    // The teaching grant is `role_assignment` with role `INSTRUCTOR` on a
    // section; any such row counts, ended or not, which can only take a section
    // out of the complement — the premise errs towards asking for less.
    const complementAnswers = databaseStatement(
      "select s.lms_section_code || ' holds ' || count(r.id) || ' responses' " +
        'from response r ' +
        'join section s on s.id = r.section_id ' +
        'join course c on c.id = s.course_id ' +
        'join survey_window sw on sw.section_id = r.section_id and sw.week_id = r.week_id ' +
        `join section h on h.lms_section_code = '${HERO.code}' ` +
        'join course hc on hc.id = h.course_id ' +
        'where s.term_id = h.term_id and s.length_weeks = h.length_weeks ' +
        'and c.level = hc.level and s.id <> h.id ' +
        'and not exists (select 1 from role_assignment theirs ' +
        'join role_assignment ours on ours.person_id = theirs.person_id ' +
        "where theirs.section_id = s.id and theirs.role = 'INSTRUCTOR' " +
        "and ours.section_id = h.id and ours.role = 'INSTRUCTOR') " +
        'and sw.closes_at <= (select w.closes_at from survey_window w ' +
        'where w.section_id = h.id order by w.closes_at offset 5 limit 1) ' +
        'group by s.lms_section_code order by s.lms_section_code;',
    );
    expect(
      complementAnswers,
      `PREMISE, not a defect: the hero's university complement must hold no answers in course ` +
        `weeks 1 to 6, and it holds: ${complementAnswers}. These are current-term sections of ` +
        `${HERO.label}'s length and level that none of its instructors teaches. Under the ` +
        'university sealing rule they are a thin complement, so the university line is correctly ' +
        'withheld and test 1 cannot show three lines. Some other drive wrote those responses; run ' +
        'on a freshly seeded stack rather than deleting another drive\'s rows from here.',
    ).toBe('');

    // The learner's door. Discovery only: the enrollments she is read through
    // are `00-enrollment-anchor.spec.ts`'s, dated at each section's start.
    learnerPlacement = await placementInto(page, LEARNER_SUBJECT, ANSWERED.label);
  } finally {
    await context.close();
  }
});

test.afterAll(async ({ browser }) => {
  // The student's rows first, then the clock. The rows are this file's own —
  // `MATH-140-E1FF` is the only section it answers — and the next file to read
  // that section's form expects it unanswered.
  clearTheWeek([ANSWERED.code]);

  const context = await browser.newContext();
  try {
    await clearTheClock(await context.newPage());
  } finally {
    await context.close();
  }
});

test('the hero report shows the prior-term default set on every week from 6 down to 1', async ({
  page,
}) => {
  // **Criterion 1's first half: three lines, and prior-term reach by value.**
  //
  // The counterfactual this rests on: `BIOL-310-R7FF`'s default set is
  // `U5FF`, `U6WW` and `R5FF`, all Spring 2026, and **0** current-term sections.
  // Were the prior term excluded — a filter on the current term, a term join
  // that dropped the past — the set would hold 0 sections, SPEC §4.1 item 7
  // would withhold every default-set figure on every week, and the payload
  // assertions below would fail on `suppressed: true`, not pass on some other
  // number. So a served figure equal to the prior-term literal is the reach.
  //
  // And the walk, not one Monday (`docs/MISTAKES.md` entry 51): six weeks, each
  // tied to its own figures, so a page or a payload that answered every week
  // with one week's numbers fails at the first step.
  test.setTimeout(CASE_TIMEOUT_MS);
  await setTheClockTo(page, READ_CLOCK);

  const report = await openTheReport(page, HERO);
  const sectionId = sectionIdFromTheUrl(page);
  const token = await theSessionToken(page);

  expect(
    await publishedWeeks(page, sectionId, token),
    `At ${READ_CLOCK} course weeks 1 to 6 of ${HERO.label} have closed windows and week 7 has not ` +
      'opened, so the six weeks are exactly the published set. A shorter list makes the walk below ' +
      'a walk over less than the claim.',
  ).toEqual(PUBLISHED_AT_READ_CLOCK);

  const previous = page.getByRole('button', { name: 'Previous week' });
  for (const [step, week] of THE_WALK.entries()) {
    if (step > 0) {
      await previous.click();
      await expect(page).toHaveURL(new RegExp(`[?&]week=${String(week)}(&|$)`));
    }
    const expected = DEFAULT_SET[week];
    const universityExpected = UNIVERSITY[week];
    if (expected === undefined || universityExpected === undefined) {
      throw new Error(`No measured figures for course week ${String(week)}.`);
    }

    // The payload first.
    const payload = await reportPayload(page, sectionId, token, week);
    for (const stream of STREAMS) {
      const benchmark = payload.streams[stream]?.benchmark;
      const comparison = pointFor(benchmark?.comparison, week);
      expect(
        comparison?.mean.suppressed,
        `Course week ${String(week)}'s default-set point for the ${stream} stream of ${HERO.label} ` +
          `is ${JSON.stringify(comparison)}. The set is three prior-term sections of 55 to 59 ` +
          'people a week, above both minimums; a withheld point here is the prior term not being ' +
          'reached — the one thing this test exists to catch.',
      ).toBe(false);
      expect(
        comparison?.mean.figure,
        `Course week ${String(week)}'s default-set ${stream} mean is not the prior-term figure ` +
          'measured on the seeded world. A different number means the set is not exactly U5FF, ' +
          'U6WW and R5FF — a current-term section joined it, or a prior-term one fell out.',
      ).toBeCloseTo(expected[stream], MEASURED_PLACES);

      // Any earlier week the series carries is the same prior-term figure: no
      // cutoff can move a response fixed in Spring 2026.
      for (const point of benchmark?.comparison.points ?? []) {
        const earlier = DEFAULT_SET[point.course_week];
        if (earlier === undefined || point.course_week > week) continue;
        expect(
          point.mean.figure,
          `On course week ${String(week)}'s report, the ${stream} default-set point for course ` +
            `week ${String(point.course_week)} is not that week's prior-term figure.`,
        ).toBeCloseTo(earlier[stream], MEASURED_PLACES);
      }

      // The university member: served, and **a different line from the
      // comparison one**. Counting lines cannot see two lines drawn on top of
      // each other, and the epic-exit review on bf729fc measured exactly that:
      // the freeze's earliest-close cutoff (set by the answerless U1WW/U2WW
      // cohort) counts no current-term answer, so without a prior-term section
      // outside the default set the university reduced to the same three
      // `BIOL-310` sections and equalled the comparison at every week. The
      // exit-demo fix adds `BIOL-215-U8FF` (no lead: university, not default
      // set). The university figures are literals measured by SQL on the seed
      // (`UNIVERSITY`), and the "differs" assertion is kept beside them: it says
      // what went wrong in words when the literal alone would say only "wrong".
      const university = pointFor(benchmark?.university, week);
      expect(
        university !== undefined && reportable(university.mean),
        `Course week ${String(week)}'s university point for the ${stream} stream is ` +
          `${JSON.stringify(university)}; three lines per panel needs it served.`,
      ).toBe(true);
      expect(
        university?.mean.figure,
        `Course week ${String(week)}'s university ${stream} mean is not the figure measured over ` +
          'the four Spring 2026 twelve-week undergraduate sections. A different number means the ' +
          'university population is not exactly U5FF, U6WW, R5FF and U8FF at this cutoff — a ' +
          'current-term answer counted, or a prior-term section fell out.',
      ).toBeCloseTo(universityExpected[stream], MEASURED_PLACES);
      for (const point of benchmark?.university.points ?? []) {
        const earlier = UNIVERSITY[point.course_week];
        if (earlier === undefined || point.course_week > week) continue;
        expect(
          point.mean.figure,
          `On course week ${String(week)}'s report, the ${stream} university point for course ` +
            `week ${String(point.course_week)} is not that week's measured figure.`,
        ).toBeCloseTo(earlier[stream], MEASURED_PLACES);
      }
      expect(
        university?.mean.figure,
        `Course week ${String(week)}'s university ${stream} mean equals the default-set mean ` +
          `(${String(comparison?.mean.figure)}), so the page draws the university line on top of ` +
          'the comparison line and shows two lines where it claims three. The university ' +
          "population must reach a prior-term section outside the default set (BIOL-215-U8FF, " +
          "launched by `support/benchmarkWorld.ts`) that the freeze counts.",
      ).not.toBeCloseTo(comparison?.mean.figure ?? Number.NaN, MEASURED_PLACES);
    }

    const workload = payload.workload_benchmark;
    expect(
      workload !== undefined &&
        reportable(workload.comparison.mean) &&
        reportable(workload.comparison.median),
      `Course week ${String(week)}'s default-set workload is ${JSON.stringify(workload?.comparison)}; ` +
        'the set clears both minimums, so both figures should be served.',
    ).toBe(true);
    expect(workload?.comparison.mean.figure).toBeCloseTo(expected.workloadMean, MEASURED_PLACES);
    expect(workload?.comparison.median.figure).toBeCloseTo(expected.workloadMedian, MEASURED_PLACES);
    expect(
      workload !== undefined &&
        reportable(workload.university.mean) &&
        reportable(workload.university.median),
      `Course week ${String(week)}'s university workload is ` +
        `${JSON.stringify(workload?.university)}.`,
    ).toBe(true);
    expect(workload?.university.mean.figure).toBeCloseTo(
      universityExpected.workloadMean,
      MEASURED_PLACES,
    );
    expect(workload?.university.median.figure).toBeCloseTo(
      universityExpected.workloadMedian,
      MEASURED_PLACES,
    );
    expect(
      workload?.university.mean.figure,
      `Course week ${String(week)}'s university workload mean equals the default-set workload ` +
        'mean, so the two columns report one population under two names — the same collapse the ' +
        'trend assertion above names.',
    ).not.toBeCloseTo(workload?.comparison.mean.figure ?? Number.NaN, MEASURED_PLACES);

    // Then the page: three lines per panel, no notice, and this week's figures
    // in the comparison cells — which is what ties the page to the week.
    await expect(report.getByTestId(COMPARISON_LINE)).toHaveCount(PANELS);
    await expect(report.getByTestId(UNIVERSITY_LINE)).toHaveCount(PANELS);
    await expect(report.locator(HERO_LINE_CLASS)).toHaveCount(PANELS);
    await expect(report.getByTestId(COMPARISON_NOTICE)).toHaveCount(0);
    await expect(report.getByTestId(UNIVERSITY_NOTICE)).toHaveCount(0);
    const cells = report.getByTestId(COMPARISON_CELL);
    await expect(cells).toHaveCount(CELLS_PER_POPULATION);
    const [median, mean] = expected.workloadOnPage;
    await expect(
      cells.filter({ hasText: median }),
      `Course week ${String(week)}'s comparison cells do not show the median ${median}. The ` +
        'address names this week, so a page showing another week’s figures is showing a stale ' +
        'report under a fresh address.',
    ).not.toHaveCount(0);
    await expect(cells.filter({ hasText: mean })).not.toHaveCount(0);
  }

  // The far end is a stop, so the walk above visited every published week.
  await expect(previous).toBeDisabled();
});

test('the thin cohort is withheld in the payload and shows every withheld treatment', async ({
  page,
}) => {
  // **Criterion 1's "the thin cohort's report shows every suppression
  // treatment".** `BIOL-215-R3WW`'s default set holds 0 sections because
  // `BIOL 215` has no lead (`scripts/seed.py`), so SPEC §4.1 item 7 withholds
  // every figure computed from it: every trend point, and both workload
  // statistics. The payload is read first, and required to carry the member
  // with weeks in it — an absent member renders E4's page, which carries no
  // notice either — then the page.
  test.setTimeout(CASE_TIMEOUT_MS);
  await setTheClockTo(page, READ_CLOCK);

  const report = await openTheReport(page, THIN);
  const sectionId = sectionIdFromTheUrl(page);
  const token = await theSessionToken(page);
  const published = await publishedWeeks(page, sectionId, token);
  expect(
    published,
    `${THIN.label} runs the same weeks as the hero (start letter R), so at ${READ_CLOCK} it has ` +
      'published the same six.',
  ).toEqual(PUBLISHED_AT_READ_CLOCK);
  const payload = await reportPayload(page, sectionId, token, 6);

  for (const stream of STREAMS) {
    const points = payload.streams[stream]?.benchmark?.comparison.points ?? [];
    expect(
      points.length,
      `The payload carries no default-set points for the ${stream} stream of ${THIN.label}, so ` +
        'there is nothing to have withheld and every assertion below would be about an absent ' +
        'member rather than a suppressed one.',
    ).toBeGreaterThan(0);
    for (const point of points) {
      expect(
        point.mean,
        `Course week ${String(point.course_week)}'s default-set point for the ${stream} stream of ` +
          `${THIN.label} is not withheld. Its set holds 0 sections; any served figure is a ` +
          'suppression that did not fire.',
      ).toMatchObject({ suppressed: true, figure: null });
    }
  }
  for (const statistic of ['mean', 'median'] as const) {
    expect(
      payload.workload_benchmark?.comparison[statistic],
      `The default-set workload ${statistic} for ${THIN.label} is not withheld (SPEC §4.1 item 7: ` +
        '"a mean, a median, or any other statistic").',
    ).toMatchObject({ suppressed: true, figure: null });
  }

  // Then the page: no comparison line, the notice once per panel, and the
  // workload cells in words with nothing number-shaped — a dash reads as "no
  // hours" and a "0.0" as "nobody spent any time", and neither is a suppression.
  await expect(report.getByTestId(COMPARISON_LINE)).toHaveCount(0);
  const notices = report.getByTestId(COMPARISON_NOTICE);
  await expect(notices).toHaveCount(PANELS);
  for (const notice of await notices.all()) {
    await expect(notice).toContainText(COMPARISON_SUPPRESSED);
  }
  const cells = report.getByTestId(COMPARISON_CELL);
  await expect(cells).toHaveCount(CELLS_PER_POPULATION);
  for (const cell of await cells.all()) {
    await expect(cell).toContainText(WITHHELD);
    await expect(cell).toContainText(CELL_TOO_SMALL);
    await expect(cell).not.toContainText(/\d/);
    await expect(cell).not.toContainText('—');
  }
});

test('a student seat on two consecutive weeks carries no benchmark on the wire or the screen', async ({
  page,
  browser,
}) => {
  // **Criterion 1's student half, per breakdown decision 9.** Every student
  // surface that exists — the landing with its survey read, the submission, and
  // the read after it — driven at `MATH-140-E1FF`'s course week 4 and then its
  // course week 5 (`docs/MISTAKES.md` entry 51: the sequence, not one Monday).
  // SPEC §4.1 item 1: "Students never see comparables, benchmarks, university
  // averages, or other sections — in charts, text, tooltips, exports, or aria
  // labels"; §5.4: "Students **never** see comparison-set or university lines".
  //
  // **The canary first** (`docs/MISTAKES.md` entry 3): the same network sweep
  // and the same document sweep are run over the hero's instructor report in
  // this world and required to hit. A sweep that has gone blind reports every
  // student screen clean, and that report is indistinguishable from a pass.
  test.setTimeout(CASE_TIMEOUT_MS);
  clearTheWeek([ANSWERED.code]);

  await setTheClockTo(page, READ_CLOCK);
  const instructorWire = await captureJsonResponses(page);
  const report = await openTheReport(page, HERO);
  // No wait for "network idle": a page may never go idle. The report region is
  // visible, so the report read has arrived, and every body read is bounded.
  await instructorWire.settle();
  const found = instructorWire.bodies.flatMap((body) => benchmarkKeysIn(body));
  expect(
    KEYS_THE_CANARY_MUST_FIND.filter((key) => !found.some((path) => path.endsWith(`.${key}`))),
    `The network sweep found ${JSON.stringify(found.slice(0, 12))} in ${HERO.label}'s instructor ` +
      'report, whose payload carries these members. **A red here is this file or the world, ' +
      'never the student read path**: either the world was not built, or the capture no longer ' +
      'sees the report fetch.',
  ).toEqual([]);

  // The canary's payload before its page: a drawable default-set point.
  const sectionId = sectionIdFromTheUrl(page);
  const token = await theSessionToken(page);
  const heroPayload = await reportPayload(page, sectionId, token, 6);
  expect(
    pointFor(heroPayload.streams.instructor?.benchmark?.comparison, 6)?.mean.figure,
    'The canary report does not serve the prior-term default-set figure for course week 6.',
  ).toBeCloseTo(DEFAULT_SET[6].instructor, MEASURED_PLACES);
  await expect(report.getByTestId(COMPARISON_LINE)).toHaveCount(PANELS);
  await expect(report.getByTestId(UNIVERSITY_LINE)).toHaveCount(PANELS);
  await expect(report.locator(HERO_LINE_CLASS)).toHaveCount(PANELS);
  const heroDocument = await theWholeDocument(page);
  expect(
    CANARY_ON_THE_HERO.filter((term) => !contains(heroDocument, term)),
    `The document sweep does not find these in ${HERO.label}'s own instructor report, the page ` +
      'that renders them. Until it is shown finding something, a clean student screen means only ' +
      'that it found nothing anywhere.',
  ).toEqual([]);

  // The student, in a context of her own: nothing of the instructor's session
  // or captured traffic is in it.
  const context = await browser.newContext();
  try {
    const student = await context.newPage();
    const wire = await captureJsonResponses(student);
    for (const { courseWeek, clock } of STUDENT_WEEKS) {
      const when = `${ANSWERED.label} course week ${String(courseWeek)} (${clock})`;
      // The clock is moved from the instructor's page, so the development
      // console's own traffic is never part of the student's capture.
      await setTheClockTo(page, clock);

      wire.begin(`the landing and survey read, ${when}`);
      const block = await landOnTheSurvey(student, learnerPlacement, ANSWERED.code);
      await expect(student.getByTestId(STUDENT_VIEW)).toBeVisible();
      await expect(student.getByTestId(sectionBlock(THIN.code))).toBeVisible();
      await expectTheFormIsShowing(block);
      await expectNothingOfABenchmark(student, wire, { mustMention: ANSWERED.code });

      wire.begin(`the submission, ${when}`);
      await chooseRating(block, 0, '4');
      await chooseRating(block, 1, '5');
      await setSlider(block, STUDENT_HOURS);
      // The submission's own response, waited for by name and started before
      // the click, so its status is a response in hand rather than a page that
      // went quiet. Its body is read by the capture's route, before the page
      // receives it (see `captureJsonResponses`).
      const submitted = student.waitForResponse(
        (response) => isAStudentWrite(response.request().method(), response.url()),
        { timeout: SUBMIT_WAIT_MS },
      );
      await block.getByTestId(SUBMIT).click();
      const write = await submitted;
      expect(
        write.status(),
        `The submission for ${when} answered ${String(write.status())} at ${write.url()}.`,
      ).toBeLessThan(400);
      await expect(
        block.getByText(SUBMITTED_TITLE, { exact: true }),
        `The submission for ${when} was not accepted, so the state swept below was never reached.`,
      ).toBeVisible();
      await expectNothingOfABenchmark(student, wire, { mustWrite: true });

      wire.begin(`the read after submitting, ${when}`);
      await student.reload();
      await expect(
        student.getByTestId(sectionBlock(ANSWERED.code)).getByText(SUBMITTED_TITLE, { exact: true }),
        `After reloading, ${when} does not read back as submitted, so this is not the read after.`,
      ).toBeVisible();
      await expectNothingOfABenchmark(student, wire, { mustMention: ANSWERED.code });
    }
  } finally {
    await context.close();
    clearTheWeek([ANSWERED.code]);
  }
});

// ---------------------------------------------------------------------------
// The student-seat sweep.
// ---------------------------------------------------------------------------

/** One JSON body the page received, and the stage it arrived in. */
interface CapturedBody {
  readonly stage: string;
  readonly url: string;
  readonly text: string;
}

/** A capture of every tool-origin JSON response one page receives. */
interface JsonCapture {
  readonly bodies: CapturedBody[];
  /**
   * JSON responses whose body could not be read within `BODY_READ_MS`, as
   * "stage: METHOD url". The sweep vouches only for what it read, so each of
   * these is a named failure rather than a clean result.
   */
  readonly unread: string[];
  /** Every write to the student API the route fetched, with what it answered. */
  readonly writes: {
    readonly stage: string;
    readonly url: string;
    readonly status: number;
    readonly type: string;
  }[];
  begin(stage: string): void;
  settle(): Promise<void>;
  stage(): string;
}

/**
 * Capture every JSON response from the tool that this page's own traffic
 * receives, reading each body the moment the response arrives.
 *
 * `page.request` reads go through a separate request context and are **not**
 * captured, so what is swept is exactly what the student's browser was sent.
 *
 * **Every body read is bounded, and that is the repair for a measured hang.** CI
 * run 35818899760 on ce9df73 showed a body read after the submission that never
 * returned, followed by a wait for network idle that never came, until the
 * test's budget ran out. So nothing here waits for the page to go quiet, and a
 * body the browser will not hand over within `BODY_READ_MS` is recorded in
 * `unread` — which the sweep then fails on by name. Recording it keeps the
 * sweep's promise honest: it never reports a body it did not read as clean.
 */
async function captureJsonResponses(page: Page): Promise<JsonCapture> {
  let current = 'before any stage';
  const pending: Promise<void>[] = [];
  const capture: JsonCapture = {
    bodies: [],
    unread: [],
    writes: [],
    begin(stage: string): void {
      current = stage;
    },
    async settle(): Promise<void> {
      await Promise.all(pending);
    },
    stage(): string {
      return current;
    },
  };

  // **The student's writes are read at the route, not off the response event.**
  // CI run 35823401653 on d7b4561 showed the submission's body
  // (`POST /student/submissions`) unreadable off the response event within the
  // bound — and it was the same body that hung run 35818899760, so it is
  // reproducible, not flaky: the browser does not keep that body for a reader
  // that asks after the page has taken it. So every write to the student API is
  // fetched here, its body read in full, and then handed to the page unchanged
  // (`route.fulfill` with the fetched response): the text swept is byte for byte
  // the text the page received, and it is read before the page can move on.
  // Redirects are not followed, so what the page gets is exactly what the tool
  // answered. The response-event listener below skips these same requests, so
  // no body is raced for twice.
  await page.route(
    (url) => url.href.startsWith(`${TOOL_ORIGIN}${STUDENT_API_PREFIX}`),
    async (route) => {
      const request = route.request();
      if (!isAStudentWrite(request.method(), request.url())) {
        await route.continue();
        return;
      }
      const stage = current;
      const url = request.url();
      const method = request.method();
      let fetched: APIResponse;
      try {
        fetched = await route.fetch({ maxRedirects: 0 });
      } catch {
        capture.unread.push(`${stage}: ${method} ${url} (the route could not fetch it)`);
        await route.continue();
        return;
      }
      const type = fetched.headers()['content-type'] ?? '';
      capture.writes.push({ stage, url, status: fetched.status(), type });
      if (type.includes('application/json')) {
        const text = await bodyWithin(fetched.text(), BODY_READ_MS);
        if (text === null) capture.unread.push(`${stage}: ${method} ${url}`);
        else capture.bodies.push({ stage, url, text });
      }
      await route.fulfill({ response: fetched });
    },
  );

  page.on('response', (response) => {
    const url = response.url();
    if (!url.startsWith(TOOL_ORIGIN)) return;
    const method = response.request().method();
    if (isAStudentWrite(method, url)) return;
    const type = response.headers()['content-type'] ?? '';
    if (!type.includes('application/json')) return;
    const stage = current;
    pending.push(
      bodyWithin(response.text(), BODY_READ_MS).then((text) => {
        if (text === null) capture.unread.push(`${stage}: ${method} ${url}`);
        else capture.bodies.push({ stage, url, text });
      }),
    );
  });
  return capture;
}

// The path the student API lives under, as the CI failure names it
// (`POST http://localhost:8000/student/submissions`).
const STUDENT_API_PREFIX = '/student/';

/** Whether one request is a write to the student API, which the route reads. */
function isAStudentWrite(method: string, url: string): boolean {
  return method !== 'GET' && url.startsWith(`${TOOL_ORIGIN}${STUDENT_API_PREFIX}`);
}

/** A body read that answers `null` if it fails or does not finish in time. */
function bodyWithin(read: Promise<string>, milliseconds: number): Promise<string | null> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const late = new Promise<null>((answer) => {
    timer = setTimeout(() => {
      answer(null);
    }, milliseconds);
  });
  const reading = read.then(
    (text) => text,
    () => null,
  );
  return Promise.race([reading, late]).finally(() => {
    clearTimeout(timer);
  });
}

/**
 * Require one stage's captured traffic, and then its rendered document, to carry
 * nothing of a benchmark.
 *
 * The wire before the screen, and each with its own premise: a stage that
 * captured nothing has proven nothing, so the landing and the read after are
 * required to have received a body naming the section they show. The
 * submission is required to have been fetched by the capture's route, and
 * every JSON write it fetched to have its body among those swept.
 *
 * Called only once the page shows the state the stage is about, so the reads
 * that state depends on have arrived; `settle` then waits for their bodies, each
 * bounded by `BODY_READ_MS`. Nothing waits for the network to go idle.
 */
async function expectNothingOfABenchmark(
  page: Page,
  wire: JsonCapture,
  premise: { readonly mustMention?: string; readonly mustWrite?: boolean },
): Promise<void> {
  await wire.settle();
  const stage = wire.stage();
  const bodies = wire.bodies.filter((body) => body.stage === stage);

  expect(
    wire.unread,
    `The browser did not hand over these JSON response bodies within ${String(BODY_READ_MS)}ms, ` +
      'so the sweep cannot vouch for them and refuses to call them clean. The request that ' +
      'answered each is named; a body that cannot be read is a finding, not a pass.',
  ).toEqual([]);
  if (premise.mustMention !== undefined) {
    const code = premise.mustMention;
    expect(
      bodies.some((body) => body.text.includes(code)),
      `${stage}: no JSON response the student's page received names ${code}, the section on her ` +
        `screen. Captured: ${JSON.stringify(bodies.map((body) => body.url))}. A sweep over traffic ` +
        'that does not include the survey read reports a clean wire about nothing.',
    ).toBe(true);
  }

  if (premise.mustWrite === true) {
    const writes = wire.writes.filter((write) => write.stage === stage);
    expect(
      writes.length,
      `${stage}: the capture's route fetched no write to the student API, so the submission's ` +
        'body is not among what was swept.',
    ).toBeGreaterThan(0);
    // A write that answers JSON has had its body read (or is in `unread`, which
    // failed above). One that answers no JSON carries no key to sweep; it is
    // named here, with its status and type, rather than passed over in silence.
    for (const write of writes) {
      if (write.type.includes('application/json')) {
        expect(
          bodies.some((body) => body.url === write.url),
          `${stage}: ${write.url} answered JSON and its body is not among those swept.`,
        ).toBe(true);
      } else {
        expect(
          write.status,
          `${stage}: ${write.url} answered ${String(write.status)} with content type ` +
            `${JSON.stringify(write.type)} — no JSON body, so no key to sweep — and that ` +
            'status is not a success.',
        ).toBeLessThan(400);
      }
    }
  }

  for (const body of bodies) {
    expect(
      benchmarkKeysIn(body),
      `${stage}: ${body.url} sent the student's page a benchmark-shaped key. SPEC §4.1 item 1 — ` +
        'the student payload carries no comparison member at all, not a suppressed one, not an ' +
        'empty one (E5 breakdown, the payload sketch).',
    ).toEqual([]);
  }

  const document = await theWholeDocument(page);
  for (const term of SWEPT_TERMS) {
    expect(
      contains(document, term),
      `${stage}: the student's screen carries ${JSON.stringify(term)}: ` +
        `${quotedAround(document, term)}. The whole rendered document is searched — text, ` +
        '`aria-*`, `title`, `data-testid` and class names — because SPEC §4.1 item 1 names all ' +
        'of them. If the word is there for a reason unrelated to a benchmark, narrow the stem ' +
        'and say why in the same change; never drop it.',
    ).toBe(false);
  }
}

/** Every key path in one captured body whose key is benchmark-shaped. */
function benchmarkKeysIn(body: CapturedBody): string[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(body.text);
  } catch {
    return [`${body.url} (not JSON, though its type said so)`];
  }
  const hits: string[] = [];
  const walk = (value: unknown, path: string): void => {
    if (Array.isArray(value)) {
      value.forEach((item, index) => {
        walk(item, `${path}[${String(index)}]`);
      });
      return;
    }
    if (typeof value !== 'object' || value === null) return;
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      const here = `${path}.${key}`;
      if (BENCHMARK_KEY_STEMS.some((stem) => key.toLowerCase().includes(stem))) hits.push(here);
      walk(child, here);
    }
  };
  walk(parsed, '$');
  return hits;
}

/**
 * The whole rendered document, with `<script>` and `<style>` removed — the
 * instrument `student-benchmark-exclusion.spec.ts` documents: both are the same
 * bytes on every screen, so neither can tell a leaking surface from a clean one.
 */
async function theWholeDocument(page: Page): Promise<string> {
  return page.evaluate(() => {
    const copy = document.documentElement.cloneNode(true) as HTMLElement;
    Array.from(copy.querySelectorAll('script, style')).forEach((noise) => {
      noise.remove();
    });
    return copy.outerHTML;
  });
}

/** Whether one term appears anywhere in a document, case-insensitively. */
function contains(document: string, term: string): boolean {
  return document.toLowerCase().includes(term.toLowerCase());
}

/** The document around the first occurrence of something that should not be in it. */
function quotedAround(document: string, term: string): string {
  const at = document.toLowerCase().indexOf(term.toLowerCase());
  if (at < 0) return '(nowhere)';
  return JSON.stringify(document.slice(Math.max(0, at - 120), at + term.length + 120));
}

// ---------------------------------------------------------------------------
// Reaching and reading an instructor report.
// ---------------------------------------------------------------------------

/** Whether one sealed figure is one the page may draw. */
function reportable(figure: ComparisonFigure | undefined): boolean {
  return figure !== undefined && figure.suppressed === false && typeof figure.figure === 'number';
}

/** One course week's point in a series, if the series carries it. */
function pointFor(series: BenchmarkSeries | undefined, week: number): BenchmarkPoint | undefined {
  return series?.points.find((point) => point.course_week === week);
}

/** Launch the instructor, open one section's report from the menu, answer the region. */
async function openTheReport(page: Page, section: typeof HERO): Promise<Locator> {
  await launchAs(page, INSTRUCTOR_SUBJECT, placements[section.label] ?? '');
  await expect(page.getByTestId(INSTRUCTOR_LANDING)).toBeVisible();
  const menu = page.getByTestId(SECTIONS_MENU);
  await expect(
    menu,
    'The instructor did not land on the section menu, so there is no link to open a report from.',
  ).toBeVisible();
  // Named by prefix, number and §2.2 code: this persona teaches several
  // `BIOL 310` and `BIOL 215` sections once the prior term exists.
  await menu.getByRole('link', { name: new RegExp(section.menuName) }).click();
  const report = page.getByTestId(REPORT);
  await expect(report).toBeVisible();
  return report;
}

/** The section key the report's own address carries. */
function sectionIdFromTheUrl(page: Page): string {
  const found = /\/instructor\/sections\/([0-9a-f-]+)/.exec(page.url());
  expect(found, `The report's address does not carry a section key: ${page.url()}`).not.toBeNull();
  return found?.[1] ?? '';
}

/** The session the instructor launch handed the page. */
async function theSessionToken(page: Page): Promise<string> {
  const token = await page.evaluate(() => window.sessionStorage.getItem('pulse.session'));
  expect(
    token,
    'The instructor launch handed over no session, so nothing below is a read of the report.',
  ).not.toBeNull();
  return token ?? '';
}

/** The published weeks the route answers for one section. */
async function publishedWeeks(page: Page, sectionId: string, token: string): Promise<number[]> {
  const answer = await page.request.get(`/instructor/sections/${sectionId}/published-weeks`, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
  });
  expect(answer.status()).toBe(200);
  return ((await answer.json()) as { published_weeks: number[] }).published_weeks;
}

/** One course week's report, read from the route with the page's own session. */
async function reportPayload(
  page: Page,
  sectionId: string,
  token: string,
  week: number,
): Promise<ReportPayload> {
  const answer = await page.request.get(
    `/instructor/sections/${sectionId}/report/${String(week)}`,
    { headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' } },
  );
  expect(answer.status()).toBe(200);
  const payload = (await answer.json()) as ReportPayload;
  expect(
    payload.week.course_week,
    'The report route answered for a week other than the one that was asked for.',
  ).toBe(week);
  return payload;
}
