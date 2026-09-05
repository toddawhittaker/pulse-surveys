// E3-08, criterion 1 — SPEC §14.3, E3's exit line: "the mock-LMS gradebook shows
// correct percentages across enrollment edge cases."
//
// **This file drives the exit table against the running stack.** Every row of
// E3-08's table is a clock position, a launch or an amendment, a passback, and a
// read of the mock platform's own gradebook. Nothing here is a unit test with a
// browser attached: the sections are provisioned by a real staff launch, their
// AGS addresses and line items come from that launch, the rosters are read by the
// real sync, the answers are typed into the real survey form, and the scores are
// read back off `GET /mock/posted-scores` — the platform's record of what it was
// sent (ADR 0047), not Pulse's record of what it sent.
//
// **THIS SPEC MOVES THE CLOCK ACROSS SIX WEEKS AND AMENDS TWO ROSTERS.** It must
// not run in the main Playwright project: a neighbouring spec that ran while the
// stack pretended it was October, or after this file dropped the learner from
// `MATH-140-E1FF`, would fail pointing at its own subject. E3-08's work order
// puts it in a `grade-passback-exit` project that runs after the others, with the
// main project ignoring this file. Until that split lands, a run of the whole
// suite will red its neighbours as well as itself, and that is the split's
// absence rather than a defect in either.
//
// **Every expected percentage and every ledger below is hand-computed from SPEC
// §3.4, with the arithmetic beside it** (E3-08 criterion 1, `docs/MISTAKES.md`
// entry 19). None is read out of `app.services.grading`, out of `grade_sync`, or
// out of anything else the implementation produces. The section calendars are
// transcribed from `scripts/seed.py`'s `START_LETTER_MAP` and the survey rhythm
// from SPEC §3.1, and each is written out where it is used.
//
// **The gradebook is not the assertion for "posted once" or "no new post."** An
// idempotent re-post and an absent post leave the same gradebook.
// `GET /mock/posted-scores` is a log in arrival order, so where this file means
// "nothing was posted" it counts entries before and after, and it always pairs
// that count with somebody who *did* post in the same sweep — an absence with no
// positive control beside it is satisfied by a sweep that did nothing at all
// (`docs/MISTAKES.md` entry 3).
//
// **One divergence from the work order's drive schedule is deliberate and is the
// reason there is a sixth clock position.** The work order predicted that
// `BIOL-215-R3WW`'s dropped member — student 07, whom `with_the_add_and_the_drop`
// seeds `Inactive` with `closed_at` 2026-10-19 — would receive no score at any
// point in the drive. Two rules that are already asserted elsewhere in this
// repository say otherwise, and they compose:
//
//   - the sync records a departed member's `ended_on` as **the platform's own end
//     date**, not the day the sync ran
//     (`test_a_dropped_member_is_ended_at_the_platforms_end_date_and_an_active_one_is_not`);
//   - the sweep posts for a student while `started_on <= clock.today AND
//     (ended_on IS NULL OR ended_on >= clock.today)` — E3-06's work order D10,
//     asserted from both sides one day apart in
//     `test_a_dropped_students_score_stops_updating.py`.
//
// So student 07's enrollment is live on every day before 2026-10-19 and his score
// updates like anybody's until then. That is not a defect: a student whose
// platform record says they leave in three weeks has not left, and a tool that
// stopped posting the moment a roster said `Inactive` would freeze three weeks of
// a grade the LMS still expects to move. The drive therefore asserts the whole
// boundary rather than half of it — 07 posting beside his classmates at
// 2026-10-05 and 2026-10-12, and 07 alone silent at 2026-10-26 while they post —
// which is exit-table row 7 driven with its own seeded member and with a positive
// control on both sides.
//
// **That divergence is a prediction and the run is what settles it.** If the
// implementation does stop posting for him the moment his roster status reads
// `Inactive`, the P4 and P5 assertions below go red — and the finding is then
// whether "Inactive with an end date three weeks out" should stop a grade today,
// which is a question for the ticket rather than a number to widen here.
//
// The learner's drop from `MATH-140-E1FF`, dated at the moment it is made, is the
// other half of row 7 and is the case where the *last posted value stands* while
// classmates in the same section move on.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect, type Locator, type Page } from "@playwright/test";

import { clearTheClock, setTheClockTo } from "./support/clock";
import {
  DEV_CONSOLE_PATH,
  MOCK_LMS_ORIGIN,
  launchAs,
  placementInto,
} from "./support/doors";
import { databaseStatement, deriveSurveyWindows } from "./support/stack";

// ---------------------------------------------------------------------------
// The world, transcribed from `mock-lms/app/seed.py` and `scripts/seed.py`.
// ---------------------------------------------------------------------------

// The two people a browser drives. Per-section students never launch and never
// submit — every tier case below is proven through the score the sweep posts for
// them and through its ledger, which is what SPEC §3.4 says the denominator is
// made of.
const LEARNER = "mock-lms-user-learner";
const INSTRUCTOR = "mock-lms-user-instructor";

// The three sections, as the launch page labels them, as `section.lms_context_id`
// holds them, and as `section.lms_section_code` spells them (§2.2's
// `{startLetter}{ordinal}{modality}`).
const BIOL = {
  label: "BIOL-215-R3WW",
  context: "mock-lms-context-biol-215-r3ww",
  code: "R3WW",
};
const MATH = {
  label: "MATH-140-E1FF",
  context: "mock-lms-context-math-140-e1ff",
  code: "E1FF",
};
const NURS = {
  label: "NURS-8100-Q2FF",
  context: "mock-lms-context-nurs-8100-q2ff",
  code: "Q2FF",
};
const EVERY_SECTION = [BIOL, MATH, NURS];

/** One per-section student's `sub`, as `mock-lms/app/seed.py::student` mints it. */
function student(section: { label: string }, ordinal: number): string {
  return `mock-lms-user-${section.label.toLowerCase()}-student-${String(ordinal).padStart(2, "0")}`;
}

// The four seeded students this file names. `with_the_add_and_the_drop` rewrites
// 04 and 07 of `BIOL-215-R3WW` and nothing else in that section;
// `without_an_enrollment_window` rewrites 03 of `NURS-8100-Q2FF`.
const BIOL_DAY_ONE = student(BIOL, 1); // dated 2026-09-07 with the rest of the class
const BIOL_LATE_ADD = student(BIOL, 4); // `opened_at` 2026-09-28 — exit row 4
const BIOL_DROPPED = student(BIOL, 7); // Inactive, `closed_at` 2026-10-19 — exit row 7
const NURS_WINDOWLESS = student(NURS, 3); // no platform dates at all — exit row 5
const NURS_DAY_ONE = student(NURS, 1); // dated 2026-09-28, the classmate row 5 compares against
const MATH_CLASSMATE = student(MATH, 1); // the positive control beside the learner's drop

// The student `POST /mock/roster-amendments` adds to `NURS-8100-Q2FF` part-way
// through — undated, so nothing but the sync that first saw him can date his
// enrollment. Exit row 6.
const NURS_LATE_ADD_ORDINAL = 4;
const NURS_LATE_ADD = student(NURS, NURS_LATE_ADD_ORDINAL);

// ---------------------------------------------------------------------------
// The calendars, and the arithmetic every expectation below rests on.
// ---------------------------------------------------------------------------
//
// `scripts/seed.py::START_LETTER_MAP`, the three rows this drive uses:
//   ("R", 12, date(2026, 9, 7))  — BIOL-215-R3WW
//   ("E",  6, date(2026, 8, 17)) — MATH-140-E1FF
//   ("Q", 12, date(2026, 9, 28)) — NURS-8100-Q2FF
//
// SPEC §3.1: a week's survey window opens Friday 18:00 and closes Sunday
// 23:59:59 in `America/New_York`, so a course week has *elapsed* once its own
// Sunday has ended. Counting each cohort's weeks from its Monday start:
//
//   BIOL (R, 12 weeks from Mon 2026-09-07)
//     week 1  09-07 … 09-13    week 5  10-05 … 10-11
//     week 2  09-14 … 09-20    week 6  10-12 … 10-18
//     week 3  09-21 … 09-27    week 7  10-19 … 10-25
//     week 4  09-28 … 10-04
//
//   MATH (E, 6 weeks from Mon 2026-08-17)
//     week 1  08-17 … 08-23    week 4  09-07 … 09-13
//     week 2  08-24 … 08-30    week 5  09-14 … 09-20
//     week 3  08-31 … 09-06    week 6  09-21 … 09-27
//
//   NURS (Q, 12 weeks from Mon 2026-09-28)
//     week 1  09-28 … 10-04    week 2  10-05 … 10-11    week 3  10-12 … 10-18
//
// The section carries five questions (SPEC §3.2's fixed v1 set), so a week is
// **five items**: two ratings, two comments and the workload. A rating or the
// workload completes by being answered; a comment completes by being answered
// and not refused by the classifier (§3.3, §3.4).

