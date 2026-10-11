// SPEC §14.3's E6 exit, driven on the running stack: "the anti-cherry-picking
// trail is visible up-chain, and a welfare-flagged comment in a 3-response week
// provably reaches Care with no trace in the instructor view."
//
// **The world.** `scripts/seed_moderation_exit_story.py` writes course weeks 9
// to 11 of `BIOL-215-R3WW`: week 9 has three responses and no comment, week 10
// has eight responses with comments shown in both streams, and week 11 has
// three responses and one comment carrying the mock provider's self-harm
// marker. Week 10 holds the two comments the instructor decides on: one with
// no marker, which she excludes with a reason, and one with the mock
// provider's harmful marker, which she keeps. Nothing here plants a moderation
// verdict: the real hourly sweep asks the mock provider, and the provider's
// answer routes each comment (ADR 0188). The summaries come from the real
// summary walk.
//
// **The seats.** The mock world's Lead Faculty member leads `BUSA 300` and its
// chair chairs Business Administration, so neither reviews `BIOL 215`. This file
// maps `BIOL 215` to the lead and gives the chair a chair assignment over
// Biology for the length of the run, and removes exactly what it added on the
// way out. A course with a lead is the lead's to review, and its chair's only
// once it has none (SPEC §2.1, ADR 0190), so the log is read twice: by both
// seats while the course is led, and by both again after the mapping is
// removed. The instructor reaches no log at all.
//
// **The clock.** Staff launches and the roster sync run at the real clock, for
// the reason `exit-instructor-report.spec.ts` records: the sync dates an
// enrollment from the effective clock. The clock then moves to Monday
// 23 November 2026 at 09:00, after course week 11's window shut (ADR 0184's
// 06:00 opening), and is cleared in `afterAll`. Like every drive here that
// reads a pinned date, this one needs the real date to be on or before it.
//
// **Shared state.** The scheduler is stopped first (`stopTheScheduler` says
// why), `BIOL-215-R3WW`'s answers are cleared before and after, so the specs
// that run later find the section as they expect it.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect, type Browser, type Locator, type Page } from '@playwright/test';

import { clearTheClock, setTheClockTo } from './support/clock';
import { DEV_CONSOLE_PATH, launchAs, placementInto, sessionToken, signInAs } from './support/doors';
import {
  databaseStatement,
  deriveSurveyWindows,
  generateWeeklySummaries,
  moderateClosedWindows,
  seedTheModerationExitStory,
  stopTheScheduler,
} from './support/stack';
import { INSTRUCTOR_SUBJECT, LEARNER_SUBJECT, clearTheWeek } from './support/survey';

const BIOL = { label: 'BIOL-215-R3WW', code: 'R3WW', menu: 'BIOL 215 R3WW' };

// The seeded calendar, read off `survey_window`: `R3WW`'s course week 11 is term
// week 14, whose window closes at 23:59:59 on Sunday 22 November in the
// institution's zone. Its report opens at 06:00 the next morning.
const AFTER_WEEK_ELEVEN = '2026-11-23T09:00';
const NO_COMMENT_WEEK = 9;
const TRAIL_WEEK = 10;
const WELFARE_WEEK = 11;

// The seeder's sentences, transcribed rather than imported (`docs/MISTAKES.md`
// entry 19).
const EXCLUDED_WITH_A_REASON =
  "Moderation exit unflagged: the instructor mentioned a classmate's grade aloud in lab.";
const FLAGGED_AND_KEPT =
  "Moderation exit flagged: the lectures are a waste of everybody's time this term. mock-ai:harmful";
const WELFARE_COMMENT =
  'Moderation exit welfare: I do not see the point of going on with any of this anymore. ' +
  'mock-ai:self-harm';
const WELFARE_WORDS = 'Moderation exit welfare';
const COURSE_VOICE = 'Moderation exit voice one, course: the lab manual matched the lecture this week.';

// What the instructor types as her reason.
const REASON = 'It names a classmate and their grade, which other students should not read.';

// The summary the summary walk stores for a stream with no comment to show
// (`app.ai.tasks.EMPTY_WEEK_SUMMARY`).
const EMPTY_WEEK_SUMMARY = 'There are no comments to show for this week.';

// The seats, by the web subjects `mock-idp/app/seed.py` publishes and the names
// `scripts/seed.py` gives their person rows.
const LEAD_WEB_SUBJECT = 'mock-idp-user-lead-faculty';
const CHAIR_WEB_SUBJECT = 'mock-idp-user-chair';
const LEAD_PERSON = `(select id from person where identity_name = 'Demo Mock-World Lead Faculty')`;
const CHAIR_PERSON = `(select id from person where identity_name = 'Demo Mock-World Chair')`;
const THE_COURSE = `(select distinct course_id from section where lms_section_code = '${BIOL.code}')`;
const BIOLOGY = `(select id from department where name = 'Biology')`;

