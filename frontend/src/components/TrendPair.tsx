import type { JSX } from 'react';

import { PulseTrendChart, type StreamBenchmark, type TrendPoint } from './PulseTrendChart';
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
 * per panel would say the same thing twice about one chart. The section's length
 * reaches both panels because it is the axis they share — the upper one plots
 * against it even though the lower one is what labels it, and two panels on
 * different domains would put one stream's week 3 above the other's week 4.
 *
 * **The lower panel's line draws second** — "TrendPair: top panel then bottom"
 * (`design/Usage Rules.md` §3). That is a delay on one 600ms draw rather than a
 * second signature moment, and like every other piece of motion here it is CSS,
 * so `design/tokens.css` removes it under `prefers-reduced-motion`.
 *
 * **The comparison series are per panel, and this passes them through** —
 * ticket E5-07. Each stream has its own comparison-set and university figures
 * in the payload (`streams.<stream>.benchmark`), so each panel is given its
 * own; nothing is shared between them and nothing is derived here. Both
 * benchmark props are optional, and a pair given neither is exactly the
 * two-line pair E4 shipped — SPEC §4.1 item 1, and `PulseTrendChart`'s
 * docstring on why an absent prop may not draw.
 *
 * **The members are the wire's own, and this reads none of them** (E5-10). The
 * props are typed as the payload spells them, so the page passes
 * `streams.<stream>.benchmark` straight through and no shape is mapped on the
 * way; every question about whether a figure may be shown is asked once, in the
 * panel, where the fail-closed reading lives.
 *
 * One consequence of one legend, said out loud: the legend is the lower panel's,
 * so it names the lines that panel draws. The two panels suppress together in
 * practice — the benchmark minimums count the sections and the students in the
 * cohort, which are the same for both streams of one section — but a payload
 * that suppressed one stream and not the other would leave the upper panel's
 * overlay lines unnamed, and each panel's own suppression notice is what still
 * says what happened.
 */
export function TrendPair({
  instructor,
  course,
  lengthWeeks,
  instructorBenchmark,
  courseBenchmark,
}: {
  /** The instructor stream's published weeks, oldest first. */
  readonly instructor: readonly TrendPoint[];
  /** The course stream's published weeks, oldest first. */
  readonly course: readonly TrendPoint[];
  /** How many weeks the section runs for, which is the axis both panels plot on. */
  readonly lengthWeeks: number;
  /** The instructor stream's two comparison series, or nothing. */
  readonly instructorBenchmark?: StreamBenchmark;
  /** The course stream's two comparison series, or nothing. */
  readonly courseBenchmark?: StreamBenchmark;
}): JSX.Element {
  return (
    <div className="pulse-trend-pair">
      <PulseTrendChart
        points={instructor}
        label={copy('instructor_report_trend.panel_instructor')}
        lengthWeeks={lengthWeeks}
        comparison={instructorBenchmark?.comparison}
        university={instructorBenchmark?.university}
        showTicks={false}
      />
      <PulseTrendChart
        points={course}
        label={copy('instructor_report_trend.panel_course')}
        lengthWeeks={lengthWeeks}
        comparison={courseBenchmark?.comparison}
        university={courseBenchmark?.university}
        showLegend
        drawDelayed
      />
    </div>
  );
}
