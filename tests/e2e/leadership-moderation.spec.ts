// The leadership review queue and exclusion log, end to end (SPEC §5.2).
//
// **What this file proves.** A Lead Faculty member signs in through the web
// door, reaches the review queue from the leadership landing, excludes one
// queued comment using the keyboard alone, watches it leave the queue, and finds
// the decision in the exclusion log: a row naming the section, the role and the
// direction, with no excerpt, because the comment's own report does not show it.
//
// **The world, built here.** `scripts/seed.py` seeds no survey data, so one
// student answers one week of `BIOL-215-R3WW` through the real form, and the
// comment held for review is routed a `harmful` verdict through the product's
// own writer (`routeSeedVerdictForComment`), as `instructor-report.spec.ts`
// does. One respondent is below SPEC §4's threshold on purpose: a lead reviews
// harmful text at any threshold (ADR 0190), and that is the case the queue
// exists for.
//
// **The reviewer.** The mock world's Lead Faculty member (`mock-idp-user-lead-
// faculty`) leads `BUSA 300` in the seed and teaches nothing. This file maps
// `BIOL 215` to her for the length of the run and removes the mapping on the way
// out, so the queue it reads is hers by SPEC §2.1's own rule and the comment is
// in a course she leads and does not teach.
//
// **Shared state.** The scheduler is stopped first (`stopTheScheduler` says
// why), the clock is moved and cleared inside a `finally`, and every row this
// file writes is deleted afterwards. Staff launches happen at the real clock,
// for the reason `instructor-report.spec.ts` measured: a roster sync that first
// sights a member while the clock is moved dates the enrollment in the future.
//
// **Accessibility.** The decision is made from the keyboard, and both pages are
// reached from the landing by the keyboard. No axe scan runs here: no spec in
// this suite runs one, and adding the scanner is a dependency change this
// ticket does not make.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect, type Page } from '@playwright/test';

import { clearTheClock, setTheClockTo } from './support/clock';
import { launchAs, placementInto, signInAs } from './support/doors';
import {
  databaseStatement,
  deriveSurveyWindows,
  routeSeedVerdictForComment,
  routeSeedVerdictsFor,
  stopTheScheduler,
} from './support/stack';
import {
  INSTRUCTOR_SUBJECT,
  INSTRUCTOR_VIEW,
  LEARNER_SUBJECT,
  SUBMIT,
  chooseRating,
  clearTheWeek,
  landOnTheSurvey,
  setSlider,
  typeComment,
  waitForTheLearnersBlocks,
} from './support/survey';

const BIOL = { label: 'BIOL-215-R3WW', code: 'R3WW' };

// Transcribed from the seeded calendar, as `instructor-report.spec.ts` does:
// `R3WW`'s fourth course week's window is open on Friday 2 October at 19:00,
// and by Monday 5 October at 09:00 it has closed.
const INSIDE_THE_BIOL_WINDOW = '2026-10-02T19:00';
const AFTER_THE_CLOSE = '2026-10-05T09:00';

// The comment held for review, and the other one the student writes. Both over
// SPEC §3.3's twenty-five-character floor, with no marker the mock model answers
// to and no `|`, the separator database reads come back on.
const HELD_COMMENT =
  'The field notebook rubric on Thursday was applied differently to every group in the room.';
const OTHER_COMMENT =
  'The pond sampling walk was well organised and the safety briefing was clear and short.';

// The reviewer, by the web subject `mock-idp/app/seed.py` publishes and the
// name `scripts/seed.py` gives her person row.
const LEAD_WEB_SUBJECT = 'mock-idp-user-lead-faculty';
const LEAD_PERSON_NAME = 'Demo Mock-World Lead Faculty';

// Testids and governed words, transcribed rather than imported
// (`docs/MISTAKES.md` entry 19).
const LEADERSHIP_VIEW = 'pulse-landing-leadership';
const QUEUE_PAGE = 'pulse-leadership-review-queue';
const LOG_LIST = 'pulse-leadership-exclusion-log-list';
const QUEUE_LINK = 'Comments awaiting your review';
const LOG_LINK = 'Exclusion log';
const REVIEW = 'Review comment';
const EXCLUDE = 'Exclude from student view';
const EXCLUDED = 'Comment excluded. The exclusion log records it.';
const NO_EXCERPT =
  'No excerpt. This comment is not shown in its section’s report, so the log does not quote it.';

const WORLD_TIMEOUT_MS = 300_000;
const CASE_TIMEOUT_MS = 120_000;

// How many Tab presses a walk may take before it is a control the keyboard
// cannot reach. Bounded, so a missing control fails rather than loops.
const MAX_TABS = 40;

