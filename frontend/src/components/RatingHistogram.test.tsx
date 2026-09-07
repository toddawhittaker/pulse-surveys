import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { RatingHistogram } from './RatingHistogram';
import { AN_ORDINARY_WEEK, A_WEEK_NOBODY_ANSWERED } from './instructorReportStats.fixtures';

// `globals` is off (ADR 0151), so `@testing-library/react` finds no global
// `afterEach` to register its own cleanup with and every render would otherwise
// pile up in one document.
afterEach(cleanup);

/**
 * Each bucket's rendered text is its count above its rating tick, so a bucket
 * reading "43" is four responses at rating 3. The counts are the fixture's, and
 * the ticks are the axis the component draws whatever the counts are — which is
 * the half that has to hold when a count is zero.
 */
const buckets = (): (string | null)[] =>
  screen.getAllByRole('listitem', { hidden: true }).map((bucket) => bucket.textContent);

describe('RatingHistogram', () => {
  it('draws all five buckets, the empty one included', () => {
    render(
      <RatingHistogram
        stream="instructor"
        distribution={AN_ORDINARY_WEEK.streams.instructor.distribution}
      />,
    );

    // Rating 1 was chosen by nobody this week and is still on the axis, with a
    // count of its own: a distribution that dropped its zeroes would say nothing
    // where it means "none".
    expect(buckets()).toEqual(['01', '12', '43', '54', '35']);
  });

  it('carries the total and every count in the accessible text', () => {
    render(
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
    expect(screen.getByText('mean 3.8')).toBeTruthy();
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
    expect(buckets()).toEqual(['01', '02', '03', '04', '05']);

    // Both directions: the absent treatment above, and neither of the two ways a
    // mean over no responses reaches a page below.
    expect(container.innerHTML).not.toContain('NaN');
    expect(container.innerHTML).not.toContain('0%');
  });
});
