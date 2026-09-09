// E4-15, criterion 1 — SPEC §14.3, E4's exit line: "an instructor opens a real
// Monday report for a seeded section with a diverging two-stream story."
//
// **This file drives that clause against the running stack.** The section is
// provisioned by a real staff launch, its roster is read by the real sync, its
// windows are materialized by the real job, its responses are written by the
// development seeder E4-15 adds, its summaries come from the real Monday summary
// walk and its release from the real Monday cutter — and every assertion below is
// made against what the instructor's own page and the instructor's own payload
// answer. Nothing here is a unit test with a browser attached, and nothing here
// asserts the absence of an error.
//
// **What it asserts, clause by clause of SPEC §5.1**, which is the substance
// criterion 1 asks for:
//
//   - **the diverging pair** — the instructor stream's weekly means rise strictly
//     across six course weeks while the course stream's fall strictly, in the
//     payload the chart is drawn from, and the stacked pair renders both panels;
//   - **both comment groups led by their own summary, each stating its response
//     count** — §5.1's grouping rule and its "state the response count they draw
//     from" clause, in the payload and in the reading order of the page;
//   - **small-N concealment** — a week of four responses declares itself
//     suppressed, hands back no comment in either stream, renders no comment card
//     and carries none of the seven withheld sentences *anywhere in its response
//     body*, while an eight-response week of the same section shows its raw
//     comments. Both halves, because a payload that hid everything would satisfy
//     the first alone;
//   - **the cumulative batched release** (§4, ADR 0152, ADR 0153) — seven held
//     comments from two disjoint quiet weeks reach the latest published week's
//     report with no week attribution on any of them, while the quiet week's own
//     report stays empty after the release exists;
//   - **week navigation across published weeks** — every published week the API
//     names is reachable by paging back from the latest, the address carries the
//     week, and the heading takes focus;
//   - **the two rates** — a response rate of eight over ten, and a validity rate
//     that moves with the one comment whose stored verdict refuses it.
//
// **Every asserted figure is hand-computed from the story plan, with the
// arithmetic beside it** (`docs/MISTAKES.md` entry 19). The plan is E4-15's work
// order decision 5 and it is transcribed into `STORY` below; the section's two
// week axes are transcribed from `scripts/seed.py`'s start-letter map the way
// `instructor-report.spec.ts` and `exit-grade-passback.spec.ts` transcribe them.
// No expectation here is read out of `app.services.reporting`, out of a view, or
// out of anything else the implementation produces.
//
// **THIS SPEC MOVES THE CLOCK ACROSS SIX WEEKS AND WRITES A TERM OF RESPONSES
// INTO ONE SECTION.** It must not run in the main Playwright project. E4-15's
// work order puts it in an `instructor-report-exit` project of its own, ordered
// after both the main project and `grade-passback-exit` by `dependencies` — after
// the E3 exit because that drive amends two rosters this one must not meet
// half-applied, and after the main project because the seeder deletes every
// response `BIOL-215-R3WW` holds, `instructor-report.spec.ts`'s among them. The
// ordering claim is only ever proven by a run of the whole suite.
//
// **What this file can put back, and what it cannot.** The clock, in an
// `afterAll` inside a `finally` — the E3 exit's shape, and for its reason. The
// story's rows are deliberately left: the seeder is idempotent by clearing this
// section's own ground before it writes, so a re-run re-seeds rather than
// doubling, and nothing runs after this project. What no hook can put back is
// `enrollment.started_on`: the roster sync writes it from the effective clock and
// nothing may rewrite it, so a suite re-run against a stack whose clock has been
// moved needs the database rebuilt (`make down && make up && make migrate &&
// make seed`). That is already true of this suite before this file — the E3 exit
// drive syncs three rosters on a pretended September clock — and this drive adds
// nothing to it, because its own staff launches happen at the real clock and its
// only sync runs there too. It is written here because this is the last file in
// the run and the last place anybody reads before rebuilding.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect, type Locator, type Page } from '@playwright/test';

import { clearTheClock, setTheClockTo } from './support/clock';
import {
  DEV_CONSOLE_PATH,
  launchAs,
  placementInto,
  sessionToken,
} from './support/doors';
import {
  cutReleaseBatches,
  databaseStatement,
  deriveSurveyWindows,
  generateWeeklySummaries,
  seedTheExitStory,
} from './support/stack';
import { INSTRUCTOR_SUBJECT, LEARNER_SUBJECT } from './support/survey';

// ---------------------------------------------------------------------------
// The world, transcribed from `mock-lms/app/seed.py` and `scripts/seed.py`.
// ---------------------------------------------------------------------------

// **The story's section is `BIOL-215-R3WW`, and the choice is measured rather
// than preferred** (E4-15's work order decision 1). The mock platform's three
// contexts are the only launchable sections. `NURS-8100-Q2FF` collides with the
// two student-survey specs, which are written against a screen with one open
// section on it. `MATH-140-E1FF` loses its learner to the E3 exit drive's roster
// drop, which runs immediately before this project. `BIOL-215-R3WW` receives no
// runtime roster amendment from any spec: its late add and its drop are seeded
// facts, not amendments.
const BIOL = {
  label: 'BIOL-215-R3WW',
  code: 'R3WW',
  course: 'BIOL 215',
  lengthWeeks: 12,
};

/** One per-section student's `sub`, as `mock-lms/app/seed.py::student` mints it. */
function student(ordinal: number): string {
  return `mock-lms-user-${BIOL.label.toLowerCase()}-student-${String(ordinal).padStart(2, '0')}`;
}

// **The nine stable day-one members, and the two the story never uses.**
// `with_the_add_and_the_drop` makes ordinal 4 a late add dated 2026-09-28 and
// ordinal 7 a member the platform already reports departed — whom Pulse never
// enrolls at all (ADR 0095). A story that put a respondent on either would be
// resting on E0-28's enrollment edge cases, which are the E3 exit's subject and
// not this one's.
const RESPONDENTS = [
  LEARNER_SUBJECT,
  student(1),
  student(2),
  student(3),
  student(5),
  student(6),
  student(8),
  student(9),
  student(10),
];

// ---------------------------------------------------------------------------
// The two week axes, and the clock.
// ---------------------------------------------------------------------------
//
// `scripts/seed.py::START_LETTER_MAP` gives start letter `R` twelve weeks from
// Monday 2026-09-07, and Fall 2026's term week 1 begins Monday 2026-08-17. So:
//
//   term week 1  08-17   term week 4  09-07 = BIOL course week 1
//   term week 2  08-24   term week 5  09-14 = BIOL course week 2
//   term week 3  08-31   term week 6  09-21 = BIOL course week 3
//                        term week 7  09-28 = BIOL course week 4
//                        term week 8  10-05 = BIOL course week 5
//                        term week 9  10-12 = BIOL course week 6
//
// which is the same offset `instructor-report.spec.ts` transcribes from the other
// end: its BIOL course week 4 is term week 7.
//
// SPEC §3.1 opens each week's window on the Friday at 18:00 and shuts it on the
// Sunday at 23:59:59 in the institution's zone, so course week 6's window shuts
// on Sunday 2026-10-18 and course week 7's does not open until Friday 2026-10-23.
// Monday 2026-10-19 at 09:00 is therefore the first Monday on which course weeks
// 1 to 6 are all published and week 7 is not — which is the Monday §5.1's report
// is *for*, and the one moment this drive stands at.
//
// **ADR 0142 before any of this arithmetic, and here is what it changes.** The
// windows are derived from the section's calendar and are stored; the effective
// clock decides only which of them have *closed*. Nothing below compares a
// response's own timestamp to anything: the seeder's rows carry a real-time
// server default `created_at`, and no figure this drive asserts reads it.
const TERM_WEEK_OF_COURSE_WEEK: Record<number, number> = {
  1: 4,
  2: 5,
  3: 6,
  4: 7,
  5: 8,
  6: 9,
};
const THE_MONDAY_AFTER_WEEK_SIX = '2026-10-19T09:00';
const LATEST_PUBLISHED_WEEK = 6;
const EVERY_PUBLISHED_WEEK = [1, 2, 3, 4, 5, 6];
const AN_UNPUBLISHED_WEEK = 7;

// SPEC §4's threshold, as `.env`'s `N_THRESHOLD_DEFAULT` and
// `app.config.Settings.n_threshold_default` both set it. Written out rather than
// read from either, so this file is not agreeing with the configuration about
// what the configuration is.
const N_THRESHOLD = 5;

