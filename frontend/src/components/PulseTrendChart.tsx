import type { JSX } from 'react';

import { copy, fillCopy } from '../copy/instructorReportTrendCopy';
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
 * file, and no `Date` is constructed or read anywhere in it — which
 * `PulseTrendChart.test.tsx` holds this file to rather than taking on trust.
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

/**
 * One week of one comparison series — ticket E5-07, shaped by the payload
 * sketch in `docs/tickets/e5/README.md`.
 *
 * The field names are {@link TrendPoint}'s, because they are the same two
 * facts: which course week, and what the mean was. **There is no `termWeek`,
 * and that is the sketch's shape rather than an omission.** A benchmark is
 * past-referencing (SPEC §5.1): week N of this section is compared against week
 * N of matching sections in the current *and prior* terms, so the figure behind
 * one point belongs to several terms at once and has no single term week to
 * carry. The axis's term-week sub-labels stay the section's own, which is the
 * only stream that has them.
 *
 * `mean` is `null` for a week the series has no reportable figure in. The line
 * breaks there, exactly as the section's line breaks at a week nobody answered:
 * drawing across it would be a claim about a week that was not reported.
 */
export interface OverlayPoint {
  readonly courseWeek: number;
  readonly mean: number | null;
}

/**
 * One comparison series as the report payload carries it: either its weeks, or
 * the fact that it is suppressed.
 *
 * SPEC §4.1 item 7 suppresses every figure computed from a comparison set below
 * the benchmark minimums, and E5's breakdown decision 2 puts the decision in
 * `comparison_after_suppression` on the server. **Nothing in this component
 * decides it** — the flag is read, never computed, and a suppressed series
 * arrives carrying no points to draw even if a caller passed some.
 *
 * **`suppressed` has to say `false` for a line to be drawn.** This is a shape
 * over JSON the client casts rather than parses, so anything else the flag
 * turns out to hold — missing, renamed, null — is read as suppressed. See
 * {@link isSuppressed} for why the check fails in that direction.
 *
 * `reason` is the payload's one-word token (`"below-minimum"` in the sketch) and
 * **nothing renders it**: a wire token is not a governed string, and the words a
 * reader sees come from `instructorReportTrendCopy.ts` like every other sentence
 * on this surface. It is carried so the payload can reach this component whole
 * in E5-10 rather than being trimmed on the way.
 */
export interface OverlaySeries {
  readonly suppressed: boolean;
  readonly reason?: string;
  readonly points: readonly OverlayPoint[];
}

/**
 * The two comparison series of one stream, as `streams.<stream>.benchmark` in
 * the payload sketch. Either member may be absent, and an absent member draws
 * nothing at all.
 */
export interface StreamBenchmark {
  readonly comparison?: OverlaySeries;
  readonly university?: OverlaySeries;
}

/** The comparison line, addressable from a test and from the end-to-end suite. */
export const TREND_LINE_COMPARISON_TESTID = 'trend-line-comparison';
/** The university line. */
export const TREND_LINE_UNIVERSITY_TESTID = 'trend-line-university';
/** The legend entry naming the comparison line, present only when that line is. */
export const TREND_LEGEND_COMPARISON_TESTID = 'trend-legend-comparison';
/** The legend entry naming the university line. */
export const TREND_LEGEND_UNIVERSITY_TESTID = 'trend-legend-university';
/** The notice standing in for a suppressed comparison series. */
export const TREND_SUPPRESSION_COMPARISON_TESTID = 'trend-suppression-comparison';
/** The notice standing in for a suppressed university series. */
export const TREND_SUPPRESSION_UNIVERSITY_TESTID = 'trend-suppression-university';

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
 * Where one course week sits horizontally, on an axis that spans the whole term.
 *
 * **The axis is the section's length and not the data's** (E4-21, and
 * `design/PulseTrendChart.dc.html:93` is what it draws): a twelve-week section in
 * its seventh week shows twelve ticks with the line occupying the elapsed seven,
 * so the shape of the term is on the page from week one and the line does not
 * re-scale itself every Monday. Stretching seven weeks across the full width
 * drew the same picture whatever the week, which is a chart that cannot say how
 * far through a course it is.
 *
 * A week's place is read off its own `courseWeek` rather than off its position in
 * the array, because published weeks have holes in them: a section whose week 3
 * never published sends weeks 2 and 4 consecutively, and an index would draw the
 * second of them one week early.
 */
