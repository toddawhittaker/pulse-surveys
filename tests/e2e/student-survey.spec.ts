// E2-10 — the StudentWeeklySurvey screen, driven end to end against the running
// stack. SPEC §9.2, SPEC §14.2 item 1.
//
// What only a browser on the composed stack can prove, and what this file is
// therefore for:
//
//   - a seeded student launches from the mock LMS, lands on the survey, and can
//     complete all five of SPEC §3.2's questions — the workload slider from the
//     keyboard alone (§14.2 item 4) — and submit;
//   - SPEC §3.3's synchronous gate reaches the person at the keyboard as
//     coaching: a thin comment bounces, the coaching sentence appears attached to
//     the comment that was sent, every other answer survives untouched, and the
//     fixed submission goes through;
//   - the question wording on screen is the API's versioned text and not this
//     build's, proved by altering the stored set and watching the screen follow.
//
// Each of those crosses a process boundary the Python suites cannot: the form,
// the API, the classifier behind `mock-ai`, and the database that stores the
// instrument are four different containers, and the assertions below are about
// the four of them meeting.
//
// **What this file deliberately does not prove.** Nothing about who may read or
// submit — that is `app.services.survey_read` and `app.services.submissions`,
// and the integration suites own it. Nothing about the window rhythm itself —
// that is `window-scheduling.spec.ts` and the calendar fixtures. This file
// assumes those and asserts what a student sees.
//
// **The clock moves, which is shared state.** The stack has one
// `clock_override` row and `playwright.config.ts` pins `workers` to 1 for that
// reason. The override is set once for the whole block and cleared in
// `afterAll`, so a failing assertion cannot leave the stack in October 2026 for
// whatever runs next.
//
// **The tests run in order and share one enrollment.** Standing the learner in a
// synced section costs a staff launch and a wait on the roster worker, so it is
// done once in `beforeAll`; each test then opens its own browser context and
// launches for itself. Each also starts from a week nobody has answered, which
// `beforeEach` sees to — so this file behaves the same on a fresh database as on
// one it has already run against, and no test depends on the one before it.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect, type Browser, type Locator, type Page } from '@playwright/test';

import { clearTheClock, setTheClockTo } from './support/clock';
import { launchAs, placementInto } from './support/doors';
import { databaseStatement, deriveSurveyWindows } from './support/stack';

// The two people. `mock-lms/app/seed.py` puts the learner in every section and
// the instructor in front of every section; the instructor is here only because
// SPEC §7.3 makes a *staff* launch the thing that stores a section's roster
// address, which is what gives the sync anything to discover.
const LEARNER_SUBJECT = 'mock-lms-user-learner';
const INSTRUCTOR_SUBJECT = 'mock-lms-user-instructor';

// The section, named rather than taken first-offered. `BIOL-215-R3WW` is how the
// mock platform labels its context, and `R3WW` is the section code
// `app.services.provisioning` parses out of that label and what the screen
// prints. Naming it is what makes the week arithmetic below mean something: a
// first-offered placement would be a different course of a different length on a
// different calendar, and every date here would be arbitrary.
const SECTION_LABEL = 'BIOL-215-R3WW';
const SECTION_CODE = 'R3WW';
const SECTION_BLOCK = `survey-section-${SECTION_CODE}`;

// The screen's own landmark — E0-18's testid, which the survey inherited from the
// landing view it replaced. Addressed for the states that render no section block
// at all.
const STUDENT_VIEW = 'pulse-landing-student';

// The minute this spec pretends it is, and the two week numbers that follow from
// it. **Transcribed from the seeded calendar, not computed from the code under
// test** (`docs/MISTAKES.md` entry 19).
//
// `scripts/seed.py`'s `START_LETTER_MAP` gives start letter `R` twelve weeks
// from Monday 7 September 2026, and the Fall 2026 term begins on Monday 17
// August. SPEC §3.1 opens each week's survey on the Friday at 18:00 in the
// institution's timezone. So:
//
//   - the section's fourth week runs Monday 28 September to Sunday 4 October,
//     and its window opens on Friday 2 October at 18:00;
//   - that is the term's seventh week — 17 August is term week 1, so 28
//     September is term week 7 — and the section began in term week 4, which
//     makes 7 − 4 + 1 = 4 its own fourth course week (SPEC §2.2).
//
// Seven in the evening is inside that window and nowhere near either edge, so
// this spec is about the form rather than about a boundary; the boundaries are
// `window-scheduling.spec.ts`'s. Daylight time is still in force on 2 October,
// so nothing here turns on the November changeover that spec is written around.
const INSIDE_THE_WINDOW = '2026-10-02T19:00';
const COURSE_WEEK = '04';
const TERM_WEEK = '07';

