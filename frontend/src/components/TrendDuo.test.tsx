import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import { RatingHistogram } from './RatingHistogram';
import { TrendDuo } from './TrendDuo';

afterEach(cleanup);

const INSTRUCTOR = [
  { courseWeek: 1, termWeek: null, mean: 3.5 },
  { courseWeek: 2, termWeek: null, mean: 4.0 },
];
const COURSE = [
  { courseWeek: 1, termWeek: null, mean: 3.0 },
  { courseWeek: 2, termWeek: null, mean: null },
];

describe('TrendDuo', () => {
  it('draws one line for each stream and nothing else', () => {
    const { container } = render(<TrendDuo instructor={INSTRUCTOR} course={COURSE} lengthWeeks={2} />);

    expect(container.querySelectorAll('path[class^="pulse-trend-line"]')).toHaveLength(2);
    expect(container.querySelectorAll('.pulse-trend-line')).toHaveLength(2);
    expect(container.querySelector('[data-testid^="trend-"]')).toBeNull();
    expect(container.querySelector('figcaption')).toBeNull();
  });

  it('names no comparison in its text, its labels or its markup', () => {
    const { container } = render(<TrendDuo instructor={INSTRUCTOR} course={COURSE} lengthWeeks={2} />);

    expect(container.innerHTML).not.toMatch(/compar|universit|benchmark|average/i);
  });

  it('puts the weeks and the means in a table, without a term-week column', () => {
    const { container } = render(<TrendDuo instructor={INSTRUCTOR} course={COURSE} lengthWeeks={2} />);

    const tables = container.querySelectorAll('table');
    expect(tables).toHaveLength(2);
    const rows = Array.from(tables[1]?.querySelectorAll('tbody tr') ?? []).map((row) =>
      Array.from(row.children).map((cell) => cell.textContent),
    );
    expect(rows).toEqual([
      ['WK 01', '3.0'],
      ['WK 02', 'No figure for this week'],
    ]);
    expect(container.textContent).not.toContain('Term week');
    expect(container.textContent).not.toContain('TERM');
  });
});

describe('the duo and the percent histogram, as a student reads them', () => {
  it('draws both panels together, with no panel waiting on the other', () => {
    const { container } = render(<TrendDuo instructor={INSTRUCTOR} course={COURSE} lengthWeeks={2} />);

    expect(container.querySelector('.pulse-trend-plot-delayed')).toBeNull();
  });

  it('gives the percent histogram a table of rating and percent, and a title naming what is rated', () => {
    const { container } = render(
      <RatingHistogram
        stream="instructor"
        distribution={{ '1': 0, '2': 10, '3': 20, '4': 40, '5': 30 }}
        unit="percent"
      />,
    );

    expect(container.textContent).toContain('Ratings about the instructor');
    const rows = Array.from(container.querySelectorAll('tbody tr')).map((row) =>
      Array.from(row.children).map((cell) => cell.textContent),
    );
    expect(rows).toEqual([
      ['1', '0%'],
      ['2', '10%'],
      ['3', '20%'],
      ['4', '40%'],
      ['5', '30%'],
    ]);
    expect(container.querySelector('table')?.className).toBe('sr-only');
    expect(container.querySelector('button.pulse-trend-numbers-toggle')).not.toBeNull();
  });
});

describe('the percent histogram’s numbers', () => {
  it('puts the toggle and the table outside the image, so both can be reached', () => {
    const { container } = render(
      <RatingHistogram
        stream="course"
        distribution={{ '1': 0, '2': 10, '3': 20, '4': 40, '5': 30 }}
        unit="percent"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Show the numbers/ }));
    expect(screen.getByRole('table')).toBeTruthy();
    for (const button of Array.from(container.querySelectorAll('button'))) {
      expect(button.closest('[role="img"]')).toBeNull();
    }
    expect(container.querySelector('table')?.closest('[role="img"]')).toBeNull();
  });

  it('keeps the trend’s buttons and tables outside any image too', () => {
    const { container } = render(<TrendDuo instructor={INSTRUCTOR} course={COURSE} lengthWeeks={2} />);

    expect(container.querySelector('[role="img"]')).toBeNull();
    expect(screen.getAllByRole('table', { hidden: true })).toHaveLength(2);
  });
});

describe('no comparison reaches a student', () => {
  // The components take no comparison prop, so a caller that planted one has
  // nothing to pass it through. The planted figures are the control: they carry
  // distinctive numbers, and none of them may appear in the text or any label.
  const PLANTED = {
    comparison: { points: [{ course_week: 1, mean: { figure: 2.718, suppressed: false } }] },
    university: { points: [{ course_week: 1, mean: { figure: 3.141, suppressed: false } }] },
  };
  const SHARES = { '1': 0, '2': 10, '3': 20, '4': 40, '5': 30 };

  function everythingReadable(container: HTMLElement): string {
    const labels = Array.from(container.querySelectorAll('[aria-label]')).map(
      (node) => node.getAttribute('aria-label') ?? '',
    );
    return `${container.textContent ?? ''} ${labels.join(' ')}`;
  }

  it('keeps planted comparison and university figures out of the trend', () => {
    const { container } = render(
      <TrendDuo instructor={INSTRUCTOR} course={COURSE} lengthWeeks={2} {...(PLANTED as object)} />,
    );

    const readable = everythingReadable(container);
    expect(readable).not.toMatch(/2\.7|3\.1|compar|universit/i);
    expect(container.querySelectorAll('.pulse-trend-line')).toHaveLength(2);
  });

  it('keeps planted figures out of the percent histogram', () => {
    const { container } = render(
      <RatingHistogram
        stream="course"
        distribution={SHARES}
        unit="percent"
        {...({ benchmark: 3.9, ...PLANTED } as object)}
      />,
    );

    expect(everythingReadable(container)).not.toMatch(/3\.9|2\.7|3\.1|compar|universit|benchmark/i);
  });
});
