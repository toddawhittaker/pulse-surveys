// SPEC §14.3's exit for the student loop, driven on the composed stack: "the
// full weekly loop demos end-to-end from one student's seat." Then the two
// response paths the E7 boundary found no re-runnable drive for.
//
// **The student's week**, in `MATH-140-E1FF`, from the learner's seat:
//
//   - **The survey.** She answers the exit week's survey through the page. The
//     window closes and the moderation sweep runs.
//   - **Held.** The Lead Faculty member set the course to required the day before
//     the report opens. On her next launch the landing shows no results lead
//     (a lead over a closed door would tease what the hold keeps back), and the
//     results page is the closed door: the course's name, her own posted
//     participation score, and nothing about the week.
//   - **Released.** The instructor publishes. The landing now leads with "Week N
//     results are in", and the page reads the response first, then the trend,
//     the two distributions, the workload median, the published instructor
//     comments, the course stream's small-N notice and the confidentiality line.
//     The week before it, one step back, shows both streams' ratings held.
//
// **The two response paths**, in `NURS-8100-Q2FF`: the lead reads a required,
// unanswered week as owed past 48 hours, then past 96 hours opens it on the
// on-behalf page and reads it unanswered, then publishes on behalf; the learner
// reads the lead's name and role.
//
// **Every page reached is scanned with axe**, the held and released results
// pages, the earlier week's ratings-held notices, the policy page, the owed list
// and the on-behalf page among them. The from-earlier-weeks group is not reached:
// a release batch's `cut_at` is the database's wall clock, not the moved
// development clock, so on this stack a batch is always cut after any past
// week's report opened and never shows (recorded for E9 in
// `docs/tickets/e9/carried-from-e8.md`).
//
// **Re-runnable on one stack, by fresh weeks, not by cleaning up.** The response
// and policy tables are append-only. The student's week is the first of course
// weeks 5 and 6 that holds no response (the seeder chooses it and prints it), so
// a second run takes week 6. The response paths take the latest course week of
// `NURS-8100-Q2FF` with no response, short of the last, so a second run takes
// the week before. Each run sets its own policy row the day before its week's
// report opens and sets the course back to encouraged before the next week's
// report opens; an earlier run's rows are all set after a later run's week
// opens, so none of them governs it. If this run's launch enrolled the
// `NURS-8100-Q2FF` roster, the enrollments are deleted on the way out: the
// student-survey drives read the learner's landing while that section is live
// and expect only their own section on it.
//
// **No date is pinned.** Every instant is read from the section's own
// `survey_window` rows and moved to with the `/dev` clock; the enrollments are
// anchored at each section's start by `standTheLearnerIn`.
//
// **The posted score is planted, and deleted on the way out.** The weekly
// passback would post every section's scores into the mock gradebook, which
// `exit-grade-passback.spec.ts` later reads from a known-empty start. So one
// `grade_sync` row stands for a post, written as the stack's superuser, and the
// page is asked to show it as posted (SPEC §3.3, ADR 0198).
//
// **The seats are real grants, removed afterwards**, as in
// `exit-response-loop.spec.ts`: each course is mapped to the mock world's Lead
// Faculty member for its block and the mapping deleted on the way out, and the
// mock instructor's name is set for the block and put back.
//
// This spec cannot be run without a seeded, running Compose stack built from the
// branch; its green is the stack-up run and CI.

import { test, expect, type Locator, type Page } from '@playwright/test';

import { expectNoAxeViolations } from './support/axe';
import { clearTheClock, setTheClockTo } from './support/clock';
import { launchAs, signInAs } from './support/doors';
import {
  databaseStatement,
  moderateClosedWindows,
  seedTheStudentLoopExitStory,
  stopTheScheduler,
} from './support/stack';
import {
  INSTRUCTOR_SUBJECT,
  LEARNER_SUBJECT,
  STUDENT_VIEW,
  SUBMIT,
  chooseRating,
  clearTheWeek,
  landOnTheSurvey,
  sectionBlock,
  sectionStartClock,
  setSlider,
  standTheLearnerIn,
  typeComment,
  type SectionUnderTest,
} from './support/survey';

const MATHEMATICS: SectionUnderTest = { label: 'MATH-140-E1FF', code: 'E1FF' };
const NURSING: SectionUnderTest = { label: 'NURS-8100-Q2FF', code: 'Q2FF' };

