// The survey page reads the way its owner asked — ticket FIX-01, criteria 1, 2 and 3.
// SPEC §9.2, §2.2, §3.1.
//
// Four rulings came out of the owner's interactive drive of the merged E2 stack
// on 2026-09-03, and three of them are about what a student reads:
//
//   - the week eyebrow names both of SPEC §2.2's axes in words — `COURSE WK 01,
//     TERM WK 04` — because "TERM 03" had to be explained to the product owner;
//   - the course heading says which course and which term this is —
//     `MATH 140 E1FF — College Algebra, Fall 2026` — and it is the page's visual
//     headline, so several courses on one screen are told apart at a glance;
//   - a closed section's placeholder names the instant the next survey opens,
//     rendered in the institution's timezone with the zone abbreviation derived
//     from the date. The system already holds that row; the sentence was
//     withholding it.
//
// Only a browser on the composed stack can prove any of them. The eyebrow and the
// heading are strings assembled from a read answer, governed copy and CSS; the
// placeholder's `6:00PM EDT` is produced by `Intl.DateTimeFormat` inside the page,
// against a zone the server sent — three processes and a formatter no Python
// suite can reach. What the *wire* carries is
// `tests/integration/test_the_student_read_answer_names_the_next_window.py`'s,
// and what the copy file holds is
// `tests/unit/test_the_student_surveys_ruled_copy_is_in_the_governed_inventory.py`'s.
//
// **EDT and EST are both asserted, and that pair is the point.** The ruling says
// "derive, never hardcode": a September date in `America/New_York` renders EDT
// and a November one renders EST, and the owner's own example said EST. A spec
// that only ever read an October screen would pass against a hardcoded `EDT`
// forever, and the first student to look at the page after the first Sunday in
// November would be told six o'clock and find the survey open at five.
//
// **Nothing here provisions anything.** The seeded world already enrols
// `mock-lms-user-learner` in both sections this file reads, and
// `student-survey-confidentiality.spec.ts` records why that matters: an earlier
// attempt to stand a second enrollment up with a staff launch into
// `NURS-8100-Q2FF` could not, because `scripts/seed.py` seeds no NURS prefix and
// the launch is recorded as an `unknown_prefix` defect. Only student launches are
// driven here, so no roster address is stored and
// `exit-dean-both-doors.spec.ts`'s witness over `MATH-140-E1FF` is untouched.
//
// **The clock is global state on a shared stack.** `playwright.config.ts` pins
// `workers` to 1 for that reason; every test sets the minute it needs and
// `afterAll` clears the override, so a failing assertion cannot leave the stack
// in 2026 for whatever runs next.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect, type Locator } from '@playwright/test';

import { setTheClockTo, clearTheClock } from './support/clock';
import { placementInto } from './support/doors';
import { databaseStatement, deriveSurveyWindows } from './support/stack';
import {
  CONFIDENTIALITY,
  LEARNER_SUBJECT,
  SUBMIT,
  type SectionUnderTest,
  clearTheWeek,
  landOnTheSurvey,
  sectionBlock,
} from './support/survey';

const MATHEMATICS: SectionUnderTest = { label: 'MATH-140-E1FF', code: 'E1FF' };
const BIOLOGY: SectionUnderTest = { label: 'BIOL-215-R3WW', code: 'R3WW' };
const BOTH = [MATHEMATICS, BIOLOGY] as const;