function xFor(courseWeek: number, weeks: number): number {
  const span = VIEW_WIDTH - LABEL_GUTTER;
  if (weeks <= 1) return LABEL_GUTTER + span / 2;
  return LABEL_GUTTER + ((courseWeek - 1) * span) / (weeks - 1);
}

/**
 * How many weeks the axis draws: the section's length, or far enough to hold
 * every week the payload carries.
 *
 * The second half is a guard and not a feature. `lengthWeeks` is the server's
 * (`section.length_weeks`), and a report whose trend reached past it would be a
 * payload disagreeing with itself; drawing the axis short would put those weeks
 * off the right-hand edge, where nobody would see that anything was wrong.
 */
function axisWeeks(lengthWeeks: number, points: readonly OverlayPoint[]): number {
  return Math.max(lengthWeeks, ...points.map((point) => point.courseWeek), 1);
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
function plot(points: readonly OverlayPoint[], weeks: number): readonly (PlottedPoint | null)[] {
  return points.map((point) =>
    point.mean === null ? null : { x: xFor(point.courseWeek, weeks), y: yFor(point.mean) },
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
 * One series' line: one path, one subpath per run of weeks that have a figure.
 *
 * A week with no responses ends the run it was in and the next answered week
 * starts a new one, so the line is visibly broken across the gap. Joining
 * across it would draw a straight segment through weeks nobody rated, which is
 * a claim about ratings that were never given.
 *
 * The hero line and the two comparison overlays share this, and share it for
 * the same reason: a comparison week the payload reported no figure for is a
 * gap in that line too, never a bridge between the weeks on either side of it.
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

/** One week of the axis: its course week, and the term week under it if there is one. */
interface AxisTick {
  readonly courseWeek: number;
  /** The term week the payload gave for this course week, or `null` for a week it has not sent. */
  readonly termWeek: number | null;
  /** Whether this is the first sub-label on the axis, which is the one named in words. */
  readonly leadsTheTermAxis: boolean;
}

/**
 * Every week of the term, with the term week under the ones the payload has
 * answered for.
 *
 * **A week ahead of the report gets no sub-label, and that is the rule rather
 * than a gap.** SPEC §2.2 keeps the term week off the client's arithmetic — "a
 * section that began in the term's fourth week, or paused over a break week,
 * breaks any offset a chart might compute" — so the axis can say which course
 * week is which for the whole term, and can say which term week a course week
 * falls in only for the weeks the server has said it about. The prototype fills
 * the rest from a term offset; that offset is exactly the derivation the spec
 * refuses.
 */
function axisTicks(weeks: number, points: readonly TrendPoint[]): readonly AxisTick[] {
  const byCourseWeek = new Map(points.map((point) => [point.courseWeek, point.termWeek]));
  const first = Math.min(...byCourseWeek.keys());
  return Array.from({ length: weeks }, (_, index) => {
    const courseWeek = index + 1;
    return {
      courseWeek,
      termWeek: byCourseWeek.get(courseWeek) ?? null,
      leadsTheTermAxis: courseWeek === first,
    };
  });
}

/**
 * SPEC §7.6's `PulseTrendChart`, single-line — ticket E4-08.
 *
 * One stream's weekly ratings as the product's signature motif: a marigold line
 * with rounded caps and a terminal dot on the most recent answered week, over
 * hairline gridlines at each point of the 1–5 scale.
 *
 * **Three lines, and two of them are optional — ticket E5-07.** §7.6 names a
 * three-line variant: the section, its comparison set, and the university. The
 * second and third arrive as `comparison` and `university`, and **an absent
 * prop draws absolutely nothing**: no path, no legend entry, no table, no
 * notice. That is not tidiness, it is SPEC §4.1 item 1 — this component is the
 * one the benchmark-free surfaces render too, and a default that drew would put
 * a comparison line in front of a reader the payload sends none to. There is no
 * default value for either prop anywhere in this file, and the test file's
 * absent-prop render is what holds it there.
 *
 * **Nothing here decides whether a comparison may be shown.** §4.1 item 7 and
 * the benchmark minimums behind it are the server's (`comparison_after_suppression`,
 * E5's breakdown decision 2). A series arrives either with points or marked
 * suppressed, and this renders what it was handed: a suppressed series draws no
 * line, contributes no legend entry, publishes no table, and says in words that
 * it is not there.
 *
 * **The three lines are told apart without colour.** The section's is solid and
 * 2.5px with its terminal dot; the comparison set's is dashed; the university's
 * is dotted — `docs/DESIGN_BRIEF.md`'s semantic mapping, and each pattern is a
 * class in `instructorReportTrend.css` rather than an inline attribute, so the
 * dash and the stroke stay in one place. On the colour those two lines take,
 * and where that departs from the brief, see the stylesheet.
 *
 * **The axis is the whole term, and the line is what has happened so far**
 * (E4-21). Every one of the section's weeks gets a tick, whether or not a report
 * exists for it; the term-week sub-label appears only under the weeks the
 * payload has answered for, because SPEC §2.2 forbids deriving one for a week
 * the server has not spoken about. See `xFor` and `axisTicks`.
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
  lengthWeeks,
  comparison,
  university,
  showTicks = true,
  showLegend = false,
  drawDelayed = false,
}: {
  /** One stream's published weeks, oldest first. */
  readonly points: readonly TrendPoint[];
  /** The stream this panel plots, in the words the pair labels it with. */
  readonly label: string;
  /**
   * How many weeks the section runs for — `section.length_weeks`, and the whole
   * axis (E4-21).
   *
   * Required rather than defaulted to the number of points: a default would be
   * the elapsed-weeks axis this ticket removes, arriving silently wherever a
   * caller forgot the section it was drawing. The number is the server's, for
   * the reason `WeekEyebrow` gives about the same field — SPEC §2.2 keeps the
   * letter-to-length table on the institution's side, and nothing here derives
   * it.
   */
  readonly lengthWeeks: number;
  /**
   * This stream's comparison-set series, or nothing.
   *
   * Optional with **no default**, and undefined means undefined: the chart is
   * then exactly the single-line chart E4 shipped. See this component's
   * docstring on why that is §4.1 item 1 rather than a convenience.
   */
  readonly comparison?: OverlaySeries;
  /** This stream's university-wide series, on the same terms as `comparison`. */
  readonly university?: OverlaySeries;
  /** Whether this panel draws the week axis. A stacked pair draws it once. */
  readonly showTicks?: boolean;
  /** Whether this panel carries the legend. A stacked pair carries it once. */
  readonly showLegend?: boolean;
  /** Whether the draw waits for another panel's: the pair draws top, then bottom. */
  readonly drawDelayed?: boolean;
}): JSX.Element {
  // What each comparison series actually contributes to the drawing. Absent and
  // suppressed both come out empty here, and they part company below: absent
  // renders nothing anywhere, suppressed renders a notice.
  const comparisonPoints = drawnPoints(comparison);
  const universityPoints = drawnPoints(university);

  // The axis still spans the section's term. The overlays join the guard for
  // the reason the section's own weeks are in it: a week past the end of the
  // axis would be drawn off the right-hand edge, where nobody would see that
  // the payload and the section's length disagreed.
  const weeks = axisWeeks(lengthWeeks, [...points, ...comparisonPoints, ...universityPoints]);
  const plotted = plot(points, weeks);
  const path = linePath(plotted);
  const comparisonPath = linePath(plot(comparisonPoints, weeks));
  const universityPath = linePath(plot(universityPoints, weeks));
  const comparisonLabel = fillCopy('instructor_report_trend.legend_comparison', {
    weeks: String(lengthWeeks),
  });
  const universityLabel = copy('instructor_report_trend.legend_university');
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
        {/* The two overlays are drawn before the hero, so the hero is the line
            on top wherever they cross. Neither carries `pathLength`: they fade
            in rather than drawing on, which is the brief's "benchmark lines
            fade in after" and keeps the one 600ms signature moment the
            section's line owns. */}
        {universityPath !== '' && (
          <path
            className="pulse-trend-line-university"
            data-testid={TREND_LINE_UNIVERSITY_TESTID}
            d={universityPath}
          />
        )}
        {comparisonPath !== '' && (
          <path
            className="pulse-trend-line-comparison"
            data-testid={TREND_LINE_COMPARISON_TESTID}
            d={comparisonPath}
          />
        )}
        {path !== '' && <path className="pulse-trend-line" d={path} pathLength={1} />}
        {terminal !== null && (
          // Rounded the way the path rounds, so the dot and the end of the line
          // it terminates are the same point rather than two points a
          // twentieth of a unit apart.
          <circle className="pulse-trend-dot" cx={round(terminal.x)} cy={round(terminal.y)} r={4} />
        )}
        {showTicks &&
          axisTicks(weeks, points).map((tick) => (
            <g key={tick.courseWeek} className="pulse-trend-tick">
              <text
                className="pulse-trend-tick-label"
                x={xFor(tick.courseWeek, weeks)}
                y={PLOT_HEIGHT + 4}
                textAnchor="middle"
              >
                {tick.courseWeek === 1
                  ? fillCopy('instructor_report_trend.course_week_tick', {
                      week: padWeek(tick.courseWeek),
                    })
                  : padWeek(tick.courseWeek)}
              </text>
              {tick.termWeek === null ? null : (
                <text
                  className="pulse-trend-tick-sub"
                  x={xFor(tick.courseWeek, weeks)}
                  y={PLOT_HEIGHT + 22}
                  textAnchor="middle"
                >
                  {tick.leadsTheTermAxis
                    ? fillCopy('instructor_report_trend.term_week_tick', {
                        week: padWeek(tick.termWeek),
                      })
                    : padWeek(tick.termWeek)}
                </text>
              )}
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
      {comparisonPoints.length > 0 && (
        <OverlayTable stream={label} series={comparisonLabel} points={comparisonPoints} />
      )}
      {universityPoints.length > 0 && (
        <OverlayTable stream={label} series={universityLabel} points={universityPoints} />
      )}
      {/* The notice and the line are decided by one question asked one way
          (`isSuppressed`), so there is no gap between them for a malformed flag
          to fall into: a series that draws no line always says why. */}
      {comparison !== undefined && isSuppressed(comparison) && (
        <p className="pulse-trend-suppression" data-testid={TREND_SUPPRESSION_COMPARISON_TESTID}>
          {fillCopy('instructor_report_trend.comparison_suppressed', {
            weeks: String(lengthWeeks),
          })}
        </p>
      )}
      {university !== undefined && isSuppressed(university) && (
        <p className="pulse-trend-suppression" data-testid={TREND_SUPPRESSION_UNIVERSITY_TESTID}>
          {copy('instructor_report_trend.university_suppressed')}
        </p>
      )}
      {showLegend && (
        <figcaption className="pulse-trend-legend">
          <span className="pulse-trend-legend-item">
            <svg width="28" height="8" aria-hidden="true" focusable="false">
              <line className="pulse-trend-legend-line" x1="2" y1="4" x2="20" y2="4" />
              <circle className="pulse-trend-legend-dot" cx="24" cy="4" r="2.5" />
            </svg>
            {copy('instructor_report_trend.legend_section')}
          </span>
          {/* A legend entry only for a line that is on the plot. A legend naming
              a suppressed series would be the chart claiming a line a reader
              cannot find, and a legend naming an absent one would be comparison
              language on a surface the payload sent no comparison to. */}
          {comparisonPath !== '' && (
            <span className="pulse-trend-legend-item" data-testid={TREND_LEGEND_COMPARISON_TESTID}>
              <svg width="28" height="8" aria-hidden="true" focusable="false">
                <line className="pulse-trend-legend-line-comparison" x1="2" y1="4" x2="26" y2="4" />
              </svg>
              {comparisonLabel}
            </span>
          )}
          {universityPath !== '' && (
            <span className="pulse-trend-legend-item" data-testid={TREND_LEGEND_UNIVERSITY_TESTID}>
              <svg width="28" height="8" aria-hidden="true" focusable="false">
                <line className="pulse-trend-legend-line-university" x1="2" y1="4" x2="26" y2="4" />
              </svg>
              {universityLabel}
            </span>
          )}
        </figcaption>
      )}
    </figure>
  );
}

/**
 * Whether a series the payload sent may be drawn — **only if its flag says
 * exactly `false`**.
 *
 * This is the one question in the file that fails closed, and the comparison is
 * `=== false` rather than a truthiness test on purpose. `OverlaySeries` is a
 * TypeScript shape over JSON the client casts without parsing at runtime, so the
 * type is a description of what the server is expected to send and not a check
 * that it did. A flag that arrived renamed, misspelled, or missing is
 * `undefined` here, and `undefined` is falsy: a truthiness test would read a
 * dropped `suppressed` as "not suppressed" and draw a line SPEC §4.1 item 7 had
 * suppressed, with no notice to say anything was withheld. The whole class of
 * payload slip resolves to "show the figure", which is the wrong direction for a
 * confidentiality rule to fail in.
 *
 * So anything that is not literally `false` is treated as suppressed. The cost,
 * named: a payload that stopped sending the flag would show suppression notices
 * on every panel rather than drawing lines — loud, visible, and withholding
 * nothing a reader was entitled to.
 *
 * **An absent prop is not this question.** `comparison === undefined` means the
 * payload carried no comparison member at all, which is §4.1 item 1's case and
 * renders nothing whatsoever — no line and no notice. This function is only ever
 * asked about a series that is there.
 */
function isSuppressed(series: OverlaySeries): boolean {
  return series.suppressed !== false;
}

/**
 * The weeks one comparison series carries, or an empty list.
 *
 * Absent and suppressed both come out empty, and the caller is what tells them
 * apart. A suppressed series is emptied here rather than trusted to arrive with
 * no points: the payload sketch says a suppressed member carries `points: []`
 * and nothing else, and a chart that drew whatever it was handed would put a
 * line under a suppression notice the first time that contract slipped. That is
 * the same defence as {@link isSuppressed}, pointed at the other half of the
 * member — the flag and the points each stop the other being believed alone.
 */
function drawnPoints(series: OverlaySeries | undefined): readonly OverlayPoint[] {
  if (series === undefined || isSuppressed(series)) return [];
  return series.points;
}

/**
 * One comparison series as text, beside the drawing.
 *
 * The same job the section's own table does, for the same reason — the brief
 * asks every chart for an accessible alternative — and a table of its own
 * rather than two more columns on the section's, because the two series do not
 * share the section's rows: a benchmark can report a week the section never
 * published, and folding it into a row set keyed by the section's weeks would
 * drop it from the text while leaving it on the picture.
 *
 * There is no term-week column, because an {@link OverlayPoint} has no term
 * week to put in one.
 */
function OverlayTable({
  stream,
  series,
  points,
}: {
  /** The panel's own label, which is what tells two panels' tables apart. */
  readonly stream: string;
  /** This series' name, in the same words the legend gives it. */
  readonly series: string;
  readonly points: readonly OverlayPoint[];
}): JSX.Element {
  return (
    <table className="sr-only">
      <caption>
        {fillCopy('instructor_report_trend.overlay_table_caption', { stream, series })}
      </caption>
      <thead>
        <tr>
          <th scope="col">{copy('instructor_report_trend.table_course_week_header')}</th>
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
              {point.mean === null
                ? copy('instructor_report_trend.overlay_no_figure')
                : point.mean.toFixed(1)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
