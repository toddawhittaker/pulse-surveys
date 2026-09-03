import type { JSX } from 'react';

import { copy } from '../copy/studentSurvey';

/**
 * The submit action and what stands with it — SPEC §7.6's `SubmitBar`.
 *
 * **SPEC §4.1 item 5 is why the confidentiality sentence is here**:
 * "confidentiality copy appears exactly once per surface (survey: once per
 * screen, in the submit area), in plain words, no shield or lock iconography".
 * So it is in this component and in no other, it is one entry in
 * `../copy/studentSurvey`, and there is no icon anywhere on this screen — the
 * reassurance is carried by what it says, at the moment the student is deciding
 * whether to send.
 *
 * **A screen is one screen however many courses are on it, and that is E2-17's
 * correction.** This component rendered the sentence unconditionally until then,
 * on the reading that "once per surface" meant once per survey being submitted —
 * so a student enrolled in two courses whose windows were open at the same
 * minute met it twice on one screen. The ruling of 2026-09-03 settles the other
 * reading, and the count is not a decision a per-section component can take: the
 * screen decides which submit area carries the sentence and says so with
 * `showConfidentiality`. There is still exactly one wording of it, in one entry,
 * which is the form the copy inventory reads.
 *
 * **The button is never disabled.** It carried `disabled` until every
 * non-comment question was answered, which took it out of the tab order
 * entirely: a student using a screen reader tabbed to the end of the form, found
 * nothing to activate, and was told nothing about why (E2-17 item 1, verified
 * against the running stack). It refuses to *send* rather than refusing to
 * exist, and `missingAnswer` is what it says when it does.
 *
 * **That sentence is a live region and it is in the document from the first
 * render**, empty until there is something to say. A region added at the moment
 * it has content is a region assistive technology has not been watching, which
 * is the same defect E2-17 item 8 removes from the form's other announcement.
 * It is also the button's `aria-describedby`, so it is read when the button
 * takes focus as well as announced when it arrives.
 *
 * The resubmit note is separate and optional: SPEC §3.1 lets a week be revised
 * while its window is open, and the note says so where the decision is made. It
 * quotes no deadline — the window's own close is in the eyebrow above, from the
 * API, and a second statement of it here would be a copy to keep in step.
 */

/**
 * Where a spec finds the action. The label changes between a first submission
 * and a revision, so addressing the button by its words would be a spec holding
 * a copy of two governed strings in order to click one thing.
 */
export const SUBMIT_TESTID = 'survey-submit';

export function SubmitBar({
  label,
  busy,
  missingAnswer,
  missingAnswerId,
  showConfidentiality,
  showResubmitNote,
  onSubmit,
}: {
  readonly label: string;
  readonly busy: boolean;
  /** Why this week cannot be sent yet, or an empty string when it can. */
  readonly missingAnswer: string;
  /** The id that sentence is reached by, from the button's `aria-describedby`. */
  readonly missingAnswerId: string;
  /**
   * Whether this submit area is the one carrying the confidentiality sentence.
   *
   * The screen decides, because §4.1 item 5 counts per screen and a section
   * cannot see the others. See this module's docstring.
   */
  readonly showConfidentiality: boolean;
  readonly showResubmitNote: boolean;
  readonly onSubmit: () => void;
}): JSX.Element {
  return (
    <div className="pulse-submit-bar">
      <button
        type="button"
        className="pulse-submit"
        data-testid={SUBMIT_TESTID}
        aria-describedby={missingAnswerId}
        onClick={onSubmit}
      >
        {busy ? copy('student_survey.submitting') : label}
      </button>
      <p className="pulse-submit-missing" id={missingAnswerId} role="status" aria-live="polite">
        {missingAnswer}
      </p>
      {showConfidentiality ? (
        <p className="pulse-confidentiality">{copy('student_survey.confidentiality')}</p>
      ) : null}
      {showResubmitNote ? (
        <p className="pulse-submit-note">{copy('student_survey.submit_again_note')}</p>
      ) : null}
    </div>
  );
}
