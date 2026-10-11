import type { JSX } from 'react';

import { PulseTrendChart, type TrendPoint } from './PulseTrendChart';
import { copy } from '../copy/studentResults';
import './instructorReportTrend.css';

/**
 * SPEC §7.6's `TrendDuo` — the two-stream trend a student reads, with no
 * comparison line.
 *
 * One panel per stream, the instructor above the course, each drawing exactly
 * one line: the section's own. The panels are given no comparison and no
 * university series, and `PulseTrendChart` draws nothing for a series it is not
 * given, so there is no line, legend entry, table, notice or tooltip for a
 * benchmark to arrive in (SPEC §4.1 item 1). The props are the page's own
 * stream trends and nothing else, so no caller can hand one over.
 *
 * **Both panels draw together, in one 600 ms moment** (`design/Usage Rules.md`
 * §3's one signature motion), rather than the report's top-then-bottom pair.
 *
 * **The axis is the weeks published so far.** The student's payload carries
 * neither the section's length nor a term week, and the chart derives neither:
 * `lengthWeeks` is the latest published week, and the tick row shows course
 * weeks only. The chart's table of numbers is the accessible equivalent.
 */
export function TrendDuo({
  instructor,
  course,
  lengthWeeks,
}: {
  /** The instructor stream's published weeks, oldest first. */
  readonly instructor: readonly TrendPoint[];
  /** The course stream's published weeks, oldest first. */
  readonly course: readonly TrendPoint[];
  /** How many course weeks the axis spans. */
  readonly lengthWeeks: number;
}): JSX.Element {
  const meanHeader = copy('student_results.trend_mean_header');
  const absentText = copy('student_results.trend_no_figure');
  return (
    <div className="pulse-trend-pair" data-testid="pulse-trend-duo">
      <PulseTrendChart
        points={instructor}
        label={copy('student_results.trend_instructor')}
        lengthWeeks={lengthWeeks}
        showTicks={false}
        meanHeader={meanHeader}
        absentText={absentText}
      />
      <PulseTrendChart
        points={course}
        label={copy('student_results.trend_course')}
        lengthWeeks={lengthWeeks}
        meanHeader={meanHeader}
        absentText={absentText}
      />
    </div>
  );
}
