// The things a browser cannot do to the Compose stack, and which this suite's
// specs need — SPEC §9.2.
//
// **What is here**, in the order it arrived: the window derivation and the
// database statement E2-10's spec needed, E4-11's weekly-summary walk, and
// E4-15's two — the exit story's seeder and the release cutter. Five helpers
// rather than the two this file opened with, so the count is named rather than
// left as prose that goes stale on the next addition (`docs/MISTAKES.md`
// entry 1).
//
// All of them shell out to `docker compose`, which is how this suite's stack is
// brought up in the first place (`README.md`'s local sequence and the `e2e` job
// in `.github/workflows/ci.yml` both run it), so nothing new has to be installed
// for these to work. They run in the process Playwright runs in, from the
// repository root, which is where the compose files are.
//
// **None of these is a shortcut past something the product does.** The window
// derivation below is the *same* task `app.jobs.schedules` runs hourly, invoked
// rather than waited for; the summary walk and the release cut are the *same*
// two Monday tasks the beat schedule runs at 02:50 and 02:40 (ADR 0152), invoked
// for the same reason; and the query below reads and writes the question set,
// which is the instrument SPEC §3.2 stores in a table precisely so that it can
// be changed without a deploy. A spec that faked any of them would be asserting
// against its own fixture (`docs/MISTAKES.md` entry 30).
//
// **The one helper that does write rows says so in as many words.**
// `seedTheExitStory` runs a development-only seeder, and what it writes is a
// *world* — responses, answers and validity verdicts, the inputs a report is a
// report *of*. It deliberately writes no `weekly_summary` and no
// `release_batch`: those two are the only things on E4-15's report that nothing
// but a job can produce, so a fixture that wrote them would be a drive agreeing
// with itself about its own subject (`docs/MISTAKES.md` entry 30 again, and
// E4-15's work order decision 2 states the same rule from the seeder's side).
//
// **New machinery ships with a control that must be green** (`doors.ts`'s rule,
// and `docs/MISTAKES.md` entry 3). Neither of E4-15's two helpers is believed on
// the strength of reading it:
//
//   - `seedTheExitStory` is controlled by the per-week response counts
//     `exit-instructor-report.spec.ts` reads back out of Pulse's own database
//     before it trusts anything rendered. A seeder that ran and wrote nothing, or
//     that refused and left the section empty, is a named failure there — rather
//     than an empty report every absence assertion later in the file would be
//     vacuously satisfied by (`docs/MISTAKES.md` entry 48's rule: check the
//     fixture reached the product's own database).
//   - `cutReleaseBatches` is controlled by the `release_batch_member` count the
//     same spec reads back before it asserts anything about a released comment.
//     A cutter that ran and cut nothing and a read path that dropped the release
//     leave the same empty list, and only that count tells them apart.

import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

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
 * A section provisioned by a launch — which is how the mock platform's four
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
 * Write §5.1's per-stream summaries for every closed week that has none, now
 * rather than on Monday at 02:50.
 *
 * The same shape and the same argument as `deriveSurveyWindows` above: E4-06's
 * job runs on `app.jobs.schedules`'s weekly beat, and a spec that needed a
 * summary before its report could not wait for Monday and must not write one.
 * SPEC §5.1 makes a summary a model output with a prompt version and a model id
 * behind it — a hand-written row would be a spec agreeing with its own fixture
 * about the one thing on the report nothing else can produce.
 *
 * So the real task is called, in the `api` container, where the application, its
 * configuration and its provider settings already are. On the development stack
 * that provider is the mock model service, which is the same one the submit path
 * classifies through.
 */
export function generateWeeklySummaries(): void {
  compose([
    'exec',
    '-T',
    'api',
    'python',
    '-c',
    'from app.jobs.tasks import generate_weekly_summaries; print(generate_weekly_summaries())',
  ]);
}

/**
 * Cut the release batches SPEC §4's cumulative rule is due, now rather than on
 * Monday at 02:40.
 *
 * The same shape and the same argument as the two helpers above. ADR 0152 puts
 * the crossing in a scheduled task of its own — deliberately not in the summary
 * job beside it — and makes `cut_due_release_batches` the one writer of
 * `release_batch` and `release_batch_member`. A spec that needed a release before
 * its report could not wait for Monday and must not write the two rows itself:
 * the batch *is* the decision (ADR 0152's consequences), so a hand-written batch
 * is a drive asserting that its own fixture crossed a threshold.
 *
 * Whether anything is cut is the task's own three-legged judgement, not this
 * helper's: a world that does not meet all three legs is answered with no batch,
 * which is why the caller reads `release_batch_member` back rather than assuming
 * the call did something.
 */
export function cutReleaseBatches(): void {
  compose([
    'exec',
    '-T',
    'api',
    'python',
    '-c',
    'from app.jobs.tasks import cut_release_batches; print(cut_release_batches())',
  ]);
}

/** Where E4-15's story seeder lives, relative to the repository root. */
export const EXIT_STORY_SEEDER = 'scripts/seed_exit_story.py';

/**
 * Write E4-15's diverging two-stream story into `BIOL-215-R3WW`, and answer what
 * the seeder printed.
 *
 * **Piped rather than mounted, and that is the whole reason this helper is not a
 * one-line `compose` call.** `scripts/` is not in the `api` image and
 * `docker-compose.yml` mounts only `scripts/db-init`, so the file cannot be
 * executed inside the container by path. It is read here — on the host, where the
 * repository is — and handed to `python -` on standard input, which is the same
 * currency `databaseStatement` already uses for SQL and `deriveSurveyWindows` for
 * a job. The alternative, a development HTTP control for the seeder, is rejected
 * in E4-15's work order (decision 3): more attack surface and a wider diff for no
 * capability this suite lacks.
 *
 * **No arguments, by decision.** The story is one section's and the seeder
 * hardcodes it, so there is no spelling of a section, a week or a respondent for
 * this file to hold a second copy of.
 *
 * The seeder is expected to refuse loudly rather than provision: it creates no
 * section, person, user, enrollment, week or window, and exits non-zero with a
 * plain message when any of them is missing. Provisioning is the caller's job,
 * done before this runs — which is the whole of `docs/MISTAKES.md` entry 48's
 * rule, enforced by the seeder rather than trusted.
 */
export function seedTheExitStory(): string {
  const path = resolve(process.cwd(), EXIT_STORY_SEEDER);
  let source: string;
  try {
    source = readFileSync(path, 'utf8');
  } catch (unreadable) {
    // The original error is attached as `cause` rather than only described: a
    // missing file and a file the process may not read are two different repairs,
    // and only the caught error's own code tells them apart.
    throw new Error(
      `${path} could not be read. E4-15 owes it: a self-contained, ` +
        'argument-less, development-guarded writer of the diverging two-stream story for ' +
        'BIOL-215-R3WW, importing only `app.*` and the standard library so that it runs inside ' +
        'the `api` image. It is piped into `docker compose exec -T api python -` because ' +
        '`scripts/` is not in that image.',
      { cause: unreadable },
    );
  }
  return compose(['exec', '-T', 'api', 'python', '-'], source);
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
