// Standing a seeded learner in front of the weekly survey — the machinery
// E2-17's two new specs share. SPEC §9.2.
//
// **Why this module exists.** Both new specs need the same four things: a
// learner enrolled in named sections of the mock platform's world, a clock
// pretending a minute those sections have an open window in, a week nobody has
// answered, and the section block on screen. `student-survey.spec.ts` already
// answers all four for one section, in its own file; a second and third
// hand-copy is `docs/MISTAKES.md` entry 13 written out in full, so the shared
// question is answered once, here.
//
// **`student-survey.spec.ts` is deliberately left holding its own copies**, for
// the reason `doors.ts` records for the six specs it did not refactor: it is
// this suite's proven-green baseline for the survey screen, and the specs
// importing this module lean on that baseline being what it was. Putting a
// refactor on the control in the same pull request that uses it as a control is
// the thing that record declined to do. (E2-17 does change two assertions in
// that file — the submit button is no longer ever disabled — and it changes
// nothing else there.)
//
// **New machinery ships with a control that must be green** (`doors.ts`'s rule,
// and `docs/MISTAKES.md` entry 3). Three tests assert only what is already true
// of the product, so a red in any of them is this module or the stack and never
// the ticket:
//
//   - `student-survey-accessibility.spec.ts`'s "a submission with no CSRF cookie
//     to read still goes through on the Bearer path" is the control on
//     `standTheLearnerIn` and on nearly everything else here — the staff launch,
//     the enrollment poll, the clock, `clearTheWeek`, `landOnTheSurvey`,
//     `expectTheFormIsShowing`, `chooseRating` and `setSlider` have all run by
//     the time it submits a week;
//   - the same file's "the accessibility-tree reading tells a rendered node from
//     a display:none one" reaches the same setup by a second route;
//   - `student-survey-confidentiality.spec.ts`'s "the learner has two sections
//     with an open survey at this clock" controls `landOnTheSurvey`,
//     `sectionBlock` and `clearTheWeek` against the **seeded** world, with no
//     launch by anybody but the learner.
//
// **Only one caller needs the staff launch, and it is kept for that caller.**
// The confidentiality spec used to stand its own second enrollment up with one
// and could not: the section it chose has no prefix in `scripts/seed.py`, so the
// launch was recorded as an `unknown_prefix` defect and provisioned nothing, and
// its premise control was red for a reason that had nothing to do with the
// ticket (measured on this stack, 2026-09-03). It reads the seeded world now.
// `standTheLearnerIn` stays because the accessibility spec still needs the
// roster sync a staff launch triggers.
//
// **The clock is global state on a shared stack.** `playwright.config.ts` pins
// `workers` to 1 for that reason, and every spec using this module clears the
// override in an `afterAll`.

import { expect, type Browser, type Locator, type Page } from '@playwright/test';

import { setTheClockTo } from './clock';
import { launchAs, placementInto } from './doors';
import { databaseStatement, deriveSurveyWindows } from './stack';

// The two people. `mock-lms/app/seed.py` puts the learner in every section and
// the instructor in front of every section; the instructor is here only because
// SPEC §7.3 makes a *staff* launch the thing that stores a section's roster
// address, which is what gives the sync anything to discover.
export const LEARNER_SUBJECT = 'mock-lms-user-learner';
export const INSTRUCTOR_SUBJECT = 'mock-lms-user-instructor';

// The landing E0-18 gives a student, and the one a staff launch lands on — the
// second is asserted after each staff launch, because a launch that was refused
// provisions no section and stores no roster address, and the poll below would
// then wait out its whole window for an enrollment nothing was writing.
export const STUDENT_VIEW = 'pulse-landing-student';
export const INSTRUCTOR_VIEW = 'pulse-landing-instructor';

// Testids the survey screen publishes (E2-10). The submit action is addressed by
// one of these rather than by its words because its label changes between a
// first submission and a revision.
export const SUBMIT = 'survey-submit';
export const REVISE = 'survey-revise';
export const BOUNCE_ANNOUNCEMENT = 'survey-bounce-announcement';

// SPEC §4.1 item 5's sentence, written out here rather than imported from
// `frontend/src/copy/studentSurvey.ts`. `landing-views.spec.ts` states the rule:
// a spec that asked the page what its own governed copy was would pass against
// any wording at all.
export const CONFIDENTIALITY =
  'Responses are confidential. Your instructor never sees your name with your answers.';

// How long the learner's enrollment is waited for, and how often it is retried —
// the same instrument and the same numbers as `student-survey.spec.ts` and
// `lti-launch.spec.ts`, for the same reason: the roster sync runs in the worker
// and its latency is seconds. Every retry is a *student* launch, which triggers
// no sync of its own (SPEC §7.3), so this window is not waiting out the sync's
// debounce — the staff launch did the triggering, once.
const SYNC_TIMEOUT_MS = 30_000;
const SYNC_RETRY_MS = 3_000;
const RENDER_WAIT_MS = 2_000;

