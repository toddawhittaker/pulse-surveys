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

  // Three projects, and the last two exist to run last, in that order (E3-08,
  // then E4-15).
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
  // `tests/e2e/exit-instructor-report.spec.ts` drives §14.3's exit proof for E4
  // and is lifted out for the same reason and one more of its own: it writes a
  // whole term of responses into `BIOL-215-R3WW`, having first put that section's
  // own ground back, so `instructor-report.spec.ts` reading the same section
  // afterwards would read this file's story instead of its own. It goes last of
  // all — after `grade-passback-exit`, because the E3 exit amends two rosters this
  // one must not meet half-applied.
  //
  // **`testIgnore` on the main project is by filename and has to name both**, which
  // is why it is a list rather than one pattern: six other `exit-*.spec.ts` files
  // run in the main project quite deliberately, so nothing about the `exit-` prefix
  // lifts a file out on its own. A file left off this list is collected into
  // `chromium` as well and runs twice — once in the wrong order.
  //
  // `dependencies` is a project-level ordering and not a fixture: Playwright runs
  // `chromium` to completion first, and skips a project whose dependency failed.
  // That is the wanted behaviour — a drive over a stack whose earlier specs did
  // not pass is measuring something else — and it is also why the ordering claim
  // is only proven by running the whole suite rather than one file alone.
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
      testIgnore: [/exit-grade-passback\.spec\.ts$/, /exit-instructor-report\.spec\.ts$/],
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
    {
      name: 'instructor-report-exit',
      use: { ...devices['Desktop Chrome'] },
      testMatch: /exit-instructor-report\.spec\.ts$/,
      // Both, and the second one is the ordering that matters: `chromium` alone
      // would let this project start beside `grade-passback-exit`, which moves the
      // one shared clock this stack has.
      dependencies: ['chromium', 'grade-passback-exit'],
      // The same 60s and the same kind of reason: this file's hooks and cases wait
      // on a roster sync, a seeder run and the two Monday jobs, each a
      // `docker compose` round trip. The file sets its own, larger, per-case
      // budgets on top of this; this is what covers the hooks.
      timeout: 60_000,
    },
  ],
});
