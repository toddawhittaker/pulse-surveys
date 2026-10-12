// The admin's People & reporting and Lead Faculty mapping screens, end to end
// (SPEC §6.3).
//
// **What this file proves.** An admin signs in through the web door, opens the
// Lead Faculty mapping table from the console, exports its current file, adds
// one mapping to the exported file, chooses it for an import, reads the dry
// run's diff, applies it, and sees the new row in the table. Before the dry run
// has answered there is no apply control on the page. A lead, signed in the
// same way, is told the page is not part of their role.
//
// **The world.** The seed maps `BIOL 215` to nobody, and this file maps it to
// the mock world's Lead Faculty member for the length of the run, through the
// product's own import. The mapping is removed on the way out, and a stale one
// a killed run left behind is removed first, so a rerun on the same stack
// starts clean. The suite runs on one worker, so no other file holds the row.
//
// **Accessibility.** Every page the drive reaches is scanned by axe: the
// console landing, the mapping table, the import's diff, the People table and
// an open person panel.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { readFileSync } from 'node:fs';

import { test, expect } from '@playwright/test';

import { expectNoAxeViolations } from './support/axe';
import { sessionToken, signInAs } from './support/doors';
import { databaseStatement } from './support/stack';

const ADMIN_SUBJECT = 'mock-idp-user-admin';
const LEAD_SUBJECT = 'mock-idp-user-lead-faculty';
const LEAD_PERSON_NAME = 'Demo Mock-World Lead Faculty';
const BIOL = { code: 'R3WW', label: 'BIOL 215' };

// Testids and addresses, transcribed rather than imported
// (`docs/MISTAKES.md` entry 19). Links are found by their address, so a copy
// change does not break the drive.
const ADMIN_LANDING = 'pulse-landing-admin';
const MAPPINGS_HREF = '/app/admin/lead-mappings';
const PEOPLE_HREF = '/app/admin/people';
const MAPPINGS_TABLE = 'pulse-admin-mappings-table';
const PEOPLE_TABLE = 'pulse-admin-people-table';
const IMPORT_DIFF = 'pulse-admin-import-diff';
const IMPORT_APPLY = 'pulse-admin-import-apply';
const PERSON_PANEL = 'pulse-admin-person-panel';
const APPLY = 'Apply these changes';
const NOT_YOUR_ROLE = 'This page is not part of your role';

const THE_COURSE = `(select distinct course_id from section where lms_section_code = '${BIOL.code}')`;
const THE_LEAD = `(select id from person where identity_name = '${LEAD_PERSON_NAME}')`;

const CASE_TIMEOUT_MS = 120_000;

function removeTheMapping(): void {
  databaseStatement(
    `delete from lead_faculty_mapping where course_id = ${THE_COURSE} and person_id = ${THE_LEAD};`,
  );
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(() => {
  removeTheMapping();
  expect(
    databaseStatement(`select count(*) from lead_faculty_mapping where course_id = ${THE_COURSE};`),
    `${BIOL.label} already has a lead, so the drive cannot add one. The seed maps it to nobody.`,
  ).toBe('0');
});

test.afterAll(() => {
  removeTheMapping();
});

test('an admin imports a mapping file, reads the diff, applies it, and sees the table change', async ({
  page,
}) => {
  test.setTimeout(CASE_TIMEOUT_MS);

  await signInAs(page, ADMIN_SUBJECT);
  const landing = page.getByTestId(ADMIN_LANDING);
  await expect(landing).toBeVisible();
  await expectNoAxeViolations(page, 'The admin console landing');

  await landing.locator(`a[href="${MAPPINGS_HREF}"]`).click();
  const table = page.getByTestId(MAPPINGS_TABLE);
  await expect(table).toBeVisible();
  await expect(table.getByText(BIOL.label, { exact: true })).toHaveCount(0);
  await expectNoAxeViolations(page, 'The Lead Faculty mapping table');

  // The current file, exactly as the table exports it.
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Export CSV' }).click(),
  ]);
  const exported = readFileSync(await download.path(), 'utf8');
  const courseId = databaseStatement(`select ${THE_COURSE};`);
  const leadId = databaseStatement(`select ${THE_LEAD};`);
  expect(courseId, 'BIOL 215 was not found in the seeded catalogue.').not.toBe('');
  expect(leadId, `${LEAD_PERSON_NAME} was not found among the seeded people.`).not.toBe('');
  const withTheNewRow = `${exported.replace(/\n*$/, '\n')}${courseId},${BIOL.label},${leadId},${LEAD_PERSON_NAME}\n`;

  // Nothing can be applied before a dry run has answered.
  await expect(page.getByRole('button', { name: APPLY })).toHaveCount(0);
  await page.getByLabel('CSV file', { exact: true }).setInputFiles({
    name: 'lead-mappings.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(withTheNewRow),
  });

  const diff = page.getByTestId(IMPORT_DIFF);
  await expect(diff).toBeVisible();
  await expect(diff.getByRole('table', { name: 'Added' })).toBeVisible();
  await expect(diff.getByRole('table', { name: 'Added' }).getByRole('cell', { name: BIOL.label })).toBeVisible();
  await expectNoAxeViolations(page, 'The import’s dry-run diff');

  // The table has not changed yet: the diff is a preview.
  await expect(table.getByText(BIOL.label, { exact: true })).toHaveCount(0);

  await page.getByTestId(IMPORT_APPLY).click();
  await expect(table.getByRole('rowheader', { name: BIOL.label })).toBeVisible();
  await expect(page.getByRole('button', { name: APPLY })).toHaveCount(0);
  await expect(page.getByRole('status')).toContainText('The import was applied.');
});

test('the People table opens a person’s panel, and every page scans clean', async ({ page }) => {
  test.setTimeout(CASE_TIMEOUT_MS);

  await signInAs(page, ADMIN_SUBJECT);
  await page.getByTestId(ADMIN_LANDING).locator(`a[href="${PEOPLE_HREF}"]`).click();

  const table = page.getByTestId(PEOPLE_TABLE);
  await expect(table).toBeVisible();
  await expectNoAxeViolations(page, 'The People & reporting table');

  await table.getByRole('button', { name: /^Manage / }).first().click();
  const panel = page.getByTestId(PERSON_PANEL);
  await expect(panel).toBeVisible();
  // Every Pulse-owned role is offered, the Care and Admin roles included.
  const offered = await panel.getByLabel('Role', { exact: true }).locator('option').allTextContents();
  expect(offered).toContain('Care');
  expect(offered).toContain('Admin');
  expect(offered).not.toContain('Instructor');
  await expectNoAxeViolations(page, 'An open person panel');
});

test('a lead faculty member is told the admin pages are not part of their role', async ({ page }) => {
  test.setTimeout(CASE_TIMEOUT_MS);

  await signInAs(page, LEAD_SUBJECT);
  // The SPA lifts the token out of the address before it is stored; going to
  // another address before then would arrive with no session at all.
  await expect(page).toHaveURL(/\/app\//);
  expect(await sessionToken(page), 'The lead faculty member was not signed in.').not.toBeNull();
  for (const address of [PEOPLE_HREF, MAPPINGS_HREF]) {
    await page.goto(address);
    // The notice and the live region both carry the sentence; the region is the one.
    await expect(page.getByRole('status')).toHaveText(NOT_YOUR_ROLE);
    await expect(page.getByRole('table')).toHaveCount(0);
  }
  await expectNoAxeViolations(page, 'The not-your-role notice on an admin page');
});