/** One section of the mock platform's world: the label it launches under, and its §2.2 code. */
export interface SectionUnderTest {
  readonly label: string;
  readonly code: string;
}

/** The testid the screen gives one section's block. */
export function sectionBlock(code: string): string {
  return `survey-section-${code}`;
}

/**
 * Enrol the learner in each named section, at a stated clock, with windows derived.
 *
 * The order is the whole of what makes this work and none of it is arbitrary:
 *
 *   1. the placements are discovered for both people **before** anything is
 *      driven, and the two are required to be the same resource link — a sync is
 *      discovered per section, so a staff launch into one section enrols nobody
 *      in another;
 *   2. the clock is moved **before** the launches, so provisioning and the
 *      roster sync both judge the enrollment against the day the spec lives in
 *      rather than against the real one. A section that has not started on the
 *      real calendar has no live enrollment on it, and a poll for its block
 *      would then wait out its whole window against a correct stack;
 *   3. the staff launches run, each asserted to have landed, because that is
 *      what stores the section's roster address (SPEC §7.3) and it is the
 *      trigger for everything after it;
 *   4. the windows are materialized, which is a job on the half hour (ADR 0111)
 *      and is invoked rather than waited for;
 *   5. and only then is the learner's own screen polled, for the block of every
 *      section asked for.
 *
 * Answers the placement the learner launches through.
 */
export async function standTheLearnerIn(
  browser: Browser,
  sections: readonly SectionUnderTest[],
  pretendNow: string,
): Promise<string> {
  const context = await browser.newContext();
  const page = await context.newPage();
  const staffPlacements: string[] = [];
  let learnerPlacement = '';
  try {
    for (const section of sections) {
      const forTheLearner = await placementInto(page, LEARNER_SUBJECT, section.label);
      const forTheStaff = await placementInto(page, INSTRUCTOR_SUBJECT, section.label);
      expect(
        forTheStaff,
        'The mock platform should offer the instructor and the learner the same resource link ' +
          `into ${section.label}. A sync is discovered per section, so a staff launch into one ` +
          'section enrols nobody in another, and this spec would then wait out its whole window ' +
          'for an enrollment nothing was writing.',
      ).toBe(forTheLearner);
      staffPlacements.push(forTheStaff);
      if (learnerPlacement === '') learnerPlacement = forTheLearner;
    }

    await setTheClockTo(page, pretendNow);

    for (const placement of staffPlacements) {
      await launchAs(page, INSTRUCTOR_SUBJECT, placement);
      await expect(page.getByTestId(INSTRUCTOR_VIEW)).toBeVisible();
    }

    // The sections reached this database through those launches, so they are
    // younger than the seed and have no `survey_window` rows yet: they are
    // materialized up front (ADR 0111) by an hourly job. Run it rather than wait
    // for it.
    deriveSurveyWindows();

    await waitForTheLearnersBlocks(browser, learnerPlacement, sections);
  } finally {
    await context.close();
  }
  return learnerPlacement;
}

/**
 * Launch as the learner until every section's block is on screen, or give up loudly.
 *
 * **The block and not the landing view.** A student launch lands on
 * `pulse-landing-student` whether or not the person is enrolled anywhere — the
 * calm empty-week state is that view — so a poll that waited for the landing is
 * satisfied the instant the launch redirects and waits for nothing at all. The
 * block is the observable form of "the roster sync has enrolled them here".
 *
 * Each attempt opens its own context, because a launch reuses whatever session
 * the last one left.
 */
async function waitForTheLearnersBlocks(
  browser: Browser,
  placement: string,
  sections: readonly SectionUnderTest[],
): Promise<void> {
  const deadline = Date.now() + SYNC_TIMEOUT_MS;
  let missing = sections.map((section) => section.code);
  while (missing.length > 0 && Date.now() < deadline) {
    const context = await browser.newContext();
    const page = await context.newPage();
    try {
      await launchAs(page, LEARNER_SUBJECT, placement);
      const stillMissing: string[] = [];
      for (const code of missing) {
        const landed = await page
          .getByTestId(sectionBlock(code))
          .waitFor({ state: 'visible', timeout: RENDER_WAIT_MS })
          .then(
            () => true,
            () => false,
          );
        if (!landed) stillMissing.push(code);
      }
      missing = stillMissing;
    } finally {
      await context.close();
    }
    if (missing.length > 0) await new Promise((wake) => setTimeout(wake, SYNC_RETRY_MS));
  }
  expect(
    missing,
    `The learner never got a survey block for ${JSON.stringify(missing)} within ` +
      `${SYNC_TIMEOUT_MS}ms of the staff launches. The roster sync is what enrols them (SPEC ` +
      '§7.3), so this is the worker not running, the mock platform not serving its roster, a ' +
      'staff launch not having stored the section’s roster address — or the pretended clock ' +
      'sitting outside the section’s own dates, which makes the enrollment not live and the ' +
      'block correctly absent.',
  ).toEqual([]);
}

