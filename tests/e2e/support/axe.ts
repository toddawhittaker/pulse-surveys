// The accessibility scan every drive runs on each page it reaches (SPEC §7.6,
// WCAG 2.2 AA). One call, so each drive's scan means the same thing: the whole
// page as it stands, every rule axe ships, and any violation fails the test,
// named by its rule and the elements it found.

import AxeBuilder from '@axe-core/playwright';
import { expect, type Page } from '@playwright/test';

/** Scan the page as it stands; any violation fails the test, naming `where`. */
export async function expectNoAxeViolations(page: Page, where: string): Promise<void> {
  const scan = await new AxeBuilder({ page }).analyze();
  expect(
    scan.violations.map(
      (violation) =>
        `${violation.id}: ${violation.help} (${violation.nodes
          .map((node) => node.target.join(' '))
          .join('; ')})`,
    ),
    `${where} has accessibility violations.`,
  ).toEqual([]);
}
