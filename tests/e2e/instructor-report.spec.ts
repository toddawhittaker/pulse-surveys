// E4-11 — the instructor's Monday report, end to end. SPEC §14.2 item 1, §9.2.
//
// **What this file proves.** E4-11's acceptance criteria 1, 4 and 6, against a
// world it builds on the running stack:
//
//   - **criterion 1**, the launch-to-report path: an instructor launches through
//     the mock LMS, meets the menu of sections she teaches, opens one, and reads
//     a real week — the stacked pair, both comment groups, the rates, and a
//     comment a student in this run actually wrote. Asserted on content the
//     world guarantees, never on the absence of an error.
//   - **criterion 3**, week navigation offering exactly the API's published
//     weeks: the whole list is walked from the report and compared against what
//     the published-weeks route answers, so a control that counted by one or
//     derived a range is red.
//   - **criterion 4**, the small-N week, in the only form that means anything:
//     the notice renders, no comment card exists in the DOM, **and the response
//     body itself is read and asserted to contain none of the withheld words**.
//     A DOM-only assertion passes with the leak sitting in the network response,
//     which is why the ticket names it as a trap.
//   - **criterion 6**, the addressable week: a deep link to a published week
//     renders it, and a deep link to an unpublished one renders the API's own
//     refusal with no report content beside it.
//
// **The world, and why it has to be built here.** `scripts/seed.py` seeds
// structure and deliberately no survey data — "no responses, no comments, no
// classifications" — so a report needs a week somebody answered. SPEC §4's
// threshold is 5 (`N_THRESHOLD_DEFAULT`), so the section under test needs five
// students to submit and the small-N section needs fewer. Both halves are
// submitted through the real form, through the real classifier, so what the
// report reads is what the product wrote.
//
// **How five students launch when the mock LMS's page offers three.**
// `mock-lms/app/seed.py`'s `LAUNCH_PAGE_CAST` is three people, and it says why:
// "every seeded person would put eighteen anonymous students on the page and
// make the two people every other suite launches as hard to find". The other
// students are seeded, enrolled and launchable — the page just does not list
// them. So `launchAsAStudentOfTheSection` below drives the platform's own launch
// form and rewrites one hidden field, `login_hint`, before submitting it.
//
// Nothing about that is a bypass of a control. The list of options is a demo
// affordance; the control is `mock_lms.app.launch.resolve_launch`, which
// "resolv[es] [the enrollment] from the seed rather than from the request", so a
// (user, context) pair the platform does not hold is refused however the request
// was assembled. And the substitution is controlled rather than assumed: the
// learner is enrolled in every section and these students in exactly one, so
// every substituted launch asserts that **one** section block is on screen. A
// substitution that silently did not take would land the learner, with more.
//
// **The clock moves, which is shared state.** `playwright.config.ts` pins
// `workers` to 1 and this file is serial. The override is set in `beforeAll` and
// cleared in `afterAll` inside a `finally`, so a failing assertion cannot leave
// the stack in October 2026 for whatever runs next; the responses and summaries
// this file writes are deleted on the way out for the same reason.
//
// **Every expectation is a literal.** The week numbers are transcribed from the
// seeded calendar, the threshold from `.env`'s `N_THRESHOLD_DEFAULT`, and the
// governed sentences from the copy modules they live in — none is computed by
// the code under test (`docs/MISTAKES.md` entry 19). The one thing deliberately
// *discovered* rather than transcribed is the published-week list, because
// criterion 3 is precisely that the page offers the API's list and not one of
// its own; that comparison is what the last test is.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect, type Locator, type Page } from '@playwright/test';

import { clearTheClock, setTheClockTo } from './support/clock';
import {
  LAUNCH_PLACEMENT,
  LAUNCH_SUBMIT,
  LAUNCH_USER,
  MOCK_LMS_ORIGIN,
  launchAs,
  placementInto,
  sessionToken,
} from './support/doors';
import { databaseStatement, deriveSurveyWindows, generateWeeklySummaries } from './support/stack';
import {
  INSTRUCTOR_SUBJECT,
  LEARNER_SUBJECT,
  SUBMIT,
  chooseRating,
  clearTheWeek,
  sectionBlock,
  setSlider,
  typeComment,
} from './support/survey';

// The two sections, by the label the platform writes on a placement and by SPEC
// §2.2's code. `BIOL-215-R3WW` is the week with data in it; `MATH-140-E1FF` is
// the week below the threshold, and having two of them is also what makes the
// instructor's section list long enough for the menu to be the page she lands
// on rather than a redirect.
//
// **`NURS-8100-Q2FF` is the small-N section this spec deliberately does not
// use, and the reason is a measured collision rather than a preference.** That
// section starts on 28 September, so answering a week of it means pretending it
// is October — and provisioning it into Pulse at all gives the learner an extra
// section with an open window at exactly the minute
// `student-survey-accessibility.spec.ts` and `student-survey.spec.ts` pretend
// it is (`2026-10-02T19:00`). Both files are written against a screen with one
// section on it: one counts live regions, the other requires SPEC §4.1 item 5's
// sentence in the block it names, and a second open section moves both. Neither
// failure points anywhere near this file. `MATH-140-E1FF` has no such overlap —
// it is a six-week section that ended on 26 September, so at that minute it
// offers nothing — and every other spec that reads it already expects it.
const BIOL = { label: 'BIOL-215-R3WW', code: 'R3WW' };
const MATH = { label: 'MATH-140-E1FF', code: 'E1FF' };

