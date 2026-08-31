// E1-15, exit clause 1 — SPEC §14.3, E1: "a student, an instructor, and a Dean
// each land on the right (empty) view from either door".
//
// **What this file proves, and what it cites.** The clause names three people
// and two doors. Two of the three are already proven on every CI run, and
// re-proving them here would duplicate thirty seconds of sync-poll machinery for
// no new information:
//
//   - the **instructor** through the launch door —
//     `lti-launch.spec.ts::an Instructor launch lands on the instructor view and
//     nothing else`;
//   - the **student** through the launch door —
//     `lti-launch.spec.ts::a Learner launch lands on the student view once the
//     roster sync has enrolled them`;
//   - the **Dean** through the web door — proven in a second form by
//     `web-login.spec.ts::a DEAN web login lands on /app/leadership with a
//     session`, which finds its dean by role rather than by name.
//
// What is left, and what is here, is the Dean through **both** doors in one
// spec: the web door by name, and the launch door, which nothing else in this
// suite has ever driven for a leadership person.
//
// **Why the launch half is new work rather than a missing test.** E1-12 wrote
// the Pulse-side `user` row `mock-lms-user-dean` so §7.3's leadership limb would
// be demonstrable, and the mock platform's own seed never grew the matching
// person — so today the dean's launch can be driven from the integration suite,
// which signs its own launches, and not from a browser. That is E1-12's
// deferral 1 in `docs/tickets/e1/deferred.md`, whose "done when" names this
// ticket, and it is why the second and third tests below are red until the mock
// LMS seeds him.
//
// **The third test is the browser half of that deferral's done-when**: a
// leadership launch stores the section's roster address. Its integration
// counterpart is
// `test_a_leadership_persons_launch_stores_the_roster_address_with_no_instructor_urn`,
// which owns the rows and races nothing; this is the same fact seen through the
// development console, over the live path, which is what §9.2 asks for.
//
// **On shared state.** All six specs run against one composed stack under
// several workers, so nothing here asserts that anything "was empty before"
// (`lti-launch.spec.ts:36-39`: a premise about global state that the suite
// itself can change is not a premise). The section this file uses,
// `MATH-140-E1FF`, is the one no other spec launches staff into — every other
// staff launch in the suite takes the first offered placement, which is
// `BIOL-215-R3WW` — so a roster address stored against it is one the dean's own
// launch stored. If a later spec launches staff into MATH, this test becomes a
// weaker witness and that is the sentence that says so.
//
// It is also the **only** section the mock LMS enrols the dean in, and that is a
// ruling rather than a convenience: enrolling him everywhere would put a sixth
// member in `NURS-8100-Q2FF`, whose five are exactly one page and are the
// fixture `test_a_single_page_roster_advertises_first_last_and_current_and_no_next`
// rests on. So the launch page pairs each user with their own sections now, and
// `placementInto` selects the subject before it reads the placement list. The
// served-HTML form of that pairing is asserted in
// `tests/integration/test_mock_lms_launch.py`.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect, type Page } from '@playwright/test';

import {
  ALL_LANDINGS,
  DEV_CONSOLE_PATH,
  launchAs,
  launchSubjectsOffered,
  placementInto,
  signInAs,
} from './support/doors';

// The dean's two subjects, one per door. Both are pinned by name on the Pulse
// side already — `tests/integration/test_demo_seed_script.py::MOCK_WORLD_SUBJECTS`
// holds the launch-side one and `tests/integration/test_dev_console.py::DEAN_SUBJECT`
// the web-side one — so these are transcriptions of a value the seed tests
// already guard rather than a fourth independent spelling.
const DEAN_WEB_SUBJECT = 'mock-idp-user-dean';
const DEAN_LAUNCH_SUBJECT = 'mock-lms-user-dean';

const LEADERSHIP_VIEW = 'pulse-landing-leadership';

// The section this file drives, written as §2.2 writes it. See the header on why
// it is not `BIOL-215-R3WW`.
const SECTION = 'MATH-140-E1FF';

// The development console's row for that section, and the cell that says whether
// its roster address was stored. The testid vocabulary is E1-15's contract for
// the console's sections table: one row per `section`, keyed
// `dev-section-{COURSE_PREFIX}-{COURSE_NUMBER}-{lms_section_code}`, and the cell
// answers yes or no on `lms_context_memberships_url IS NOT NULL` — never the URL
// itself, which is a service address and not something a console prints.
const SECTION_ROW = `dev-section-${SECTION}`;
const ROSTER_ADDRESS_STORED = 'section-roster-address-stored';

/**
 * Require the mock platform to offer the dean a launch, before one is driven.
 *
 * **Shared by both launch tests rather than written into one**, which is the
 * repair for a real divergence: the roster-address test below went straight to
 * `placementInto` and failed as a thirty-second `selectOption` timeout naming a
 * locator, while its sibling failed on this sentence naming the deferral. The
 * same red, two very different messages, and only one of them sends the reader
 * anywhere useful.
 */
