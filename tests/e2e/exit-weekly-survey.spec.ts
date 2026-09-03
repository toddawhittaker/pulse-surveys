// E2-13, exit clause 1 — SPEC §14.3, E2: "a student submits a valid response".
//
// **What this file proves, and what it deliberately leaves alone.** E2's exit
// line has four clauses. Clause 2 ("it was okay" is bounced with immediate
// feedback) and the closed-window states this epic also rests on are already
// driven end to end by `student-survey.spec.ts` — its second, fourth and fifth
// tests — and that spec is in the enforcing Playwright gate. Re-driving them here
// would put a second copy of the same proof in the suite and would make a red
// ambiguous about which file owned it. So this file covers only what nothing
// asserts today:
//
//   - **Test A, clause 1 itself.** A valid submission through the browser, and
//     then the rows: exactly one `response` for this student, this section and
//     this week, and a `classification` for each comment that was submitted,
//     carrying a real audit pair. A screen that says "Your pulse is in" over a
//     database that stored nothing satisfies every browser-side assertion there
//     is, and clause 1 is about the response existing.
//   - **Test B, the fail-open submit.** SPEC §3.3: "on provider timeout, the
//     heuristic floor applies and the submission is accepted, then classified
//     async (fail open, never block a student on an outage)." The epic's
//     correctness rests on it and no browser has ever driven it.
//
// **A and B are a boundary pair, and neither is worth much alone.** They stand on
// either side of the same line — the audit pair a classification is stamped with.
// A submission whose comments the provider answered carries a real prompt version
// and a real model ID; a submission the provider stalled past the budget carries
// ADR 0054's floor markers, `character-floor` and `no-model`. Test A alone passes
// against an implementation that floors *nothing* — one whose synchronous budget
// outlasts any provider, or one that refuses a student on timeout instead of
// accepting them. Test B alone passes against one that floors *everything*,
// including a stack calling no provider at all. Read together they say the two
// paths are distinguishable in the record, which is the whole of what ADR 0054 is
// for.
//
// **The pre-existing green spec every helper shape here is borrowed from is
// `student-survey.spec.ts`.** The landing helper, the serial/`beforeAll` clock
// discipline, the `beforeEach` week clear and its three-statement delete order,
// the form helpers and the section testids are all its, copied rather than
// re-invented: it is this suite's proven-green baseline for the survey surface,
// and a new exit spec that solved those problems again would be asserting against
// its own machinery. The two e2e traps the memory records — Chromium's Local
// Network Access rules around the synthetic-iframe wrapper, and the dev cookies
// being `SameSite=None` without `Secure`, so the session rides the Bearer path —
// are navigated by taking `support/doors.ts` exactly as the E1 exit specs take
// it, and by never reaching for the cookie jar.
//
// **The clock moves, which is shared state.** The stack has one `clock_override`
// row and `playwright.config.ts` pins `workers` to 1 for that reason. The
// override is set once in `beforeAll` and cleared in `afterAll`, so a failing
// assertion cannot leave the stack in October 2026 for whatever runs next. This
// file also clears the section's week on the way out as well as on the way in, so
// the later-running `student-survey.spec.ts` inherits nothing from it.
//
// **Every expectation below is a literal.** The week numbers are transcribed from
// the seeded calendar, the floor markers from ADR 0054, and the character floor
// from SPEC §3.3 — none is computed by the code under test
// (`docs/MISTAKES.md` entry 19).
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect, type Browser, type Locator, type Page } from '@playwright/test';

import { clearTheClock, setTheClockTo } from './support/clock';
import { launchAs, placementInto } from './support/doors';
import { databaseStatement, deriveSurveyWindows } from './support/stack';

// The two people, as `student-survey.spec.ts` names them. The instructor is here
// only because SPEC §7.3 makes a *staff* launch the thing that stores a section's
// roster address, which is what gives the sync anything to discover.
const LEARNER_SUBJECT = 'mock-lms-user-learner';
const INSTRUCTOR_SUBJECT = 'mock-lms-user-instructor';

// The section, named rather than taken first-offered, so the week arithmetic
// below means something.
const SECTION_LABEL = 'BIOL-215-R3WW';
const SECTION_CODE = 'R3WW';
const SECTION_BLOCK = `survey-section-${SECTION_CODE}`;