// The respondents the seeder needs enrolled, as `scripts/seed_moderation_exit_story.py`
// names them.
const RESPONDENTS = [
  LEARNER_SUBJECT,
  ...[1, 2, 3, 5, 6, 8, 9].map(
    (ordinal) => `mock-lms-user-${BIOL.label.toLowerCase()}-student-${String(ordinal).padStart(2, '0')}`,
  ),
];

// Testids and governed words, transcribed (`docs/MISTAKES.md` entry 19).
const INSTRUCTOR_LANDING = 'pulse-landing-instructor';
const SECTIONS_MENU = 'pulse-instructor-sections';
const REPORT = 'pulse-instructor-report';
const LEADERSHIP_VIEW = 'pulse-landing-leadership';
const LOG_PAGE_PATH = '/app/leadership/exclusion-log';
const LOG_LIST = 'pulse-leadership-exclusion-log-list';
const LOG_API_PATH = '/leadership/moderation/log';
const ROSTER_SYNC_RUN = 'roster-sync-run';
const EXCLUDE = 'Exclude from student view';
const EXCLUDE_WITH_REASON = 'Exclude with this reason';
const REASON_LABEL = 'Why should students not see this comment?';
const KEEP = 'Keep for students';
const REVIEW = 'Review comment';
const EXCLUDED_NOTICE = /^Excluded — students will not see this comment/;
const KEPT_BY_YOU = 'You kept this comment for students.';
const EXCLUDED_ROW = 'Excluded · Unflagged, reason given';
const KEPT_ROW = 'Kept · AI-flagged';
const AS_INSTRUCTOR = 'Decided by the instructor';

const WORLD_TIMEOUT_MS = 300_000;
const CASE_TIMEOUT_MS = 120_000;
const ROSTER_TIMEOUT_MS = 60_000;
const ROSTER_RETRY_MS = 3_000;

let placement = '';
let mappedTheLead = false;
let chairAssignment = '';

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  test.setTimeout(WORLD_TIMEOUT_MS);
  stopTheScheduler();
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    placement = await placementInto(page, INSTRUCTOR_SUBJECT, BIOL.label);
    expect(
      await placementInto(page, LEARNER_SUBJECT, BIOL.label),
      `The mock platform should offer the instructor and the learner the same link into ${BIOL.label}.`,
    ).toBe(placement);

    // The staff launch, the windows and the roster, at the real clock.
    await clearTheClock(page);
    await launchAs(page, INSTRUCTOR_SUBJECT, placement);
    await expect(page.getByTestId(INSTRUCTOR_LANDING)).toBeVisible();
    deriveSurveyWindows();
    await page.goto(DEV_CONSOLE_PATH);
    await page.getByTestId(ROSTER_SYNC_RUN).click();
    await waitForTheRoster();

    // The story, on a clean section.
    clearTheWeek([BIOL.code]);
    expect(seedTheModerationExitStory(), 'The moderation exit story seeder printed nothing.').toContain(
      'wrote BIOL-215-R3WW: 12 comments',
    );

    // The close, then the two jobs, in the beat's order: moderation at minute
    // 10, the summary walk at minute 50.
    await setTheClockTo(page, AFTER_WEEK_ELEVEN);
    moderateClosedWindows();
    generateWeeklySummaries();
    expect(
      databaseStatement(
        'select count(*) from answer a join response r on r.id = a.response_id ' +
          `join section s on s.id = r.section_id where s.lms_section_code = '${BIOL.code}' ` +
          "and a.comment_text is not null and not exists (select 1 from classification c " +
          "where c.answer_id = a.id and c.task = 'MODERATION');",
      ),
      'A seeded comment holds no moderation verdict after the sweep, so its week shows nothing.',
    ).toBe('0');

    // The seats, recording what this run added so that only that is removed.
    expect(
      databaseStatement(`select count(*) from lead_faculty_mapping where course_id = ${THE_COURSE};`),
      'BIOL 215 already has a lead, so this run cannot give it the mock world’s lead.',
    ).toBe('0');
    databaseStatement(
      `insert into lead_faculty_mapping (person_id, course_id) select ${LEAD_PERSON}, ${THE_COURSE};`,
    );
    mappedTheLead = true;
    chairAssignment = databaseStatement(
      `insert into role_assignment (person_id, role, department_id) ` +
        `select ${CHAIR_PERSON}, 'CHAIR', ${BIOLOGY} returning id;`,
    );
    expect(chairAssignment, 'The chair seat over Biology was not written.').toMatch(
      /^[0-9a-f-]{36}$/,
    );
  } finally {
    await context.close();
  }
});