const LEAD_WEB_SUBJECT = 'mock-idp-user-lead-faculty';
const LEAD_NAME = 'Demo Mock-World Lead Faculty';
const LEAD_PERSON = `(select id from person where identity_name = '${LEAD_NAME}')`;

const INSTRUCTOR_NAME = 'Professor Lorna Abernethy';
const REPLY = 'Thank you for the notes on the problem sets. Next week each set is two questions shorter.';
const LEADS = 'Thank you for this week’s answers. The review session moves to Tuesday.';

// The learner's own answer to the exit week.
const LEARNER_VOICE = 'Student loop, the learner: the board work was easy to follow from the back row.';

// The seeder's words the drive asserts (`scripts/seed_student_loop_exit_story.py`),
// transcribed (`docs/MISTAKES.md` entry 19).
const INSTRUCTOR_VOICES = [
  'Student loop voice one: the worked examples made the factoring steps clear.',
  'Student loop voice two: questions in class got patient and complete answers.',
  'Student loop voice three: the review at the start of class helped me catch up.',
  'Student loop voice four: office hours were easy to find and worth the trip.',
  'Student loop voice five: the instructor explained why each method works.',
];
const LONE_COURSE_VOICE = 'Student loop course voice: the problem sets ran longer than the reading.';
const EARLIER_COURSE_VOICE = 'Student loop earlier week: the quiz covered exactly what the module promised.';

// The planted posted score: its two texts as the page prints them.
const SCORE_TEXT = '84.0';
const LEDGER_TEXT = 'Week 1: 5 of 5 items';

// Governed words, transcribed (`docs/MISTAKES.md` entry 19).
const AWAITING = 'There is no reply to show for this week yet.';
const POSTED_SCORE = `Your participation: ${SCORE_TEXT}%`;
const CONFIDENTIALITY_LINE = 'Comments are shown without the names of the students who wrote them.';
const SMALL_N_TITLE = 'Comments in this group are not shown this week';
const INSTRUCTOR_RATINGS_HELD = 'Ratings about the instructor are not shown this week';
const COURSE_RATINGS_HELD = 'Ratings about the course are not shown this week';
const WORKLOAD_MEDIAN = /^Class median: \d+\.\d hours on this course$/;
const LEADS_BYLINE = `${LEAD_NAME}, Lead Faculty`;
const LEADERSHIP_VIEW = 'pulse-landing-leadership';
const POLICY_LINK = 'Response policy';
const OWED_LINK = 'Responses owed';
const OWED_LIST = 'pulse-leadership-responses-owed-list';
const ON_BEHALF_PAGE = 'pulse-leadership-on-behalf';
const RESPOND = 'Respond on behalf';
const CARD = 'article.pulse-response-card';
const RESULTS = 'pulse-student-results';
const RESULTS_LEAD = 'pulse-results-lead';

const WORLD_TIMEOUT_MS = 300_000;
const CASE_TIMEOUT_MS = 180_000;
const INSTITUTION_ZONE = 'America/New_York';

test.describe.configure({ mode: 'serial' });

/** The `section` key of one section code, as a subquery. */
function sectionOf(section: SectionUnderTest): string {
  return `(select id from section where lms_section_code = '${section.code}')`;
}

/** The course of one section code, as a subquery. */
function courseOf(section: SectionUnderTest): string {
  return `(select course_id from section where lms_section_code = '${section.code}')`;
}

/** One course week's window row, as a subquery over the section's windows in order. */
function windowColumn(section: SectionUnderTest, courseWeek: number, column: string): string {
  return (
    `(select ${column} from survey_window where section_id = ${sectionOf(section)} ` +
    `order by opens_at offset ${String(courseWeek - 1)} limit 1)`
  );
}

/** A local `YYYY-MM-DDTHH:MM` minute an hour after one course week's window opens. */
function insideTheWindowOf(section: SectionUnderTest, courseWeek: number): string {
  return databaseStatement(
    `select to_char(${windowColumn(section, courseWeek, 'opens_at')} at time zone ` +
      `'${INSTITUTION_ZONE}' + interval '1 hour', 'YYYY-MM-DD"T"HH24:MI');`,
  );
}