// The minutes this spec pretends it is: one per week it answers, and one it
// reads the reports at. **Transcribed from the seeded calendar** the way
// `exit-weekly-survey.spec.ts` transcribes it:
//
//   - `scripts/seed.py`'s `START_LETTER_MAP` gives start letter `R` twelve weeks
//     from Monday 7 September 2026 and start letter `E` six weeks from Monday 17
//     August; Fall 2026 begins Monday 17 August.
//   - So `E1FF`'s sixth and last course week runs 21 to 27 September and
//     `R3WW`'s fourth runs 28 September to 4 October. SPEC §3.1 opens each
//     week's window on the Friday at 18:00 and shuts it on the Sunday at
//     23:59:59, so Friday at 19:00 is an hour inside each.
//   - 17 August is term week 1, so 21 September is term week 6 and 28 September
//     is term week 7. The two sections sit at different offsets between the
//     axes, which is the pair SPEC §2.2's two axes exist for.
//   - Monday 5 October is after both windows shut, so both weeks are published
//     (E4's breakdown decision 6: a published week is one whose window has
//     closed).
const INSIDE_THE_MATH_WINDOW = '2026-09-25T19:00';
const INSIDE_THE_BIOL_WINDOW = '2026-10-02T19:00';
const AFTER_THE_CLOSE = '2026-10-05T09:00';
const BIOL_COURSE_WEEK = 4;
const MATH_COURSE_WEEK = 6;
const TERM_WEEK = 7;

// A course week `R3WW` runs but has not reached at this clock: the section is
// twelve weeks long and week 11 has not opened, let alone closed. Criterion 6's
// second half asks for a deep link to an unpublished week.
const AN_UNPUBLISHED_WEEK = 11;

// SPEC §4's threshold, as `.env`'s `N_THRESHOLD_DEFAULT` and
// `app.config.Settings.n_threshold_default` both set it. Written out rather than
// read from either, so this file is not agreeing with the configuration about
// what the configuration is.
const N_THRESHOLD = 5;

// The students who answer, by the identifier `mock-lms/app/seed.py`'s `student()`
// mints — `mock-lms-user-{section label, lower case}-student-{ordinal, two
// digits}`. **Ordinals 4 and 7 of `BIOL-215-R3WW` are deliberately absent**: the
// seed makes one of them a late add and the other a drop, and a spec that
// counted on either would be counting on the enrollment edge cases E0-28 put
// there.
//
// Five answer `BIOL-215-R3WW`, which is exactly SPEC §4's threshold and so the
// smallest week that shows raw comments; three answer `MATH-140-E1FF`, which is
// under it. Both counts are stated rather than derived, because "five" being the
// threshold is the whole reason the first list is the length it is.
const BIOL_STUDENTS = [
  LEARNER_SUBJECT,
  'mock-lms-user-biol-215-r3ww-student-01',
  'mock-lms-user-biol-215-r3ww-student-02',
  'mock-lms-user-biol-215-r3ww-student-03',
  'mock-lms-user-biol-215-r3ww-student-05',
];
const MATH_STUDENTS = [
  LEARNER_SUBJECT,
  'mock-lms-user-math-140-e1ff-student-01',
  'mock-lms-user-math-140-e1ff-student-02',
];

// One distinctive sentence per section, written by the first student to answer
// it. Both are comfortably over SPEC §3.3's twenty-five-character floor, neither
// carries a marker the mock model provider answers to, and neither contains a
// `|` — the column separator the database reads below come back on. They are
// distinctive so that "this comment reached the report" and "this comment did
// not reach the wire" are both statements about one sentence rather than about a
// shape of sentence.
const BIOL_DISTINCTIVE_COMMENT =
  'The Wednesday staining protocol demonstration was slow enough to actually follow this week.';
const MATH_DISTINCTIVE_COMMENT =
  'The linear systems worksheet gave us far more practice with substitution than I expected.';

// What everybody else writes. Distinct sentences rather than one repeated, so a
// failure message names which student's submission is missing, and all of them
// substantive enough that SPEC §3.3's gate accepts them.
const OTHER_COMMENTS = [
  'Office hours ran over and nobody was turned away, which made a real difference.',
  'The reading list for this week was long but the ordering made it manageable.',
  'Feedback on the last write-up was specific enough to act on before the next one.',
  'The lab pacing held up well and the worked examples afterwards were genuinely useful.',
];

