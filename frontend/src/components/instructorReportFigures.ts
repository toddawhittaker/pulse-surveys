import { copy, fillCopy } from '../copy/instructorReportStatCopy';

/**
 * How the Monday report writes a number — ticket E4-09's rules, ticket E4-12's file.
 *
 * These two functions shipped inside `instructorReportStatCopy.ts` until E4-12
 * moved that file into `frontend/src/copy/`. **A copy module's code may not name
 * a key.** `tests/fixtures/copy_inventory.py` parses every file in the copy
 * directory and refuses any quotation mark outside the one object literal, so a
 * sentence written among a copy file's helpers cannot ship unread — and a helper
 * that looks its own entry up by key is refused by the same rule, because the
 * parser reads a quotation mark and not a meaning.
 *
 * Rounding a percent and fixing a decimal place are presentation rules rather
 * than words, so they sit beside the components that render them and reach the
 * words the way every other component does: through `copy()` and `fillCopy()`.
 * The rules themselves are unchanged, and the keys they read are the same two.
 */

/**
 * A workload statistic as the report writes it: one decimal place, always.
 *
 * One rule in one place, for both figures and for the distribution's mean, so
 * that "8" and "8.04" and "8.0" are one number on the page. `toFixed` rounds
 * rather than truncating — 9.46 is "9.5" and not "9.4" — and a value that is
 * not a finite number gets the absent treatment rather than reaching the DOM as
 * `NaN`, which is the shape SPEC §5.1's zero-response week would otherwise
 * produce through a division by no responses.
 */
export function formatStatistic(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return copy('instructor_report_stats.absent_figure');
  }
  return value.toFixed(1);
}

/**
 * A rate as the report writes it: a whole percent, from the payload's 0–1
 * fraction.
 *
 * The report's rates arrive as fractions (`{"response_rate": 0.62}`), and a
 * fraction rendered straight is how "62.000000001%" reaches a page —
 * `0.83 * 100` is `83.00000000000001` in IEEE 754 and `0.29 * 100` is
 * `28.999999999999996`. Rounding to a whole percent is the one rule, applied
 * here and nowhere else; the counts beside it carry the precision anyone
 * actually needs.
 */
export function formatRate(rate: number | null): string {
  if (rate === null || !Number.isFinite(rate)) {
    return copy('instructor_report_stats.absent_figure');
  }
  return fillCopy('instructor_report_stats.percent', {
    percent: String(Math.round(rate * 100)),
  });
}
