import type { JSX } from 'react';

import { copy } from '../copy/studentSurvey';

/**
 * The submit action and the confidentiality line — SPEC §7.6's `SubmitBar`.
 *
 * **SPEC §4.1 item 5 is the whole reason the sentence lives here**: "confidentiality
 * copy appears exactly once per surface (survey: in the submit bar), in plain
 * words, no shield or lock iconography". So it is in this component and in no
 * other, it is one entry in `../copy/studentSurvey`, and there is no icon
 * anywhere on this screen — the reassurance is carried by what it says, at the
 * moment the student is deciding whether to send.
 *
 * Its placement is also the reason this component renders it rather than the
 * screen: a submit bar that could be used without the sentence is a submit bar
 * somebody will eventually use without it.
 *
 * **A reader enrolled in two open sections answers two surveys and meets the
 * sentence once in each.** "Once per surface" is read as once per survey being
 * submitted, which is what the design's own single-course screen shows and what
 * makes the line mean anything where the student is about to act. There is still
 * exactly one wording of it, in one entry, which is the form the inventory reads.
 *
 * The resubmit note is separate and optional: SPEC §3.1 lets a week be revised
 * while its window is open, and the note says so where the decision is made. It
 * quotes no deadline — the window's own close is in the eyebrow above, from the
 * API, and a second statement of it here would be a copy to keep in step.
 */
export function SubmitBar({
  label,
  disabled,
  busy,
  showResubmitNote,
  onSubmit,
}: {
  readonly label: string;
  readonly disabled: boolean;
  readonly busy: boolean;
  readonly showResubmitNote: boolean;
  readonly onSubmit: () => void;
}): JSX.Element {
  return (
    <div className="pulse-submit-bar">
      <button type="button" className="pulse-submit" disabled={disabled} onClick={onSubmit}>
        {busy ? copy('student_survey.submitting') : label}
      </button>
      <p className="pulse-confidentiality">{copy('student_survey.confidentiality')}</p>
      {showResubmitNote ? (
        <p className="pulse-submit-note">{copy('student_survey.submit_again_note')}</p>
      ) : null}
    </div>
  );
}