// Governed copy the report ships, transcribed from
// `frontend/src/components/instructorReportPageCopy.ts` and its three siblings.
// Written out here rather than imported: a spec that asked the page what its own
// words were would pass against any words at all
// (`tests/e2e/landing-views.spec.ts` states the rule).
const PICKER_HEADING = 'Your sections';
const SMALL_N_TITLE = 'Comments are hidden this week';
const NO_RESPONSES = 'No responses yet this week';
const COMMENTS_NOTE = 'Shown in random order. No names, no timestamps.';
const COURSE_WEEK_UNAVAILABLE = 'There is no report for that week of this section.';

// The testids the report surface publishes (E4-11), and the landing every
// instructor launch reaches.
const INSTRUCTOR_LANDING = 'pulse-landing-instructor';
const REPORT = 'pulse-instructor-report';
const SECTIONS_MENU = 'pulse-instructor-sections';

// Budgets. The world is built once and it is a launch plus a form plus a
// classifier round trip per student, eight times over, on top of three staff
// launches and a roster sync — minutes rather than seconds, and a hook that ran
// out of harness rather than out of patience would read as a flake.
const WORLD_TIMEOUT_MS = 600_000;
const CASE_TIMEOUT_MS = 120_000;
const SYNC_TIMEOUT_MS = 30_000;
const SYNC_RETRY_MS = 3_000;
const RENDER_WAIT_MS = 2_000;

// How far the week walk may step before it is a control that is not stepping.
// Bounded rather than trusted: a `while` over a disabled state is a `while`
// nothing can stop if the state never arrives.
const MAX_WEEK_STEPS = 20;

/** The placement each section launches through, discovered in `beforeAll`. */
const placements: Record<string, string> = {};

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  test.setTimeout(WORLD_TIMEOUT_MS);
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    for (const section of [BIOL, MATH]) {
      placements[section.label] = await placementInto(page, LEARNER_SUBJECT, section.label);
      const forTheStaff = await placementInto(page, INSTRUCTOR_SUBJECT, section.label);
      expect(
        forTheStaff,
        `The mock platform should offer the instructor and the students the same resource link ` +
          `into ${section.label}. A roster sync is discovered per section, so a staff launch into ` +
          'one section enrols nobody in another.',
      ).toBe(placements[section.label]);
    }

    // **The staff launches happen at the real clock, and the pretended one is
    // set afterwards.** This is the opposite of `support/survey.ts`'s ordering
    // and the reason is measured rather than argued.
    //
    // `app.services.roster_sync` writes `started_on` from the **effective now**
    // when it first sights a member, and its own docstring says the value "is a
    // first-seen fact and is never rewritten — the grant does not even permit
    // it". So a sync that runs while the clock pretends it is October stamps a
    // start date a month in the future onto every enrollment in the section, and
    // every later spec that launches a student at the real clock is refused at
    // the door: the enrollment is not live yet. Nothing repairs it, because
    // nothing is allowed to.
    //
    // Measured on this stack: with the clock moved first, this file left all
    // twenty-four enrollment rows dated 2026-10-02, and `exit-weekly-survey`,
    // `lti-launch`, `student-survey` and the two specs beside it all failed
    // afterwards with a learner who could not get through the door.
    //
    // `support/survey.ts` moves the clock first for a reason that is real —
    // "a section that has not started on the real calendar has no live
    // enrollment on it" — but that reason is about a *student's* launch, and the
    // launches below are staff launches, which land whether or not the section
    // has started (measured: both do). The students launch after the clock has
    // moved, which is where that reason applies and where this file honours it.
    //
    // The clock is cleared first rather than assumed clear: this file's
    // correctness now depends on the launches happening at the real now, and a
    // spec that failed before its own `afterAll` could have left an override
    // standing.
    await clearTheClock(page);

    // SPEC §7.3: a staff launch is what stores a section's roster address, which
    // is the whole of what gives the scheduled sync anything to discover. Each
    // is asserted to have landed, because a refused launch provisions nothing
    // and every wait after it would be waiting for work nobody asked for.
    for (const section of [BIOL, MATH]) {
      await launchAs(page, INSTRUCTOR_SUBJECT, placements[section.label] ?? '');
      await expect(page.getByTestId(INSTRUCTOR_LANDING)).toBeVisible();
    }

    // The sections reached this database through those launches, so they are
    // younger than the seed and have no `survey_window` rows: they are
    // materialized up front (ADR 0111) by a job on the half hour. Run it rather
    // than wait for it.
    deriveSurveyWindows();

    // Both weeks start unanswered, so every count below is this run's.
    clearTheWeek([BIOL.code, MATH.code]);
    clearTheSummaries([BIOL.code, MATH.code]);

    // **Two weeks, two windows, so two clocks.** The sections run at different
    // times of the term — that is why one of them can be over while the other is
    // open — so there is no single minute at which both take an answer. Each
    // week is answered inside its own window, oldest first, and the report clock
    // comes last.
    await setTheClockTo(page, INSIDE_THE_MATH_WINDOW);
    await waitForTheRoster(page, MATH.label, MATH.code, MATH_STUDENTS);
    await answerTheWeek(page, MATH, MATH_STUDENTS, MATH_DISTINCTIVE_COMMENT);

    await setTheClockTo(page, INSIDE_THE_BIOL_WINDOW);
    await waitForTheRoster(page, BIOL.label, BIOL.code, BIOL_STUDENTS);
    await answerTheWeek(page, BIOL, BIOL_STUDENTS, BIOL_DISTINCTIVE_COMMENT);

    // Past both closes, which is what makes both weeks published (breakdown
    // decision 6) and what puts the instructor on the Monday the report is for.
    await setTheClockTo(page, AFTER_THE_CLOSE);

    // E4-06's Monday walk, invoked rather than waited for — the same move the
    // window derivation above makes, and for the same reason.
    generateWeeklySummaries();

    // **The tripwire on the ordering above, and it is not ceremony.** A sync
    // that first-sights a member while the clock pretends it is October stamps
    // `started_on` a month ahead, nothing may rewrite it, and every later spec
    // that launches a student at the real clock is then refused at the door —
    // a failure that lands in five other files and points at none of them. This
    // says so here, where the cause is.
    const dated = databaseStatement('select count(*) from enrollment where started_on > now();');
    expect(
      Number(dated),
      `${dated} enrollment row(s) carry a start date in the future. \`app.services.roster_sync\` ` +
        'writes `started_on` from the effective now and never rewrites it, so a roster sync that ' +
        'ran while this file’s clock was set has dated every member of those sections a month ' +
        'ahead — and `exit-weekly-survey`, `lti-launch` and the three student-survey specs will ' +
        'all fail afterwards with a learner the door refuses. The staff launches in this hook run ' +
        'at the real clock precisely so this cannot happen; if it happened anyway, the hourly ' +
        '`sync_rosters` beat fired while the override was standing, and the stack needs its ' +
        'database rebuilt (`make down && make up && make migrate && make seed`) rather than this ' +
        'assertion relaxed.',
    ).toBe(0);
  } finally {
    await context.close();
  }
});

