import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import { CommentCard } from './CommentCard';
import {
  EXCLUDED_COMMENT,
  FLAGGED_COMMENT,
  PUBLISHED_COMMENT,
} from './instructorReportCommentFixtures';

// `globals` is off (ADR 0151), so React Testing Library cannot register its own
// cleanup: nothing has told it there is an `afterEach` to register with. Without
// this, every render in this file stays in the document and the next query in
// the next test finds two of everything.
afterEach(cleanup);

describe('CommentCard', () => {
  it('renders a published comment as the words a student wrote, and nothing else', () => {
    const { container } = render(
      <CommentCard text={PUBLISHED_COMMENT.text} status={PUBLISHED_COMMENT.status} />,
    );

    expect(screen.getByText(PUBLISHED_COMMENT.text)).toBeTruthy();
    expect(screen.getByRole('article')).toBeTruthy();
    // No moderation lifecycle here: the exclude, keep and undo controls of SPEC
    // §5.2 are E6's, and a button offering a decision the backend cannot record
    // would be a promise this ticket cannot keep.
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(container.querySelector('time')).toBeNull();
  });

  it('renders no timestamp in any of its four states', () => {
    // §4: "Comment display order is randomized; timestamps are never shown with
    // comments." The four states of §7.6, one after another, in one document.
    const { container } = render(
      <>
        <CommentCard text={PUBLISHED_COMMENT.text} status={PUBLISHED_COMMENT.status} />
        <CommentCard
          text={FLAGGED_COMMENT.text}
          status={FLAGGED_COMMENT.status}
          flagReason={FLAGGED_COMMENT.flagReason}
        />
        <CommentCard text={EXCLUDED_COMMENT.text} status={EXCLUDED_COMMENT.status} />
      </>,
    );

    // The flagged card's third state — expanded — is reached by its disclosure,
    // so it is opened here rather than passed in: expanding is UI state.
    fireEvent.click(screen.getByRole('button', { name: 'Review comment' }));

    // Non-emptiness first: an assertion that no timestamp is rendered means
    // nothing over a document that rendered nothing at all.
    expect(screen.getAllByRole('article')).toHaveLength(3);
    expect(screen.getByRole('button', { name: 'Collapse' })).toBeTruthy();
    expect(container.querySelector('time')).toBeNull();
    expect(container.querySelector('[datetime]')).toBeNull();
  });

  it('has no prop through which a timestamp or an author could arrive', () => {
    // This is the assertion, and it is made by the compiler rather than by the
    // DOM: SPEC §4 keeps identity off every instructor surface and timestamps
    // off every comment, and the guarantee here is that there is nowhere to put
    // either. `npm run typecheck` fails if either directive below stops being
    // needed — which is what would happen the moment such a prop was added.
    const { container } = render(
      <>
        {/* @ts-expect-error — a comment card takes no timestamp (SPEC §4). */}
        <CommentCard text={PUBLISHED_COMMENT.text} status="published" submittedAt="2026-09-07" />
        {/* @ts-expect-error — a comment card takes no author (SPEC §4). */}
        <CommentCard text={PUBLISHED_COMMENT.text} status="published" authorName="Dana Okoye" />
      </>,
    );

    expect(screen.getAllByRole('article')).toHaveLength(2);
    expect(container.textContent).not.toContain('2026');
    expect(container.textContent).not.toContain('Dana Okoye');
  });

  describe('the flagged states', () => {
    it('starts collapsed, with the chip and its reason and no comment text', () => {
      const { container } = render(
        <CommentCard
          text={FLAGGED_COMMENT.text}
          status={FLAGGED_COMMENT.status}
          flagReason={FLAGGED_COMMENT.flagReason}
        />,
      );

      // The chip and the procedural line are the positive controls for the
      // absence below: they prove the card rendered its flagged state.
      expect(screen.getByText('Flagged: privacy')).toBeTruthy();
      expect(screen.getByText('Hidden from students pending your review')).toBeTruthy();
      expect(screen.getByRole('button').getAttribute('aria-expanded')).toBe('false');
      expect(screen.queryByText(FLAGGED_COMMENT.text)).toBeNull();
      expect(container.textContent).not.toContain(FLAGGED_COMMENT.text);
    });

    it('opens and closes from the keyboard, showing and hiding the comment', () => {
      render(
        <CommentCard
          text={FLAGGED_COMMENT.text}
          status={FLAGGED_COMMENT.status}
          flagReason={FLAGGED_COMMENT.flagReason}
        />,
      );

      const disclosure = screen.getByRole('button', { name: 'Review comment' });

      // Keyboard operability rests on this being a real button: focusable in the
      // tab order, and activated by Enter and Space by the browser itself. jsdom
      // does not synthesize the click a browser raises from Enter, so the key
      // press and the activation are both sent here — the assertion that makes
      // the press meaningful is the one above it, that the control is a native
      // button holding focus, rather than a div with a handler.
      expect(disclosure.tagName).toBe('BUTTON');
      disclosure.focus();
      expect(document.activeElement).toBe(disclosure);

      fireEvent.keyDown(disclosure, { key: 'Enter' });
      fireEvent.click(disclosure);

      expect(screen.getByText(FLAGGED_COMMENT.text)).toBeTruthy();
      expect(screen.getByRole('button').getAttribute('aria-expanded')).toBe('true');
      // The chip stays where it was — the brief keeps it fixed as the eye's
      // anchor while the body opens.
      expect(screen.getByText('Flagged: privacy')).toBeTruthy();

      fireEvent.keyDown(screen.getByRole('button'), { key: 'Enter' });
      fireEvent.click(screen.getByRole('button'));

      expect(screen.queryByText(FLAGGED_COMMENT.text)).toBeNull();
      expect(screen.getByRole('button').getAttribute('aria-expanded')).toBe('false');
    });
  });

  it('renders an excluded comment muted, above its notice, with nothing to press', () => {
    render(<CommentCard text={EXCLUDED_COMMENT.text} status={EXCLUDED_COMMENT.status} />);

    const text = screen.getByText(EXCLUDED_COMMENT.text);
    const notice = screen.getByText(
      'Excluded — students will not see this comment. The exclusion is logged and visible to the Lead Faculty.',
    );

    // §5.2: "Excluded comments keep their text visible to the instructor, muted,
    // above the exclusion notice." Above, in the document's own order — jsdom
    // applies no stylesheet, so the order is read from the tree rather than from
    // a computed position.
    expect(text.className).toContain('pulse-comment-card__text--muted');
    expect(text.compareDocumentPosition(notice) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // Undo is E6's, and so is every other lifecycle control.
    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });

  describe('the optional stream chip', () => {
    it('is off unless a stream is given', () => {
      render(<CommentCard text={PUBLISHED_COMMENT.text} status={PUBLISHED_COMMENT.status} />);

      expect(screen.getByText(PUBLISHED_COMMENT.text)).toBeTruthy();
      expect(screen.queryByText('Instructor')).toBeNull();
      expect(screen.queryByText('Course')).toBeNull();
    });

    it('renders the stream when one is given, which is what makes the default meaningful', () => {
      render(
        <CommentCard
          text={PUBLISHED_COMMENT.text}
          status={PUBLISHED_COMMENT.status}
          stream="instructor"
        />,
      );

      expect(screen.getByText('Instructor')).toBeTruthy();
    });
  });
});
