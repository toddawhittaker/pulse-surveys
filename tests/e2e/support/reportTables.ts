// The instructor report's accessible tables, and how many of them there should
// be — ticket E5-10.
//
// **Why this module exists.** Two specs asserted `getByRole('table')` resolves
// to two inside the report: one table per panel, which was the whole structure
// while each panel drew one line. E5-07 gives every *drawn* comparison series a
// table of its own — a benchmark can report a week the section never published,
// so folding it into the section's row set would drop it from the text while
// leaving it on the picture — and E5-10 wires the payload's benchmark members
// through, so a report can now publish up to six. Both specs asked the same
// question and a second hand-written answer to it is `docs/MISTAKES.md` entry 13
// written out in full, so the question is answered once, here.
//
// **The structure is asserted, never the number.** A literal four would be right
// on one section of one seeded world and wrong on the next: how many comparison
// series are drawn is the server's decision, taken per week against SPEC §11's
// minimums over populations these specs do not control. So the two panel tables
// are required by name, and the overlay tables are required to be exactly one
// per drawn overlay line — the property E5-07 built. The line count is read off
// the page and the table count is read off the page, but they come from
// different renderings of one decision, so neither is the other's source.
//
// **Named with `exact`, because a role's accessible name matches as a
// substring.** "Weekly ratings: Instructor" also names that panel's overlay
// table, "Weekly ratings: Instructor, University" — measured: the locator
// resolved to two. It is the `getByText` trap `instructor-report.spec.ts`
// already records for the validity label, one locator along.

import { expect, type Locator } from '@playwright/test';

/** E5-07's two overlay lines, which are what say how many overlay tables are owed. */
export const TREND_LINE_COMPARISON = 'trend-line-comparison';
export const TREND_LINE_UNIVERSITY = 'trend-line-university';

/** How `PulseTrendChart` captions one panel's own table (`instructorReportTrendCopy.ts`). */
export function panelTable(report: Locator, panel: 'Instructor' | 'Course'): Locator {
  return report.getByRole('table', { name: `Weekly ratings: ${panel}`, exact: true });
}

/**
 * Every accessible table on one report, named: the two panels' own, and one for
 * each comparison line that is actually drawn.
 */
export async function expectTheTablesMatchTheLines(report: Locator): Promise<void> {
  for (const panel of ['Instructor', 'Course'] as const) {
    await expect(
      panelTable(report, panel),
      `The ${panel} panel published no table of its own weeks. Every chart on this surface owes ` +
        'an accessible alternative (`docs/DESIGN_BRIEF.md`, SPEC §14.2 item 4).',
    ).toHaveCount(1);
  }

  const comparisonLines = await report.getByTestId(TREND_LINE_COMPARISON).count();
  const universityLines = await report.getByTestId(TREND_LINE_UNIVERSITY).count();

  await expect(
    report.getByRole('table', { name: /, Comparable \d+-week courses$/ }),
    'The comparison series’ tables and its lines disagree. A drawn series publishes its weeks as ' +
      'text and a withheld one publishes nothing at all — a table of "no figure" rows under a ' +
      'suppression would be publishing the shape of the set §4.1 item 7 withholds.',
  ).toHaveCount(comparisonLines);
  await expect(
    report.getByRole('table', { name: /, University$/ }),
    'The university series’ tables and its lines disagree.',
  ).toHaveCount(universityLines);

  await expect(
    report.getByRole('table'),
    'The report published a table that is neither a panel’s own nor a drawn comparison series’.',
  ).toHaveCount(2 + comparisonLines + universityLines);
}
