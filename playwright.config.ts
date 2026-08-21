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

  // One retry so `trace: 'on-first-retry'` has a retry to capture; a flaky
  // network hiccup against the local stack gets one more chance, a real failure
  // still fails.
  retries: process.env.CI ? 1 : 0,

  // The whole run and each expectation get finite, generous budgets. A hung
  // door fails loudly instead of holding the pipeline open.
  timeout: 30_000,
  expect: { timeout: 10_000 },

  // The HTML report lands where the CI job already uploads its artifact from.
  reporter: [['html', { outputFolder: 'playwright-report', open: 'never' }], ['list']],

  use: {
    baseURL: 'http://localhost:8000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