// ADR 0152's leg (c): a batch draws from at least this many distinct
// under-threshold closed weeks (`WEEKS_A_RELEASE_MUST_SPAN`). The story's two
// quiet weeks are exactly that floor, which is why their respondent sets are
// disjoint — see `STORY`.
const WEEKS_A_RELEASE_MUST_SPAN = 2;

// ---------------------------------------------------------------------------
// The story plan — E4-15's work order decision 5, transcribed.
// ---------------------------------------------------------------------------
//
// **This table is the contract `scripts/seed_exit_story.py` and this file both
// implement.** The respondent counts and the two rating sums are fixed by the
// work order so that both sides agree without either reading the other; which
// student gives which rating inside a week is the seeder's business.
//
// Every mean below is `sum / respondents`, computed here by hand and written out
// as a literal (`docs/MISTAKES.md` entry 19):
//
//   week 1   instructor 16 / 8 = 2.0      course 36 / 8 = 4.5
//   week 2   instructor 20 / 8 = 2.5      course 34 / 8 = 4.25
//   week 3   instructor 12 / 4 = 3.0      course 14 / 4 = 3.5
//   week 4   instructor 10 / 3 = 3.3333…  course  9 / 3 = 3.0
//   week 5   instructor 32 / 8 = 4.0      course 20 / 8 = 2.5
//   week 6   instructor 36 / 8 = 4.5      course 16 / 8 = 2.0
//
// Every sum is reachable from its count with integer ratings 1 to 5 — week 1's
// instructor sum is eight 2s, its course sum four 5s and four 4s, and so on — so
// no row of this table asks the seeder for a rating the survey does not have.
// Only week 4's two means are not exact in binary, which is why the payload
// comparisons below are `toBeCloseTo`.
//
// **Weeks 3 and 4 are the quiet pair, and their respondent sets are disjoint.**
// Four respondents and three, both under the threshold of five, sharing nobody —
// so the comments they hold carry seven distinct authors across two distinct
// closed under-threshold weeks, which is what opens all three legs of ADR 0152's
// release gate at once. A pair that overlapped would fail leg (b) with the same
// two weeks and the same seven comments.
const STORY = [
  { courseWeek: 1, respondents: 8, instructorMean: 2.0, courseMean: 4.5 },
  { courseWeek: 2, respondents: 8, instructorMean: 2.5, courseMean: 4.25 },
  { courseWeek: 3, respondents: 4, instructorMean: 3.0, courseMean: 3.5 },
  { courseWeek: 4, respondents: 3, instructorMean: 3.3333, courseMean: 3.0 },
  { courseWeek: 5, respondents: 8, instructorMean: 4.0, courseMean: 2.5 },
  { courseWeek: 6, respondents: 8, instructorMean: 4.5, courseMean: 2.0 },
];

const QUIET_WEEK = 3;
const THE_OTHER_QUIET_WEEK = 4;

/** One week of the plan, or a failure saying this file's own table is short. */
function planFor(courseWeek: number): (typeof STORY)[number] {
  const found = STORY.find((week) => week.courseWeek === courseWeek);
  expect(
    found,
    `The story plan in this file names no course week ${String(courseWeek)}.`,
  ).toBeDefined();
  return found ?? STORY[0];
}

// ---------------------------------------------------------------------------
// The sentences the story writes. The seeder must write exactly these.
// ---------------------------------------------------------------------------
//
// **These strings are part of the contract, not decoration.** The drive asserts
// that seven of them are withheld from one week's response body and then carried
// by another week's release, and that two more are on the page — so a seeder that
// wrote different words is a red naming the mismatch rather than a silently
// weaker proof.
//
// Every one of them obeys the three rules `instructor-report.spec.ts` states for
// a comment a spec asserts about: comfortably over SPEC §3.3's twenty-five
// character floor, no marker the mock model provider answers to, and no `|` — the
// column separator `databaseStatement`'s rows come back on. Each is distinct
// inside its first forty characters, because the absence check below compares
// forty-character prefixes and a shared prefix would make seven assertions one.
// The whole set was grepped against this repository before it was written: no
// other test, fixture, eval case or seed asserts anything about any of them.

// The four course-stream comments of quiet week 3.
const HELD_IN_WEEK_THREE = [
  'Exit story alpha: the shared lab bench rota left two of us without a slot.',
  'Exit story bravo: the second reading assumed a module I have not taken yet.',
  'Exit story charlie: the recording cut out about twenty minutes into the session.',
  'Exit story delta: nobody replied on the message board and the pair task stalled.',
];

// The three course-stream comments of quiet week 4.
const HELD_IN_WEEK_FOUR = [
  'Exit story echo: the worked example arrived after the exercise was already due.',
  'Exit story foxtrot: the reading list was long and the ordering made it workable.',
  'Exit story golf: two slides disagreed about which deadline actually applies.',
];

const EVERY_HELD_COMMENT = [...HELD_IN_WEEK_THREE, ...HELD_IN_WEEK_FOUR];

// One comment per stream in each of the four weeks at or above the threshold.
const WEEK_SIX_INSTRUCTOR_COMMENT =
  'Exit story week six instructor: office hours ran long and nobody was turned away.';
const WEEK_SIX_COURSE_COMMENT =
  'Exit story week six course: the final project brief arrived far too late to plan.';

// **The one comment whose stored verdict refuses it**, in week 5's course
// stream. Its text is deliberately as substantive as every other sentence here:
// the seeder plants the verdict rather than asking the classifier for it, so what
// the validity rate is a statement about is the *stored* verdict, and a sentence
// chosen to look insufficient would let a reader believe the rate came from the
// words. §3.3's rate is valid responses over responses, and this is the one
// response of week five's eight that is not valid.
const WEEK_FIVE_REFUSED_COMMENT =
  'Exit story week five course: the assessment weighting still is not clear to me.';

// ---------------------------------------------------------------------------
// The expectations, hand-computed.
// ---------------------------------------------------------------------------

// **The enrolled denominator, derived by hand from `mock-lms/app/seed.py`'s
// membership and premise-guarded below rather than trusted.** At this drive's
// clock the section's live members are the learner plus students 01, 02, 03, 04,
// 05, 06, 08, 09 and 10 — ten people. Student 07 is never enrolled in Pulse at
// all, because the platform reports him departed the first time the tool reads
// the roster and ADR 0095 gives such a member no row. Student 04 is a late add
// the platform dates 2026-09-28, which falls inside course week 4 and so well
// before course week 6, and he is therefore in this week's denominator although
// he answers nothing.
//
// **Ten is this week's number and not the section's**, which is worth saying
// because the constant's name is the only thing that says so. SPEC §3.4 starts a
// denominator at the student's first enrolled week from the platform's own
// enrolment data, so student 04 is *outside* the denominator of course weeks 1 to
// 3 and inside it from course week 4 on: the early weeks hold nine. Nothing in
// this file asserts a rate for those weeks — the response rate is read at course
// week 6 and the validity rates at weeks 5 and 6, all of them after his date — so
// no expectation here moves with that rule. A later assertion about an early
// week's response rate divides by nine, and
// `tests/integration/test_the_report_payload_divides_the_rates.py`'s
// `test_a_platform_dated_late_add_is_outside_the_denominator_of_the_weeks_before_him`
// is where the rule itself is held.
const ENROLLED_IN_WEEK_SIX = 10;

// Week 6's response rate: 8 of the section's 10 live members answered.
// 8 / 10 = 0.8. The two who did not are student 04, the late add, and student 10,
// who is in the respondent pool and does not answer this week.
const WEEK_SIX_RESPONSE_RATE = 0.8;

// Week 6's validity rate: all eight of its responses carry substantive comments
// or no comment at all, so 8 / 8 = 1.0.
const WEEK_SIX_VALIDITY_RATE = 1.0;

// Week 5's validity rate: one of its eight responses holds the refused comment
// above, so seven are valid and 7 / 8 = 0.875. **This is the half of the pair
// that moves.** Week 6's 1.0 is what a rate hard-coded to one, or computed over
// the enrolment, or divided the wrong way round would also produce; only a week
// whose answer is neither 1 nor 0 tells those apart, and 0.875 is exact in binary
// so nothing here turns on a float's spelling.
const WEEK_FIVE_VALIDITY_RATE = 0.875;
const WEEK_FIVE_VALID_RESPONSES = 7;

