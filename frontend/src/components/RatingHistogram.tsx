import type { JSX } from 'react';

import { copy, fillCopy } from '../copy/instructorReportStatCopy';
import { formatStatistic } from './instructorReportFigures';
import './instructorReportStats.css';

/** The two comment streams SPEC §5.1 reports each week under. */
export type RatingStream = 'instructor' | 'course';

/**
 * One week's ratings for one stream, as the report payload carries them:
 * a count per rating value, 1 through 5.
 *
 * Five declared members rather than `Record<string, number>`, so a distribution
 * missing a bucket does not compile and no bucket has to be defended against
 * being `undefined` at render time. The keys are the payload's own — the sketch
 * in `docs/tickets/e4/README.md` writes `{"1": 0, "2": 1, "3": 4, "4": 5,
 * "5": 3}` — so the page hands this member straight through.
 */
export interface RatingDistribution {
  readonly '1': number;
  readonly '2': number;
  readonly '3': number;
  readonly '4': number;
  readonly '5': number;
}

/** The rating values, in the order the axis draws them. */
const RATING_VALUES = ['1', '2', '3', '4', '5'] as const;

/** The prototype's bar geometry, in pixels. */
const TALLEST_BAR = 72;
const SHORTEST_DRAWN_BAR = 3;
const EMPTY_BAR = 2;

const STREAM_TITLE = {
  instructor: 'instructor_report_stats.instructor_stream',
  course: 'instructor_report_stats.course_stream',
} as const;

/**
 * This week's rating distribution for one stream — SPEC §7.6's `RatingHistogram`.
 *
 * SPEC §5.1 puts two of these on the Monday report, one per stream, showing "this
 * week rating distributions for both streams". `design/RatingHistogram.dc.html`
 * is the contract for what they look like: a title, a quiet mono mean above the
 * bars, five bars sharing the tallest count's scale, and the rating values along
 * a hairline beneath them.
 *
 * **Every bucket is drawn, including the empty ones.** A distribution that
 * dropped its zeroes would redraw its own axis every week and quietly say that
 * nobody rated the course a 1 by not saying anything at all. A zero-count bucket
 * keeps the prototype's 2px stub, so "no responses here" is a bar with nothing in
 * it.
 *
 * **The bars are decoration and the sentence is the chart.** The brief requires
 * an accessible alternative for every chart, so the drawn part is `aria-hidden`
 * and the whole distribution — the total, the mean and every count in rating
 * order — is spoken by the one label on the figure.
 *
 * **A week with no responses has no mean**, and this says so rather than
 * dividing by it: the summary line becomes the brief's empty-state sentence and
 * the label says the same, which is the only honest thing to say about a week
 * nobody answered. Nothing here can render `NaN` or a zero pretending to be a
 * rating.
 *
 * **No comparison figure.** The prototype's mean line carries a "comparable"
 * benchmark beside the section's own; comparison figures are E5's, gated by §4.1
 * item 7 through E4-07's guarded payload member, and this ticket ships none.
 */
export function RatingHistogram({
  stream,
  distribution,
}: {
  readonly stream: RatingStream;
  readonly distribution: RatingDistribution;
}): JSX.Element {
  const buckets = RATING_VALUES.map((value) => ({ value, count: distribution[value] }));
  const total = buckets.reduce((running, bucket) => running + bucket.count, 0);
  const mean =
    total === 0
      ? null
      : buckets.reduce((running, bucket, index) => running + bucket.count * (index + 1), 0) / total;
  const tallest = Math.max(...buckets.map((bucket) => bucket.count), 1);

  const title = copy(STREAM_TITLE[stream]);
  const reading =
    mean === null
      ? fillCopy('instructor_report_stats.distribution_reading_absent', { stream: title })
      : fillCopy('instructor_report_stats.distribution_reading', {
          stream: title,
          total: String(total),
          mean: formatStatistic(mean),
          counts: buckets.map((bucket) => String(bucket.count)).join(', '),
        });

  return (
    <div className="pulse-stat-histogram" role="img" aria-label={reading}>
      <p className="pulse-stat-histogram-title">{title}</p>
      <p className="pulse-stat-histogram-summary">
        {mean === null
          ? copy('instructor_report_stats.no_responses')
          : fillCopy('instructor_report_stats.distribution_mean', { mean: formatStatistic(mean) })}
      </p>
      <ul className="pulse-stat-histogram-buckets" aria-hidden="true">
        {buckets.map((bucket) => (
          <li className="pulse-stat-histogram-bucket" key={bucket.value}>
            <span className="pulse-stat-histogram-count">{String(bucket.count)}</span>
            <span
              className="pulse-stat-histogram-bar"
              style={{ height: barHeight(bucket.count, tallest) }}
            />
            <span className="pulse-stat-histogram-tick">{bucket.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * One bar's height, as the prototype computes it: the count against the week's
 * tallest bucket, floored so that a drawn bar is visible and an empty one is
 * still there.
 */
function barHeight(count: number, tallest: number): string {
  const drawn = Math.round((count / tallest) * TALLEST_BAR);
  return `${String(Math.max(drawn, count > 0 ? SHORTEST_DRAWN_BAR : EMPTY_BAR))}px`;
}
