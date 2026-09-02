// Two things a browser cannot do to the Compose stack, and which E2-10's spec
// needs — SPEC §9.2.
//
// Both shell out to `docker compose`, which is how this suite's stack is
// brought up in the first place (`README.md`'s local sequence and the `e2e` job
// in `.github/workflows/ci.yml` both run it), so nothing new has to be installed
// for these to work. They run in the process Playwright runs in, from the
// repository root, which is where the compose files are.
//
// **Neither of these is a shortcut past something the product does.** The window
// derivation below is the *same* task `app.jobs.schedules` runs hourly, invoked
// rather than waited for; the query below reads and writes the question set,
// which is the instrument SPEC §3.2 stores in a table precisely so that it can
// be changed without a deploy. A spec that faked either would be asserting
// against its own fixture (`docs/MISTAKES.md` entry 30).

import { execFileSync } from 'node:child_process';

/** How long either command may take before it is a stack that is not answering. */
const COMMAND_TIMEOUT_MS = 60_000;

/** Run one `docker compose` invocation and answer its standard output. */
function compose(args: string[], input?: string): string {
  return execFileSync('docker', ['compose', ...args], {
    cwd: process.cwd(),
    encoding: 'utf8',
    input,
    timeout: COMMAND_TIMEOUT_MS,
    stdio: ['pipe', 'pipe', 'pipe'],
  });
}

/**
 * Derive every section's survey windows, now rather than on the hour.
 *
 * A section provisioned by a launch — which is how the mock platform's three
 * contexts reach this database at all — has no `survey_window` rows until
 * `app.jobs.tasks.derive_survey_windows` next runs, and
 * `app.jobs.schedules` runs it on `crontab(minute="30")`. A spec cannot wait up
 * to an hour, and it must not invent the rows either: what the student's read
 * path answers is exactly the set of materialized windows (ADR 0111), so a
 * hand-written row would be a spec agreeing with itself about the rhythm.
 *
 * So the real task is called, in the `api` container, where the application and
 * its configuration already are. `scripts/seed.py` calls the same service for
 * the same reason after it creates the demo institution's sections.
 */
export function deriveSurveyWindows(): void {
  compose([
    'exec',
    '-T',
    'api',
    'python',
    '-c',
    'from app.jobs.tasks import derive_survey_windows; derive_survey_windows()',
  ]);
}

/**
 * Run one statement against the stack's database and answer its rows, unaligned.
 *
 * Inside the `db` container as its own superuser, so no credential from `.env`
 * reaches this process or this file. `ON_ERROR_STOP` makes a failing statement a
 * non-zero exit rather than a message on standard error and a green run —
 * `docs/MISTAKES.md` entry 34's shape, one layer down.
 *
 * The statement is passed on standard input rather than as an argument, so a
 * value carrying a quote is the shell's problem in neither direction.
 */
export function databaseStatement(sql: string): string {
  const out = compose(
    [
      'exec',
      '-T',
      'db',
      'sh',
      '-c',
      'psql --quiet --no-align --tuples-only --set ON_ERROR_STOP=1 ' +
        '--username "$POSTGRES_USER" --dbname "$POSTGRES_DB"',
    ],
    sql,
  );
  return out.trim();
}