test.afterAll(async ({ browser }) => {
  // The rows first, then the clock, and the clock inside a `finally`: a failure
  // clearing this file's data must not also leave the stack in October for
  // whatever runs next.
  const context = await browser.newContext();
  try {
    try {
      clearTheSummaries([BIOL.code, MATH.code]);
      clearTheWeek([BIOL.code, MATH.code]);
    } finally {
      await clearTheClock(await context.newPage());
    }
  } finally {
    await context.close();
  }
});

test('an instructor launches, chooses a section, and reads its week', async ({ page }) => {
  // **Criterion 1.** Every assertion is on content this run put there — a
  // student's own sentence, the section's own name, the week's own rates — and
  // none of it is "no error appeared".
  test.setTimeout(CASE_TIMEOUT_MS);

  await launchAs(page, INSTRUCTOR_SUBJECT, placements[BIOL.label] ?? '');
  await expect(page.getByTestId(INSTRUCTOR_LANDING)).toBeVisible();

  // She teaches three sections, so the landing is the menu rather than a
  // redirect — and the menu names them in the governed label the server
  // composes, which is the same string the report's own heading carries.
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(PICKER_HEADING);
  const menu = page.getByTestId(SECTIONS_MENU);
  await expect(menu).toBeVisible();
  await expect(menu.getByRole('link', { name: /BIOL 215/ })).toBeVisible();
  await expect(menu.getByRole('link', { name: /MATH 140/ })).toBeVisible();

  await menu.getByRole('link', { name: /BIOL 215/ }).click();

  const report = page.getByTestId(REPORT);
  await expect(
    report,
    'The section menu did not open a report. Three causes look the same from here: the link ' +
      'points at an address the router does not serve, the published-weeks read was refused, or ' +
      'the section has no closed week at this clock.',
  ).toBeVisible();

  // The heading is the section, in the words its instructor knows it by.
  await expect(page.getByRole('heading', { level: 1 })).toContainText('BIOL 215');
  // And the week, on both of SPEC §2.2's axes, with the section's own length.
  await expect(page.getByTestId(INSTRUCTOR_LANDING)).toContainText(
    `COURSE WK 0${String(BIOL_COURSE_WEEK)} / 12,`,
  );

  // SPEC §5.1's stacked pair: two panels, each with the accessible table that
  // carries its weeks and values as text.
  await expect(report.getByRole('table')).toHaveCount(2);

  // Both comment groups, each led by its own heading, and the note §4's
  // randomized order and absent timestamps are stated in.
  await expect(report.getByRole('heading', { name: 'About the instructor' })).toBeVisible();
  await expect(report.getByRole('heading', { name: 'About the course' })).toBeVisible();
  await expect(report.getByText(COMMENTS_NOTE)).toBeVisible();

  // A sentence a student in this run actually wrote, which is the assertion that
  // makes the rest of it a report rather than a layout.
  await expect(
    report.getByText(BIOL_DISTINCTIVE_COMMENT),
    'The comment the first student submitted this week is not on the report. Above the ' +
      `threshold of ${String(N_THRESHOLD)} responses SPEC §4 shows raw comments, and this week ` +
      `has ${String(BIOL_STUDENTS.length)}.`,
  ).toBeVisible();

  // The two rates, with the counts they are ratios of. Five of the section's
  // students answered; the enrolment is the roster's and is not asserted as a
  // number here, because it is the platform's to change.
  await expect(report.getByText('Response rate')).toBeVisible();
  await expect(report.getByText('Validity rate')).toBeVisible();
  await expect(report.getByText(`${String(BIOL_STUDENTS.length)} /`).first()).toBeVisible();

  // Nothing anywhere names a comparison: E5 has not run, and §4.1 item 7 governs
  // the figures rather than the words.
  const shown = (await page.getByTestId(INSTRUCTOR_LANDING).textContent()) ?? '';
  expect(shown.toLowerCase()).not.toContain('comparable');
  expect(shown.toLowerCase()).not.toContain('university');
});

