// The leadership roll-up's one drive (SPEC §5.5): a chair lands on the roll-up,
// switches the tree to by-lead mode, opens an attention card's section, and
// reads its drill-down, read-only. Every page the drive reaches gets the axe
// scan.
//
// **The world.** The mock world's chair is given a CHAIR seat over Biology for
// the run, so BIOL 215 R3WW is in her purview. The learner is enrolled in that
// section and the clock is moved past the first week's report opening with no
// response written, so the section's first published week has a response rate
// of nothing out of its enrolment, which is SPEC §5.6's "response rate under
// 40%" and puts an attention card on the page. Every instant comes from the
// seeded calendar (the section's own first survey window), never a pinned
// date, and the seat and the week's rows are removed afterwards so a rerun
// starts clean.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect, type Locator, type Page } from '@playwright/test';

import { expectNoAxeViolations } from './support/axe';
import { clearTheClock, setTheClockTo } from './support/clock';
import { signInAs } from './support/doors';
import { databaseStatement, stopTheScheduler } from './support/stack';
import {
  clearTheWeek,
  sectionStartClock,
  standTheLearnerIn,
  type SectionUnderTest,
} from './support/survey';

const BIOL: SectionUnderTest = { label: 'BIOL-215-R3WW', code: 'R3WW' };

const CHAIR_WEB_SUBJECT = 'mock-idp-user-chair';
const CHAIR_PERSON = `(select id from person where identity_name = 'Demo Mock-World Chair')`;
const BIOLOGY = `(select id from department where name = 'Biology')`;
const SECTION = `(select id from section where lms_section_code = '${BIOL.code}')`;
const FIRST_WINDOW_CLOSES = `(select closes_at from survey_window where section_id = ${SECTION} order by opens_at limit 1)`;

const LEADERSHIP_VIEW = 'pulse-landing-leadership';
const DRILL_DOWN = 'pulse-leadership-drill-down';
const CONTEXT_BAR = 'pulse-drill-down-context';
const BY_LEAD = 'Lead faculty';

const WORLD_TIMEOUT_MS = 300_000;
const CASE_TIMEOUT_MS = 180_000;
const INSTITUTION_ZONE = 'America/New_York';

let sectionId = '';
let reportOpensAt = '';
let chairAssignment = '';

test.describe.configure({ mode: 'serial' });

/** A wall-clock minute plus whole hours; the calendar days in play never cross a clock change. */
function plusHours(minute: string, hours: number): string {
  const at = new Date(`${minute}:00Z`);
  at.setUTCHours(at.getUTCHours() + hours);
  return at.toISOString().slice(0, 16);
}

test.beforeAll(async ({ browser }) => {
  test.setTimeout(WORLD_TIMEOUT_MS);
  stopTheScheduler();
  await standTheLearnerIn(browser, [BIOL], sectionStartClock(BIOL.code));
  clearTheWeek([BIOL.code]);

  sectionId = databaseStatement(`select ${SECTION};`);
  expect(sectionId, 'BIOL 215 R3WW is not seeded.').toMatch(/^[0-9a-f-]{36}$/);
  // The first week's report opens on the Monday at 06:00 local after its window closes.
  reportOpensAt = databaseStatement(
    'select to_char(' +
      `date_trunc('week', ${FIRST_WINDOW_CLOSES} at time zone '${INSTITUTION_ZONE}') ` +
      `+ interval '7 days 6 hours', 'YYYY-MM-DD"T"HH24:MI');`,
  );
  expect(reportOpensAt, 'The report-open instant could not be derived.').toMatch(
    /^\d{4}-\d\d-\d\dT06:00$/,
  );

  chairAssignment = databaseStatement(
    `insert into role_assignment (person_id, role, department_id) ` +
      `select ${CHAIR_PERSON}, 'CHAIR', ${BIOLOGY} returning id;`,
  );
  expect(chairAssignment, 'The chair seat over Biology was not written.').toMatch(
    /^[0-9a-f-]{36}$/,
  );
});

