// E0-18 PR 2 — the proof, flow 3: the mock IdP code flow lands the dean on the
// leadership view.
//
// What it proves: starting the web door at the tool's GET /auth/oidc/login,
// signing in at the mock IdP as the dean, and returning to the tool's callback
// lands on the leadership landing view. The landing role is derived from the
// verified id_token's roles claim (ticket "The boundary with E1").
//
// Falsification (the one change that must turn it red): if the dean's completed
// web login landed on any testid but pulse-landing-leadership — a different
// role's view, or a single fixed landing for every login — this fails. The
// leadership view being empty by design (transitive_purview raises, ADR 0003)
// is expected; the spec asserts only which view was routed to, never its content.
//
// This spec cannot be run without the implementer's Playwright harness and a
// seeded, running Compose stack. At HEAD it is "red" only in the sense that no
// harness exists to run it; its green is confirmed by the implementer's stack-up
// run and CI.

import { test, expect } from '@playwright/test';

// Testids the mock IdP login form publishes (mock-idp/app/pages.py).
const IDP_IDENTITY = 'mock-idp-identity';
const IDP_SUBMIT = 'mock-idp-submit';

// Every landing view the tool can route to; the dean must reach exactly one.
const ALL_LANDINGS = [
  'pulse-landing-student',
  'pulse-landing-instructor',
  'pulse-landing-leadership',
  'pulse-landing-care',
  'pulse-landing-admin',
];

test('the dean web login lands on the leadership view and nothing else', async ({ page }) => {
  // baseURL is the tool; GET /auth/oidc/login begins the code flow and the tool
  // redirects the browser to the mock IdP's authorization endpoint.
  await page.goto('/auth/oidc/login');
  // Subject by its settled value (the option's wire value becomes the sub claim).
  await page.getByTestId(IDP_IDENTITY).selectOption('mock-idp-user-dean');
  await page.getByTestId(IDP_SUBMIT).click();

  // Positive first: this waits for the callback to render the leadership landing,
  // so the absence checks below are meaningful rather than passing on an
  // unfinished navigation (docs/MISTAKES.md entry 3).
  await expect(page.getByTestId('pulse-landing-leadership')).toBeVisible();
  for (const other of ALL_LANDINGS.filter((t) => t !== 'pulse-landing-leadership')) {
    await expect(page.getByTestId(other)).toHaveCount(0);
  }
});