/**
 * The report-open minute of one course week, local, from its window row: the
 * first Monday at 06:00 after the window closes (`reporting.report_opens_at`).
 */
function reportOpensOf(section: SectionUnderTest, courseWeek: number): string {
  const opens = databaseStatement(
    'select to_char(' +
      `date_trunc('week', ${windowColumn(section, courseWeek, 'closes_at')} at time zone ` +
      `'${INSTITUTION_ZONE}') + interval '7 days 6 hours', 'YYYY-MM-DD"T"HH24:MI');`,
  );
  expect(
    opens,
    `Course week ${String(courseWeek)} of ${section.label} has no window to derive a report opening from.`,
  ).toMatch(/^\d{4}-\d\d-\d\dT06:00$/);
  return opens;
}

/** A wall-clock minute plus whole hours; the days in play never cross a clock change. */
function plusHours(minute: string, hours: number): string {
  const at = new Date(`${minute}:00Z`);
  at.setUTCHours(at.getUTCHours() + hours);
  return at.toISOString().slice(0, 16);
}

/** Map a course to the mock lead, and answer whether this run wrote the row. */
function mapTheLeadTo(section: SectionUnderTest): boolean {
  databaseStatement(
    `delete from lead_faculty_mapping where course_id = ${courseOf(section)} and person_id = ${LEAD_PERSON};`,
  );
  return (
    databaseStatement(
      'with inserted as (insert into lead_faculty_mapping (person_id, course_id) ' +
        `select ${LEAD_PERSON}, ${courseOf(section)} on conflict (course_id) do nothing returning 1) ` +
        'select count(*) from inserted;',
    ) === '1'
  );
}

function unmapTheLeadFrom(section: SectionUnderTest): void {
  databaseStatement(
    `delete from lead_faculty_mapping where course_id = ${courseOf(section)} and person_id = ${LEAD_PERSON};`,
  );
}

function latestPolicyOf(section: SectionUnderTest): string {
  return databaseStatement(
    `select mode from response_policy where course_id = ${courseOf(section)} order by sequence desc limit 1;`,
  );
}

/** Sign in as the lead and open one of the landing's links. */
async function leadOpens(page: Page, link: string): Promise<void> {
  await signInAs(page, LEAD_WEB_SUBJECT);
  await expect(page.getByTestId(LEADERSHIP_VIEW)).toBeVisible();
  await page.getByRole('link', { name: link }).click();
}

/** The lead flips the course's switch on the policy page, from `from` to its other state. */
async function leadSwitches(page: Page, prefix: string, from: boolean): Promise<void> {
  await leadOpens(page, POLICY_LINK);
  const toggle = page.getByRole('switch', { name: `Response required for ${prefix} courses you set` });
  await expect(toggle).toHaveAttribute('aria-checked', String(from));
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-checked', String(!from));
  await expectNoAxeViolations(page, 'The policy page after a change');
}

/** Launch as the learner and open one course week's results page. */
async function studentReads(
  page: Page,
  placement: string,
  sectionId: string,
  courseWeek: number,
): Promise<Locator> {
  await launchAs(page, LEARNER_SUBJECT, placement);
  // The landing showing means the page has stored the session the launch handed
  // over, so the navigation below carries it.
  await expect(page.getByTestId(STUDENT_VIEW)).toBeVisible();
  await page.goto(`/app/student/sections/${sectionId}/weeks/${String(courseWeek)}/results`);
  const results = page.getByTestId(RESULTS);
  await expect(results).toBeVisible();
  return results;
}