// Monday morning, after that window closed at 23:59:59 on Sunday 4 October and
// four days before the next one opens on Friday the 9th. SPEC §3.1: "missed
// weeks cannot be back-filled", so at this instant the section has nothing to
// answer and nothing to offer.
const AFTER_THE_WINDOW = '2026-10-05T09:00';

// How long the learner's enrollment is waited for, and how often it is retried.
// The same instrument and the same numbers as `lti-launch.spec.ts`, for the same
// reason: the roster sync runs in the worker, its latency is seconds, and this
// is far above it with room for a loaded CI box. Every retry is a *student*
// launch, which triggers no sync of its own (SPEC §7.3), so this window is not
// waiting out the sync's five-minute debounce — the single staff launch above
// did the triggering, once.
const SYNC_TIMEOUT_MS = 30_000;
const SYNC_RETRY_MS = 3_000;
const RENDER_WAIT_MS = 2_000;

// Testids the screen publishes (E2-10). The submit action is addressed by one of
// these rather than by its words because its label changes between a first
// submission and a revision, and a spec holding two governed strings in order to
// click one button is two strings that can go stale.
const SUBMIT = 'survey-submit';
const REVISE = 'survey-revise';
const BOUNCE_ANNOUNCEMENT = 'survey-bounce-announcement';

// The governed copy this spec reads, written out here rather than imported from
// `frontend/src/copy/studentSurvey.ts`. `landing-views.spec.ts` states the rule:
// a spec that asked the page what its own heading was would pass against any
// heading at all. These are SPEC §4.1 item 5's confidentiality line, §3.3's
// optional-comment credit note, and the two states a week can be in.
const CONFIDENTIALITY =
  'Responses are confidential. Your instructor never sees your name with your answers.';
const OPTIONAL_CREDIT_NOTE =
  'Optional, but written feedback counts toward full participation credit — a sentence or two is enough.';
const REQUIRED_HELP =
  'A low rating needs a why — a specific sentence is what earns participation credit and gives your instructor something to act on.';
const REQUIRED_FLAG = 'Needed to submit';
const SUBMITTED_TITLE = 'Your pulse is in';
const SECTION_CLOSED_TITLE = 'Nothing to answer here right now';
const SECTION_CLOSED_BODY = 'When the next survey for this course opens, it appears here.';

// What a read the server refused says, and the sentence it must never say
// instead. E2-10's security review: a 401 that renders the calm empty-week state
// tells a student whose session has run out that nothing is due, on a week they
// still have time to answer.
const SESSION_ENDED_TITLE = 'Open this from your course';
const SESSION_ENDED_BODY =
  'This page is not signed in, so it cannot say what is due. Open Pulse Surveys from inside your course in the LMS, and this week’s questions will be here.';
const CALM_EMPTY_WEEK = 'There is no survey open for you yet. When one opens, it appears here.';

// Where the SPA keeps the session it lifted out of the launch fragment (E1-08,
// `frontend/src/lib/session.ts`). Spelled the same way `support/doors.ts` spells
// it; this spec writes to it to age a session out.
const SESSION_STORAGE_KEY = 'pulse.session';

// SPEC §3.2's first question, as `scripts/seed.py` transcribes it from the spec.
// The altered wording below is this spec's own invention and is written to be
// unmistakable: nothing else in the product says it, so finding it on screen can
// only mean the screen read it from the database.
const SEEDED_FIRST_PROMPT = 'This week, my instructor supported my learning.';
const ALTERED_FIRST_PROMPT = 'A different question entirely, seeded by the E2-10 end-to-end spec.';

// SPEC §3.3's own example of a comment that must be bounced, and E2-10's first
// acceptance criterion's: "type 'it was okay' with a low rating and see the
// bounce with its coaching copy". Eleven characters, so the mock provider's
// published character rule calls it `insufficient` (ADR 0113,
// `mock-ai/app/rules.py`) — the ordinary path rather than a forced verdict.
const THIN_COMMENT = 'it was okay';

