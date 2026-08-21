// E0-18 PR 2 — the proof, flow 1 and 2: an LTI launch lands on the view its
// verified LIS roles claim names.
//
// What it proves: a launch initiated from the mock LMS as a Learner reaches the
// tool's student landing view; the same launch as an Instructor reaches the
// instructor landing view. The landing role is derived from the verified token's
// roles claim alone (ticket "The boundary with E1"), so this is the browser-level
// witness that the claim is read and routed.
//
// Falsification (the one change that must turn each case red): if the launch
// ignored the LIS roles claim and landed on any testid but the one its role
// names — the other role's view, or both views at once — the case fails. A door
// that rendered a single fixed landing for every launch fails one case or the
// other.
//
// This spec cannot be run without the implementer's Playwright harness
// (package.json, playwright.config.ts, baseURL) and a seeded, running Compose
// stack. At HEAD it is "red" only in the sense that no harness exists to run it;
// its green is confirmed by the implementer's stack-up run and CI.

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
  // resource_link_id: both launch-page users are enrolled in every seeded
  // section, so any offered placement is a valid launch, and reading the offered
  // value keeps this from encoding a section identifier the seed may renumber.
  await page.getByTestId(LAUNCH_PLACEMENT).selectOption({ index: 0 });
  await page.getByTestId(LAUNCH_SUBMIT).click();
}

const cases = [
  {
    name: 'a Learner launch lands on the student view and nothing else',
    subject: 'mock-lms-user-learner',
    lands: 'pulse-landing-student',
    forbidden: 'pulse-landing-instructor',
  },
  {
    name: 'an Instructor launch lands on the instructor view and nothing else',
    subject: 'mock-lms-user-instructor',
    lands: 'pulse-landing-instructor',
    forbidden: 'pulse-landing-student',
  },
];

for (const c of cases) {
  test(c.name, async ({ page }) => {
    await launchAs(page, c.subject);
    // Positive assertion first: getByTestId(...).toBeVisible() waits for the
    // correct landing to render, so the absence check below cannot pass merely
    // because navigation had not finished (docs/MISTAKES.md entry 3).
    await expect(page.getByTestId(c.lands)).toBeVisible();
    await expect(page.getByTestId(c.forbidden)).toHaveCount(0);
  });
}
