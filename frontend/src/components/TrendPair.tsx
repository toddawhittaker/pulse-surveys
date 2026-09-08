import type { JSX } from 'react';

import { PulseTrendChart, type TrendPoint } from './PulseTrendChart';
import { copy } from '../copy/instructorReportTrendCopy';
import './instructorReportTrend.css';

/**
 * SPEC §7.6's `TrendPair` — ticket E4-08.
 *
 * The instructor report's stacked pair: the instructor stream above, the course
 * stream below, "shared 1–5 y-scale, one legend" (SPEC §5.1). The two panels
 * are the two questions SPEC §3.2 asks every week, and their order is fixed
 * rather than chosen by a caller — `design/Usage Rules.md` §1 makes it the same
 * order as the survey's questions and the report's comment groups, so a reader
 * moving down the report meets the streams in one order everywhere.
 *
 * **The scale is shared because it is fixed.** Both panels plot 1 to 5, which
 * is the instrument's range, so a dip in one panel is the same distance as the
 * same dip in the other. A chart that scaled each panel to its own data would
 * draw two different pictures of the same half-point and be read as two
 * different stories.
 *
 * **One axis and one legend, at the bottom.** The upper panel draws neither:
 * the weeks under the lower panel are the weeks of both, and a legend repeated
 * per panel would say the same thing twice about one chart.
 *
 * **The lower panel's line draws second** — "TrendPair: top panel then bottom"
 * (`design/Usage Rules.md` §3). That is a delay on one 600ms draw rather than a
 * second signature moment, and like every other piece of motion here it is CSS,
 * so `design/tokens.css` removes it under `prefers-reduced-motion`.
 */
export function TrendPair({
  instructor,
  course,
}: {
  /** The instructor stream's published weeks, oldest first. */
  readonly instructor: readonly TrendPoint[];
  /** The course stream's published weeks, oldest first. */
  readonly course: readonly TrendPoint[];
}): JSX.Element {
  return (
    <div className="pulse-trend-pair">
      <PulseTrendChart
        points={instructor}
        label={copy('instructor_report_trend.panel_instructor')}
        showTicks={false}
      />
      <PulseTrendChart
        points={course}
        label={copy('instructor_report_trend.panel_course')}
        showLegend
        drawDelayed
      />
    </div>
  );
}
