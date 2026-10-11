// SPEC §14.3's exit for the response loop, driven on the composed stack:
// "a required-mode section shows nothing to students until a named human
// publishes."
//
//   - **Held.** The Lead Faculty member sets the course to required from the
//     policy page before course week 3's report opens. In that week the student
//     reads the closed door: no response, no name.
//   - **Released by a named human.** The instructor uses the AI draft, checks
//     it, and publishes; the student reads the response under the instructor's
//     name. The instructor edits it; the student reads the new text, and the
//     week stays released.
//   - **On behalf.** Course week 4 has no response. The lead sees it owed at 48
//     hours past its report opening, and past 96 hours publishes on behalf; the
//     student reads the lead's name and role.
//   - **Not your role.** The student, opening a leadership page, reads that it
//     is not part of their role.
//
// **The section is `MATH-140-E1FF`.** The student has to be the mock platform's
// one launchable learner, and of her sections `BIOL-215-R3WW`'s response table
// is read empty by `instructor-response.spec.ts`, which runs after this file.
// The response table is append-only, so this file cannot be run twice on one
// stack: a second run's publish is refused as a second response.
//
// **No date is pinned.** Every instant is read from the section's own
// `survey_window` rows and moved to with the `/dev` clock. A week's report opens
// on the first Monday at 06:00 in the institution's zone after its window
// closes (`reporting.report_opens_at`), computed here from the window row. The
// learner's enrollment is dated from the section's start by
// `standTheLearnerIn`, so every reading clock here stands after it.
//
// **The policy covers course weeks 3 and 4 only.** It is set a day before week
// 3's report opens, after week 2's, and set back to encouraged at the end, past
// week 4's opening and before week 5's (SPEC §5.3: the policy in force when a
// week's report opens governs that week).
//
// **The seats are real grants, removed afterwards**, as in
// `leadership-response.spec.ts`: `MATH 140` is mapped to the mock world's Lead
// Faculty member and the mapping deleted on the way out. The mock instructor's
// name is set for this file and put back to what it was.
//
// **Only the answers are seeded** (`scripts/seed_response_loop_exit_story.py`).
// The policy and every response go through the product's own pages.
//
// This spec cannot be run without a seeded, running Compose stack built from the
// branch; its green is the stack-up run and CI.

import { test, expect, type Locator, type Page } from '@playwright/test';

import { clearTheClock, setTheClockTo } from './support/clock';
import { launchAs, signInAs } from './support/doors';
import {
  databaseStatement,
  seedTheResponseLoopExitStory,
  stopTheScheduler,
} from './support/stack';
import {
  INSTRUCTOR_SUBJECT,
  LEARNER_SUBJECT,
  STUDENT_VIEW,
  clearTheWeek,
  sectionStartClock,
  standTheLearnerIn,
  type SectionUnderTest,
} from './support/survey';

const MATHEMATICS: SectionUnderTest = { label: 'MATH-140-E1FF', code: 'E1FF' };

const INSTRUCTORS_WEEK = 3;
const ON_BEHALF_WEEK = 4;

const LEAD_WEB_SUBJECT = 'mock-idp-user-lead-faculty';
const LEAD_NAME = 'Demo Mock-World Lead Faculty';
const LEAD_PERSON = `(select id from person where identity_name = '${LEAD_NAME}')`;
const SECTION = `(select id from section where lms_section_code = '${MATHEMATICS.code}')`;
const THE_COURSE = `(select course_id from section where lms_section_code = '${MATHEMATICS.code}')`;
const INSTRUCTOR =
  '(select ra.person_id from role_assignment ra ' +
  `where ra.role = 'INSTRUCTOR' and ra.section_id = ${SECTION} limit 1)`;

const INSTRUCTOR_NAME = 'Professor Imogen Quarry';
const REPLY = 'You told us the problem sets ran long. We are cutting two questions from each.';
const REVISED = 'You told us the problem sets ran long. We are cutting two questions and adding hints.';
const LEADS = 'Thank you for your notes on pacing. The next unit starts with a review session.';

