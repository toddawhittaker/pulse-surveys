import type { JSX } from 'react';

import type { InstructorReportStatsCopyKey } from '../copy/instructorReportStatCopy';
import { copy } from '../copy/instructorReportStatCopy';
import { formatStatistic } from './instructorReportFigures';
import './instructorReportStats.css';

/**
 * One benchmark number, sealed — the wire's `ComparisonFigure`, which ticket
 * E5-10 reconciled this component's props to.
 *
 * SPEC §4.1 item 7 suppresses every figure computed from a comparison set below
 * the benchmark minimums — "a mean, a median, or any other statistic, not only a
 * drawn line" — and E5's breakdown puts that decision on the server, **per
 * figure**. E5-08 built this component against the README's payload sketch,
 * where one flag per column governed the mean and the median together; the
 * shipped schema (`app/schemas/report_benchmark.py`) seals the two
 * independently, "and neither rides on the other's decision". So the shape below
 * is the wire's and the seal is read once per cell.
 *
 * **`suppressed` has to say `false` for a figure to be drawn.** This is a
 * TypeScript shape over JSON the client casts rather than parses, so the type
 * describes what the server is expected to send and not what arrived. See
 * {@link isReportable} for why the check fails in that direction — the same
 * rule, and the same reason, as `PulseTrendChart`'s `isDrawable`.
 *
 * `reason` is the payload's one-word token (`"below-minimum"`) and **nothing
 * renders it**: a wire token is not a governed string, and the words a reader
 * sees come from `instructorReportStatCopy.ts` like every other sentence on this
 * surface.
 *
 * `figure` is `null` wherever `suppressed` is true, because a figure under a
 * suppression is the inference the suppression exists to prevent; it is `null`
 * again for a week the population has no figure in, which is a different fact
 * and takes different words.
 */
export interface BenchmarkFigure {
  readonly suppressed: boolean;
  readonly reason?: string | null;
  readonly figure?: number | null;
}

/**
 * One comparison column's pair of figures — the wire's
 * `WorkloadBenchmarkFigures`.
 *
 * Two independently sealed figures and **no flag over the pair**, which is the
 * schema's shape: a column whose median the server could report and whose mean
 * it could not shows one number and one sentence, rather than withholding both
 * on one decision nothing made.
 *
 * Both members are optional and nullable here though the schema makes both
 * required, for the reason the column members below are: the payload is cast
 * rather than parsed, and every unreadable shape has to land somewhere that
 * withholds.
 */
export interface WorkloadBenchmarkFigures {
  readonly mean?: BenchmarkFigure | null;
  readonly median?: BenchmarkFigure | null;
}

/**
 * The workload pair's two comparison columns, as `workload_benchmark` on the
 * wire. Either member may be absent, and an absent member draws no column at
 * all — not a figure and not a notice, which is SPEC §4.1 item 1's case rather
 * than item 7's.
 *
 * **A member may also arrive as `null`, and that is not the absent case.** A
 * server written in Python sends `null` for a member it computed as `None`, so
 * the difference between `undefined` and `null` here is the difference between
 * a comparison the payload never made and one it made and could not answer. The
 * second sent a member, so it draws a column — a withheld one. The type says
 * `null` because the wire carries it; a shape that denied it is what let the
 * component read `suppressed` off nothing and throw.
 */
export interface WorkloadBenchmark {
  readonly comparison?: WorkloadBenchmarkFigures | null;
  readonly university?: WorkloadBenchmarkFigures | null;
}

/** The comparison-set column's cells, addressable from a test and from E5-14's run. */
export const STAT_CELL_COMPARISON_TESTID = 'stat-cell-comparison';
/** The university column's cells. */
export const STAT_CELL_UNIVERSITY_TESTID = 'stat-cell-university';

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
 * the third line — the prototype's comparison slot — says why in the brief's own
 * words. Nothing renders a zero, which on an hours figure would read as "this
 * course took nobody any time".
 *
 * **A description list, because that is what this is:** labelled figures, each
 * label bound to its value in the markup rather than only by position, so an
 * assistive technology reads "Median hours this week, 8.0 h" instead of four
 * unrelated fragments.
 *
 * ## The comparison columns — ticket E5-08
 *
 * SPEC §5.1 asks for the section's workload figures "against comparison-set and
 * university figures", and the optional `benchmark` prop is where they arrive.
 * Given it, the list grows from two labelled figures to six: median and mean for
 * the section, for the comparison set, and for the university, each still a
 * label bound to its own value.
 *
 * **Optional, with no default anywhere.** A caller that passes no `benchmark` —
 * which is what the report does when the payload carries no
 * `workload_benchmark` — renders exactly the pair E4-09 shipped: no third column, no notice, and no comparison word in the
 * DOM at all. SPEC §4.1 item 1 is why that has to be a property of the component
 * rather than of its callers: a default that drew a column would put comparison
 * language one careless render away from a surface that must never carry it.
 *
 * **A withheld comparison figure is a sentence, never a shape that reads as a
 * number.** See `instructor_report_stats.benchmark_withheld` for the wording and
 * {@link isReportable} for what makes a figure reportable at all.
 *
 * **No benchmark figure is compared to anything here.** The component draws
 * three labelled figures and computes no difference, no ratio and no ordering
 * between them: SPEC §4.1 item 4 forbids ranking and composite scores, and a
 * "+1.2 h above comparable" line is a ranking of one section against a cohort
 * assembled at render time. The prototype's "vs 5.0 h comparable · 4.8 h
 * university" third line is the same numbers without that framing, and the
 * labelled columns carry them.
 */
