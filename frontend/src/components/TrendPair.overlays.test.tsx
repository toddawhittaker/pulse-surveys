import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';

import { TrendPair } from './TrendPair';
import {
  TREND_LEGEND_COMPARISON_TESTID,
  TREND_LEGEND_UNIVERSITY_TESTID,
  TREND_LINE_COMPARISON_TESTID,
  TREND_LINE_UNIVERSITY_TESTID,
  TREND_SUPPRESSION_COMPARISON_TESTID,
  TREND_SUPPRESSION_UNIVERSITY_TESTID,
  type StreamBenchmark,
  type TrendPoint,
} from './PulseTrendChart';

/**
 * The stacked pair with its comparison series — ticket E5-07.
 *
 * `TrendPair.test.tsx` holds the two-line pair E4 shipped and is untouched;
 * this file is what the benchmark props add. What it is really about is the
 * wiring: each panel gets its **own** stream's figures, and a pair given none
 * is the pair E4 shipped.
 *
 * **The four benchmark series carry twelve values and no value repeats.** The
 * two panels' comparison sets are different numbers, and so are their
 * university lines, because a pair that handed one panel's benchmark to the
 * other would draw a perfectly plausible chart out of fixtures that shared
 * values. The section streams are the same shape E4's fixtures are — one
 * constant term-week offset, which is the only offset a payload can carry.
 */
const SECTION_WEEKS = 12;

const INSTRUCTOR_WEEKS: readonly TrendPoint[] = [
  { courseWeek: 1, termWeek: 7, mean: 4.1 },
  { courseWeek: 2, termWeek: 8, mean: 4.4 },
];

const COURSE_WEEKS: readonly TrendPoint[] = [
  { courseWeek: 1, termWeek: 7, mean: 3.4 },
  { courseWeek: 2, termWeek: 8, mean: 2.6 },
];

const INSTRUCTOR_BENCHMARK: StreamBenchmark = {
  comparison: {
    suppressed: false,
    points: [
      { courseWeek: 1, mean: 3.9 },
      { courseWeek: 2, mean: 3.7 },
    ],
  },
  university: {
    suppressed: false,
    points: [
      { courseWeek: 1, mean: 3.5 },
      { courseWeek: 2, mean: 3.3 },
    ],
  },
};

const COURSE_BENCHMARK: StreamBenchmark = {
  comparison: {
    suppressed: false,
    points: [
      { courseWeek: 1, mean: 3.1 },
      { courseWeek: 2, mean: 2.9 },
    ],
  },
  university: {
    suppressed: false,
    points: [
      { courseWeek: 1, mean: 2.8 },
      { courseWeek: 2, mean: 2.4 },
    ],
  },
};

const COMPARISON_LEGEND = 'Comparable 12-week courses';
const UNIVERSITY_LEGEND = 'University';

afterEach(cleanup);

/** The two panels, in the order they are read down the page. */
function panelsOf(container: HTMLElement): { upper: Element; lower: Element } {
  const panels = [...container.querySelectorAll('.pulse-trend')];
  expect(panels, 'the pair did not render two panels').toHaveLength(2);
  const [upper, lower] = panels;
  if (upper === undefined || lower === undefined) {
    throw new Error('the pair did not render two panels, so nothing below asserted anything.');
  }
  return { upper, lower };
}

/** One panel's three lines, or as many of them as it drew. */
function linesOf(panel: Element): string[] {
  return [...panel.querySelectorAll('path')].map((path) => path.getAttribute('class') ?? '');
}