// Week 6's workload figures, over the hours the plan gives its eight
// respondents — 6, 7, 8, 9, 10, 11, 12 and 20. Sum 83, so the mean is
// 83 / 8 = 10.375; sorted, the two middle values are 9 and 10, so the median is
// (9 + 10) / 2 = 9.5. **Chosen so the mean and the median are different
// numbers**, which is what makes a payload that served one in the other's place
// red rather than plausible. Both are exact in binary. Every value is inside SPEC
// §3.2's 0-to-40 range in half-hour steps.
const WEEK_SIX_WORKLOAD_MEAN = 10.375;
const WEEK_SIX_WORKLOAD_MEDIAN = 9.5;

// How many comments the release carries: the seven held ones, and no more.
const RELEASED_COMMENTS = 7;

// `ReportComment`'s whole field list, per ADR 0153 — "`ReportComment` has three
// fields — `text`, `status`, `stream` — and is frozen". Asserted as a closed set
// over what the payload hands back rather than as a search for a `week` member,
// because the field that names a week is the one nobody has thought of yet.
const COMMENT_FIELDS = ['status', 'stream', 'text'];

// ---------------------------------------------------------------------------
// The surfaces this drive reads, and the copy it holds as literals.
// ---------------------------------------------------------------------------

// Testids the report surface publishes (E4-11), and the landing a staff launch
// reaches (E0-18).
const INSTRUCTOR_LANDING = 'pulse-landing-instructor';
const REPORT = 'pulse-instructor-report';
const SECTIONS_MENU = 'pulse-instructor-sections';

// E3-08's roster-sync control, on the development console (ADR 0142).
const ROSTER_SYNC_RUN = 'roster-sync-run';

// Governed copy and accessible names, transcribed from
// `instructor-report.spec.ts` — which transcribes them from the copy modules
// E4-12 governs — rather than read off the page. `landing-views.spec.ts` states
// the rule: a spec that asked the page what its own words were would pass against
// any words at all.
const SMALL_N_TITLE = 'Comments are hidden this week';
const COMMENTS_NOTE = 'Shown in random order. No names, no timestamps.';
const INSTRUCTOR_GROUP_HEADING = 'About the instructor';
const COURSE_GROUP_HEADING = 'About the course';
const PREVIOUS_WEEK = 'Previous week';

// The two axis forms SPEC §2.2 requires of a course-level page, in the two
// spellings the epic settled: E4-08's chart axis is "WK 01…" with the quiet
// "TERM 04…" sub-label, and FIX-01's ruling of 2026-09-03 fixes the week
// eyebrow's own wording as `COURSE WK NN / LL, TERM WK NN` (E4-17). Nothing here
// asserts one of them in the other's place.
const FIRST_AXIS_WEEK = 'WK 01';
const FIRST_AXIS_TERM_SUB_LABEL = 'TERM 04';
const EYEBROW_COURSE_WEEK = `COURSE WK 0${String(LATEST_PUBLISHED_WEEK)} / ${String(BIOL.lengthWeeks)},`;
const EYEBROW_TERM_WEEK = `TERM WK 0${String(TERM_WEEK_OF_COURSE_WEEK[LATEST_PUBLISHED_WEEK])}`;

// Budgets. The world is one staff launch, a roster sync, a seeder run, two
// Monday jobs and several `docker compose` round trips; a hook or a case that ran
// out of harness rather than out of patience would read as a flake.
const WORLD_TIMEOUT_MS = 600_000;
const CASE_TIMEOUT_MS = 180_000;
const ROSTER_TIMEOUT_MS = 60_000;
const ROSTER_RETRY_MS = 3_000;

// How far the week walk may step before it is a control that is not stepping.
// Bounded rather than trusted: a `while` over a disabled state is a `while`
// nothing can stop if the state never arrives.
const MAX_WEEK_STEPS = 20;

/** The placement both people launch `BIOL-215-R3WW` through, found in `beforeAll`. */
let placement = '';

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  // **Discovery only.** Everything that writes to the stack is in the first test
  // rather than here, so a tree missing one of E4-15's deliverables reds as a
  // FAILED naming it instead of as an error in a hook — `docs/MISTAKES.md`
  // entry 44's rule, read across to a browser suite. Serial mode then skips the
  // rest of the file, which is the same protection a failing hook would have
  // given and a better report.
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    placement = await placementInto(page, INSTRUCTOR_SUBJECT, BIOL.label);
    const forTheLearner = await placementInto(
      page,
      LEARNER_SUBJECT,
      BIOL.label,
    );
    expect(
      forTheLearner,
      'The mock platform offers the instructor and the learner different resource links into ' +
        `${BIOL.label}. A section is provisioned per resource link, so two links are two sections ` +
        'and this drive would seed a story into one and read a report from the other.',
    ).toBe(placement);
  } finally {
    await context.close();
  }
});

test.afterAll(async ({ browser }) => {
  // The clock is the one piece of shared state this file can put back, and it
  // goes back inside a `finally` so that a failure anywhere above cannot leave
  // the stack standing in October. The story's rows are deliberately left — the
  // seeder clears this section's own ground before it writes, so a re-run
  // re-seeds rather than doubling.
  const context = await browser.newContext();
  try {
    await clearTheClock(await context.newPage());
  } finally {
    await context.close();
  }
});

test('the story reaches Pulse’s own database, and the two Monday jobs run over it', async ({
  page,
}) => {
  // **The world, and the premise every assertion after it rests on.**
  //
  // The order is the whole of what makes this work and none of it is arbitrary:
  //
  //   1. the clock is *cleared* and the staff launch happens at the real now.
  //      `app.services.roster_sync` writes `enrollment.started_on` from the
  //      effective clock when it first sights a member and nothing may rewrite
  //      it, so a sync run while this file pretended it was October would date
  //      every member of this section a month ahead — and a staff launch is what
  //      triggers a sync (SPEC §7.3). `instructor-report.spec.ts` records the
  //      measurement behind that ordering;
  //   2. the windows are materialized, because a section provisioned by a launch
  //      has none until the half-hourly job next runs (ADR 0111);
  //   3. the roster sync is run through the development console, which is the
  //      only way to reach it on demand — the launch trigger debounces against
  //      five *real* minutes (ADR 0142);
  //   4. the roster is waited for **against the database** rather than against a
  //      survey block. The block is the observable `instructor-report.spec.ts`
  //      polls, and it needs an open window, which would force this file to move
  //      the clock before the sync and re-open the hazard step 1 exists to avoid.
  //      What the seeder needs is the enrollment rows, and those are exactly what
  //      is read here;
  //   5. the story is seeded, which refuses loudly if any of the above is missing
  //      rather than provisioning it (`docs/MISTAKES.md` entry 48);
  //   6. only then does the clock move, to the Monday after course week 6's
  //      window shut;
  //   7. and the two Monday jobs run, in the beat's own order — the cutter at
  //      02:40 and the summary walk at 02:50 are two separate tasks by decision
  //      (ADR 0152), and this drive calls both rather than writing either's rows.
  //
  // **The two premise reads at the end are `docs/MISTAKES.md` entry 48's rule
  // applied to this drive's exact shape.** A platform offering a launch says the
  // platform holds the section, never that the tool provisioned it — so the
  // response counts are read back per week out of Pulse's own database and
  // compared against the plan, and the release the cutter wrote is counted there
  // too. Without them, a seeder that refused and a cutter that cut nothing would
  // leave a report every absence assertion in this file is vacuously satisfied by.
  //
  // **The mutations this test kills:** a seeder that exits zero without writing;
  // a seeder that writes the plan's rows into the wrong weeks (the counts are
  // asserted per week, not in total, so a story shifted by one week is red); a
  // seeder that does not clear the section's existing responses, which
  // `instructor-report.spec.ts` leaves five of in course week 4; and a cutter
  // that ran and cut no batch. **The near miss it must survive:** a seeder that
  // writes the right number of responses in the right weeks and nothing else —
  // which this test does not catch and does not claim to, and which the comment,
  // rate and release assertions below are what reach.
  test.setTimeout(WORLD_TIMEOUT_MS);

  await clearTheClock(page);

  await launchAs(page, INSTRUCTOR_SUBJECT, placement);
  await expect(
    page.getByTestId(INSTRUCTOR_LANDING),
    'The staff launch into BIOL-215-R3WW did not land, so nothing was provisioned: no section, no ' +
      'roster address for the sync to discover, and no world for the seeder to refuse to invent.',
  ).toBeVisible();

  deriveSurveyWindows();

  await page.goto(DEV_CONSOLE_PATH);
  const syncControl = page.getByTestId(ROSTER_SYNC_RUN);
  await expect(
    syncControl,
    `The development console carries no element with \`data-testid="${ROSTER_SYNC_RUN}"\`. ADR ` +
      '0142 ships it as the only way to run a roster sync on demand — the launch trigger debounces ' +
      'against five real minutes, which a drive cannot wait out.',
  ).toBeVisible();
  await syncControl.click();
  await expect(page).toHaveURL(new RegExp(`${DEV_CONSOLE_PATH}/?$`));

  await waitForTheRosterInTheDatabase();

  const seeded = seedTheExitStory();
  expect(
    seeded.trim(),
    'The story seeder printed nothing. E4-15 makes it print a one-line completion summary of what ' +
      'it wrote, which is the only thing distinguishing a run that wrote the story from a process ' +
      'that started and exited.',
  ).not.toBe('');

  await setTheClockTo(page, THE_MONDAY_AFTER_WEEK_SIX);

  generateWeeklySummaries();
  cutReleaseBatches();

  // The story, counted per week on the Pulse side.
  const stored = responsesByCourseWeek();
  const expected = new Map(
    STORY.map((week): [number, number] => [week.courseWeek, week.respondents]),
  );
  expect(
    stored,
    'The responses `BIOL-215-R3WW` holds in Pulse’s own database are not the story plan. Read as ' +
      'a map of course week to response count, the plan is ' +
      `${JSON.stringify([...expected])} and the database holds ${JSON.stringify([...stored])}.\n\n` +
      'A short or empty map is a seeder that refused, or that wrote into another section, or that ' +
      'did not clear the responses `instructor-report.spec.ts` leaves in course week 4 — and any ' +
      'of the three makes every assertion in this file a statement about a report of nothing ' +
      '(`docs/MISTAKES.md` entry 48).',
  ).toEqual(expected);

  // The release, counted where the cutter wrote it.
  const released = Number(
    databaseStatement(
      'select count(*) from release_batch_member m ' +
        'join release_batch b on b.id = m.batch_id ' +
        'join section s on s.id = b.section_id ' +
        `where s.lms_section_code = ${quoted(BIOL.code)};`,
    ),
  );
  expect(
    released,
    `The cutter left ${String(released)} release membership rows for ${BIOL.code}, and the story ` +
      `holds ${String(RELEASED_COMMENTS)} comments across course weeks ${String(QUIET_WEEK)} and ` +
      `${String(THE_OTHER_QUIET_WEEK)}, whose respondent sets are disjoint. All three of ADR ` +
      '0152’s legs are open on that world: the term’s cumulative comment volume is fifteen, the ' +
      `held comments carry ${String(RELEASED_COMMENTS)} distinct authors against a threshold of ` +
      `${String(N_THRESHOLD)}, and they span ${String(WEEKS_A_RELEASE_MUST_SPAN)} distinct closed ` +
      'under-threshold weeks.\n\nZero here is the cutter refusing or not having run; it is ' +
      'asserted before the payload so that an empty released list below cannot be read as a read ' +
      'path dropping what the cutter wrote.',
  ).toBe(RELEASED_COMMENTS);
});