// The six moments this drive stands the development clock at, as
// `<input type="datetime-local">` values in the institution's zone.
const P1 = "2026-09-11T19:00"; // Fri, inside BIOL week 1's and MATH week 4's windows
const P2 = "2026-09-18T19:00"; // Fri, inside BIOL week 2's window
const P3 = "2026-09-21T09:00"; // Mon, BIOL weeks 1–2 and MATH weeks 1–5 elapsed
const P4 = "2026-10-05T09:00"; // Mon, BIOL 1–4, MATH 1–6, NURS 1 elapsed
const P5 = "2026-10-12T09:00"; // Mon, BIOL 1–5, NURS 1–2 elapsed
const P6 = "2026-10-26T09:00"; // Mon, BIOL 1–7 elapsed; past BIOL 07's 10-19 drop

// The day the learner is dropped from `MATH-140-E1FF`, as an RFC 3339 instant for
// the amendment route (ADR 0048: an offset, never a bare date). 2026-09-21 is
// eastern daylight time, hence `-04:00`.
const MATH_DROP_INSTANT = "2026-09-21T09:00:00-04:00";

// ---------------------------------------------------------------------------
// The expectations. Each is hand-computed here from the calendars above and
// SPEC §3.4's formula — "completed items ÷ total items across the student's
// elapsed weeks" — with the arithmetic shown.
// ---------------------------------------------------------------------------

// SPEC §3.4's ledger line, transcribed from the specification's own example
// (`Week 1: 4 of 5 items`) and joined one per line in course-week order.
const ITEMS_PER_WEEK = 5;

function ledgerLine(
  courseWeek: number,
  completed: number,
  total: number,
): string {
  return `Week ${courseWeek}: ${completed} of ${total} items`;
}

function ledgerOf(weeks: [number, number][]): string {
  return weeks
    .map(([week, completed]) => ledgerLine(week, completed, ITEMS_PER_WEEK))
    .join("\n");
}

/** A run of consecutive weeks nobody answered — `0 of 5` for each. */
function unanswered(from: number, to: number): [number, number][] {
  const weeks: [number, number][] = [];
  for (let week = from; week <= to; week += 1) weeks.push([week, 0]);
  return weeks;
}

// **P1, MATH, the learner.** Weeks 1–3 have elapsed (week 3 closed Sun 09-06);
// week 4's window is open, so it is not in the denominator yet. The learner has
// just answered week 4 and nothing else.
//   completed 0, total 3 × 5 = 15 → 0/15 × 100 = 0.0
const P1_MATH_LEARNER_SCORE = 0;
const P1_MATH_LEARNER_LEDGER = ledgerOf(unanswered(1, 3));

// **P3, BIOL, the learner.** Weeks 1 and 2 have elapsed (week 2 closed Sun
// 09-20); week 3 is open. Both were answered in full — exit row 1.
//   completed 5 + 5 = 10, total 2 × 5 = 10 → 10/10 × 100 = 100.0
const P3_BIOL_LEARNER_SCORE = 100;
const P3_BIOL_LEARNER_LEDGER = ledgerOf([
  [1, 5],
  [2, 5],
]);

// **P3, MATH, the learner.** Weeks 1–5 have elapsed (week 5 closed Sun 09-20);
// week 6 is open. Only week 4 was answered, and one optional comment was left
// blank — four items of five (exit rows 2 and 3: the fraction, and the missed
// weeks still in the denominator at their full width).
//   completed 4, total 5 × 5 = 25 → 4/25 × 100 = 16.0
const P3_MATH_LEARNER_SCORE = 16;
const P3_MATH_LEARNER_LEDGER = ledgerOf([
  [1, 0],
  [2, 0],
  [3, 0],
  [4, 4],
  [5, 0],
]);

// **P3, BIOL, a day-one classmate who answered nothing.** Two elapsed weeks at
// their full width — exit row 3 again, from the other direction.
//   completed 0, total 10 → 0.0
const P3_BIOL_SILENT_SCORE = 0;
const P3_BIOL_SILENT_LEDGER = ledgerOf(unanswered(1, 2));

// **P4, BIOL, the learner.** Weeks 1–4 have elapsed (week 4 closed Sun 10-04).
//   completed 10, total 4 × 5 = 20 → 10/20 × 100 = 50.0
const P4_BIOL_LEARNER_SCORE = 50;

// **P4, BIOL, the platform-dated late add (student 04).** §3.4's first tier: the
// denominator starts at the student's first enrolled week, which is the earliest
// course week whose window closes at or after their platform start. `opened_at`
// is 2026-09-28T00:00-04:00; week 3 closed 09-27 23:59:59, which is before that,
// and week 4 closes 10-04 23:59:59, which is after. So week 4 is the first, and
// at P4 exactly one of his weeks has elapsed — exit row 4, in both directions:
// week 4 present, weeks 1–3 absent.
//   completed 0, total 1 × 5 = 5 → 0.0
const P4_BIOL_LATE_ADD_SCORE = 0;
const P4_BIOL_LATE_ADD_LEDGER = ledgerLine(4, 0, ITEMS_PER_WEEK);

// **P4, NURS, the windowless member and her day-one classmate.** §3.4's undated
// tier: "Where the platform supplies no enrollment dates … a student counts as
// enrolled from the section's start date." She was already on the roster at the
// section's first sync, so the later-sync exception does not reach her. Her
// classmate carries `opened_at` 2026-09-28, which is week 1's own Monday. Both
// therefore start at week 1, and at P4 exactly week 1 has elapsed (closed Sun
// 10-04) — exit row 5, asserted as an intended *equality* and not as a defect.
//   completed 0, total 1 × 5 = 5 → 0.0
const P4_NURS_SCORE = 0;
const P4_NURS_LEDGER = ledgerLine(1, 0, ITEMS_PER_WEEK);

// **P4, MATH, a classmate of the dropped learner.** All six weeks have elapsed by
// 10-05 (week 6 closed Sun 09-27), and nobody but the learner answered anything.
//   completed 0, total 6 × 5 = 30 → 0.0
// The percentage is the same as his P3 one and the **ledger is not** — five lines
// became six — so ADR 0137's pair comparison re-posts him. That is what makes him
// the positive control for the learner's silence in the same sweep.
const P4_MATH_CLASSMATE_SCORE = 0;
const P4_MATH_CLASSMATE_LEDGER = ledgerOf(unanswered(1, 6));

// **P5, BIOL, the learner.** Week 5 closed Sun 10-11, so five weeks have elapsed.
//   completed 10, total 5 × 5 = 25 → 10/25 × 100 = 40.0
const P5_BIOL_LEARNER_SCORE = 40;

// **P5, NURS, the member added part-way through.** §3.4's third tier: "a student
// who first appears in a roster sync later than their section's first sync counts
// from the week of that sync." His first sync ran on the effective day 2026-10-05
// and NURS week 1 had already closed (10-04), so the first week whose window
// closes on or after that day is week 2 (closes 10-11). At P5 week 2 has just
// elapsed — exit row 6, in both directions: week 2 present, week 1 absent.
//   completed 0, total 1 × 5 = 5 → 0.0
const P5_NURS_LATE_ADD_SCORE = 0;
const P5_NURS_LATE_ADD_LEDGER = ledgerLine(2, 0, ITEMS_PER_WEEK);

// **P5, BIOL, the dropped member (student 07).** His platform end date is
// 2026-10-19, which is still ahead, so he is enrolled and scored like any
// classmate who answered nothing. This is his **last** posted value; nothing
// after it moves.
//   completed 0, total 5 × 5 = 25 → 0.0, with a five-line ledger
const P5_BIOL_SILENT_SCORE = 0;
const P5_BIOL_SILENT_LEDGER = ledgerOf(unanswered(1, 5));

// **P6, BIOL, the learner and the day-one classmate.** Week 7 closed Sun 10-25,
// so seven weeks have elapsed.
//   learner:   completed 10, total 7 × 5 = 35 → 10/35 × 100 = 28.5714…,
//              which is 28.6 to one decimal, rounded half up (E3-03's rule)
//   classmate: completed 0, total 35 → 0.0, with a seven-line ledger
const P6_BIOL_LEARNER_SCORE = 28.6;
const P6_BIOL_SILENT_LEDGER = ledgerOf(unanswered(1, 7));

// ---------------------------------------------------------------------------
// The controls this drive needs, and the surfaces it reads.
// ---------------------------------------------------------------------------

// E3-07's trigger, already shipped (`tests/fixtures/dev_console.py`).
const PASSBACK_RUN = "passback-run";

// E3-08's roster-sync control, on the same console beside it. The testid is the
// work order's (`ROSTER_SYNC_RUN_TESTID`); the button's wording is the
// implementer's and is not asserted anywhere.
const ROSTER_SYNC_RUN = "roster-sync-run";

// The mock platform's two `/mock/` surfaces. Both are outside the AGS namespace
// and both are tokenless by decision (ADR 0047, ADR 0134): no real platform
// serves either, and nothing under `backend/app/` may read either —
// `tests/unit/test_no_backend_module_reads_the_mock_only_score_log.py` asserts
// the half of that which concerns the score log.
const POSTED_SCORES_URL = `${MOCK_LMS_ORIGIN}mock/posted-scores`;
const ROSTER_AMENDMENTS_URL = `${MOCK_LMS_ORIGIN}mock/roster-amendments`;

