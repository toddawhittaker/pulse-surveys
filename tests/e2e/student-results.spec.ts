// The student's heading and results page — SPEC §5.3, §5.4, §7.6.
//
// Three things a student reads, on the composed stack:
//
//   - the survey names who teaches the section, in the heading area;
//   - a course whose policy requires a response shows a closed door for a week
//     that has none yet, and nothing else about the week;
//   - once the instructor's response is in, the card shows it, by name.
//
// The two seeded facts the stack does not hold are set in the database as its
// superuser: the instructor's name (the mock platform sends none, ADR 0050) and
// the course's policy (the doors that set one are another ticket's). The
// response is inserted as the section's own instructor, so the table's guard
// trigger judges it exactly as it judges the real writer's. The policy row goes
// in with its guard on: the instructor is first given the course's lead grant and
// mapping, which is what the guard checks.
//
// **No date is pinned.** The reading day is the section's start day (the seeded
// calendar, via `sectionStartClock`) plus seven days, which is the Monday the
// first course week's report opens (SPEC §3.1). The policy is recorded at the
// epoch, which is before any week's report opens whatever the calendar says.
//
// **The response table is append-only**, so this spec cannot reset the stack
// between runs; the block is serial and its last test is the one that publishes.
// The scheduler is stopped for the reason `stopTheScheduler` gives.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect } from "@playwright/test";

import { clearTheClock, setTheClockTo } from "./support/clock";
import { databaseStatement, stopTheScheduler } from "./support/stack";
import {
  LEARNER_SUBJECT,
  type SectionUnderTest,
  landOnTheSurvey,
  sectionStartClock,
  standTheLearnerIn,
} from "./support/survey";
import { launchAs } from "./support/doors";

const MATHEMATICS: SectionUnderTest = { label: "MATH-140-E1FF", code: "E1FF" };

// The name this spec gives the section's instructor, and the reply it publishes.
const INSTRUCTOR_NAME = "Professor Ada Ember";
const REPLY = "Thank you for the honest notes. We will slow the pace next week.";

const AWAITING = "There is no reply to show for this week yet.";
const LINK = "See your instructor’s reply";

test.describe.configure({ mode: "serial" });

let placement = "";

/** The section start day plus seven days: the Monday course week 1's report opens. */
function readingClock(): string {
  const start = new Date(`${sectionStartClock(MATHEMATICS.code).slice(0, 10)}T12:00:00Z`);
  start.setUTCDate(start.getUTCDate() + 7);
  return `${start.toISOString().slice(0, 10)}T12:00`;
}

const SECTION = `(select id from section where lms_section_code = '${MATHEMATICS.code}')`;
const INSTRUCTOR =
  "(select ra.person_id from role_assignment ra " +
  `where ra.role = 'INSTRUCTOR' and ra.section_id = ${SECTION} limit 1)`;
const FIRST_WEEK =
  "(select week_id from survey_window " +
  `where section_id = ${SECTION} order by opens_at limit 1)`;

test.beforeAll(async ({ browser }) => {
  test.setTimeout(180_000);
  stopTheScheduler();
  placement = await standTheLearnerIn(browser, [MATHEMATICS], sectionStartClock(MATHEMATICS.code));

  const named = databaseStatement(
    `update person set identity_name = '${INSTRUCTOR_NAME}' where id = ${INSTRUCTOR} returning id;`,
  );
  expect(
    named,
    "No person holds an INSTRUCTOR grant on the section, so there is no one to name. The staff " +
      "launch in `standTheLearnerIn` is what provisions that grant.",
  ).not.toBe("");

  const context = await browser.newContext();
  try {
    await setTheClockTo(await context.newPage(), readingClock());
  } finally {
    await context.close();
  }
});

test.afterAll(async ({ browser }) => {
  const context = await browser.newContext();
  try {
    await clearTheClock(await context.newPage());
  } finally {
    await context.close();
  }
});

test("the survey names the instructor in the section's heading and links to the reply", async ({
  page,
}) => {
  const block = await landOnTheSurvey(page, placement, MATHEMATICS.code);
  await expect(block.getByText(`with ${INSTRUCTOR_NAME}`, { exact: true })).toBeVisible();
  await expect(block.getByRole("link", { name: LINK })).toBeVisible();
});

test("a required-mode week with no reply shows the closed door and nothing about the week", async ({
  page,
}) => {
  // The instructor is made the course's lead, the way the guard checks it: a
  // LEAD_FACULTY assignment and the course's lead mapping.
  databaseStatement(
    "insert into role_assignment (person_id, role, course_id)\n" +
      `select ${INSTRUCTOR}, 'LEAD_FACULTY', s.course_id from section s where s.id = ${SECTION};\n` +
      "insert into lead_faculty_mapping (person_id, course_id)\n" +
      `select ${INSTRUCTOR}, s.course_id from section s where s.id = ${SECTION};\n` +
      "insert into response_policy (course_id, prefix_id, set_by_person_id, role, mode, set_at)\n" +
      `select s.course_id, c.prefix_id, ${INSTRUCTOR}, 'LEAD_FACULTY', 'REQUIRED', '1970-01-01T00:00Z'\n` +
      `from section s join course c on c.id = s.course_id where s.id = ${SECTION};`,
  );

  const block = await landOnTheSurvey(page, placement, MATHEMATICS.code);
  await block.getByRole("link", { name: LINK }).click();

  const results = page.getByTestId("pulse-student-results");
  await expect(results.getByText(AWAITING)).toBeVisible();
  const text = (await results.textContent()) ?? "";
  expect(text, "A held week shows no number, date, countdown or name.").not.toMatch(/\d/);
  expect(text).not.toContain(INSTRUCTOR_NAME);
});

test("after the instructor publishes, the card shows the reply under the instructor's name", async ({
  page,
}) => {
  databaseStatement(
    "insert into instructor_response (section_id, term_id, week_id, author_person_id, role, ai_seeded, body, published_at)\n" +
      `select s.id, s.term_id, ${FIRST_WEEK}, ${INSTRUCTOR}, 'INSTRUCTOR', false, '${REPLY}', now()\n` +
      `from section s where s.id = ${SECTION};`,
  );

  await launchAs(page, LEARNER_SUBJECT, placement);
  const block = page.getByTestId(`survey-section-${MATHEMATICS.code}`);
  await block.getByRole("link", { name: LINK }).click();

  const results = page.getByTestId("pulse-student-results");
  await expect(results.getByText(REPLY)).toBeVisible();
  await expect(results.getByText(INSTRUCTOR_NAME, { exact: true })).toBeVisible();
  await expect(results.getByText(AWAITING)).toHaveCount(0);
});
