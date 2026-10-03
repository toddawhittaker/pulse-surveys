import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';

import {
  StatPair,
  STAT_CELL_COMPARISON_TESTID,
  STAT_CELL_UNIVERSITY_TESTID,
  type WorkloadBenchmark,
} from './StatPair';
import {
  AN_ORDINARY_WEEK,
  A_BENCHMARK_BOTH_REPORTING,
  A_BENCHMARK_WITH_A_NULL_MEMBER,
  A_BENCHMARK_WITH_AN_UNREADABLE_FLAG,
  A_BENCHMARK_WITH_NO_FIGURE_THIS_WEEK,
  A_BENCHMARK_WITH_ONLY_THE_MEDIAN_WITHHELD,
  A_BENCHMARK_WITH_THE_COMPARISON_SUPPRESSED,
  A_BENCHMARK_WITH_THE_UNIVERSITY_SUPPRESSED,
} from './instructorReportStats.fixtures';

/**
 * The workload pair's two comparison columns — ticket E5-08.
 *
 * `StatPair.test.tsx` holds the section-only pair E4-09 shipped and is not
 * touched by this ticket; this file is the comparison columns, a second file
 * beside the component for the reason `PulseTrendChart.overlays.test.tsx` is
 * (ADR 0151's placement convention, one file per body of work).
 *
 * Every figure in the fixtures renders a different string, so a column drawn
 * from the wrong member fails here rather than agreeing with the right answer
 * by coincidence.
 */

// `globals` is off (ADR 0151), so `@testing-library/react` finds no global
// `afterEach` to register its own cleanup with.
afterEach(cleanup);

const WEEK = { median: AN_ORDINARY_WEEK.workload.median, mean: AN_ORDINARY_WEEK.workload.mean };

/** The section's own two figures, as this week's fixture renders them. */
const SECTION_MEDIAN = '8.0 h';
const SECTION_MEAN = '9.5 h';

/** The comparison set's, and the university's, from the reporting fixtures. */
const COMPARISON_MEDIAN = '7.0 h';
const COMPARISON_MEAN = '9.0 h';
const UNIVERSITY_MEDIAN = '8.1 h';
const UNIVERSITY_MEAN = '10.5 h';

const WITHHELD = 'Not shown';
const TOO_SMALL = 'The set behind this figure is too small to report on.';
const NO_FIGURE = 'There is no figure for this week.';

const labels = (): (string | null)[] =>
  screen.getAllByRole('term').map((term) => term.textContent);

const values = (): (string | null)[] =>
  screen.getAllByRole('definition').map((definition) => definition.textContent);

/** The two cells of one comparison column — its median and its mean, in order. */
const cellsOf = (testid: string): HTMLElement[] => screen.getAllByTestId(testid);

describe('StatPair with both comparison columns reporting', () => {
  it('renders three labelled columns, each figure to one decimal place', () => {
    render(<StatPair {...WEEK} benchmark={A_BENCHMARK_BOTH_REPORTING} />);

    // Median row then mean row, section first in each. The fixtures are 8.96,
    // 7.04, 10.46 and 8.06: truncation would print "8.9", "7.0" without its
    // trailing zero, "10.4" and "8.0", so every wrong rule shows.
    expect(labels()).toEqual([
      'Median hours this week',
      'Median hours, comparable courses',
      'Median hours, university',
      'Mean hours this week',
      'Mean hours, comparable courses',
      'Mean hours, university',
    ]);
    expect(values()).toEqual([
      SECTION_MEDIAN,
      COMPARISON_MEDIAN,
      UNIVERSITY_MEDIAN,
      SECTION_MEAN,
      COMPARISON_MEAN,
      UNIVERSITY_MEAN,
    ]);
  });

  it('binds each comparison figure to its own column', () => {
    render(<StatPair {...WEEK} benchmark={A_BENCHMARK_BOTH_REPORTING} />);

    // Read through the cells rather than through the flat list, so that two
    // columns swapped in the grid fail here as well as in the order above.
    expect(cellsOf(STAT_CELL_COMPARISON_TESTID).map((cell) => cell.textContent)).toEqual([
      `Median hours, comparable courses${COMPARISON_MEDIAN}`,
      `Mean hours, comparable courses${COMPARISON_MEAN}`,
    ]);
    expect(cellsOf(STAT_CELL_UNIVERSITY_TESTID).map((cell) => cell.textContent)).toEqual([
      `Median hours, university${UNIVERSITY_MEDIAN}`,
      `Mean hours, university${UNIVERSITY_MEAN}`,
    ]);
  });

  it('lays the six figures out three across', () => {
    // jsdom applies no stylesheet, so the layout is pinned at the class the
    // grid rule hangs on (`instructorReportStats.css`): three labelled figures
    // per row is what makes a row readable as one figure across three columns,
    // and six cells in a two-column grid would pair the section's median with
    // the comparison set's.
    const { container } = render(<StatPair {...WEEK} benchmark={A_BENCHMARK_BOTH_REPORTING} />);

    const list = container.querySelector('dl');
    expect(list?.className).toBe('pulse-stat-pair-figures pulse-stat-pair-figures--three');
    expect(list?.children).toHaveLength(6);
  });

  it('states no comparison between the three figures', () => {
    // SPEC §4.1 item 4: no ranking, no composite scores. The prototype's third
    // line reads "vs 5.0 h comparable · 4.8 h university"; three labelled
    // figures say the same numbers and position no section against any other.
    const { container } = render(<StatPair {...WEEK} benchmark={A_BENCHMARK_BOTH_REPORTING} />);

    expect(container.textContent).not.toMatch(
      /rank|best|worst|top|bottom|score|underperform|above|below|behind|ahead|\bvs\b/i,
    );
  });
});

