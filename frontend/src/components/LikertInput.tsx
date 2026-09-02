import type { JSX } from 'react';

import type { SurveyQuestion } from '../api/student';
import { copy } from '../copy/studentSurvey';

/**
 * One of SPEC §3.2's agreement scales — SPEC §7.6's `LikertInput`.
 *
 * **The wording and the scale are both the question row's.** §3.2 stores the
 * five questions in a versioned table and E2-09's read answer carries each one's
 * `prompt`, `minimum_value`, `maximum_value` and `step`; this component draws
 * whatever that says. A hard-coded "1 to 5" here would be a second statement of
 * the instrument, right until a set is versioned, and a hard-coded sentence
 * would be a second statement of the question itself.
 *
 * **Native radios in a fieldset, not buttons carrying `role="radio"`.** SPEC
 * §14.2 item 4 puts keyboard and screen-reader basics in-slice, and the platform
 * control already has them: one tab stop for the group, arrow keys to move
 * within it, the selected value announced with the legend. The prototype draws
 * the dots with buttons; what it is drawing is a radio group, and the input is
 * what the browser is told it is while the span beside it is what a person sees.
 *
 * The chosen dot beats once — 180ms, the pulse motif at fingertip scale
 * (`design/Usage Rules.md` §3). `design/tokens.css` removes it under
 * `prefers-reduced-motion`, and nothing here animates in JavaScript, so there is
 * no motion that can escape that switch.
 */
export function LikertInput({
  question,
  name,
  value,
  onSelect,
}: {
  readonly question: SurveyQuestion;
  /** The radio group's name; unique per section and question. */
  readonly name: string;
  /** The chosen value as it will be submitted, or `null` when unanswered. */
  readonly value: string | null;
  readonly onSelect: (value: string) => void;
}): JSX.Element {
  const scale = scaleOf(question);
  return (
    <fieldset className="pulse-likert">
      <legend>{question.prompt}</legend>
      <div className="pulse-likert-scale">
        {scale.map((point) => (
          <label className="pulse-likert-point" key={point}>
            {/* The dot *is* the input — `appearance: none` and a border, rather
                than a hidden control beside a styled span. The focus ring, the
                arrow keys and the announced position in the group are then the
                platform's rather than something this file reimplements. */}
            <input
              type="radio"
              name={name}
              value={point}
              checked={value === point}
              onChange={() => {
                onSelect(point);
              }}
            />
            <span className="pulse-likert-value">{point}</span>
          </label>
        ))}
      </div>
      <div className="pulse-likert-ends">
        <span>{copy('student_survey.likert_low_label')}</span>
        <span>{copy('student_survey.likert_high_label')}</span>
      </div>
    </fieldset>
  );
}

/**
 * How many points this question's scale has, in the spelling they are submitted
 * in.
 *
 * A question carrying no bounds names no scale, and this answers with none
 * rather than falling back to five: falling back would draw a scale the server
 * will refuse and would hide the fact that the question row is incomplete. The
 * iteration is bounded on the step's sign as well as on the maximum, because a
 * zero or negative step is a row that would otherwise loop forever.
 */
function scaleOf(question: SurveyQuestion): string[] {
  const minimum = Number(question.minimum_value);
  const maximum = Number(question.maximum_value);
  const step = Number(question.step);
  if (!Number.isFinite(minimum) || !Number.isFinite(maximum) || !Number.isFinite(step)) return [];
  if (step <= 0 || maximum < minimum) return [];

  const points: string[] = [];
  for (let point = minimum; point <= maximum; point += step) {
    points.push(String(point));
  }
  return points;
}
