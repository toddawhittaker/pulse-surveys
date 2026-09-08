import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';

import { TrendPair } from './TrendPair';
import type { TrendPoint } from './PulseTrendChart';

/**
 * The two streams of one section, shaped by the payload sketch in
 * `docs/tickets/e4/README.md`: `streams.instructor.trend` and
 * `streams.course.trend`, one row per published course week, each row carrying
 * the term week SPEC §2.2 puts under the axis.
 *
 * The two streams tell different stories on purpose — the instructor stream
 * holds steady while the course stream falls away, which is E4's own exit
 * criterion in miniature — and they span different ranges, so a pair that
 * scaled each panel to its own data would draw two different y-axes and this
 * file's shared-scale assertion would red.
 *
 * **Both streams' week pairs sit at one constant offset**, six, and that is a
 * property of the payload rather than a tidy-up: the server derives a section's
 * term week from its course week with one per-section constant, so within one
 * report `termWeek - courseWeek` is the same everywhere. These fixtures held a
 * break week — course week 3 at term week 10 — which is a payload
 * `app.services.reporting` cannot emit; E4-19's security round found it and
 * E4-11 corrected it while reconciling the fixtures with the schema (E4's
 * breakdown decision 5). Six rather than zero, so a component rendering one axis
 * in the other's place is visible.
 */
const INSTRUCTOR_WEEKS: readonly TrendPoint[] = [
  { courseWeek: 1, termWeek: 7, mean: 4.1 },
  { courseWeek: 2, termWeek: 8, mean: 4.4 },
  { courseWeek: 3, termWeek: 9, mean: 4.2 },
];

const COURSE_WEEKS: readonly TrendPoint[] = [
  { courseWeek: 1, termWeek: 7, mean: 3.4 },
  { courseWeek: 2, termWeek: 8, mean: 2.6 },
  { courseWeek: 3, termWeek: 9, mean: 1.8 },
];

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

/** One panel's y-axis, as the pair of things a reader can see about it. */
function yAxisOf(panel: Element): { label: string | null; y: string | null }[] {
  return [...panel.querySelectorAll('.pulse-trend-grid-label')].map((element) => ({
    label: element.textContent,
    y: element.getAttribute('y'),
  }));
}

describe('TrendPair', () => {
  it('stacks the instructor stream above the course stream', () => {
    const { container } = render(
      <TrendPair instructor={INSTRUCTOR_WEEKS} course={COURSE_WEEKS} />,
    );

    // SPEC §5.1 fixes the order — instructor above, course below — and
    // `design/Usage Rules.md` §1 makes it the same order as the survey's
    // questions and the report's comment groups.
    const { upper, lower } = panelsOf(container);
    expect(upper.querySelector('.pulse-trend-panel-label')?.textContent).toBe('Instructor');
    expect(lower.querySelector('.pulse-trend-panel-label')?.textContent).toBe('Course');

    // And the same order for anyone reading rather than looking: the two
    // accessible tables arrive in the order the panels are drawn, each named by
    // its own stream.
    expect(screen.getAllByRole('table')).toHaveLength(2);
    expect([...container.querySelectorAll('caption')].map((caption) => caption.textContent)).toEqual([
      'Weekly ratings: Instructor',
      'Weekly ratings: Course',
    ]);
  });

  it('gives both panels the same 1 to 5 scale, whatever each stream did', () => {
    const { container } = render(
      <TrendPair instructor={INSTRUCTOR_WEEKS} course={COURSE_WEEKS} />,
    );

    const { upper, lower } = panelsOf(container);
    const upperAxis = yAxisOf(upper);
    const lowerAxis = yAxisOf(lower);

    // Non-empty first: two empty axes are identical, and would satisfy every
    // line below without asserting anything (`docs/MISTAKES.md` entry 3).
    expect(upperAxis).toHaveLength(5);
    expect(upperAxis.map((tick) => tick.label)).toEqual(['1.0', '2.0', '3.0', '4.0', '5.0']);
    expect(lowerAxis).toEqual(upperAxis);
  });

  it('draws one week axis and one legend, at the bottom of the pair', () => {
    const { container } = render(
      <TrendPair instructor={INSTRUCTOR_WEEKS} course={COURSE_WEEKS} />,
    );

    const { upper, lower } = panelsOf(container);
    expect(upper.querySelectorAll('.pulse-trend-tick-label')).toHaveLength(0);
    expect(lower.querySelectorAll('.pulse-trend-tick-label')).toHaveLength(3);
    expect(upper.querySelector('.pulse-trend-legend')).toBeNull();
    expect(lower.querySelector('.pulse-trend-legend')).not.toBeNull();

    // One legend for the whole pair, naming the one line E4 draws.
    expect(screen.getAllByText('This section')).toHaveLength(1);
    expect(container.querySelectorAll('.pulse-trend-legend')).toHaveLength(1);

    // The weeks are written once, under the lower panel, and they are both
    // axes: the course week and the quiet term week beneath it.
    expect([...container.querySelectorAll('.pulse-trend-tick-label')].map((t) => t.textContent)).toEqual(
      ['WK 01', '02', '03'],
    );
    expect([...container.querySelectorAll('.pulse-trend-tick-sub')].map((t) => t.textContent)).toEqual(
      ['TERM 07', '08', '09'],
    );
  });

  it('lets the lower panel draw after the upper one', () => {
    // `design/Usage Rules.md` §3: "TrendPair: top panel then bottom". The delay
    // is a class the stylesheet reads, so the reduced-motion switch in
    // `design/tokens.css` removes the whole staggered draw with everything else.
    const { container } = render(
      <TrendPair instructor={INSTRUCTOR_WEEKS} course={COURSE_WEEKS} />,
    );

    const { upper, lower } = panelsOf(container);
    expect(upper.querySelector('.pulse-trend-plot-delayed')).toBeNull();
    expect(lower.querySelector('.pulse-trend-plot-delayed')).not.toBeNull();
    // Both lines exist to be drawn: a pair with one missing line would satisfy
    // the two lines above by having nothing to delay.
    expect(container.querySelectorAll('.pulse-trend-line')).toHaveLength(2);
  });

  it('reads each stream’s weeks into its own table', () => {
    render(<TrendPair instructor={INSTRUCTOR_WEEKS} course={COURSE_WEEKS} />);

    const instructor = screen.getByRole('table', { name: 'Weekly ratings: Instructor' });
    expect(within(instructor).getAllByRole('cell').map((cell) => cell.textContent)).toEqual([
      'TERM 07',
      '4.1',
      'TERM 08',
      '4.4',
      'TERM 09',
      '4.2',
    ]);

    const course = screen.getByRole('table', { name: 'Weekly ratings: Course' });
    expect(within(course).getAllByRole('cell').map((cell) => cell.textContent)).toEqual([
      'TERM 07',
      '3.4',
      'TERM 08',
      '2.6',
      'TERM 09',
      '1.8',
    ]);
  });
});