describe('StatPair with one comparison column suppressed', () => {
  it('withholds the comparison set in words while the university still reports', () => {
    render(<StatPair {...WEEK} benchmark={A_BENCHMARK_WITH_THE_COMPARISON_SUPPRESSED} />);

    for (const cell of cellsOf(STAT_CELL_COMPARISON_TESTID)) {
      expect(within(cell).getByText(WITHHELD)).toBeTruthy();
      expect(within(cell).getByText(TOO_SMALL)).toBeTruthy();
    }
    expect(cellsOf(STAT_CELL_UNIVERSITY_TESTID).map((cell) => cell.textContent)).toEqual([
      `Median hours, university${UNIVERSITY_MEDIAN}`,
      `Mean hours, university${UNIVERSITY_MEAN}`,
    ]);
  });

  it('withholds the university the same way, with the comparison set reporting', () => {
    render(<StatPair {...WEEK} benchmark={A_BENCHMARK_WITH_THE_UNIVERSITY_SUPPRESSED} />);

    for (const cell of cellsOf(STAT_CELL_UNIVERSITY_TESTID)) {
      expect(within(cell).getByText(WITHHELD)).toBeTruthy();
      expect(within(cell).getByText(TOO_SMALL)).toBeTruthy();
    }
    expect(cellsOf(STAT_CELL_COMPARISON_TESTID).map((cell) => cell.textContent)).toEqual([
      `Median hours, comparable courses${COMPARISON_MEDIAN}`,
      `Mean hours, comparable courses${COMPARISON_MEAN}`,
    ]);
  });

  it('puts no number and no dash where the withheld figure would be', () => {
    // The ticket's named trap. In a column of hours a "0.0" reads as "this
    // course took nobody any time" and an em dash reads as "no hours"; the
    // withholding says neither. The em dash stays the section column's own
    // treatment for a week with no measurement, which this fixture's week has.
    render(<StatPair {...WEEK} benchmark={A_BENCHMARK_WITH_THE_COMPARISON_SUPPRESSED} />);

    for (const cell of cellsOf(STAT_CELL_COMPARISON_TESTID)) {
      expect(cell.textContent).not.toMatch(/\d/);
      expect(cell.textContent).not.toContain('—');
      expect(cell.textContent).not.toContain('0');
    }
  });

  it('says the figure is withheld, never that it is zero or that nobody responded', () => {
    // SPEC §4.1 item 7 is why the figure is missing and the sentence says so —
    // the set is too small to report on. It names no minimum, because two
    // minimums stand behind the suppression and a notice naming one would be
    // wrong whenever the other fired, and it publishes no count, because a
    // count under a suppression is the inference the suppression prevents.
    const { container } = render(
      <StatPair {...WEEK} benchmark={A_BENCHMARK_WITH_THE_COMPARISON_SUPPRESSED} />,
    );

    expect(screen.getAllByText(TOO_SMALL)).toHaveLength(2);
    for (const cell of cellsOf(STAT_CELL_COMPARISON_TESTID)) {
      expect(cell.textContent).not.toMatch(/zero|none|no hours|nobody|no responses/i);
    }
    // And no count of anything anywhere: a set size beside a suppression is the
    // inference §4.1 item 7 exists to prevent.
    expect(container.textContent).not.toMatch(/\b\d+ (sections?|courses?|students?|responses?)\b/i);
  });

  it('writes the payload’s reason token on no screen', () => {
    // `reason` is a wire value, not a governed string: the words a reader sees
    // come from the copy module. The token is carried through the props so that
    // E5-10 can hand this component the payload member whole.
    const { container } = render(
      <StatPair {...WEEK} benchmark={A_BENCHMARK_WITH_THE_COMPARISON_SUPPRESSED} />,
    );

    expect(
      [
        A_BENCHMARK_WITH_THE_COMPARISON_SUPPRESSED.comparison?.mean?.reason,
        A_BENCHMARK_WITH_THE_COMPARISON_SUPPRESSED.comparison?.median?.reason,
      ],
      'the fixture carries no reason token, so this asserted nothing',
    ).toEqual(['below-minimum', 'below-minimum']);
    expect(container.textContent).not.toContain('below-minimum');
  });
});