// The minute this spec pretends it is, and the term week that follows from it.
// **Transcribed from the seeded calendar, not computed from the code under test**
// (`docs/MISTAKES.md` entry 19), and transcribed the same way
// `student-survey.spec.ts` transcribes it:
//
//   - `scripts/seed.py`'s `START_LETTER_MAP` gives start letter `R` twelve weeks
//     from Monday 7 September 2026, and the Fall 2026 term begins on Monday 17
//     August;
//   - the section's fourth week runs Monday 28 September to Sunday 4 October and
//     its window opens on Friday 2 October at 18:00 (SPEC §3.1);
//   - 17 August is term week 1, so 28 September is term week 7.
//
// `week.number` is the *term* week — `tests/fixtures/survey_windows.py` seeds the
// eighteen `week` rows of Fall 2026 by that number — so 7 is what a `response`
// written in this window points at, and `TERM_WEEK` is the number the screen
// prints beside `WK 04`.
const INSIDE_THE_WINDOW = '2026-10-02T19:00';
const COURSE_WEEK = '04';
const TERM_WEEK = 7;

// How long the learner's enrollment is waited for, and how often it is retried —
// the same instrument and the same numbers as `student-survey.spec.ts` and
// `lti-launch.spec.ts`, for the reason those two give: the roster sync runs in
// the worker, its latency is seconds, and a student launch triggers no sync of
// its own, so this window is not waiting out the five-minute debounce.
const SYNC_TIMEOUT_MS = 30_000;
const SYNC_RETRY_MS = 3_000;
const RENDER_WAIT_MS = 2_000;

// A budget for each test's own body. The default is 30s and Test B spends about
// four of them inside one click, on top of a launch and several `docker compose
// exec` round trips — a case that ran out of harness rather than out of patience
// would read as a flake.
const CASE_TIMEOUT_MS = 120_000;

// How long the submitted state is given to appear in Test B. SPEC §3.3's budget
// is the classifier's, and the mock deliberately overruns it: the submit returns
// once the backend gives up waiting, which is seconds rather than milliseconds.
const FAIL_OPEN_WAIT_MS = 20_000;

// Testids the screen publishes (E2-10).
const SUBMIT = 'survey-submit';
const REVISE = 'survey-revise';

// The governed copy this spec reads, written out here rather than imported from
// `frontend/src/copy/studentSurvey.ts` — `landing-views.spec.ts` states the rule:
// a spec that asked the page what its own heading was would pass against any
// heading at all.
const SUBMITTED_TITLE = 'Your pulse is in';

// Where the mock model provider publishes the vocabulary it answers to.
// `README.md`: "`GET /mock/rules` serves the whole vocabulary — the marker
// phrases, the character threshold, the stall … and that route, not this page, is
// what the tests aim at." `docker-compose.override.yml` publishes the service on
// this host port.
const MOCK_AI_ORIGIN = 'http://127.0.0.1:8082';
const MOCK_AI_RULES_PATH = '/mock/rules';

// The marker that makes the provider answer correctly and far too late. Its
// behaviour is the mock's published contract and is not restated here as a
// number: what this spec needs is that the answer arrives after the backend has
// stopped waiting, and the assertion for that is the stored audit pair rather
// than a stopwatch.
const STALL_MARKER = 'mock-ai:stall';

// ADR 0054: "A floored classification records `character-floor` as its prompt
// version and `no-model` as its model ID." Transcribed from that record — and
// from `README.md`, which says the same thing in prose — rather than read off
// `app.ai.tasks`, so this file is not agreeing with the implementation about what
// the implementation should write.
const FLOOR_PROMPT_VERSION = 'character-floor';
const FLOOR_MODEL_ID = 'no-model';

// SPEC §3.3's number for the prototype heuristic the fail-open floor keeps: "The
// prototype's ≥25-character heuristic is a placeholder only … with the character
// heuristic retained solely as the fail-open floor below." Used below only as a
// premise guard on this file's own comment, never as an expectation about the
// system.
const CHARACTER_FLOOR = 25;

// Test A's two comments. Both are comfortably over the character floor, neither
// carries a marker of any kind, and neither contains a `|` — the column separator
// the rows below come back on.
const INSTRUCTOR_COMMENT =
  'The Wednesday seminar spent long enough on the staining protocol for it to land.';
const COURSE_COMMENT =
  'The week four reading list was long, and the ordering made it manageable.';

// Test B's one comment: the marker, and enough words after it to clear the
// character floor. **The padding is load-bearing.** On the timeout the floor is
// what decides the verdict, and under twenty-five characters the floor answers
// `insufficient` — so a short marked comment would bounce, and this test would
// fail on a coaching sentence rather than on anything to do with failing open.
const STALLED_COMMENT = `${STALL_MARKER} - the lab pacing held up well and the reading load was fair.`;

