import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { RatingHistogram } from './RatingHistogram';
import { AN_ORDINARY_WEEK, A_WEEK_NOBODY_ANSWERED } from './instructorReportStats.fixtures';

// `globals` is off (ADR 0151), so `@testing-library/react` finds no global
// `afterEach` to register its own cleanup with and every render would otherwise
// pile up in one document.
afterEach(cleanup);

/**
 * The chart's two rows, read separately — E4-21 draws the counts and bars in one
 * box and the rating ticks in another (`design/RatingHistogram.dc.html:14-24`),
 * so a bucket's count and its tick are no longer one element's text.
 *
 * Addressed by the classes `instructorReportStats.css` paints them with, which
 * are the component's published surface rather than selectors added for a test:
 * the whole drawing is `aria-hidden`, being the picture, and the sentence beside
 * it is the part a person can read.
 */
function textsOf(container: HTMLElement, className: string): (string | null)[] {
  const found = [...container.querySelectorAll(`.${className}`)];
  expect(found.length, `nothing in the chart carries the class ${className}`).toBeGreaterThan(0);
  return found.map((element) => element.textContent);
}

const counts = (container: HTMLElement): (string | null)[] =>
  textsOf(container, 'pulse-stat-histogram-count');

const ticks = (container: HTMLElement): (string | null)[] =>
  textsOf(container, 'pulse-stat-histogram-tick');

describe('RatingHistogram', () => {
  it('draws all five buckets, the empty one included', () => {
    const { container } = render(
      <RatingHistogram
        stream="instructor"
        distribution={AN_ORDINARY_WEEK.streams.instructor.distribution}
      />,
    );

    // Rating 1 was chosen by nobody this week and is still on the axis, with a
    // count of its own: a distribution that dropped its zeroes would say nothing
    // where it means "none".
    expect(counts(container)).toEqual(['0', '1', '4', '5', '3']);
    expect(ticks(container)).toEqual(['1', '2', '3', '4', '5']);
  });

  it('holds the counts and the bars in one box and the ticks in another', () => {
    // E4-21 scope item 4, and `design/RatingHistogram.dc.html:14-24`. The count
    // shared a 96px column with its bar *and* its tick, so the tallest bucket's
    // count was pushed out of the chart region and into the mean line above it.
    // Two boxes is what stops that, and the rule under the bars is one rule and
    // not five dashes.
    const { container } = render(
      <RatingHistogram
        stream="instructor"
        distribution={AN_ORDINARY_WEEK.streams.instructor.distribution}
      />,
    );

    const bars = container.querySelector('.pulse-stat-histogram-bars');
    const tickRow = container.querySelector('.pulse-stat-histogram-ticks');
    if (bars === null || tickRow === null) {
      throw new Error('the chart drew no bars row or no tick row, so nothing below asserted.');
    }

    // Each box holds five of its own thing, and neither holds the other's: a
    // count inside the tick row, or a tick inside the bars row, is the single
    // column this replaces.
    expect(bars.querySelectorAll('.pulse-stat-histogram-count')).toHaveLength(5);
    expect(bars.querySelectorAll('.pulse-stat-histogram-bar')).toHaveLength(5);
    expect(bars.querySelectorAll('.pulse-stat-histogram-tick')).toHaveLength(0);
    expect(tickRow.querySelectorAll('.pulse-stat-histogram-tick')).toHaveLength(5);
    expect(tickRow.querySelectorAll('.pulse-stat-histogram-count')).toHaveLength(0);

    // And the tick row follows the bars, so the axis is under the chart.
    expect(bars.compareDocumentPosition(tickRow) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // The whole drawing stays out of the accessibility tree; the label carries
    // it in words (asserted below).
    expect(bars.getAttribute('aria-hidden')).toBe('true');
    expect(tickRow.getAttribute('aria-hidden')).toBe('true');
  });

  it('sets the mean’s own figure apart from the word in front of it', () => {
    // `design/RatingHistogram.dc.html:13`: the digits are full spruce inside a
    // spruce-60 line. That needs the figure to be its own element — a colour
    // cannot reach half a text node — so this pins the split rather than the
    // colour, which is the stylesheet's.
    const { container } = render(
      <RatingHistogram
        stream="instructor"
        distribution={AN_ORDINARY_WEEK.streams.instructor.distribution}
      />,
    );

    expect(textsOf(container, 'pulse-stat-histogram-mean')).toEqual(['3.8']);
    // And the label is still beside it, so the line reads as a sentence.
    expect(container.querySelector('.pulse-stat-histogram-summary')?.textContent).toBe('mean 3.8');
  });

  it('carries the total and every count in the accessible text', () => {
    const { container } = render(
      <RatingHistogram
        stream="instructor"
        distribution={AN_ORDINARY_WEEK.streams.instructor.distribution}
      />,
    );

    const reading = screen.getByRole('img').getAttribute('aria-label') ?? '';

    // Non-empty first: an absent label and an empty one both read as "no match"
    // in a query, and only one of them is this component working.
    expect(reading).not.toHaveLength(0);
    expect(reading).toBe(
      'About the instructor, ratings this week: 13 responses, mean 3.8. Responses by rating 1 to 5: 0, 1, 4, 5, 3.',
    );
    expect(container.querySelector('.pulse-stat-histogram-summary')?.textContent).toBe('mean 3.8');
  });

  it('titles the course stream as its own', () => {
    render(
      <RatingHistogram stream="course" distribution={AN_ORDINARY_WEEK.streams.course.distribution} />,
    );

    expect(screen.getByText('About the course')).toBeTruthy();
    expect(screen.getByRole('img').getAttribute('aria-label')).toBe(
      'About the course, ratings this week: 13 responses, mean 3.5. Responses by rating 1 to 5: 1, 2, 3, 4, 3.',
    );
  });

  it('shows the absent treatment, and no mean at all, for a week nobody answered', () => {
    const { container } = render(
      <RatingHistogram
        stream="instructor"
        distribution={A_WEEK_NOBODY_ANSWERED.streams.instructor.distribution}
      />,
    );

    expect(screen.getByText('No responses yet this week')).toBeTruthy();
    expect(screen.getByRole('img').getAttribute('aria-label')).toBe(
      'About the instructor, ratings this week: no responses yet.',
    );
    // Every bucket still drawn, every one of them empty.
    expect(counts(container)).toEqual(['0', '0', '0', '0', '0']);
    expect(ticks(container)).toEqual(['1', '2', '3', '4', '5']);
    // And no figure to set apart, the week having no mean at all.
    expect(container.querySelectorAll('.pulse-stat-histogram-mean')).toHaveLength(0);

    // Both directions: the absent treatment above, and neither of the two ways a
    // mean over no responses reaches a page below.
    expect(container.innerHTML).not.toContain('NaN');
    expect(container.innerHTML).not.toContain('0%');
  });
});