// The AGS score members, spelled as AGS 2.0 spells them and as
// `tests/fixtures/ags_client.py` transcribes them.
const SCORE_USER = "userId";
const SCORE_GIVEN = "scoreGiven";
const SCORE_COMMENT = "comment";

// The survey form's testids (E2-10) and the submitted-state heading, taken from
// `exit-weekly-survey.spec.ts` rather than from `frontend/src/copy/`.
const SUBMIT = "survey-submit";
const SUBMITTED_TITLE = "Your pulse is in";

// Two comments known to clear the mock provider's substantiveness rule, copied
// from `exit-weekly-survey.spec.ts` — a comment the classifier refuses does not
// complete its item (§3.4), and every count below assumes these do.
const INSTRUCTOR_COMMENT =
  "The Wednesday seminar spent long enough on the staining protocol for it to land.";
const COURSE_COMMENT =
  "The week four reading list was long, and the ordering made it manageable.";

// How long the asynchronous halves are given. Line items are created by the
// worker after a staff launch (E3-05) and the sweep skips a section that has none
// yet, so both the wait and the re-trigger are the ticket's own named trap.
const ASYNC_TIMEOUT_MS = 90_000;
const ASYNC_RETRY_MS = 3_000;

// A budget per case. Each moves the clock, drives a launch or two, pulls a
// trigger several times and shells out to `docker compose` — a case that ran out
// of harness rather than out of patience would read as a flake.
const CASE_TIMEOUT_MS = 300_000;

/** One score body as the platform recorded it, plus which line item it went to. */
interface PostedEntry {
  lineItem: string;
  score: Record<string, unknown>;
}

/** The placements `beforeAll` discovers for the instructor, per section label. */
const placements = new Map<string, string>();

/**
 * The learner's own resource link into `BIOL-215-R3WW`, discovered separately.
 *
 * Every learner launch in this file goes through it, and the student view it
 * lands on lists a block per section the learner has an open survey in — so one
 * launch reaches all three sections and the block is chosen by section code.
 */
let learnerPlacement = "";

/**
 * How many scores the platform held for the learner against `MATH-140-E1FF` at
 * the moment he was dropped from it.
 *
 * Captured rather than counted from this file's own reading of the drive, because
 * the claim P4 makes is "no *new* entry" and a hand-derived total would be a
 * second thing to keep in step with the schedule. P3 asserts what the latest of
 * them says before this is recorded, so it is known to be non-zero and known to
 * be the 16.0 entry.
 */
let learnerMathEntriesWhenHeWasDropped = 0;

test.describe.configure({ mode: "serial" });

// ---------------------------------------------------------------------------
// Reading the platform.
// ---------------------------------------------------------------------------

/**
 * Every score the mock platform has been sent, in arrival order.
 *
 * ADR 0047 fixes the shape: `{"scores": [{"lineItem": …, "score": {…}}]}`. It is
 * asserted rather than normalised, because a helper that accepted four shapes
 * would go on answering `[]` after the route changed and every absence assertion
 * in this file would then pass for that reason.
 */
async function postedEntries(page: Page): Promise<PostedEntry[]> {
  const response = await page.request.get(POSTED_SCORES_URL);
  expect(
    response.status(),
    `GET ${POSTED_SCORES_URL} answered ${response.status()}. ADR 0047 puts the posted-score ` +
      "readback outside the AGS namespace as a tokenless inspection surface; a 401 here is the " +
      "AGS credential enforcement having been applied by path prefix rather than by route.",
  ).toBe(200);
  const document: unknown = await response.json();
  const scores =
    typeof document === "object" && document !== null
      ? (document as Record<string, unknown>).scores
      : undefined;
  expect(
    Array.isArray(scores),
    `${POSTED_SCORES_URL} served ${JSON.stringify(document).slice(0, 400)}. The shape ADR 0047 ` +
      'fixes is `{"scores": [{"lineItem": …, "score": {…}}]}`, and a reader that shrugged at ' +
      'another shape would answer "no scores" for every assertion in this file.',
  ).toBe(true);
  return (scores as PostedEntry[]).map((entry) => ({
    lineItem: String(entry.lineItem ?? ""),
    score: (entry.score ?? {}) as Record<string, unknown>,
  }));
}

/**
 * Every score body posted for one student against one section's line item, in order.
 *
 * The section is matched on the mock's own context identifier, which every AGS
 * URL this platform composes carries as a path segment
 * (`mock-lms/app/config.py::LINE_ITEMS_PATH`). Matching on the served URL rather
 * than on a line-item id read out of Pulse's database keeps this read on the
 * platform's side of the wire, which is the whole point of reading it here.
 */
function scoresFor(
  entries: PostedEntry[],
  contextId: string,
  subject: string,
): Record<string, unknown>[] {
  return entries
    .filter((entry) => entry.lineItem.includes(contextId))
    .filter((entry) => String(entry.score[SCORE_USER] ?? "") === subject)
    .map((entry) => entry.score);
}

/** The last thing the platform was told about one student, or `undefined`. */
function latestScoreFor(
  entries: PostedEntry[],
  contextId: string,
  subject: string,
): Record<string, unknown> | undefined {
  const found = scoresFor(entries, contextId, subject);
  return found.length === 0 ? undefined : found[found.length - 1];
}

/**
 * The line item the section holding this context id points at, or `'none'`.
 *
 * Read out of Pulse's own `section` row rather than guessed, and used only as a
 * premise: an absence assertion about a section whose line item the worker has
 * not created yet says nothing about the formula (`docs/MISTAKES.md` entry 3).
 * `lms_context_id` is the column E1-10 binds a section to its platform context
 * with, and it is unique per deployment, so this addresses one row.
 */
function storedLineItem(contextId: string): string {
  const answered = databaseStatement(
    "select coalesce(ags_line_item_url, 'none') from section where lms_context_id = " +
      `${quoted(contextId)};`,
  );
  const rows = answered === "" ? [] : answered.split("\n");
  expect(
    rows.length,
    `\`section\` holds ${rows.length} rows with \`lms_context_id\` = ${contextId}, and this drive ` +
      "needs exactly one. None means no staff launch has provisioned the section; more than one " +
      "means the binding E1-10 makes unique is not.",
  ).toBe(1);
  return rows[0];
}

/** One string as a SQL literal (`exit-weekly-survey.spec.ts`'s helper). */
function quoted(value: string): string {
  return `'${value.replace(/'/g, "''")}'`;
}

// ---------------------------------------------------------------------------
// Driving the stack.
// ---------------------------------------------------------------------------

/**
 * Click one `/dev` control and come back to the console.
 *
 * Through the page rather than by a bare request, because both controls carry a
 * same-origin `Origin` check (E3-07's D4, ADR 0141) and only a browser sends the
 * header a working click sends. The redirect is asserted, so a control that
 * answered something else is a named failure rather than a silent no-op.
 */
async function clickTheControl(page: Page, testid: string): Promise<void> {
  await page.goto(DEV_CONSOLE_PATH);
  const button = page.getByTestId(testid);
  await expect(
    button,
    `The development console carries no element with \`data-testid="${testid}"\`. E3-07 adds ` +
      `\`${PASSBACK_RUN}\` and E3-08's work order adds \`${ROSTER_SYNC_RUN}\` beside it; without ` +
      "the button there is no way to reach the control from the page, which is the whole reason " +
      "either exists.",
  ).toBeVisible();
  await button.click();
  await expect(page).toHaveURL(new RegExp(`${DEV_CONSOLE_PATH}/?$`));
}

/**
 * Pull the passback trigger until `settled` answers true, or give up loudly.
 *
 * Re-triggering rather than waiting: a section whose line item the worker has not
 * finished creating is skipped by the sweep and asked about again on the next run
 * (E3-06), so the thing to repeat is the sweep and not the read. The answer is a
 * boolean the caller asserts, so a give-up is a FAILED carrying the caller's own
 * sentence rather than a timeout naming a locator.
 */
async function passbackUntil(
  page: Page,
  settled: () => Promise<boolean>,
): Promise<boolean> {
  const deadline = Date.now() + ASYNC_TIMEOUT_MS;
  for (;;) {
    await clickTheControl(page, PASSBACK_RUN);
    if (await settled()) return true;
    if (Date.now() >= deadline) return false;
    await new Promise((wake) => setTimeout(wake, ASYNC_RETRY_MS));
  }
}

/** One amendment to the mock platform's roster, and the status it answered. */
async function amendTheRoster(
  page: Page,
  body: Record<string, unknown>,
): Promise<number> {
  const response = await page.request.post(ROSTER_AMENDMENTS_URL, {
    data: body,
  });
  return response.status();
}

/**
 * Land as the learner and answer with one section's survey block.
 *
 * `student-survey.spec.ts`'s helper and its diagnosis: three causes look the same
 * from here — no enrollment yet, no materialized window for the pretended week,
 * or a clock that is not where this test put it.
 */
async function landOnTheSurvey(page: Page, code: string): Promise<Locator> {
  await launchAs(page, LEARNER, learnerPlacement);
  const block = page.getByTestId(`survey-section-${code}`);
  await expect(
    block,
    `The learner landed without a survey block for ${code}. Either the roster sync has not ` +
      "enrolled them in that section, the section has no materialized `survey_window` row for " +
      "the pretended week, or the development clock is not where this test set it.",
  ).toBeVisible();
  return block;
}