// What a comment with no classification row at all comes back as, so that the
// missing row is a value this file can name in a message rather than a row that
// is simply not in the result. A `left join` and a sentinel, because an inner
// join would answer "nothing" both when the classification is missing and when
// the query has gone blind, and those are different failures
// (`docs/MISTAKES.md` entry 3).
const NO_CLASSIFICATION = 'no classification row';

// How many times the week clear is attempted, and how long it waits between
// tries. **Not defensiveness — a named collision.** Test B leaves a floored
// classification behind, the submit path enqueues the async re-classification for
// exactly those (SPEC §3.3: "then classified async"), and that sweep *adds* a row
// rather than replacing one — which
// `tests/integration/test_the_submit_path_follows_adr_0056s_taxonomy.py` asserts
// in as many words. The comment it re-sends still carries the stall marker, so
// the insert lands several seconds after the submit returned, which can be while
// this delete is running. `classification.answer_id` is `ON DELETE RESTRICT`
// (ADR 0055, ADR 0115), so a row inserted between the first delete and the second
// makes the second fail. Retrying is the honest repair: by the next attempt the
// sweep has finished and there is one more row to remove.
const CLEAR_ATTEMPTS = 3;
const CLEAR_RETRY_MS = 3_000;

// The placement `beforeAll` discovers and every test launches through.
let placement = '';

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  test.setTimeout(SYNC_TIMEOUT_MS + 120_000);
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    placement = await placementInto(page, LEARNER_SUBJECT, SECTION_LABEL);
    const staffPlacement = await placementInto(page, INSTRUCTOR_SUBJECT, SECTION_LABEL);
    expect(
      staffPlacement,
      'The mock platform should offer the instructor and the learner the same resource link into ' +
        `${SECTION_LABEL}. A sync is discovered per section, so a staff launch into one section ` +
        'enrolls nobody in another, and this spec would then wait out its whole window for an ' +
        'enrollment nothing was writing.',
    ).toBe(placement);

    // The trigger, and its own control. SPEC §7.3: an instructor's launch stores
    // the section's roster service address, which is the whole of what gives the
    // scheduled sync its discovery. A staff launch that was refused provisioned
    // no section and stored no address, and the poll below would then be waiting
    // for a sync nobody asked for.
    await launchAs(page, INSTRUCTOR_SUBJECT, placement);
    await expect(page.getByTestId('pulse-landing-instructor')).toBeVisible();

    await waitForTheLearnersEnrollment(browser);

    // The section reached this database through that launch, so it is younger
    // than the seed and has no `survey_window` rows yet: they are materialized up
    // front (ADR 0111) by an hourly job. Run it rather than wait for it.
    deriveSurveyWindows();

    await setTheClockTo(page, INSIDE_THE_WINDOW);
  } finally {
    await context.close();
  }
});

test.beforeEach(async () => {
  // Each test starts from a week nobody has answered — `student-survey.spec.ts`'s
  // rule and its reason: ADR 0109 makes the development clock an offset rather
  // than a freeze, so a revision written against a re-set clock can carry a
  // `last_submitted_at` before its stored `first_submitted_at` and `response`'s
  // own check constraint refuses it. Clearing also makes each test here
  // independent of the one before it.
  await clearTheWeek();
});

test.afterAll(async ({ browser }) => {
  // The week first, then the clock. Both are shared state and this file is not
  // the last thing the suite runs: `student-survey.spec.ts` sorts after it, opens
  // the same section for the same learner, and starts by asserting the form is
  // showing — which a week this file had answered and left behind would deny it.
  await clearTheWeek();

  const context = await browser.newContext();
  try {
    await clearTheClock(await context.newPage());
  } finally {
    await context.close();
  }
});

