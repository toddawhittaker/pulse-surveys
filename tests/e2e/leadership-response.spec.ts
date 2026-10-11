// The leadership response pages, end to end — SPEC §5.3 and §5.6.
//
// A Lead Faculty member sets a course's response to required from the policy
// page; with the stack's clock moved forward from the seeded calendar, the
// section is owed a response at report open plus 48 hours and is not at plus 47;
// past plus 96 hours the lead publishes on behalf and reads the card students
// will see, signed with the lead's own name and role. A chair, on the same
// course, sees the setting read-only and attributed to the lead's role. A
// distinctive comment a student wrote is absent from the on-behalf page.
//
// **The second week, not the first.** `instructor-response.spec.ts` publishes into the
// section's first week, and a week holds one response; this spec's policy is also
// set after the first week's report opened, so it governs the second week on.
//
// **No date is pinned.** The week's window and report-open instant are read from
// the section's own `survey_window` row and moved to with the `/dev` clock, so
// the calendar passing does not redden this spec. The report opens on the first
// Monday at 06:00 in the institution's zone after the window closes
// (`reporting.report_opens_at`), which is computed here from that row.
//
// **The seats are real grants, removed afterwards.** `BIOL 215` is seeded with no
// lead; this file maps it to the mock world's Lead Faculty member and gives the
// mock world's chair a chair seat over Biology, as `exit-moderation.spec.ts`
// does, and deletes exactly what it wrote on the way out. The mock instructor is
// given no grant at all: a leftover lead grant on a shared mock person sends
// that person to the leadership landing in every later spec.
//
// **Only the policy is set through the page.** The comment is written through
// the real survey form; the policy, the owed list and the publish are all the
// product's own doors.
//
// This spec cannot be run without a seeded, running Compose stack built from the
// branch; its green is the stack-up run and CI.

import { test, expect, type Page } from '@playwright/test';

import { expectNoAxeViolations } from './support/axe';
import { clearTheClock, setTheClockTo } from './support/clock';
import { signInAs } from './support/doors';
import { databaseStatement, stopTheScheduler } from './support/stack';
import {
  chooseRating,
  clearTheWeek,
  landOnTheSurvey,
  sectionStartClock,
  setSlider,
  standTheLearnerIn,
  SUBMIT,
  typeComment,
  type SectionUnderTest,
} from './support/survey';

const BIOL: SectionUnderTest = { label: 'BIOL-215-R3WW', code: 'R3WW' };

// The seats, by the web subjects the mock IdP publishes and the names
// `scripts/seed.py` gives their person rows.
const LEAD_WEB_SUBJECT = 'mock-idp-user-lead-faculty';
const CHAIR_WEB_SUBJECT = 'mock-idp-user-chair';
const LEAD_NAME = 'Demo Mock-World Lead Faculty';
const LEAD_PERSON = `(select id from person where identity_name = '${LEAD_NAME}')`;
const CHAIR_PERSON = `(select id from person where identity_name = 'Demo Mock-World Chair')`;
const SECTION = `(select id from section where lms_section_code = '${BIOL.code}')`;
const THE_COURSE = `(select distinct course_id from section where lms_section_code = '${BIOL.code}')`;
const BIOLOGY = `(select id from department where name = 'Biology')`;
// The section's second window, not its first: `instructor-response.spec.ts` publishes
// into the first week of this section, and a week holds one response.
const SECOND_WINDOW = `(select %COLUMN% from survey_window where section_id = ${SECTION} order by opens_at offset 1 limit 1)`;

// A comment no other string in the world contains, over SPEC §3.3's floor, with
// no marker the mock model answers to.
const PLANTED_COMMENT =
  'Pelican-quartz-7731 is what the field notebook rubric should have been called.';
const RESPONSE = 'You asked for a clearer rubric. We are rewriting it before the next lab.';

// Testids and governed words, transcribed (`docs/MISTAKES.md` entry 19).
const LEADERSHIP_VIEW = 'pulse-landing-leadership';
const POLICY_LINK = 'Response policy';
const OWED_LINK = 'Responses owed';
const OWED_PAGE = 'pulse-leadership-responses-owed';
const OWED_LIST = 'pulse-leadership-responses-owed-list';
const ON_BEHALF_PAGE = 'pulse-leadership-on-behalf';
const SWITCH_NAME = 'Response required for BIOL courses you set';
const SAVED = 'Setting saved for BIOL. It applies from the next week’s report.';
const EMPTY_TITLE = 'No responses are owed';
const RESPOND = 'Respond on behalf';
const READ_ONLY_NOTE = 'Set by the course’s Lead Faculty. Read-only at your role.';
const THE_SECTION_ROW = 'BIOL 215 R3WW';

const WORLD_TIMEOUT_MS = 300_000;
const CASE_TIMEOUT_MS = 120_000;
const INSTITUTION_ZONE = 'America/New_York';