export function StatPair({
  median,
  mean,
  benchmark,
}: {
  /** The section's median hours this week, or `null` when the week has none. */
  readonly median: number | null;
  /** The section's mean hours this week, or `null` when the week has none. */
  readonly mean: number | null;
  /**
   * The comparison set's and the university's figures, when the payload carries
   * them. Absent on every surface whose payload has no comparison member.
   */
  readonly benchmark?: WorkloadBenchmark;
}): JSX.Element {
  // Both figures come from the same week's answers, so they are absent
  // together; the note explains the pair rather than each dash.
  const absent = !isMeasured(median) && !isMeasured(mean);

  // Only the members the payload actually sent, in the order the brief reads
  // them: the section, then the comparison set, then the university. A member
  // sent as `null` was sent, so it keeps its column and the column is withheld;
  // only a member that is not there at all draws nothing.
  const columns = BENCHMARK_COLUMNS.filter((column) => benchmark?.[column.member] !== undefined);

  return (
    <div className="pulse-stat-pair">
      <dl
        className={
          // Three columns only when there are three: one comparison member
          // sent, or none, still lays out as the two-column grid E4-09 shipped.
          columns.length === 2
            ? 'pulse-stat-pair-figures pulse-stat-pair-figures--three'
            : 'pulse-stat-pair-figures'
        }
      >
        <Figure labelKey="instructor_report_stats.workload_median" value={median} />
        {columns.map((column) => (
          <BenchmarkCell
            key={column.member}
            labelKey={column.medianLabelKey}
            testId={column.testId}
            figure={benchmark?.[column.member]?.median}
          />
        ))}
        <Figure labelKey="instructor_report_stats.workload_mean" value={mean} />
        {columns.map((column) => (
          <BenchmarkCell
            key={column.member}
            labelKey={column.meanLabelKey}
            testId={column.testId}
            figure={benchmark?.[column.member]?.mean}
          />
        ))}
      </dl>
      {absent ? <p className="pulse-stat-note">{copy('instructor_report_stats.no_responses')}</p> : null}
    </div>
  );
}

/**
 * The two comparison columns, in the order SPEC §5.1 names them and the brief
 * reads them: the comparison set first, the university after.
 *
 * Each column names its own two labels rather than composing one from a figure
 * and a column name: a label assembled at render time is a sentence the copy
 * inventory cannot read, and §4.1 item 4 is a rule about words something has to
 * be able to find.
 */
const BENCHMARK_COLUMNS = [
  {
    member: 'comparison',
    testId: STAT_CELL_COMPARISON_TESTID,
    medianLabelKey: 'instructor_report_stats.workload_median_comparison',
    meanLabelKey: 'instructor_report_stats.workload_mean_comparison',
  },
  {
    member: 'university',
    testId: STAT_CELL_UNIVERSITY_TESTID,
    medianLabelKey: 'instructor_report_stats.workload_median_university',
    meanLabelKey: 'instructor_report_stats.workload_mean_university',
  },
] as const satisfies readonly {
  readonly member: keyof WorkloadBenchmark;
  readonly testId: string;
  readonly medianLabelKey: InstructorReportStatsCopyKey;
  readonly meanLabelKey: InstructorReportStatsCopyKey;
}[];

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
 * One comparison column's figure: the number, or the words that stand in for it.
 *
 * **One cell, one seal** (E5-10). The wire seals the mean and the median
 * independently, so this component is handed one figure and asks about that one:
 * a column whose median reports and whose mean does not shows a number on one
 * line and a sentence on the other, which is what the payload said.
 *
 * The two withheld cases are told apart because they are different facts and a
 * reader is owed the right one. A **suppressed** figure is §4.1 item 7 — the set
 * behind it is too small to report on — and an unsuppressed figure with no
 * number is a week the set has no figure in, the same fact an overlay point's
 * empty `mean` carries on the trend chart. Neither draws a dash and neither
 * draws a digit: in a column of hours, "—" reads as no hours and "0.0" reads as
 * no time spent, and the withholding says neither of those things.
 */
