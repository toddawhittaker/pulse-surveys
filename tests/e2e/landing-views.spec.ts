// E1-04 — the five empty landing views, served by the application at their own
// routes.
//
// What it proves: each of the five role routes under /app is served by the tool,
// renders the landing view that route names, and renders it with the governed
// copy — the heading and the empty-state sentence — from the served route rather
// than from a string this file handed the page. E1-04 acceptance criterion 4:
// "a spec asserts each landing view renders its role label from a served route
// (not a fixture string)."
//
// Why this is the instrument for that criterion and a unit test is not: the copy
// has to come out of the built application, through the app factory's static
// serve, through the client router, into a real browser. Nothing short of that
// distinguishes "the string is in the repository" from "a person landing here
// reads it".
//
// Falsification (the changes that must turn it red): a route that 404s because
// the SPA fallback is missing; a route that renders another role's view; a
// heading edited away from the governed wording; a view with no main landmark or
// with more than one h1 (SPEC §14.2 item 4 puts accessibility in-slice —
// labelled landmarks on every landing view now, not in E13).
//
// What it deliberately does NOT prove: that any door redirects here. Both doors
// render at their own entry URLs today, and the post-entry redirect arrives with
// E1-08/E1-09's sessions; the existing door specs are the witnesses for entry.
// This spec navigates directly, which is also what the wiring contract says the
// frontend must cope with — the backend decides the role and hands over a route,
// and the frontend renders whatever route it is handed and never re-derives role
// from anything client-side.
//
// This spec cannot be run without a production build and a running, seeded
// Compose stack. At HEAD it is "red" only in the sense that there is no frontend
// to serve; its green is confirmed by the implementer's stack-up run and CI.

import { test, expect } from '@playwright/test';

// Every landing view the tool can render. Each route must reach exactly one of
// them (E0-18 established these testids; the same five are named in
// tests/fixtures/doors.py, mock-idp/app/pages.py's convention, and the door
// specs beside this one).
const ALL_LANDINGS = [
  'pulse-landing-student',
  'pulse-landing-instructor',
  'pulse-landing-leadership',
  'pulse-landing-care',
  'pulse-landing-admin',
];

// The governed copy, per SPEC §4.1 items 4 and 5 and docs/DESIGN_BRIEF.md's
// register rules: calm, plain, counting nothing and blaming nobody. It is
// written here rather than read from the application on purpose — a spec that
// asked the page what its own heading was would pass against any heading at all.
const VIEWS = [
  {
    role: 'student',
    testid: 'pulse-landing-student',
    heading: 'Your weekly check-in',
    empty: 'There is no survey open for you yet. When one opens, it appears here.',
  },
  {
    role: 'instructor',
    testid: 'pulse-landing-instructor',
    heading: 'Your section report',
    empty: 'There are no responses to report yet. Reports appear here once a week has closed.',
  },
  {
    role: 'leadership',
    testid: 'pulse-landing-leadership',
    heading: 'Your roll-up',
    empty: 'There is nothing to roll up yet. Sections you oversee appear here once they report.',
  },
  {
    role: 'care',
    testid: 'pulse-landing-care',
    heading: 'Community standards queue',
    empty: 'Nothing needs attention.',
  },
  {
    role: 'admin',
    testid: 'pulse-landing-admin',
    heading: 'Pulse console',
    empty: 'There is nothing to administer yet.',
  },
];

for (const view of VIEWS) {
  test(`the ${view.role} route renders the ${view.role} landing view and its governed copy`, async ({
    page,
  }) => {
    // baseURL is the tool (playwright.config.ts). The SPA mounts at /app and the
    // client router routes below it.
    await page.goto(`/app/${view.role}`);

    // Positive first: this waits for the view to render, so the absence checks
    // below are meaningful rather than passing on an unfinished navigation
    // (docs/MISTAKES.md entry 3).
    await expect(page.getByTestId(view.testid)).toBeVisible();

    // The copy, exactly. A heading that reads "Student Dashboard" or "Your
    // Weekly Check-In" is a different product voice, and §4.1 items 4 and 5 are
    // enforced by review until E2's copy inventory — which makes this the only
    // automated reader of these strings until then.
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(view.heading);
    await expect(page.getByText(view.empty, { exact: true })).toBeVisible();

    // Accessibility in-slice: one labelled landmark holding the view, and one
    // first-level heading in it. Two h1s or none is the commonest way a
    // scaffolded page ships, and a screen reader lands on neither.
    await expect(page.getByRole('main')).toBeVisible();
    await expect(page.getByRole('main').getByRole('heading', { level: 1 })).toHaveText(view.heading);
    await expect(page.locator('h1')).toHaveCount(1);

    // Exactly one of the five, so a route that rendered every landing — or the
    // wrong one — fails here rather than passing on the testid it was asked for.
    for (const other of ALL_LANDINGS.filter((testid) => testid !== view.testid)) {
      await expect(page.getByTestId(other)).toHaveCount(0);
    }
  });
}
