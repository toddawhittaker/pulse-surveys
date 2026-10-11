// The instructor's composer — SPEC §5.3, §7.6.
//
// One instructor, one week, on the composed stack: use the AI draft, check it,
// change a character and see the check go, run it again, publish, read the card
// as students see it under the instructor's name, edit, and read the new text.
//
// **Nothing posts before the publish button.** After the draft and the checks,
// and before Publish, the response table holds no row for the section: that is
// asserted in the database, not in the page.
//
// The section is `BIOL-215-R3WW`, not the one `student-results.spec.ts` uses,
// because the response table is append-only and that spec inserts its own reply
// into `MATH-140-E1FF`'s first week; two specs publishing into one week would
// collide. For the same reason this block is serial and cannot reset the stack
// between runs. The instructor's name is set in the database as the superuser,
// since the mock platform sends none (ADR 0050).
//
// **No date is pinned.** The reading day is the section's start day (the seeded
// calendar, via `sectionStartClock`) plus seven days: the Monday course week 1's
// report opens (SPEC §3.1). The week has no answers and so no stored summary, so
// the check names no theme; the draft and the check still run through the mock
// model provider, and what this spec proves is the page's behaviour around them.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect } from "@playwright/test";

import { clearTheClock, setTheClockTo } from "./support/clock";
import { INSTRUCTOR_SUBJECT, type SectionUnderTest, sectionStartClock, standTheLearnerIn } from "./support/survey";
import { databaseStatement, stopTheScheduler } from "./support/stack";
import { launchAs } from "./support/doors";

const BIOLOGY: SectionUnderTest = { label: "BIOL-215-R3WW", code: "R3WW" };

const INSTRUCTOR_NAME = "Professor Grace Larch";
const REPLY = "You said the readings pile up. We heard that, and we are trimming next week's list.";
const REVISED = "You said the readings pile up. We are trimming next week's list and moving one to optional.";

const CHECK_PANEL = "Themes your draft has not addressed";

test.describe.configure({ mode: "serial" });

let placement = "";

/** The section start day plus seven days: the Monday course week 1's report opens. */
function readingClock(): string {
  const start = new Date(`${sectionStartClock(BIOLOGY.code).slice(0, 10)}T12:00:00Z`);
  start.setUTCDate(start.getUTCDate() + 7);
  return `${start.toISOString().slice(0, 10)}T12:00`;
}

const SECTION = `(select id from section where lms_section_code = '${BIOLOGY.code}')`;
const INSTRUCTOR =
  "(select ra.person_id from role_assignment ra " +
  `where ra.role = 'INSTRUCTOR' and ra.section_id = ${SECTION} limit 1)`;

test.beforeAll(async ({ browser }) => {
  test.setTimeout(180_000);
  stopTheScheduler();
  placement = await standTheLearnerIn(browser, [BIOLOGY], sectionStartClock(BIOLOGY.code));

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

test("draft, check, edit clears the check, publish, read as students do, then edit", async ({
  page,
}) => {
  await launchAs(page, INSTRUCTOR_SUBJECT, placement);
  await page
    .getByTestId("pulse-instructor-sections")
    .getByRole("link", { name: /BIOL 215 R3WW/ })
    .click();
  await expect(page.getByTestId("pulse-instructor-report")).toBeVisible();

  const composer = page.getByRole("region", { name: "Your response to this week" });
  const editor = composer.getByRole("textbox", { name: "Your response" });
  const check = composer.getByRole("button", { name: "Check draft with AI" });
  const panel = composer.getByRole("region", { name: CHECK_PANEL });

  // The draft fills the editor and the page posts nothing.
  await composer.getByRole("button", { name: "Use draft" }).click();
  await expect(editor).not.toHaveValue("");

  // A check shows for the text it ran on, and goes at the next keystroke.
  await check.click();
  await expect(panel).toBeVisible();
  await editor.press("End");
  await editor.pressSequentially("!");
  await expect(panel).toHaveCount(0);
  await check.click();
  await expect(panel).toBeVisible();

  const rows = databaseStatement(
    `select count(*) from instructor_response where section_id = ${SECTION};`,
  );
  expect(
    rows.trim(),
    "A draft and two checks were run and nothing was published, so the section holds no response.",
  ).toBe("0");

  // Publish: the card, as students see it, under the instructor's name.
  await editor.fill(REPLY);
  await composer.getByRole("button", { name: "Publish" }).click();
  const card = composer.locator("article.pulse-response-card");
  await expect(card.getByText(REPLY)).toBeVisible();
  await expect(card.getByText(INSTRUCTOR_NAME, { exact: true })).toBeVisible();
  await expect(composer.getByText("As students see it")).toBeVisible();
  await expect(editor).toHaveCount(0);

  // Edit opens the composer on the published text; publishing it shows the new text.
  await composer.getByRole("button", { name: "Edit response" }).click();
  await expect(editor).toHaveValue(REPLY);
  await editor.fill(REVISED);
  await composer.getByRole("button", { name: "Publish changes" }).click();
  await expect(card.getByText(REVISED)).toBeVisible();
  await expect(card.getByText(REPLY)).toHaveCount(0);
  await expect(card.getByText(INSTRUCTOR_NAME, { exact: true })).toBeVisible();
});