describe('StatPair with a comparison member that reports nothing this week', () => {
  it('says there is no figure, rather than that the set is too small', () => {
    // Unsuppressed and empty is not suppressed: the set is large enough to
    // report on and this week has nothing from it. Saying "too small" here
    // would be a statement about the set that is not true.
    render(<StatPair {...WEEK} benchmark={A_BENCHMARK_WITH_NO_FIGURE_THIS_WEEK} />);

    for (const cell of cellsOf(STAT_CELL_COMPARISON_TESTID)) {
      expect(within(cell).getByText(WITHHELD)).toBeTruthy();
      expect(within(cell).getByText(NO_FIGURE)).toBeTruthy();
      expect(within(cell).queryByText(TOO_SMALL)).toBeNull();
      expect(cell.textContent).not.toMatch(/\d/);
    }
    expect(screen.getByText(`Median hours, university`)).toBeTruthy();
  });
});

describe('StatPair with one figure of a column withheld and the other not', () => {
  it('withholds that figure alone and prints the one the payload could answer', () => {
    // The shape the payload sketch could not express, and the reason E5-10
    // respelled these props: `workload_benchmark.comparison.mean` and `.median`
    // are sealed independently on the wire, so a column may report one and
    // withhold the other. A component carrying one flag per column had to
    // withhold both or show both, and either answer misstates the payload.
    render(<StatPair {...WEEK} benchmark={A_BENCHMARK_WITH_ONLY_THE_MEDIAN_WITHHELD} />);

    const [median, mean] = cellsOf(STAT_CELL_COMPARISON_TESTID);
    if (median === undefined || mean === undefined) {
      throw new Error('the comparison column did not render both of its cells.');
    }

    // The median is the withheld one, in words and with no digit of any kind.
    expect(within(median).getByText(WITHHELD)).toBeTruthy();
    expect(within(median).getByText(TOO_SMALL)).toBeTruthy();
    expect(median.textContent).not.toMatch(/\d/);

    // And the mean is printed, which is the half a component that withheld the
    // whole column would fail.
    expect(mean.textContent).toBe(`Mean hours, comparable courses${COMPARISON_MEAN}`);
    expect(within(mean).queryByText(WITHHELD)).toBeNull();

    // The university column is untouched by either decision.
    expect(cellsOf(STAT_CELL_UNIVERSITY_TESTID).map((cell) => cell.textContent)).toEqual([
      `Median hours, university${UNIVERSITY_MEDIAN}`,
      `Mean hours, university${UNIVERSITY_MEAN}`,
    ]);
  });
});

describe('StatPair with a member the payload sent as null', () => {
  it('withholds that column rather than throwing on the way to it', () => {
    // A JSON `null` is what a server written in Python sends when the figure
    // came out as `None`, and it is a member that **was** sent: it takes the
    // withheld treatment rather than the absent-column treatment, because the
    // payload made the comparison and could not answer it. Reading `suppressed`
    // off it throws a TypeError, and a guard that throws takes the whole
    // report's render down with it — the security review's finding of
    // 2026-09-13, reproduced here before it was fixed.
    const { container } = render(<StatPair {...WEEK} benchmark={A_BENCHMARK_WITH_A_NULL_MEMBER} />);

    for (const cell of cellsOf(STAT_CELL_COMPARISON_TESTID)) {
      expect(within(cell).getByText(WITHHELD)).toBeTruthy();
      expect(within(cell).getByText(TOO_SMALL)).toBeTruthy();
      expect(cell.textContent).not.toMatch(/\d/);
    }

    // And the rest of the report still renders: the section's own pair, and the
    // member that arrived whole.
    expect(values()).toEqual([
      SECTION_MEDIAN,
      `${WITHHELD}${TOO_SMALL}`,
      UNIVERSITY_MEDIAN,
      SECTION_MEAN,
      `${WITHHELD}${TOO_SMALL}`,
      UNIVERSITY_MEAN,
    ]);
    expect(container.textContent).not.toContain('null');
  });
});

