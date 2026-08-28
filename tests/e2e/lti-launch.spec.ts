// E0-18 PR 2 — the proof, flow 1 and 2: what an LTI launch lands on.
//
// **Rewritten for E1-13, and the header is rewritten with it.** This comment used
// to read "the landing role is derived from the verified token's roles claim
// alone", which was true and is the model E1-13 retires. The landing now comes
// from the launching person's own live assignments, filtered by ADR 0026's
// `permits_launch` column, with enrollment as the student fallback (ADR 0028);
// no roles claim, in either vocabulary, has any say in which view a person
// reaches. That is the same one-level-up correction E1-13 made to the section
// header in tests/integration/test_web_login_door.py — a record left asserting
// the retired model is how the next reader learns the wrong rule.
//
// What the two cases prove now:
//
//   - **An Instructor launch reaches the instructor view**, because the seeded
//     mock-world person behind that subject holds a live INSTRUCTOR assignment.
//     This case is unchanged and is now a stronger witness than it was: it used
//     to show a claim being routed and now shows an assignment being resolved.
//   - **A Learner launch on a fresh stack reaches the calm no-access page**, and
//     no landing view at all. That is the browser-level witness that the claim
//     stopped deciding: the token says Learner as loudly as it ever did, and the
//     person behind it holds nothing Pulse's own records can land them on.
//
// Why the Learner case cannot land on a freshly seeded stack, which is a fact
// about the seed rather than a gap: a student's access resolves from `enrollment`
// (ADR 0028), enrollment rows are written by the roster sync, a **student** launch
// triggers no sync (SPEC §7.3 — instructors and leadership only), and the seed
// cannot write an enrollment scoped to a section that does not exist until the
// first staff launch provisions it. So on a fresh stack the ordering is
// staff launch → sync → student launch, and only then does a Learner land.
//
// **The student-lands-in-a-browser proof is not dropped, it is owned elsewhere.**
// E1-15's exit clause owns that orchestration — staff launch, roster sync, then a
// student launch that lands on `pulse-landing-student` — because it is the spec
// that can drive the three steps in order. Nothing here should be read as saying
// a student never reaches a view in a browser.
//
// Falsification (the changes that must turn these red): a door that landed a
// person on a view their rows do not entitle them to — the Learner reaching any
// landing testid at all — fails the first case, and that is the mutation E1-13
// exists to kill. A door that stopped resolving assignments, or filtered them by
// the wrong permission column, lands the instructor on the calm page and fails
// the second. A door that rendered a single fixed answer for every launch fails
// one or the other.
//
// This spec cannot be run without the implementer's Playwright harness
// (package.json, playwright.config.ts, baseURL) and a seeded, running Compose
// stack.

import { test, expect, Page } from '@playwright/test';

// Settled fact (E0-18 ticket + docker-compose.override.yml): the mock LMS serves
// its launch page at this browser-facing origin. baseURL — the tool, on
// http://localhost:8000 — comes from playwright.config.ts and is not repeated here.
const MOCK_LMS_ORIGIN = 'http://localhost:8080/';

// Testids the mock LMS launch form publishes (mock-lms/app/pages.py) and the
// tool's landing views publish. Named once so a rename is one line, not a search.
const LAUNCH_USER = 'mock-lms-login-hint';
const LAUNCH_PLACEMENT = 'mock-lms-message-hint';
const LAUNCH_SUBMIT = 'mock-lms-launch';

async function launchAs(page: Page, subject: string): Promise<void> {
  await page.goto(MOCK_LMS_ORIGIN);
  // Subject by its settled value (the option's wire value is the user_id).
  await page.getByTestId(LAUNCH_USER).selectOption(subject);
  // Placement by the first offered option rather than a hardcoded
  // resource_link_id: the mock LMS offers both launch-page users a placement in
  // every section it seeds, so any offered placement is a valid launch, and
  // reading the offered value keeps this from encoding a section identifier the
  // seed may renumber.
  //
  // "A placement the mock offers" is not "a row in Pulse's `enrollment` table",
  // and since E1-13 the difference decides where a launch lands. The mock's
  // placements are what a platform lets somebody launch *from*; enrollment is
  // Pulse's own record of who is in a section, written by the roster sync, and
  // it is what the student fallback reads. The Learner case below turns on
  // exactly that gap.
  await page.getByTestId(LAUNCH_PLACEMENT).selectOption({ index: 0 });
  await page.getByTestId(LAUNCH_SUBMIT).click();
}

// Every landing view the tool can render, so "no landing at all" is a statement
// about all five rather than about the one this file happened to think of. The
// same five are named in tests/fixtures/doors.py and in landing-views.spec.ts.
const ALL_LANDINGS = [
  'pulse-landing-student',
  'pulse-landing-instructor',
  'pulse-landing-leadership',
  'pulse-landing-care',
  'pulse-landing-admin',
];

// E1-13's calm page, by the testid the server-rendered page carries. Not one of
// the five landings and not the refusal page: a launch this door verified, by a
// person whose rows entitle them to no view, is a state rather than a fault.
const NO_ACCESS = 'no-access';

test('a Learner launch on a fresh stack is answered with the calm page and no landing view', async ({
  page,
}) => {
  await launchAs(page, 'mock-lms-user-learner');

  // Positive assertion first: `.toBeVisible()` waits for the calm page to
  // render, so the absence checks below cannot pass merely because navigation
  // had not finished (docs/MISTAKES.md entry 3). It also makes this a statement
  // about *which* answer arrived: a refusal page or a blank document would fail
  // here rather than sail through five absence checks.
  await expect(page.getByTestId(NO_ACCESS)).toBeVisible();

  // The whole of what the claim bought her. Her token states the Learner role,
  // verified and signed, and Pulse's own records hold no assignment and no live
  // enrollment for the subject behind it — so she reaches none of the five.
  for (const landing of ALL_LANDINGS) {
    await expect(page.getByTestId(landing)).toHaveCount(0);
  }
});

test('an Instructor launch lands on the instructor view and nothing else', async ({ page }) => {
  await launchAs(page, 'mock-lms-user-instructor');
  // Positive assertion first: getByTestId(...).toBeVisible() waits for the
  // correct landing to render, so the absence check below cannot pass merely
  // because navigation had not finished (docs/MISTAKES.md entry 3).
  await expect(page.getByTestId('pulse-landing-instructor')).toBeVisible();
  await expect(page.getByTestId('pulse-landing-student')).toHaveCount(0);
});