/**
 * Answer one week: two ratings above §3.2's conditional threshold, two comments,
 * and the workload slider.
 *
 * `comments` carries one entry per comment field, in order; an empty string
 * leaves that field blank, which is a valid response (§3.3) and one item of the
 * week not completed (§3.4). The ratings are 4 and 5 so that neither comment is
 * *required* and a blank one is genuinely optional.
 */
async function answerTheWeek(
  block: Locator,
  comments: [string, string],
): Promise<void> {
  await block.getByRole("radio", { name: /^4\b/ }).nth(0).check();
  await block.getByRole("radio", { name: /^5\b/ }).nth(1).check();
  await block.getByRole("textbox").nth(0).fill(comments[0]);
  await block.getByRole("textbox").nth(1).fill(comments[1]);
  const slider = block.getByRole("slider");
  await slider.focus();
  await slider.fill("6.5");
  await block.getByTestId(SUBMIT).click();
  await expect(
    block.getByText(SUBMITTED_TITLE, { exact: true }),
    "The submission was not accepted. Every denominator below counts this week as answered, so a " +
      "bounce here makes the rest of this drive assert the wrong arithmetic rather than fail.",
  ).toBeVisible();
}

/**
 * Assert one student's latest posted score and ledger.
 *
 * The percentage is compared as the number the platform decoded, because that is
 * what a gradebook holds: E3-03's canonical string goes over the wire as JSON, so
 * `"40.0"` arrives as `40`. The **ledger** is compared as exact text, because it
 * is a string all the way down and SPEC §3.4 fixes its form.
 */
function expectTheGradebookShows(
  entries: PostedEntry[],
  section: { label: string; context: string },
  subject: string,
  expected: { score: number; ledger: string },
  why: string,
): void {
  const posted = latestScoreFor(entries, section.context, subject);
  expect(
    posted,
    `The mock gradebook for ${section.label} holds no score at all for ${subject}. ${why}\n\n` +
      `Every entry this platform holds for that section is ${JSON.stringify(
        entries.filter((entry) => entry.lineItem.includes(section.context)),
      )}`,
  ).toBeDefined();
  expect(
    posted?.[SCORE_GIVEN],
    `${section.label}: the last score posted for ${subject} is ` +
      `${JSON.stringify(posted?.[SCORE_GIVEN])} and SPEC §3.4's arithmetic makes it ` +
      `${expected.score}. ${why}`,
  ).toBe(expected.score);
  expect(
    posted?.[SCORE_COMMENT],
    `${section.label}: the ledger posted for ${subject} reads\n` +
      `${String(posted?.[SCORE_COMMENT])}\n\nand SPEC §3.4's per-week ledger for this student ` +
      `is\n${expected.ledger}\n\n${why}\n\nA ledger that disagrees while the percentage matches ` +
      "is the denominator being assembled from a different set of weeks than the fraction was — " +
      "which is exactly what every enrollment row of this exit table is about.",
  ).toBe(expected.ledger);
}

// ---------------------------------------------------------------------------
// Setup and teardown.
// ---------------------------------------------------------------------------

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    for (const section of EVERY_SECTION) {
      placements.set(
        section.label,
        await placementInto(page, INSTRUCTOR, section.label),
      );
    }
    learnerPlacement = await placementInto(page, LEARNER, BIOL.label);
    expect(
      learnerPlacement,
      `The mock platform offers the instructor and the learner different resource links into ` +
        `${BIOL.label}. A section is provisioned per resource link, so two links are two sections ` +
        "and this drive would answer surveys in one while reading a gradebook from the other.",
    ).toBe(placements.get(BIOL.label));
  } finally {
    await context.close();
  }
});

test.afterAll(async ({ browser }) => {
  // The clock is the one piece of shared state this file can put back. The two
  // roster amendments cannot be undone — the work order settles that the mock
  // offers no reset action, because CI seeds a fresh stack per run and a local
  // re-run re-seeds — so the project split is what protects the neighbours, not
  // this hook.
  const context = await browser.newContext();
  try {
    await clearTheClock(await context.newPage());
  } finally {
    await context.close();
  }
});

// ---------------------------------------------------------------------------
// The deliverables this drive is built on, named before anything rests on them.
// ---------------------------------------------------------------------------

test("the console and the mock offer the two controls this drive needs", async ({
  page,
}) => {
  // **This test exists so that a tree without E3-08's two controls reds here,
  // naming them, instead of reding six cases later on an arithmetic assertion
  // that never had a chance to run** (`docs/MISTAKES.md` entry 44's spirit,
  // applied to a browser suite: a red must say what is missing).
  //
  // **The mutations it kills:** a roster-sync route added with no console button,
  // which leaves the control unreachable from the page and therefore unreachable
  // behind the same-origin check at all; and an amendment route that answers 404
  // to everything, which is indistinguishable from an unregistered path by status
  // alone.
  //
  // **The 422 is what proves the route exists, and it has to come first.** An
  // unknown section is answered 404, and so is a path nobody registered — so the
  // malformed-body case is the only one of the two whose status can only come
  // from a handler. The pair is asserted in that order for that reason.
  test.setTimeout(CASE_TIMEOUT_MS);

  await page.goto(DEV_CONSOLE_PATH);
  await expect(
    page.getByTestId(PASSBACK_RUN),
    `The development console carries no \`${PASSBACK_RUN}\` button. E3-07 shipped it; its absence ` +
      "here means this drive cannot run a passback at all, and it is asserted first so that a " +
      `missing \`${ROSTER_SYNC_RUN}\` below is distinguishable from a console serving nothing.`,
  ).toBeVisible();
  await expect(
    page.getByTestId(ROSTER_SYNC_RUN),
    `The development console carries no \`${ROSTER_SYNC_RUN}\` button. E3-08's work order adds a ` +
      "development-only, POST-only, same-origin-checked control that runs the roster sync for " +
      "every registered section synchronously and redirects back to the console — the " +
      "launch-triggered sync's debounce is five *real* minutes, so a drive on a pretended clock " +
      "cannot wait one out.",
  ).toBeVisible();

  const malformed = await amendTheRoster(page, { nonsense: true });
  expect(
    malformed,
    `\`POST ${ROSTER_AMENDMENTS_URL}\` with a body naming no section and no action answered ` +
      `${malformed}, and E3-08's work order settles 422. A 404 here is a route nobody registered, ` +
      "which is what this assertion is placed before the two below to tell apart.",
  ).toBe(422);

  const unknownSection = await amendTheRoster(page, {
    section: "NOPE-000-Z9ZZ",
    action: "add",
    ordinal: 99,
  });
  expect(
    unknownSection,
    `\`POST ${ROSTER_AMENDMENTS_URL}\` naming a section this platform does not seed answered ` +
      `${unknownSection}, and the work order settles 404. The malformed case above already ` +
      "established that the route is registered, so this 404 is the handler discriminating rather " +
      "than the router shrugging.",
  ).toBe(404);

  const alreadyThere = await amendTheRoster(page, {
    section: NURS.label,
    action: "add",
    ordinal: 1,
  });
  expect(
    alreadyThere,
    `\`POST ${ROSTER_AMENDMENTS_URL}\` adding an ordinal ${NURS.label} already holds answered ` +
      `${alreadyThere}, and the work order settles 409. Without this the add below could be ` +
      "silently re-enrolling somebody rather than adding a member the section has never had, " +
      "and exit row 6's whole subject is a member first seen in a later sync.",
  ).toBe(409);
});

// ---------------------------------------------------------------------------
// P1 — the sections are provisioned, the learner answers, and the first sweep
// runs. Exit rows 2 and 3 are set up here and read at P3.
// ---------------------------------------------------------------------------