describe('StatPair with a flag it cannot read', () => {
  it('withholds both columns, figures and all', () => {
    // The fail-closed reading. Both members carry a mean and a median and
    // neither carries `suppressed: false` — one lost the flag on the way, one
    // has a flag that is not a boolean — and a truthiness test would print both
    // sets of figures with nothing on the page to say anything was withheld.
    const { container } = render(
      <StatPair {...WEEK} benchmark={A_BENCHMARK_WITH_AN_UNREADABLE_FLAG} />,
    );

    for (const cell of [
      ...cellsOf(STAT_CELL_COMPARISON_TESTID),
      ...cellsOf(STAT_CELL_UNIVERSITY_TESTID),
    ]) {
      expect(within(cell).getByText(WITHHELD)).toBeTruthy();
      expect(within(cell).getByText(TOO_SMALL)).toBeTruthy();
    }

    // The section's own pair is untouched, and none of the four figures the
    // malformed member carried reached the page.
    expect(values()).toEqual([
      SECTION_MEDIAN,
      `${WITHHELD}${TOO_SMALL}`,
      `${WITHHELD}${TOO_SMALL}`,
      SECTION_MEAN,
      `${WITHHELD}${TOO_SMALL}`,
      `${WITHHELD}${TOO_SMALL}`,
    ]);
    for (const figure of [COMPARISON_MEDIAN, COMPARISON_MEAN, UNIVERSITY_MEDIAN, UNIVERSITY_MEAN]) {
      expect(container.textContent, `${figure} reached the page past an unreadable flag`).not.toContain(
        figure,
      );
    }
  });
});

describe('StatPair given one comparison member and not the other', () => {
  it('draws that column and nothing at all for the member the payload left out', () => {
    // SPEC §4.1 item 1's case rather than item 7's: a member that was never
    // sent is not a withheld figure, and a notice standing in for it would
    // announce a comparison the payload never made.
    const ONLY_THE_UNIVERSITY: WorkloadBenchmark = {
      university: A_BENCHMARK_BOTH_REPORTING.university,
    };
    render(<StatPair {...WEEK} benchmark={ONLY_THE_UNIVERSITY} />);

    expect(screen.queryAllByTestId(STAT_CELL_COMPARISON_TESTID)).toEqual([]);
    expect(screen.queryByText(/comparable/i)).toBeNull();
    expect(labels()).toEqual([
      'Median hours this week',
      'Median hours, university',
      'Mean hours this week',
      'Mean hours, university',
    ]);
    expect(values()).toEqual([SECTION_MEDIAN, UNIVERSITY_MEDIAN, SECTION_MEAN, UNIVERSITY_MEAN]);
  });
});

describe('StatPair with no benchmark at all', () => {
  it('is exactly the pair E4 shipped', () => {
    // SPEC §4.1 item 1: the component stays usable by a surface whose payload
    // carries no comparison, and the new prop has no default that draws. This
    // is the DOM every caller renders until E5-10 joins the real payload.
    const { container } = render(<StatPair {...WEEK} />);

    for (const testid of [STAT_CELL_COMPARISON_TESTID, STAT_CELL_UNIVERSITY_TESTID]) {
      expect(screen.queryAllByTestId(testid), `${testid} is in a pair given no benchmark`).toEqual(
        [],
      );
    }
    expect(labels()).toEqual(['Median hours this week', 'Mean hours this week']);
    expect(values()).toEqual([SECTION_MEDIAN, SECTION_MEAN]);
    expect(screen.queryByText(/comparable|university|benchmark|not shown/i)).toBeNull();

    // Byte for byte the markup E4-09's own tests render, down to the grid class
    // the two-column layout carries: a third column reaching a caller that
    // passed no benchmark would be a widening, not a regression.
    expect(container.innerHTML).toBe(
      '<div class="pulse-stat-pair">' +
        '<dl class="pulse-stat-pair-figures">' +
        '<div><dt class="pulse-stat-figure-label">Median hours this week</dt>' +
        '<dd class="pulse-stat-figure-value">8.0<span class="pulse-stat-figure-unit"> h</span></dd></div>' +
        '<div><dt class="pulse-stat-figure-label">Mean hours this week</dt>' +
        '<dd class="pulse-stat-figure-value">9.5<span class="pulse-stat-figure-unit"> h</span></dd></div>' +
        '</dl></div>',
    );
  });

  it('renders no comparison word for a week nobody answered either', () => {
    const { container } = render(<StatPair median={null} mean={null} />);

    expect(values()).toEqual(['—', '—']);
    expect(screen.getByText('No responses yet this week')).toBeTruthy();
    expect(container.textContent).not.toMatch(/comparable|university|not shown/i);
  });
});