// Governed words, transcribed (`docs/MISTAKES.md` entry 19).
const AWAITING = 'There is no reply to show for this week yet.';
const LEADS_BYLINE = `${LEAD_NAME}, Lead Faculty`;
const NOT_YOUR_ROLE = /not part of your role/i;
const LEADERSHIP_VIEW = 'pulse-landing-leadership';
const POLICY_LINK = 'Response policy';
const OWED_LINK = 'Responses owed';
const OWED_LIST = 'pulse-leadership-responses-owed-list';
const ON_BEHALF_PAGE = 'pulse-leadership-on-behalf';
const SWITCH_NAME = 'Response required for MATH courses you set';
const SAVED = 'Setting saved for MATH. It applies from the next week’s report.';
const RESPOND = 'Respond on behalf';
const THE_SECTION_ROW = 'MATH 140 E1FF';
const CARD = 'article.pulse-response-card';

const WORLD_TIMEOUT_MS = 300_000;
const CASE_TIMEOUT_MS = 120_000;
const INSTITUTION_ZONE = 'America/New_York';

let placement = '';
let sectionId = '';
const reportOpens: Record<number, string> = {};
let mappedTheLead = false;
let formerInstructorName = '';

test.describe.configure({ mode: 'serial' });

/** The report-open minute of one course week, `YYYY-MM-DDTHH:MM` local, from its window row. */
function reportOpensOf(courseWeek: number): string {
  const closes =
    `(select closes_at from survey_window where section_id = ${SECTION} ` +
    `order by opens_at offset ${String(courseWeek - 1)} limit 1)`;
  return databaseStatement(
    'select to_char(' +
      `date_trunc('week', ${closes} at time zone '${INSTITUTION_ZONE}') ` +
      `+ interval '7 days 6 hours', 'YYYY-MM-DD"T"HH24:MI');`,
  );
}

/** A wall-clock minute plus whole hours; the days in play never cross a clock change. */
function plusHours(minute: string, hours: number): string {
  const at = new Date(`${minute}:00Z`);
  at.setUTCHours(at.getUTCHours() + hours);
  return at.toISOString().slice(0, 16);
}

/** Sign in as the lead and open one of the landing's links. */
async function leadOpens(page: Page, link: string): Promise<void> {
  await signInAs(page, LEAD_WEB_SUBJECT);
  await expect(page.getByTestId(LEADERSHIP_VIEW)).toBeVisible();
  await page.getByRole('link', { name: link }).click();
}

/** Launch as the learner and open one course week's results page. */
async function studentReads(page: Page, courseWeek: number): Promise<Locator> {
  await launchAs(page, LEARNER_SUBJECT, placement);
  // The launch hands the session over in the address bar; the landing showing
  // means the page has stored it, so the navigation below carries it.
  await expect(page.getByTestId(STUDENT_VIEW)).toBeVisible();
  await page.goto(`/app/student/sections/${sectionId}/weeks/${String(courseWeek)}/results`);
  const results = page.getByTestId('pulse-student-results');
  await expect(results).toBeVisible();
  return results;
}

test.beforeAll(async ({ browser }) => {
  test.setTimeout(WORLD_TIMEOUT_MS);
  stopTheScheduler();
  placement = await standTheLearnerIn(browser, [MATHEMATICS], sectionStartClock(MATHEMATICS.code));
  clearTheWeek([MATHEMATICS.code]);
  sectionId = databaseStatement(`select ${SECTION};`);
  expect(sectionId, 'The section was not provisioned by the staff launch.').toMatch(/^[0-9a-f-]{36}$/);

  for (const courseWeek of [INSTRUCTORS_WEEK, ON_BEHALF_WEEK, ON_BEHALF_WEEK + 1]) {
    reportOpens[courseWeek] = reportOpensOf(courseWeek);
    expect(
      reportOpens[courseWeek],
      `Course week ${String(courseWeek)}'s report opening could not be derived from its window.`,
    ).toMatch(/^\d{4}-\d\d-\d\dT06:00$/);
  }

  formerInstructorName = databaseStatement(
    `select coalesce(quote_literal(identity_name), 'NULL') from person where id = ${INSTRUCTOR};`,
  );
  expect(formerInstructorName, 'No person holds an INSTRUCTOR grant on the section.').not.toBe('');
  databaseStatement(`update person set identity_name = '${INSTRUCTOR_NAME}' where id = ${INSTRUCTOR};`);

  databaseStatement(
    `delete from lead_faculty_mapping where course_id = ${THE_COURSE} and person_id = ${LEAD_PERSON};`,
  );
  mappedTheLead =
    databaseStatement(
      'with inserted as (insert into lead_faculty_mapping (person_id, course_id) ' +
        `select ${LEAD_PERSON}, ${THE_COURSE} on conflict (course_id) do nothing returning 1) ` +
        'select count(*) from inserted;',
    ) === '1';
  expect(mappedTheLead, 'MATH 140 already has a lead, so this run cannot give it the mock world’s lead.').toBe(
    true,
  );

  const printed = seedTheResponseLoopExitStory();
  expect(printed).toContain('wrote MATH-140-E1FF: 6 responses');
});