test('a valid submission leaves one response and a real classification for every comment', async ({
  page,
}) => {
  // **SPEC §14.3, E2's exit line, clause 1: "a student submits a valid
  // response."** The browser half is the student's; the database half is the
  // clause's, and it is the half no screen can show. `student-survey.spec.ts`
  // proves the form works and the submitted state survives a reload; what it
  // cannot say is that the row a reload reads is a `response` for this week with
  // a `classification` per comment behind it.
  //
  // **The half of the boundary pair on the provider's side.** `Test B` is the
  // other half, and the two directions are different. What this test refuses is a
  // stack that floors *everything* — one calling no provider at all stamps
  // `character-floor` on the rows below and fails here. What it cannot see is the
  // other direction: an implementation that never floors, because its budget
  // outlasts any provider or because it refuses on timeout instead of accepting,
  // satisfies every assertion here completely. That direction is Test B's.
  //
  // **The mutations this must kill:**
  //   1. *The accepted path writes no `classification` rows.* The submission is
  //      stored, the screen congratulates the student, and every comment is
  //      unjudged — so §3.3's validity is decided by nothing and E3's
  //      participation formula counts a week that was never classified. Caught by
  //      the sentinel: the join is a `left join`, so an unjudged comment comes
  //      back carrying `no classification row` rather than not coming back.
  //   2. *The real path writes the floor markers.* A classification stamped
  //      `character-floor`/`no-model` when the provider answered is ADR 0054's
  //      distinction erased in the direction nobody notices — every downstream
  //      reader that excludes floored rows then excludes rows a model produced.
  //   3. *More than one `response` for the week.* A resubmission that inserts
  //      instead of revising (ADR 0115) double-counts the week.
  //
  // **The near misses that must stay green:** any verdict the provider likes for
  // these two comments, since nothing here reads `verdict`; any prompt version
  // and model ID at all as long as they are not the floor's; and a second
  // classification row per comment, which the async sweep is entitled to add.
  test.setTimeout(CASE_TIMEOUT_MS);

  const block = await landOnTheSurvey(page);

  // The week, under both of SPEC §2.2's names, before anything is answered. This
  // is also what says the clock moved and the window is the one this spec means:
  // with the override cleared, today is not week 4 of a section that had not
  // started.
  await expect(block).toContainText(`WK ${COURSE_WEEK}`);
  await expect(block).toContainText(`TERM 0${TERM_WEEK}`);
  await expectTheFormIsShowing(block);

  // Two ratings above SPEC §3.2's "Required if Q ≤ 2" threshold, so both comments
  // are optional and both are written anyway: a week with no words in it
  // exercises none of the classifier, and this clause is about what the
  // classifier stored.
  await chooseRating(block, 0, '4');
  await chooseRating(block, 1, '5');
  await typeComment(block, 0, INSTRUCTOR_COMMENT);
  await typeComment(block, 1, COURSE_COMMENT);
  await setSlider(block, '6.5');

  await block.getByTestId(SUBMIT).click();
  await expect(block.getByText(SUBMITTED_TITLE, { exact: true })).toBeVisible();

  // ---- the server side ----------------------------------------------------
  //
  // Controls first (`docs/MISTAKES.md` entries 3 and 35). Before anything is
  // asserted about classifications, the comments this test typed are read back
  // out of `answer`. That is the canary on the whole query: it is joined through
  // exactly the tables and columns the assertions below join through, so a query
  // that has gone blind — a section code that no longer matches, a subject spelled
  // another way, a renamed foreign key — fails here, naming itself, instead of
  // reporting that no comment carried a floor marker.
  const classified = classifiedCommentsOfThisWeek();
  expect(
    commentsAmong(classified),
    'The two comments this test typed were not read back out of `answer` for this learner, this ' +
      'section and this week. Nothing below is a statement about classifications until they are: ' +
      'an empty result satisfies every "no row carries the floor marker" assertion perfectly. ' +
      `The query answered ${JSON.stringify(classified)}.`,
  ).toEqual([INSTRUCTOR_COMMENT, COURSE_COMMENT].sort());

  // Mutation 3. Exactly one `response` for this student, this section and this
  // week — SPEC §3.1's "exactly one open survey at a time per section", and the
  // row clause 1 says has to exist.
  expect(
    responseCountForThisWeek(),
    `A valid submission should leave exactly one \`response\` row for ${LEARNER_SUBJECT} in ` +
      `${SECTION_CODE} on term week ${TERM_WEEK}. Zero means the screen showed "${SUBMITTED_TITLE}" ` +
      'over a database that stored nothing, which is exit clause 1 unmet with every browser-side ' +
      'assertion green. More than one means a submission inserted where ADR 0115 revises in ' +
      'place, and E3 will divide by a week that was answered twice.',
  ).toBe(1);

  // Mutation 1. Every comment that was submitted carries a classification.
  const unjudged = classified.filter((row) => row.promptVersion === NO_CLASSIFICATION);
  expect(
    unjudged,
    'These comments were stored with no `classification` row behind them: ' +
      `${JSON.stringify(unjudged)}. SPEC §3.3 makes each submitted comment the classifier's ` +
      "subject, and clause 1 of E2's exit line names the classification rows alongside the " +
      'response. A comment nothing judged is a week whose validity was decided by nobody.',
  ).toEqual([]);

  // Mutation 2. None of them is the floor's. ADR 0054: the pair exists so that "a
  // verdict a model produced and a verdict a character count produced are never
  // confused for one another", and this is the direction of that distinction the
  // fail-open test cannot see.
  const floored = classified.filter(
    (row) => row.promptVersion === FLOOR_PROMPT_VERSION || row.modelId === FLOOR_MODEL_ID,
  );
  expect(
    floored,
    'A submission the mock model provider answered was recorded as if a character count had ' +
      `judged it: ${JSON.stringify(floored)}. ADR 0054 stamps ${FLOOR_PROMPT_VERSION} and ` +
      `${FLOOR_MODEL_ID} only when SPEC §3.3's fail-open floor applied. Getting here means ` +
      'either the provider was never called on a path that reports success, or the floor markers ' +
      'are written on every row — and both make every reader that excludes floored rows exclude ' +
      'rows a model produced.',
  ).toEqual([]);
});