test('the two streams diverge across six published weeks, and the stacked pair renders both', async ({
  page,
}) => {
  // **SPEC §14.3's exit clause, and §5.1's stacked pair.** The instructor
  // stream's weekly mean rises strictly while the course stream's falls
  // strictly, over the same six course weeks — which is the whole of what "a
  // diverging two-stream story" is, and the reason the seed had to grow one.
  //
  // Each mean is compared against the literal hand-computed from the plan's own
  // sum and count (see `STORY`), and the monotonicity is asserted separately over
  // the values the payload answered. The second is implied by the first today and
  // is written anyway, because "diverges" is the spec's own clause and a later
  // change to the plan's numbers must not quietly take the clause with it.
  //
  // **The mutations this kills:** a trend that serves one stream's means under
  // both keys (the two sequences would be equal, and each equality would fail
  // against one of them); a trend computed as a running average across weeks (no
  // week's value would match); a mean divided by the *enrolment* rather than by
  // the answered count; and the two streams swapped, which turns a rise into a
  // fall. **The near miss it must survive:** a mean computed over the response
  // count rather than the answered rating count, which weeks 1, 2, 5 and 6 cannot
  // tell apart — every respondent rates both streams there — and which week 4's
  // 3.3333 over three responses would only reveal if a rating were absent. This
  // file does not reach that distinction and does not claim to; it is asserted in
  // `tests/integration/test_the_report_payload_divides_the_rates.py`, whose world
  // plants a response that rates one stream and not the other.
  test.setTimeout(CASE_TIMEOUT_MS);

  const report = await openTheReport(page);
  const payload = await readTheReport(page, LATEST_PUBLISHED_WEEK);

  const instructor = trendMeansOf(payload, 'instructor');
  const course = trendMeansOf(payload, 'course');

  for (const week of STORY) {
    expect(
      instructor.get(week.courseWeek),
      `The instructor stream's trend carries ${String(instructor.get(week.courseWeek))} for course ` +
        `week ${String(week.courseWeek)}; the story plans ${String(week.instructorMean)} there.`,
    ).toBeCloseTo(week.instructorMean, 2);
    expect(
      course.get(week.courseWeek),
      `The course stream's trend carries ${String(course.get(week.courseWeek))} for course week ` +
        `${String(week.courseWeek)}; the story plans ${String(week.courseMean)} there.`,
    ).toBeCloseTo(week.courseMean, 2);
  }

  const instructorSequence = EVERY_PUBLISHED_WEEK.map(
    (week) => instructor.get(week) ?? NaN,
  );
  const courseSequence = EVERY_PUBLISHED_WEEK.map(
    (week) => course.get(week) ?? NaN,
  );
  expect(
    strictlyRising(instructorSequence),
    `The instructor stream's means across course weeks 1 to 6 are ` +
      `${JSON.stringify(instructorSequence)}, which does not rise strictly. SPEC §14.3's exit ` +
      'clause is a section whose two streams diverge, and this is the half that goes up.',
  ).toBe(true);
  expect(
    strictlyRising([...courseSequence].reverse()),
    `The course stream's means across course weeks 1 to 6 are ${JSON.stringify(courseSequence)}, ` +
      'which does not fall strictly. This is the half that goes down, and a story where both ' +
      'streams moved the same way would not be a diverging one.',
  ).toBe(true);

  // The rendered pair: §5.1's two panels, each carrying the accessible table
  // that states its weeks and values as text (E4-08).
  await expect(
    report.getByRole('table'),
    'SPEC §5.1 puts the instructor stream above the course stream as a stacked pair with a shared ' +
      'scale, and E4-08 gives each panel a visually hidden data table so the chart’s data is ' +
      'reachable as text. Two tables is one panel each.',
  ).toHaveCount(2);

  const tables = await report.getByRole('table').allInnerTexts();
  expect(
    tables[0],
    'The two panels’ data tables carry identical text, so both panels are drawn from one stream. ' +
      'The story’s two streams answer six different numbers each, and no week of it gives them the ' +
      'same mean.',
  ).not.toBe(tables[1]);

  // The two axes SPEC §2.2 requires, in the two spellings the epic settled.
  await expect(report).toContainText(FIRST_AXIS_WEEK);
  await expect(report).toContainText(FIRST_AXIS_TERM_SUB_LABEL);
  await expect(page.getByTestId(INSTRUCTOR_LANDING)).toContainText(
    EYEBROW_COURSE_WEEK,
  );
  await expect(page.getByTestId(INSTRUCTOR_LANDING)).toContainText(
    EYEBROW_TERM_WEEK,
  );
});