// The two headings, in the order the owner ruled: "prefix, number, then section
// code, then the em-dash title, then the term's name". **Transcribed, not
// assembled** (`docs/MISTAKES.md` entry 19), and each part has a named source:
//
//   - the prefix code and the number are the two halves of the mock platform's
//     own context label, `BIOL-215-R3WW` and `MATH-140-E1FF`
//     (`mock-lms/app/seed.py`, and README.md's "What it is seeded with" table);
//   - the section code is the third, which is SPEC §2.2's
//     `{startLetter}{ordinal}{modality}`;
//   - the titles are that same table's — Cell Biology and College Algebra;
//   - the term name is `scripts/seed.py`'s `TERM_NAME = "Fall 2026"`.
//
// `MATH 140 E1FF — College Algebra, Fall 2026` is FIX-01's acceptance criterion 1
// written out in the ticket itself, so that one is the ruling verbatim rather
// than this file's reading of it. The control below reads the stored title,
// number and term name back out of the database before either is believed.
const TERM_NAME = 'Fall 2026';
const BIOLOGY_HEADING = `BIOL 215 R3WW — Cell Biology, ${TERM_NAME}`;
const MATHEMATICS_HEADING = `MATH 140 E1FF — College Algebra, ${TERM_NAME}`;

// What the control expects the database to hold for each section, as
// `number|title|term`. Same three facts, in the shape one SQL row answers.
const STORED_COURSE = {
  [BIOLOGY.code]: `215|Cell Biology|${TERM_NAME}`,
  [MATHEMATICS.code]: `140|College Algebra|${TERM_NAME}`,
};

// Friday 11 September 2026 at 19:00, an hour after term week 4's window opened.
// **Transcribed from the seeded calendar** (`docs/MISTAKES.md` entry 19), the way
// `student-survey-confidentiality.spec.ts` transcribes the same minute:
// `scripts/seed.py`'s term begins Monday 17 August 2026, so term week 4 begins
// Monday 7 September, and SPEC §3.1 opens each week's survey on the Friday at
// 18:00 in the institution's timezone.
//
// Both sections are open at it, and their two course weeks differ, which is what
// makes the eyebrow readable: `BIOL-215-R3WW` runs twelve weeks from term week 4
// (start letter `R`, 7 September) so term week 4 is its *first* course week;
// `MATH-140-E1FF` runs six weeks from term week 1 (start letter `E`, 17 August)
// so the same week is its *fourth*. A screen serving the term week in the course
// week's place would read `COURSE WK 04` for both.
const BOTH_WINDOWS_OPEN = '2026-09-11T19:00';
const BIOLOGY_EYEBROW = { course: '01', term: '04' };
const MATHEMATICS_EYEBROW = { course: '04', term: '04' };

// Monday 5 October at nine in the morning — `student-survey.spec.ts`'s
// `AFTER_THE_WINDOW`. Term week 7's window closed at 23:59:59 on Sunday the 4th,
// and term week 8 runs Monday 5 October to Sunday the 11th with its window
// opening on Friday the 9th at 18:00. Daylight time is still in force in
// `America/New_York` on that date, so the abbreviation the page derives is EDT.
// `BIOL-215-R3WW` runs to term week 15, so week 8 is comfortably inside it.
const AFTER_A_WINDOW = '2026-10-05T09:00';
const DATED_IN_OCTOBER =
  'When the next survey for this course opens at 6:00PM EDT on Friday, October 9, it appears here.';

// The same instant expressed for SQL, for the one test that has to talk about
// "windows after now" to the database. `-04` is the offset `America/New_York`
// keeps while daylight time is in force, which is the whole reason the sentence
// above says EDT.
const AFTER_A_WINDOW_AS_SQL = '2026-10-05 09:00:00-04';

// Wednesday 4 November at midday. US daylight time ends on Sunday 1 November
// 2026, so `America/New_York` is on standard time by then and the abbreviation
// the page derives is EST. Term week 12 runs Monday 2 November to Sunday the 8th
// — 17 August plus eleven weeks — and its window opens on Friday the 6th at
// 18:00; term week 11's closed on Sunday the 1st. So `BIOL-215-R3WW` is closed
// at this minute with a window four days ahead.
//
// **This is the mutation-killer for a hardcoded EDT.** The October case above and
// this one are the same code path over two dates, and only the pair can tell a
// derived abbreviation from a written one.
const AFTER_A_WINDOW_IN_NOVEMBER = '2026-11-04T12:00';
const DATED_IN_NOVEMBER =
  'When the next survey for this course opens at 6:00PM EST on Friday, November 6, it appears here.';