test('a comment the provider stalls past the budget is accepted on the floor and says so in the record', async ({
  page,
}) => {
  // **SPEC §3.3, the fail-open clause:** "Classifier latency budget: p95 < 2s; on
  // provider timeout, the heuristic floor applies and the submission is accepted,
  // then classified async (fail open, never block a student on an outage)." E2's
  // correctness rests on this and no browser has driven it; the epic's exit is
  // where that gets fixed.
  //
  // **The half of the boundary pair on the floor's side.** `Test A` is the other
  // half. Read alone this test passes against an implementation that floors
  // *everything* — a stack that calls no provider stamps `character-floor` on this
  // row too, and would look perfect from here. Test A is what refuses that, by
  // requiring an answered comment to carry a real pair; together the two say the
  // paths are distinguishable in the record, which is the whole of what ADR 0054
  // is for.
  //
  // **The mutations this must kill:**
  //   1. *The synchronous budget is raised past the stall* — say, to ten seconds —
  //      so the provider's real answer arrives in time and the row carries a real
  //      audit pair. Nothing goes red anywhere else: the submission still
  //      succeeds, the verdict is still `substantive`, and the only casualty is
  //      §3.3's promise about what a student waits for.
  //   2. *Fail open turned fail closed.* The timeout is answered with a refusal —
  //      a 503, an error page, a bounce — instead of an acceptance. §3.3 forbids
  //      it in as many words: "never block a student on an outage." Caught by the
  //      submitted state below.
  //   3. *The floored row is written without the markers*, or with only one of
  //      them, so it is indistinguishable from a verdict a model produced
  //      (ADR 0054).
  //   4. *The floored classification is not written at all* — the submission is
  //      accepted and nothing records that the provider never answered, so the
  //      async sweep has nothing unresolved to find. Caught by the sentinel.
  //
  // **The near misses that must stay green:** a second classification row for the
  // same comment, which is exactly what the async re-classification adds and what
  // `test_the_submit_path_follows_adr_0056s_taxonomy.py` requires of it — so this
  // asserts that a floor-marked row is *among* the rows, never that it is the only
  // one; and any latency at all under the mock's stall, since what is asserted is
  // the stored pair rather than a stopwatch reading.
  test.setTimeout(CASE_TIMEOUT_MS);

  // The canary on the marker, before the browser does anything. If the mock no
  // longer answers to this phrase, the comment below is an ordinary comment, the
  // provider answers it in milliseconds, and the floor assertion fails pointing at
  // the backend — which would be the wrong file. `README.md` puts the published
  // vocabulary at this route precisely so that a consumer outside `mock-ai/` need
  // not hold a copy of it. The whole served document is searched as text rather
  // than by member name: what has to be true is that the phrase is published, and
  // the shape of the document is the mock's to change.
  const rules = await page.request.get(`${MOCK_AI_ORIGIN}${MOCK_AI_RULES_PATH}`);
  expect(
    rules.status(),
    `GET ${MOCK_AI_ORIGIN}${MOCK_AI_RULES_PATH} answered ${rules.status()}. The mock model ` +
      'provider serves its whole vocabulary there, and `docker-compose.override.yml` publishes ' +
      'the service on this host port for exactly this kind of read.',
  ).toBe(200);
  const published = await rules.text();
  expect(
    published,
    `The mock model provider's published rules do not mention ${STALL_MARKER}. This test drives ` +
      'the fail-open path by sending a comment carrying that phrase; against a mock that does ' +
      'not answer to it, the comment is an ordinary one, the provider replies inside the budget, ' +
      'and the assertion about the stored floor markers fails pointing at the backend instead of ' +
      `here. The route served ${published.slice(0, 400)}`,
  ).toContain(STALL_MARKER);

  // The premise on this file's own fixture, not an assertion about the system.
  // SPEC §3.3 keeps the twenty-five-character heuristic "solely as the fail-open
  // floor", and the floor is what decides the verdict once the provider has
  // stalled: under the floor this comment would be judged `insufficient` and
  // bounced, and this test would then be failing on coaching copy.
  expect(
    STALLED_COMMENT.length,
    `This test's marked comment is ${STALLED_COMMENT.length} characters. Below SPEC §3.3's ` +
      `${CHARACTER_FLOOR}-character floor the floored verdict is \`insufficient\`, the submission ` +
      'bounces, and this case stops being about failing open at all.',
  ).toBeGreaterThanOrEqual(CHARACTER_FLOOR);

  const block = await landOnTheSurvey(page);
  await expectTheFormIsShowing(block);

  // Ratings above the conditional threshold, one marked comment, the other left
  // blank. Exactly one comment is submitted, so exactly one comment can be
  // floored and the reading below is unambiguous.
  await chooseRating(block, 0, '4');
  await chooseRating(block, 1, '4');
  await typeComment(block, 0, STALLED_COMMENT);
  await typeComment(block, 1, '');
  await setSlider(block, '3');

  await block.getByTestId(SUBMIT).click();

  // Mutation 2. The submission is accepted — not bounced, not refused, not an
  // error page. This wait is longer than the ordinary one on purpose: the click
  // does not return until the backend has stopped waiting for the provider, and
  // that is the behaviour under test rather than a slow page.
  await expect(
    block.getByText(SUBMITTED_TITLE, { exact: true }),
    'A provider that stalled past the synchronous budget refused the student instead of ' +
      'accepting them. SPEC §3.3: "on provider timeout, the heuristic floor applies and the ' +
      'submission is accepted, then classified async (fail open, never block a student on an ' +
      'outage)." A bounce or a refusal here is somebody else\'s outage charged to a student.',
  ).toBeVisible({ timeout: FAIL_OPEN_WAIT_MS });
  await expect(block.getByTestId(SUBMIT)).toHaveCount(0);

  // ---- the server side ----------------------------------------------------
  //
  // The control first, as in Test A: the marked comment is read back out of
  // `answer` before anything is said about its classification, so a query that
  // reaches nothing says so rather than reporting an absent floor marker.
  const classified = classifiedCommentsOfThisWeek();
  expect(
    commentsAmong(classified),
    'The marked comment was not read back out of `answer` for this learner, this section and ' +
      'this week, so nothing below is a statement about its classification — and "no row carries ' +
      'the floor markers" is satisfied by no rows at all. Exactly one comment was submitted. ' +
      `The query answered ${JSON.stringify(classified)}.`,
  ).toEqual([STALLED_COMMENT]);

  // Mutation 4. Something judged it.
  const unjudged = classified.filter((row) => row.promptVersion === NO_CLASSIFICATION);
  expect(
    unjudged,
    'The accepted submission left its comment with no `classification` row at all: ' +
      `${JSON.stringify(unjudged)}. Failing open is not the same as recording nothing — ADR ` +
      '0054 has the floored row carry the markers precisely so the async sweep can find it ' +
      'again, and a submission accepted with no row is one nothing will ever come back to.',
  ).toEqual([]);

  // Mutations 1 and 3. A row carrying **both** markers, exactly. Among the rows
  // rather than the only row: the async re-classification adds a second one for
  // the same comment, and requiring a single row would make this test race a
  // worker doing its job.
  const onTheFloor = classified.filter(
    (row) => row.promptVersion === FLOOR_PROMPT_VERSION && row.modelId === FLOOR_MODEL_ID,
  );
  expect(
    onTheFloor.length,
    `No classification of the stalled comment carries ADR 0054's pair — prompt version ` +
      `${FLOOR_PROMPT_VERSION}, model ID ${FLOOR_MODEL_ID}. The rows are ` +
      `${JSON.stringify(classified)}.\n\n` +
      'Two defects look like this and they are worth telling apart. If the pairs below name a ' +
      'real prompt file and a real model, the provider answered in time — which means the ' +
      "synchronous budget has been raised past the mock's stall, and SPEC §3.3's promise about " +
      'what a student waits for is no longer kept. If they name something else again, the floor ' +
      'is being recorded under some other spelling, and every reader that excludes floored rows ' +
      '(§6.1\'s drift panel among them) now silently includes them.',
  ).toBeGreaterThan(0);
});