test.describe('the student’s week, from her seat', () => {
  let placement = '';
  let sectionId = '';
  let exitWeek = 0;
  let reportOpens = '';
  let nextReportOpens = '';
  let mappedTheLead = false;
  let formerInstructorName = '';
  let plantedScore = '';

  const SECTION = sectionOf(MATHEMATICS);
  const INSTRUCTOR =
    '(select ra.person_id from role_assignment ra ' +
    `where ra.role = 'INSTRUCTOR' and ra.section_id = ${SECTION} limit 1)`;
  const LEARNER_USER = `(select id from "user" where lms_user_id = '${LEARNER_SUBJECT}')`;

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(WORLD_TIMEOUT_MS);
    stopTheScheduler();
    placement = await standTheLearnerIn(browser, [MATHEMATICS], sectionStartClock(MATHEMATICS.code));
    clearTheWeek([MATHEMATICS.code]);
    sectionId = databaseStatement(`select ${SECTION};`);
    expect(sectionId, 'The section was not provisioned by the staff launch.').toMatch(/^[0-9a-f-]{36}$/);

    const printed = seedTheStudentLoopExitStory();
    const chosen = /exit week (\d+), 8 responses, 9 comments\./.exec(printed);
    expect(chosen, `The seeder printed ${JSON.stringify(printed)}.`).not.toBeNull();
    exitWeek = Number(chosen?.[1]);
    reportOpens = reportOpensOf(MATHEMATICS, exitWeek);
    nextReportOpens = reportOpensOf(MATHEMATICS, exitWeek + 1);

    formerInstructorName = databaseStatement(
      `select coalesce(quote_literal(identity_name), 'NULL') from person where id = ${INSTRUCTOR};`,
    );
    expect(formerInstructorName, 'No person holds an INSTRUCTOR grant on the section.').not.toBe('');
    databaseStatement(`update person set identity_name = '${INSTRUCTOR_NAME}' where id = ${INSTRUCTOR};`);

    mappedTheLead = mapTheLeadTo(MATHEMATICS);
    expect(mappedTheLead, 'MATH 140 already has a lead, so this run cannot give it the mock world’s lead.').toBe(
      true,
    );

    plantedScore = databaseStatement(
      'insert into grade_sync (section_id, user_id, score_text, score_timestamp, ledger_text, outcome, response_code) ' +
        `select ${SECTION}, ${LEARNER_USER}, '${SCORE_TEXT}', now(), '${LEDGER_TEXT}', 'posted', 200 returning id;`,
    );
    expect(plantedScore, 'The learner’s posted score could not be planted.').toMatch(/^[0-9a-f-]{36}$/);
  });

  test.afterAll(async ({ browser }) => {
    const context = await browser.newContext();
    try {
      try {
        if (plantedScore !== '') databaseStatement(`delete from grade_sync where id = '${plantedScore}';`);
        if (mappedTheLead) unmapTheLeadFrom(MATHEMATICS);
        if (formerInstructorName !== '') {
          databaseStatement(
            `update person set identity_name = ${formerInstructorName} where id = ${INSTRUCTOR};`,
          );
        }
        clearTheWeek([MATHEMATICS.code]);
      } finally {
        await clearTheClock(await context.newPage());
      }
    } finally {
      await context.close();
    }
  });

  test('she answers the exit week’s survey through the page', async ({ page }) => {
    test.setTimeout(CASE_TIMEOUT_MS);
    await setTheClockTo(page, insideTheWindowOf(MATHEMATICS, exitWeek));
    const block = await landOnTheSurvey(page, placement, MATHEMATICS.code);
    await chooseRating(block, 0, '5');
    await chooseRating(block, 1, '4');
    await typeComment(block, 0, LEARNER_VOICE);
    await setSlider(block, '6.5');
    await block.getByTestId(SUBMIT).click();
    await expect(block.getByText('Your pulse is in', { exact: true })).toBeVisible();
  });

  test('the lead sets the course to required the day before the report opens', async ({ page }) => {
    test.setTimeout(CASE_TIMEOUT_MS);
    await setTheClockTo(page, plusHours(reportOpens, -24));
    await leadSwitches(page, 'MATH', false);
    expect(latestPolicyOf(MATHEMATICS), 'The switch did not record a required policy for MATH 140.').toBe(
      'REQUIRED',
    );
  });

  test('the window closes and the moderation sweep gives every comment its verdict', async ({ page }) => {
    test.setTimeout(CASE_TIMEOUT_MS);
    await setTheClockTo(page, plusHours(reportOpens, -2));
    moderateClosedWindows();
    const waiting = (verdict: 'with' | 'without'): string =>
      databaseStatement(
        'select count(*) from answer a join response r on r.id = a.response_id ' +
          `where r.section_id = ${SECTION} and a.comment_text is not null and btrim(a.comment_text) <> '' ` +
          `and ${verdict === 'with' ? '' : 'not '}exists (select 1 from classification c ` +
          "where c.answer_id = a.id and c.task = 'MODERATION');",
      );
    // Nine from the seeder and the learner's one.
    expect(waiting('with'), 'The sweep did not moderate every comment of the two weeks.').toBe('10');
    expect(waiting('without')).toBe('0');
  });

  test('held: no lead on the landing, and the page is the closed door with her own score', async ({ page }) => {
    test.setTimeout(CASE_TIMEOUT_MS);
    await setTheClockTo(page, plusHours(reportOpens, 1));
    await launchAs(page, LEARNER_SUBJECT, placement);
    const block = page.getByTestId(sectionBlock(MATHEMATICS.code));
    await expect(block).toBeVisible();
    await expect(block.getByTestId(RESULTS_LEAD)).toHaveCount(0);

    const results = await studentReads(page, placement, sectionId, exitWeek);
    await expect(results.getByText(AWAITING)).toBeVisible();
    await expect(results.getByTestId('pulse-results-course')).toContainText('MATH 140');
    await expect(results.getByText(POSTED_SCORE)).toBeVisible();
    await expect(results.getByText(LEDGER_TEXT, { exact: true })).toBeVisible();
    await expect(results.locator(CARD)).toHaveCount(0);
    await expect(results.getByTestId('pulse-trend-duo')).toHaveCount(0);
    await expect(results.locator('.pulse-stat-histogram')).toHaveCount(0);
    await expect(results.locator('.pulse-results-workload')).toHaveCount(0);
    await expect(results.locator('.pulse-comment-group')).toHaveCount(0);
    await expect(results.locator('.pulse-small-n-notice')).toHaveCount(0);
    const text = (await results.textContent()) ?? '';
    for (const words of [...INSTRUCTOR_VOICES, LEARNER_VOICE, LONE_COURSE_VOICE, INSTRUCTOR_NAME]) {
      expect(text, 'The closed door shows something of the week.').not.toContain(words);
    }
    expect(text).not.toContain(CONFIDENTIALITY_LINE);
    await expectNoAxeViolations(page, 'The closed door');
  });

  test('released: the landing leads with the week, and the page reads the response first, then the class', async ({
    page,
  }) => {
    test.setTimeout(CASE_TIMEOUT_MS);
    await setTheClockTo(page, plusHours(reportOpens, 2));
    await launchAs(page, INSTRUCTOR_SUBJECT, placement);
    await page
      .getByTestId('pulse-instructor-sections')
      .getByRole('link', { name: /MATH 140 E1FF/ })
      .click();
    await expect(page.getByTestId('pulse-instructor-report')).toBeVisible();
    const composer = page.getByRole('region', { name: 'Your response to this week' });
    await composer.getByRole('textbox', { name: 'Your response' }).fill(REPLY);
    await composer.getByRole('button', { name: 'Publish' }).click();
    await expect(composer.locator(CARD).getByText(REPLY)).toBeVisible();

    await launchAs(page, LEARNER_SUBJECT, placement);
    const lead = page.getByTestId(sectionBlock(MATHEMATICS.code)).getByTestId(RESULTS_LEAD);
    await expect(lead).toContainText(`Week ${String(exitWeek)} results are in`);
    await expectNoAxeViolations(page, 'The landing with a results lead');
    await lead.getByRole('link').click();

    const results = page.getByTestId(RESULTS);
    await expect(results.locator(CARD).getByText(REPLY)).toBeVisible();
    await expect(results.locator(CARD).getByText(INSTRUCTOR_NAME, { exact: true })).toBeVisible();
    await expect(results.getByText(AWAITING)).toHaveCount(0);
    await expect(results.getByTestId('pulse-results-course')).toContainText('MATH 140');
    await expect(results.getByText(POSTED_SCORE)).toBeVisible();

    // The response first, then the class's figures.
    const trend = results.getByTestId('pulse-trend-duo');
    await expect(trend).toBeVisible();
    const responseFirst = await results.evaluate((root) => {
      const card = root.querySelector('article.pulse-response-card');
      const figures = root.querySelector('[data-testid="pulse-trend-duo"]');
      return (
        card !== null &&
        figures !== null &&
        (card.compareDocumentPosition(figures) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0
      );
    });
    expect(responseFirst, 'The trend comes before the response.').toBe(true);

    // Six classmates rated both streams: two distributions, and the workload median.
    await expect(results.locator('.pulse-stat-histogram')).toHaveCount(2);
    for (const title of ['Ratings about the instructor', 'Ratings about the course']) {
      await expect(results.locator('.pulse-stat-histogram-title').getByText(title, { exact: true })).toBeVisible();
    }
    await expect(results.getByText(INSTRUCTOR_RATINGS_HELD)).toHaveCount(0);
    await expect(results.getByText(COURSE_RATINGS_HELD)).toHaveCount(0);
    await expect(results.locator('.pulse-results-workload')).toHaveText(WORKLOAD_MEDIAN);

    // Six commented on the instructor, so those comments show; one on the
    // course, so that stream is the small-N notice and its comment stays out.
    for (const voice of [...INSTRUCTOR_VOICES, LEARNER_VOICE]) {
      await expect(results.getByText(voice, { exact: true })).toBeVisible();
    }
    await expect(results.getByText(SMALL_N_TITLE)).toHaveCount(1);
    await expect(results.getByText(LONE_COURSE_VOICE)).toHaveCount(0);

    const text = (await results.textContent()) ?? '';
    expect(text.split(CONFIDENTIALITY_LINE).length - 1).toBe(1);
    await expectNoAxeViolations(page, 'The released week');

    // One step back: three classmates rated, so both streams' ratings are held.
    await results.getByRole('button', { name: 'Previous week' }).click();
    await expect(results.getByText(INSTRUCTOR_RATINGS_HELD)).toBeVisible();
    await expect(results.getByText(COURSE_RATINGS_HELD)).toBeVisible();
    await expect(results.locator('.pulse-stat-histogram')).toHaveCount(0);
    await expect(results.locator('.pulse-results-workload')).toHaveCount(0);
    await expect(results.getByText(SMALL_N_TITLE).first()).toBeVisible();
    await expect(results.getByText(EARLIER_COURSE_VOICE)).toHaveCount(0);
    await expectNoAxeViolations(page, 'The week before, with its ratings held');
  });

  test('the lead sets the course back to encouraged before the next week’s report opens', async ({ page }) => {
    // The policy table is append-only: this run's setting is undone by a later
    // row, dated before the next week opens, so only the exit week was held.
    test.setTimeout(CASE_TIMEOUT_MS);
    const now = plusHours(reportOpens, 3);
    expect(now < nextReportOpens).toBe(true);
    await setTheClockTo(page, now);
    await leadSwitches(page, 'MATH', true);
    expect(latestPolicyOf(MATHEMATICS)).toBe('ENCOURAGED');
  });
});