test('week navigation carries the week in the address and lands focus on the heading', async ({
  page,
}) => {
  // **Criterion 6's first half, and SPEC §14.2 item 4's focus management.**
  // Paging replaces everything under the heading, so the address has to say
  // which week is open and the keyboard has to end up somewhere that names it.
  test.setTimeout(CASE_TIMEOUT_MS);

  const report = await openTheReport(page, BIOL.code);
  await expect(page).toHaveURL(new RegExp(`/app/instructor/sections/[0-9a-f-]+$`));

  await page.getByRole('button', { name: 'Previous week' }).click();

  // The chosen week is in the address, which is the whole of what makes it a
  // link somebody can send.
  await expect(page).toHaveURL(/[?&]week=\d+/);
  const week = Number(new URL(page.url()).searchParams.get('week'));
  expect(week).toBeLessThan(BIOL_COURSE_WEEK);

  // Only the week this spec answered has responses, so the week before it is the
  // zero-response state — the full report shape with every figure's absent
  // treatment, rather than an error or an empty page.
  await expect(report).toBeVisible();
  await expect(report.getByText(NO_RESPONSES).first()).toBeVisible();
  await expect(report.getByRole('table')).toHaveCount(2);

  // And focus is on the heading, which is what names the thing that changed.
  await expect(page.locator('h1')).toBeFocused();
});

test('a deep link opens the week it names, and refuses a week that is not published', async ({
  page,
}) => {
  // **Criterion 6's second half.** The API decides publishability; the page asks
  // for the week the address names and mirrors whatever came back. There is no
  // membership test in the client, which is why a week the section has not
  // reached produces the route's own sentence rather than a client-side guess.
  test.setTimeout(CASE_TIMEOUT_MS);

  const sectionId = await openTheReport(page, BIOL.code).then(() => sectionIdFromTheUrl(page));

  await page.goto(`/app/instructor/sections/${sectionId}?week=${String(BIOL_COURSE_WEEK)}`);
  const report = page.getByTestId(REPORT);
  await expect(report).toBeVisible();
  await expect(report.getByText(BIOL_DISTINCTIVE_COMMENT)).toBeVisible();

  await page.goto(`/app/instructor/sections/${sectionId}?week=${String(AN_UNPUBLISHED_WEEK)}`);
  await expect(page.getByText(COURSE_WEEK_UNAVAILABLE)).toBeVisible();
  // **No report content beside the refusal.** The published weeks came back
  // before the refusal did, so a page that kept a chart, a rate or a week
  // navigation from them would be showing part of a report it could not read.
  await expect(page.getByTestId(REPORT)).toHaveCount(0);
  await expect(page.getByRole('table')).toHaveCount(0);
  await expect(page.getByText(BIOL_DISTINCTIVE_COMMENT)).toHaveCount(0);
});

