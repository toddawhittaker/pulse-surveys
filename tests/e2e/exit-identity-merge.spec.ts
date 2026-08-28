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
// **And one value compared with itself is the same emptiness wearing a
// different shape**, which a security review found here and which is worth
// stating at the top rather than only at the line that fixes it. Both tokens are
// read from one `sessionStorage` key. If the launch delivers no session, the web
// login's token is still sitting in that key, `sessionToken` returns it a second
// time — its wait is satisfied instantly by a URL that never carried a fragment
// — and the clause passes having compared the Care token with the Care token.
// The key is therefore cleared between the doors, and the two tokens are
// required to differ.
//
// Falsification — the changes that must turn this red:
//
//   - a launch door that delivers no session at all: the launch token is null
//     and the presence assertion fails. This is the one that used to pass, and
//     the reason for the clear and the inequality;
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

import {
  SESSION_STORAGE_KEY,
  launchAs,
  sessionPayload,
  sessionToken,
  signInAs,
} from './support/doors';

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
  //
  // **The key is cleared first, and that is a repair rather than tidiness.** This
  // comment used to say "the launch overwrites the key", which stated as an
  // assumption the very thing under proof: `sessionToken` waits only for a URL
  // with no `session=` in it, and a URL that never carried a fragment satisfies
  // that instantly, while the SPA's capture returns early without clearing when
  // there is no fragment to capture. So a launch that delivered **no** session
  // would leave her Care token sitting in the key, and this clause would compare
  // the web token with itself and pass — the emptiest possible green, on exactly
  // the failure it exists to catch. The battery's `person_id=None` mutation did
  // not expose it because that mutation still delivered a fragment.
  //
  // Two guards, deliberately: the key is emptied here, and the two tokens are
  // required to differ below. Either alone would close it; together, a future
  // change that removes one leaves the other. Clearing the key is the same idiom
  // `exit-refused-launches.spec.ts` uses between its legitimate launch and its
  // replay, and for the same reason — anything found afterwards was delivered
  // afterwards.
  await page.evaluate((key) => window.sessionStorage.removeItem(key), SESSION_STORAGE_KEY);

  await launchAs(page, LAUNCH_SUBJECT);
  await expect(page.getByTestId(INSTRUCTOR_VIEW)).toBeVisible();

  const launchToken = await sessionToken(page);
  expect(
    launchToken,
    'a completed launch leaves its session token in sessionStorage, captured from the fragment ' +
      '(E1-08); with none, the comparison below is about one value and an absence',
  ).not.toBeNull();
  // The second of the two guards on aliasing. A token identical to the web
  // door's is not a launch that agreed with the web login — it is the web
  // login's own token, read twice, which is what the cleared key above is meant
  // to make impossible and what this makes impossible to miss if it ever is not.
  expect(
    launchToken,
    'the launch door left the *same* token the web login did. That is not two doors agreeing on ' +
      'one person: it is one token read twice, because the launch delivered no session of its ' +
      'own and the previous one was still in sessionStorage. Every assertion below would then be ' +
      'comparing the web token with itself and passing on the exact failure this clause exists ' +
      'to catch.',
  ).not.toEqual(webToken);

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
