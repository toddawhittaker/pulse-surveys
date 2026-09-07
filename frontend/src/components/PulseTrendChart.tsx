import type { JSX } from 'react';

import { copy, fillCopy } from './instructorReportTrendCopy';
import './instructorReportTrend.css';

/**
 * One week of one stream's ratings, exactly as the report payload carries it.
 *
 * **Both week numbers are the server's.** SPEC §2.2 gives course-level pages
 * two axes — the course week a section is in, and the term week the institution
 * is in — and the second cannot be derived from the first: a section that began
 * in the term's fourth week, or paused over a break week, breaks any offset a
 * chart might compute. E4-07's report payload carries both, so this component
 * renders both and calculates neither. There is no date arithmetic in this
 * file and no `Date` anywhere in it.
 *
 * `mean` is `null` for a week with no responses, which is not the same fact as
 * a week rated zero — see {@link PulseTrendChart} on how the two are drawn
 * apart.
 */
export interface TrendPoint {
  readonly courseWeek: number;
  readonly termWeek: number;
  readonly mean: number | null;
}

/** The scale every rating chart in this product shares: SPEC §5.1's 1–5. */
const SCALE_MINIMUM = 1;
const SCALE_MAXIMUM = 5;

/** The gridlines, one per whole point of the scale. */
const GRID_VALUES = [1, 2, 3, 4, 5] as const;

/**
 * The drawing surface, in user units.
 *
 * The SVG scales to its container, so these are proportions rather than pixels:
 * the plot band is `PLOT_TOP`–`PLOT_BOTTOM`, the gutter on the left holds the
 * scale's labels, and the axis band under the plot — present only when this
 * panel draws the ticks — holds the two week labels.
 */
const VIEW_WIDTH = 708;
const PLOT_HEIGHT = 190;
const PLOT_TOP = 14;
const PLOT_BOTTOM = PLOT_HEIGHT - 14;
const LABEL_GUTTER = 34;
const AXIS_BAND = 36;

/** Where a mean sits vertically. Higher ratings are higher on the screen. */
function yFor(mean: number): number {
  const fraction = (mean - SCALE_MINIMUM) / (SCALE_MAXIMUM - SCALE_MINIMUM);
  return PLOT_BOTTOM - fraction * (PLOT_BOTTOM - PLOT_TOP);
}

/**
 * Where the week at `index` sits horizontally.
 *
 * The axis spans the weeks the payload carries and no further. The prototype's
 * axis runs the section's whole length, labelling every week ahead from a term
 * offset — and that offset is the arithmetic SPEC §2.2 and this ticket's
 * known-trap forbid, because the sub-label under a week nobody has published is
 * a number the server never said. So the axis ends where the data does.
 */
function xFor(index: number, count: number): number {
  const span = VIEW_WIDTH - LABEL_GUTTER;
  if (count <= 1) return LABEL_GUTTER + span / 2;
  return LABEL_GUTTER + (index * span) / (count - 1);
}

/** A coordinate as the path writes it: one decimal, the way the prototype rounds. */
function round(value: number): string {
  return value.toFixed(1);
}

/** A week number as every axis in this product writes it: two digits. */
function padWeek(week: number): string {
  return String(week).padStart(2, '0');
}

interface PlottedPoint {
  readonly x: number;
  readonly y: number;
}

/** Each week's place on the plot, or `null` for a week with no rating. */
function plot(points: readonly TrendPoint[]): readonly (PlottedPoint | null)[] {
  return points.map((point, index) =>
    point.mean === null ? null : { x: xFor(index, points.length), y: yFor(point.mean) },
  );
}

/**
 * One unbroken run of weeks, as a path fragment.
 *
 * A run of a single week is written as a zero-length segment rather than a lone
 * `M`, because a lone `M` draws nothing at all: one answered week between two
 * silent ones would vanish from the line while its row sat in the table. The
 * round cap the line is drawn with turns that segment into a dot.
 */
function subpath(run: readonly PlottedPoint[]): string {
  const commands = run.map((point, index) => `${index === 0 ? 'M' : 'L'}${round(point.x)} ${round(point.y)}`);
  const only = run[0];
  if (run.length === 1 && only !== undefined) {
    commands.push(`L${round(only.x)} ${round(only.y)}`);
  }
  return commands.join(' ');
}

/**
 * The hero line: one path, one subpath per run of answered weeks.
 *
 * A week with no responses ends the run it was in and the next answered week
 * starts a new one, so the line is visibly broken across the gap. Joining
 * across it would draw a straight segment through weeks nobody rated, which is
 * a claim about ratings that were never given.
 */
function linePath(plotted: readonly (PlottedPoint | null)[]): string {
  const runs: PlottedPoint[][] = [];
  let run: PlottedPoint[] = [];
  for (const point of plotted) {
    if (point === null) {
      if (run.length > 0) runs.push(run);
      run = [];
      continue;
    }
    run.push(point);
  }
  if (run.length > 0) runs.push(run);
  return runs.map(subpath).join(' ');
}

