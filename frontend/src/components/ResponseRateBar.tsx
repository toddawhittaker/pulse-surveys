import type { JSX } from 'react';

import type { InstructorReportStatsCopyKey } from './instructorReportStatCopy';
import { copy, fillCopy, formatRate } from './instructorReportStatCopy';
import './instructorReportStats.css';

/**
 * One rate, as the report payload carries it: the fraction, and the two counts
 * it was computed from.
 *
 * All three travel because they answer different questions. The fraction is what
 * the bar is drawn from and what the percent is written from; the counts are
 * what the sentence says, and they are integers the page was given rather than a
 * number multiplied back out of a rounded rate.
 */
export interface RateFigure {
  /** The rate as a 0–1 fraction — `0.62`, not `62`. */
  readonly rate: number;
  /** How many: responses for a response rate, valid responses for a validity rate. */
  readonly numerator: number;
  /** Out of how many: enrolled students, or the week's responses. */
  readonly denominator: number;
}

/**
 * SPEC §5.1's participation figures — SPEC §7.6's `ResponseRateBar`.
 *
 * `design/ResponseRateBar.dc.html` is the contract for each row: the figure's
 * name on the left, a mono readout of the counts and the percent on the right,
 * and a thin filled track beneath. `design/InstructorMondayReport.dc.html` puts
 * two of them under "Participation" — the response rate, and the validity rate
 * beneath it.
 *
 * **The validity rate is an optional prop, and that is the point.** SPEC §3.3
 * ends "shown on instructor and leadership surfaces only, never to students".
 * A component that knew about validity would carry the word into every surface
 * that reuses it, so this one is told about it or not: pass no validity figure
 * — as E8's student results will — and nothing about validity is rendered, named
 * or spoken. The audience decision stays with the caller and the payload, which
 * is where §3.3 puts it.
 *
 * **"13 of 21" is never computed from 0.62.** The rate is a rounded fraction;
 * multiplying it back out gives 13.02 and no honest integer. The counts are
 * rendered from the counts, and the percent from the rate, each from the member
 * that carries it.
 *
 * **A rate with no responses behind it withholds its percent.** A week nobody
 * answered is not a nought-percent week in the sense a reader takes from "0%",
 * and a week whose responses were all classified nonsense is said exactly by "0
 * of 13". Where there is nothing to be a rate of at all — the validity rate of a
 * week with no responses — both the counts and the percent go, because "0 / 0"
 * is a fact about nothing. In every case the em dash stands where the figure
 * would be, and the track is drawn empty rather than filled to zero.
 */
export function ResponseRateBar({
  response,
  validity,
}: {
  /** Responses out of enrolled students, per SPEC §5.1. */
  readonly response: RateFigure;
  /** Valid responses out of responses (SPEC §3.3) — omitted for any surface a student sees. */
  readonly validity?: RateFigure;
}): JSX.Element {
  return (
    <div className="pulse-stat-rates">
      <Rate labelKey="instructor_report_stats.response_rate" figure={response} />
      {validity === undefined ? null : (
        <Rate labelKey="instructor_report_stats.validity_rate" figure={validity} />
      )}
    </div>
  );
}

/** One labelled rate: its readout, its accessible sentence, and its track. */
function Rate({
  labelKey,
  figure,
}: {
  readonly labelKey: InstructorReportStatsCopyKey;
  readonly figure: RateFigure;
}): JSX.Element {
  const label = copy(labelKey);
  const numerator = String(figure.numerator);
  const denominator = String(figure.denominator);
  const absentFigure = copy('instructor_report_stats.absent_figure');

  // Three cases, in the order they stop being facts: nothing to be a rate of,
  // no responses behind the rate, and a rate. A rate that arrived as a
  // non-finite number is the second of those — a division by no responses,
  // wherever it happened — rather than a "NaN%" on the page.
  const nothingToRate = figure.denominator === 0;
  const measured = figure.numerator > 0 && Number.isFinite(figure.rate);
  const percent = nothingToRate || !measured ? null : formatRate(figure.rate);

  let readout = absentFigure;
  let reading = fillCopy('instructor_report_stats.rate_reading_absent', { label });
  if (!nothingToRate) {
    readout = fillCopy('instructor_report_stats.rate_readout', {
      numerator,
      denominator,
      percent: percent ?? absentFigure,
    });
    reading =
      percent === null
        ? fillCopy('instructor_report_stats.rate_reading_counts_only', {
            label,
            numerator,
            denominator,
          })
        : fillCopy('instructor_report_stats.rate_reading', {
            label,
            numerator,
            denominator,
            percent,
          });
  }

  return (
    <div className="pulse-stat-rate" role="img" aria-label={reading}>
      <div className="pulse-stat-rate-head">
        <span className="pulse-stat-rate-label">{label}</span>
        <span className="pulse-stat-rate-readout">{readout}</span>
      </div>
      <div className="pulse-stat-rate-track" aria-hidden="true">
        {percent === null ? null : <div className="pulse-stat-rate-fill" style={{ width: percent }} />}
      </div>
    </div>
  );
}