// The sentence a section with no future window keeps — E2-10's, unchanged by this
// ticket and named here because the dated one has to be told from it.
const UNDATED = 'When the next survey for this course opens, it appears here.';

// `design/tokens.css`: `--text-3: 20px;  /* section headings */` and `--text-2:
// 16px;  /* body, comment text */`. Criterion 3 makes the course heading the
// page's visual headline, and the brief's own scale names the step. Transcribed
// from that file rather than read off the page, which is the difference between
// asserting the criterion and asking the page whether it agrees with itself.
const SECTION_HEADING_PX = 20;

// The placement the learner launches through. One launch shows every section they
// are enrolled in, so which of the two it names does not matter.
let placement = '';

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  test.setTimeout(120_000);
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    placement = await placementInto(page, LEARNER_SUBJECT, BIOLOGY.label);

    // Materialize any window that is missing. Windows are written up front (ADR
    // 0111) by a job on the half hour and `scripts/seed.py` calls the same
    // service, so this is ordinarily a no-op; it is here for the case where a
    // section reached this database through an earlier spec's launch rather than
    // through the seed. A spec cannot wait an hour, and it must not write the
    // rows itself — what the read path answers is exactly the set of
    // materialized windows.
    deriveSurveyWindows();
  } finally {
    await context.close();
  }
});

test.beforeEach(() => {
  // Both weeks start unanswered. An answered week renders the submitted state,
  // which has no form in it — and the closed-state placeholder this file reads is
  // only reachable on a week nobody has answered.
  clearTheWeek(BOTH.map((section) => section.code));
});

test.afterAll(async ({ browser }) => {
  const context = await browser.newContext();
  try {
    await clearTheClock(await context.newPage());
  } finally {
    await context.close();
  }
});

test('the seeded world holds the courses, the term and the two open windows this spec names', async ({
  page,
}) => {
  // **The control, and nothing here is about FIX-01.** Every heading assertion
  // below is a literal transcribed from `mock-lms/app/seed.py`, README.md and
  // `scripts/seed.py`; if the database holds a different course title or a
  // differently-named term, those assertions fail against a *correct*
  // implementation and the failure points at the ticket. This says so first.
  //
  // **A red here means this spec is broken, or the seeded world has moved — never
  // that the ticket is unbuilt.**
  for (const section of BOTH) {
    expect(
      courseAndTermOf(section.code),
      `The stored course and term for ${section.code} are not what this spec transcribed from ` +
        '`mock-lms/app/seed.py` and `scripts/seed.py`. Every heading assertion in this file is ' +
        'built out of these three values, so a difference here would redden them against a ' +
        'correct page. Two lines in this answer means more than one section carries that code, ' +
        'and the heading would then be about whichever one the page happened to show.',
    ).toBe(STORED_COURSE[section.code]);
  }

  await setTheClockTo(page, BOTH_WINDOWS_OPEN);
  await landOnTheSurvey(page, placement, BIOLOGY.code);
  for (const section of BOTH) {
    const block = page.getByTestId(sectionBlock(section.code));
    await expect(
      block,
      `The learner has no block for ${section.code} at ${BOTH_WINDOWS_OPEN}. The seeded world ` +
        "enrols them in both of this file's sections; a block missing here is an enrollment the " +
        'seed no longer holds, or one that is not live on the pretended day.',
    ).toBeVisible();
    await expect(
      block.getByTestId(SUBMIT),
      `${section.code} is on screen without a submit control, so its week is not open. Term week ` +
        '4 opens on Friday 11 September at 18:00 and closes on Sunday the 13th at 23:59:59; a ' +
        "section showing the closed state here is one whose own dates do not cover that week, or " +
        'one whose windows were never materialized (ADR 0111).',
    ).toBeVisible();
  }
});