/**
 * Launch as the learner and answer with the section's block once it is on screen.
 *
 * `student-survey.spec.ts`'s helper, and its diagnosis: three causes look the
 * same from here.
 */
async function landOnTheSurvey(page: Page): Promise<Locator> {
  await launchAs(page, LEARNER_SUBJECT, placement);
  const block = page.getByTestId(SECTION_BLOCK);
  await expect(
    block,
    `The learner landed without a block for ${SECTION_CODE}. Three causes look the same from ` +
      'here: the roster sync has not enrolled them, the section has no materialized survey ' +
      'window for the pretended week, or the development clock is not where `beforeAll` put it.',
  ).toBeVisible();
  return block;
}

/** Assert the open, unanswered state: the form is on screen and nothing else is. */
async function expectTheFormIsShowing(block: Locator): Promise<void> {
  await expect(block.getByTestId(SUBMIT)).toBeVisible();
  await expect(block.getByTestId(REVISE)).toHaveCount(0);
}

/** Choose a point on the nth Likert scale in this block. */
async function chooseRating(block: Locator, scale: number, point: string): Promise<void> {
  await block.getByRole('radio', { name: point, exact: true }).nth(scale).check();
}

/** Type into the nth comment field in this block, or empty it. */
async function typeComment(block: Locator, field: number, words: string): Promise<void> {
  await block.getByRole('textbox').nth(field).fill(words);
}