test("P1: the three sections are provisioned and only the section with elapsed weeks is scored", async ({
  page,
}) => {
  // **What P1 establishes.** A staff launch into each section provisions it,
  // stores its AGS gradebook address and enqueues its line item (SPEC §7.3,
  // E3-05); the roster-sync control then reads all three rosters on the effective
  // clock, which is what dates every `nrps_call` row this drive's tier-3
  // comparison is measured against; and the learner answers BIOL week 1 in full
  // and MATH week 4 four items of five.
  //
  // **The assertion is SPEC §3.4's absent-versus-zero rule**, which is a rule
  // about a gradebook and not about a formula: "A section with no elapsed weeks
  // has no score posted yet — an absent score, never a posted zero, because a
  // zero in a gradebook is a statement about a student and only absence is true
  // before the first week closes." At this moment BIOL's week 1 window is *open*
  // and NURS has not started, while MATH has three closed weeks.
  //
  // **The mutation this kills:** a sweep that posts 0.0 for a section whose first
  // week has not closed, which writes a zero into every student's gradebook
  // column on the Friday of week one — a statement about a class that has not
  // been asked anything yet.
  //
  // **The absence is only worth asserting because of two things beside it**
  // (`docs/MISTAKES.md` entry 3): MATH's entries in the same sweep, which say the
  // sweep ran and posted; and the line-item guard below, which says BIOL and NURS
  // were postable — without it, "no BIOL score" is satisfied by a line item the
  // worker had not finished creating.
  test.setTimeout(CASE_TIMEOUT_MS);

  await setTheClockTo(page, P1);

  for (const section of EVERY_SECTION) {
    await launchAs(page, INSTRUCTOR, placements.get(section.label));
    await expect(
      page.getByTestId("pulse-landing-instructor"),
      `The instructor did not land on the instructor view launching into ${section.label}. A ` +
        "staff launch that was refused provisioned no section and stored no gradebook address, " +
        "so nothing below has a line item to post to.",
    ).toBeVisible();
  }

  // The sections reached this database through those launches, so they are
  // younger than the seed and carry no `survey_window` rows yet: they are
  // materialized up front (ADR 0111) by an hourly job. Run it rather than wait.
  deriveSurveyWindows();

  await clickTheControl(page, ROSTER_SYNC_RUN);

  // Every section postable before any absence is read. This is the premise guard
  // the paragraph above names, and it is also what makes the poll below a wait
  // for the *sweep* rather than for the worker.
  let lineItems: Record<string, string> = {};
  const ready = await waitFor(async () => {
    lineItems = Object.fromEntries(
      EVERY_SECTION.map((section) => [
        section.label,
        storedLineItem(section.context),
      ]),
    );
    return Object.values(lineItems).every((url) => url !== "none");
  });
  expect(
    ready,
    "At least one of the three sections still holds no `ags_line_item_url` after " +
      `${ASYNC_TIMEOUT_MS}ms: ${JSON.stringify(lineItems)}` +
      ". E3-05 creates one line item per section on its first staff launch, in the worker. The " +
      'sweep skips a section with no stored line item, so every "no score was posted" assertion ' +
      "in this file would otherwise be satisfied by a line item that had not been created yet.",
  ).toBe(true);

  // BIOL week 1 and MATH week 4 are both open at this minute, so the learner sees
  // a block for each. BIOL is answered in full; MATH is answered with the
  // instructor comment left blank — four items of five, which is exit row 2's
  // fraction and §3.3's "a blank optional comment costs its item".
  await launchAs(page, LEARNER, learnerPlacement);
  const biolWeekOne = page.getByTestId(`survey-section-${BIOL.code}`);
  const mathWeekFour = page.getByTestId(`survey-section-${MATH.code}`);
  await expect(
    biolWeekOne,
    "The learner has no open survey for BIOL-215-R3WW at 2026-09-11 19:00, when week 1 of a " +
      "cohort starting Monday 2026-09-07 has its window open (SPEC §3.1: Friday 18:00 to Sunday " +
      "23:59:59).",
  ).toBeVisible();
  await expect(
    mathWeekFour,
    "The learner has no open survey for MATH-140-E1FF at 2026-09-11 19:00, when week 4 of a " +
      "six-week cohort starting Monday 2026-08-17 has its window open. The learner is enrolled " +
      "in all three seeded sections, so a landing showing only one of them is a read path " +
      "narrowing to a single section rather than a window that is shut.",
  ).toBeVisible();

  await answerTheWeek(biolWeekOne, [INSTRUCTOR_COMMENT, COURSE_COMMENT]);
  await answerTheWeek(mathWeekFour, ["", COURSE_COMMENT]);

  const settled = await passbackUntil(page, async () => {
    const entries = await postedEntries(page);
    return scoresFor(entries, MATH.context, LEARNER).length > 0;
  });
  expect(
    settled,
    `No score was posted for the learner against ${MATH.label} within ${ASYNC_TIMEOUT_MS}ms of ` +
      "the first passback. Three of that section's six weeks have closed by 2026-09-11, so §3.4 " +
      "has something to post, and the trigger was pulled repeatedly.",
  ).toBe(true);

  const entries = await postedEntries(page);

  expectTheGradebookShows(
    entries,
    MATH,
    LEARNER,
    {
      score: P1_MATH_LEARNER_SCORE,
      ledger: P1_MATH_LEARNER_LEDGER,
    },
    "MATH-140-E1FF runs six weeks from Monday 2026-08-17, so at 2026-09-11 19:00 weeks 1, 2 and " +
      "3 have closed and week 4 is still open. The learner has just answered week 4 and nothing " +
      "else, so no *elapsed* week carries a completed item: 0 of 15, which is 0.0%. Week 4 must " +
      "not appear in the ledger at all — a week whose window is open is not yet in the " +
      "denominator.",
  );

  for (const section of [BIOL, NURS]) {
    const posted = entries.filter((entry) =>
      entry.lineItem.includes(section.context),
    );
    expect(
      posted,
      `${section.label} has ${posted.length} scores in the platform's log at 2026-09-11 19:00: ` +
        `${JSON.stringify(posted)}. Neither section has a closed week yet — BIOL's week 1 window ` +
        "is open until Sunday the 13th and NURS does not begin until the 28th — and SPEC §3.4 is " +
        'explicit that this state is an *absent* score and never a posted zero, "because a zero ' +
        "in a gradebook is a statement about a student and only absence is true before the first " +
        'week closes". The section holds a line item (asserted above) and the sweep did post to ' +
        `${MATH.label} in this same run, so this is not a sweep that did nothing.`,
    ).toEqual([]);
  }
});

// ---------------------------------------------------------------------------
// P2 — one more answered week, so the learner's BIOL numerator is 10 and not 5.
// ---------------------------------------------------------------------------

test("P2: the learner answers BIOL week 2 in full", async ({ page }) => {
  // No assertion about a gradebook here: this moment exists so that at P3 the
  // learner has two fully answered weeks out of two elapsed ones, which is the
  // only shape in which exit row 1's 100% is reachable at all.
  //
  // **MATH week 5 is deliberately left unanswered**, and its window is open at
  // this minute. That is what makes exit row 3 — "a missed week: zero of that
  // week's items, the week still in the denominator" — a real case at P3 rather
  // than an arithmetic identity.
  test.setTimeout(CASE_TIMEOUT_MS);

  await setTheClockTo(page, P2);
  const block = await landOnTheSurvey(page, BIOL.code);
  await answerTheWeek(block, [INSTRUCTOR_COMMENT, COURSE_COMMENT]);
});

// ---------------------------------------------------------------------------
// P3 — exit rows 1, 2 and 3, and the first half of row 7's setup.
// ---------------------------------------------------------------------------