test.describe('the two response paths, as the lead and then the student', () => {
  let placement = '';
  let sectionId = '';
  let courseWeek = 0;
  let reportOpens = '';
  let nextReportOpens = '';
  let mappedTheLead = false;
  let enrolledBefore = '';

  const SECTION = sectionOf(NURSING);
  const THE_SECTION_ROW = 'NURS 8100 Q2FF';

  /** The owed list's row for this run's week. */
  function owedRow(page: Page): Locator {
    return page
      .getByTestId(OWED_LIST)
      .getByRole('listitem')
      .filter({ hasText: THE_SECTION_ROW })
      .filter({ hasText: `Week ${String(courseWeek)}` });
  }

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(WORLD_TIMEOUT_MS);
    stopTheScheduler();
    enrolledBefore = databaseStatement(
      `select count(*) from enrollment where section_id in (select id from section where lms_section_code = '${NURSING.code}');`,
    );
    placement = await standTheLearnerIn(browser, [NURSING], sectionStartClock(NURSING.code));
    sectionId = databaseStatement(`select ${SECTION};`);
    expect(sectionId, 'The section was not provisioned by the staff launch.').toMatch(/^[0-9a-f-]{36}$/);

    // The latest course week that holds no response, short of the last, so a
    // next week's opening bounds the run's policy, and the published response
    // sits after every pinned date the other drives read.
    courseWeek = Number(
      databaseStatement(
        'select n from (select w.week_id, row_number() over (order by w.opens_at) as n ' +
          `from survey_window w where w.section_id = ${SECTION}) weeks ` +
          `where n < (select count(*) from survey_window where section_id = ${SECTION}) ` +
          'and not exists (select 1 from instructor_response r ' +
          `where r.section_id = ${SECTION} and r.week_id = weeks.week_id) order by n desc limit 1;`,
      ),
    );
    expect(
      courseWeek,
      `Every week of ${NURSING.label} already holds a response, which the table keeps for good. Run on a fresh stack.`,
    ).toBeGreaterThan(0);
    reportOpens = reportOpensOf(NURSING, courseWeek);
    nextReportOpens = reportOpensOf(NURSING, courseWeek + 1);

    mappedTheLead = mapTheLeadTo(NURSING);
    expect(mappedTheLead, 'NURS 8100 already has a lead, so this run cannot give it the mock world’s lead.').toBe(
      true,
    );
  });

  test.afterAll(async ({ browser }) => {
    const context = await browser.newContext();
    try {
      try {
        if (mappedTheLead) unmapTheLeadFrom(NURSING);
        // The student-survey drives read the learner's landing at dates when
        // this section is live, and expect it not to be on her screen. If this
        // run's launch enrolled the roster, its enrollments go again; the next
        // staff launch syncs them back.
        if (enrolledBefore === '0') {
          databaseStatement(
            `delete from enrollment where section_id in (select id from section where lms_section_code = '${NURSING.code}');`,
          );
        }
      } finally {
        await clearTheClock(await context.newPage());
      }
    } finally {
      await context.close();
    }
  });

  test('the lead sets the course to required the day before the week’s report opens', async ({ page }) => {
    test.setTimeout(CASE_TIMEOUT_MS);
    await setTheClockTo(page, plusHours(reportOpens, -24));
    await leadSwitches(page, 'NURS', false);
    expect(latestPolicyOf(NURSING)).toBe('REQUIRED');
  });

  test('past the 48-hour deadline the lead reads the unanswered week as owed, with no on-behalf door yet', async ({
    page,
  }) => {
    test.setTimeout(CASE_TIMEOUT_MS);
    await setTheClockTo(page, plusHours(reportOpens, 48));
    await leadOpens(page, OWED_LINK);
    await expect(owedRow(page)).toHaveCount(1);
    await expect(owedRow(page).getByRole('link', { name: new RegExp(RESPOND) })).toHaveCount(0);
    await expectNoAxeViolations(page, 'The owed list at 48 hours');
  });

  test('past 96 hours the lead opens the week, reads it unanswered, and publishes on behalf', async ({ page }) => {
    test.setTimeout(CASE_TIMEOUT_MS);
    await setTheClockTo(page, plusHours(reportOpens, 96));

    const closed = await studentReads(page, placement, sectionId, courseWeek);
    await expect(closed.getByText(AWAITING)).toBeVisible();
    await expect(closed.locator(CARD)).toHaveCount(0);

    await leadOpens(page, OWED_LINK);
    await owedRow(page).getByRole('link', { name: new RegExp(RESPOND) }).click();
    const onBehalf = page.getByTestId(ON_BEHALF_PAGE);
    const editor = onBehalf.getByRole('textbox', { name: 'Your response' });
    await expect(editor).toHaveValue('');
    await expect(onBehalf.locator(CARD)).toHaveCount(0);
    await expectNoAxeViolations(page, 'The on-behalf page for an unanswered week');

    await editor.fill(LEADS);
    await onBehalf.getByRole('button', { name: 'Publish' }).click();
    await expect(onBehalf.locator(CARD).getByText(LEADS)).toBeVisible();
    await expectNoAxeViolations(page, 'The on-behalf page after a publish');

    const results = await studentReads(page, placement, sectionId, courseWeek);
    await expect(results.locator(CARD).getByText(LEADS)).toBeVisible();
    await expect(results.locator(CARD).getByText(LEADS_BYLINE, { exact: true })).toBeVisible();
    await expect(results.getByText(AWAITING)).toHaveCount(0);
    await expectNoAxeViolations(page, 'The week answered on behalf');
  });

  test('the lead sets the course back to encouraged before the next week’s report opens', async ({ page }) => {
    test.setTimeout(CASE_TIMEOUT_MS);
    const now = plusHours(reportOpens, 97);
    expect(now < nextReportOpens).toBe(true);
    await setTheClockTo(page, now);
    await leadSwitches(page, 'NURS', true);
    expect(latestPolicyOf(NURSING)).toBe('ENCOURAGED');
  });
});
