import type { JSX } from 'react';

import { copy } from '../copy/studentSurvey';

/** The three states SPEC §7.6 names for this primitive. */
export type CommentState = 'optional' | 'required' | 'bounce';

/**
 * A free-text answer that changes state — SPEC §7.6's
 * `ConditionalTextArea (optional/required/bounce)`.
 *
 * One component with three variants rather than three components, which is what
 * §7.6 asks for and what keeps the three states looking like one control that
 * changed rather than three controls that resemble each other.
 *
 * **`optional`** carries §3.3's own instruction to say so: "optional-state helper
 * copy notes that written feedback counts toward full participation credit."
 *
 * **`required`** is §3.2's conditional rule showing itself — the rule is read off
 * the question row, never from a copy of it here. The border warms to marigold
 * and the helper line slides down, 180ms, per `docs/DESIGN_BRIEF.md`: *marigold,
 * not madder*, because a low rating asking for a sentence is an invitation and
 * madder is reserved for "attend to this" (`design/Usage Rules.md` §2). The state
 * is also carried in words and in `aria-required`, not in the colour alone —
 * SPEC §14.2 item 4.
 *
 * **The crossing into `required` is announced, and this component does not do
 * the announcing** (E2-17 item 4). The flag, the helper and `aria-required` all
 * changed silently until then, so a student who was not looking at the screen
 * learned the form had changed under them only by going back. The sentence goes
 * into the form's own live region, which is `StudentWeeklySurvey`'s: the region
 * covers the whole form and this component would open a second one per comment
 * field. Only the crossing *into* required is announced — becoming optional
 * again is a relaxation (the ruling of 2026-09-03), and a sentence saying a
 * comment is needed must not be left standing when it is not.
 *
 * **`bounce`** is §3.3's synchronous gate having refused this comment. The
 * sentence is the server's, verbatim, in the same marigold register and entering
 * the same way: "the field does not shake. Nothing in this product shames." The
 * field is marked `aria-invalid` and points at the coaching with
 * `aria-describedby`, so the reason arrives with the field rather than only
 * above the form.
 */
export function ConditionalTextArea({
  id,
  state,
  required,
  value,
  bounceMessage,
  onChange,
}: {
  /** The textarea's own id; the screen focuses a bounced field by it. */
  readonly id: string;
  readonly state: CommentState;
  /**
   * Whether §3.2's conditional rule makes this comment required right now.
   *
   * Separate from `state`, and it has to be: a comment the classifier bounced
   * may be one the rating beside it never required, and telling an optional
   * field it is "needed to submit" because it was coached is a false statement
   * about what the form will accept.
   */
  readonly required: boolean;
  readonly value: string;
  /** SPEC §3.3's coaching sentence, as the server sent it. Only on `bounce`. */
  readonly bounceMessage?: string;
  readonly onChange: (value: string) => void;
}): JSX.Element {
  const helpId = `${id}-help`;
  return (
    <div className="pulse-comment" data-state={state} data-required={required}>
      <label htmlFor={id}>
        {copy('student_survey.comment_label')}
        {required ? (
          <span className="pulse-comment-flag">{copy('student_survey.comment_required_flag')}</span>
        ) : null}
      </label>
      <textarea
        id={id}
        rows={3}
        value={value}
        placeholder={copy('student_survey.comment_placeholder')}
        aria-required={required}
        aria-invalid={state === 'bounce'}
        aria-describedby={helpId}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
      <p className="pulse-comment-help" id={helpId}>
        {helpText(state, bounceMessage)}
      </p>
    </div>
  );
}

/**
 * What sits under the box in each state.
 *
 * The bounce's words are the server's and the other two are this surface's — the
 * split SPEC §4.1's copy inventory is built on. A bounce with no sentence falls
 * back to the required-state helper rather than to an empty line, so a field
 * marked invalid always says something about why.
 */
function helpText(state: CommentState, bounceMessage: string | undefined): string {
  if (state === 'bounce' && bounceMessage !== undefined && bounceMessage !== '') {
    return bounceMessage;
  }
  if (state === 'optional') return copy('student_survey.comment_optional_help');
  return copy('student_survey.comment_required_help');
}