function BenchmarkCell({
  labelKey,
  testId,
  figure,
}: {
  readonly labelKey: InstructorReportStatsCopyKey;
  readonly testId: string;
  readonly figure: BenchmarkFigure | null | undefined;
}): JSX.Element {
  return (
    <div data-testid={testId}>
      <dt className="pulse-stat-figure-label">{copy(labelKey)}</dt>
      <dd className="pulse-stat-figure-value pulse-stat-figure-value--benchmark">
        {isReportable(figure) ? (
          <>
            {formatStatistic(figure.figure)}
            <span className="pulse-stat-figure-unit">{` ${copy('instructor_report_stats.workload_unit')}`}</span>
          </>
        ) : (
          <>
            <span className="pulse-stat-figure-withheld">
              {copy('instructor_report_stats.benchmark_withheld')}
            </span>
            <span className="pulse-stat-figure-withheld-note">
              {copy(
                saysItIsNotSuppressed(figure)
                  ? 'instructor_report_stats.benchmark_withheld_no_figure'
                  : 'instructor_report_stats.benchmark_withheld_suppressed',
              )}
            </span>
          </>
        )}
      </dd>
    </div>
  );
}

/**
 * Whether one comparison figure may be shown — **only if its own flag says
 * exactly `false` and its own number is a number**.
 *
 * This is the one question in the file that fails closed, and both halves are
 * written the strict way on purpose. {@link BenchmarkFigure} is a shape over
 * JSON the client casts without parsing at runtime, so a flag that arrived
 * renamed, misspelled or missing is `undefined` here, and `undefined` is falsy:
 * a truthiness test would read a dropped `suppressed` as "not suppressed" and
 * print a mean SPEC §4.1 item 7 had suppressed, with nothing on the page to say
 * a figure was withheld. The whole class of payload slip would resolve to "show
 * the figure", which is the wrong direction for a confidentiality rule to fail
 * in.
 *
 * The second half is the same argument about the number. The server's rule is
 * that a suppressed figure carries none, so a value beside a raised flag is a
 * payload contradicting itself, and {@link isMeasured} refuses a string, a
 * `null`, an absent member and an arithmetic-over-nothing `NaN` together.
 *
 * So anything that is not literally `false` beside a real number is withheld.
 * The cost, named: a payload that stopped sending the flag would show withheld
 * notices on every report rather than its comparison figures — loud, visible,
 * and withholding nothing a reader was entitled to.
 *
 * **An absent member is not this question.** `benchmark.comparison === undefined`
 * means the payload carried no comparison member at all, which is §4.1 item 1's
 * case and draws no column whatsoever. This function is only ever asked about a
 * cell of a column that is there, and answers `false` for one that is not so
 * that a slip in the caller cannot open a figure either.
 */
function isReportable(
  figure: BenchmarkFigure | null | undefined,
): figure is BenchmarkFigure & { readonly figure: number } {
  // `!= null` rather than `!== undefined`: a member sent as JSON `null` is one
  // this function must answer about, and reading `suppressed` off it throws.
  return figure != null && figure.suppressed === false && isMeasured(figure.figure);
}

/**
 * Whether a withheld cell's words are "no figure this week" rather than "the set
 * is too small".
 *
 * The narrower question of the two, and it decides only the sentence: a figure
 * whose seal is open and whose number is missing is a week the population has no
 * figure in, which is not a statement about the size of the set. Anything this
 * cannot read — a raised flag, an unreadable one, a member sent as `null`, a
 * member never sent — takes the suppression sentence, which is the one that
 * withholds rather than the one that explains.
 */
function saysItIsNotSuppressed(figure: BenchmarkFigure | null | undefined): boolean {
  return figure != null && figure.suppressed === false;
}

/**
 * A figure the week actually has.
 *
 * `null` is the payload saying there is nothing to average; a non-finite number
 * is arithmetic over no responses arriving as one, and both take the absent
 * treatment rather than reaching the page as "NaN h". `undefined` is a member
 * the payload left out — a suppressed comparison figure carries no `mean` and no
 * `median` at all — and is not a measurement either.
 */
function isMeasured(value: number | null | undefined): value is number {
  return value !== null && value !== undefined && Number.isFinite(value);
}
