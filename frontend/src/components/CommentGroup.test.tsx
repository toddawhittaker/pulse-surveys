import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

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
const SMALL_N_TITLE = 'No raw comments are shown here this week';
const HELD_NOTE = 'One comment is held for review (privacy).';
/** The line that stands where the panel would have been (E4-11). */
const ABSENT_SUMMARY = 'No summary was written for this week.';

/**
 * A summary whose payload carries a held note — the sentence SPEC §5.1 allows a
 * summary to add "above small-N", "with type only". No E4 path populates one
 * (E6 writes the moderation states behind them), so it is written here rather
 * than in the shared fixtures: what a week with a held note looks like is this
 * pair of tests' concern.
 */
const SUMMARY_WITH_HELD_NOTE = { ...SMALL_N_SUMMARY, heldNote: 'privacy' };

describe('CommentGroup', () => {
  it('leads with the stream summary and follows it with the comments, in the order given', () => {
    render(
      <CommentGroup
        stream="instructor"
        summary={INSTRUCTOR_SUMMARY}
        comments={INSTRUCTOR_COMMENTS}
        suppressed={false}
        threshold={SMALL_N_THRESHOLD}
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
    render(<CommentGroup
        stream="course"
        summary={COURSE_SUMMARY}
        comments={COURSE_COMMENTS}
        suppressed={false}
        threshold={SMALL_N_THRESHOLD}
      />);

    expect(screen.getByRole('heading', { name: 'About the course' })).toBeTruthy();
    expect(screen.getByRole('region', { name: 'AI summary — course comments' })).toBeTruthy();
    expect(screen.getAllByRole('article')).toHaveLength(COURSE_COMMENTS.length);
  });

  describe('a week that produced no comments', () => {
    it('keeps its heading and its summary and states the fact in one line', () => {
      render(
        <CommentGroup
          stream="instructor"
          summary={INSTRUCTOR_SUMMARY}
          comments={[]}
          suppressed={false}
          threshold={SMALL_N_THRESHOLD}
        />,
      );

      // §5.1: "empty groups show a one-line notice, not a hidden heading."
      expect(screen.getByRole('heading', { name: 'About the instructor' })).toBeTruthy();
      expect(screen.getByRole('region', { name: 'AI summary — instructor comments' })).toBeTruthy();
      expect(screen.getByText(EMPTY_NOTICE)).toBeTruthy();
      expect(screen.queryAllByRole('article')).toHaveLength(0);
    });

    it('does not tell the instructor the comments are being withheld', () => {
      render(
        <CommentGroup
          stream="instructor"
          summary={INSTRUCTOR_SUMMARY}
          comments={[]}
          suppressed={false}
          threshold={SMALL_N_THRESHOLD}
        />,
      );

      // The empty group and the suppressed group are different facts about the
      // class, and the copy for one must never stand in for the other.
      expect(screen.getByText(EMPTY_NOTICE)).toBeTruthy();
      expect(screen.queryByText(SMALL_N_TITLE)).toBeNull();
      expect(screen.queryByText(/raw comments in this group are shown only/)).toBeNull();
    });
  });

  describe('a week no summary was written for', () => {
    it('says so where the panel would have been, and renders the cards intact', () => {
      // E4-11's fifth criterion: "the absent-summary state renders its honest
      // treatment and the rest of the report intact." The comments are the
      // "rest" this component owns, so they are asserted here rather than only
      // on the page.
      //
      // **The mutations this kills.** An `AiPanel` rendered with an empty string
      // in it, which is the brief's provenance treatment wrapped around nothing
      // and reads as a model that had nothing to say. The whole group returning
      // early, which would take the heading and the cards with it. And the
      // empty-week notice standing in for the absence, which is a different fact
      // about the class.
      render(
        <CommentGroup
          stream="instructor"
          summary={null}
          comments={INSTRUCTOR_COMMENTS}
          suppressed={false}
          threshold={SMALL_N_THRESHOLD}
        />,
      );

      expect(screen.getByText(ABSENT_SUMMARY)).toBeTruthy();
      expect(screen.queryByRole('region', { name: 'AI summary — instructor comments' })).toBeNull();

      // The heading and every card, unchanged.
      expect(screen.getByRole('heading', { name: 'About the instructor' })).toBeTruthy();
      expect(screen.getAllByRole('article').map((card) => card.textContent)).toEqual(
        INSTRUCTOR_COMMENTS.map((comment) => comment.text),
      );
      expect(screen.queryByText(EMPTY_NOTICE)).toBeNull();
    });

    it('keeps the concealment when the week is also suppressed', () => {
      // The two absences are independent: E4-06 not having run is not the same
      // fact as the week being under the threshold, and a week can be both. The
      // concealment must survive the summary being gone — otherwise the branch
      // that renders the absence line is a branch that skipped the suppression.
      render(
        <CommentGroup
          stream="instructor"
          summary={null}
          comments={WITHHELD_COMMENTS}
          suppressed
          threshold={SMALL_N_THRESHOLD}
        />,
      );

      // The absence line is the positive control: the group rendered, so the
      // cards being gone is a fact about the suppression rather than about a
      // component that drew nothing.
      expect(screen.getByText(ABSENT_SUMMARY)).toBeTruthy();
      expect(screen.queryAllByRole('article')).toHaveLength(0);
      for (const comment of WITHHELD_COMMENTS) {
        expect(screen.queryByText(comment.text)).toBeNull();
      }
    });
  });

  it('passes the summary’s held note through on a week above the threshold', () => {
    render(
      <CommentGroup
        stream="instructor"
        summary={SUMMARY_WITH_HELD_NOTE}
        comments={INSTRUCTOR_COMMENTS}
        suppressed={false}
        threshold={SMALL_N_THRESHOLD}
      />,
    );

    // The other direction of the assertion below, and the reason it means
    // something: above small-N §5.1 lets the summary say a comment is held, so
    // a group that never rendered the note would pass the concealment test for
    // the wrong reason.
    expect(screen.getByText(HELD_NOTE)).toBeTruthy();
  });

  describe('a stream below the commenter threshold', () => {
    it('keeps the summary and shows no comment at all', () => {
      // The fixture hands a suppressed group a full week of comments on purpose:
      // "no cards rendered" has to be a fact about the suppression rather than
      // about an empty array.
      expect(WITHHELD_COMMENTS).toHaveLength(WITHHELD_COMMENT_COUNT);

      render(
        <CommentGroup
          stream="instructor"
          summary={SMALL_N_SUMMARY}
          comments={WITHHELD_COMMENTS}
          suppressed
          threshold={SMALL_N_THRESHOLD}
        />,
      );

      // §4: below the threshold the instructor sees the summary and no raw
      // comments. The summary is the positive control that makes the empty card
      // list mean suppression rather than a group that failed to render.
      expect(screen.getByRole('region', { name: 'AI summary — instructor comments' })).toBeTruthy();
      expect(screen.getByText(SMALL_N_SUMMARY.text)).toBeTruthy();
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
          suppressed
          threshold={SMALL_N_THRESHOLD}
        />,
      );

      // §5.2: below the threshold there is "no chip, no count, no flag-type
      // hint". Two halves, because a count can hide in either: every number a
      // reader sees, and every number an attribute carries.
      expect(container.textContent).toContain(SMALL_N_SUMMARY.text);

      // The only numbers in the words are the count the summary drew from and
      // the configured threshold the group's notice states (E5.1-01), in that
      // order. Both are the payload's, neither is a count of what was withheld,
      // and the notice states no count of anybody.
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

    it('withholds the summary’s held note, which names a flag type', () => {
      const { container } = render(
        <CommentGroup
          stream="instructor"
          summary={SUMMARY_WITH_HELD_NOTE}
          comments={WITHHELD_COMMENTS}
          suppressed
          threshold={SMALL_N_THRESHOLD}
        />,
      );

      // §5.2's small-N concealment: below the threshold flagged comments are
      // hidden from the instructor entirely — "no chip, no count, no flag-type
      // hint" — and §5.1 permits the held note only above small-N. The note
      // names the type, so a suppressed week rendering it would leak exactly
      // what the concealment exists to withhold. Honouring the suppression the
      // payload already declared is the same fail-closed move the cards make,
      // not a threshold rule invented here.
      //
      // The summary is the positive control: the group did render, so the
      // note's absence is a fact about the concealment rather than about a
      // group that rendered nothing.
      expect(screen.getByText(SMALL_N_SUMMARY.text)).toBeTruthy();
      expect(screen.queryByText(HELD_NOTE)).toBeNull();
      expect(screen.queryByText(/held for review/)).toBeNull();
      // The flag type itself, wherever it might have been written — the
      // sentence is not the only shape a hint could take.
      expect(container.innerHTML).not.toContain('privacy');
    });

    it('states the notice inside the group, after its summary, in either stream', () => {
      const { container } = render(
        <CommentGroup
          stream="course"
          summary={SMALL_N_SUMMARY}
          comments={WITHHELD_COMMENTS}
          suppressed
          threshold={SMALL_N_THRESHOLD}
        />,
      );

      // E5.1-01: the threshold counts distinct commenters per stream (ADR 0182),
      // so a suppressed group states its own notice — one group of a week can be
      // shown while the other is held, and a notice under both would claim both
      // were. The mutation this kills is the notice left to the page, which then
      // shows none for a group the payload says is held. It does not fall back to
      // the empty-week line either, because the stream was not empty.
      const group = container.querySelector('.pulse-comment-group');
      const summary = screen.getByRole('region', { name: 'AI summary — course comments' });
      const notices = screen
        .getAllByText(SMALL_N_TITLE)
        .map((title) => title.parentElement as Element);

      expect(notices).toHaveLength(1);
      const notice = notices[0] as Element;
      expect(group?.contains(notice)).toBe(true);
      expect(
        summary.compareDocumentPosition(notice) & Node.DOCUMENT_POSITION_FOLLOWING,
        'the notice is not after the summary',
      ).toBeTruthy();
      expect(notice.textContent).toContain(`at least ${String(SMALL_N_THRESHOLD)} students`);
      expect(screen.getByText(SMALL_N_SUMMARY.text)).toBeTruthy();
      expect(screen.queryByText(EMPTY_NOTICE)).toBeNull();
      expect(screen.queryAllByRole('article')).toHaveLength(0);
    });

    it('states no notice in a group that is not suppressed', () => {
      // The pair to the test above, so that one is about the suppression and not
      // about a group that always renders a notice.
      render(
        <CommentGroup
          stream="course"
          summary={COURSE_SUMMARY}
          comments={COURSE_COMMENTS}
          suppressed={false}
          threshold={SMALL_N_THRESHOLD}
        />,
      );

      expect(screen.getAllByRole('article')).toHaveLength(COURSE_COMMENTS.length);
      expect(screen.queryByText(SMALL_N_TITLE)).toBeNull();
    });
  });
});

describe('decisions on a group’s comments (SPEC §5.2)', () => {
  const HANDLE = '9a1e2b3c-4d5e-4f60-8a7b-0c1d2e3f4a5b';

  it('binds each card’s decision to that comment’s handle, and offers none without one', () => {
    const decide = vi.fn(() => new Promise<never>(() => undefined));
    render(
      <CommentGroup
        stream="course"
        summary={COURSE_SUMMARY}
        comments={[{ ...COURSE_COMMENTS[0]!, answerId: HANDLE }, COURSE_COMMENTS[1]!]}
        suppressed={false}
        threshold={SMALL_N_THRESHOLD}
        decide={decide}
      />,
    );

    // Both cards rendered; only the one with a handle offers a decision.
    expect(screen.getAllByRole('article')).toHaveLength(2);
    const offered = screen.getAllByRole('button', { name: 'Exclude from student view' });
    expect(offered).toHaveLength(1);

    fireEvent.click(offered[0]!);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Off topic.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Exclude with this reason' }));
    expect(decide).toHaveBeenCalledWith(HANDLE, { action: 'exclude', reason: 'Off topic.' });
  });

  it('offers no decision in a suppressed group, because it renders no card', () => {
    render(
      <CommentGroup
        stream="course"
        summary={COURSE_SUMMARY}
        comments={[{ ...COURSE_COMMENTS[0]!, answerId: HANDLE }]}
        suppressed
        threshold={SMALL_N_THRESHOLD}
        decide={vi.fn()}
      />,
    );

    // The notice is the control: the group rendered, in its suppressed state.
    expect(screen.getByText('No raw comments are shown here this week')).toBeTruthy();
    expect(screen.queryAllByRole('article')).toHaveLength(0);
    expect(screen.queryByRole('button', { name: 'Exclude from student view' })).toBeNull();
  });
});