/** Launch as the learner and answer with one section's block once it is on screen. */
export async function landOnTheSurvey(
  page: Page,
  placement: string,
  code: string,
): Promise<Locator> {
  await launchAs(page, LEARNER_SUBJECT, placement);
  const block = page.getByTestId(sectionBlock(code));
  await expect(
    block,
    `The learner landed without a block for ${code}. Three causes look the same from here: the ` +
      'roster sync has not enrolled them, the section has no materialized survey window for the ' +
      'pretended week, or the development clock is not where the spec put it.',
  ).toBeVisible();
  return block;
}

/**
 * Assert the open, unanswered state: the form is on screen and nothing else is.
 *
 * Every test using this module starts here, because `clearTheWeek` puts the week
 * back to unanswered before each one.
 */
export async function expectTheFormIsShowing(block: Locator): Promise<void> {
  await expect(block.getByTestId(SUBMIT)).toBeVisible();
  await expect(block.getByTestId(REVISE)).toHaveCount(0);
}

/**
 * Delete these sections' stored responses, so their weeks are unanswered again.
 *
 * Three statements and they have to be in this order: `classification.answer_id`
 * carries `ON DELETE RESTRICT` (ADR 0055, ADR 0115), which is the database
 * refusing to let a verdict lose the comment it judged, so the verdicts go
 * first, then the answers they named, then the responses holding them.
 *
 * The application has no path that does this and should not: SPEC §3.1 says a
 * week cannot be back-filled and §8 keeps the record. This is a development
 * stack being put back to a known state, which is the same thing `make seed`
 * does for the institution around it.
 */
export function clearTheWeek(codes: readonly string[]): void {
  const list = codes.map((code) => quoted(code)).join(', ');
  const ofTheseSections =
    'select r.id from response r join section s on s.id = r.section_id ' +
    `where s.lms_section_code in (${list})`;
  databaseStatement(
    `delete from classification where answer_id in (select id from answer where response_id in (${ofTheseSections}));\n` +
      `delete from answer where response_id in (${ofTheseSections});\n` +
      `delete from response where id in (${ofTheseSections});`,
  );
}

/**
 * One point on the nth Likert scale in this block, addressed by its accessible name.
 *
 * **Anchored on the digit rather than matched exactly**, and that is E2-17 item
 * 2 reaching back into the machinery: the 1 and 5 radios grow their end words
 * ("Strongly disagree", "Strongly agree") into their accessible names, so
 * `{ name: '5', exact: true }` stops matching the radio it used to. The anchored
 * pattern matches both spellings, which is what lets this helper — and the two
 * older specs, repaired the same way — stay green either side of that change.
 * `docs/MISTAKES.md` entry 22 is the shape: a later ticket's rule makes an
 * earlier ticket's tests unrunnable, and the repair is on the test side.
 */
export function ratingRadio(block: Locator, point: string): Locator {
  return block.getByRole('radio', { name: new RegExp(`^${point}\\b`) });
}

/** Choose a point on the nth Likert scale in this block. */
export async function chooseRating(block: Locator, scale: number, point: string): Promise<void> {
  await ratingRadio(block, point).nth(scale).check();
}

/** Type into the nth comment field in this block, or empty it. */
export async function typeComment(block: Locator, field: number, words: string): Promise<void> {
  await block.getByRole('textbox').nth(field).fill(words);
}

/** Put the workload slider on one value, from the keyboard. */
export async function setSlider(block: Locator, hours: string): Promise<void> {
  const slider = block.getByRole('slider');
  await slider.focus();
  await slider.fill(hours);
  await expect(slider).toHaveValue(hours);
}

/**
 * The wording SPEC §3.2's first question is stored under, in the set in force.
 *
 * Read so that a spec holding that sentence as a literal can say so before it
 * uses it: the questions are versioned rows (§3.2) and a stack seeded from
 * something other than `scripts/seed.py` would make an assertion about the
 * sentence a message names into an assertion about a sentence nothing says.
 * `student-survey.spec.ts` keeps its own copy of this query, deliberately — see
 * this module's header on why the baseline is left alone.
 */
export function firstQuestionPrompt(): string {
  return databaseStatement(
    'select prompt from question where position = 1 and question_set_id = ' +
      '(select id from question_set order by version desc limit 1);',
  );
}

/** One string as a SQL literal. */
function quoted(value: string): string {
  return `'${value.replace(/'/g, "''")}'`;
}
