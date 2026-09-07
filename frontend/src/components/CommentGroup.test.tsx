import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { CommentGroup } from './CommentGroup';
import {
  COURSE_COMMENTS,
  COURSE_SUMMARY,
  INSTRUCTOR_COMMENTS,
  INSTRUCTOR_SUMMARY,
  SMALL_N_SUMMARY,
  SMALL_N_THRESHOLD,
  WITHHELD_COMMENT_COUNT,
  WITHHELD_COMMENTS,
} from './instructorReportCommentFixtures';

afterEach(cleanup);

const EMPTY_NOTICE = 'No comments this week.';
const SMALL_N_TITLE = 'Comments are hidden this week';

describe('CommentGroup', () => {
  it('leads with the stream summary and follows it with the comments, in the order given', () => {
    render(
      <CommentGroup
        stream="instructor"
        summary={INSTRUCTOR_SUMMARY}
        comments={INSTRUCTOR_COMMENTS}
      />,
    );

    // SPEC §5.1: comments grouped under "About the instructor" / "About the
    // course", "each group led by its own AI summary".
    expect(screen.getByRole('heading', { name: 'About the instructor' })).toBeTruthy();

    const summary = screen.getByRole('region', { name: 'AI summary — instructor comments' });
    const cards = screen.getAllByRole('article');

    expect(cards).toHaveLength(INSTRUCTOR_COMMENTS.length);
    expect(
      summary.compareDocumentPosition(cards[0] as Element) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    // The order is the array's, which is the order the server randomized (§4).
    // Nothing here sorts or groups, and this is what says so.
    expect(cards.map((card) => card.textContent)).toEqual(
      INSTRUCTOR_COMMENTS.map((comment) => comment.text),
    );
  });

  it('names the course stream with the course stream headings', () => {
    render(<CommentGroup stream="course" summary={COURSE_SUMMARY} comments={COURSE_COMMENTS} />);

    expect(screen.getByRole('heading', { name: 'About the course' })).toBeTruthy();
    expect(screen.getByRole('region', { name: 'AI summary — course comments' })).toBeTruthy();
    expect(screen.getAllByRole('article')).toHaveLength(COURSE_COMMENTS.length);
  });

  describe('a week that produced no comments', () => {
    it('keeps its heading and its summary and states the fact in one line', () => {
      render(<CommentGroup stream="instructor" summary={INSTRUCTOR_SUMMARY} comments={[]} />);

      // §5.1: "empty groups show a one-line notice, not a hidden heading."
      expect(screen.getByRole('heading', { name: 'About the instructor' })).toBeTruthy();
      expect(screen.getByRole('region', { name: 'AI summary — instructor comments' })).toBeTruthy();
      expect(screen.getByText(EMPTY_NOTICE)).toBeTruthy();
      expect(screen.queryAllByRole('article')).toHaveLength(0);
    });

    it('does not tell the instructor the comments are being withheld', () => {
      render(<CommentGroup stream="instructor" summary={INSTRUCTOR_SUMMARY} comments={[]} />);

      // The empty group and the suppressed group are different facts about the
      // class, and the copy for one must never stand in for the other.
      expect(screen.getByText(EMPTY_NOTICE)).toBeTruthy();
      expect(screen.queryByText(SMALL_N_TITLE)).toBeNull();
      expect(screen.queryByText(/raw comments stay hidden/)).toBeNull();
    });
  });

  describe('a week below the response threshold', () => {
    it('shows the notice and the summary and no comments at all', () => {
      // The fixture hands a suppressed group a full week of comments on purpose:
      // "no cards rendered" has to be a fact about the suppression rather than
      // about an empty array.
      expect(WITHHELD_COMMENTS).toHaveLength(WITHHELD_COMMENT_COUNT);

      render(
        <CommentGroup
          stream="instructor"
          summary={SMALL_N_SUMMARY}
          comments={WITHHELD_COMMENTS}
          smallN={{ threshold: SMALL_N_THRESHOLD, withNotice: true }}
        />,
      );

      // §4: below the threshold the instructor sees the summary and no raw
      // comments. All three assertions matter together — the summary and the
      // notice are the positive controls that make the empty card list mean
      // suppression rather than a group that failed to render.
      expect(screen.getByRole('region', { name: 'AI summary — instructor comments' })).toBeTruthy();
      expect(screen.getByText(SMALL_N_SUMMARY.text)).toBeTruthy();
      expect(screen.getByRole('region', { name: SMALL_N_TITLE })).toBeTruthy();
      expect(screen.queryAllByRole('article')).toHaveLength(0);
      for (const comment of WITHHELD_COMMENTS) {
        expect(screen.queryByText(comment.text)).toBeNull();
      }
      // And this is a withheld week, not an empty one.
      expect(screen.queryByText(EMPTY_NOTICE)).toBeNull();
    });

    it('carries no count of what was withheld, in its text or in any attribute', () => {
      const { container } = render(
        <CommentGroup
          stream="instructor"
          summary={SMALL_N_SUMMARY}
          comments={WITHHELD_COMMENTS}
          smallN={{ threshold: SMALL_N_THRESHOLD, withNotice: true }}
        />,
      );

      // §5.2: below the threshold there is "no chip, no count, no flag-type
      // hint". Two halves, because a count can hide in either: every number a
      // reader sees, and every number an attribute carries.
      expect(container.textContent).toContain(SMALL_N_SUMMARY.text);

      // The only numbers in the words are the count the summary drew from and
      // the configured threshold — in that order, as the group renders them.
      const digits = (container.textContent ?? '').match(/\d+/g) ?? [];
      expect(digits).toEqual([String(SMALL_N_SUMMARY.responseCount), String(SMALL_N_THRESHOLD)]);

      // And the attributes, `data-` ones included. React's generated ids are
      // skipped: they are the runtime's own counter and say nothing about this
      // week. The two assertions before the last one are what stop this scan
      // passing over a tree it never read.
      const attributes: string[] = [];
      for (const element of container.querySelectorAll('*')) {
        for (const attribute of element.attributes) {
          if (attribute.name === 'id' || attribute.name === 'aria-labelledby') continue;
          attributes.push(`${attribute.name}="${attribute.value}"`);
        }
      }

      expect(attributes.length).toBeGreaterThan(0);
      expect(attributes.some((attribute) => attribute.startsWith('class='))).toBe(true);
      expect(attributes.filter((attribute) => attribute.startsWith('data-'))).toEqual([]);
      expect(
        attributes.filter((attribute) => attribute.includes(String(WITHHELD_COMMENT_COUNT))),
      ).toEqual([]);
    });

    it('shows the summary without the notice when the surface states it elsewhere', () => {
      render(
        <CommentGroup
          stream="course"
          summary={SMALL_N_SUMMARY}
          comments={WITHHELD_COMMENTS}
          smallN={{ threshold: SMALL_N_THRESHOLD, withNotice: false }}
        />,
      );

      // SPEC §4.1 item 5: confidentiality copy appears exactly once per surface.
      // A suppressed week suppresses both of the report's groups, so the second
      // one carries the summary and no second copy of the notice — and it does
      // not fall back to the empty-week line either, because the week was not
      // empty.
      expect(screen.getByRole('region', { name: 'AI summary — course comments' })).toBeTruthy();
      expect(screen.getByText(SMALL_N_SUMMARY.text)).toBeTruthy();
      expect(screen.queryByText(SMALL_N_TITLE)).toBeNull();
      expect(screen.queryByText(EMPTY_NOTICE)).toBeNull();
      expect(screen.queryAllByRole('article')).toHaveLength(0);
    });
  });
});
