// The student's heading and results page — SPEC §5.3, §5.4, §7.6.
//
// Three things a student reads, on the composed stack:
//
//   - the survey names who teaches the section, in the heading area;
//   - a course whose policy requires a response shows a closed door for a week
//     that has none yet: the course's name and nothing about the week;
//   - once the instructor's response is in, the page for that week shows it by
//     name, under the course's name, with both comment groups and the page's one
//     confidentiality line, and no comparison of any kind.
//
// The two seeded facts the stack does not hold are set in the database as its
// superuser: the instructor's name (the mock platform sends none, ADR 0050) and
// the course's policy (the doors that set one are another ticket's). The
// response is inserted as the section's own instructor, so the table's guard
// trigger judges it exactly as it judges the real writer's. The policy row goes
// in with its guard on: the instructor is first given the course's lead grant and
// mapping, which is what the guard checks, and the grant is removed again
// straight after, so no other spec's launch lands somewhere new.
//
// **No date is pinned.** The reading day is the section's start day (the seeded
// calendar, via `sectionStartClock`) plus fourteen days, the Monday the second
// course week's report opens (SPEC §3.1), so weeks 1 and 2 are both published.
// The policy is recorded at the epoch, which is before any week's report opens
// whatever the calendar says.
//
// **The response table is append-only, so the run is built to be repeated on one
// stack.** Week 2 is never answered: it is the held week every run reads first.
// Week 1 is the answered one, and every write is guarded by a check for its own
// row, so a second run inserts nothing the first left behind and the stack is in
// the same state after each. The block is serial. The scheduler is stopped for
// the reason `stopTheScheduler` gives.
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
const CONFIDENTIALITY_LINE = "Comments are shown without the names of the students who wrote them.";

test.describe.configure({ mode: "serial" });

let placement = "";

/** The section start day plus fourteen days: the Monday course week 2's report opens. */
function readingClock(): string {
  const start = new Date(`${sectionStartClock(MATHEMATICS.code).slice(0, 10)}T12:00:00Z`);
  start.setUTCDate(start.getUTCDate() + 14);
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

test("a required-mode week with no reply shows the course and the closed door, and nothing about the week", async ({
  page,
}) => {
  // The instructor is made the course's lead, the way the guard checks it: a
  // LEAD_FACULTY assignment and the course's lead mapping. Each row is written
  // only if it is not already there, and the grant is taken away again after.
  databaseStatement(
    "insert into role_assignment (person_id, role, course_id)\n" +
      `select ${INSTRUCTOR}, 'LEAD_FACULTY', s.course_id from section s where s.id = ${SECTION}\n` +
      `and not exists (select 1 from role_assignment ra where ra.person_id = ${INSTRUCTOR} and ra.role = 'LEAD_FACULTY' and ra.course_id = s.course_id);\n` +
      "insert into lead_faculty_mapping (person_id, course_id)\n" +
      `select ${INSTRUCTOR}, s.course_id from section s where s.id = ${SECTION}\n` +
      `and not exists (select 1 from lead_faculty_mapping m where m.person_id = ${INSTRUCTOR} and m.course_id = s.course_id);\n` +
      "insert into response_policy (course_id, prefix_id, set_by_person_id, role, mode, set_at)\n" +
      `select s.course_id, c.prefix_id, ${INSTRUCTOR}, 'LEAD_FACULTY', 'REQUIRED', '1970-01-01T00:00Z'\n` +
      `from section s join course c on c.id = s.course_id where s.id = ${SECTION}\n` +
      "and not exists (select 1 from response_policy p where p.course_id = s.course_id);\n" +
      // The grant is only needed while the guard looks at it. Left in place it
      // would send this person to the leadership landing on every later launch
      // as the instructor, and other specs wait for the instructor's.
      `delete from lead_faculty_mapping where person_id = ${INSTRUCTOR};\n` +
      `delete from role_assignment where person_id = ${INSTRUCTOR} and role = 'LEAD_FACULTY';`,
  );

  const block = await landOnTheSurvey(page, placement, MATHEMATICS.code);
  await block.getByRole("link", { name: LINK }).click();

  // The latest published week is the second, and nobody has answered it.
  const results = page.getByTestId("pulse-student-results");
  await expect(results.getByText(AWAITING)).toBeVisible();
  await expect(results.getByTestId("pulse-results-course")).toContainText("MATH");
  const text = (await results.textContent()) ?? "";
  expect(text, "A held week shows no week number.").not.toMatch(/Week\s*\d/);
  expect(text).not.toContain(INSTRUCTOR_NAME);
  expect(text, "A held week shows no confidentiality promise: it shows no comments.").not.toContain(
    CONFIDENTIALITY_LINE,
  );
  for (const testId of ["pulse-trend-duo"]) {
    await expect(results.getByTestId(testId)).toHaveCount(0);
  }
  await expect(results.locator(".pulse-stat-histogram")).toHaveCount(0);
  await expect(results.locator(".pulse-comment-group")).toHaveCount(0);
  await expect(results.locator(".pulse-small-n-notice")).toHaveCount(0);
});

test("after the instructor publishes, the week's page shows the reply, both groups and the one confidentiality line", async ({
  page,
}) => {
  databaseStatement(
    "insert into instructor_response (section_id, term_id, week_id, author_person_id, role, ai_seeded, body, published_at)\n" +
      `select s.id, s.term_id, ${FIRST_WEEK}, ${INSTRUCTOR}, 'INSTRUCTOR', false, '${REPLY}', now()\n` +
      `from section s where s.id = ${SECTION}\n` +
      `and not exists (select 1 from instructor_response r where r.section_id = s.id and r.week_id = ${FIRST_WEEK});`,
  );

  await launchAs(page, LEARNER_SUBJECT, placement);
  const block = page.getByTestId(`survey-section-${MATHEMATICS.code}`);
  await block.getByRole("link", { name: LINK }).click();

  // The latest week is still held; the answered one is a step back.
  const results = page.getByTestId("pulse-student-results");
  await expect(results.getByText(AWAITING)).toBeVisible();
  await results.getByRole("button", { name: "Previous week" }).click();

  await expect(results.getByText(REPLY)).toBeVisible();
  await expect(results.getByText(INSTRUCTOR_NAME, { exact: true })).toBeVisible();
  await expect(results.getByText(AWAITING)).toHaveCount(0);
  await expect(results.getByTestId("pulse-results-course")).toContainText("MATH");

  // The figures and both comment groups, and the line, once.
  await expect(results.getByTestId("pulse-trend-duo")).toBeVisible();
  await expect(results.locator(".pulse-stat-histogram")).toHaveCount(2);
  await expect(results.getByRole("heading", { name: "About the instructor" })).toBeVisible();
  await expect(results.getByRole("heading", { name: "About the course" })).toBeVisible();
  const text = (await results.textContent()) ?? "";
  expect(text.split(CONFIDENTIALITY_LINE).length - 1).toBe(1);

  // Nothing compares this section with anything, in text or in a label.
  const labels = await results.locator("[aria-label]").evaluateAll((nodes) =>
    nodes.map((node) => node.getAttribute("aria-label") ?? "").join(" "),
  );
  expect(`${text} ${labels}`).not.toMatch(/compar|universit|benchmark|average|other sections/i);
  await expect(results.locator("path.pulse-trend-line")).toHaveCount(2);
});
