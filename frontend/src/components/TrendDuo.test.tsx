import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render } from '@testing-library/react';

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