test('each comment group is led by its own summary, and each summary states its response count', async ({
  page,
}) => {
  // **SPEC §5.1's grouping rule and its counting rule.** De-identified comments
  // are "grouped under 'About the instructor' / 'About the course', each group
  // led by its own AI summary", and the summaries "state the response count they
  // draw from".
  //
  // The count is the *week's* response count and not the number of comments the
  // summary read: week 6 holds eight responses and two comments, one per stream,
  // so the two numbers are eight and one and a payload serving either in the
  // other's place is red. `tests/unit/test_the_weekly_summary_task.py`'s
  // "the stated response count is the caller's and not the number of comments"
  // pins the same distinction one layer down.
  //
  // **"Led by" is asserted as reading order rather than as markup**, because the
  // clause is about what an instructor meets first: the summary's own text
  // appears before that stream's first comment in the page's text. The summary
  // text itself is read off the payload rather than written out here — it is the
  // model's output and this file has no business holding a copy of it — and it is
  // required to be non-empty before it is used as a position, so a blank summary
  // cannot satisfy the ordering by being found at index zero.
  //
  // **The mutations this kills:** a summary rendered after its group's comments,
  // or outside the group entirely; a `response_count` filled with the comment
  // count; a summary generated for one stream only, which the two-sided
  // assertion catches; and a group heading rendered with no summary above it at
  // all. **The near miss it must survive:** a summary whose count is the number
  // of *comments in the whole week* — two — which is neither eight nor one and
  // fails the equality rather than slipping past it.
  test.setTimeout(CASE_TIMEOUT_MS);

  const report = await openTheReport(page);
  const payload = await readTheReport(page, LATEST_PUBLISHED_WEEK);
  const respondents = planFor(LATEST_PUBLISHED_WEEK).respondents;

  await expect(
    report.getByRole('heading', { name: INSTRUCTOR_GROUP_HEADING }),
  ).toBeVisible();
  await expect(
    report.getByRole('heading', { name: COURSE_GROUP_HEADING }),
  ).toBeVisible();
  await expect(report.getByText(COMMENTS_NOTE)).toBeVisible();

  const shown = await report.innerText();
  for (const [stream, leadComment] of [
    ['instructor', WEEK_SIX_INSTRUCTOR_COMMENT],
    ['course', WEEK_SIX_COURSE_COMMENT],
  ] as const) {
    const summary = payload.streams[stream]?.summary;
    expect(
      summary,
      `The week ${String(LATEST_PUBLISHED_WEEK)} payload carries no summary for the ${stream} ` +
        'stream. SPEC §5.1 makes one per stream, and the summary walk this drive ran is what ' +
        'writes it.',
    ).not.toBeNull();
    const text = (summary?.text ?? '').trim();
    expect(
      text.length,
      `The ${stream} summary's text is empty, so the ordering assertion below would be about an ` +
        'empty string and would hold wherever it was rendered.',
    ).toBeGreaterThan(0);
    expect(
      summary?.response_count,
      `The ${stream} summary states a response count of ${String(summary?.response_count)}. Course ` +
        `week ${String(LATEST_PUBLISHED_WEEK)} holds ${String(respondents)} responses and two ` +
        'comments — one per stream — so a count of one or two is the number of comments rather ' +
        'than the number of responses SPEC §5.1 asks the summary to state.',
    ).toBe(respondents);

    const summaryAt = shown.indexOf(text);
    const commentAt = shown.indexOf(leadComment);
    expect(
      summaryAt,
      `The ${stream} summary's text is not on the page, although the payload carries it.`,
    ).toBeGreaterThanOrEqual(0);
    expect(
      commentAt,
      `The ${stream} stream's comment from course week ${String(LATEST_PUBLISHED_WEEK)} is not on ` +
        `the page. The week holds ${String(respondents)} responses against a threshold of ` +
        `${String(N_THRESHOLD)}, so SPEC §4 shows its raw comments.`,
    ).toBeGreaterThanOrEqual(0);
    expect(
      summaryAt,
      `The ${stream} group's comment is rendered before its summary. SPEC §5.1 has each group led ` +
        'by its own summary, which is what makes the summary the thing an instructor reads first ' +
        'rather than a footnote under the comments.',
    ).toBeLessThan(commentAt);
  }
});

test('a quiet week hides its comments in the payload and not only on the page', async ({
  page,
}) => {
  // **SPEC §4's small-N rule, and the trap E4-11's own spec names.** Below the
  // threshold the instructor sees the rating distributions and the summary and no
  // raw comments — so this reads the week's response body itself, through the same
  // route with the same session, and requires the four sentences that week holds
  // and the three the other quiet week holds to be absent from it. A DOM-only
  // assertion passes with the whole set sitting in the network response.
  //
  // **The canary comes first** (`docs/MISTAKES.md` entry 3). A body that is not
  // this week's, or a report of a section with nothing in it, satisfies every
  // absence assertion here perfectly. So the things that must be *present* are
  // asserted before the things that must not: the week is the one asked for, the
  // threshold is five, the week declares itself suppressed, and its course
  // stream's summary is there stating four responses — because §5.1 generates a
  // summary "even in small-N weeks", where "the summary is the only comment
  // signal".
  //
  // **This is one half of a pair.** The other half is the test below, where an
  // eight-response week of the same section shows its raw comments: a payload
  // that suppressed everything would pass this test and fail that one, and
  // neither alone is a statement about the threshold.
  //
  // **And it is the concealment half of the release pair too.** The release has
  // already been cut by the time this runs, so this week's own report is being
  // read *after* its comments went out in a batch — and it still hands back
  // nothing. A read path that filled a week's comment list from the release would
  // pass every assertion in the release test below and fail here.
  //
  // **The mutations this kills:** a suppression applied in the browser rather
  // than in the payload; a suppression that empties the comment list and leaves
  // the words in some other member (the search is over the raw body text at any
  // depth, under any name); a threshold read as "fewer than four" or "five or
  // fewer", either of which would show this week's four; and a quiet week whose
  // own payload serves the release. **The near miss it must survive:** a report
  // that suppresses by returning nothing at all, which the four positive
  // assertions ahead of the absences refuse.
  test.setTimeout(CASE_TIMEOUT_MS);

  const report = await openTheReport(page, QUIET_WEEK);

  // The DOM half.
  await expect(report.getByRole('region', { name: SMALL_N_TITLE })).toHaveCount(
    1,
  );
  await expect(
    report.getByRole('article'),
    'A comment card is in the DOM on a week below the threshold. SPEC §4 hides raw comments below ' +
      `${String(N_THRESHOLD)} responses, and course week ${String(QUIET_WEEK)} holds ` +
      `${String(planFor(QUIET_WEEK).respondents)}.`,
  ).toHaveCount(0);
  for (const withheld of EVERY_HELD_COMMENT) {
    await expect(report.getByText(withheld)).toHaveCount(0);
  }

  // The wire half.
  const { payload, raw } = await readTheReportWithItsBody(page, QUIET_WEEK);

  expect(payload.week.course_week).toBe(QUIET_WEEK);
  expect(payload.small_n.threshold).toBe(N_THRESHOLD);
  expect(
    payload.small_n.suppressed,
    `The payload does not declare course week ${String(QUIET_WEEK)} suppressed. It holds ` +
      `${String(planFor(QUIET_WEEK).respondents)} responses against a threshold of ` +
      `${String(N_THRESHOLD)}.`,
  ).toBe(true);

  const courseSummary = payload.streams.course?.summary;
  expect(
    (courseSummary?.text ?? '').trim().length,
    `Course week ${String(QUIET_WEEK)} has no course-stream summary text. SPEC §5.1 generates a ` +
      'summary even in a small-N week, and says why: there the summary is the only comment signal ' +
      'the instructor gets. A week with no summary and no comments is a suppression that also ' +
      'suppressed the thing §4 promises still reaches them.',
  ).toBeGreaterThan(0);
  expect(
    courseSummary?.response_count,
    `The quiet week's course summary states ${String(courseSummary?.response_count)} responses; ` +
      `the week holds ${String(planFor(QUIET_WEEK).respondents)}.`,
  ).toBe(planFor(QUIET_WEEK).respondents);

  expect(payload.streams.instructor?.comments).toEqual([]);
  expect(payload.streams.course?.comments).toEqual([]);
  expect(
    payload.released_from_earlier_weeks,
    `Course week ${String(QUIET_WEEK)} is not the latest published week, and the release belongs ` +
      'to the latest published week alone (ADR 0152, and E4-07 places it). A release carried by ' +
      'every week would hand these seven comments back under the very week they were held from — ' +
      'which is the week attribution ADR 0153 removes, arriving through the container instead of ' +
      'through a field.',
  ).toEqual([]);

  for (const withheld of EVERY_HELD_COMMENT) {
    expect(
      raw,
      'A comment held from a week below the threshold reached the wire. SPEC §4 hides it in the ' +
        'payload rather than in the browser, and a page that hid it on screen over a response ' +
        `that carried it would leak every word to anybody who opened a network tab. The sentence ` +
        `is ${JSON.stringify(withheld.slice(0, 40))}…`,
    ).not.toContain(withheld.slice(0, 40));
  }
});