test("P3: a full record scores 100%, a four-of-five week scores its fraction, a missed week keeps its denominator", async ({
  page,
}) => {
  // **Exit rows 1, 2 and 3, all three read off one sweep.**
  //
  //   - row 1: the learner answered every item of every elapsed BIOL week → 100%
  //   - row 2: the learner's MATH week 4 is four items of five, and the ledger
  //     says so in SPEC §3.4's own words
  //   - row 3: MATH weeks 1, 2, 3 and 5 were missed and each contributes 0 of 5
  //     rather than dropping out
  //
  // **The mutations these kill:**
  //   1. *The superseded formula* — valid weeks ÷ weeks elapsed — under which the
  //      learner's four-of-five week is a failed week and MATH reads 0.0 rather
  //      than 16.0. That rule was replaced on 2026-09-04 and this is the exit's
  //      own check that the replacement reached a real gradebook.
  //   2. *A numerator that credits a whole week for any submission at all*, which
  //      makes MATH 5 of 25 = 20.0.
  //   3. *A denominator assembled from the weeks the student responded in*, which
  //      drops the four missed MATH weeks and reads 4 of 5 = 80.0 — a student who
  //      answered one week in six scoring higher than one who answered two in two.
  //   4. *A ledger numbered on the term axis.* MATH's course week 4 is term week
  //      4 by coincidence, but BIOL's course week 1 is term week 4, so the BIOL
  //      ledger below reads `Week 1` under §2.2's course axis and `Week 4` under
  //      the term axis — which is why row 1's ledger is asserted as text and not
  //      only as a percentage.
  //   5. *A late add credited from the section's start*, caught by student 04
  //      having no entry at all: his first credited week is 4, and no week of his
  //      has elapsed yet.
  //
  // **The absences are paired.** Student 04's silence sits beside student 01's
  // posted zero in the same sweep, so "no entry" is a statement about his
  // denominator rather than about a sweep that skipped the section.
  test.setTimeout(CASE_TIMEOUT_MS);

  await setTheClockTo(page, P3);

  const settled = await passbackUntil(page, async () => {
    const entries = await postedEntries(page);
    return scoresFor(entries, BIOL.context, LEARNER).length > 0;
  });
  expect(
    settled,
    `No score was posted for the learner against ${BIOL.label} within ${ASYNC_TIMEOUT_MS}ms of a ` +
      "passback at 2026-09-21 09:00, when weeks 1 and 2 of that section have closed.",
  ).toBe(true);

  const entries = await postedEntries(page);

  expectTheGradebookShows(
    entries,
    BIOL,
    LEARNER,
    {
      score: P3_BIOL_LEARNER_SCORE,
      ledger: P3_BIOL_LEARNER_LEDGER,
    },
    "Exit row 1. BIOL-215-R3WW runs twelve weeks from Monday 2026-09-07, so at 2026-09-21 09:00 " +
      "weeks 1 (closed 09-13) and 2 (closed 09-20) have elapsed and week 3 is still open. The " +
      "learner answered both in full: 5 + 5 = 10 completed items over 2 × 5 = 10, which is " +
      "10/10 × 100 = 100.0. The ledger names the **course** week — this section starts in term " +
      "week 4, so a ledger reading `Week 4` and `Week 5` is the term axis in the wrong place.",
  );

  expectTheGradebookShows(
    entries,
    MATH,
    LEARNER,
    {
      score: P3_MATH_LEARNER_SCORE,
      ledger: P3_MATH_LEARNER_LEDGER,
    },
    "Exit rows 2 and 3. MATH-140-E1FF has five closed weeks at 2026-09-21 09:00 (week 5 closed " +
      "09-20) and week 6 open. The learner answered week 4 only, leaving one optional comment " +
      "blank: 4 completed items over 5 × 5 = 25, which is 4/25 × 100 = 16.0. Weeks 1, 2, 3 and 5 " +
      'each contribute 0 of 5 and their full width to the denominator — §3.4: "0 of N, never ' +
      "omitted from the denominator\" — and week 4 reads `4 of 5 items`, which is §3.4's own " +
      "example of the line.",
  );

  expectTheGradebookShows(
    entries,
    BIOL,
    BIOL_DAY_ONE,
    {
      score: P3_BIOL_SILENT_SCORE,
      ledger: P3_BIOL_SILENT_LEDGER,
    },
    "A day-one member of BIOL-215-R3WW who answered nothing: 0 completed over 2 × 5 = 10, which " +
      "is 0.0. He is asserted here as the positive control for student 04's absence below — " +
      'without somebody in this section posting a zero, "the late add has no entry" is satisfied ' +
      "by a sweep that skipped the section.",
  );

  const lateAdd = scoresFor(entries, BIOL.context, BIOL_LATE_ADD);
  expect(
    lateAdd,
    `Exit row 4, the "not yet" half. ${BIOL_LATE_ADD} carries \`opened_at\` 2026-09-28, so §3.4's ` +
      "first tier starts his denominator at the earliest course week whose window closes at or " +
      "after that instant — week 4, which closes 2026-10-04. At 2026-09-21 no week of his has " +
      "elapsed, so he has no score at all rather than a zero. A score here means the denominator " +
      "was taken from the section's start date and his three missing weeks are being counted " +
      `against him. The platform holds ${JSON.stringify(lateAdd)}.`,
  ).toEqual([]);

  // Exit row 7's other half is set up here: the learner leaves MATH-140-E1FF on
  // this day, and the sync ingests the platform's own end date for it. Nothing is
  // asserted about the drop until P4, where a classmate posting in the same sweep
  // makes his silence mean something.
  //
  // The count is recorded now, on the reading whose latest entry was just
  // asserted to be the 16.0 one, so P4 compares against what the platform held at
  // the moment of the drop rather than against a total this file worked out.
  learnerMathEntriesWhenHeWasDropped = scoresFor(
    entries,
    MATH.context,
    LEARNER,
  ).length;

  const dropped = await amendTheRoster(page, {
    section: MATH.label,
    action: "drop",
    user_id: LEARNER,
    closed_at: MATH_DROP_INSTANT,
  });
  expect(
    dropped,
    `\`POST ${ROSTER_AMENDMENTS_URL}\` dropping the learner from ${MATH.label} answered ` +
      `${dropped} and the work order settles 200. Without the drop, exit row 7's second half has ` +
      "no case to run against and P4 would be asserting that an enrolled student stopped being " +
      "posted.",
  ).toBe(200);
  await clickTheControl(page, ROSTER_SYNC_RUN);
});

// ---------------------------------------------------------------------------
// P4 — exit rows 4, 5 and the drop's silence beside a classmate who posts.
// ---------------------------------------------------------------------------

