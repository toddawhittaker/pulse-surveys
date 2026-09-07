import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { ResponseRateBar } from './ResponseRateBar';
import {
  AN_ORDINARY_WEEK,
  A_FULL_RESPONSE_RATE,
  A_SPARSE_RESPONSE_RATE,
  A_THIN_WEEK,
  A_WEEK_NOBODY_ANSWERED,
  responseRateOf,
  validityRateOf,
} from './instructorReportStats.fixtures';

// `globals` is off (ADR 0151), so `@testing-library/react` finds no global
// `afterEach` to register its own cleanup with and every render would otherwise
// pile up in one document.
afterEach(cleanup);

const readings = (): (string | null)[] =>
  screen.getAllByRole('img').map((figure) => figure.getAttribute('aria-label'));

describe('ResponseRateBar', () => {
  it('says "N of M" with the counts it was given, not with the rate multiplied out', () => {
    render(<ResponseRateBar response={responseRateOf(AN_ORDINARY_WEEK)} />);

    // The fixture's rate is 0.62 and its counts are 13 and 21. Multiplying the
    // rate back out gives 13.02, which is no honest count of anybody — so a
    // sentence reading "13 of 21" is one taken from the integers.
    expect(readings()).toEqual(['Response rate: 13 of 21, 62%.']);
    expect(screen.getByText('13 / 21 · 62%')).toBeTruthy();
  });

  it('renders nothing about validity when it is given no validity figure', () => {
    // SPEC §3.3: the validity rate is for instructors and leadership, never for
    // students. E8 reuses this component by leaving the prop off, so leaving it
    // off has to remove the word as well as the row.
    const { container } = render(<ResponseRateBar response={responseRateOf(AN_ORDINARY_WEEK)} />);

    expect(screen.getAllByRole('img')).toHaveLength(1);
    expect(container.innerHTML.toLowerCase()).not.toContain('valid');
  });

  it('renders the validity rate beneath the response rate when it is given one', () => {
    render(
      <ResponseRateBar
        response={responseRateOf(AN_ORDINARY_WEEK)}
        validity={validityRateOf(AN_ORDINARY_WEEK)}
      />,
    );

    expect(readings()).toEqual(['Response rate: 13 of 21, 62%.', 'Validity rate: 12 of 13, 92%.']);
  });

  it('writes whole percents, from rates that do not multiply out cleanly', () => {
    render(
      <ResponseRateBar
        response={responseRateOf(A_THIN_WEEK)}
        validity={validityRateOf(A_THIN_WEEK)}
      />,
    );

    // 0.29 * 100 is 28.999999999999996 in IEEE 754 and 0.83 * 100 is
    // 83.00000000000001; a rate rendered straight would print either in full.
    expect(readings()).toEqual(['Response rate: 6 of 21, 29%.', 'Validity rate: 5 of 6, 83%.']);
  });

  it('reads a rate of one as a hundred percent', () => {
    // A fraction mistaken for a percent renders "1%", which is the same claim
    // upside down.
    render(<ResponseRateBar response={A_FULL_RESPONSE_RATE} />);

    expect(readings()).toEqual(['Response rate: 21 of 21, 100%.']);
  });

  it('rounds a sparse rate to a whole percent', () => {
    render(<ResponseRateBar response={A_SPARSE_RESPONSE_RATE} />);

    expect(readings()).toEqual(['Response rate: 1 of 200, 1%.']);
  });

  it('states the counts and withholds the percent for a week nobody answered', () => {
    const { container } = render(
      <ResponseRateBar
        response={responseRateOf(A_WEEK_NOBODY_ANSWERED)}
        validity={validityRateOf(A_WEEK_NOBODY_ANSWERED)}
      />,
    );

    // "0 of 21" is exact and complete; the percent beside it would be the "0%"
    // that reads as a verdict on the week. The validity rate has nothing to be a
    // rate of at all, so it says that instead of "0 / 0".
    expect(readings()).toEqual([
      'Response rate: 0 of 21.',
      'Validity rate: no responses yet this week.',
    ]);
    expect(screen.getByText('0 / 21 · —')).toBeTruthy();
    expect(screen.getByText('—')).toBeTruthy();

    expect(container.innerHTML).not.toContain('NaN');
    expect(container.innerHTML).not.toContain('0%');
  });
});
