// E1-08 — the proof for criterion 2: a launch inside a cross-site iframe, with
// third-party cookies blocked, still reaches a landing view — because the
// session was carried in the URL fragment and captured into sessionStorage, not
// on a cookie.
//
// What it proves: a real launch runs this tool inside the LMS's iframe, where the
// tool is a third party and a browser increasingly blocks its cookies. The launch
// door hands the session over in the landing URL's fragment
// (/app/<role>#session=<jwt>); frontend/src/lib/session.ts lifts it into
// sessionStorage and strips it from the address bar. This spec blocks third-party
// cookies, drives a launch inside an iframe, and asserts the landing view renders
// and the session token is in the frame's sessionStorage.
//
// Test-fidelity guard: on the dev stack every service is a port on localhost, and
// localhost:8000 embedded in localhost:8080 is same-site, so the browser's
// third-party-cookie block does not actually engage and a cookie could ride along
// while this still reported the fragment path working. So the spec also reads the
// tool-origin cookies the context holds and asserts none of them is a leftover
// in-flight handshake cookie — a pass then means the fragment carried the
// session, not that an unrelated cookie happened to ride along.
//
// **The handshake is genuinely cookieless, per dispute E1-08-01's ruling.** The
// launch state/nonce live in a server-side store (app.lti.in_flight /
// lti_launch_state, dispute E1-08-05's grant), not cookies, so the launch
// validates even when third-party cookies are fully blocked. The launch door
// sets no cookie at all during the handshake, and only the session and CSRF
// cookies on a successful launch (E1-08's session model). So the tool-origin
// cookie-jar assertion below is meaningful even on a genuinely cross-site setup,
// not only on this dev stack's same-site accident: the only cookies a valid
// launch may leave behind are `pulse_session` and `pulse_csrf`, and the session
// token itself reached the frame's own JavaScript through the fragment and
// sessionStorage regardless of whether a cookie happened to carry it too.
//
// This file was not run locally (it needs the seeded Compose stack with the
// built frontend at /app); its green is the stack-up run and CI.

import { test, expect, type Frame, type Page } from '@playwright/test';

// `--disable-features=LocalNetworkAccessChecks`: Chromium 151's Local Network
// Access blocks the synthesized wrapper's loopback subframe to the mock LMS
// (localhost:8080) because a `page.route`-fulfilled page has no real origin
// Chromium will call non-public. LNA is orthogonal to what this test proves —
// the cookie/fragment/Bearer handoff — and only trips here because the dev
// stack runs on loopback; a real cross-site deployment uses routable
// hostnames LNA never blocks. Restores the intended test; does not weaken it.
test.use({
  launchOptions: {
    args: ['--test-third-party-cookie-phaseout', '--disable-features=LocalNetworkAccessChecks'],
  },
});

const MOCK_LMS_ORIGIN = 'http://localhost:8080/';
const TOOL_ORIGIN = 'http://localhost:8000';

const LAUNCH_USER = 'mock-lms-login-hint';
const LAUNCH_PLACEMENT = 'mock-lms-message-hint';
const LAUNCH_SUBMIT = 'mock-lms-launch';
const LEARNER_SUBJECT = 'mock-lms-user-learner';
const STUDENT_VIEW = 'pulse-landing-student';
const SESSION_STORAGE_KEY = 'pulse.session';

// The two cookies a valid launch may leave on the tool's own origin —
// `app.services.session.SESSION_COOKIE` and `.CSRF_COOKIE` (E1-08's interface
// ruling). Anything else here — an in-flight handshake cookie especially — is
// exactly what dispute E1-08-01's server-side store means never exists.
const EXPECTED_TOOL_COOKIES = new Set(['pulse_session', 'pulse_csrf']);

const WRAPPER_URL = `${TOOL_ORIGIN}/e2e-cookieless-wrapper`;

async function openLaunchFrame(page: Page): Promise<Frame> {
  await page.route(WRAPPER_URL, (route) =>
    route.fulfill({
      contentType: 'text/html',
      body:
        '<!doctype html><html><body>' +
        `<iframe title="lms" src="${MOCK_LMS_ORIGIN}" width="900" height="700"></iframe>` +
        '</body></html>',
    }),
  );
  await page.goto(WRAPPER_URL);
  const frame = page.frameLocator('iframe[title="lms"]');
  await frame.getByTestId(LAUNCH_USER).selectOption(LEARNER_SUBJECT);
  await frame.getByTestId(LAUNCH_PLACEMENT).selectOption({ index: 0 });
  await frame.getByTestId(LAUNCH_SUBMIT).click();
  const launched = page.frames().find((f) => f !== page.mainFrame());
  if (launched === undefined) {
    throw new Error('The launch frame was lost after submitting the launch.');
  }
  return launched;
}

test('a cookie-blocked launch reaches the student view and carries its session in the fragment', async ({
  page,
  context,
}) => {
  const frame = await openLaunchFrame(page);

  // Positive assertion first: `.toBeVisible()` waits for the correct landing
  // to render, so nothing below can pass merely because navigation had not
  // finished yet (docs/MISTAKES.md entry 3).
  await expect(frame.getByTestId(STUDENT_VIEW)).toBeVisible();

  const storedSession = await frame.evaluate(
    (key) => window.sessionStorage.getItem(key),
    SESSION_STORAGE_KEY,
  );
  expect(
    storedSession,
    'the session token should be in sessionStorage, captured from the fragment',
  ).not.toBeNull();
  expect(storedSession).toContain('.');

  const frameUrl = frame.url();
  expect(frameUrl.startsWith(`${TOOL_ORIGIN}/app/student`)).toBeTruthy();
  expect(
    frameUrl,
    'the fragment should have been stripped from the address bar once captured',
  ).not.toContain('session=');

  // The cookie-jar inventory: nothing here that is not one of the two cookies
  // a valid launch itself issues. A stray third cookie — especially one
  // shaped like an in-flight handshake carrier — is exactly what the
  // server-side store (dispute E1-08-01) means should never exist.
  const toolCookies = await context.cookies(TOOL_ORIGIN);
  const unexpected = toolCookies
    .map((cookie) => cookie.name)
    .filter((name) => !EXPECTED_TOOL_COOKIES.has(name));
  expect(
    unexpected,
    'the tool-origin cookie jar should hold nothing beyond the session and CSRF cookies a ' +
      'valid launch itself issues',
  ).toEqual([]);

  // The session cookie is required, not merely tolerated: E1-08 sets it on
  // every valid launch, cookieless handshake or not. And it carries the same
  // token the fragment delivered — one token, issued once, handed over on
  // two channels (the cookie for future same-origin requests, the fragment
  // for this frame's own JavaScript to capture) — never a different value
  // standing in for it.
  const sessionCookie = toolCookies.find((cookie) => cookie.name === 'pulse_session');
  expect(
    sessionCookie?.value,
    'the tool-origin cookie jar carries no `pulse_session` cookie after a launch that just ' +
      `landed on the student view (cookies present: ${toolCookies.map((c) => c.name).join(', ')})`,
  ).toBeDefined();
  expect(
    sessionCookie?.value,
    'the session cookie should carry the same token the fragment delivered',
  ).toBe(storedSession);
});
