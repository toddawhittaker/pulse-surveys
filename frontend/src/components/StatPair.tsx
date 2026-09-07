import type { JSX } from 'react';

import type { InstructorReportStatsCopyKey } from './instructorReportStatCopy';
import { copy, formatStatistic } from './instructorReportStatCopy';
import './instructorReportStats.css';

/**
 * The week's workload figures, side by side — SPEC §7.6's `StatPair`.
 *
 * SPEC §5.1 asks the report for "workload mean/median for the section ... (true
 * numeric statistics — §3.2)", and `design/InstructorMondayReport.dc.html` lays
 * them out as a pair under one "Workload" heading, median first.
 * `design/StatPair.dc.html` is the contract for each figure: a quiet label, a
 * large mono value with its unit trailing at reading size, and a third line
 * beneath.
 *
 * **Both figures, one decimal, one rule** — `formatStatistic`, so a median of 8
 * and a mean of 9.46 are "8.0" and "9.5" rather than two spellings of a number
 * on one line.
 *
 * **A pair with nothing in it says so.** A week nobody answered has no mean and
 * no median; the values take the prototypes' absent treatment (an em dash) and
 * the third line — the prototype's comparison slot, which is E5's and empty on
 * this surface — says why in the brief's own words. Nothing renders a zero,
 * which on an hours figure would read as "this course took nobody any time".
 *
 * **A description list, because that is what this is:** two labelled figures,
 * each label bound to its value in the markup rather than only by position, so
 * an assistive technology reads "Median hours this week, 8.0 h" instead of four
 * unrelated fragments.
 */
export function StatPair({
  median,
  mean,
}: {
  /** The section's median hours this week, or `null` when the week has none. */
  readonly median: number | null;
  /** The section's mean hours this week, or `null` when the week has none. */
  readonly mean: number | null;
}): JSX.Element {
  // Both figures come from the same week's answers, so they are absent
  // together; the note explains the pair rather than each dash.
  const absent = !isMeasured(median) && !isMeasured(mean);

  return (
    <div className="pulse-stat-pair">
      <dl className="pulse-stat-pair-figures">
        <Figure labelKey="instructor_report_stats.workload_median" value={median} />
        <Figure labelKey="instructor_report_stats.workload_mean" value={mean} />
      </dl>
      {absent ? <p className="pulse-stat-note">{copy('instructor_report_stats.no_responses')}</p> : null}
    </div>
  );
}

/** One labelled figure, with its unit where the prototype puts it. */
function Figure({
  labelKey,
  value,
}: {
  readonly labelKey: InstructorReportStatsCopyKey;
  readonly value: number | null;
}): JSX.Element {
  return (
    <div>
      <dt className="pulse-stat-figure-label">{copy(labelKey)}</dt>
      <dd className="pulse-stat-figure-value">
        {formatStatistic(value)}
        {/* No unit on an absent figure: "— h" claims a measurement in hours
            that the week does not have. */}
        {isMeasured(value) ? (
          <span className="pulse-stat-figure-unit">{` ${copy('instructor_report_stats.workload_unit')}`}</span>
        ) : null}
      </dd>
    </div>
  );
}

/**
 * A figure the week actually has.
 *
 * `null` is the payload saying there is nothing to average; a non-finite number
 * is arithmetic over no responses arriving as one, and both take the absent
 * treatment rather than reaching the page as "NaN h".
 */
function isMeasured(value: number | null): value is number {
  return value !== null && Number.isFinite(value);
}
