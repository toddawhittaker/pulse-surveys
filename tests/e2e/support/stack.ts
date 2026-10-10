// The things a browser cannot do to the Compose stack, and which this suite's
// specs need — SPEC §9.2.
//
// **What is here**, in the order it arrived: the window derivation and the
// database statement E2-10's spec needed, E4-11's weekly-summary walk, E4-15's
// two — the exit story's seeder and the release cutter — E5-10's two, which
// pipe the other two development seeders the repository already ships, and
// E6-01's, which routes seed moderation verdicts through the product's writer,
// and E6-02's, which stops Celery beat so the scheduler cannot race a drive.
// Nine helpers rather than the two this file opened with, so the count is named
// rather than left as prose that goes stale on the next addition
// (`docs/MISTAKES.md` entry 1).
//
// All of them shell out to `docker compose`, which is how this suite's stack is
// brought up in the first place (`README.md`'s local sequence and the `e2e` job
// in `.github/workflows/ci.yml` both run it), so nothing new has to be installed
// for these to work. They run in the process Playwright runs in, from the
// repository root, which is where the compose files are.
//
// **None of these is a shortcut past something the product does.** The window
// derivation below is the *same* task `app.jobs.schedules` runs hourly, invoked
// rather than waited for; the summary walk is the *same* task the beat schedule
// runs hourly at minute 50 (ADR 0188), and the release cut the *same* Monday
// 02:40 task (ADR 0152), each invoked for the same reason; and the query below reads and writes the question set,
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
 * Stop Celery beat, so the scheduler cannot run a job in the middle of a drive.
 *
 * Since ADR 0188 beat runs the summary walk every hour at minute 50 and the
 * moderation sweep every hour at minute 10. A drive seeds responses into weeks
 * whose windows have already closed by the real date, then calls the jobs itself
 * (the helpers below). If beat's walk fires between the two, it stores a
 * summary of a closed week before the drive's responses are in it, and a stored
 * summary is never rewritten, so the report shows a 0-response summary for a week
 * the drive filled. That is the product working as specified and the harness
 * racing the scheduler; CI's e2e run met it at a 05:50 walk. So the drives that
 * seed and run the jobs stop beat first and do all the scheduling themselves.
 *
 * `docker compose stop` on a stopped service succeeds, so calling this from
 * every such spec is safe. **It does not start beat again**: Playwright's global
 * teardown would need `playwright.config.ts`, which this suite does not change
 * for it. On a developer's machine, `make up` (or `docker compose start beat`)
 * brings beat back after an e2e run.
 *
 * A job beat had already enqueued just before the stop still runs in the worker;
 * stopping beat closes the window from then on, not retroactively.
 */