test("P4: the late add starts at his own week, the undated member starts at the section start, and the dropped learner stops", async ({
  page,
}) => {
  // **Exit rows 4, 5 and 7 (second half), plus the setup for row 6.**
  //
  //   - row 4: student 04's first entry names week 4 and **only** week 4 — the
  //     boundary asserted in both directions, week 4 present and weeks 1–3 absent
  //   - row 5: the windowless NURS member's ledger starts at week 1 and equals a
  //     platform-dated classmate's, which is §3.4's accepted under-credit
  //     asserted as the intended behaviour
  //   - row 7: the learner, dropped from MATH on 09-21, gets no new entry while a
  //     classmate in the same section gets one in the same sweep
  //
  // **The mutations these kill:**
  //   1. *A late add's denominator taken from the section's start*, which makes
  //      student 04's first ledger four lines instead of one and charges him for
  //      three weeks he was not enrolled for. Caught by the ledger being asserted
  //      as the whole string rather than by the percentage, which is 0.0 either
  //      way — this is the row where a percentage-only assertion sees nothing.
  //   2. *An undated member treated as having no enrolled weeks*, or credited
  //      from the day Pulse first saw them, either of which makes the windowless
  //      member differ from her classmate. §3.4 settles that they are
  //      indistinguishable and accepts the under-credit; the equality is the
  //      assertion.
  //   3. *The drop rule dropped from the sweep*, which re-posts a departed
  //      student every Monday for the rest of term. Caught by the pair: the
  //      learner silent and his classmate posting in one run.
  //   4. *A comparison over the percentage alone rather than over the (score,
  //      ledger) pair* (ADR 0137). The MATH classmate's percentage is 0.0 at P3
  //      and 0.0 at P4; only his ledger changed, from five lines to six. Under a
  //      percentage-only comparison he does not re-post, the positive control
  //      vanishes, and the learner's silence stops meaning anything — so this
  //      case is what makes mutation 3's proof sound.
  //
  // **Why the learner's silence is not confusable with an unchanged value.** Had
  // he stayed enrolled he would be 4 of 30 = 13.3, which is not the 16.0 the
  // platform already holds — so a sweep that recomputed and posted would have
  // written a different number, and the count of his entries is what says it did
  // not.
  test.setTimeout(CASE_TIMEOUT_MS);

  await setTheClockTo(page, P4);

  // Exit row 6's setup: a member the platform never dated, added to NURS after
  // that section's first sync and first seen by the sync run below.
  const added = await amendTheRoster(page, {
    section: NURS.label,
    action: "add",
    ordinal: NURS_LATE_ADD_ORDINAL,
  });
  expect(
    added,
    `\`POST ${ROSTER_AMENDMENTS_URL}\` adding ordinal ${NURS_LATE_ADD_ORDINAL} to ${NURS.label} ` +
      `answered ${added} and the work order settles 201.`,
  ).toBe(201);
  await clickTheControl(page, ROSTER_SYNC_RUN);

  // **The premise exit row 6 rests on**, asserted rather than assumed: §3.4's
  // third tier fires only for a student "who first appears in a roster sync later
  // than their section's first sync", so this section's earliest recorded call
  // has to predate today's. The dev control stamps its `nrps_call` rows on the
  // effective clock (E3-08's work order), which is what bounds this at all — a
  // sync log written on real time would put the comparison at the mercy of the
  // calendar date CI happens to run on.
  const firstSync = firstSyncDayOf(NURS.context);
  expect(
    firstSync < "2026-10-05",
    `${NURS.label}'s earliest \`nrps_call\` is dated ${firstSync}, which is not before the ` +
      "2026-10-05 sync that first saw the new member. §3.4's third tier only applies to a member " +
      "first seen in a sync *later* than the section's first, so with these two on the same day " +
      "the assertions below are about the undated tier and not the later-sync one — the same " +
      "answer for a different reason.",
  ).toBe(true);

  const settled = await passbackUntil(page, async () => {
    const entries = await postedEntries(page);
    return scoresFor(entries, NURS.context, NURS_DAY_ONE).length > 0;
  });
  expect(
    settled,
    `No score was posted for ${NURS_DAY_ONE} within ${ASYNC_TIMEOUT_MS}ms of a passback at ` +
      "2026-10-05 09:00, when week 1 of a cohort starting Monday 2026-09-28 has closed.",
  ).toBe(true);

  const entries = await postedEntries(page);

  expectTheGradebookShows(
    entries,
    BIOL,
    LEARNER,
    {
      score: P4_BIOL_LEARNER_SCORE,
      ledger: ledgerOf([
        [1, 5],
        [2, 5],
        [3, 0],
        [4, 0],
      ]),
    },
    "Four BIOL weeks have elapsed at 2026-10-05 (week 4 closed 10-04). The learner answered weeks " +
      "1 and 2 in full and missed 3 and 4: 10 completed over 4 × 5 = 20, which is " +
      "10/20 × 100 = 50.0.",
  );

  expectTheGradebookShows(
    entries,
    BIOL,
    BIOL_LATE_ADD,
    {
      score: P4_BIOL_LATE_ADD_SCORE,
      ledger: P4_BIOL_LATE_ADD_LEDGER,
    },
    "Exit row 4. `opened_at` 2026-09-28 puts this student's first enrolled course week at 4 — " +
      "the earliest week whose window closes at or after that instant, week 3 having closed " +
      "09-27 — and week 4 is the only week of his that has elapsed at 2026-10-05. So the whole " +
      "ledger is one line: 0 completed over 1 × 5 = 5, which is 0.0. **Weeks 1, 2 and 3 must not " +
      "appear at all**; a four-line ledger here is a denominator taken from the section's start " +
      "date, and its percentage is 0.0 either way.",
  );

  const classmate = latestScoreFor(entries, NURS.context, NURS_DAY_ONE);
  expectTheGradebookShows(
    entries,
    NURS,
    NURS_DAY_ONE,
    {
      score: P4_NURS_SCORE,
      ledger: P4_NURS_LEDGER,
    },
    "The platform-dated NURS member this row compares against. `opened_at` 2026-09-28 is week " +
      "1's own Monday, so his denominator starts at week 1, and week 1 is the only NURS week " +
      "closed at 2026-10-05: 0 of 5, which is 0.0.",
  );
  expectTheGradebookShows(
    entries,
    NURS,
    NURS_WINDOWLESS,
    {
      score: P4_NURS_SCORE,
      ledger: P4_NURS_LEDGER,
    },
    "Exit row 5. This member carries no platform enrollment dates at all — `app.nrps` omits the " +
      'extension key entirely for her — and §3.4 says a student the platform never dated "counts ' +
      "as enrolled from the section's start date\", the later-sync exception not reaching her " +
      "because she was on the roster at the first sync. So her ledger starts at week 1, exactly " +
      "like the dated classmate above. **This equality is the intended behaviour and not a " +
      'defect**: §3.4 accepts the under-credit outright, "because no rule can recover data the ' +
      'platform never supplied".',
  );
  expect(
    latestScoreFor(entries, NURS.context, NURS_WINDOWLESS),
    "The windowless NURS member and her platform-dated classmate were posted different scores. " +
      "Exit row 5 is an assertion that they are indistinguishable, which is what §3.4 settles for " +
      `a student the platform never dated. The classmate holds ${JSON.stringify(classmate)}.`,
  ).toEqual(classmate);

  const nursLateAdd = scoresFor(entries, NURS.context, NURS_LATE_ADD);
  expect(
    nursLateAdd,
    `Exit row 6, the "not yet" half. ${NURS_LATE_ADD} was first seen in a sync dated 2026-10-05, ` +
      "later than this section's first, so §3.4's third tier credits him \"from the week of that " +
      'sync" — the first week whose window closes on or after 10-05, which is week 2, closing ' +
      "10-11. No week of his has elapsed at 2026-10-05, so he has no score. A zero here means he " +
      "was credited from week 1 (the undated tier) or from the section start, and either charges " +
      `him for a week he was not on the roster for. The platform holds ${JSON.stringify(nursLateAdd)}.`,
  ).toEqual([]);

  // Exit row 7, second half — the pair. The classmate first, so the learner's
  // silence is measured against a sweep that demonstrably posted to this section
  // in this run.
  expectTheGradebookShows(
    entries,
    MATH,
    MATH_CLASSMATE,
    {
      score: P4_MATH_CLASSMATE_SCORE,
      ledger: P4_MATH_CLASSMATE_LEDGER,
    },
    "The positive control for the drop below. All six MATH weeks have closed by 2026-10-05, so " +
      "this classmate is 0 of 30 = 0.0 — the same percentage he held at P3 and a **different " +
      "ledger**, five lines having become six. ADR 0137 compares the (score, ledger) pair, so he " +
      "re-posts; under a percentage-only comparison he would not, and the learner's silence " +
      "below would then be indistinguishable from a sweep that posted nothing to this section.",
  );

  const learnerMath = scoresFor(entries, MATH.context, LEARNER);
  expect(
    learnerMathEntriesWhenHeWasDropped,
    "The platform held no scores at all for the learner in MATH-140-E1FF at the moment he was " +
      'dropped, so "no new entry since then" is a claim about nothing. P3 is where his 16.0 is ' +
      "posted and asserted.",
  ).toBeGreaterThan(0);
  expect(
    learnerMath.length,
    `Exit row 7. The learner was dropped from ${MATH.label} on 2026-09-21, when the platform held ` +
      `${learnerMathEntriesWhenHeWasDropped} scores for him there; it now holds ` +
      `${learnerMath.length}: ${JSON.stringify(learnerMath)}. SPEC §3.4: "Drops: scores stop ` +
      'updating." A further entry is a sweep that went on recomputing a departed student, and it ' +
      "would be a *different* number: with all six weeks elapsed he would be 4 of 30 = 13.3, not " +
      "the 16.0 already in the column. His classmate above posted a new entry in this same sweep, " +
      "so this is not a section the sweep skipped.",
  ).toBe(learnerMathEntriesWhenHeWasDropped);
  expect(
    learnerMath[learnerMath.length - 1]?.[SCORE_GIVEN],
    "The value the platform holds for the dropped learner is not the one his last successful " +
      "post sent. §3.4 gives the LMS the column — Pulse neither blanks it nor writes a final " +
      "zero — so the 16.0 posted at P3 is what must still stand. Read beside the count above: " +
      "the count says nothing new arrived and this says the thing that is there is the right one.",
  ).toBe(P3_MATH_LEARNER_SCORE);

  // The other member of `with_the_add_and_the_drop`. His platform record ends
  // 2026-10-19, which is still ahead of this clock, so he is enrolled and scored
  // exactly like the classmate who answered nothing — see this file's header for
  // why that is the settled behaviour and not the absence the work order
  // predicted. His stop is asserted at P6.
  const stillEnrolled = latestScoreFor(entries, BIOL.context, BIOL_DROPPED);
  expect(
    stillEnrolled,
    `${BIOL_DROPPED} is reported \`Inactive\` by the platform with \`closed_at\` 2026-10-19, and ` +
      "the roster sync records that date as his `ended_on` rather than the day it ran. The sweep " +
      "posts while `ended_on >= clock.today`, so on 2026-10-05 he is still enrolled and still " +
      'scored. No entry here means a roster status of `Inactive` is being read as "gone now", ' +
      "which withholds two weeks of grade updates from a student the LMS still has on its books.",
  ).toBeDefined();
  expect(
    stillEnrolled,
    "The still-enrolled dropped member was scored differently from a day-one classmate who also " +
      "answered nothing. Both carry `opened_at` 2026-09-07 and neither submitted anything, so " +
      "their denominators and numerators are identical; a difference is the drop leaking into the " +
      "formula, which ADR 0131 keeps out of it.",
  ).toEqual(latestScoreFor(entries, BIOL.context, BIOL_DAY_ONE));
});

// ---------------------------------------------------------------------------
// P5 — exit row 6, and the last value the dropped BIOL member is given.
// ---------------------------------------------------------------------------

test("P5: the member first seen in a later sync is credited from that week and no earlier", async ({
  page,
}) => {
  // **Exit row 6, in both directions**: the NURS member added at P4 gets his
  // first entry now, and its ledger names week 2 and **only** week 2.
  //
  // **The mutations this kills:**
  //   1. *The later-sync tier missing altogether*, so an undated member added in
  //      week two is credited from the section's start — a two-line ledger, and a
  //      student charged for a week before they were on the roster.
  //   2. *The tier credited from the week of the sync's own date rather than from
  //      the first week whose window closes on or after it.* His sync ran
  //      2026-10-05, which is inside NURS week 2 (10-05 to 10-11); week 1 had
  //      already closed on 10-04. Both readings give week 2 here, which is why
  //      this case alone does not separate them — what it does separate is either
  //      of them from the section-start reading.
  //   3. *A late add's own week omitted rather than counted as 0 of 5*, which
  //      would leave him with no entry at all at this moment.
  //
  // **The pair.** His single-line ledger is asserted beside the two-line ledger
  // of a member who has been there since the section started, in the same sweep —
  // so "week 1 is absent" is a statement about his denominator and not about a
  // ledger that renders one line for everybody.
  test.setTimeout(CASE_TIMEOUT_MS);

  await setTheClockTo(page, P5);

  const settled = await passbackUntil(page, async () => {
    const entries = await postedEntries(page);
    return scoresFor(entries, NURS.context, NURS_LATE_ADD).length > 0;
  });
  expect(
    settled,
    `No score was posted for ${NURS_LATE_ADD} within ${ASYNC_TIMEOUT_MS}ms of a passback at ` +
      "2026-10-12 09:00. NURS week 2 closed on 2026-10-11 and that is the first week §3.4 credits " +
      "him with, so this is the moment his first entry becomes due. Silence here is either the " +
      "later-sync tier crediting him from a week that has not elapsed, or the sync never having " +
      "enrolled him at all.",
  ).toBe(true);

  const entries = await postedEntries(page);

  expectTheGradebookShows(
    entries,
    NURS,
    NURS_LATE_ADD,
    {
      score: P5_NURS_LATE_ADD_SCORE,
      ledger: P5_NURS_LATE_ADD_LEDGER,
    },
    "Exit row 6. First seen in a roster sync dated 2026-10-05, later than this section's first " +
      'sync, so §3.4 credits him "from the week of that sync": the first week whose window closes ' +
      "on or after 10-05 is week 2, closing 10-11. Exactly one week of his has elapsed at " +
      "2026-10-12, so the whole ledger is one line: 0 of 5, which is 0.0. **Week 1 must not " +
      "appear** — it closed before he was on the roster, and its percentage would be 0.0 either " +
      "way, so the ledger is the only thing that can tell the two apart.",
  );

  expectTheGradebookShows(
    entries,
    NURS,
    NURS_WINDOWLESS,
    {
      score: 0,
      ledger: ledgerOf(unanswered(1, 2)),
    },
    "The pair for the assertion above: a member of the same section, in the same sweep, whose " +
      "ledger runs from week 1. Two NURS weeks have closed by 2026-10-12, so hers is 0 of 10 = " +
      '0.0 across two lines. Without her, "the late add\'s ledger has one line" is satisfied by a ' +
      "ledger that renders one line for everybody.",
  );

  expectTheGradebookShows(
    entries,
    BIOL,
    LEARNER,
    {
      score: P5_BIOL_LEARNER_SCORE,
      ledger: ledgerOf([[1, 5], [2, 5], ...unanswered(3, 5)]),
    },
    "Five BIOL weeks have elapsed at 2026-10-12 (week 5 closed 10-11). The learner answered weeks " +
      "1 and 2 in full: 10 completed over 5 × 5 = 25, which is 10/25 × 100 = 40.0.",
  );

  expectTheGradebookShows(
    entries,
    BIOL,
    BIOL_DROPPED,
    {
      score: P5_BIOL_SILENT_SCORE,
      ledger: P5_BIOL_SILENT_LEDGER,
    },
    "The seeded BIOL drop, still enrolled: his platform `closed_at` is 2026-10-19, a week ahead " +
      "of this clock. 0 completed over 5 × 5 = 25, which is 0.0, across five ledger lines. **This " +
      "is the value P6 requires to still be standing**, and the five-line ledger is what " +
      "distinguishes it from the seven-line one his classmates get there — both percentages are " +
      "0.0, so the ledger is the only thing that can say a stale entry is stale.",
  );
});

