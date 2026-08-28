// E1-15, exit clause 5 — SPEC §14.3, E1: "a roster read succeeds as an
// authenticated service call, not an unauthenticated GET".
//
// **The clause has two halves and this file carries one of them.**
//
//   - *It succeeds.* Witnessed by `exit-synced-section-dates.spec.ts`, whose
//     enrolled count only becomes non-zero because the scheduled sync read the
//     mock's roster through `pylti1p3`'s token machinery. A green there is a
//     roster read that worked.
//   - *Not an unauthenticated GET.* That is here, and it is the half that makes
//     the other one mean something: a sync passing against a service that
//     answers anybody proves nothing about authentication. Two instruments, both
//     refusals — a request with no `Authorization` header at all, and one
//     carrying a bearer token the platform never issued.
//
// **Where the roster address comes from, and why it is not written down.** A
// conformant tool learns a service address one way only: from the launch's own
// NRPS claim (`mock-lms/app/launch.py` says so at length — a mock serving a
// perfect roster at a fixed path with no claim in the token has built something
// `pylti1p3` cannot find). This file learns it the same way, off the `id_token`
// the platform's self-submitting form posts to the tool, which is the only place
// a browser can see it — LTI 1.3's `form_post` response keeps the token out of
// every URL. So no context identifier is written here, and a reseeding moves
// these tests with it. The integration suite discovers the same value the same
// way (`tests/fixtures/lti_services.py::SeededContext.memberships_url`).
//
// **One thing is rewritten: the origin.** The address a launch advertises is the
// one the *tool* resolves, and on Compose that is `http://mock-lms:8000`, a name
// only a container on that network can resolve. Playwright runs on the host,
// where `docker-compose.override.yml` publishes the same service at
// `localhost:8080`. The path — and so the context identifier inside it — is
// exactly what the platform advertised.
//
// **What makes these refusals non-vacuous.** A 404 and a 401 look alike to a
// test that only asks "was it refused", and a mistyped URL produces the first
// for a reason that has nothing to do with authentication. So the status is
// asserted **exactly** 401, and the `WWW-Authenticate` header is required with
// it: that header is the thing that says "refused for want of a credential"
// rather than "no such thing here". The first test in this file is the control
// on the discovery itself, and it must be green whatever the platform does about
// tokens.
//
// **Predicted red on this branch.** The mock's NRPS route still answers 200 to a
// tokenless request: E1-06 ruled enforcement pairs with E1-11's client, E1-11
// merged without it, and the enforcement is its own pull request. Until that
// lands the two refusal tests below are red, and the control above them is
// green — which is exactly the pair a red should come in.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect, type Page } from '@playwright/test';

import {
  MOCK_LMS_ORIGIN,
  launchAs,
  launchTokensDelivered,
  onMockLmsHostOrigin,
  sessionPayload,
} from './support/doors';

const INSTRUCTOR_SUBJECT = 'mock-lms-user-instructor';
const INSTRUCTOR_VIEW = 'pulse-landing-instructor';

// NRPS 2.0's own claim and member names, as the specification spells them —
// `tests/fixtures/provisioning.py::MEMBERSHIPS_URL_MEMBER` carries the second of
// the two for the same reason. Neither is this suite's vocabulary or the mock's.
const NRPS_CLAIM = 'https://purl.imsglobal.org/spec/lti-nrps/claim/namesroleservice';
const MEMBERSHIPS_URL_MEMBER = 'context_memberships_url';

// A bearer token no token endpoint issued. Deliberately not shaped like a JWT:
// what is being asserted is that an unissued credential is refused, and a value
// that cannot be mistaken for a real one keeps the failure message readable.
const UNISSUED_TOKEN = 'not-a-token-this-platform-ever-issued';

// RFC 6750 §3: a 401 from a bearer-token-protected resource carries this header.
// It is what distinguishes "you need a credential" from "there is nothing here".
const CHALLENGE_HEADER = 'www-authenticate';

/**
 * Drive a launch and hand back the roster address it advertised, on the host origin.
 *
 * Each test does its own launch rather than sharing one, so a test that fails
 * says which of its own steps failed. The landing assertion inside is the
 * control: a launch that was refused advertises nothing, and "no roster address
 * was found" would then be a statement about a launch rather than about a claim.
 */