test('a small-N week hides its comments in the payload and not only on the page', async ({
  page,
}) => {
  // **Criterion 4, and the trap the ticket names.** A DOM-only assertion passes
  // with the leak sitting in the network response, so this reads the response
  // body itself — through the same route, with the same session — and requires
  // the withheld words to be absent from it.
  test.setTimeout(CASE_TIMEOUT_MS);

  const report = await openTheReport(page, MATH.code);

  // The DOM half. §4: below the threshold the instructor sees the summary and no
  // raw comments; §4.1 item 5 puts the confidentiality copy on the surface once.
  await expect(report.getByRole('region', { name: SMALL_N_TITLE })).toHaveCount(1);
  await expect(
    report.getByRole('article'),
    'A comment card is in the DOM on a week below the threshold. SPEC §4 hides raw comments ' +
      `below ${String(N_THRESHOLD)} responses, and this week has ${String(MATH_STUDENTS.length)}.`,
  ).toHaveCount(0);
  await expect(report.getByText(MATH_DISTINCTIVE_COMMENT)).toHaveCount(0);

  // The wire half. The section key comes off the menu route rather than out of
  // the address bar, so this asks the API the same question the page asked.
  const token = await sessionToken(page);
  expect(token, 'The instructor launch handed over no session, so nothing below is a read.').not
    .toBeNull();
  const sectionId = sectionIdFromTheUrl(page);
  const answer = await page.request.get(
    `/instructor/sections/${sectionId}/report/${String(MATH_COURSE_WEEK)}`,
    { headers: { Authorization: `Bearer ${token ?? ''}`, Accept: 'application/json' } },
  );
  expect(answer.status()).toBe(200);
  const raw = await answer.text();

  // The canary first (`docs/MISTAKES.md` entry 3). A body that is not this
  // section's week satisfies every absence assertion below perfectly, so the
  // things that must be *present* are asserted before the things that must not.
  const payload = JSON.parse(raw) as {
    week: { course_week: number; term_week: number };
    small_n: { suppressed: boolean; threshold: number };
    streams: Record<string, { comments: unknown[]; summary: unknown }>;
    released_from_earlier_weeks: unknown[];
  };
  expect(payload.week.course_week).toBe(MATH_COURSE_WEEK);
  expect(payload.small_n.threshold).toBe(N_THRESHOLD);

  expect(
    payload.small_n.suppressed,
    `The payload does not declare this week suppressed. It has ${String(MATH_STUDENTS.length)} ` +
      `responses against a threshold of ${String(N_THRESHOLD)}.`,
  ).toBe(true);
  expect(payload.streams.instructor?.comments).toEqual([]);
  expect(payload.streams.course?.comments).toEqual([]);
  expect(payload.released_from_earlier_weeks).toEqual([]);

  // And the words themselves, searched for as text anywhere in the body — at any
  // depth, under any member, whatever a future field is called.
  for (const withheld of [MATH_DISTINCTIVE_COMMENT, ...OTHER_COMMENTS.slice(0, 2)]) {
    expect(
      raw,
      'A comment from a week below the threshold reached the wire. SPEC §4 hides it in the ' +
        'payload rather than in the browser, and a page that hid it on screen over a response ' +
        'that carried it would leak every word to anybody who opened a network tab.',
    ).not.toContain(withheld.slice(0, 40));
  }
});

test('the week navigation offers exactly the weeks the API answers', async ({ page }) => {
  // **Criterion 3**, driven rather than argued. The published-week list is read
  // from the route that answers it, and then the report is stepped backwards
  // until the control is disabled, collecting the week the address names at each
  // stop. A control that counted by one, or that derived a range from the first
  // and last entries, visits a different sequence.
  test.setTimeout(CASE_TIMEOUT_MS);

  await openTheReport(page, BIOL.code);
  const sectionId = sectionIdFromTheUrl(page);
  const token = await sessionToken(page);

  const answered = await page.request.get(`/instructor/sections/${sectionId}/published-weeks`, {
    headers: { Authorization: `Bearer ${token ?? ''}`, Accept: 'application/json' },
  });
  expect(answered.status()).toBe(200);
  const published = ((await answered.json()) as { published_weeks: number[] }).published_weeks;
  expect(
    published.length,
    'The published-weeks route answered an empty list, which would make the walk below a walk ' +
      'over nothing and every comparison in it vacuous.',
  ).toBeGreaterThan(1);

  const visited: number[] = [weekOnScreen(page, BIOL_COURSE_WEEK)];
  const previous = page.getByRole('button', { name: 'Previous week' });
  for (let step = 0; step < MAX_WEEK_STEPS; step += 1) {
    if (await previous.isDisabled()) break;
    await previous.click();
    await expect(page).toHaveURL(/[?&]week=\d+/);
    visited.push(weekOnScreen(page, BIOL_COURSE_WEEK));
  }

  expect(
    visited,
    'Stepping back through the report did not visit exactly the weeks the API answers with. ' +
      'SPEC §5.1 pages across published weeks, and E4-08’s axis rule applied to navigation ' +
      'means the list is the API’s: a section with a gap in its published weeks — a window that ' +
      'has not closed, a week it does not run — must not offer the week between.',
  ).toEqual([...published].reverse());

  // And the far end is a stop rather than a wrap: the earliest published week
  // offers no step back.
  await expect(previous).toBeDisabled();
});

test('the trend axis carries SPEC §2.2’s term-week sub-label', async ({ page }) => {
  // **This is the one assertion expected red on this branch, and it is left
  // standing rather than softened.** SPEC §2.2 puts a quiet term-week sub-label
  // under every course-level axis, `PulseTrendChart` renders one, and the number
  // has to arrive on the wire: it cannot be derived from the course week,
  // because a section that began in the term's fourth week or paused over a
  // break breaks any offset. E4-19 is the ticket adding `term_week` to
  // `app.schemas.report.TrendPoint`, and it is not on this branch — so the stack
  // built from this branch serves a trend point without it and the sub-label has
  // nothing to say.
  //
  // Deriving it in the browser is the repair this ticket is forbidden to make
  // (E4-08's known trap, and `tests/unit/test_no_frontend_source_reads_the_clock_
  // outside_the_files_that_may.py` now walks the tree for the clock such a
  // derivation would need). So the assertion is written for the merged epic and
  // goes green when E4-19 lands.
  test.setTimeout(CASE_TIMEOUT_MS);

  const report = await openTheReport(page, BIOL.code);
  await expect(report).toContainText(`TERM 0${String(TERM_WEEK)}`);
});