// ---------------------------------------------------------------------------
// P6 — exit row 7 with its own seeded member: the drop takes effect, and the
// last posted value stands.
// ---------------------------------------------------------------------------

test("P6: the seeded dropped member stops being posted while his classmates go on", async ({
  page,
}) => {
  // **Exit row 7, driven with the member the ticket names.** E3-08's table says
  // "the dropped member of `with_the_add_and_the_drop` — the score stops updating
  // and the last posted value stands", and that member's platform record ends on
  // 2026-10-19. Every earlier moment in this drive is before that date, so this
  // is the first one at which the rule has anything to do. The learner's drop
  // from MATH at P4 is the same rule on a different member; this is the seeded
  // case the ticket names, and the two together are the rule from both ends of
  // the same `AND`.
  //
  // **The mutations this kills:**
  //   1. *The live-enrollment predicate dropped from the sweep*, which re-posts a
  //      departed student every Monday for the rest of the term.
  //   2. *The predicate written `ended_on > clock.today` or against the wrong
  //      clock*, which this case cannot fully separate — that boundary is one day
  //      wide and belongs to
  //      `test_a_dropped_students_score_stops_updating.py`, which poses both
  //      sides of it a day apart. What this case adds is that the rule survives
  //      the whole path: a platform roster, a real sync, a real `ended_on`.
  //   3. *A final zero, or a blanked column, written on the drop.* §3.4 gives the
  //      LMS the column outright — "the LMS owns what happens to it" — so the
  //      value must be the one his last successful post sent and nothing else.
  //
  // **The counts are taken before the sweep and compared after it**, because a
  // gradebook cannot tell an absent post from an idempotent one: his percentage
  // is 0.0 before and would be 0.0 after. What changes under the mutation is the
  // *number of entries* and the ledger's length — and both are read here.
  //
  // **The pair is in the same sweep.** Two classmates who also answered nothing
  // must gain a new entry with a seven-line ledger while he gains none.
  test.setTimeout(CASE_TIMEOUT_MS);

  const before = await postedEntries(page);
  const droppedBefore = scoresFor(before, BIOL.context, BIOL_DROPPED).length;
  const classmateBefore = scoresFor(before, BIOL.context, BIOL_DAY_ONE).length;
  expect(
    droppedBefore,
    `${BIOL_DROPPED} has no scores at all before this moment, so "his last posted value stands" ` +
      "is a claim about nothing and the count comparison below is satisfied by a student the " +
      "sweep has never posted for. P5 is where his last entry is written.",
  ).toBeGreaterThan(0);

  await setTheClockTo(page, P6);

  const settled = await passbackUntil(page, async () => {
    const entries = await postedEntries(page);
    return (
      scoresFor(entries, BIOL.context, BIOL_DAY_ONE).length > classmateBefore
    );
  });
  expect(
    settled,
    `${BIOL_DAY_ONE} gained no new score within ${ASYNC_TIMEOUT_MS}ms of a passback at ` +
      "2026-10-26 09:00, when BIOL weeks 6 and 7 have closed since the last sweep. His ledger has " +
      "grown from five lines to seven, so ADR 0137's (score, ledger) comparison has something " +
      "to re-post even though his percentage is 0.0 either way. Without this the silence asserted " +
      "below is a sweep that did nothing, which is the whole failure mode this pair exists for.",
  ).toBe(true);

  const after = await postedEntries(page);

  expectTheGradebookShows(
    after,
    BIOL,
    BIOL_DAY_ONE,
    {
      score: 0,
      ledger: P6_BIOL_SILENT_LEDGER,
    },
    "The positive control. Seven BIOL weeks have elapsed at 2026-10-26 (week 7 closed 10-25) and " +
      "this day-one member answered none of them: 0 completed over 7 × 5 = 35, which is 0.0, " +
      "across seven ledger lines.",
  );

  expectTheGradebookShows(
    after,
    BIOL,
    LEARNER,
    {
      score: P6_BIOL_LEARNER_SCORE,
      ledger: ledgerOf([[1, 5], [2, 5], ...unanswered(3, 7)]),
    },
    "The second half of the control, and the one whose percentage moves. The learner answered " +
      "weeks 1 and 2 in full: 10 completed over 7 × 5 = 35, which is 10/35 × 100 = 28.5714…, " +
      "rounded half up to one decimal as 28.6 (E3-03's canonical string rule). A value of 28.5 " +
      "here is banker's rounding or truncation reaching the wire.",
  );

  const droppedAfter = scoresFor(after, BIOL.context, BIOL_DROPPED);
  expect(
    droppedAfter.length,
    `Exit row 7. ${BIOL_DROPPED} left ${BIOL.label} on 2026-10-19 and the platform holds ` +
      `${droppedAfter.length} scores for him, against ${droppedBefore} before this sweep. SPEC ` +
      '§3.4: "Drops: scores stop updating." Two classmates gained an entry in this same run, so ' +
      "a new entry here is the live-enrollment predicate missing from the sweep rather than a " +
      `sweep that skipped the section. The whole log for him is ${JSON.stringify(droppedAfter)}.`,
  ).toBe(droppedBefore);

  expectTheGradebookShows(
    after,
    BIOL,
    BIOL_DROPPED,
    {
      score: P5_BIOL_SILENT_SCORE,
      ledger: P5_BIOL_SILENT_LEDGER,
    },
    'Exit row 7, the "last posted value stands" half. The value the platform holds for him must ' +
      "still be the one his last successful post sent at 2026-10-12: 0 of 25 across five ledger " +
      "lines. **The percentage cannot tell this apart from a fresh post** — a student who " +
      "answered nothing is 0.0 at every moment — so the ledger is the assertion: seven lines here " +
      "means the sweep recomputed and re-posted a departed student, and Pulse neither blanks the " +
      "column nor writes a final zero, because §3.4 gives the LMS what happens to it.",
  );
});

// ---------------------------------------------------------------------------
// Small shared instruments.
// ---------------------------------------------------------------------------

/** Poll `settled` on this file's shared budget, and answer whether it ever held. */
async function waitFor(settled: () => Promise<boolean>): Promise<boolean> {
  const deadline = Date.now() + ASYNC_TIMEOUT_MS;
  for (;;) {
    if (await settled()) return true;
    if (Date.now() >= deadline) return false;
    await new Promise((wake) => setTimeout(wake, ASYNC_RETRY_MS));
  }
}

/**
 * The date of the earliest roster call recorded against one section, as text.
 *
 * `nrps_call` is SPEC §6.1's log at the grain of one HTTP call to a platform
 * service, and §3.4's third tier is measured against the day of the earliest one
 * a section has. Read as a date string so a comparison in this file is a
 * comparison of ISO days and not of instants in whichever zone `psql` renders.
 */
function firstSyncDayOf(contextId: string): string {
  const answered = databaseStatement(
    "select to_char(min(c.called_at) at time zone 'America/New_York', 'YYYY-MM-DD') " +
      "from nrps_call c join section s on s.id = c.section_id " +
      `where s.lms_context_id = ${quoted(contextId)};`,
  );
  expect(
    answered,
    `\`nrps_call\` holds no row for the section bound to ${contextId}, so this section has never ` +
      "been synced and §3.4's third tier has no first sync to compare against. The dev roster " +
      "sync control is what writes these rows on the effective clock.",
  ).not.toBe("");
  return answered;
}
