// The accessibility scan every drive runs on each page it reaches (SPEC §7.6,
// WCAG 2.2 AA). One call, so each drive's scan means the same thing: the whole
// page as it stands, every rule axe ships, and any violation fails the test,
// named by its rule and the elements it found.

import AxeBuilder from '@axe-core/playwright';
import { expect, type Page } from '@playwright/test';

/** Scan the page as it stands; any violation fails the test, naming `where`. */
export async function expectNoAxeViolations(page: Page, where: string): Promise<void> {
  // A card that has just opened fades in over 200ms, and axe measures the
  // colour it sees, so a scan mid-fade reads a half-transparent text as low
  // contrast. Finite animations are let finish first; colours are not touched.
  await page.evaluate(async () => {
    await Promise.all(
      document
        .getAnimations()
        .filter((animation) => Number.isFinite(animation.effect?.getComputedTiming().endTime ?? Infinity))
        .map((animation) => animation.finished.catch(() => undefined)),
    );
  });
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
