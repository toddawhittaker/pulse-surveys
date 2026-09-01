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

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
