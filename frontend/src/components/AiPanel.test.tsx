import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { AiPanel } from './AiPanel';
import { INSTRUCTOR_SUMMARY } from './instructorReportCommentFixtures';

afterEach(cleanup);

const HEADING = 'AI summary — instructor comments';

describe('AiPanel', () => {
  it('labels itself as AI-generated and is reachable as a named region', () => {
    render(
      <AiPanel
        heading={HEADING}
        text={INSTRUCTOR_SUMMARY.text}
        responseCount={INSTRUCTOR_SUMMARY.responseCount}
        heldNote={INSTRUCTOR_SUMMARY.heldNote}
      />,
    );

    // The brief's one consistent AI-provenance treatment: the small mono "AI"
    // label, so a reader never mistakes a model's prose for a colleague's.
    expect(screen.getByText('AI')).toBeTruthy();
    expect(screen.getByRole('region', { name: HEADING })).toBeTruthy();
    expect(screen.getByText(INSTRUCTOR_SUMMARY.text)).toBeTruthy();
  });

  it('states the response count it was given', () => {
    render(
      <AiPanel
        heading={HEADING}
        text={INSTRUCTOR_SUMMARY.text}
        responseCount={13}
        heldNote={null}
      />,
    );

    // SPEC §5.1: a summary states the count it draws from, and ADR 0148 makes
    // that number the caller's rather than the model's. Thirteen responses, and
    // three comments in the fixture beside it — the two counts differ on
    // purpose (§3.2 makes a comment optional), so a panel deriving the number
    // from a list could not produce this.
    expect(screen.getByText('Drawn from 13 responses')).toBeTruthy();
  });

  it('states a different count when it is given one', () => {
    render(<AiPanel heading={HEADING} text={INSTRUCTOR_SUMMARY.text} responseCount={3} heldNote={null} />);

    expect(screen.getByText('Drawn from 3 responses')).toBeTruthy();
  });

  it('writes a week of one response in the singular', () => {
    render(<AiPanel heading={HEADING} text={INSTRUCTOR_SUMMARY.text} responseCount={1} heldNote={null} />);

    expect(screen.getByText('Drawn from 1 response')).toBeTruthy();
    expect(screen.queryByText('Drawn from 1 responses')).toBeNull();
  });

  describe('the held-note slot', () => {
    it('is absent when the payload holds no note', () => {
      render(
        <AiPanel
          heading={HEADING}
          text={INSTRUCTOR_SUMMARY.text}
          responseCount={INSTRUCTOR_SUMMARY.responseCount}
          heldNote={null}
        />,
      );

      // The positive control for the absence: the panel rendered, so "no note"
      // is a fact about this panel rather than about an empty document.
      expect(screen.getByText(INSTRUCTOR_SUMMARY.text)).toBeTruthy();
      expect(screen.queryByText(/held for review/)).toBeNull();
    });

    it('renders the note, with its type, when the payload populates it', () => {
      render(
        <AiPanel heading={HEADING} text={INSTRUCTOR_SUMMARY.text} responseCount={13} heldNote="privacy" />,
      );

      // §5.1 allows the note "with type only" above small-N. Whether it appears
      // is the payload's decision: this panel renders it exactly when it is
      // given one, and holds no threshold rule of its own.
      expect(screen.getByText('One comment is held for review (privacy).')).toBeTruthy();
    });
  });
});
