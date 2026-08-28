// E1-15, exit clause 2 — SPEC §14.3, E1: "the seeded two-hat person enters by
// both doors and resolves to the same stored identity row".
//
// **What this proves that `two-hat.spec.ts` does not.** That spec proves both
// doors open for her and each lands role-appropriately, and says in as many
// words that the same-identity merge is "E1's DB-level concern, out of scope
// here". This is the spec that closes that forward reference: she enters by both
// doors in one test, and the two entries name one `person`.
//
// **The seam, and why it is honest.** The ticket allows a dev-only introspection
// for this assertion and none is needed: the app's own session token carries the
// `person_id` the door resolved (`backend/app/services/session.py`, ADRs 0094
// and 0097), so what is compared is the tool's own answer to "who is this",
// taken from the artifact it hands the browser, at both doors. The token is
// decoded and **not verified** — a spec reads a claim to say what a door
// decided; it does not trust it for anything (`support/doors.ts::sessionPayload`).
//
// **The order of the assertions is the whole design.** Two absent values compare
// equal, and a merge asserted as `a === b` over two nulls is the emptiest
// possible pass (`docs/MISTAKES.md` entry 3). So each door's `person_id` is
// required present *before* the two are compared, and the file says which
// mutation each half kills.
//
// Falsification — the changes that must turn this red:
//
//   - a launch door that mints its session with `person_id` unset: the second
//     presence assertion fails, naming the door;
//   - a door that resolves her launch to a second `person` row rather than to
//     the one her web login resolves to (the identity merge failing in the
//     direction E1-12 is about): the equality fails, with both values printed;
//   - either door failing to land her at all: the landing assertion above the
//     read fails first, so a null token is never read as a missing merge.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect } from '@playwright/test';

import { launchAs, sessionPayload, sessionToken, signInAs } from './support/doors';

// Her two subjects, one per door. `scripts/seed.py::MOCK_WORLD_PEOPLE` links
// both to one person — the web-side subject through the mock provider's seed,
// the launch-side one through `mock-idp/app/seed.py::LMS_INSTRUCTOR_USER_ID` —
// and `test_the_seed_links_the_two_hat_persons_two_subjects_to_one_person` is
// the seed-level guard on the same fact. This is its browser half.
const WEB_SUBJECT = 'mock-idp-user-care-who-teaches';
const LAUNCH_SUBJECT = 'mock-lms-user-instructor';

const CARE_VIEW = 'pulse-landing-care';
const INSTRUCTOR_VIEW = 'pulse-landing-instructor';

// The claim the session token carries the resolved identity in.
const PERSON_CLAIM = 'person_id';

test('both doors resolve the two-hat person to one stored identity', async ({ page }) => {
  // -- The web door, her Care hat. -----------------------------------------
  //
  // Positive first: this waits for the callback's redirect to be followed and
  // the SPA to render, so the session read below is taken after a finished
  // entry (`docs/MISTAKES.md` entry 3). It is also the control for everything
  // that follows — `two-hat.spec.ts` already proves this half lands on Care, so
  // a red here is the helper or the seed rather than the merge.
  await signInAs(page, WEB_SUBJECT);
  await expect(page.getByTestId(CARE_VIEW)).toBeVisible();

  const webToken = await sessionToken(page);
  expect(
    webToken,
    'a completed web login leaves its session token in sessionStorage; with none there is ' +
      'nothing to read a resolved identity out of, and the comparison below would be about two ' +
      'absent values',
  ).not.toBeNull();
  const webPerson = sessionPayload(webToken as string)[PERSON_CLAIM];
  expect(
    webPerson,
    `the web door's session carries no \`${PERSON_CLAIM}\`. That claim is how the tool says which ` +
      'stored person a verified subject resolved to, and without it this clause has no seam to be ' +
      'asserted through at all',
  ).toBeTruthy();

  // -- The launch door, her teaching hat. -----------------------------------
  //
  // The same browser, so the two entries are the two entries one person makes.
  // sessionStorage is per origin and the launch overwrites the key, which is why
  // the web token is read above rather than at the end.
  await launchAs(page, LAUNCH_SUBJECT);
  await expect(page.getByTestId(INSTRUCTOR_VIEW)).toBeVisible();

  const launchToken = await sessionToken(page);
  expect(
    launchToken,
    'a completed launch leaves its session token in sessionStorage, captured from the fragment ' +
      '(E1-08); with none, the comparison below is about one value and an absence',
  ).not.toBeNull();
  const launchPerson = sessionPayload(launchToken as string)[PERSON_CLAIM];
  expect(
    launchPerson,
    `the launch door's session carries no \`${PERSON_CLAIM}\`. This is the mutation the clause is ` +
      'written against: a door that mints a session without naming the person it resolved has ' +
      'nothing behind every purview decision that follows',
  ).toBeTruthy();

  // -- The clause. ----------------------------------------------------------
  expect(
    launchPerson,
    'her launch and her web login resolved to two different stored people. SPEC §14.3 (E1): the ' +
      'seeded two-hat person "enters by both doors and resolves to the same stored identity row" ' +
      '— two rows means every assignment she holds is split across two purviews, and the door ' +
      'she used decides what she can see.',
  ).toEqual(webPerson);
});