/**
 * SPEC §7.6's `PulseTrendChart`, single-line — ticket E4-08.
 *
 * One stream's weekly ratings as the product's signature motif: a marigold line
 * with rounded caps and a terminal dot on the most recent answered week, over
 * hairline gridlines at each point of the 1–5 scale.
 *
 * **One line, and the props say so.** §7.6 names a three-line variant — the
 * section, its comparison set, and the university — and E4 has none of the data
 * behind the second and third. This component takes one series because that is
 * what E4 can draw; E5 adds the comparison lines together with the figures they
 * plot and the suppression rule (§4.1 item 7) that decides whether they may
 * appear at all. Nothing here anticipates them, in a prop, a legend entry, or
 * an aria label.
 *
 * **A gap is not a zero.** A week with no responses breaks the line and says so
 * in words in the table below; a week rated 1.0 sits on the scale's bottom
 * gridline. Rendering a silent week at zero would put it below the scale's own
 * floor and read as the worst week a section ever had.
 *
 * **The chart's data is reachable as text.** `docs/DESIGN_BRIEF.md` requires an
 * accessible alternative for every chart, and SPEC §14.2 item 4 puts keyboard
 * and screen-reader basics in-slice. The drawing is `aria-hidden` and a
 * visually hidden table beside it carries the same weeks and the same values,
 * so nothing about the week's story is available only as a picture. The
 * alternative is a table rather than a sentence assembled from the numbers:
 * this component writes no strings, and a spoken summary of a chart is a string
 * a component would have to write.
 *
 * **All of the motion is CSS** (`instructorReportTrend.css`), so
 * `design/tokens.css`'s global `prefers-reduced-motion` block removes it. There
 * is no inline animation and no JavaScript animation here, either of which
 * would escape that switch.
 */
export function PulseTrendChart({
  points,
  label,
  showTicks = true,
  showLegend = false,
  drawDelayed = false,
}: {
  /** One stream's published weeks, oldest first. */
  readonly points: readonly TrendPoint[];
  /** The stream this panel plots, in the words the pair labels it with. */
  readonly label: string;
  /** Whether this panel draws the week axis. A stacked pair draws it once. */
  readonly showTicks?: boolean;
  /** Whether this panel carries the legend. A stacked pair carries it once. */
  readonly showLegend?: boolean;
  /** Whether the draw waits for another panel's: the pair draws top, then bottom. */
  readonly drawDelayed?: boolean;
}): JSX.Element {
  const plotted = plot(points);
  const path = linePath(plotted);
  const terminal = plotted.reduce<PlottedPoint | null>(
    (latest, point) => point ?? latest,
    null,
  );
  const viewHeight = showTicks ? PLOT_HEIGHT + AXIS_BAND : PLOT_HEIGHT;

  return (
    <figure className="pulse-trend">
      <div className="pulse-trend-panel-label">{label}</div>
      <svg
        className={`pulse-trend-plot${drawDelayed ? ' pulse-trend-plot-delayed' : ''}`}
        viewBox={`0 0 ${String(VIEW_WIDTH)} ${String(viewHeight)}`}
        aria-hidden="true"
        focusable="false"
      >
        {GRID_VALUES.map((value) => (
          <line
            key={value}
            className="pulse-trend-grid"
            x1={LABEL_GUTTER}
            x2={VIEW_WIDTH}
            y1={yFor(value)}
            y2={yFor(value)}
          />
        ))}
        {GRID_VALUES.map((value) => (
          <text
            key={value}
            className="pulse-trend-grid-label"
            x={LABEL_GUTTER - 8}
            y={yFor(value)}
            textAnchor="end"
            dominantBaseline="middle"
          >
            {value.toFixed(1)}
          </text>
        ))}
        {path !== '' && <path className="pulse-trend-line" d={path} pathLength={1} />}
        {terminal !== null && (
          // Rounded the way the path rounds, so the dot and the end of the line
          // it terminates are the same point rather than two points a
          // twentieth of a unit apart.
          <circle className="pulse-trend-dot" cx={round(terminal.x)} cy={round(terminal.y)} r={4} />
        )}
        {showTicks &&
          points.map((point, index) => (
            <g key={point.courseWeek} className="pulse-trend-tick">
              <text
                className="pulse-trend-tick-label"
                x={xFor(index, points.length)}
                y={PLOT_HEIGHT + 4}
                textAnchor="middle"
              >
                {index === 0
                  ? fillCopy('instructor_report_trend.course_week_tick', {
                      week: padWeek(point.courseWeek),
                    })
                  : padWeek(point.courseWeek)}
              </text>
              <text
                className="pulse-trend-tick-sub"
                x={xFor(index, points.length)}
                y={PLOT_HEIGHT + 22}
                textAnchor="middle"
              >
                {index === 0
                  ? fillCopy('instructor_report_trend.term_week_tick', {
                      week: padWeek(point.termWeek),
                    })
                  : padWeek(point.termWeek)}
              </text>
            </g>
          ))}
      </svg>
      <table className="sr-only">
        <caption>
          {fillCopy('instructor_report_trend.table_caption', { stream: label })}
        </caption>
        <thead>
          <tr>
            <th scope="col">{copy('instructor_report_trend.table_course_week_header')}</th>
            <th scope="col">{copy('instructor_report_trend.table_term_week_header')}</th>
            <th scope="col">{copy('instructor_report_trend.table_mean_header')}</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point) => (
            <tr key={point.courseWeek}>
              <th scope="row">
                {fillCopy('instructor_report_trend.course_week_tick', {
                  week: padWeek(point.courseWeek),
                })}
              </th>
              <td>
                {fillCopy('instructor_report_trend.term_week_tick', {
                  week: padWeek(point.termWeek),
                })}
              </td>
              <td>
                {point.mean === null
                  ? copy('instructor_report_trend.no_responses')
                  : point.mean.toFixed(1)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {showLegend && (
        <figcaption className="pulse-trend-legend">
          <span className="pulse-trend-legend-item">
            <svg width="28" height="8" aria-hidden="true" focusable="false">
              <line className="pulse-trend-legend-line" x1="2" y1="4" x2="20" y2="4" />
              <circle className="pulse-trend-legend-dot" cx="24" cy="4" r="2.5" />
            </svg>
            {copy('instructor_report_trend.legend_section')}
          </span>
        </figcaption>
      )}
    </figure>
  );
}