async function requireTheDeanIsLaunchable(page: Page): Promise<void> {
  const offered = await launchSubjectsOffered(page);
  expect(
    offered,
    `The mock LMS launch page does not offer ${DEAN_LAUNCH_SUBJECT}; it offers ` +
      `${JSON.stringify(offered)}. E1-12 deferral 1: Pulse seeds that \`user\` row so §7.3's ` +
      'leadership limb is demonstrable, and the mock platform never grew the matching person, so ' +
      'the launch can be driven from the integration suite and not from a browser.',
  ).toContain(DEAN_LAUNCH_SUBJECT);
}

test('a Dean web login lands on the leadership view and nothing else', async ({ page }) => {
  // The must-be-green half of this file, and it is deliberately first. The web
  // door already lands a dean on `/app/leadership` (`web-login.spec.ts`), so a
  // red here is the shared `signInAs` helper or the seeded person, not the
  // clause — which is what tells the next reader whether the launch half below
  // failed for its own reason.
  await signInAs(page, DEAN_WEB_SUBJECT);

  // Positive first: this waits for the callback's redirect to be followed and the
  // SPA to render, so the absence checks below are about a finished navigation
  // rather than one that had not started (`docs/MISTAKES.md` entry 3).
  await expect(page.getByTestId(LEADERSHIP_VIEW)).toBeVisible();

  // Exactly one of the five. A door that landed every login on one view — or on
  // the wrong one — fails here rather than passing on the testid it was asked
  // for.
  for (const other of ALL_LANDINGS.filter((testid) => testid !== LEADERSHIP_VIEW)) {
    await expect(page.getByTestId(other)).toHaveCount(0);
  }
});

test('a Dean LTI launch lands on the leadership view and nothing else', async ({ page }) => {
  // **The mutation this must kill:** the dean dropped from `mock-lms/app/seed.py`.
  // The premise is asserted before the launch so that a missing person is a
  // sentence naming the deferral rather than a `selectOption` timeout naming a
  // locator — and so a reviewer can tell "the mock does not offer him" from "he
  // launched and landed somewhere else", which are the same red from a browser.
  await requireTheDeanIsLaunchable(page);

  const placement = await placementInto(page, DEAN_LAUNCH_SUBJECT, SECTION);
  await launchAs(page, DEAN_LAUNCH_SUBJECT, placement);

  // Positive first, and it is also what distinguishes a landing from E1-13's
  // calm no-access page: that page renders no landing view at all, so a launch
  // that stopped resolving his DEAN assignment — or filtered assignments by the
  // wrong permission column (ADR 0026's `permits_launch`) — fails here.
  await expect(page.getByTestId(LEADERSHIP_VIEW)).toBeVisible();

  for (const other of ALL_LANDINGS.filter((testid) => testid !== LEADERSHIP_VIEW)) {
    await expect(page.getByTestId(other)).toHaveCount(0);
  }
});

test("a Dean launch stores the launched section's roster address", async ({ page }) => {
  // **The mutation this must kill:** a launch door that stores the roster
  // address only for a roles claim carrying the Instructor URN. SPEC §7.3 gives
  // the address to instructors *and* leadership, and the dean's launch carries
  // no Instructor URN by construction — so a door that reads the claim instead
  // of the person's own assignments provisions this section and stores nothing,
  // and the hourly sync then has no section to discover.
  //
  // The same premise its sibling makes, and for the same reason: until the mock
  // seeds the dean this test is red, and it should say so in a sentence rather
  // than spend thirty seconds failing to find him in a `<select>`.
  await requireTheDeanIsLaunchable(page);

  const placement = await placementInto(page, DEAN_LAUNCH_SUBJECT, SECTION);
  await launchAs(page, DEAN_LAUNCH_SUBJECT, placement);

  // Positive first, twice over. The landing proves the launch was accepted, so a
  // console row that is missing below is a missing row rather than a launch that
  // never happened; and the row itself is required visible before the cell in it
  // is read, so "the address was stored" cannot pass against a console that
  // renders no sections at all.
  await expect(page.getByTestId(LEADERSHIP_VIEW)).toBeVisible();

  await page.goto(DEV_CONSOLE_PATH);
  const row = page.getByTestId(SECTION_ROW);
  await expect(
    row,
    `The development console lists no section ${SECTION}. A launch provisions the section it ` +
      'came from, so an absent row means the launch above provisioned nothing — or the console ' +
      'has no sections table, which is the surface E1-15 adds for this proof.',
  ).toBeVisible();

  await expect(
    row.getByTestId(ROSTER_ADDRESS_STORED),
    `Section ${SECTION} exists and its roster address was not stored. SPEC §7.3 has an ` +
      "instructor's or a leadership person's launch store the section's NRPS address; without it " +
      'the scheduled sync has nothing to discover and the roster is never read. This is the ' +
      'browser half of E1-12 deferral 1, whose integration counterpart is ' +
      'test_a_leadership_persons_launch_stores_the_roster_address_with_no_instructor_urn.',
  ).toHaveText(/^\s*yes\s*$/i);
});