/**
 * Launch the instructor, open one section's report, and answer with it.
 *
 * The menu is the page she lands on — she teaches three sections — so the report
 * is reached the way a person reaches it rather than by an address this file
 * assembled.
 */
async function openTheReport(page: Page, code: string): Promise<Locator> {
  await launchAs(page, INSTRUCTOR_SUBJECT, placements[sectionLabelOf(code)] ?? '');
  await expect(page.getByTestId(INSTRUCTOR_LANDING)).toBeVisible();
  const menu = page.getByTestId(SECTIONS_MENU);
  await expect(
    menu,
    'The instructor did not land on the section menu. This hook launched her into two sections ' +
      'and the seed gives her one of its own, so a page that redirected her to a report means the ' +
      'section list answered with exactly one — which is a section list read, not a menu bug.',
  ).toBeVisible();
  await menu.getByRole('link', { name: new RegExp(courseOf(code)) }).click();
  const report = page.getByTestId(REPORT);
  await expect(report).toBeVisible();
  return report;
}

/** Which of the three sections a §2.2 code belongs to. */
function sectionLabelOf(code: string): string {
  const known = [BIOL, MATH].find((section) => section.code === code);
  expect(known, `This spec knows no section with code ${code}.`).toBeDefined();
  return known?.label ?? '';
}

/** How the menu names one section's course, as a pattern its link is found by. */
function courseOf(code: string): string {
  if (code === BIOL.code) return 'BIOL 215';
  return 'MATH 140';
}

/** The section key out of the address the report is being read at. */
function sectionIdFromTheUrl(page: Page): string {
  const found = /\/instructor\/sections\/([0-9a-f-]+)/.exec(page.url());
  expect(found, `The report's address does not carry a section key: ${page.url()}`).not.toBeNull();
  return found?.[1] ?? '';
}

/** The course week the address names, or the latest published one when it names none. */
function weekOnScreen(page: Page, latest: number): number {
  const named = new URL(page.url()).searchParams.get('week');
  return named === null ? latest : Number(named);
}

/**
 * Wait until every named student has an enrollment this section's survey can see.
 *
 * **The block and not the landing view**, for the reason `support/survey.ts`
 * records: a student launch lands on `pulse-landing-student` whether or not the
 * person is enrolled anywhere, so a poll that waited for the landing waits for
 * nothing. The block is the observable form of "the roster sync has enrolled
 * them here".
 */
async function waitForTheRoster(
  page: Page,
  label: string,
  code: string,
  students: readonly string[],
): Promise<void> {
  const deadline = Date.now() + SYNC_TIMEOUT_MS;
  let missing = [...students];
  while (missing.length > 0 && Date.now() < deadline) {
    const stillMissing: string[] = [];
    for (const subject of missing) {
      await launchAsAStudentOfTheSection(page, subject, label);
      const landed = await page
        .getByTestId(sectionBlock(code))
        .waitFor({ state: 'visible', timeout: RENDER_WAIT_MS })
        .then(
          () => true,
          () => false,
        );
      if (!landed) stillMissing.push(subject);
    }
    missing = stillMissing;
    if (missing.length > 0) await new Promise((wake) => setTimeout(wake, SYNC_RETRY_MS));
  }
  expect(
    missing,
    `These students never got a survey block for ${code} within ${String(SYNC_TIMEOUT_MS)}ms of ` +
      'the staff launch: ' +
      `${JSON.stringify(missing)}. The roster sync is what enrols them (SPEC §7.3), so this is ` +
      'the worker not running, the mock platform not serving its roster, the staff launch not ' +
      'having stored the section’s roster address — or the pretended clock sitting outside the ' +
      'section’s own dates, which makes the enrollment not live and the block correctly absent.',
  ).toEqual([]);
}