describe('TrendPair with both streams benchmarked', () => {
  it('gives each panel three lines', () => {
    const { container } = render(
      <TrendPair
        instructor={INSTRUCTOR_WEEKS}
        course={COURSE_WEEKS}
        lengthWeeks={SECTION_WEEKS}
        instructorBenchmark={INSTRUCTOR_BENCHMARK}
        courseBenchmark={COURSE_BENCHMARK}
      />,
    );

    // Drawing order is the same in both: the university line, then the
    // comparison set, then the section's own on top of them.
    const { upper, lower } = panelsOf(container);
    const expected = [
      'pulse-trend-line-university',
      'pulse-trend-line-comparison',
      'pulse-trend-line',
    ];
    expect(linesOf(upper)).toEqual(expected);
    expect(linesOf(lower)).toEqual(expected);

    expect(screen.getAllByTestId(TREND_LINE_COMPARISON_TESTID)).toHaveLength(2);
    expect(screen.getAllByTestId(TREND_LINE_UNIVERSITY_TESTID)).toHaveLength(2);
  });

  it('gives each panel its own stream’s figures', () => {
    // The mutation this kills is one panel's benchmark reaching both — which
    // draws two entirely credible charts, and puts the course stream's context
    // under the instructor stream's line.
    render(
      <TrendPair
        instructor={INSTRUCTOR_WEEKS}
        course={COURSE_WEEKS}
        lengthWeeks={SECTION_WEEKS}
        instructorBenchmark={INSTRUCTOR_BENCHMARK}
        courseBenchmark={COURSE_BENCHMARK}
      />,
    );

    const valuesOf = (stream: string, series: string): (string | null)[] =>
      within(screen.getByRole('table', { name: `Weekly ratings: ${stream}, ${series}` }))
        .getAllByRole('cell')
        .map((cell) => cell.textContent);

    expect(valuesOf('Instructor', COMPARISON_LEGEND)).toEqual(['3.9', '3.7']);
    expect(valuesOf('Instructor', UNIVERSITY_LEGEND)).toEqual(['3.5', '3.3']);
    expect(valuesOf('Course', COMPARISON_LEGEND)).toEqual(['3.1', '2.9']);
    expect(valuesOf('Course', UNIVERSITY_LEGEND)).toEqual(['2.8', '2.4']);
  });

  it('still draws one legend, at the bottom, now naming three lines', () => {
    // SPEC §5.1: one legend for the pair. Three lines do not make it two.
    const { container } = render(
      <TrendPair
        instructor={INSTRUCTOR_WEEKS}
        course={COURSE_WEEKS}
        lengthWeeks={SECTION_WEEKS}
        instructorBenchmark={INSTRUCTOR_BENCHMARK}
        courseBenchmark={COURSE_BENCHMARK}
      />,
    );

    const { upper, lower } = panelsOf(container);
    expect(upper.querySelector('.pulse-trend-legend')).toBeNull();
    const legend = lower.querySelector('.pulse-trend-legend');
    expect(legend).not.toBeNull();
    expect(
      [...(legend?.querySelectorAll('.pulse-trend-legend-item') ?? [])].map(
        (item) => item.textContent,
      ),
    ).toEqual(['This section', COMPARISON_LEGEND, UNIVERSITY_LEGEND]);
    expect(container.querySelectorAll('.pulse-trend-legend')).toHaveLength(1);
  });
});

describe('TrendPair with no benchmark at all', () => {
  it('is exactly the pair E4 shipped', () => {
    // SPEC §4.1 item 1: the components stay usable by a surface whose payload
    // carries no comparison, and neither prop has a default that draws.
    const { container } = render(
      <TrendPair instructor={INSTRUCTOR_WEEKS} course={COURSE_WEEKS} lengthWeeks={SECTION_WEEKS} />,
    );

    for (const testid of [
      TREND_LINE_COMPARISON_TESTID,
      TREND_LINE_UNIVERSITY_TESTID,
      TREND_LEGEND_COMPARISON_TESTID,
      TREND_LEGEND_UNIVERSITY_TESTID,
      TREND_SUPPRESSION_COMPARISON_TESTID,
      TREND_SUPPRESSION_UNIVERSITY_TESTID,
    ]) {
      expect(screen.queryAllByTestId(testid), `${testid} is in a pair given no benchmark`).toEqual(
        [],
      );
    }

    // Two lines, two tables, one legend entry, and no comparison word anywhere.
    expect(container.querySelectorAll('path')).toHaveLength(2);
    expect(screen.getAllByRole('table')).toHaveLength(2);
    expect(container.querySelectorAll('.pulse-trend-legend-item')).toHaveLength(1);
    expect(screen.queryByText(/comparable|university|benchmark/i)).toBeNull();
  });
});

