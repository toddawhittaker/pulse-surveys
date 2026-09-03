// SPEC §4.1 item 5 on a screen that carries more than one survey — ticket E2-17
// item 6.
//
// Item 5 reads "confidentiality copy appears exactly once per surface", and the
// ruling of 2026-09-03 settles what a surface is for the survey: **once per
// screen**, in the submit area. The sentence sits in the per-section submit bar
// today, so a student enrolled in two courses whose windows are open at the same
// minute reads it twice — which is the state this file is written against.
//
// **A screen with one open survey cannot ask the question.** `student-survey.
// spec.ts` asserts the sentence appears once, scoped to one section block, at a
// clock where the learner has exactly one open window; that assertion passes
// against both readings of "once per surface" and always will. So this file
// moves the clock to a minute where the seeded learner's *two* sections are both
// open, and counts over the whole screen.
//
// **The two sections, and the minute.** At 19:00 on Friday 11 September 2026 the
// seeded calendar is in term week 4 (Monday 7 September to Sunday 13 September),
// whose window opened at 18:00 that evening. `MATH-140-E1FF` runs six weeks from
// term week 1, so term week 4 is its fourth course week; `BIOL-215-R3WW` runs
// twelve weeks from term week 4, so the same window is its first. Both are open,
// and neither is at a boundary — the boundaries are `window-scheduling.spec.ts`'s.
//
// **Nothing here provisions anything, and that is the repair.** An earlier
// version of this file staff-launched into `NURS-8100-Q2FF` to stand up a second
// enrollment, and the premise could not be met: `scripts/seed.py` seeds no NURS
// prefix, so the launch records an `unknown_prefix` defect and creates no section
// at all (measured on this stack, 2026-09-03, from `launch_defect` and the
// `prefix` table). The seeded world already holds what this file needs — the
// learner in both sections above, both windows open at that minute, verified by
// the epic-boundary review — so the learner is simply landed and read.
//
// **That is also why `MATH-140-E1FF` is safe to use here.**
// `exit-dean-both-doors.spec.ts` records it as "the one no other spec launches
// staff into", because a *staff* launch is what stores a section's roster address
// (SPEC §7.3) and that spec's witness is that the stored address is the dean's
// own. This file drives a **student** launch, which stores no roster address and
// triggers no sync, so the witness is untouched.
//
// **The clock moves, which is shared state.** `playwright.config.ts` pins
// `workers` to 1 for that reason, and the override is cleared in `afterAll` so a
// failing assertion cannot leave the stack in September 2026 for whatever runs
// next.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect } from '@playwright/test';

import { setTheClockTo, clearTheClock } from './support/clock';
import { placementInto } from './support/doors';
import { deriveSurveyWindows } from './support/stack';
import {
  CONFIDENTIALITY,
  LEARNER_SUBJECT,
  STUDENT_VIEW,
  SUBMIT,
  type SectionUnderTest,
  clearTheWeek,
  landOnTheSurvey,
  sectionBlock,
} from './support/survey';

const MATHEMATICS: SectionUnderTest = { label: 'MATH-140-E1FF', code: 'E1FF' };
const BIOLOGY: SectionUnderTest = { label: 'BIOL-215-R3WW', code: 'R3WW' };
const BOTH = [MATHEMATICS, BIOLOGY] as const;

// Term week 4's window, an hour after it opened. Transcribed from the seeded
// calendar, not computed from the code under test (`docs/MISTAKES.md` entry 19):
// `scripts/seed.py`'s term begins Monday 17 August 2026, so term week 4 begins
// Monday 7 September, and SPEC §3.1 opens each week's survey on the Friday at
// 18:00 in the institution's timezone. Daylight time is still in force, so
// nothing here turns on the November changeover.
const BOTH_WINDOWS_OPEN = '2026-09-11T19:00';

// The placement the learner launches through. One launch shows every section
// they are enrolled in, so which of the two it names does not matter.
let placement = '';

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  test.setTimeout(120_000);
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    // A placement to land through, and the clock. **No launch by anybody but the
    // learner**: the enrollments this file reads are the seeded world's, so there
    // is no roster sync to trigger and nothing to wait for.
    placement = await placementInto(page, LEARNER_SUBJECT, BIOLOGY.label);
    await setTheClockTo(page, BOTH_WINDOWS_OPEN);

    // Materialize any window that is missing. Windows are written up front (ADR
    // 0111) by a job on the half hour, and `scripts/seed.py` calls the same
    // service for the sections it seeds — so this is ordinarily a no-op, and it
    // is here for the case where one of these sections reached the database
    // through an earlier spec's launch rather than through the seed. A spec
    // cannot wait an hour, and it must not write the rows itself: what the read
    // path answers is exactly the set of materialized windows.
    deriveSurveyWindows();
  } finally {
    await context.close();
  }
});