test('each open course sits under its own heading naming prefix, number, section, title and term', async ({
  page,
}) => {
  // Acceptance criterion 1, first half: "the page shows each course under its own
  // headline-scale heading reading `<PREFIX> <number> <code> — <title>, <term
  // name>`".
  //
  // **The mutations this kills.** The heading shipped today, which is the section
  // code beside `<prefix> <number> — <title>` and never says which term — the
  // defect the ruling names. A label that keeps the code but drops the term name,
  // or appends it with something other than a comma and a space. The parts in a
  // different order, which reads perfectly well and is not what was ruled. And a
  // single label looked up once and repeated on both courses, which is why two
  // sections are read rather than one.
  //
  // **The near miss it must survive**: the two blocks in either order on screen,
  // since each heading is looked for inside its own section's block.
  //
  // **It is asserted as a heading and not as text**, because the criterion is that
  // each course *is* a heading with a course under it. A `<div>` carrying the same
  // words is a screen reader landing in the middle of a list of courses with no
  // way to move between them.
  await setTheClockTo(page, BOTH_WINDOWS_OPEN);
  await landOnTheSurvey(page, placement, BIOLOGY.code);

  for (const [section, heading] of [
    [BIOLOGY, BIOLOGY_HEADING],
    [MATHEMATICS, MATHEMATICS_HEADING],
  ] as const) {
    await expect(
      page.getByTestId(sectionBlock(section.code)).getByRole('heading', {
        name: heading,
        exact: true,
      }),
      `${section.code} is not under a heading reading ${JSON.stringify(heading)}. The order is ` +
        "the owner's ruling of 2026-09-03: prefix, number, then section code, then the em-dash " +
        "title, then the term's name. A heading missing the term name is the page that never " +
        'says which term this is; one missing the section code is the §2.2 code that used to sit ' +
        'beside it having been dropped rather than folded in.',
    ).toHaveCount(1);
  }
});

test('the week eyebrow names both of the two week axes in words', async ({ page }) => {
  // Acceptance criterion 1, second half: "the eyebrow reads `COURSE WK NN, TERM
  // WK NN`". SPEC §2.2 gives a course-level page two axes — the course week with
  // a quiet term-week sub-label — and until this ruling the page printed them as
  // `WK 03 / TERM 03`, which had to be explained to its own product owner.
  //
  // **Two sections, and their course weeks differ.** At this minute BIOL is in
  // its first course week and MATH in its fourth, both in term week 4. A page
  // serving the term week in the course week's place reads `COURSE WK 04` for
  // both and passes any single-section reading of this.
  //
  // **The mutations this kills.** The old `WK NN` and `TERM NN` left in place —
  // `TERM 04` is not a substring of `TERM WK 04`, so the second half of each pair
  // reds on it. The comma dropped, which the ruling puts inside the first string.
  // And the two labels swapped, which each section's own distinct pair catches.
  //
  // **Matched with `\s*` between the halves**, deliberately: the two numbers are
  // rendered as separate spans and whether any whitespace sits between them in
  // the DOM is a rendering decision the ruling does not make. What is asserted is
  // the ruled words, in the ruled order, with the ruled comma.
  await setTheClockTo(page, BOTH_WINDOWS_OPEN);
  await landOnTheSurvey(page, placement, BIOLOGY.code);

  for (const [section, weeks] of [
    [BIOLOGY, BIOLOGY_EYEBROW],
    [MATHEMATICS, MATHEMATICS_EYEBROW],
  ] as const) {
    await expect(
      page.getByTestId(sectionBlock(section.code)),
      `${section.code}'s eyebrow does not read "COURSE WK ${weeks.course}, TERM WK ${weeks.term}". ` +
        'SPEC §2.2 keeps the two axes apart because a 12-week section that started in term week 4 ' +
        'is not thirteen weeks into itself, and the ruling of 2026-09-03 makes the page say which ' +
        'is which in words.',
    ).toContainText(new RegExp(`COURSE WK ${weeks.course},\\s*TERM WK ${weeks.term}`));
  }
});