test('an above-threshold week of the same section shows its raw comments', async ({
  page,
}) => {
  // **The other half of the small-N pair.** Course week 6 holds eight responses
  // against a threshold of five, so §4 shows its raw comments — and the section,
  // the instructor, the session and the route are the same ones the quiet week
  // was read through. Without this, "no comment appeared" is satisfied by a
  // report that never shows a comment to anybody
  // (`docs/MISTAKES.md` entries 2 and 3).
  //
  // **The mutations this kills:** a threshold comparison inverted, which hides
  // the eight-response week and shows the four; a suppression applied to every
  // week; and a comment list served empty while the summary carries the text.
  test.setTimeout(CASE_TIMEOUT_MS);

  const report = await openTheReport(page);
  const payload = await readTheReport(page, LATEST_PUBLISHED_WEEK);

  expect(
    payload.small_n.suppressed,
    `Course week ${String(LATEST_PUBLISHED_WEEK)} holds ` +
      `${String(planFor(LATEST_PUBLISHED_WEEK).respondents)} responses against a threshold of ` +
      `${String(N_THRESHOLD)}, so it is not a suppressed week.`,
  ).toBe(false);
  expect(payload.streams.instructor?.comments.length).toBeGreaterThan(0);
  expect(payload.streams.course?.comments.length).toBeGreaterThan(0);

  await expect(report.getByText(WEEK_SIX_INSTRUCTOR_COMMENT)).toBeVisible();
  await expect(report.getByText(WEEK_SIX_COURSE_COMMENT)).toBeVisible();
  await expect(report.getByRole('region', { name: SMALL_N_TITLE })).toHaveCount(
    0,
  );
});

test('the cumulative release carries the held comments with no week attribution', async ({
  page,
}) => {
  // **SPEC §4's cumulative rule, as ADR 0152 gates it and ADR 0153 presents it.**
  // Seven comments were held from two disjoint quiet weeks; the crossing has been
  // cut by the real task; and §4's promise is that they "surface as raw text",
  // batched "so that timing cannot identify an author".
  //
  // **Three things are asserted and the third is the one the records rest on.**
  // That the release is carried by the latest published week's report. That it
  // carries all seven sentences. And that **no released comment carries a week in
  // any currency** — asserted as an equality over each comment object's whole
  // field list rather than as a search for a member called `week`, which is ADR
  // 0153's own device and its stated reason: "the absence is structural for that
  // reason, asserted as an equality over the whole field list rather than as a
  // search for a name". A field nobody has thought of yet is exactly what a
  // search for known names cannot find.
  //
  // **This is the crossing half of a boundary pair.** The concealment half is the
  // quiet-week test above, which reads that week's own report after this release
  // exists and finds nothing. Together they say what the two records claim: the
  // comments surface, and they surface detached from the week they came from.
  //
  // **The mutations this kill:** a release cut with the week preserved on the
  // comment (the field-list equality); a release rendered under its week's
  // heading (the quiet-week half); a release carried by every week's payload (the
  // quiet-week half again); a release that goes out with fewer than the whole
  // held set, which the count of seven catches; and a gate that released a single
  // quiet week's comments — four or three rather than seven. **The near miss it
  // must survive:** a release whose comments are present in the payload and
  // absent from the page, which is why the rendered half is asserted beside the
  // payload half.
  test.setTimeout(CASE_TIMEOUT_MS);

  const report = await openTheReport(page);
  const payload = await readTheReport(page, LATEST_PUBLISHED_WEEK);
  const released = payload.released_from_earlier_weeks;

  expect(
    released.length,
    `The latest published week's report carries ${String(released.length)} released comments and ` +
      `the story holds ${String(RELEASED_COMMENTS)} — four from course week ` +
      `${String(QUIET_WEEK)} and three from course week ${String(THE_OTHER_QUIET_WEEK)}, seven ` +
      'distinct authors across two disjoint closed under-threshold weeks. Four or three here ' +
      'would be a batch confined to one week, which ADR 0152’s leg (c) refuses because a ' +
      'one-week batch is the week attribution ADR 0153 removes.',
  ).toBe(RELEASED_COMMENTS);

  // Narrowed rather than stringified: a comment object's `text` arrives as
  // `unknown` off the wire, and `String(…)` on a non-string would turn an object
  // into `[object Object]` and compare that. A `text` that is not a string is not
  // one of the seven sentences, so it takes the empty string and fails the
  // membership assertion below by name.
  const texts = released.map((comment) =>
    typeof comment.text === 'string' ? comment.text : '',
  );
  for (const held of EVERY_HELD_COMMENT) {
    expect(
      texts,
      `The release does not carry ${JSON.stringify(held.slice(0, 40))}…, which was held from a ` +
        'week below the threshold. SPEC §4: "they surface as raw text once the section’s ' +
        'cumulative comment volume for the term crosses the threshold".',
    ).toContain(held);
  }

  for (const comment of released) {
    expect(
      Object.keys(comment).sort(),
      `A released comment carries the fields ${JSON.stringify(Object.keys(comment).sort())}; ADR ` +
        `0153 freezes them at ${JSON.stringify(COMMENT_FIELDS)} and says why: a released comment ` +
        'grouped under a week can be joined to the per-week completion ledger SPEC §3.4 posts ' +
        'into the gradebook, and in a small week that intersection is frequently one person. Any ' +
        'further field is the leak, not a convenience — a stored instant nobody exposes today is ' +
        'a leak somebody ships tomorrow.',
    ).toEqual(COMMENT_FIELDS);
  }

  // And the rendered half: the words are on the page the instructor is reading.
  for (const held of EVERY_HELD_COMMENT) {
    await expect(
      report.getByText(held),
      `${JSON.stringify(held.slice(0, 40))}… is in the payload's released list and not on the ` +
        'page. §4’s promise is that the comments surface as raw text, and a payload the report ' +
        'does not render keeps that promise nowhere a person can see.',
    ).toBeVisible();
  }
});

test('week navigation reaches every published week and lands focus on the heading', async ({
  page,
}) => {
  // **SPEC §5.1's "week navigation pages across published weeks", and §14.2 item
  // 4's focus management.** The published-week list is read from the route that
  // answers it — discovered rather than derived, because the claim is that the
  // page offers the API's list and not one of its own — and the report is then
  // stepped back from the latest until the control is disabled, collecting the
  // week the address names at each stop.
  //
  // **The mutations this kills:** a control that counts by one, which visits a
  // week the section has published nothing for; a control that derives a range
  // from the first and last entries, which is the same sequence here and is why
  // the API's own list is compared rather than a hand-written one — a section
  // with a gap would part the two, and this story has none, so that distinction
  // is `instructor-report.spec.ts`'s and is named here as out of reach
  // (`docs/MISTAKES.md` entry 14); a far end that wraps rather than stops; and a
  // page that swaps everything under the heading without moving focus.
  test.setTimeout(CASE_TIMEOUT_MS);

  await openTheReport(page);
  const sectionId = sectionIdFromTheUrl(page);
  const token = await sessionToken(page);

  const answered = await page.request.get(
    `/instructor/sections/${sectionId}/published-weeks`,
    {
      headers: {
        Authorization: `Bearer ${token ?? ''}`,
        Accept: 'application/json',
      },
    },
  );
  expect(answered.status()).toBe(200);
  const published = ((await answered.json()) as { published_weeks: number[] })
    .published_weeks;
  expect(
    published,
    `The published-weeks route answered ${JSON.stringify(published)}. At this drive's clock — the ` +
      'Monday after course week 6’s window shut — course weeks 1 to 6 have closed windows and ' +
      `course week ${String(AN_UNPUBLISHED_WEEK)} has not opened one, so the six weeks the story ` +
      'was written into are exactly the published set. A shorter list makes the walk below a walk ' +
      'over less than the story.',
  ).toEqual(EVERY_PUBLISHED_WEEK);

  const previous = page.getByRole('button', { name: PREVIOUS_WEEK });
  const visited: number[] = [weekOnScreen(page)];
  for (let step = 0; step < MAX_WEEK_STEPS; step += 1) {
    if (await previous.isDisabled()) break;
    await previous.click();
    await expect(page).toHaveURL(/[?&]week=\d+/);
    await expect(page.locator('h1')).toBeFocused();
    visited.push(weekOnScreen(page));
  }

  expect(
    visited,
    'Stepping back through the report did not visit exactly the weeks the API answers with. SPEC ' +
      '§5.1 pages across published weeks, and the address is what makes each of them a link ' +
      'somebody can send.',
  ).toEqual([...published].reverse());
  await expect(previous).toBeDisabled();
});