/** Put the workload slider on one value, from the keyboard. */
async function setSlider(block: Locator, hours: string): Promise<void> {
  const slider = block.getByRole('slider');
  await slider.focus();
  await slider.fill(hours);
  await expect(slider).toHaveValue(hours);
}

/** One comment of this week, with one audit pair recorded against it. */
interface ClassifiedComment {
  comment: string;
  promptVersion: string;
  modelId: string;
}

/**
 * Every comment this learner submitted for this section and week, with each
 * classification recorded against it.
 *
 * **A `left join`, and a sentinel where the classification is missing.** An inner
 * join answers the empty set both when no comment was judged and when the query
 * reaches no comments at all, and those are opposite findings: the first is the
 * defect this file exists to catch, the second is this file being broken. With
 * the outer join a comment always comes back, so the caller can assert on the
 * comment text as a canary before it asserts on anything a classification says
 * (`docs/MISTAKES.md` entry 3).
 *
 * A comment may legitimately come back more than once: SPEC §3.3 has a floored
 * submission "classified async" afterwards, and that sweep adds a row rather than
 * replacing the floored one. Callers are written for that.
 *
 * The tables and columns are the ones `student-survey.spec.ts`'s `clearTheWeek`
 * already addresses — `response.section_id`, `answer.response_id`,
 * `classification.answer_id` — plus `response.user_id` and `response.week_id`,
 * which are the two `tests/integration/test_survey_schema.py` names as the rest of
 * a response's key. `"user"` is quoted because it is a reserved word.
 */
function classifiedCommentsOfThisWeek(): ClassifiedComment[] {
  const rows = databaseStatement(
    'select a.comment_text, ' +
      `coalesce(c.prompt_version, ${quoted(NO_CLASSIFICATION)}), ` +
      `coalesce(c.model_id, ${quoted(NO_CLASSIFICATION)}) ` +
      'from answer a ' +
      'join response r on r.id = a.response_id ' +
      'join section s on s.id = r.section_id ' +
      'join week w on w.id = r.week_id ' +
      'join "user" u on u.id = r.user_id ' +
      'left join classification c on c.answer_id = a.id ' +
      `where s.lms_section_code = ${quoted(SECTION_CODE)} ` +
      `and u.lms_user_id = ${quoted(LEARNER_SUBJECT)} ` +
      `and w.number = ${TERM_WEEK} ` +
      "and a.comment_text is not null and a.comment_text <> '' " +
      'order by a.comment_text, c.classified_at;',
  );
  if (rows === '') return [];
  return rows.split('\n').map((line) => {
    const cells = line.split('|');
    expect(
      cells.length,
      `A row of the comment query came back with ${cells.length} columns rather than 3: ` +
        `${JSON.stringify(line)}. The three values are read positionally, so a comment carrying ` +
        "psql's unaligned column separator would be split across them.",
    ).toBe(3);
    return { comment: cells[0], promptVersion: cells[1], modelId: cells[2] };
  });
}

/**
 * The distinct comments among those rows, sorted.
 *
 * Distinct, because a comment may legitimately appear twice: SPEC §3.3 has a
 * floored submission "classified async" afterwards and that sweep adds a row for
 * the same answer. The canary's claim is that each comment was reachable, and
 * counting rows here would make it fail against a worker doing its job.
 */
function commentsAmong(rows: ClassifiedComment[]): string[] {
  return Array.from(new Set(rows.map((row) => row.comment))).sort();
}