/** Every named student answers this section's open week, the first one distinctively. */
async function answerTheWeek(
  page: Page,
  section: { label: string; code: string },
  students: readonly string[],
  distinctive: string,
): Promise<void> {
  for (const [position, subject] of students.entries()) {
    const block = await launchAsAStudentOfTheSection(page, subject, section.label).then(() =>
      page.getByTestId(sectionBlock(section.code)),
    );
    await expect(
      block,
      `${subject} landed without a block for ${section.code}, so this week cannot be answered.`,
    ).toBeVisible();
    await expect(block.getByTestId(SUBMIT)).toBeVisible();

    // Two ratings above SPEC §3.2's "required if Q ≤ 2" threshold, so both
    // comments are optional and both are written anyway: a week with no words in
    // it exercises nothing this report is about.
    await chooseRating(block, 0, '4');
    await chooseRating(block, 1, '5');
    await typeComment(block, 0, position === 0 ? distinctive : commentAt(position));
    await typeComment(block, 1, commentAt(position + 1));
    await setSlider(block, '6.5');

    await block.getByTestId(SUBMIT).click();
    await expect(
      block.getByText('Your pulse is in', { exact: true }),
      `${subject}'s submission into ${section.code} was not stored. A bounce here is SPEC §3.3's ` +
        'gate refusing one of this file’s comments, which would mean the sentence is no longer ' +
        'substantive enough for the classifier in front of it.',
    ).toBeVisible();
  }
}

/** One of the spare comments, chosen so no two students in a section write the same words. */
function commentAt(position: number): string {
  return OTHER_COMMENTS[position % OTHER_COMMENTS.length] ?? OTHER_COMMENTS[0] ?? '';
}

/**
 * Launch as one seeded student of a section, whether or not the page lists them.
 *
 * `mock-lms/app/pages.py` renders **one form per launchable user**, each carrying
 * that person's subject in a hidden `login_hint` field and posting the OIDC
 * third-party login initiation to the tool. `LAUNCH_PAGE_CAST` keeps three
 * people on the chooser so the two everybody launches as are easy to find; the
 * other students of a section are seeded, enrolled and perfectly launchable.
 *
 * So the visible form is the learner's — she is enrolled in every section, which
 * is what makes her form the one carrying every placement — and the only thing
 * rewritten is that hidden subject. Everything else the platform put on the form
 * is untouched: the issuer, the client, the deployment, the target link and the
 * placement.
 *
 * **This is not a bypass of a control, and the control is what proves it.**
 * `mock_lms.app.launch.resolve_launch` resolves the enrollment "from the seed
 * rather than from the request", which is "the whole difference between a mock
 * platform and a signing oracle" — a pair the platform does not hold is refused
 * however the request was assembled. And the substitution is checked rather than
 * assumed: these students are enrolled in exactly one section while the learner
 * is enrolled in every one of them, so every substituted launch below asserts
 * that exactly one section block is on screen. A rewrite that silently did not
 * take lands the learner, who at both of this file's clocks has two.
 */
async function launchAsAStudentOfTheSection(
  page: Page,
  subject: string,
  label: string,
): Promise<void> {
  const placement = placements[label] ?? '';
  if (subject === LEARNER_SUBJECT) {
    await launchAs(page, LEARNER_SUBJECT, placement);
    return;
  }

  await page.goto(MOCK_LMS_ORIGIN);
  await page.getByTestId(LAUNCH_USER).selectOption(LEARNER_SUBJECT);
  await page.getByTestId(LAUNCH_PLACEMENT).selectOption(placement);

  const rewritten = await page.evaluate((wanted: string) => {
    const form = document.querySelector('form[data-launch-as]:not([hidden])');
    const field = form?.querySelector('input[name="login_hint"]');
    if (!(field instanceof HTMLInputElement)) return null;
    const before = field.value;
    field.value = wanted;
    return before;
  }, subject);
  expect(
    rewritten,
    'The mock LMS launch page has no visible form carrying a hidden `login_hint`, so this spec ' +
      'cannot launch as a student the chooser does not list. `mock-lms/app/pages.py` renders one ' +
      'form per launchable user with that field; if the markup has changed, this helper is what ' +
      'needs changing rather than the assertion that meets it.',
  ).toBe(LEARNER_SUBJECT);

  await page.getByTestId(LAUNCH_SUBMIT).click();

  // The control on the substitution. These students take exactly one section and
  // the learner takes all three, so one block on screen is the observable proof
  // that somebody other than the learner landed.
  await expect(page.getByTestId('pulse-landing-student')).toBeVisible();
  await expect(
    page.locator('[data-testid^="survey-section-"]'),
    `The launch as ${subject} landed a person enrolled in more than one section, which is the ` +
      'learner. The `login_hint` rewrite did not take, so every submission below would revise ' +
      'one person’s week in place (ADR 0115) and the section would never cross SPEC §4’s ' +
      'threshold.',
  ).toHaveCount(1);
}

/**
 * Delete the summaries this file's job run wrote, so a rerun regenerates them.
 *
 * E4-06 generates once and never regenerates (E4's breakdown decision 2), so a
 * summary left behind would lead the next run's groups with prose about a week
 * whose responses this file had already deleted. The application has no path
 * that does this and should not; this is a development stack being put back to a
 * known state, which is what `support/survey.ts`'s own cleanup says of itself.
 */
function clearTheSummaries(codes: readonly string[]): void {
  const list = codes.map((code) => `'${code.replace(/'/g, "''")}'`).join(', ');
  databaseStatement(
    'delete from weekly_summary where section_id in ' +
      `(select id from section where lms_section_code in (${list}));`,
  );
}