export function stopTheScheduler(): void {
  compose(['stop', 'beat']);
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
 * rather than at the next minute 50.
 *
 * The same shape and the same argument as `deriveSurveyWindows` above: E4-06's
 * job runs on `app.jobs.schedules`'s beat, hourly since ADR 0188, and a spec that
 * needed a summary before its report could not wait for the hour and must not
 * write one.
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

/**
 * Route a `clear` moderation verdict for every comment in the named sections
 * that holds none yet, and answer how many it routed.
 *
 * **Why a drive needs this since E6-01.** `report_comment` v004 shows a comment
 * only once it holds a moderation verdict, and the summary walk does not
 * summarize a section-week until every comment in it holds one. Moderation runs
 * at window close (SPEC §7.4) and its sweep is E6-02's, so a drive that submits
 * comments through the page and reads them back would find none on the report
 * and no summary above it — `docs/MISTAKES.md` entry 22, one layer out.
 *
 * **Through the product's one writer, never a row.** The verdicts go through
 * `app.services.moderation.route_verdict` — the routing definer, which writes the
 * verdict and its route together — under the seed provenance the module defines
 * (`SEED_PROMPT_VERSION`, `SEED_MODEL_ID`), so a planted verdict says it is one
 * and is never mistaken for a model's. It runs in the `api` container on the
 * application's own connection, which is also what proves the grant
 * (`docs/MISTAKES.md` entry 46). A blank comment is left alone: the view does not
 * show one, so nothing waits for it.
 *
 * The count is the control: the caller compares it with the comments it typed.
 */
export function routeSeedVerdictsFor(codes: readonly string[]): number {
  const program = [
    'import json',
    'from sqlalchemy import text',
    'from app.ai.contracts import ModerationVerdict',
    'from app.db import SessionLocal',
    'from app.services.moderation import SEED_MODEL_ID, SEED_PROMPT_VERSION, route_verdict',
    `codes = json.loads(${JSON.stringify(JSON.stringify(codes))})`,
    'waiting = text(',
    '    "select a.id from answer a "',
    '    "join response r on r.id = a.response_id "',
    '    "join section s on s.id = r.section_id "',
    '    "where s.lms_section_code = any(:codes) "',
    '    "and a.comment_text is not null and btrim(a.comment_text) <> \'\' "',
    '    "and not exists (select 1 from classification c "',
    '    "where c.answer_id = a.id and c.task = \'MODERATION\')"',
    ')',
    'with SessionLocal() as session:',
    '    answers = list(session.execute(waiting, {"codes": codes}).scalars())',
    '    for answer_id in answers:',
    '        route_verdict(session, answer_id, ModerationVerdict.CLEAR,',
    '                      prompt_version=SEED_PROMPT_VERSION, model_id=SEED_MODEL_ID)',
    '    session.commit()',
    'print(len(answers))',
  ].join('\n');
  const printed = compose(['exec', '-T', 'api', 'python', '-'], program).trim().split('\n');
  return Number(printed[printed.length - 1]);
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

/** Where E5-12's prior-term seeder lives, relative to the repository root. */
export const BENCHMARK_HISTORY_SEEDER = 'scripts/seed_benchmark_history.py';

/** Where E4-20's demo story for `BIOL-310-R7FF` lives. */
export const DEMO_STORY_SEEDER = 'scripts/seed_demo_story.py';

/**
 * Pipe one of the repository's development seeders into the `api` container and
 * answer what it printed.
 *
 * `seedTheExitStory` above is this, written out for one file; E5-10 needs two
 * more of them, so the shape is said once rather than three times
 * (`docs/MISTAKES.md` entry 13). **That file is deliberately left holding its
 * own copy**, for the reason `doors.ts` records about the specs it did not
 * refactor: `exit-instructor-report.spec.ts` is the proven-green control for the
 * exit story, and putting a diff on it inside the change that leans on it is
 * what that record declined to do.
 *
 * **Piped rather than executed by path.** `scripts/` is not in the `api` image
 * and `docker-compose.yml` mounts only `scripts/db-init`, so the file is read
 * here — on the host, where the repository is — and handed to `python -` on
 * standard input, which is the currency `databaseStatement` already uses for SQL
 * and `deriveSurveyWindows` for a job.
 *
 * Every seeder reached this way refuses loudly rather than provisioning: none of
 * them creates a section, a person, an enrollment, a week or a window, and each
 * exits non-zero with a sentence naming what is missing. A non-zero exit throws
 * out of `execFileSync`, so a refusal reaches the caller as a failure rather than
 * as an empty world every later absence assertion would be satisfied by
 * (`docs/MISTAKES.md` entry 48).
 */
function pipeTheSeeder(relativePath: string): string {
  const path = resolve(process.cwd(), relativePath);
  let source: string;
  try {
    source = readFileSync(path, 'utf8');
  } catch (unreadable) {
    throw new Error(`${path} could not be read, so no world was seeded from it.`, {
      cause: unreadable,
    });
  }
  return compose(['exec', '-T', 'api', 'python', '-'], source);
}

/**
 * Write E5-12's prior-term world — a term of answers for each of the five
 * sections the mock platform publishes in the term before this one — and answer
 * what the seeder printed.
 *
 * The seeder reads every date it writes off a row and asks the clock nothing, so
 * this is the one step of E5-12's runbook that does not care what the clock says.
 * What it does care about is that the five sections have been launched, their
 * rosters synced and their windows derived, which is the caller's job: see
 * `benchmarkWorld.ts`, which is the only caller and does all of it.
 *
 * **The control is the seeder's own recount**, which counts sections and distinct
 * students per cohort week out of the database and compares them against the
 * configured minimums. `benchmarkWorld.ts` requires its verdict sentence, so a
 * run that wrote a world too thin to demonstrate anything is a failure there
 * rather than a report full of suppression notices three assertions later.
 */
export function seedThePriorTermBenchmarks(): string {
  return pipeTheSeeder(BENCHMARK_HISTORY_SEEDER);
}

/**
 * Write E4-20's demo story into `BIOL-310-R7FF` — twenty students answering
 * every week of that section whose window has closed — and answer what it
 * printed.
 *
 * **This is the hero section's own weeks, and a benchmark drive needs them.** A
 * section with no responses of its own draws no line of its own, so a report of
 * it could show two comparison lines and no third: the thing E5-10's first
 * criterion is about would be missing the line it is a comparison *to*.
 *
 * The seeder writes a response for every week whose window has closed **at the
 * effective clock**, and refuses when none has, so the caller moves the clock
 * forward before this runs. It is deterministic per section label and course
 * week and idempotent by natural key.
 */
export function seedTheDemoStory(): string {
  return pipeTheSeeder(DEMO_STORY_SEEDER);
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