test.beforeEach(() => {
  // Both weeks start unanswered. An answered week renders the submitted state,
  // which has no submit bar in it — so a spec counting a sentence that lives in
  // the submit area would be counting over a screen with one submit area on it,
  // whatever the fix did.
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

test('the learner has two sections with an open survey at this clock', async ({ page }) => {
  // **The premise, and the control on everything this file's machinery does.**
  // Nothing here is about E2-17: it asserts what the seeded world does today, so
  // a red is the seed, the clock or the stack — never the ticket.
  // `landOnTheSurvey`, `sectionBlock` and `clearTheWeek` have all run by the time
  // it finishes (`doors.ts`'s rule that new machinery ships with a control that
  // must be green).
  //
  // **It is a claim about the seed and not about a sync.** The first version of
  // this file tried to *build* the second enrollment with a staff launch into a
  // third section, and it could not: that section's prefix is not in
  // `scripts/seed.py`, so the launch was recorded as an `unknown_prefix` defect
  // and provisioned nothing, and this control was red for a reason that had
  // nothing to do with either reading of item 5. Read rather than built, it is
  // deterministic — there is no roster sync in flight and nothing to poll.
  //
  // It is also the guard the count below cannot do without: "the sentence
  // appears exactly once" is true of a screen showing one survey, and that is
  // the reading this whole file exists to distinguish from the ruling's.
  await landOnTheSurvey(page, placement, BIOLOGY.code);
  for (const section of BOTH) {
    const block = page.getByTestId(sectionBlock(section.code));
    await expect(
      block,
      `The learner has no block for ${section.code} at ${BOTH_WINDOWS_OPEN}. The seeded world ` +
        'enrols them in both of this file\'s sections; a block missing here is an enrollment the ' +
        'seed no longer holds, or one that is not live on the pretended day.',
    ).toBeVisible();
    await expect(
      block.getByTestId(SUBMIT),
      `${section.code} is on screen without a submit control, so its week is not open and ` +
        'answerable. Term week 4 opens on Friday 11 September at 18:00 and closes on Sunday the ' +
        '13th at 23:59:59; a section showing the closed state here is one whose own dates do not ' +
        'cover that week, or one whose windows were never materialized (ADR 0111).',
    ).toBeVisible();
  }
});

test('the confidentiality sentence renders once on a screen carrying two open surveys', async ({
  page,
}) => {
  // Criterion 6. SPEC §4.1 item 5, under the ruling of 2026-09-03: once per
  // screen, in the submit area.
  //
  // **The mutation this kills** is the one that is shipped today: the sentence
  // rendered by `SubmitBar`, once per section, which a student in two courses
  // meets twice on one screen. It also kills the fix's near miss — a sentence
  // lifted to the page and left in the submit bar as well, which reads once per
  // screen only for a student with one course.
  //
  // **The near miss it must survive**: the wording is not this spec's business
  // and is not asserted beyond the sentence itself, which is held here as a
  // literal for `landing-views.spec.ts`'s reason — a spec that asked the page
  // what its own confidentiality copy was would pass against any wording at all.
  await landOnTheSurvey(page, placement, BIOLOGY.code);

  // **The premise, asserted here and not only in the test above.** "Exactly
  // once" is true of a screen carrying one open survey, which is what this whole
  // file exists to rule out — and each test gets its own browser context, so the
  // first test's reading says nothing about this one's page. A count taken over
  // a screen that happened to show one section would pass against the defect
  // (`docs/MISTAKES.md` entry 3).
  for (const section of BOTH) {
    await expect(
      page.getByTestId(sectionBlock(section.code)).getByTestId(SUBMIT),
      `${section.code} has no open survey on this screen, so a count of one confidentiality ` +
        'sentence would be the per-section rendering being correct for a student with one ' +
        'course rather than the ruling being kept.',
    ).toBeVisible();
  }

  // Counted over the whole document rather than inside the student view, and
  // that is deliberate: the ruling says once per *screen*, and where on the
  // screen the sentence goes — above the sections, or in the sticky submit area
  // — is the implementer's to choose from the design brief. A count scoped to
  // one testid would go red on a correct placement that happened to sit outside
  // it. The view is required to be on screen first, so the count is over the
  // page this test means.
  await expect(page.getByTestId(STUDENT_VIEW)).toBeVisible();

  const perBlock: Record<string, number> = {};
  for (const section of BOTH) {
    perBlock[section.code] = await page
      .getByTestId(sectionBlock(section.code))
      .getByText(CONFIDENTIALITY, { exact: true })
      .count();
  }

  await expect(
    page.getByText(CONFIDENTIALITY, { exact: true }),
    'The confidentiality sentence is on this screen ' +
      `${JSON.stringify(perBlock)} times inside the section blocks alone. SPEC §4.1 item 5 ` +
      'allows it exactly once per surface, and the ruling of 2026-09-03 reads a surface as a ' +
      'screen: a student enrolled in two courses whose windows are open at the same minute is ' +
      'one screen, not two. Twice is the per-section submit bar it is rendered from today; zero ' +
      'is a sentence that was lifted out of the submit bar and put nowhere, which is the same ' +
      'item unenforced from the other side.',
  ).toHaveCount(1);
});
