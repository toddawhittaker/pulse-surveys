import { defineConfig, devices } from '@playwright/test';

// The end-to-end suite for SPEC §9.2: both entry doors exercised in a real
// browser against a running, seeded Compose stack. The stack is brought up
// separately (docker compose up + migrate + seed), so there is deliberately no
// `webServer` block here — this config only points a browser at services that
// are already listening.
//
// Horizons (docker-compose.override.yml publishes these host ports):
//   - the tool itself      -> http://localhost:8000  (baseURL, below)
//   - the mock LMS door     -> http://localhost:8080  (specs reach it by absolute URL)
//   - the mock IdP door     -> http://localhost:8081  (specs reach it by absolute URL)
// Only the tool is the baseURL; the mocks are cross-origin and named in the specs.

export default defineConfig({
  testDir: './tests/e2e',

  // `forbidOnly` on CI turns a stray `test.only` — which silently narrows the
  // suite to one case — into a failure rather than a green run over one test.
  forbidOnly: !!process.env.CI,

  // No retries, anywhere (E0-40 decision 3). A spec that failed once and passed
  // on a second attempt exited zero, so the e2e gate reported success over a
  // test that failed — CLAUDE.md's rule against marking a test flaky to make CI
  // pass, reached through a configuration option instead of a marker and applied
  // to every spec at once. The debugging artifact the retry was buying is kept
  // by the trace setting below, which no longer needs one.
  retries: 0,

  // One worker, because the stack these specs drive has one clock (E2-06).
  // `dev-clock.spec.ts` and `window-scheduling.spec.ts` both write the single
  // `clock_override` row, and the first of them *clears* it — at the start of its
  // test and again in its `finally` — so run in parallel each would read a clock
  // the other had moved. The failure that produces is the worst kind: it lands in
  // whichever spec lost the race, points at the door that spec is about, and does
  // not reproduce when that spec is run alone. It is pinned here rather than
  // worked around in a spec because the shared thing is the composed stack, which
  // no spec owns.
  workers: 1,

  // The whole run and each expectation get finite, generous budgets. A hung
  // door fails loudly instead of holding the pipeline open.
  timeout: 30_000,
  expect: { timeout: 10_000 },

  // The HTML report lands where the CI job already uploads its artifact from.
  reporter: [['html', { outputFolder: 'playwright-report', open: 'never' }], ['list']],

  use: {
    baseURL: 'http://localhost:8000',
    // Kept for the run that failed rather than for a second attempt: with no
    // retries there is never a second attempt, so a mode that waits for one
    // would quietly stop producing traces altogether.
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },

  // Two projects, and the second one exists to run last (E3-08).
  //
  // `tests/e2e/exit-grade-passback.spec.ts` drives SPEC §14.3's exit proof for E3
  // across six weeks of pretended time and amends two of the mock platform's
  // rosters on the way — it drops the learner from `MATH-140-E1FF` and adds a
  // member to `NURS-8100-Q2FF`, neither of which this stack can undo. A spec that
  // ran after it would fail pointing at its own subject: a door, a window or a
  // survey, reading a world some other file had moved. So it is lifted out of the
  // main project, which ignores it, and into one that `dependencies` orders after
  // every other spec has finished.
  //
  // `dependencies` is a project-level ordering and not a fixture: Playwright runs
  // `chromium` to completion first, and skips this project if it failed. That is
  // the wanted behaviour — a drive over a stack whose earlier specs did not pass
  // is measuring something else — and it is also why the ordering claim is only
  // proven by running the whole suite rather than this file alone.
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
      testIgnore: /exit-grade-passback\.spec\.ts$/,
    },
    {
      name: 'grade-passback-exit',
      use: { ...devices['Desktop Chrome'] },
      testMatch: /exit-grade-passback\.spec\.ts$/,
      dependencies: ['chromium'],
      // Longer than the suite's 30s, because each case here waits on two
      // asynchronous halves the other specs never touch: the worker creating a
      // section's AGS line item after a staff launch, and the participation sweep
      // being re-triggered until it has one to post to. The file sets its own
      // per-case budget on top of this; this is what covers the hooks.
      timeout: 60_000,
    },
  ],
});
