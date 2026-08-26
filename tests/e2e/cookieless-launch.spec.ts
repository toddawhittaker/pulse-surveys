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
// third-party-cookie block does not actually engage — a cookie could in
// principle ride along while this still reported the fragment path working.
// What closes that gap here is not the 3PC block but a second, independent
// reason the cookie jar comes back empty: the tool is served over http with
// `ENVIRONMENT=development`, so its session and CSRF cookies are emitted
// `SameSite=None` without `Secure` (the two-secret-cookie interface E1-08
// settles), and a browser refuses to store a `SameSite=None` cookie that is
// not `Secure`, same-site or not. So the spec reads the tool-origin cookie jar
// and asserts it carries neither cookie — a pass then means the fragment
// carried the session on this stack for a reason that also holds in a real
// https cross-site deployment (there the third-party-cookie block itself
// closes the gap the dev stack's same-siteness leaves open).
//
// **The handshake is genuinely cookieless, per dispute E1-08-01's ruling.** The
// launch state/nonce live in a server-side store (app.lti.in_flight /
// lti_launch_state, dispute E1-08-05's grant), not cookies, so the launch
// validates even when third-party cookies are fully blocked. The launch door
// sets no cookie at all during the handshake, and the session and CSRF cookies
// a successful launch does send (E1-08's session model) are exactly the two
// this spec proves never reach the browser's jar on this stack, for the reason
// above — the session reaches this frame's own JavaScript through the
// fragment and sessionStorage alone.
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

  // Criterion 2 / SPEC §7.3, the actual proof: the session survived on the
  // fragment → sessionStorage path (asserted above), NOT on a cookie. The
  // tool-origin cookie jar carries neither the session nor the CSRF cookie. The
  // server does send `Set-Cookie` for both on every valid launch, but the browser
  // declines them here: on the dev stack the tool is served over http with
  // `ENVIRONMENT=development`, so `set_session_cookie`/`set_csrf_cookie` emit
  // `SameSite=None` WITHOUT `Secure`, and a browser rejects a `SameSite=None`
  // cookie that is not `Secure`. In a real https cross-site deployment the same
  // jar is empty for the other half of the reason — the third-party-cookie block.
  // Either way the session cannot have ridden a cookie, which is the whole point.
  const toolCookieNames = (await context.cookies(TOOL_ORIGIN)).map((c) => c.name);
  expect(
    toolCookieNames,
    'a cookie-blocked cross-site launch must leave no session cookie on the tool origin — ' +
      'the session reached this frame through the fragment and sessionStorage, not a cookie',
  ).not.toContain('pulse_session');
  expect(
    toolCookieNames,
    'nor a CSRF cookie: it shares the session cookie’s SameSite=None/no-Secure attributes ' +
      'and is declined for the same reason',
  ).not.toContain('pulse_csrf');
});
