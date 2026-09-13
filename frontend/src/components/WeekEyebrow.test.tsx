import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { WeekEyebrow } from './WeekEyebrow';

// `@testing-library/react` registers its own cleanup only when `afterEach` is an
// ambient global, and ADR 0151 turns globals off. This file did without it while
// every case asserted a *presence* — two stacked documents still hold one match
// each — and the closed-week case below asserts an absence, which the leftovers
// from the two cases above would make false. Added rather than worked around:
// E4-11 is the ticket that needed the third case.
afterEach(cleanup);

describe('WeekEyebrow', () => {
  it('names both week axes in words and states the closing instant', () => {
    const closesAt = '2026-09-10T18:00:00Z';

    render(<WeekEyebrow courseWeek={4} termWeek={7} lengthWeeks={12} closesAt={closesAt} />);

    expect(screen.getByText('COURSE WK 04 / 12,')).toBeTruthy();
    expect(screen.getByText('TERM WK 07')).toBeTruthy();

    const expectedClose = new Intl.DateTimeFormat(undefined, {
      weekday: 'short',
      hour: 'numeric',
      minute: '2-digit',
    }).format(new Date(closesAt));

    expect(screen.getByText(`closes ${expectedClose}`)).toBeTruthy();
  });

  it('shows the closing instant as it arrived when it cannot be parsed', () => {
    render(<WeekEyebrow courseWeek={1} termWeek={1} lengthWeeks={12} closesAt="not-a-date" />);

    expect(screen.getByText('closes not-a-date')).toBeTruthy();
  });

  it('states both week axes and no closing span at all on a week that has closed', () => {
    // E4-11's variant: the instructor's Monday report is read after the window
    // has shut, so there is no close to state. SPEC §7.6 asks for variants
    // rather than copies, and the variant is the absence of the span — not an
    // empty one and not a dash, either of which would be the eyebrow saying
    // something about a deadline.
    //
    // **The mutations this kills.** The span rendered with nothing in it, which
    // leaves "closes" on the page over a week nobody can answer. The span
    // rendered with `undefined` formatted, which reads "closes Invalid Date".
    // And the two week numbers dropped along with it, which is why they are
    // asserted here as well as in the case above.
    const { container } = render(<WeekEyebrow courseWeek={4} termWeek={7} lengthWeeks={12} />);

    expect(screen.getByText('COURSE WK 04 / 12,')).toBeTruthy();
    expect(screen.getByText('TERM WK 07')).toBeTruthy();
    expect(container.textContent).not.toContain('closes');
    expect(container.textContent).not.toContain('Invalid Date');
    expect(container.textContent).not.toContain('undefined');
  });
});