test('a course heading is set at the section-heading step of the type scale and above body copy', async ({
  page,
}) => {
  // Acceptance criterion 3: "each course's heading gets a clearly larger type
  // treatment so the courses are distinguishable at a glance", with
  // `design/tokens.css` governing the step.
  //
  // **Both halves, and neither alone is enough.** The absolute size says the
  // heading sits on the token the brief names for section headings (`--text-3`,
  // 20px) rather than on some near value somebody typed. The comparison against
  // body copy says the *step* survives — a token reshuffle that grew the heading
  // and the body together would satisfy the first and leave a screen where the
  // courses look alike, which is the thing the owner asked for.
  //
  // **The mutation this kills** is the shipped state: the heading rendered at
  // body size, so a student in three courses scans one undifferentiated column.
  //
  // **What this cannot assert** is "clearly larger at a glance", which is a
  // judgement for visual review. Two numbers are what a test can carry, and this
  // carries them.
  await setTheClockTo(page, BOTH_WINDOWS_OPEN);
  await landOnTheSurvey(page, placement, BIOLOGY.code);

  const heading = page
    .getByTestId(sectionBlock(BIOLOGY.code))
    .getByRole('heading', { name: BIOLOGY_HEADING, exact: true });
  await expect(
    heading,
    'The course heading is not on screen, so there is nothing here to measure. The heading itself ' +
      'is asserted by its own test above; this one is about its size.',
  ).toHaveCount(1);

  // The confidentiality sentence is this page's ordinary body copy — SPEC §4.1
  // item 5 requires it "in plain words" — and it is addressed by its text, so
  // nothing here depends on a class name or a DOM shape.
  const bodyCopy = page.getByText(CONFIDENTIALITY, { exact: true });
  await expect(
    bodyCopy,
    'The confidentiality sentence is not on this screen, and it is what the heading is measured ' +
      'against. Its own rule is `student-survey-confidentiality.spec.ts`\'s; here it is simply a ' +
      'run of governed body copy that is certainly present.',
  ).toHaveCount(1);

  const headingPx = await pixelsOf(heading);
  const bodyPx = await pixelsOf(bodyCopy);

  expect(
    headingPx,
    `The course heading renders at ${headingPx}px. \`design/tokens.css\` names \`--text-3\` ` +
      `(${SECTION_HEADING_PX}px) as the section-heading step of the scale, and criterion 3 makes ` +
      'this heading the page\'s visual headline. A value equal to the body size below is the ' +
      'shipped state; a value near but not equal to the token is a hand-typed size rather than ' +
      'the scale.',
  ).toBe(SECTION_HEADING_PX);
  expect(
    headingPx,
    `The heading renders at ${headingPx}px and this page's body copy at ${bodyPx}px. The step is ` +
      'what makes several courses on one screen tell each other apart, so it is asserted as well ' +
      'as the absolute size: a reshuffle that moved both together would satisfy the token check ' +
      'and leave the screen exactly as flat as it is today.',
  ).toBeGreaterThan(bodyPx);
});

