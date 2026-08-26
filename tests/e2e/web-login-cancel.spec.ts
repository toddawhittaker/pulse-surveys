// E1-09 criterion 2 — Playwright drives an IdP refusal; the tool shows the calm
// page; no session exists afterwards.
//
// What it proves: a web login that ends in RFC 6749 §4.1.2.1's error redirect —
// the user cancelled, the provider declined — lands the person on E1-09's calm
// page, and no session is ever handed to the browser.
//
// **How the absence is asserted, and how it is not.** The criterion asks for the
// forbidden state (docs/MISTAKES.md entry 2), and the trap in asserting one in a
// browser is that almost everything is absent when nothing happened. So two
// instruments are used, and each is shown finding a session on the login that
// succeeds:
//
//   - every response's `Location` header is collected, and a `#session=` fragment
//     must never appear in one. That is "the session was never delivered", read
//     off the wire rather than inferred.
//   - the SPA's sessionStorage key must be empty. That is "the session was never
//     captured", read where E1-08 puts it.
//
// The second test in this file is the control for both: the same collector and the
// same read, on a login that completes, where both must find the session. Without
// it, a spec whose page never navigated would report a clean pass.
//
// **The cookie jar is deliberately not consulted.** On the dev stack the tool's
// session and CSRF cookies are emitted `SameSite=None` without `Secure` (it is
// served over http with ENVIRONMENT=development), and a browser refuses to store
// such a cookie at all — so the jar is empty after a *successful* login too, and
// its emptiness proves nothing. That is E1-08's cookieless-launch lesson, and
// reaching for the jar here is the one way this spec could pass while a session
// was being handed out.
//
// Falsification (the changes that must turn the cancel case red): a door with no
// error branch, which refuses and never shows the calm page; a door that shows the
// calm page and issues a session anyway; a door that treats the returned `state`
// as good enough without comparing it, which the integration suite catches in
// detail and which shows up here as the calm page appearing for a browser that
// never began a login.
//
// This spec cannot be run without a production frontend build and a seeded,
// running Compose stack; its green is the stack-up run and CI.

import { test, expect, type Page } from '@playwright/test';

// Testids the mock IdP login form publishes (mock-idp/app/pages.py).
const IDP_IDENTITY = 'mock-idp-identity';
const IDP_SUBMIT = 'mock-idp-submit';

// E1-09's contract for the page a cancelled login lands on.
const CANCELLED_VIEW = 'web-login-cancelled';

// Where the SPA keeps a session it lifted out of the fragment (E1-08,
// frontend/src/lib/session.ts).
const SESSION_STORAGE_KEY = 'pulse.session';

// A subject the mock IdP's seed does not carry. Its login form offers a select and
// a submit button and no cancel control (mock-idp/app/pages.py), so a cancel is
// produced the way that form can produce one: by naming somebody this provider
// will not sign in. RFC 6749 §4.1.2.1 gives both events the same answer —
// `access_denied` with the `state` echoed — which is why
// tests/integration/test_mock_idp_error_redirects.py uses the same shape and says
// so in its own docstring.
const UNKNOWN_SUBJECT = 'e1-09-nobody';

// Collect the `Location` of every response that hands the browser a session token.
// Attached before the first navigation, so it sees the callback's own redirect.
function sessionsDelivered(page: Page): string[] {
  const delivered: string[] = [];
  page.on('response', (response) => {
    const location = response.headers()['location'];
    if (location !== undefined && location.includes('session=')) delivered.push(location);
  });
  return delivered;
}

function storedSession(page: Page): Promise<string | null> {
  return page.evaluate((key) => window.sessionStorage.getItem(key), SESSION_STORAGE_KEY);
}

test('a cancelled web login shows the calm page and no session is ever delivered', async ({
  page,
}) => {
  const delivered = sessionsDelivered(page);

  await page.goto('/auth/oidc/login');
  // Name somebody this provider will not sign in. The option is added to the
  // form's own select rather than typed somewhere else, so what reaches the
  // provider is the request its form makes; the provider decides the rest.
  await page.getByTestId(IDP_IDENTITY).evaluate((element, subject) => {
    const select = element as HTMLSelectElement;
    const option = document.createElement('option');
    option.value = subject;
    option.textContent = subject;
    select.append(option);
    select.value = subject;
  }, UNKNOWN_SUBJECT);
  await page.getByTestId(IDP_SUBMIT).click();

  // Positive first: this waits for the provider's error redirect to reach the
  // tool's callback and for the calm page to render, so the two absences below
  // are about a finished navigation (docs/MISTAKES.md entry 3).
  await expect(page.getByTestId(CANCELLED_VIEW)).toBeVisible();

  expect(
    delivered,
    'no response in a cancelled login may carry a session token in its Location — the token is ' +
      'how this tool hands a session to a browser, and nobody was signed in',
  ).toEqual([]);
  expect(
    await storedSession(page),
    'the SPA holds no session after a cancelled login; the control below shows this same read ' +
      'finding one when a login succeeds',
  ).toBeNull();
});

test('the same instruments find a session when the login succeeds', async ({ page }) => {
  // The control, and the test above is worth nothing without it. If a spec whose
  // login never happened can report "no session delivered, nothing stored", then
  // so can one whose page failed to navigate — this is what tells the two apart
  // (docs/MISTAKES.md entry 35: require the guard to find the thing on a subject
  // that certainly has it).
  const delivered = sessionsDelivered(page);

  await page.goto('/auth/oidc/login');
  await page.getByTestId(IDP_IDENTITY).selectOption({ index: 0 });
  await page.getByTestId(IDP_SUBMIT).click();

  // Whoever the form offers first is a seeded person this door signs in, so this
  // lands on one of the three routes §2 gives the web door. Which one is
  // tests/e2e/web-login.spec.ts's subject, not this file's: all that matters here
  // is that a session was delivered and captured.
  await expect(page).toHaveURL(/\/app\//);

  expect(
    delivered.length,
    'a completed web login must deliver its session in a Location fragment; if this is zero the ' +
      'collector above sees nothing and the cancel case proves nothing',
  ).toBeGreaterThan(0);
  expect(delivered.some((location) => location.includes('#session='))).toBeTruthy();
  expect(
    await storedSession(page),
    'a completed web login leaves the session in sessionStorage; if this is null the read above ' +
      'is blind and the cancel case proves nothing',
  ).not.toBeNull();
});