async function rosterAddressAdvertisedTo(page: Page): Promise<string> {
  const tokens = launchTokensDelivered(page);
  await launchAs(page, INSTRUCTOR_SUBJECT);
  await expect(page.getByTestId(INSTRUCTOR_VIEW)).toBeVisible();

  expect(
    tokens,
    'no `id_token` was seen posted to the tool, so this launch advertised nothing this test can ' +
      "read. LTI 1.3 delivers a launch as a self-submitting form post; if that has changed, this " +
      'file needs a different seam and not a different assertion.',
  ).not.toHaveLength(0);

  const claim = sessionPayload(tokens[0])[NRPS_CLAIM];
  expect(
    typeof claim === 'object' && claim !== null,
    `the launch carries no \`${NRPS_CLAIM}\` object. That claim is the only way a conformant tool ` +
      'learns where a roster is served, so without it there is no roster read to authenticate ' +
      'and nothing here to assert.',
  ).toBeTruthy();

  const advertised = (claim as Record<string, unknown>)[MEMBERSHIPS_URL_MEMBER];
  expect(
    typeof advertised === 'string' && advertised.length > 0,
    `the NRPS claim carries no \`${MEMBERSHIPS_URL_MEMBER}\` (it carries ` +
      `${JSON.stringify(claim)}).`,
  ).toBeTruthy();

  const url = advertised as string;
  expect(
    url.startsWith('http://') || url.startsWith('https://'),
    `the roster address \`${url}\` is not absolute. A tool resolves this value with no knowledge ` +
      'of where the token came from, so a relative path is a service it cannot call.',
  ).toBeTruthy();

  return onMockLmsHostOrigin(url);
}

test('the roster address a launch advertises is served at the published mock origin', async ({
  page,
  request,
}) => {
  // The control on everything below, and it must be green whatever the platform
  // does about tokens. Two ways the refusal tests could otherwise pass while
  // proving nothing: a launch that advertised no address at all — asserted
  // inside the helper — and an origin rewrite that points at nothing, so that
  // every request is refused by a listener that is not this platform.
  const address = await rosterAddressAdvertisedTo(page);

  const landing = await request.get(MOCK_LMS_ORIGIN);
  expect(
    landing.status(),
    `${MOCK_LMS_ORIGIN} does not serve the mock platform's launch page, so the origin these ` +
      'tests rewrite roster addresses onto is not the platform. `docker-compose.override.yml` ' +
      'publishes it there.',
  ).toBe(200);

  expect(
    address.startsWith(MOCK_LMS_ORIGIN.replace(/\/$/, '')),
    `the rewritten roster address \`${address}\` is not on ${MOCK_LMS_ORIGIN}, so the two ` +
      'requests below would be made against whatever host the launch happened to name.',
  ).toBeTruthy();
});

test('the mock platform refuses a roster read carrying no Authorization header', async ({
  page,
  request,
}) => {
  const address = await rosterAddressAdvertisedTo(page);

  const answered = await request.get(address, { failOnStatusCode: false });

  // Exactly 401, and the reason for the exactness is in the file header: a 404
  // is what a mistyped address produces, and "not 200" would accept it.
  expect(
    answered.status(),
    `A tokenless GET of ${address} answered ${answered.status()}. SPEC §14.3 (E1) requires the ` +
      'roster read to be an authenticated service call and not an unauthenticated GET, so a 200 ' +
      'here means the sync that passes elsewhere in this suite could have been passing without ' +
      'ever presenting a credential. A 404 would mean this address is wrong and the test proves ' +
      'nothing either way.',
  ).toBe(401);

  expect(
    answered.headers()[CHALLENGE_HEADER],
    `the 401 from ${address} carries no \`WWW-Authenticate\` header. RFC 6750 §3: that header is ` +
      'what tells a client it was refused for want of a credential rather than for want of a ' +
      'resource, and it is what makes this assertion about authentication.',
  ).toBeDefined();
});

test('the mock platform refuses a roster read carrying a token it never issued', async ({
  page,
  request,
}) => {
  // The other half of the pair. A service that refuses a *missing* header and
  // accepts any string presented in one is a service with an authentication
  // check that reads whether a header exists — which is the near miss the first
  // test cannot tell from the real thing.
  const address = await rosterAddressAdvertisedTo(page);

  const answered = await request.get(address, {
    headers: { authorization: `Bearer ${UNISSUED_TOKEN}` },
    failOnStatusCode: false,
  });

  expect(
    answered.status(),
    `A GET of ${address} bearing a token no token endpoint issued answered ` +
      `${answered.status()}. A platform that accepts an unissued bearer token is authenticating ` +
      'the presence of a header, which is no authentication at all.',
  ).toBe(401);
});
