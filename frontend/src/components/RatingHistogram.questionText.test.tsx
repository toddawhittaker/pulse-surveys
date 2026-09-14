import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { RatingHistogram } from './RatingHistogram';

/**
 * The served question wording, as the histogram title — ticket E5-02, criterion
 * 4 and the histogram half of criterion 5.
 *
 * > 4. The histogram titles render the served strings — a fixture with a
 * >    deliberately non-mockup wording renders that wording, proving nothing is
 * >    pasted client-side.
 *
 * SPEC §3.2 stores question text in a versioned table, so the wording is the
 * server's and arrives on the payload. A client carrying its own copy would be
 * right until the first re-versioning and quietly wrong afterwards, so **every
 * assertion here renders a string this file wrote and looks for that string** —
 * never one copied out of `design/InstructorMondayReport.dc.html`, which a
 * pasted-in title would also satisfy.
 *
 * A new file rather than additions to `RatingHistogram.test.tsx`: that module
 * pins the chart E4 shipped, and nothing about it changes here.
 *
 * The distributions are written inline. `instructorReportStats.fixtures.ts` is
 * another ticket's file this wave, and the counts below carry nothing this
 * module reads beyond being a week somebody answered.
 */

afterEach(cleanup);

/** A week with answers in it, so the chart draws its ordinary state. */
const AN_ANSWERED_WEEK = { '1': 0, '2': 1, '3': 4, '4': 5, '5': 3 } as const;

/**
 * Wording no mockup and no spec sentence carries.
 *
 * `design/InstructorMondayReport.dc.html` titles its two charts "My instructor
 * supported my learning" and "Materials and activities supported my learning".
 * Neither appears in this file, so a component rendering the design's words
 * instead of its prop fails every case below.
 */
const A_SERVED_INSTRUCTOR_QUESTION = 'Turning up to this class was worth my week';
const A_SERVED_COURSE_QUESTION = 'The materials this week earned the hours they cost';

/** The stream labels E4 titled these charts with, which the absent path keeps. */
const INSTRUCTOR_STREAM_LABEL = 'About the instructor';
const COURSE_STREAM_LABEL = 'About the course';

function titleOf(container: HTMLElement): string {
  const found = container.querySelector('.pulse-stat-histogram-title');
  if (found === null) throw new Error('the chart drew no title, so nothing below asserted.');
  return found.textContent ?? '';
}

describe('RatingHistogram with a served question', () => {
  it('titles the chart with the served wording, in the mockup’s quotes', () => {
    // **The mutation this kills:** the prop accepted and the stream label
    // rendered anyway, which is today's chart under a new prop name. **The near
    // miss:** the wording rendered bare, without the quotes the mockup uses to
    // say the line is a question students were asked rather than a heading the
    // product wrote.
    const { container } = render(
      <RatingHistogram
        stream="instructor"
        distribution={AN_ANSWERED_WEEK}
        questionText={A_SERVED_INSTRUCTOR_QUESTION}
      />,
    );

    expect(titleOf(container)).toBe(`“${A_SERVED_INSTRUCTOR_QUESTION}”`);
    // The stream label is gone from the visible title: the question replaced it
    // rather than joining it.
    expect(titleOf(container)).not.toContain(INSTRUCTOR_STREAM_LABEL);
  });

  it('gives each stream its own question rather than repeating one', () => {
    // **The mutation this kills:** one wording rendered for both charts — a page
    // that read `streams.instructor.question_text` and handed it to both, which
    // draws two identically titled charts and tells a reader nothing about which
    // is which.
    const { container } = render(
      <>
        <RatingHistogram
          stream="instructor"
          distribution={AN_ANSWERED_WEEK}
          questionText={A_SERVED_INSTRUCTOR_QUESTION}
        />
        <RatingHistogram
          stream="course"
          distribution={AN_ANSWERED_WEEK}
          questionText={A_SERVED_COURSE_QUESTION}
        />
      </>,
    );

    const titles = [...container.querySelectorAll('.pulse-stat-histogram-title')].map(
      (element) => element.textContent,
    );
    expect(titles).toEqual([`“${A_SERVED_INSTRUCTOR_QUESTION}”`, `“${A_SERVED_COURSE_QUESTION}”`]);
  });

  it('keeps the stream label in the spoken reading of the chart', () => {
    // The picture is `aria-hidden` and this sentence is the chart for anyone not
    // looking at it. It names the stream, because that is how a listener tells
    // the page's two charts apart; the question itself is text above it that a
    // screen reader reaches in its own right, so repeating it here would read it
    // out twice.
    render(
      <RatingHistogram
        stream="instructor"
        distribution={AN_ANSWERED_WEEK}
        questionText={A_SERVED_INSTRUCTOR_QUESTION}
      />,
    );

    const reading = screen.getByRole('img').getAttribute('aria-label') ?? '';
    expect(reading).not.toHaveLength(0);
    expect(reading).toContain(INSTRUCTOR_STREAM_LABEL);
  });

  it('titles the chart by its stream when the payload carries no wording', () => {
    // Criterion 5's histogram half. A payload built before E5-02 — a cached
    // answer, an older fixture — carries no wording, and the chart it draws is
    // the one E4 shipped rather than an empty title or a pair of quotes with
    // nothing between them.
    const { container } = render(<RatingHistogram stream="course" distribution={AN_ANSWERED_WEEK} />);

    expect(titleOf(container)).toBe(COURSE_STREAM_LABEL);
    expect(container.textContent).not.toContain('undefined');
    expect(container.textContent).not.toContain('“');
  });

  it('falls back to the stream label rather than quoting an empty wording', () => {
    // The near miss the case above cannot see: the member present and blank,
    // which is what a read that resolved nothing would serve if the wire allowed
    // it. Quoting that puts an empty pair of quotation marks where the chart's
    // title goes.
    const { container } = render(
      <RatingHistogram stream="instructor" distribution={AN_ANSWERED_WEEK} questionText="   " />,
    );

    expect(titleOf(container)).toBe(INSTRUCTOR_STREAM_LABEL);
    expect(container.textContent).not.toContain('“');
  });
});