test.afterAll(async ({ browser }) => {
  const context = await browser.newContext();
  try {
    try {
      if (mappedTheLead) {
        databaseStatement(
          `delete from lead_faculty_mapping where course_id = ${THE_COURSE} and person_id = ${LEAD_PERSON};`,
        );
      }
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

test('the lead sets the course to required before course week 3’s report opens', async ({ page }) => {
  test.setTimeout(CASE_TIMEOUT_MS);
  // A day before week 3's report opens, and so after week 2's.
  await setTheClockTo(page, plusHours(reportOpens[INSTRUCTORS_WEEK], -24));
  await leadOpens(page, POLICY_LINK);
  const toggle = page.getByRole('switch', { name: SWITCH_NAME });
  await expect(toggle).toHaveAttribute('aria-checked', 'false');
  await toggle.click();
  await expect(page.getByText(SAVED)).toBeVisible();
  expect(
    databaseStatement(
      `select mode from response_policy where course_id = ${THE_COURSE} order by sequence desc limit 1;`,
    ),
    'The switch did not record a required policy for MATH 140.',
  ).toBe('REQUIRED');
});

test('in the required week the student reads the closed door and nothing else', async ({ page }) => {
  test.setTimeout(CASE_TIMEOUT_MS);
  await setTheClockTo(page, plusHours(reportOpens[INSTRUCTORS_WEEK], 1));
  const results = await studentReads(page, INSTRUCTORS_WEEK);
  await expect(results.getByText(AWAITING)).toBeVisible();
  await expect(results.locator(CARD)).toHaveCount(0);
  const text = (await results.textContent()) ?? '';
  expect(text).not.toContain(INSTRUCTOR_NAME);
  expect(text).not.toContain(LEAD_NAME);
});

test('the instructor drafts, checks and publishes; the student reads it by name, and after an edit the new text', async ({
  page,
}) => {
  test.setTimeout(CASE_TIMEOUT_MS);
  await setTheClockTo(page, plusHours(reportOpens[INSTRUCTORS_WEEK], 2));

  await launchAs(page, INSTRUCTOR_SUBJECT, placement);
  await page
    .getByTestId('pulse-instructor-sections')
    .getByRole('link', { name: /MATH 140 E1FF/ })
    .click();
  await expect(page.getByTestId('pulse-instructor-report')).toBeVisible();
  const composer = page.getByRole('region', { name: 'Your response to this week' });
  const editor = composer.getByRole('textbox', { name: 'Your response' });

  await composer.getByRole('button', { name: 'Draft with AI', exact: true }).click();
  await expect(editor).not.toHaveValue('');
  await composer.getByRole('button', { name: 'Check draft with AI' }).click();
  await expect(composer.getByRole('region', { name: 'Themes your draft has not addressed' })).toBeVisible();
  expect(
    databaseStatement(`select count(*) from instructor_response where section_id = ${SECTION};`),
    'A draft and a check were run and nothing was published, so the section holds no response.',
  ).toBe('0');

  await editor.fill(REPLY);
  await composer.getByRole('button', { name: 'Publish' }).click();
  await expect(composer.locator(CARD).getByText(REPLY)).toBeVisible();

  let results = await studentReads(page, INSTRUCTORS_WEEK);
  await expect(results.locator(CARD).getByText(REPLY)).toBeVisible();
  await expect(results.locator(CARD).getByText(INSTRUCTOR_NAME, { exact: true })).toBeVisible();
  await expect(results.getByText(AWAITING)).toHaveCount(0);

  await launchAs(page, INSTRUCTOR_SUBJECT, placement);
  await page
    .getByTestId('pulse-instructor-sections')
    .getByRole('link', { name: /MATH 140 E1FF/ })
    .click();
  await composer.getByRole('button', { name: 'Edit response' }).click();
  await expect(editor).toHaveValue(REPLY);
  await editor.fill(REVISED);
  await composer.getByRole('button', { name: 'Publish changes' }).click();
  await expect(composer.locator(CARD).getByText(REVISED)).toBeVisible();

  results = await studentReads(page, INSTRUCTORS_WEEK);
  await expect(results.locator(CARD).getByText(REVISED)).toBeVisible();
  await expect(results.locator(CARD).getByText(INSTRUCTOR_NAME, { exact: true })).toBeVisible();
  await expect(results.getByText(REPLY, { exact: true })).toHaveCount(0);
  await expect(results.getByText(AWAITING)).toHaveCount(0);
});

test('course week 4 is owed at 48 hours, and past 96 the lead publishes on behalf under their name and role', async ({
  page,
}) => {
  test.setTimeout(CASE_TIMEOUT_MS);
  await setTheClockTo(page, plusHours(reportOpens[ON_BEHALF_WEEK], 48));
  await leadOpens(page, OWED_LINK);
  let row = page
    .getByTestId(OWED_LIST)
    .getByRole('listitem')
    .filter({ hasText: THE_SECTION_ROW })
    .filter({ hasText: `Week ${String(ON_BEHALF_WEEK)}` });
  await expect(row).toHaveCount(1);
  await expect(row.getByRole('link', { name: new RegExp(RESPOND) })).toHaveCount(0);

  let results = await studentReads(page, ON_BEHALF_WEEK);
  await expect(results.getByText(AWAITING)).toBeVisible();
  await expect(results.locator(CARD)).toHaveCount(0);

  await setTheClockTo(page, plusHours(reportOpens[ON_BEHALF_WEEK], 96));
  await leadOpens(page, OWED_LINK);
  row = page
    .getByTestId(OWED_LIST)
    .getByRole('listitem')
    .filter({ hasText: THE_SECTION_ROW })
    .filter({ hasText: `Week ${String(ON_BEHALF_WEEK)}` });
  await row.getByRole('link', { name: new RegExp(RESPOND) }).click();
  const onBehalf = page.getByTestId(ON_BEHALF_PAGE);
  await onBehalf.getByRole('textbox', { name: 'Your response' }).fill(LEADS);
  await onBehalf.getByRole('button', { name: 'Publish' }).click();
  await expect(onBehalf.locator(CARD).getByText(LEADS)).toBeVisible();

  results = await studentReads(page, ON_BEHALF_WEEK);
  await expect(results.locator(CARD).getByText(LEADS)).toBeVisible();
  await expect(results.locator(CARD).getByText(LEADS_BYLINE, { exact: true })).toBeVisible();
  await expect(results.getByText(AWAITING)).toHaveCount(0);
  expect((await results.textContent()) ?? '').not.toContain(INSTRUCTOR_NAME);
});

test('the student, opening a leadership page, reads that it is not part of their role', async ({ page }) => {
  test.setTimeout(CASE_TIMEOUT_MS);
  await launchAs(page, LEARNER_SUBJECT, placement);
  await expect(page.getByTestId(STUDENT_VIEW)).toBeVisible();
  await page.goto('/app/leadership/responses-owed');
  await expect(page.getByText(NOT_YOUR_ROLE).first()).toBeVisible();
  await expect(page.getByText(LEADS)).toHaveCount(0);
});

test('the lead sets the course back to encouraged before course week 5’s report opens', async ({ page }) => {
  // The policy table is append-only, so the setting this run made is undone by
  // a later row, dated before week 5 opens: only weeks 3 and 4 were held.
  test.setTimeout(CASE_TIMEOUT_MS);
  await setTheClockTo(page, plusHours(reportOpens[ON_BEHALF_WEEK], 96));
  expect(plusHours(reportOpens[ON_BEHALF_WEEK], 96) < reportOpens[ON_BEHALF_WEEK + 1]).toBe(true);
  await leadOpens(page, POLICY_LINK);
  const toggle = page.getByRole('switch', { name: SWITCH_NAME });
  await expect(toggle).toHaveAttribute('aria-checked', 'true');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-checked', 'false');
  expect(
    databaseStatement(
      `select mode from response_policy where course_id = ${THE_COURSE} order by sequence desc limit 1;`,
    ),
  ).toBe('ENCOURAGED');
});