test('a closed section names when its next survey opens, and says so in Eastern Daylight Time', async ({
  page,
}) => {
  // Acceptance criterion 2, first direction. The section is closed — term week
  // 7's window shut on Sunday evening — and term week 8's opens on Friday 9
  // October at 18:00. The ruled sentence names that instant in the institution's
  // timezone, with the abbreviation derived from the date.
  //
  // **The mutations this kills.** The undated sentence still being served, which
  // is the shipped state and the defect: the system holds the row and the page
  // will not say. The instant rendered in the reader's own zone rather than the
  // institution's, which on a CI box set to UTC reads `10:00PM UTC`. The minute
  // dropped or the space before PM restored, both of which the ruling's shape
  // settles. And the *closing* instant rendered in the opening one's place, which
  // would read `11:59PM EDT on Sunday, October 11`.
  //
  // **The near miss it must survive**: the undated sentence must not also be on
  // screen, which is what a fallback rendered beside the dated one would look
  // like — so its absence is asserted rather than assumed.
  try {
    await setTheClockTo(page, AFTER_A_WINDOW);
    const block = await landOnTheSurvey(page, placement, BIOLOGY.code);

    await expect(
      block.getByText(DATED_IN_OCTOBER, { exact: true }),
      `${BIOLOGY.code} does not say when its next survey opens. At ${AFTER_A_WINDOW} term week ` +
        "7's window has closed and term week 8's opens on Friday 9 October at 18:00 in " +
        '`America/New_York`, where daylight time is still in force — so the sentence the owner ' +
        'ruled on 2026-09-03 reads exactly this. The plain sentence in its place is the ' +
        'placeholder withholding a date the system already holds.',
    ).toHaveCount(1);
    await expect(
      block.getByText(UNDATED, { exact: true }),
      'The undated sentence is on screen beside the dated one. Only one of the two is ever ' +
        'right for a given section, and both together is a fallback rendered as well as the ' +
        'answer rather than instead of it.',
    ).toHaveCount(0);

    // `design/Usage Rules.md` §4: "Missed weeks state facts and the next window;
    // no guilt language." The ruling adds the next window; it does not add a
    // countdown or a reproach.
    expect(
      (await block.innerText()).toLowerCase(),
      'A student who missed a week is told what is true and nothing else. A countdown, a tally ' +
        'of missed weeks, or the word "missed" itself is the guilt language that rule forbids.',
    ).not.toMatch(/missed|overdue|late|you did not|remember to/);
  } finally {
    await clearTheClock(page);
  }
});

test('the same section in November says Eastern Standard Time, because the date decides', async ({
  page,
}) => {
  // Acceptance criterion 2, and the reason it says "with a derived zone
  // abbreviation". The owner's own example said EST; a September date in
  // `America/New_York` renders EDT. Both are right, for their dates, and nothing
  // in the product may write either down.
  //
  // **The mutation this kills** is the one the October case cannot see: `EDT`
  // written as a literal, or an offset resolved once and reused. US daylight time
  // ends on Sunday 1 November 2026, so at this minute the same section, the same
  // code path and the same formatter must produce EST — and a page that says EDT
  // here tells a student six o'clock for a survey that opens at five.
  //
  // **The near miss it must survive**: the correct sentence, which differs from
  // October's in one letter and in the date. Both are asserted in full, so a
  // build that fixed the abbreviation and broke the date fails too.
  try {
    await setTheClockTo(page, AFTER_A_WINDOW_IN_NOVEMBER);
    const block = await landOnTheSurvey(page, placement, BIOLOGY.code);

    await expect(
      block.getByText(DATED_IN_NOVEMBER, { exact: true }),
      `${BIOLOGY.code} does not name Friday 6 November in standard time. At ` +
        `${AFTER_A_WINDOW_IN_NOVEMBER} term week 11's window has closed and term week 12's opens ` +
        'on Friday the 6th at 18:00; daylight time ended on Sunday 1 November 2026, so the ' +
        'abbreviation `Intl.DateTimeFormat` derives for that date is EST. `EDT` here is an ' +
        'abbreviation somebody wrote down, which is what the ruling forbids in as many words: ' +
        '"derive, never hardcode".',
    ).toHaveCount(1);
    await expect(
      block.getByText(DATED_IN_OCTOBER, { exact: true }),
      'The October sentence is on a November screen, so the date is not being read off the ' +
        'window at all.',
    ).toHaveCount(0);
  } finally {
    await clearTheClock(page);
  }
});