// The placement `beforeAll` discovers and every test launches through.
let placement = '';

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  test.setTimeout(SYNC_TIMEOUT_MS + 120_000);
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    placement = await placementInto(page, LEARNER_SUBJECT, SECTION_LABEL);
    const staffPlacement = await placementInto(page, INSTRUCTOR_SUBJECT, SECTION_LABEL);
    expect(
      staffPlacement,
      'The mock platform should offer the instructor and the learner the same resource link into ' +
        `${SECTION_LABEL}. A sync is discovered per section, so a staff launch into one section ` +
        'enrolls nobody in another, and this spec would then wait out its whole window for an ' +
        'enrollment nothing was writing.',
    ).toBe(placement);

    // The trigger. SPEC §7.3: a launch by an instructor stores the section's
    // roster service address, which is the whole of what gives the scheduled
    // sync its discovery. Landing her is the control on it — a staff launch
    // that was refused provisioned no section and stored no address, and the
    // poll below would then be waiting for a sync nobody asked for.
    await launchAs(page, INSTRUCTOR_SUBJECT, placement);
    await expect(page.getByTestId('pulse-landing-instructor')).toBeVisible();

    await waitForTheLearnersEnrollment(browser);

    // The section reached this database through that launch, so it is younger
    // than the seed and has no `survey_window` rows yet: they are materialized
    // up front (ADR 0111) by an hourly job. Run it rather than wait for it.
    deriveSurveyWindows();

    await setTheClockTo(page, INSIDE_THE_WINDOW);
  } finally {
    await context.close();
  }
});

test.beforeEach(() => {
  // Each test starts from a week nobody has answered.
  //
  // **Not tidiness — the alternative does not work.** ADR 0109 makes the
  // development clock an *offset* rather than a freeze, so setting it to the
  // same pretended minute in a later run produces an effective now a few seconds
  // *earlier* than the last run reached. A revision written against that clock
  // carries a `last_submitted_at` before the stored `first_submitted_at`, and
  // `response`'s own check constraint refuses it — a 500 on a resubmission,
  // measured while writing this file and recorded in
  // `docs/tickets/e2/deferred.md`. Clearing the week keeps that out of every
  // assertion here, and it also makes each test independent of the ones before
  // it: a file whose second test only passed after its first had run is a file
  // nobody can debug one test at a time.
  clearTheWeek();
});

test.afterAll(async ({ browser }) => {
  // Whatever happened above, the stack goes back to real time. A failing
  // assertion that left the clock in October 2026 would fail the specs running
  // after this file, and those failures would point at everything except this
  // one.
  const context = await browser.newContext();
  try {
    await clearTheClock(await context.newPage());
  } finally {
    await context.close();
  }
});

