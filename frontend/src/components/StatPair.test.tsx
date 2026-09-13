import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { StatPair } from './StatPair';
import { AN_ORDINARY_WEEK, A_WEEK_NOBODY_ANSWERED } from './instructorReportStats.fixtures';

// `globals` is off (ADR 0151), so `@testing-library/react` finds no global
// `afterEach` to register its own cleanup with and every render would otherwise
// pile up in one document.
afterEach(cleanup);

const labels = (): (string | null)[] =>
  screen.getAllByRole('term').map((term) => term.textContent);

const values = (): (string | null)[] =>
  screen.getAllByRole('definition').map((definition) => definition.textContent);

describe('StatPair', () => {
  it('writes both workload figures to one decimal place', () => {
    render(
      <StatPair median={AN_ORDINARY_WEEK.workload.median} mean={AN_ORDINARY_WEEK.workload.mean} />,
    );

    // The fixture is 8.04 and 9.46. Truncation would print "8.0" and "9.4",
    // passing the value through unformatted would print "8.04" and "9.46", and
    // dropping trailing zeroes would print "8" — so each wrong rule shows.
    expect(labels()).toEqual(['Median hours this week', 'Mean hours this week']);
    expect(values()).toEqual(['8.0 h', '9.5 h']);
  });

  it('shows the absent treatment, and no hours at all, for a week nobody answered', () => {
    const { container } = render(
      <StatPair
        median={A_WEEK_NOBODY_ANSWERED.workload.median}
        mean={A_WEEK_NOBODY_ANSWERED.workload.mean}
      />,
    );

    expect(values()).toEqual(['—', '—']);
    expect(screen.getByText('No responses yet this week')).toBeTruthy();
    expect(container.innerHTML).not.toContain('NaN');
    expect(container.innerHTML).not.toContain('0.0');
  });

  it('takes the absent treatment for a figure that arrived as arithmetic over nothing', () => {
    // Not a shape the payload should ever send, and the one it would send if a
    // mean were divided by no responses upstream. It renders as an absent
    // figure rather than as the word NaN beside an "h".
    const { container } = render(<StatPair median={Number.NaN} mean={Number.NaN} />);

    expect(values()).toEqual(['—', '—']);
    expect(screen.getByText('No responses yet this week')).toBeTruthy();
    expect(container.innerHTML).not.toContain('NaN');
  });
});
