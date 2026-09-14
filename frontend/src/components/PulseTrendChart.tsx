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
 * One benchmark number as the report payload carries it — the wire's
 * `ComparisonFigure`, reconciled to the schema by ticket E5-10.
 *
 * **This is the shape the server sends and not a shape of this component's
 * choosing.** E5-07 built the overlays against the README's payload sketch,
 * where a point's `mean` was a bare number and a whole series carried one
 * `suppressed` flag. The shipped schema (`app/schemas/report_benchmark.py`)
 * seals every single figure on its own instead, and E5-10 is the named
 * reconciliation point: the field names below are the wire's, so the page hands
 * this component the payload member whole and nothing maps on the way.
 *
 * `figure` is `null` wherever `suppressed` is true — a value carrying both would
 * be a suppressed figure on the wire, which SPEC §4.1 item 7 is exactly about —
 * and it is `null` again for a week the population reported nothing in, which is
 * a different fact the notice below tells apart.
 *
 * `reason` is the payload's one-word token (`"below-minimum"`) and **nothing
 * renders it**: a wire token is not a governed string, and the words a reader
 * sees come from `instructorReportTrendCopy.ts` like every other sentence on
 * this surface.
 *
 * Both optional members are optional **and** nullable because this is a
 * TypeScript shape over JSON the client casts rather than parses. See
 * {@link isDrawable} for why that is read fail-closed.
 */
export interface OverlayFigure {
  readonly suppressed: boolean;
  readonly reason?: string | null;
  readonly figure?: number | null;
}

/**
 * One week of one comparison series — the wire's `BenchmarkSeriesPoint`.
 *
 * **Every week the report publishes is a point here, suppressed weeks
 * included.** The server says so in as many words: "a suppressed week is a point
 * that is present and whose `mean` says it is suppressed". A series that dropped
 * its suppressed weeks would draw a chart with no gap where a week was withheld,
 * and a reader could subtract the section's own published weeks to find which
 * weeks the comparison population answered in.
 *
 * **There is no `termWeek`, and that is the schema's shape rather than an
 * omission.** A benchmark is past-referencing (SPEC §5.1): week N of this
 * section is compared against week N of matching sections in the current *and
 * prior* terms, so the figure behind one point belongs to several terms at once
 * and has no single term week to carry. The axis's term-week sub-labels stay the
 * section's own, which is the only stream that has them.
 */
export interface OverlayPoint {
  readonly course_week: number;
  readonly mean: OverlayFigure;
}

/**
 * One comparison series as the report payload carries it — the wire's
 * `BenchmarkSeries`, which is its weeks and nothing else.
 *
 * **There is no series-level `suppressed` flag**, and the server's schema says
 * why: a flag over a whole series is a statistic about a comparison set, and one
 * assembled outside the chokepoint is a figure no minimum was applied to. So the
 * question this component asks is per week, and "this series is suppressed"
 * means "no week of it is drawable" — see {@link drawnPoints}.
 *
 * Nothing here decides a suppression. SPEC §4.1 item 7 and the benchmark
 * minimums behind it are the server's (`comparison_after_suppression`, E5's
 * breakdown decision 2); every flag below is read, never computed.
 */
export interface OverlaySeries {
  readonly points: readonly OverlayPoint[];
}

/**
 * The two comparison series of one stream, as `streams.<stream>.benchmark` on
 * the wire. Either member may be absent, and an absent member draws nothing at
 * all.
 *
 * Both members are optional here though the schema makes both required, because
 * the payload reaching this component is cast rather than parsed: a member the
 * server stopped sending has to arrive somewhere, and the absent case is already
 * the one §4.1 item 1 governs.
 */