/** The `BIOL 215` course, by the section this file answers. */
const THE_COURSE = `(select distinct course_id from section where lms_section_code = '${BIOL.code}')`;
const THE_LEAD = `(select id from person where identity_name = '${LEAD_PERSON_NAME}')`;

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  test.setTimeout(WORLD_TIMEOUT_MS);
  stopTheScheduler();
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    const placement = await placementInto(page, LEARNER_SUBJECT, BIOL.label);
    expect(
      await placementInto(page, INSTRUCTOR_SUBJECT, BIOL.label),
      `The mock platform should offer the instructor and the learner the same link into ${BIOL.label}.`,
    ).toBe(placement);

    // The staff launch at the real clock, then the windows, then a clean week.
    await clearTheClock(page);
    await launchAs(page, INSTRUCTOR_SUBJECT, placement);
    await expect(page.getByTestId(INSTRUCTOR_VIEW)).toBeVisible();
    deriveSurveyWindows();
    clearTheWeek([BIOL.code]);

    await setTheClockTo(page, INSIDE_THE_BIOL_WINDOW);
    await waitForTheLearnersBlocks(browser, placement, [BIOL]);
    const block = await landOnTheSurvey(page, placement, BIOL.code);
    await chooseRating(block, 0, '4');
    await chooseRating(block, 1, '5');
    await typeComment(block, 0, HELD_COMMENT);
    await typeComment(block, 1, OTHER_COMMENT);
    await setSlider(block, '6.5');
    await block.getByTestId(SUBMIT).click();
    await expect(
      block.getByText('Your pulse is in', { exact: true }),
      'The learner’s submission was not stored, so there is no comment to hold for review.',
    ).toBeVisible();

    await setTheClockTo(page, AFTER_THE_CLOSE);

    // The held comment first, then everything else in the section cleared.
    expect(
      routeSeedVerdictForComment(BIOL.code, HELD_COMMENT, 'HARMFUL'),
      'The comment this run holds for review was not routed exactly once.',
    ).toBe(1);
    expect(
      routeSeedVerdictsFor([BIOL.code]),
      'The learner’s other comment was not cleared exactly once.',
    ).toBe(1);

    // The reviewer leads the course for this run (SPEC §2.1's mapping).
    databaseStatement(
      `insert into lead_faculty_mapping (person_id, course_id) ` +
        `select ${THE_LEAD}, ${THE_COURSE} on conflict (course_id) do nothing;`,
    );
    expect(
      databaseStatement(
        `select count(*) from lead_faculty_mapping where course_id = ${THE_COURSE} ` +
          `and person_id = ${THE_LEAD};`,
      ),
      `BIOL 215 is not mapped to ${LEAD_PERSON_NAME}, so her queue cannot hold this comment. ` +
        'Either the person or the course was not found, or somebody else already leads it.',
    ).toBe('1');
  } finally {
    await context.close();
  }
});

test.afterAll(async ({ browser }) => {
  const context = await browser.newContext();
  try {
    try {
      databaseStatement(
        `delete from lead_faculty_mapping where course_id = ${THE_COURSE} ` +
          `and person_id = ${THE_LEAD};`,
      );
      clearTheWeek([BIOL.code]);
    } finally {
      await clearTheClock(await context.newPage());
    }
  } finally {
    await context.close();
  }
});

/** Press Tab until the focused element is the named control, and answer whether it got there. */
async function tabTo(page: Page, name: string): Promise<boolean> {
  for (let presses = 0; presses < MAX_TABS; presses += 1) {
    await page.keyboard.press('Tab');
    const focused = await page.evaluate(() => document.activeElement?.textContent?.trim() ?? '');
    if (focused === name) return true;
  }
  return false;
}

test('a lead excludes a queued comment from the keyboard and finds it in the log', async ({
  page,
}) => {
  test.setTimeout(CASE_TIMEOUT_MS);

  await signInAs(page, LEAD_WEB_SUBJECT);
  await expect(page.getByTestId(LEADERSHIP_VIEW)).toBeVisible();

  // The landing's link, by keyboard.
  expect(await tabTo(page, QUEUE_LINK), 'The queue link is not reachable by Tab.').toBe(true);
  await page.keyboard.press('Enter');
  const queue = page.getByTestId(QUEUE_PAGE);
  await expect(queue).toBeVisible();

  // The item is the comment's section and its flagged card; its words appear
  // once the card is opened.
  const item = queue.getByRole('listitem').filter({ hasText: 'BIOL 215 R3WW' });
  await expect(item).toHaveCount(1);
  await expect(item).not.toContainText(/\bweeks?\b/i);

  // Open the card and exclude, from the keyboard alone.
  await item.getByRole('button', { name: REVIEW }).focus();
  await page.keyboard.press('Enter');
  await expect(item.getByText(HELD_COMMENT, { exact: true })).toBeVisible();
  expect(await tabTo(page, EXCLUDE), 'The exclude control is not reachable by Tab.').toBe(true);
  await page.keyboard.press('Enter');

  await expect(queue.getByRole('status').first()).toHaveText(EXCLUDED);
  await expect(queue.getByText(HELD_COMMENT, { exact: true })).toHaveCount(0);

  // The log, from the landing, by keyboard.
  await page.goBack();
  await expect(page.getByTestId(LEADERSHIP_VIEW)).toBeVisible();
  expect(await tabTo(page, LOG_LINK), 'The log link is not reachable by Tab.').toBe(true);
  await page.keyboard.press('Enter');

  const log = page.getByTestId(LOG_LIST);
  await expect(log).toBeVisible();
  const row = log.getByRole('listitem').filter({ hasText: 'BIOL 215 R3WW' }).first();
  await expect(row).toContainText('Decided by lead faculty');
  await expect(row).toContainText('Excluded · AI-flagged');
  // One respondent: the comment's own report does not show it, so no excerpt.
  await expect(row).toContainText(NO_EXCERPT);
  await expect(row).not.toContainText(HELD_COMMENT);
  await expect(row).not.toContainText(/\d{1,2}:\d{2}/);
});
