// E0-18 PR 2 — the proof, flow 4: the two-hat person opens both doors, and each
// lands role-appropriately.
//
// What it proves, in ONE spec: the person who holds a Care assignment on the web
// door and teaches on the launch door can enter through both, and each door
// routes to the view its own verified claim names — the web door to Care, the
// launch door to instructor.
//
// What it deliberately does NOT prove: that the two doors resolve to one stored
// person. The database-level same-identity merge is E1's, recorded in E1's
// carried-forward notes (carried-from-e0.md); nothing in E0 stores a user row
// for a mock subject (ticket "The boundary with E1", consequence 2). This spec is
// the browser witness that both doors open for her and land role-appropriately,
// not that they are one row.
//
// Falsification (the one change that must turn it red): if the web door read her
// launch-only instructor role instead of her Care role — landing her on the
// instructor view — the first half fails; if the launch door landed her teaching
// identity anywhere but the instructor view, the second half fails. A door that
// routed by the wrong one of her two hats is exactly what this catches.
//
// This spec cannot be run without the implementer's Playwright harness and a
// seeded, running Compose stack. At HEAD it is "red" only in the sense that no
// harness exists to run it; its green is confirmed by the implementer's stack-up
// run and CI.

import { test, expect } from '@playwright/test';

// Settled fact (E0-18 ticket + docker-compose.override.yml): the mock LMS launch
// page origin. baseURL — the tool — comes from playwright.config.ts.
const MOCK_LMS_ORIGIN = 'http://localhost:8080/';

test('both doors open for the two-hat person and each lands role-appropriately', async ({ page }) => {
  // Web door — her Care assignment. The mock IdP will only ever sign her in
  // under the Care half (mock-idp index page), so a completed web login must
  // land on Care, never on the instructor view her other hat holds.
  await page.goto('/auth/oidc/login');
  await page.getByTestId('mock-idp-identity').selectOption('mock-idp-user-care-who-teaches');
  await page.getByTestId('mock-idp-submit').click();
  await expect(page.getByTestId('pulse-landing-care')).toBeVisible();
  await expect(page.getByTestId('pulse-landing-instructor')).toHaveCount(0);

  // Launch door — her teaching identity (the shared mock LMS instructor subject
  // that mock-idp/app/seed.py::LMS_INSTRUCTOR_USER_ID pins her to). A launch as
  // that subject carries the Instructor roles claim and must land on the
  // instructor view, never on Care.
  await page.goto(MOCK_LMS_ORIGIN);
  await page.getByTestId('mock-lms-login-hint').selectOption('mock-lms-user-instructor');
  await page.getByTestId('mock-lms-message-hint').selectOption({ index: 0 });
  await page.getByTestId('mock-lms-launch').click();
  await expect(page.getByTestId('pulse-landing-instructor')).toBeVisible();
  await expect(page.getByTestId('pulse-landing-care')).toHaveCount(0);
});