test('a closed section with no window ahead of it keeps the plain sentence', async ({ page }) => {
  // Acceptance criterion 2, second direction: "one with no future window keeps
  // the current sentence".
  //
  // **The state is built rather than found, and it has to be.** Every section in
  // the seeded world that is still running has a window ahead of it, and one that
  // has finished has no live enrollment and so no block on screen — a section's
  // last window closes on the same Sunday its own dates end. So the case is posed
  // by removing this section's future `survey_window` rows, which is a
  // development stack being put into a state the product reaches at the end of
  // every term, and restoring them afterwards by running the same hourly job that
  // wrote them (ADR 0111). Nothing is invented: the rows come back from the real
  // derivation.
  //
  // **Both directions in one test, and the first is the control on the second.**
  // The dated sentence is required *before* the rows are removed, so a green on
  // the undated one cannot be a page that never learned to date anything
  // (`docs/MISTAKES.md` entry 3). The count of rows removed is required to be
  // non-zero for the same reason: a delete that matched nothing leaves the screen
  // exactly as it was, and the second half would then be asserting today's
  // behaviour and calling it the fallback.
  //
  // **The mutation this kills**: a dated sentence rendered whatever the answer
  // carries — a formatter fed `null` and printing `Invalid Date`, or a fallback
  // that was never written because the field is "always there in practice".
  test.setTimeout(90_000);
  const filter =
    `section_id in (select id from section where lms_section_code = ${quoted(BIOLOGY.code)}) ` +
    `and opens_at > timestamptz ${quoted(AFTER_A_WINDOW_AS_SQL)}`;
  let removed = 0;
  try {
    await setTheClockTo(page, AFTER_A_WINDOW);
    const block = await landOnTheSurvey(page, placement, BIOLOGY.code);
    await expect(
      block.getByText(DATED_IN_OCTOBER, { exact: true }),
      'The dated sentence is not on screen before this test removes the windows it names. Every ' +
        'assertion after the removal is about a fallback, and a page that never dated anything ' +
        'in the first place would satisfy all of them.',
    ).toHaveCount(1);

    removed = Number(databaseStatement(`select count(*) from survey_window where ${filter};`));
    expect(
      removed,
      `No \`survey_window\` row for ${BIOLOGY.code} opens after ${AFTER_A_WINDOW_AS_SQL}, so the ` +
        'delete below changes nothing and the reload would show the same screen for a reason ' +
        'that has nothing to do with the fallback.',
    ).toBeGreaterThan(0);
    databaseStatement(`delete from survey_window where ${filter};`);

    await page.reload();
    const afterwards = page.getByTestId(sectionBlock(BIOLOGY.code));
    await expect(
      afterwards.getByText(UNDATED, { exact: true }),
      `With ${removed} future window(s) removed, ${BIOLOGY.code} still has an open enrollment and ` +
        'nothing ahead of it. FIX-01 item 4: "a section with no future window keeps the current ' +
        'sentence". A dated sentence here is a formatter given nothing and printing something ' +
        'anyway.',
    ).toHaveCount(1);
    await expect(
      afterwards.getByText(DATED_IN_OCTOBER, { exact: true }),
      'The dated sentence survived the removal of the window it names, so the page is not ' +
        'reading the instant from the answer at all.',
    ).toHaveCount(0);
  } finally {
    // The rows come back from the job that wrote them, not from this file. The
    // derivation skips an existing `(section_id, week_id)` and writes the rest,
    // so what is restored is exactly what was removed.
    deriveSurveyWindows();
    await clearTheClock(page);
  }
});

/** The computed `font-size` of one element, in whole pixels. */
async function pixelsOf(locator: Locator): Promise<number> {
  const size = await locator.evaluate((element) => window.getComputedStyle(element).fontSize);
  return Number.parseFloat(size);
}

/**
 * The stored `lms_number|lms_title|term name` for one section code.
 *
 * Read out of the database rather than off the page, which is the difference
 * between a control and a tautology: a spec that asked the screen what its own
 * course was called would agree with any heading at all
 * (`landing-views.spec.ts`'s rule).
 */
function courseAndTermOf(code: string): string {
  return databaseStatement(
    "select c.lms_number || '|' || c.lms_title || '|' || t.name from section s " +
      'join course c on c.id = s.course_id join term t on t.id = s.term_id ' +
      `where s.lms_section_code = ${quoted(code)};`,
  );
}

/** One string as a SQL literal. */
function quoted(value: string): string {
  return `'${value.replace(/'/g, "''")}'`;
}