test.afterAll(async ({ browser }) => {
  const context = await browser.newContext();
  try {
    try {
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

/** The section's attention-card link, wherever in the chosen node's list it is. */
function attentionLinkTo(page: Page): Locator {
  return page.locator(`a.pulse-attention-link[href^="/app/leadership/sections/${sectionId}?"]`);
}

/** Choose each root of the tree in turn until one carries the section's card. */
async function chooseTheRootHoldingTheCard(page: Page): Promise<void> {
  const roots = page.locator(
    'nav.pulse-hierarchy > ul.pulse-hierarchy-list > li > div > button.pulse-hierarchy-select',
  );
  const count = await roots.count();
  expect(count, 'The by-lead tree has no root.').toBeGreaterThan(0);
  for (let index = 0; index < count; index += 1) {
    await roots.nth(index).click();
    await expect(page.locator('.pulse-rollup-content-pane > [role="status"]')).toHaveText('');
    if ((await attentionLinkTo(page).count()) > 0) return;
  }
  throw new Error(`No root of the chair's by-lead tree carries the card for ${BIOL.label}.`);
}

test('a chair reads the roll-up by lead, opens an attention card, and reads the drill-down', async ({
  page,
}) => {
  test.setTimeout(CASE_TIMEOUT_MS);
  await setTheClockTo(page, plusHours(reportOpensAt, 1));
  await signInAs(page, CHAIR_WEB_SUBJECT);

  // The roll-up: the landing's own heading, the tree, and a chosen node.
  const rollup = page.getByTestId(LEADERSHIP_VIEW);
  await expect(rollup).toBeVisible();
  await expect(rollup.getByRole('navigation', { name: 'Your purview' })).toBeVisible();
  await expect(rollup.locator('article.pulse-rollup-article h2')).toBeVisible();
  await expectNoAxeViolations(page, 'The roll-up');

  // Keyboard: open the first root, choose its first child, then press the
  // root's breadcrumb with Enter; focus lands on the root's heading.
  const firstRoot = rollup.locator('nav.pulse-hierarchy > ul > li').first();
  const rootName = (await firstRoot.locator('.pulse-hierarchy-select .pulse-hierarchy-name').first().textContent()) ?? '';
  await firstRoot.locator('button.pulse-hierarchy-toggle').first().press('Enter');
  await firstRoot.locator('ul button.pulse-hierarchy-select').first().press('Enter');
  const crumb = rollup
    .getByRole('navigation', { name: 'Where you are in the tree' })
    .getByRole('button', { name: rootName, exact: true });
  await crumb.focus();
  await page.keyboard.press('Enter');
  await expect(rollup.locator('article.pulse-rollup-article h2')).toBeFocused();
  await expect(rollup.locator('article.pulse-rollup-article h2')).toHaveText(rootName);

  // By-lead mode is offered to a chair, and switches the tree.
  const byLead = rollup.getByRole('button', { name: BY_LEAD });
  await expect(byLead).toHaveAttribute('aria-pressed', 'false');
  await byLead.click();
  await expect(byLead).toHaveAttribute('aria-pressed', 'true');
  await chooseTheRootHoldingTheCard(page);
  await expectNoAxeViolations(page, 'The roll-up in by-lead mode');

  // The attention card opens the section's drill-down at its week.
  const card = attentionLinkTo(page).first();
  const href = await card.getAttribute('href');
  expect(href).toMatch(new RegExp(`^/app/leadership/sections/${sectionId}\\?week=\\d+$`));
  await card.click();

  const drillDown = page.getByTestId(DRILL_DOWN);
  await expect(drillDown).toBeVisible();
  await expect(drillDown.getByTestId(CONTEXT_BAR)).toHaveText(
    'Viewing as Department Chair · read-only',
  );
  await expect(drillDown.getByRole('heading', { level: 1 })).toBeVisible();
  // Read-only: no moderation control and no composer.
  await expect(drillDown.getByRole('button', { name: /exclude|keep for students|undo/i })).toHaveCount(
    0,
  );
  await expect(drillDown.getByRole('textbox')).toHaveCount(0);
  await expectNoAxeViolations(page, 'The drill-down');
});