let placement = '';
let windowOpensAt = '';
let reportOpensAt = '';
let mappedTheLead = false;
let chairAssignment = '';

test.describe.configure({ mode: 'serial' });

/** `YYYY-MM-DDTHH:MM`, the form the clock control takes, in the institution's zone. */
function localMinute(instant: string): string {
  return (
    `to_char(${instant} at time zone '${INSTITUTION_ZONE}', 'YYYY-MM-DD"T"HH24:MI')`
  );
}

/** A wall-clock minute plus whole hours; the calendar days in play never cross a clock change. */
function plusHours(minute: string, hours: number): string {
  const at = new Date(`${minute}:00Z`);
  at.setUTCHours(at.getUTCHours() + hours);
  return at.toISOString().slice(0, 16);
}

test.beforeAll(async ({ browser }) => {
  test.setTimeout(WORLD_TIMEOUT_MS);
  stopTheScheduler();
  placement = await standTheLearnerIn(browser, [BIOL], sectionStartClock(BIOL.code));
  clearTheWeek([BIOL.code]);

  // The second window's own dates. The report opens on the first Monday at 06:00
  // local after the window closes.
  windowOpensAt = databaseStatement(
    `select ${localMinute(SECOND_WINDOW.replace('%COLUMN%', 'opens_at'))};`,
  );
  reportOpensAt = databaseStatement(
    'select to_char(' +
      `date_trunc('week', ${SECOND_WINDOW.replace('%COLUMN%', 'closes_at')} at time zone '${INSTITUTION_ZONE}') ` +
      `+ interval '7 days 6 hours', 'YYYY-MM-DD"T"HH24:MI');`,
  );
  expect(windowOpensAt, 'The section has no survey window to read.').toMatch(/^\d{4}-\d\d-\d\dT\d\d:\d\d$/);
  expect(reportOpensAt, 'The report-open instant could not be derived.').toMatch(
    /^\d{4}-\d\d-\d\dT06:00$/,
  );

  // The seats, recording what this run added so that only that is removed.
  databaseStatement(
    `delete from lead_faculty_mapping where course_id = ${THE_COURSE} and person_id = ${LEAD_PERSON};`,
  );
  mappedTheLead =
    databaseStatement(
      `with inserted as (insert into lead_faculty_mapping (person_id, course_id) ` +
        `select ${LEAD_PERSON}, ${THE_COURSE} on conflict (course_id) do nothing returning 1) ` +
        `select count(*) from inserted;`,
    ) === '1';
  expect(mappedTheLead, 'BIOL 215 already has a lead, so this run cannot give it the mock world’s lead.').toBe(
    true,
  );
  chairAssignment = databaseStatement(
    `insert into role_assignment (person_id, role, department_id) ` +
      `select ${CHAIR_PERSON}, 'CHAIR', ${BIOLOGY} returning id;`,
  );
  expect(chairAssignment, 'The chair seat over Biology was not written.').toMatch(/^[0-9a-f-]{36}$/);

  // The student writes the distinctive comment through the real form, inside the
  // first window and so before the report opens.
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    await setTheClockTo(page, plusHours(windowOpensAt, 1));
    const block = await landOnTheSurvey(page, placement, BIOL.code);
    await chooseRating(block, 0, '4');
    await chooseRating(block, 1, '5');
    await typeComment(block, 0, PLANTED_COMMENT);
    await setSlider(block, '6.5');
    await block.getByTestId(SUBMIT).click();
    await expect(block.getByText('Your pulse is in', { exact: true })).toBeVisible();
  } finally {
    await context.close();
  }
  expect(
    databaseStatement(
      `select count(*) from answer a join response r on r.id = a.response_id ` +
        `where r.section_id = ${SECTION} and a.comment_text like '%Pelican-quartz-7731%';`,
    ),
    'The planted comment was not stored, so its absence from the page would prove nothing.',
  ).toBe('1');
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
      if (chairAssignment !== '') {
        databaseStatement(`delete from role_assignment where id = '${chairAssignment}';`);
      }
      clearTheWeek([BIOL.code]);
    } finally {
      await clearTheClock(await context.newPage());
    }
  } finally {
    await context.close();
  }
});

/** Sign in as the lead and open one of the landing's links. */
async function leadOpens(page: Page, link: string): Promise<void> {
  await signInAs(page, LEAD_WEB_SUBJECT);
  await expect(page.getByTestId(LEADERSHIP_VIEW)).toBeVisible();
  await page.getByRole('link', { name: link }).click();
}