export interface StreamBenchmark {
  readonly comparison?: OverlaySeries | null;
  readonly university?: OverlaySeries | null;
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
function axisWeeks(lengthWeeks: number, points: readonly DrawnPoint[]): number {
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

/**
 * One week of any line on this chart, once the payload's shape has been read
 * off it: which course week, and the figure to draw there or `null`.
 *
 * The section's own {@link TrendPoint} already is one of these and reaches the
 * drawing unchanged; a comparison week becomes one in {@link drawnPoints}, which
 * is the single place the wire's per-point seal is read. Every function below
 * this line draws, and none of them asks whether a figure may be shown.
 */
interface DrawnPoint {
  readonly courseWeek: number;
  readonly mean: number | null;
}

/** Each week's place on the plot, or `null` for a week with no rating. */
function plot(points: readonly DrawnPoint[], weeks: number): readonly (PlottedPoint | null)[] {
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
 * E5's breakdown decision 2). **The decision arrives per week** (E5-10, ADR
 * 0171): every published week is a point and each point's own figure says
 * whether it may be drawn. A series with no drawable week at all draws no line,
 * contributes no legend entry, publishes no table, and says in words that it is
 * not there; a series with some draws those and leaves a gap at each withheld
 * week, exactly as it leaves one at a week the population reported nothing in.
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
  readonly comparison?: OverlaySeries | null;
  /** This stream's university-wide series, on the same terms as `comparison`. */
  readonly university?: OverlaySeries | null;
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
      {/* The notice and the line are decided by one list (`drawnPoints`), so
          there is no gap between them for a malformed payload to fall into: a
          series that is there and draws no line always says why, and a series
          that was never sent says nothing. A series with *some* drawable weeks
          draws them with a gap at each withheld week and gets no notice — the
          picture already shows the break, and a notice would be saying the line
          is missing while a reader is looking at it. */}
      {comparison !== undefined && comparisonPoints.length === 0 && (
        <p className="pulse-trend-suppression" data-testid={TREND_SUPPRESSION_COMPARISON_TESTID}>
          {fillCopy('instructor_report_trend.comparison_suppressed', {
            weeks: String(lengthWeeks),
          })}
        </p>
      )}
      {university !== undefined && universityPoints.length === 0 && (
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
 * Whether one benchmark week may be drawn — **only if its own flag says exactly
 * `false` and its own figure is a number**.
 *
 * This is the one question in the file that fails closed, and both halves of it
 * are written the strict way on purpose. {@link OverlayFigure} is a TypeScript
 * shape over JSON the client casts without parsing at runtime, so the type is a
 * description of what the server is expected to send and not a check that it
 * did. A flag that arrived renamed, misspelled, or missing is `undefined` here,
 * and `undefined` is falsy: a truthiness test would read a dropped `suppressed`
 * as "not suppressed" and draw a figure SPEC §4.1 item 7 had suppressed. The
 * whole class of payload slip resolves to "show the figure", which is the wrong
 * direction for a confidentiality rule to fail in.
 *
 * The second half is the same argument about the number. The server's rule is
 * that `figure` is `null` wherever `suppressed` is true, so a figure beside a
 * raised flag is a payload contradicting itself — and `typeof === 'number'`
 * refuses a string, a `null` and an absent member together, none of which can be
 * plotted without becoming `NaN` somewhere down the file.
 *
 * So anything that is not literally `false` beside a real number is treated as a
 * week with nothing to draw. The cost, named: a payload that stopped sending the
 * flag would show suppression notices on every panel rather than drawing lines —
 * loud, visible, and withholding nothing a reader was entitled to.
 */
function isDrawable(figure: OverlayFigure | null | undefined): boolean {
  // `!= null` rather than `!== undefined`: a JSON `null` in the `mean` position
  // is a member that was sent and cannot be read, and reading `suppressed` off
  // it throws.
  return figure != null && figure.suppressed === false && typeof figure.figure === 'number';
}

/**
 * The weeks one comparison series has something to draw, or an empty list.
 *
 * **Empty means "this series says nothing", and the caller is what turns that
 * into either silence or a notice.** An absent member renders nothing at all
 * (SPEC §4.1 item 1); a member that is present and has no drawable week renders
 * the suppression notice, which is §4.1 item 7's case and is what a series every
 * one of whose weeks the server withheld actually looks like on the wire.
 *
 * **A week that is present and not drawable stays in the list as a gap**, so the
 * line breaks there and the table beside it says there is no figure — the same
 * treatment a week the population simply did not report in gets, because from
 * the reader's side they are the same absence and the notice is what names a
 * suppression. Dropping those weeks instead would join the line across them,
 * which is a claim about weeks that were withheld.
 *
 * **A member with no `points` array is "nothing to draw" rather than a crash.**
 * `points` is required by the schema, so a member arriving without it is a
 * malformed first-party payload — the same class as an unreadable flag — and it
 * takes the same treatment. Before E5-10 this function returned `undefined`
 * there and the spread in {@link axisWeeks} threw, taking the whole panel's
 * render down with it (`docs/tickets/e5/deferred.md`).
 */
function drawnPoints(series: OverlaySeries | null | undefined): readonly DrawnPoint[] {
  const weeks = sentWeeks(series?.points).map((point) => ({
    courseWeek: point.course_week,
    mean: isDrawable(point.mean) ? (point.mean.figure ?? null) : null,
  }));
  return weeks.some((week) => week.mean !== null) ? weeks : [];
}

/**
 * The weeks a member actually carried, or none.
 *
 * Written over `unknown` rather than over {@link OverlaySeries}'s own member,
 * because the question is whether the payload sent an array at all: the type
 * says it did and the type is a description of the server rather than a check on
 * it. The cast on the other side of the test is what that costs, and it is
 * bounded — every field read off a point afterwards goes back through
 * {@link isDrawable}, which answers for a malformed one.
 */
function sentWeeks(points: unknown): readonly OverlayPoint[] {
  return Array.isArray(points) ? (points as readonly OverlayPoint[]) : [];
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
  readonly points: readonly DrawnPoint[];
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