/** How many `response` rows this learner has for this section on this term week. */
function responseCountForThisWeek(): number {
  const counted = databaseStatement(
    'select count(*) from response r ' +
      'join section s on s.id = r.section_id ' +
      'join week w on w.id = r.week_id ' +
      'join "user" u on u.id = r.user_id ' +
      `where s.lms_section_code = ${quoted(SECTION_CODE)} ` +
      `and u.lms_user_id = ${quoted(LEARNER_SUBJECT)} ` +
      `and w.number = ${TERM_WEEK};`,
  );
  const count = Number.parseInt(counted, 10);
  expect(
    Number.isNaN(count),
    `The response count query answered ${JSON.stringify(counted)}, which is not a number. That ` +
      'is a query that did not run rather than a week with no response in it.',
  ).toBe(false);
  return count;
}

/**
 * Delete this section's stored responses, so the week is unanswered again.
 *
 * `student-survey.spec.ts`'s statement and its ordering, which is not a
 * preference: `classification.answer_id` carries `ON DELETE RESTRICT` (ADR 0055,
 * ADR 0115) — the database refusing to let a verdict lose the comment it judged —
 * so the verdicts go first, then the answers they named, then the response
 * holding them.
 *
 * **The retry is this file's addition, and `CLEAR_ATTEMPTS` says why.** This spec
 * is the first to leave a floored classification behind, so it is the first whose
 * delete can race the async re-classification inserting another one.
 */
async function clearTheWeek(): Promise<void> {
  const ofThisSection =
    'select r.id from response r join section s on s.id = r.section_id ' +
    `where s.lms_section_code = ${quoted(SECTION_CODE)}`;
  const statements =
    `delete from classification where answer_id in (select id from answer where response_id in (${ofThisSection}));\n` +
    `delete from answer where response_id in (${ofThisSection});\n` +
    `delete from response where id in (${ofThisSection});`;

  let refused: unknown = null;
  for (let attempt = 1; attempt <= CLEAR_ATTEMPTS; attempt += 1) {
    try {
      databaseStatement(statements);
      return;
    } catch (error) {
      refused = error;
      if (attempt < CLEAR_ATTEMPTS) {
        await new Promise((wake) => setTimeout(wake, CLEAR_RETRY_MS));
      }
    }
  }
  throw new Error(
    `Clearing ${SECTION_CODE}'s week failed ${CLEAR_ATTEMPTS} times. The likeliest cause is the ` +
      'async re-classification: this spec leaves a floored classification behind, the sweep adds ' +
      'a row for the same answer several seconds later, and `classification.answer_id` is ON ' +
      'DELETE RESTRICT — so a row inserted between the first delete and the second makes the ' +
      `second one fail. The last refusal was: ${String(refused)}`,
  );
}

/** One string as a SQL literal. */
function quoted(value: string): string {
  return `'${value.replace(/'/g, "''")}'`;
}

/**
 * Launch as the learner until the survey screen appears, or give up loudly.
 *
 * `student-survey.spec.ts`'s poll, unchanged: the roster sync runs in the worker
 * after the staff launch above, so the learner's enrollment arrives a second or
 * two later, and each attempt opens its own context because a launch reuses
 * whatever session the last one left. `waitFor` and not `isVisible`, for the
 * reason that file measured — the second answers about the page as it stands at
 * the instant it is called, so every attempt read a document that had not
 * navigated yet and the poll spent its whole window measuring nothing.
 */
async function waitForTheLearnersEnrollment(browser: Browser): Promise<void> {
  const deadline = Date.now() + SYNC_TIMEOUT_MS;
  let landed = false;
  while (!landed && Date.now() < deadline) {
    const context = await browser.newContext();
    const page = await context.newPage();
    try {
      await launchAs(page, LEARNER_SUBJECT, placement);
      landed = await page
        .getByTestId('pulse-landing-student')
        .waitFor({ state: 'visible', timeout: RENDER_WAIT_MS })
        .then(
          () => true,
          () => false,
        );
    } finally {
      await context.close();
    }
    if (!landed) await new Promise((wake) => setTimeout(wake, SYNC_RETRY_MS));
  }
  expect(
    landed,
    `The learner never reached the student view within ${SYNC_TIMEOUT_MS}ms of a staff launch ` +
      `into ${SECTION_LABEL}. The roster sync is what enrolls them (SPEC §7.3), so this is the ` +
      'worker not running, the mock platform not serving its roster, or the staff launch not ' +
      "having stored the section's roster address.",
  ).toBe(true);
}