test('a lead sets the course to required and the page says when it takes effect', async ({ page }) => {
  test.setTimeout(CASE_TIMEOUT_MS);
  await leadOpens(page, POLICY_LINK);

  await expect(
    page.getByText('A change applies from the next week’s report.', { exact: false }),
  ).toBeVisible();
  const toggle = page.getByRole('switch', { name: SWITCH_NAME });
  await expect(toggle).toHaveAttribute('aria-checked', 'false');
  await toggle.click();
  await expect(page.getByText(SAVED)).toBeVisible();
  await expect(toggle).toHaveAttribute('aria-checked', 'true');
  await expectNoAxeViolations(page, 'The policy page after a change');

  expect(
    databaseStatement(
      `select mode from response_policy where course_id = ${THE_COURSE} order by sequence desc limit 1;`,
    ),
    'The switch did not record a required policy for the course.',
  ).toBe('REQUIRED');
});

test('a section is owed at 48 hours past report open and not at 47', async ({ page }) => {
  test.setTimeout(CASE_TIMEOUT_MS);

  await setTheClockTo(page, plusHours(reportOpensAt, 47));
  await leadOpens(page, OWED_LINK);
  await expect(page.getByTestId(OWED_PAGE)).toBeVisible();
  await expect(page.getByText(EMPTY_TITLE)).toBeVisible();
  await expect(page.getByTestId(OWED_LIST)).toHaveCount(0);
  await expectNoAxeViolations(page, 'The empty owed list');

  await setTheClockTo(page, plusHours(reportOpensAt, 48));
  // The clock control leaves the page on the console, so the list is opened
  // again; the session the page holds is still good.
  await page.goto('/app/leadership/responses-owed');
  const row = page.getByTestId(OWED_LIST).getByRole('listitem').filter({ hasText: THE_SECTION_ROW });
  await expect(row).toHaveCount(1);
  await expect(row).toContainText('Week 2');
  // Owed, and not yet open to respond on behalf: that is 96 hours.
  await expect(row.getByRole('link', { name: RESPOND })).toHaveCount(0);
  const text = (await page.getByTestId(OWED_PAGE).textContent()) ?? '';
  expect(text).not.toMatch(/delinquent|late|overdue/i);
  await expectNoAxeViolations(page, 'The owed list with a week owed');
});

test('past 96 hours the lead publishes on behalf and reads the card under their own name', async ({
  page,
}) => {
  test.setTimeout(CASE_TIMEOUT_MS);
  await setTheClockTo(page, plusHours(reportOpensAt, 96));
  await leadOpens(page, OWED_LINK);

  const row = page.getByTestId(OWED_LIST).getByRole('listitem').filter({ hasText: THE_SECTION_ROW });
  await row.getByRole('link', { name: new RegExp(RESPOND) }).click();

  const onBehalf = page.getByTestId(ON_BEHALF_PAGE);
  await expect(onBehalf.getByRole('textbox', { name: 'Your response' })).toBeVisible();
  // The distinctive comment is stored and is nowhere on the page.
  expect(await onBehalf.textContent()).not.toContain('Pelican-quartz-7731');
  await expectNoAxeViolations(page, 'The on-behalf page before a publish');

  await onBehalf.getByRole('textbox', { name: 'Your response' }).fill(RESPONSE);
  await onBehalf.getByRole('button', { name: 'Publish' }).click();

  const card = onBehalf.locator('article.pulse-response-card');
  await expect(card.getByText(RESPONSE)).toBeVisible();
  await expect(card.getByText(`${LEAD_NAME}, Lead Faculty`, { exact: true })).toBeVisible();
  await expect(onBehalf.getByText('As students see it')).toBeVisible();
  expect(await onBehalf.textContent()).not.toContain('Pelican-quartz-7731');
  await expectNoAxeViolations(page, 'The on-behalf page after a publish');

  // Answered, so it leaves the owed list.
  await page.goto('/app/leadership/responses-owed');
  await expect(page.getByText(EMPTY_TITLE)).toBeVisible();
});

test('a chair sees the led course read-only, attributed to the lead’s role', async ({ page }) => {
  test.setTimeout(CASE_TIMEOUT_MS);
  await signInAs(page, CHAIR_WEB_SUBJECT);
  await expect(page.getByTestId(LEADERSHIP_VIEW)).toBeVisible();
  await page.getByRole('link', { name: POLICY_LINK }).click();

  const course = page.getByRole('listitem').filter({ hasText: 'BIOL 215' });
  await expect(course).toHaveCount(1);
  await expect(course).toContainText('Response required');
  await expect(course.getByText(READ_ONLY_NOTE)).toBeVisible();
  await expect(course.getByRole('switch')).toHaveCount(0);
  await expectNoAxeViolations(page, 'The policy page, read by a chair');
});

test('the lead sets the course back to encouraged, so later weeks and later specs are not held', async ({
  page,
}) => {
  // The policy table is append-only, so the setting this run made is undone by a
  // later row, set at the clock the run ended on: weeks whose report opens after
  // it are encouraged again.
  test.setTimeout(CASE_TIMEOUT_MS);
  await setTheClockTo(page, plusHours(reportOpensAt, 96));
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