test.afterAll(async ({ browser }) => {
  const context = await browser.newContext();
  try {
    try {
      if (mappedTheLead) {
        databaseStatement(
          `delete from lead_faculty_mapping where course_id = ${THE_COURSE} ` +
            `and person_id = ${LEAD_PERSON};`,
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

test('a comment with the self-harm marker opens a threat case', () => {
  // No product reader of `threat_case` exists before the Care queue, so the
  // table is read directly, by the comment's own words.
  expect(
    databaseStatement(
      'select count(*) from threat_case t join answer a on a.id = t.answer_id ' +
        `where a.comment_text = '${WELFARE_COMMENT}';`,
    ),
    'The self-harm comment has no threat case: SPEC §6.2 routes it to Care at window close.',
  ).toBe('1');
});

test('the instructor’s welfare week shows what a week with no comment shows', async ({ page }) => {
  test.setTimeout(CASE_TIMEOUT_MS);
  const report = await openTheReport(page);
  const sectionId = sectionIdFromTheUrl(page);
  const token = (await sessionToken(page)) ?? '';

  const welfare = await reportFor(page, token, sectionId, WELFARE_WEEK);
  const quiet = await reportFor(page, token, sectionId, NO_COMMENT_WEEK);
  const canary = await reportFor(page, token, sectionId, TRAIL_WEEK);

  for (const stream of ['instructor', 'course']) {
    expect(commentBearing(welfare, stream), `The ${stream} stream of week 11`).toEqual(
      commentBearing(quiet, stream),
    );
    expect(commentBearing(welfare, stream).summary).toBe(EMPTY_WEEK_SUMMARY);
  }
  expect(JSON.stringify(welfare)).not.toContain(WELFARE_WORDS);

  // The canary: the same world's week 10 shows its comments.
  const courseTexts = streamOf(canary, 'course').comments.map((card) => card.text);
  expect(courseTexts, 'Week 10 shows no course comments, so the absence above means nothing.').toContain(
    COURSE_VOICE,
  );

  // And the page as drawn: the latest week is the welfare week.
  await expect(report).not.toContainText(WELFARE_WORDS);
  await expect(report).toContainText(EMPTY_WEEK_SUMMARY);
});

test('the instructor excludes an unflagged comment with a reason and keeps a flagged one', async ({
  page,
}) => {
  test.setTimeout(CASE_TIMEOUT_MS);
  const report = await openTheReport(page);
  await page.getByRole('button', { name: 'Previous week' }).click();
  await expect(page).toHaveURL(new RegExp(`[?&]week=${String(TRAIL_WEEK)}\\b`));
  await expect(report).toContainText(COURSE_VOICE);

  const unflagged = report.getByRole('article').filter({ hasText: EXCLUDED_WITH_A_REASON });
  await expect(unflagged).toHaveCount(1);
  await unflagged.getByRole('button', { name: EXCLUDE }).click();
  await unflagged.getByLabel(REASON_LABEL).fill(REASON);
  await unflagged.getByRole('button', { name: EXCLUDE_WITH_REASON }).click();
  await expect(
    report.getByRole('article').filter({ hasText: EXCLUDED_WITH_A_REASON }).getByText(EXCLUDED_NOTICE),
  ).toBeVisible();

  const flagged = report.getByRole('article').filter({ hasText: 'Flagged: harmful' });
  await expect(flagged).toHaveCount(1);
  await flagged.getByRole('button', { name: REVIEW }).click();
  await expect(flagged.getByText(FLAGGED_AND_KEPT)).toBeVisible();
  await flagged.getByRole('button', { name: KEEP }).click();
  await expect(
    report.getByRole('article').filter({ hasText: FLAGGED_AND_KEPT }).getByText(KEPT_BY_YOU),
  ).toBeVisible();
});

test('while the course has a lead, the lead finds both rows and the chair finds neither', async ({
  browser,
}) => {
  test.setTimeout(CASE_TIMEOUT_MS);
  await asSeat(browser, LEAD_WEB_SUBJECT, expectTheTrail);
  await asSeat(browser, CHAIR_WEB_SUBJECT, expectNoTrail);
});

test('once the course has no lead, the chair finds both rows and the lead finds neither', async ({
  browser,
}) => {
  test.setTimeout(CASE_TIMEOUT_MS);
  databaseStatement(
    `delete from lead_faculty_mapping where course_id = ${THE_COURSE} and person_id = ${LEAD_PERSON};`,
  );
  mappedTheLead = false;
  await asSeat(browser, CHAIR_WEB_SUBJECT, expectTheTrail);
  await asSeat(browser, LEAD_WEB_SUBJECT, expectNoTrail);
});

test('an instructor-only seat reaches no exclusion log', async ({ page }) => {
  test.setTimeout(CASE_TIMEOUT_MS);
  await openTheReport(page);
  const token = (await sessionToken(page)) ?? '';
  const answered = await page.request.get(LOG_API_PATH, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
  });
  expect(answered.status(), 'An instructor read the exclusion log.').not.toBe(200);
  expect(await answered.text()).not.toContain(REASON);
});

/** Sign one seat in at the web door, in a browser context of its own, and open its exclusion log. */
async function asSeat(
  browser: Browser,
  subject: string,
  check: (page: Page, subject: string) => Promise<void>,
): Promise<void> {
  const context = await browser.newContext();
  try {
    const page = await context.newPage();
    await signInAs(page, subject);
    await expect(page.getByTestId(LEADERSHIP_VIEW)).toBeVisible();
    await page.goto(LOG_PAGE_PATH);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await check(page, subject);
  } finally {
    await context.close();
  }
}

/** Both of the instructor's decisions are in this seat's log, each naming the role. */
async function expectTheTrail(page: Page, subject: string): Promise<void> {
  const rows = page.getByTestId(LOG_LIST).getByRole('listitem').filter({ hasText: BIOL.menu });
  const excluded = rows.filter({ hasText: REASON });
  await expect(excluded, `${subject} does not find the reasoned exclusion.`).toHaveCount(1);
  await expect(excluded).toContainText(EXCLUDED_ROW);
  await expect(excluded).toContainText(AS_INSTRUCTOR);
  const kept = rows.filter({ hasText: KEPT_ROW });
  await expect(kept, `${subject} does not find the kept flagged comment.`).toHaveCount(1);
  await expect(kept).toContainText(AS_INSTRUCTOR);
}

/** This seat's log holds no row from this section. */
async function expectNoTrail(page: Page, subject: string): Promise<void> {
  await expect(page.getByText(REASON), `${subject} finds the reasoned exclusion.`).toHaveCount(0);
  await expect(page.getByText(BIOL.menu), `${subject} finds a row from ${BIOL.menu}.`).toHaveCount(0);
}

/** Launch the instructor and open this section's report at its latest published week. */
async function openTheReport(page: Page): Promise<Locator> {
  await launchAs(page, INSTRUCTOR_SUBJECT, placement);
  await expect(page.getByTestId(INSTRUCTOR_LANDING)).toBeVisible();
  await page.getByTestId(SECTIONS_MENU).getByRole('link', { name: new RegExp(BIOL.menu) }).click();
  const report = page.getByTestId(REPORT);
  await expect(report).toBeVisible();
  return report;
}

type Card = { text: string };
type Stream = {
  comments: Card[];
  summary: { text: string } | null;
  small_n: unknown;
};
type WeekReport = { streams: Record<string, Stream> };

function streamOf(body: WeekReport, stream: string): Stream {
  const found = body.streams[stream];
  expect(found, `The report carries no ${stream} stream.`).toBeDefined();
  return found;
}

/** The members of one stream that show a comment, summarize comments, or count commenters. */
function commentBearing(
  body: WeekReport,
  stream: string,
): { comments: Card[]; summary: string | null; small_n: unknown } {
  const found = streamOf(body, stream);
  return { comments: found.comments, summary: found.summary?.text ?? null, small_n: found.small_n };
}

async function reportFor(
  page: Page,
  token: string,
  sectionId: string,
  courseWeek: number,
): Promise<WeekReport> {
  const answered = await page.request.get(
    `/instructor/sections/${sectionId}/report/${String(courseWeek)}`,
    { headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' } },
  );
  expect(answered.status(), `The report for course week ${String(courseWeek)}`).toBe(200);
  return (await answered.json()) as WeekReport;
}

function sectionIdFromTheUrl(page: Page): string {
  const found = /\/instructor\/sections\/([0-9a-f-]+)/.exec(page.url());
  expect(found, `The report's address carries no section key: ${page.url()}`).not.toBeNull();
  return found?.[1] ?? '';
}

/** Wait until every respondent the seeder needs is enrolled in the section. */
async function waitForTheRoster(): Promise<void> {
  const deadline = Date.now() + ROSTER_TIMEOUT_MS;
  let missing = [...RESPONDENTS];
  while (missing.length > 0 && Date.now() < deadline) {
    const enrolled = new Set(
      databaseStatement(
        'select u.lms_user_id from enrollment e join "user" u on u.id = e.user_id ' +
          `join section s on s.id = e.section_id where s.lms_section_code = '${BIOL.code}';`,
      )
        .split('\n')
        .map((row) => row.trim()),
    );
    missing = missing.filter((subject) => !enrolled.has(subject));
    if (missing.length > 0) await new Promise((wake) => setTimeout(wake, ROSTER_RETRY_MS));
  }
  expect(missing, 'These respondents were not enrolled by the roster sync.').toEqual([]);
}