test('a student answers all five questions, the slider by keyboard, and the week is recorded', async ({
  page,
}) => {
  const block = await landOnTheSurvey(page);

  // The week, under both of SPEC §2.2's names, before anything is answered. This
  // is also the assertion that says the clock moved and the window is the one
  // this spec means: with the override cleared, today is not week 4 of a section
  // that had not started.
  await expect(block).toContainText(`WK ${COURSE_WEEK}`);
  await expect(block).toContainText(`TERM ${TERM_WEEK}`);

  await expectTheFormIsShowing(block);

  // SPEC §4.1 item 5: the confidentiality line, in plain words, in the submit
  // bar, exactly once on this surface. Asserted with the form on screen, because
  // the submit bar is where §4.1 puts it and a week already answered has no
  // submit bar to put it in.
  await expect(block.getByText(CONFIDENTIALITY, { exact: true })).toHaveCount(1);

  // Nothing has been answered, and the submit control is still there and still
  // operable.
  //
  // **This assertion read `toBeDisabled()` until E2-17.** The button carried
  // `disabled` until every non-comment question was answered, which took it out
  // of the tab order entirely: a student using a screen reader tabbed to the end
  // of the form, found nothing to activate, and was told nothing about why.
  // E2-17 item 1 settles that it stays enabled and focusable always and refuses
  // to *send* rather than refusing to exist. The half this line used to carry —
  // that an incomplete week is not submitted — moved with the construction and is
  // `student-survey-accessibility.spec.ts`'s, where the refused activation is
  // driven and the request recorder shows nothing was sent.
  await expect(block.getByTestId(SUBMIT)).toBeEnabled();

  // A rating of 2 on the first question makes the comment beside it required
  // (SPEC §3.2, "Required if Q1 ≤ 2"); a 4 on the second leaves its comment
  // optional.
  await chooseRating(block, 0, '2');
  await chooseRating(block, 1, '4');

  // Exactly one of the two comments is required, and it is the one whose rating
  // is low. Both directions in one reading: a form that marked every comment
  // required, or none, would fail this and pass a check that only looked at the
  // low-rated one.
  await expect(block.getByRole('textbox').nth(0)).toHaveAttribute('aria-required', 'true');
  await expect(block.getByRole('textbox').nth(1)).toHaveAttribute('aria-required', 'false');

  // And the required state is announced rather than only coloured — SPEC §14.2
  // item 4: `aria-required` above for a screen reader, and these words beside
  // the label for everyone. §3.3's own optional-state sentence is under the
  // other one, saying that written feedback still counts toward participation
  // credit.
  await expect(block.getByText(REQUIRED_FLAG, { exact: true })).toHaveCount(1);
  await expect(await commentHelp(block, 1)).toHaveText(OPTIONAL_CREDIT_NOTE);

  // §3.2's fifth question, from the keyboard alone: focus the slider and press.
  // Nothing is clicked and nothing is dragged, which is the whole point of the
  // case — §14.2 item 4 puts keyboard operation in-slice. `Home` is a keyboard
  // action too, and it is what makes the arithmetic below independent of
  // whatever this week already held.
  const slider = block.getByRole('slider');
  await slider.focus();
  await page.keyboard.press('Home');
  await expect(slider).toHaveValue('0');
  for (let press = 0; press < 13; press += 1) {
    await page.keyboard.press('ArrowRight');
  }
  expect(
    await slider.inputValue(),
    'Thirteen presses from the bottom of a 0-to-40 range that moves in half hours is 6.5. A ' +
      'different number here means the slider took its step from somewhere other than the ' +
      "question row's, which is the one statement of it in the system (ADR 0110).",
  ).toBe('6.5');
  // The live numeric readout §3.2 asks for, and the same value spoken.
  await expect(block.getByText('6.5 h', { exact: true })).toBeVisible();
  await expect(slider).toHaveAttribute('aria-valuetext', '6.5 h');

  // Four of the five are answered now and the fifth is the required comment.
  //
  // **This pair read `toBeDisabled()` then `toBeEnabled()` until E2-17**, and it
  // was the file's reading of the conditional-required rule: the button was the
  // thing that told a student the low-rated comment was still owed. Under E2-17
  // item 1 the button never disables, so the pair says nothing about the rule
  // and the rule is asserted where it is now stated — `aria-required` and the
  // "Needed to submit" flag above, both already in this test, and the refused
  // activation in `student-survey-accessibility.spec.ts`. What is kept here is
  // that the control does not change state around the answer at all.
  await expect(block.getByTestId(SUBMIT)).toBeEnabled();
  await typeComment(block, 0, 'The Thursday lab walkthrough made the staining protocol click.');
  await expect(block.getByTestId(SUBMIT)).toBeEnabled();

  // The optional one is answered too, because a week with no words in it
  // exercises none of the classifier.
  await typeComment(block, 1, 'The reading list for week four was long but the ordering helped.');

  await block.getByTestId(SUBMIT).click();

  await expect(block.getByText(SUBMITTED_TITLE, { exact: true })).toBeVisible();
  await expect(block.getByTestId(SUBMIT)).toHaveCount(0);

  // The week survives a reload, which is the half that says the server stored it
  // rather than the screen having congratulated itself.
  await page.reload();
  const reloaded = page.getByTestId(SECTION_BLOCK);
  await expect(reloaded.getByText(SUBMITTED_TITLE, { exact: true })).toBeVisible();

  // And the stored answers come back into the form — `OwnSubmission`, prefilled,
  // all three value columns. A prefill missing one would blank a field the
  // student had filled in, and the next submission would overwrite it with
  // nothing.
  await reloaded.getByTestId(REVISE).click();
  await expect(reloaded.getByRole('slider')).toHaveValue('6.5');
  await expect(reloaded.getByRole('textbox').nth(0)).toHaveValue(
    'The Thursday lab walkthrough made the staining protocol click.',
  );
  await expect(reloaded.getByRole('textbox').nth(1)).toHaveValue(
    'The reading list for week four was long but the ordering helped.',
  );
  await expect(reloaded.getByRole('radio', { name: '2', exact: true }).first()).toBeChecked();
  await expect(reloaded.getByRole('radio', { name: '4', exact: true }).nth(1)).toBeChecked();
});

