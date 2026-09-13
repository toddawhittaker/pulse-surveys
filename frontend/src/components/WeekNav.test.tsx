import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import { WeekNav } from './WeekNav';

/**
 * A section whose week 3 never published — its survey window has not closed,
 * or it opened late. The report can answer for weeks 1, 2, 4 and 5 and for no
 * others, which is the whole reason this control takes a list rather than a
 * count: stepping by one from week 2 would land on a week that has no report.
 */
const PUBLISHED_WEEKS = [1, 2, 4, 5];

afterEach(cleanup);

describe('WeekNav', () => {
  it('offers both directions as named controls inside a labelled navigation', () => {
    render(
      <WeekNav publishedWeeks={PUBLISHED_WEEKS} currentWeek={2} onSelectWeek={vi.fn()} />,
    );

    const navigation = screen.getByRole('navigation', { name: 'Week navigation' });
    expect(navigation).toBeTruthy();
    // Buttons rather than styled spans, so each is in the tab order and takes a
    // keyboard press without this component reimplementing one (SPEC §14.2
    // item 4). Each is named in words: an arrow is not a name.
    expect(screen.getByRole('button', { name: 'Previous week' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Next week' })).toBeTruthy();
  });

  it('pages across published weeks rather than counting by one', () => {
    const chosen = vi.fn();
    render(<WeekNav publishedWeeks={PUBLISHED_WEEKS} currentWeek={2} onSelectWeek={chosen} />);

    fireEvent.click(screen.getByRole('button', { name: 'Next week' }));
    // Week 3 never published, so the week after 2 is 4. A control that added
    // one would ask the report for a week it has no answer for.
    expect(chosen).toHaveBeenCalledWith(4);

    fireEvent.click(screen.getByRole('button', { name: 'Previous week' }));
    expect(chosen).toHaveBeenCalledWith(1);
    expect(chosen).toHaveBeenCalledTimes(2);
  });

  it('reads the published weeks in whatever order they arrive', () => {
    const chosen = vi.fn();
    render(<WeekNav publishedWeeks={[5, 1, 4, 2]} currentWeek={2} onSelectWeek={chosen} />);

    fireEvent.click(screen.getByRole('button', { name: 'Next week' }));
    expect(chosen).toHaveBeenCalledWith(4);
  });

  it('stops at the ends, and reports nothing from a control it has stopped', () => {
    const chosen = vi.fn();
    const { rerender } = render(
      <WeekNav publishedWeeks={PUBLISHED_WEEKS} currentWeek={1} onSelectWeek={chosen} />,
    );

    const back = screen.getByRole('button', { name: 'Previous week' });
    expect(back.hasAttribute('disabled')).toBe(true);
    // The other direction is live at the same moment, which is what makes the
    // line above a statement about week 1 rather than about a control that is
    // never operable.
    expect(screen.getByRole('button', { name: 'Next week' }).hasAttribute('disabled')).toBe(false);
    fireEvent.click(back);
    expect(chosen).not.toHaveBeenCalled();

    rerender(<WeekNav publishedWeeks={PUBLISHED_WEEKS} currentWeek={5} onSelectWeek={chosen} />);

    const forward = screen.getByRole('button', { name: 'Next week' });
    expect(forward.hasAttribute('disabled')).toBe(true);
    expect(screen.getByRole('button', { name: 'Previous week' }).hasAttribute('disabled')).toBe(
      false,
    );
    fireEvent.click(forward);
    expect(chosen).not.toHaveBeenCalled();
  });
});