test('the two rates state the week’s own arithmetic', async ({ page }) => {
  // **SPEC §5.1's "response rate and validity rate", both hand-computed, and the
  // enrolled denominator premise-guarded rather than trusted.**
  //
  // Course week 6: eight of the section's ten live members answered, so the
  // response rate is 8 / 10 = 0.8, and all eight responses are valid, so the
  // validity rate is 8 / 8 = 1.0. Course week 5: eight responses again, one of
  // which holds the comment whose stored verdict refuses it, so seven are valid
  // and the validity rate is 7 / 8 = 0.875.
  //
  // **The pair is the point.** A validity rate hard-coded to one, computed over
  // the enrolment, or divided the wrong way round all answer 1.0 for week 6. Only
  // week 5's 0.875 tells them apart, and only week 6's 1.0 shows that 0.875 is
  // not the shape of every week. Both values are exact in binary, so no assertion
  // here turns on a float's spelling (`docs/MISTAKES.md` entry 3's fixture-value
  // shape).
  //
  // **The enrolled count is a premise, and it names its source.** Ten is derived
  // by hand from `mock-lms/app/seed.py`'s membership: the learner plus students
  // 01 to 10, less student 07 whom Pulse never enrolls (ADR 0095). It is asserted
  // rather than assumed so that a roster change, a late add the sync has not
  // sighted, or an enrolled instructor counted among the students fails *here*,
  // naming the denominator, rather than turning the response rate into a wrong
  // number that reads as a plausible percentage.
  //
  // **The workload figures are asserted beside them** because §5.1 asks for the
  // section's workload mean *and* median, and the story's eight values were
  // chosen so the two are different numbers: 6, 7, 8, 9, 10, 11, 12 and 20 give
  // a mean of 83 / 8 = 10.375 and a median of (9 + 10) / 2 = 9.5. A payload that
  // served one in the other's place is red rather than plausible.
  //
  // **The mutations this kills:** a response rate over the response count rather
  // than the enrolment; an enrolled denominator counting every enrollment row the
  // section holds, instructor included; a validity rate that ignores the stored
  // verdict; a mean and a median computed by one formula; and a validity rate
  // whose denominator is the enrolment. **The near miss it must survive:** a
  // validity rate that counts *comments* rather than responses — week 5 holds two
  // comments of which one is refused, so a comment-denominated rate is 1 / 2 = 0.5
  // and not 0.875.
  test.setTimeout(CASE_TIMEOUT_MS);

  await openTheReport(page);

  const sixth = await readTheReport(page, LATEST_PUBLISHED_WEEK);
  expect(
    sixth.rates.enrolled,
    `The payload puts ${String(sixth.rates.enrolled)} people in course week ` +
      `${String(LATEST_PUBLISHED_WEEK)}'s denominator, and this drive is written for ` +
      `${String(ENROLLED_IN_WEEK_SIX)}: the learner plus students 01, 02, 03, 04, 05, 06, 08, 09 ` +
      'and 10 of `mock-lms/app/seed.py`’s BIOL roster. Student 07 is reported departed at the ' +
      'first sync and gets no Pulse enrollment at all (ADR 0095); student 04 is a late add dated ' +
      '2026-09-28, which is inside course week 4 and so live by week 6.\n\nNine here is the late ' +
      'add missing. Eleven is the instructor’s own enrollment row being counted among the ' +
      'students. Either way the response rate below is a ratio of the wrong denominator, and this ' +
      'assertion is what says so instead of letting it read as a plausible percentage.',
  ).toBe(ENROLLED_IN_WEEK_SIX);
  expect(sixth.rates.responses).toBe(
    planFor(LATEST_PUBLISHED_WEEK).respondents,
  );
  expect(
    sixth.rates.response_rate,
    `The response rate for course week ${String(LATEST_PUBLISHED_WEEK)} is ` +
      `${String(sixth.rates.response_rate)}; the week is ` +
      `${String(planFor(LATEST_PUBLISHED_WEEK).respondents)} responses over ` +
      `${String(ENROLLED_IN_WEEK_SIX)} enrolled, which is ${String(WEEK_SIX_RESPONSE_RATE)}.`,
  ).toBeCloseTo(WEEK_SIX_RESPONSE_RATE, 4);
  expect(
    sixth.rates.validity_rate,
    `The validity rate for course week ${String(LATEST_PUBLISHED_WEEK)} is ` +
      `${String(sixth.rates.validity_rate)}. Every one of that week's eight responses carries ` +
      'either a substantive comment or none at all, so SPEC §3.3’s valid responses over responses ' +
      'is 8 / 8.',
  ).toBeCloseTo(WEEK_SIX_VALIDITY_RATE, 4);

  expect(
    sixth.workload.mean,
    `The workload mean is ${String(sixth.workload.mean)}; the week's eight values sum to 83, so ` +
      `83 / 8 = ${String(WEEK_SIX_WORKLOAD_MEAN)}. The median of the same values is ` +
      `${String(WEEK_SIX_WORKLOAD_MEDIAN)}, which is what a payload serving the median here would ` +
      'answer.',
  ).toBeCloseTo(WEEK_SIX_WORKLOAD_MEAN, 4);
  expect(
    sixth.workload.median,
    `The workload median is ${String(sixth.workload.median)}; sorted, the week's eight values put ` +
      `9 and 10 in the middle, so the median is ${String(WEEK_SIX_WORKLOAD_MEDIAN)}.`,
  ).toBeCloseTo(WEEK_SIX_WORKLOAD_MEDIAN, 4);

  const fifth = await readTheReport(page, 5);
  expect(fifth.rates.responses).toBe(planFor(5).respondents);
  expect(
    fifth.rates.valid_responses,
    `Course week 5 reports ${String(fifth.rates.valid_responses)} valid responses of ` +
      `${String(fifth.rates.responses)}. One of its eight responses holds ` +
      `${JSON.stringify(WEEK_FIVE_REFUSED_COMMENT)}, the one comment this ` +
      'story plants a refusing verdict on, and SPEC §3.3 says a nonsense-flagged response reduces ' +
      'the rate — so seven are valid.\n\nEight here is the planted verdict reaching nothing: ' +
      '`rates.valid_responses` counts `response.is_valid` as `app/services/validity.py` maintains ' +
      'it (ADR 0147), never `classification` directly, so a seeder that appended a verdict row ' +
      'without the column that column is derived from leaves this week looking perfect.',
  ).toBe(WEEK_FIVE_VALID_RESPONSES);
  expect(
    fifth.rates.validity_rate,
    `The validity rate for course week 5 is ${String(fifth.rates.validity_rate)}; the week is ` +
      `${String(WEEK_FIVE_VALID_RESPONSES)} valid responses over ${String(fifth.rates.responses)}, ` +
      `which is ${String(WEEK_FIVE_VALIDITY_RATE)}. One half of a comment-denominated rate would ` +
      'be 0.5, and a rate over the enrolment would be 0.7.',
  ).toBeCloseTo(WEEK_FIVE_VALIDITY_RATE, 4);
});

// ---------------------------------------------------------------------------
// Driving the stack.
// ---------------------------------------------------------------------------

/** One decoded report payload, in the shape the payload sketch and E4-07's schema fix. */
interface ReportPayload {
  week: { course_week: number; term_week: number; published_weeks: number[] };
  rates: {
    response_rate: number | null;
    validity_rate: number | null;
    responses: number;
    valid_responses: number;
    enrolled: number;
  };
  streams: Record<
    string,
    {
      trend: { course_week: number; term_week: number; mean: number | null }[];
      summary: { text: string; response_count: number } | null;
      comments: Record<string, unknown>[];
    }
  >;
  workload: { mean: number | null; median: number | null };
  small_n: { suppressed: boolean; threshold: number };
  released_from_earlier_weeks: Record<string, unknown>[];
}

/**
 * Launch the instructor, open `BIOL-215-R3WW`'s report, and answer with it.
 *
 * The report is reached the way a person reaches it — a launch, the menu of
 * sections she teaches, a click — rather than by an address this file assembled,
 * because "an instructor opens a real Monday report" is the exit clause and the
 * opening is half of it. A course week may be named, in which case the address
 * carries it the way a link somebody sent would.
 */