test('a thin comment is coached where it was typed, the rest of the form survives, and the fix goes through', async ({
  page,
}) => {
  const block = await landOnTheSurvey(page);
  await expectTheFormIsShowing(block);

  // A low rating on the first question and a thin comment beside it, which is
  // the case SPEC §3.3 and this ticket's first acceptance criterion both write
  // out. A high rating on the second leaves its comment optional and empty, and
  // that is what makes the coaching's placement readable: exactly one comment is
  // submitted, so exactly one field may carry the sentence.
  await chooseRating(block, 0, '2');
  await chooseRating(block, 1, '5');
  await typeComment(block, 0, THIN_COMMENT);
  await typeComment(block, 1, '');
  await setSlider(block, '9');

  await block.getByTestId(SUBMIT).click();

  // The coaching is the server's sentence — `app.copy.submit`'s
  // `submit.bounce.insufficient` — and this spec does not hold a copy of it. It
  // asserts what §3.3 requires of it instead: that it arrived, that it is
  // announced once in a live region, and that it says what a useful answer looks
  // like by giving one concrete example in quotation marks.
  const announcement = block.getByTestId(BOUNCE_ANNOUNCEMENT);
  await expect(announcement).not.toBeEmpty();
  const coaching = ((await announcement.textContent()) ?? '').trim();
  expect(
    coaching,
    'SPEC §3.3 requires the bounce to carry "coaching copy and one concrete example". The ' +
      'example is quoted in `app.copy.submit`, which is where the sentence lives; a bounce ' +
      'reaching the screen without it is the shame state that section forbids arriving by ' +
      'omission. Either quotation mark counts — which one the registry writes is a typography ' +
      'decision this spec has no business pinning.',
  ).toMatch(/["“][^"”]+["”]/);
  expect(
    coaching.toLowerCase(),
    'The bounce is coaching, never a shame state (SPEC §3.3). No sentence a student meets here ' +
      'may say they failed, or were rejected, or did anything wrong.',
  ).not.toMatch(/reject|fail|invalid|wrong|error/);

  // Attached to the comment that was submitted, and to no other field. The
  // second comment was empty, so it still carries the optional-state helper.
  await expect(block.getByText(coaching)).toHaveCount(2); // the live region, and the field
  await expect(await commentHelp(block, 0)).toHaveText(coaching);
  await expect(await commentHelp(block, 1)).toHaveText(OPTIONAL_CREDIT_NOTE);
  await expect(block.getByRole('textbox').nth(0)).toHaveAttribute('aria-invalid', 'true');

  // Focus moved to the coached field, so a keyboard is already where the fix has
  // to be made.
  expect(
    await block.getByRole('textbox').nth(0).evaluate((field) => field === document.activeElement),
    'A bounce that is announced and not focused leaves a keyboard user to hunt for the field it ' +
      'is about (SPEC §14.2 item 4).',
  ).toBe(true);

  // Everything else is exactly as it was typed. A bounce stores nothing (§3.3
  // refuses "before submission"), so losing the week's other answers here would
  // mean a student retyping all five questions because one sentence was thin.
  await expect(block.getByRole('textbox').nth(0)).toHaveValue(THIN_COMMENT);
  await expect(block.getByRole('radio', { name: '2', exact: true }).first()).toBeChecked();
  // Anchored rather than exact, for `chooseRating`'s reason: E2-17 item 2 puts
  // "Strongly agree" into the accessible name of every scale's 5.
  await expect(block.getByRole('radio', { name: /^5\b/ }).nth(1)).toBeChecked();
  await expect(block.getByRole('slider')).toHaveValue('9');

  // The fix, and the week goes in. The field goes back to the state its rating
  // puts it in — still required, because the rating is still a 2 — rather than
  // staying coached.
  await typeComment(block, 0, 'The pacing in week three was too fast to finish the second assay.');
  await expect(await commentHelp(block, 0)).toHaveText(REQUIRED_HELP);
  await expect(announcement).toBeEmpty();

  await block.getByTestId(SUBMIT).click();
  await expect(block.getByText(SUBMITTED_TITLE, { exact: true })).toBeVisible();
});

test('the question on screen is the versioned set the API serves, not a sentence in this build', async ({
  page,
}) => {
  // Acceptance criterion 2. SPEC §3.2 stores the five questions in a versioned
  // table "even though v1 ships one fixed set", and the form is required to
  // render that text rather than a copy of it. The proof is both directions: the
  // seeded wording is on screen before the change and gone after it, and the
  // altered wording is absent before and present after. Either half alone passes
  // against a form with the sentence compiled in.
  const before = await landOnTheSurvey(page);
  await expectTheFormIsShowing(before);
  await expect(before.getByText(SEEDED_FIRST_PROMPT, { exact: true })).toBeVisible();
  await expect(before.getByText(ALTERED_FIRST_PROMPT, { exact: true })).toHaveCount(0);

  const original = firstQuestionPrompt();
  expect(
    original,
    'The stored wording of SPEC §3.2\'s first question should be the seeded one before this test ' +
      'changes it. A database that already held something else means an earlier run of this ' +
      'spec did not restore what it borrowed, and the restore below would then write the wrong ' +
      'sentence back.',
  ).toBe(SEEDED_FIRST_PROMPT);

  try {
    setFirstQuestionPrompt(ALTERED_FIRST_PROMPT);

    await page.reload();
    const after = page.getByTestId(SECTION_BLOCK);
    await expectTheFormIsShowing(after);
    await expect(after.getByText(ALTERED_FIRST_PROMPT, { exact: true })).toBeVisible();
    await expect(after.getByText(SEEDED_FIRST_PROMPT, { exact: true })).toHaveCount(0);
  } finally {
    setFirstQuestionPrompt(original);
  }

  // And back, so this file leaves the instrument as it found it and the next
  // spec to read a question reads SPEC §3.2's own words.
  await page.reload();
  const restored = page.getByTestId(SECTION_BLOCK);
  await expectTheFormIsShowing(restored);
  await expect(restored.getByText(SEEDED_FIRST_PROMPT, { exact: true })).toBeVisible();
});

test('a section with no window open says so, and offers nothing to answer', async ({ page }) => {
  // The ticket's "no open window" state. The section is still reported — the
  // enrollment does not come and go with the window, and a student is owed
  // "there is nothing to answer this minute" rather than an answer that leaves
  // out the course they are in.
  try {
    await setTheClockTo(page, AFTER_THE_WINDOW);
    const block = await landOnTheSurvey(page);

    await expect(block.getByText(SECTION_CLOSED_TITLE, { exact: true })).toBeVisible();
    await expect(block.getByText(SECTION_CLOSED_BODY, { exact: true })).toBeVisible();

    // Nothing to answer means nothing to answer with: no form, no submit, and no
    // way back into a week that cannot be answered.
    await expect(block.getByTestId(SUBMIT)).toHaveCount(0);
    await expect(block.getByTestId(REVISE)).toHaveCount(0);
    await expect(block.getByRole('slider')).toHaveCount(0);

    // `design/Usage Rules.md` §4: "Missed weeks state facts and the next window;
    // no guilt language." Nothing here counts what was missed or asks why.
    expect(
      (await block.innerText()).toLowerCase(),
      'A student who missed a week is told what is true and nothing else. A countdown, a tally ' +
        'of missed weeks, or the word "missed" itself is the guilt language that rule forbids.',
    ).not.toMatch(/missed|overdue|late|you did not|remember to/);
  } finally {
    await setTheClockTo(page, INSIDE_THE_WINDOW);
  }
});

test('a window that closes under an open form takes the form away and says why', async ({
  page,
}) => {
  // The ticket's "window closed" state, reached the only way a student reaches
  // it: with the form already open. SPEC §3.1 gives the week a hard close, so a
  // submission a minute late is refused — and going on offering a submit button
  // after that would be a trap.
  try {
    const block = await landOnTheSurvey(page);
    await expectTheFormIsShowing(block);
    await chooseRating(block, 0, '4');
    await chooseRating(block, 1, '4');
    await setSlider(block, '3');
    await expect(block.getByTestId(SUBMIT)).toBeEnabled();

    // The window shuts while the page sits there. A second page moves the clock
    // so the form's own tab is not navigated away from.
    const console_ = await page.context().newPage();
    try {
      await setTheClockTo(console_, AFTER_THE_WINDOW);
    } finally {
      await console_.close();
    }

    await block.getByTestId(SUBMIT).click();

    await expect(block.getByTestId(SUBMIT)).toHaveCount(0);
    await expect(block.getByText(SUBMITTED_TITLE, { exact: true })).toHaveCount(0);

    // The sentence is `app.copy.submit`'s `submit.window_closed` and this spec
    // holds no copy of it; what it pins is the meaning — the student is told the
    // week has closed — and that the telling is not a shame state.
    const said = (await block.innerText()).trim();
    expect(
      said,
      'A refused submission that says nothing is a form that appears to have swallowed the week. ' +
        'The server sends a sentence for this (SPEC §3.1, `submit.window_closed`) and the screen ' +
        'is what puts it where the student is standing.',
    ).toMatch(/closed/i);
    expect(
      said.toLowerCase(),
      'SPEC §3.1 says a missed week cannot be back-filled; it does not say anybody failed. ' +
        'Nothing in this product shames.',
    ).not.toMatch(/reject|fail|invalid|wrong|error/);
  } finally {
    await setTheClockTo(page, INSIDE_THE_WINDOW);
  }
});

test('a session the server will not accept says which page can answer, never that nothing is due', async ({
  page,
}) => {
  // E2-10's security review, as a case. The session a launch issues lives an
  // hour (`SESSION_LIFETIME_SECONDS`) and a survey window stands open from
  // Friday evening to Sunday night, so the ordinary way to meet a 401 here is a
  // student coming back to yesterday's tab inside a window that is still open.
  //
  // **The state this must not render is the calm one.** "There is no survey open
  // for you yet" is a claim about the week, and a page whose read was refused
  // has not been told anything about the week. Asserting its absence is the
  // whole point of the case: a screen that collapsed the refusal back into the
  // empty-week state would satisfy every other assertion here.

  // A real launch first, so the tab is one a student actually reached and the
  // window really is open. The survey on screen is the control: it says this
  // student, this section and this clock would otherwise show a form, so what
  // changes below is the session and nothing else.
  const block = await landOnTheSurvey(page);
  await expectTheFormIsShowing(block);

  // Now age the session out. A token the server will not verify is what an
  // expired one looks like from here — `require_student` answers 401 to both,
  // deliberately and identically, so that a caller cannot tell a stale session
  // from a forged one.
  await page.evaluate(
    ([key, token]) => {
      window.sessionStorage.setItem(key, token);
    },
    [SESSION_STORAGE_KEY, 'not.a.session'],
  );
  await page.reload();

  const refused = page.getByTestId(STUDENT_VIEW);
  await expect(refused).toBeVisible();
  await expect(refused.getByText(SESSION_ENDED_TITLE, { exact: true })).toBeVisible();
  await expect(refused.getByText(SESSION_ENDED_BODY, { exact: true })).toBeVisible();

  // The claim that must not be made, and the form that must not be offered.
  await expect(
    refused.getByText(CALM_EMPTY_WEEK, { exact: true }),
    'A read the server refused rendered the calm empty-week state. That sentence says the week ' +
      'holds nothing, which is a fact this page was not given: the request was refused before ' +
      'any window was read. A student whose hour-long session ran out inside a window that is ' +
      'open for days would be told, authoritatively, that there is nothing to answer.',
  ).toHaveCount(0);
  await expect(refused.getByTestId(SUBMIT)).toHaveCount(0);
  await expect(refused.getByTestId(SECTION_BLOCK)).toHaveCount(0);

  // Calm, and nobody at fault: the register rule holds here as everywhere else
  // on this surface. Nothing went wrong — a session simply ran out.
  expect(
    (await refused.innerText()).toLowerCase(),
    'A session running out is not a failure a student committed. `design/Usage Rules.md` §4 ' +
      'keeps student surfaces plain and blameless, and an expiry is the easiest place to slip ' +
      'into the language of error.',
  ).not.toMatch(/reject|fail|invalid|denied|forbidden|unauthori/);
});

/**
 * Launch as the learner and answer with the section's block once it is on screen.
 */
async function landOnTheSurvey(page: Page): Promise<Locator> {
  await launchAs(page, LEARNER_SUBJECT, placement);
  const block = page.getByTestId(SECTION_BLOCK);
  await expect(
    block,
    `The learner landed without a block for ${SECTION_CODE}. Three causes look the same from ` +
      'here: the roster sync has not enrolled them, the section has no materialized survey ' +
      'window for the pretended week, or the development clock is not where `beforeAll` put it.',
  ).toBeVisible();
  return block;
}

/**
 * Assert the open, unanswered state: the form is on screen and nothing else is.
 *
 * One of the five states the screen has to have, and the one every test here
 * starts in because `beforeEach` clears the week.
 */
async function expectTheFormIsShowing(block: Locator): Promise<void> {
  await expect(block.getByTestId(SUBMIT)).toBeVisible();
  await expect(block.getByTestId(REVISE)).toHaveCount(0);
}

/**
 * Delete this section's stored responses, so the week is unanswered again.
 *
 * Three statements and they have to be in this order: `classification.answer_id`
 * carries `ON DELETE RESTRICT` (ADR 0055, ADR 0115), which is the database
 * refusing to let a verdict lose the comment it judged, so the verdicts go
 * first, then the answers they named, then the response holding them.
 *
 * The application has no path that does this and should not: SPEC §3.1 says a
 * week cannot be back-filled and §8 keeps the record. This is a development
 * stack being put back to a known state, which is the same thing `make seed`
 * does for the institution around it.
 */
function clearTheWeek(): void {
  const ofThisSection =
    'select r.id from response r join section s on s.id = r.section_id ' +
    `where s.lms_section_code = ${quoted(SECTION_CODE)}`;
  databaseStatement(
    `delete from classification where answer_id in (select id from answer where response_id in (${ofThisSection}));\n` +
      `delete from answer where response_id in (${ofThisSection});\n` +
      `delete from response where id in (${ofThisSection});`,
  );
}

/**
 * Choose a point on the nth Likert scale in this block.
 *
 * **The name is anchored on the digit rather than matched exactly**, and that is
 * E2-17 item 2 reaching back into this helper: the 1 and 5 radios grow their end
 * words into their accessible names ("1 — Strongly disagree"), so `{ name: '5',
 * exact: true }` stops matching the radio it used to. The anchored pattern
 * matches the old spelling and the new one alike, which is what lets this file
 * stay green either side of that change (`docs/MISTAKES.md` entry 22: a later
 * ticket's rule makes an earlier ticket's tests unrunnable, and the repair is on
 * the test side).
 */
async function chooseRating(block: Locator, scale: number, point: string): Promise<void> {
  await block
    .getByRole('radio', { name: new RegExp(`^${point}\\b`) })
    .nth(scale)
    .check();
}

/** Type into the nth comment field in this block, or empty it. */
async function typeComment(block: Locator, field: number, words: string): Promise<void> {
  await block.getByRole('textbox').nth(field).fill(words);
}

/**
 * The helper line under the nth comment field — the optional, required or
 * coaching one.
 *
 * Reached through the field's own `aria-describedby` rather than by position or
 * by class, so this is also the assertion that the two are wired together: a
 * coaching sentence a screen reader never reaches when the field takes focus is
 * a sentence half the people meeting it do not get (SPEC §14.2 item 4).
 */
async function commentHelp(block: Locator, field: number): Promise<Locator> {
  const describes = await block.getByRole('textbox').nth(field).getAttribute('aria-describedby');
  expect(
    describes,
    `Comment field ${field} points at no description, so whatever is written under it — the ` +
      'optional-credit note, the conditional-required invitation, or §3.3’s coaching — is not ' +
      'part of the field’s accessible name or description.',
  ).not.toBeNull();
  return block.locator(`#${describes ?? ''}`);
}

/** Put the workload slider on one value, from the keyboard. */
async function setSlider(block: Locator, hours: string): Promise<void> {
  const slider = block.getByRole('slider');
  await slider.focus();
  await slider.fill(hours);
  await expect(slider).toHaveValue(hours);
}

/** The wording SPEC §3.2's first question is stored under, in the set in force. */
function firstQuestionPrompt(): string {
  return databaseStatement(
    'select prompt from question where position = 1 and question_set_id = ' +
      '(select id from question_set order by version desc limit 1);',
  );
}

/** Store one wording for that question. */
function setFirstQuestionPrompt(prompt: string): void {
  databaseStatement(
    `update question set prompt = ${quoted(prompt)} where position = 1 and question_set_id = ` +
      '(select id from question_set order by version desc limit 1);',
  );
}

/** One string as a SQL literal. */
function quoted(value: string): string {
  return `'${value.replace(/'/g, "''")}'`;
}

/**
 * Launch as the learner until the survey screen appears, or give up loudly.
 *
 * The roster sync runs in the worker after the staff launch above, so the
 * learner's enrollment arrives a second or two later. Each attempt opens its own
 * context, because a launch reuses whatever session the last one left.
 */
async function waitForTheLearnersEnrollment(browser: Browser): Promise<void> {
  const deadline = Date.now() + SYNC_TIMEOUT_MS;
  let landed = false;
  while (!landed && Date.now() < deadline) {
    const context = await browser.newContext();
    const page = await context.newPage();
    try {
      await launchAs(page, LEARNER_SUBJECT, placement);
      // The launch answers with a redirect and the application renders after
      // hydrating, so a read taken the instant `launchAs` resolves is a read
      // taken before there is anything to see. The calm page never grows this
      // testid, so an attempt that really did reach it waits this out and
      // retries — which is the behaviour this poll needs while the worker is
      // still working (`lti-launch.spec.ts` learned it first).
      //
      // `waitFor` and not `isVisible`: the second answers about the page as it
      // stands at the instant it is called and takes no timeout, so every
      // attempt read a document that had not navigated yet and the poll spent
      // its whole window measuring nothing. Measured, on the first run of this
      // file.
      landed = await page
        .getByTestId('pulse-landing-student')
        .waitFor({ state: 'visible', timeout: RENDER_WAIT_MS })
        .then(
          () => true,
          () => false,
        );
    } finally {
      await context.close();
    }
    if (!landed) await new Promise((wake) => setTimeout(wake, SYNC_RETRY_MS));
  }
  expect(
    landed,
    `The learner never reached the student view within ${SYNC_TIMEOUT_MS}ms of a staff launch ` +
      `into ${SECTION_LABEL}. The roster sync is what enrolls them (SPEC §7.3), so this is the ` +
      'worker not running, the mock platform not serving its roster, or the staff launch not ' +
      'having stored the section\'s roster address.',
  ).toBe(true);
}