describe('TrendPair carries a malformed flag through unchanged', () => {
  it('leaves the panel to fail closed, and still draws nothing for an absent member', () => {
    // `TrendPair` gates nothing: it hands each panel its stream's two members
    // and the panel decides. This is the proof that the pass-through does not
    // undo the panel's fail-closed reading — a pair that filled in a default
    // member, or that read the flag itself on the way past, would show a line
    // here. The upper panel's comparison member arrives with no flag at all and
    // its university member is absent entirely, so one panel carries both sides
    // of the boundary at once: a member that cannot be read says so, a member
    // that was never sent says nothing.
    const flagless = {
      comparison: { reason: 'below-minimum', points: INSTRUCTOR_BENCHMARK.comparison?.points },
    } as unknown as StreamBenchmark;

    const { container } = render(
      <TrendPair
        instructor={INSTRUCTOR_WEEKS}
        course={COURSE_WEEKS}
        lengthWeeks={SECTION_WEEKS}
        instructorBenchmark={flagless}
        courseBenchmark={COURSE_BENCHMARK}
      />,
    );

    const { upper, lower } = panelsOf(container);
    expect(linesOf(upper)).toEqual(['pulse-trend-line']);
    expect(
      upper.querySelectorAll(`[data-testid="${TREND_SUPPRESSION_COMPARISON_TESTID}"]`),
    ).toHaveLength(1);
    expect(
      upper.querySelectorAll(`[data-testid="${TREND_SUPPRESSION_UNIVERSITY_TESTID}"]`),
    ).toHaveLength(0);

    // And the lower panel, whose members are well formed, is untouched by any
    // of it: three lines and no notice.
    expect(linesOf(lower)).toEqual([
      'pulse-trend-line-university',
      'pulse-trend-line-comparison',
      'pulse-trend-line',
    ]);
    expect(lower.querySelectorAll('.pulse-trend-suppression')).toHaveLength(0);
  });
});

describe('TrendPair when the payload suppresses', () => {
  it('says so under each panel, and keeps the series that was not suppressed', () => {
    const suppressedComparison: StreamBenchmark = {
      comparison: { suppressed: true, reason: 'below-minimum', points: [] },
      university: INSTRUCTOR_BENCHMARK.university,
    };
    const suppressedBoth: StreamBenchmark = {
      comparison: { suppressed: true, reason: 'below-minimum', points: [] },
      university: { suppressed: true, reason: 'below-minimum', points: [] },
    };

    const { container } = render(
      <TrendPair
        instructor={INSTRUCTOR_WEEKS}
        course={COURSE_WEEKS}
        lengthWeeks={SECTION_WEEKS}
        instructorBenchmark={suppressedComparison}
        courseBenchmark={suppressedBoth}
      />,
    );

    const { upper, lower } = panelsOf(container);

    // The upper panel loses its comparison line and keeps the university one.
    expect(linesOf(upper)).toEqual(['pulse-trend-line-university', 'pulse-trend-line']);
    expect(upper.querySelectorAll(`[data-testid="${TREND_SUPPRESSION_COMPARISON_TESTID}"]`)).toHaveLength(
      1,
    );
    expect(upper.querySelectorAll(`[data-testid="${TREND_SUPPRESSION_UNIVERSITY_TESTID}"]`)).toHaveLength(
      0,
    );

    // The lower panel loses both and says so twice, once per series.
    expect(linesOf(lower)).toEqual(['pulse-trend-line']);
    expect(lower.querySelectorAll(`[data-testid="${TREND_SUPPRESSION_COMPARISON_TESTID}"]`)).toHaveLength(
      1,
    );
    expect(lower.querySelectorAll(`[data-testid="${TREND_SUPPRESSION_UNIVERSITY_TESTID}"]`)).toHaveLength(
      1,
    );

    // Neither panel's own line is affected by any of it: a suppressed benchmark
    // hides a benchmark, never the section's own week.
    expect(container.querySelectorAll('.pulse-trend-line')).toHaveLength(2);
    expect(screen.getAllByRole('table', { name: /^Weekly ratings: (Instructor|Course)$/ })).toHaveLength(
      2,
    );
  });
});