async function openTheReport(
  page: Page,
  courseWeek?: number,
): Promise<Locator> {
  await launchAs(page, INSTRUCTOR_SUBJECT, placement);
  await expect(page.getByTestId(INSTRUCTOR_LANDING)).toBeVisible();
  const menu = page.getByTestId(SECTIONS_MENU);
  await expect(
    menu,
    'The instructor did not land on the section menu. She teaches this section, the one the seed ' +
      'gives her and whatever other specs have launched her into, so a page that redirected her ' +
      'straight to a report means the section list answered with exactly one — which is a section ' +
      'list read rather than a menu defect.',
  ).toBeVisible();
  await menu.getByRole('link', { name: new RegExp(BIOL.course) }).click();
  const report = page.getByTestId(REPORT);
  await expect(
    report,
    'The section menu did not open a report. Three causes look the same from here: the link ' +
      'points at an address the router does not serve, the published-weeks read was refused, or ' +
      'the section has no closed week at this clock.',
  ).toBeVisible();
  if (courseWeek !== undefined) {
    await page.goto(
      `/app/instructor/sections/${sectionIdFromTheUrl(page)}?week=${String(courseWeek)}`,
    );
    await expect(page.getByTestId(REPORT)).toBeVisible();
  }
  return page.getByTestId(REPORT);
}

/**
 * One week's report, read through the API with the session the launch handed over.
 *
 * The section key comes off the address the page is being read at, so this asks
 * the API the same question the page asked. The status is asserted here rather
 * than in every caller, because a body decoded off a refusal is a body every
 * later assertion is vacuously true of.
 */
async function readTheReportWithItsBody(
  page: Page,
  courseWeek: number,
): Promise<{ payload: ReportPayload; raw: string }> {
  const token = await sessionToken(page);
  expect(
    token,
    'The instructor launch handed over no session, so nothing read below is a read of anything.',
  ).not.toBeNull();
  const sectionId = sectionIdFromTheUrl(page);
  const answered = await page.request.get(
    `/instructor/sections/${sectionId}/report/${String(courseWeek)}`,
    {
      headers: {
        Authorization: `Bearer ${token ?? ''}`,
        Accept: 'application/json',
      },
    },
  );
  expect(
    answered.status(),
    `The report for course week ${String(courseWeek)} answered ${String(answered.status())} for ` +
      'the section this session teaches.',
  ).toBe(200);
  const raw = await answered.text();
  return { payload: JSON.parse(raw) as ReportPayload, raw };
}

/** One week's report payload. */
async function readTheReport(
  page: Page,
  courseWeek: number,
): Promise<ReportPayload> {
  const { payload } = await readTheReportWithItsBody(page, courseWeek);
  expect(
    payload.week.course_week,
    `The report asked for course week ${String(courseWeek)} answered for course week ` +
      `${String(payload.week.course_week)}.`,
  ).toBe(courseWeek);
  return payload;
}

/**
 * One stream's trend, as a map of course week to mean.
 *
 * A map rather than the list, because what this file asserts is one week's mean
 * and not a position in an array: a trend that carries the section's later weeks
 * with no mean is a legitimate shape (the payload zero-fills the weeks the chart
 * needs), and nothing here asserts the list's length or its order. That is
 * deliberately out of reach and said so (`docs/MISTAKES.md` entry 14).
 */
function trendMeansOf(
  payload: ReportPayload,
  stream: string,
): Map<number, number | null> {
  const points = payload.streams[stream]?.trend;
  expect(
    Array.isArray(points),
    `The payload carries no trend for the ${stream} stream; \`streams\` holds ` +
      `${JSON.stringify(Object.keys(payload.streams ?? {}))}.`,
  ).toBe(true);
  const means = new Map<number, number | null>();
  for (const point of points ?? []) means.set(point.course_week, point.mean);
  return means;
}

/** Whether a sequence of numbers rises strictly, with no gap in it. */
function strictlyRising(values: (number | null)[]): boolean {
  return values.every(
    (value, index) =>
      typeof value === 'number' &&
      Number.isFinite(value) &&
      (index === 0 || value > (values[index - 1] as number)),
  );
}

/**
 * Every response `BIOL-215-R3WW` holds, counted per course week, out of Pulse's
 * own database.
 *
 * `response.week_id` names a `week` row and a `week` row carries the **term**
 * week (E2-05's schema), so the term weeks come back and are translated into
 * course weeks here through this file's own hand-written table. A translation the
 * report also performs, done here from the transcribed calendar rather than
 * borrowed from the payload — the point of this read is to be a second opinion
 * about the story, and one that asked the report where its weeks were would be
 * the report agreeing with itself.
 */
function responsesByCourseWeek(): Map<number, number> {
  const rows = databaseStatement(
    'select w.number, count(*) from response r ' +
      'join section s on s.id = r.section_id ' +
      'join week w on w.id = r.week_id ' +
      `where s.lms_section_code = ${quoted(BIOL.code)} ` +
      'group by w.number order by w.number;',
  );
  const courseWeekOfTermWeek = new Map(
    Object.entries(TERM_WEEK_OF_COURSE_WEEK).map(
      ([courseWeek, termWeek]): [number, number] => [
        termWeek,
        Number(courseWeek),
      ],
    ),
  );
  const counted = new Map<number, number>();
  for (const row of rows.split('\n')) {
    if (row.trim() === '') continue;
    const [termWeek, count] = row.split('|');
    const courseWeek = courseWeekOfTermWeek.get(Number(termWeek));
    expect(
      courseWeek,
      `\`BIOL-215-R3WW\` holds ${String(count)} responses in term week ${String(termWeek)}, which ` +
        'is not one of the six course weeks this story is written into (term weeks 4 to 9). Either ' +
        'the seeder wrote into a week the plan does not name, or the seeded calendar has moved ' +
        'under the transcription at the top of this file.',
    ).toBeDefined();
    counted.set(courseWeek ?? 0, Number(count));
  }
  return counted;
}

/**
 * Wait until every one of the story's nine respondents has an enrollment row.
 *
 * **The enrollment row and not the survey block**, which is where this departs
 * from `instructor-report.spec.ts`'s poll and why. That poll launches as each
 * student and waits for their section block, which is the right observable when
 * the question is "can this person answer this week" — it needs an open window,
 * and so it needs the clock inside one. This drive's question is different: the
 * seeder writes the rows itself and refuses if the enrollments are missing, so
 * what has to be true is exactly what is read here. Polling the block would cost
 * nine launches and would force the clock to move before the roster sync, which
 * is the one ordering this drive must not have.
 */
async function waitForTheRosterInTheDatabase(): Promise<void> {
  const deadline = Date.now() + ROSTER_TIMEOUT_MS;
  let missing = [...RESPONDENTS];
  while (missing.length > 0 && Date.now() < deadline) {
    const enrolled = new Set(
      databaseStatement(
        'select u.lms_user_id from enrollment e ' +
          'join "user" u on u.id = e.user_id ' +
          'join section s on s.id = e.section_id ' +
          `where s.lms_section_code = ${quoted(BIOL.code)};`,
      )
        .split('\n')
        .map((row) => row.trim())
        .filter((row) => row !== ''),
    );
    missing = missing.filter((subject) => !enrolled.has(subject));
    if (missing.length > 0)
      await new Promise((wake) => setTimeout(wake, ROSTER_RETRY_MS));
  }
  expect(
    missing,
    `These respondents have no enrollment in ${BIOL.code} within ` +
      `${String(ROSTER_TIMEOUT_MS)}ms of the roster sync: ${JSON.stringify(missing)}. The sync is ` +
      'what enrols them (SPEC §7.3), so this is the worker not running, the mock platform not ' +
      'serving its roster, or the staff launch not having stored the section’s roster address. The ' +
      'seeder refuses to invent an enrollment (E4-15’s work order decision 2), which is why this ' +
      'is waited for here rather than discovered as a refusal there.',
  ).toEqual([]);
}

/** The section key out of the address the report is being read at. */
function sectionIdFromTheUrl(page: Page): string {
  const found = /\/instructor\/sections\/([0-9a-f-]+)/.exec(page.url());
  expect(
    found,
    `The report's address does not carry a section key: ${page.url()}`,
  ).not.toBeNull();
  return found?.[1] ?? '';
}

/** The course week the address names, or the latest published one when it names none. */
function weekOnScreen(page: Page): number {
  const named = new URL(page.url()).searchParams.get('week');
  return named === null ? LATEST_PUBLISHED_WEEK : Number(named);
}

/** One string as a SQL literal. */
function quoted(value: string): string {
  return `'${value.replace(/'/g, "''")}'`;
}
