import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';

import {
  CommentCard,
  type CommentDecision,
  type DecisionAnswer,
  type ReportComment,
} from './CommentCard';
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
    // No moderation controls without `decide`: a card the caller cannot send a
    // decision for offers none (SPEC §5.2's controls are tested below).
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
    // Without `decide` there is no Undo, nor any other control.
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

/** The exclusion notice, as SPEC §5.2's excluded state words it. */
const EXCLUDED_NOTICE =
  'Excluded — students will not see this comment. The exclusion is logged and visible to the Lead Faculty.';

/**
 * A `decide` that answers each call with the next answer given, and records
 * what it was sent — the server's side of a decision, as the card sees it.
 */
function deciding(...answers: DecisionAnswer[]) {
  const queue = [...answers];
  return vi.fn((decision: CommentDecision): Promise<DecisionAnswer> => {
    void decision;
    const next = queue.shift();
    if (next === undefined)
      return Promise.reject(new Error('This test answers no more decisions.'));
    return Promise.resolve(next);
  });
}

const decided = (comment: ReportComment): DecisionAnswer => ({
  kind: 'decided',
  comment,
});

describe('CommentCard moderation (SPEC §5.2)', () => {
  it('offers Keep and Exclude on a flagged comment once it is opened, and Undo restores it', async () => {
    const decide = deciding(
      decided({ ...FLAGGED_COMMENT, status: 'kept', decidedByYou: true }),
      decided({ ...FLAGGED_COMMENT, decidedByYou: false }),
    );
    render(<CommentCard {...FLAGGED_COMMENT} decide={decide} />);

    fireEvent.click(screen.getByRole('button', { name: 'Review comment' }));
    fireEvent.click(screen.getByRole('button', { name: 'Keep for students' }));

    expect(await screen.findByText('You kept this comment for students.')).toBeTruthy();
    expect(screen.getByText(FLAGGED_COMMENT.text)).toBeTruthy();
    expect(screen.queryByText('Flagged: privacy')).toBeNull();
    expect(decide).toHaveBeenLastCalledWith({ action: 'keep', reason: null });

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));

    expect(await screen.findByText('Flagged: privacy')).toBeTruthy();
    expect(decide).toHaveBeenLastCalledWith({ action: 'undo', reason: null });
    expect(screen.queryByText('You kept this comment for students.')).toBeNull();
    // The restored card is collapsed again: its words are out of the DOM.
    expect(screen.queryByText(FLAGGED_COMMENT.text)).toBeNull();
  });

  it('excludes a flagged comment without asking for a reason, muting its text above the notice', async () => {
    const decide = deciding(
      decided({ ...FLAGGED_COMMENT, status: 'excluded', decidedByYou: true }),
      decided({ ...FLAGGED_COMMENT, decidedByYou: false }),
    );
    render(<CommentCard {...FLAGGED_COMMENT} decide={decide} />);

    fireEvent.click(screen.getByRole('button', { name: 'Review comment' }));
    fireEvent.click(screen.getByRole('button', { name: 'Exclude from student view' }));

    const notice = await screen.findByText(EXCLUDED_NOTICE);
    const text = screen.getByText(FLAGGED_COMMENT.text);
    expect(decide).toHaveBeenLastCalledWith({
      action: 'exclude',
      reason: null,
    });
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(text.className).toContain('pulse-comment-card__text--muted');
    expect(text.compareDocumentPosition(notice) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(await screen.findByText('Flagged: privacy')).toBeTruthy();
    expect(screen.queryByText(EXCLUDED_NOTICE)).toBeNull();
  });

  it('offers Undo only on the reader’s own decision', () => {
    render(
      <>
        <CommentCard {...EXCLUDED_COMMENT} decidedByYou={false} decide={deciding()} />
        <CommentCard
          {...PUBLISHED_COMMENT}
          status="kept"
          decidedByYou={false}
          decide={deciding()}
        />
      </>,
    );

    // Both cards rendered their decided states: these are the controls for the
    // absence of Undo below.
    expect(screen.getByText(EXCLUDED_NOTICE)).toBeTruthy();
    expect(screen.getByText('Kept after review.')).toBeTruthy();
    expect(screen.queryByText('You kept this comment for students.')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Undo' })).toBeNull();
  });

  it('keeps the earlier card and shows the server’s sentence when a decision is refused', async () => {
    const refusal =
      'That decision does not apply to this comment as it stands, so nothing was changed.';
    const decide = deciding({ kind: 'refused', detail: refusal });
    render(<CommentCard {...FLAGGED_COMMENT} decide={decide} />);

    fireEvent.click(screen.getByRole('button', { name: 'Review comment' }));
    fireEvent.click(screen.getByRole('button', { name: 'Keep for students' }));

    expect((await screen.findByRole('alert')).textContent).toBe(refusal);
    expect(screen.getByText('Flagged: privacy')).toBeTruthy();
    expect(screen.getByText(FLAGGED_COMMENT.text)).toBeTruthy();
  });

  describe('the stated reason for excluding an unflagged comment', () => {
    it('asks for a reason, and sends nothing while the field holds no words', () => {
      const decide = deciding();
      render(<CommentCard {...PUBLISHED_COMMENT} decide={decide} />);

      fireEvent.click(screen.getByRole('button', { name: 'Exclude from student view' }));

      const field = screen.getByRole('textbox', {
        name: 'Why should students not see this comment?',
      });
      const submit = screen.getByRole('button', {
        name: 'Exclude with this reason',
      });
      expect(field.getAttribute('maxlength')).toBe('500');
      expect(screen.getByText('500 characters left')).toBeTruthy();
      expect((submit as HTMLButtonElement).disabled).toBe(true);

      fireEvent.change(field, { target: { value: '   ' } });
      expect((submit as HTMLButtonElement).disabled).toBe(true);
      fireEvent.submit(field.closest('form') as HTMLFormElement);
      expect(decide).not.toHaveBeenCalled();
    });

    it('sends the reason as typed and shows the server’s refusal under the field', async () => {
      const refusal = 'A stated reason can be at most 500 characters long. Nothing was changed.';
      const decide = deciding({ kind: 'refused', detail: refusal });
      render(<CommentCard {...PUBLISHED_COMMENT} decide={decide} />);

      fireEvent.click(screen.getByRole('button', { name: 'Exclude from student view' }));
      const field = screen.getByRole('textbox');
      fireEvent.change(field, { target: { value: 'Names a classmate.' } });
      expect(screen.getByText('482 characters left')).toBeTruthy();
      fireEvent.click(screen.getByRole('button', { name: 'Exclude with this reason' }));

      const alert = await screen.findByRole('alert');
      expect(alert.textContent).toBe(refusal);
      expect(decide).toHaveBeenCalledWith({
        action: 'exclude',
        reason: 'Names a classmate.',
      });
      // Inline under the field: inside the prompt, after the textarea.
      const form = field.closest('form') as HTMLFormElement;
      expect(within(form).getByRole('alert')).toBe(alert);
      expect(field.compareDocumentPosition(alert) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      expect(screen.getByText(PUBLISHED_COMMENT.text).className).not.toContain('--muted');
    });

    it('excludes with the reason once the server accepts it', async () => {
      const decide = deciding(
        decided({
          ...PUBLISHED_COMMENT,
          status: 'excluded',
          decidedByYou: true,
        }),
      );
      render(<CommentCard {...PUBLISHED_COMMENT} decide={decide} />);

      fireEvent.click(screen.getByRole('button', { name: 'Exclude from student view' }));
      fireEvent.change(screen.getByRole('textbox'), {
        target: { value: 'Off topic.' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Exclude with this reason' }));

      expect(await screen.findByText(EXCLUDED_NOTICE)).toBeTruthy();
      expect(screen.queryByRole('textbox')).toBeNull();
      expect(screen.getByRole('button', { name: 'Undo' })).toBeTruthy();
    });
  });

  it('shows no date, no time and no name in any decided state', () => {
    const { container } = render(
      <>
        <CommentCard {...FLAGGED_COMMENT} decide={deciding()} />
        <CommentCard {...EXCLUDED_COMMENT} decidedByYou decide={deciding()} />
        <CommentCard {...EXCLUDED_COMMENT} decidedByYou={false} decide={deciding()} />
        <CommentCard {...PUBLISHED_COMMENT} status="kept" decidedByYou decide={deciding()} />
        <CommentCard
          {...PUBLISHED_COMMENT}
          status="kept"
          decidedByYou={false}
          decide={deciding()}
        />
        <CommentCard {...PUBLISHED_COMMENT} decide={deciding()} />
      </>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Review comment' }));

    // Non-emptiness first: every card rendered, and its decided state with it,
    // so the absences below are about a full page and not an empty one.
    expect(screen.getAllByRole('article')).toHaveLength(6);
    expect(screen.getAllByText(EXCLUDED_NOTICE)).toHaveLength(2);
    expect(screen.getByText('You kept this comment for students.')).toBeTruthy();
    expect(screen.getByText('Kept after review.')).toBeTruthy();

    // The patterns below are proven on a sample of what each refuses first,
    // so a pattern gone blind fails here rather than passing everything.
    const sample = 'Kept by Dana on October 5 2026 at 9:14';
    expect(sample).toMatch(/\b(19|20)\d{2}\b/);
    expect(sample).toMatch(/\d{1,2}:\d{2}/);
    expect(sample).toMatch(/\b(October)\b/);
    expect(sample).toMatch(/\b(by|Decided by) [A-Z]/);

    const shown = container.textContent;
    expect(container.querySelector('time, [datetime]')).toBeNull();
    // A year, a clock time, a month name or a decider named by role: none.
    expect(shown).not.toMatch(/\b(19|20)\d{2}\b/);
    expect(shown).not.toMatch(/\d{1,2}:\d{2}/);
    expect(shown).not.toMatch(
      /\b(January|February|March|April|May|June|July|August|September|October|November|December)\b/,
    );
    expect(shown).not.toMatch(/\b(by|Decided by) [A-Z]/);
  });
});
