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
 *
 * **The scale's polarity is spoken as well as drawn** (E2-17 item 2). Verified
 * before that ticket: the ends were a `div` with no id, the group was described
 * by nothing, and every radio's accessible name was a bare digit — so a student
 * using a screen reader was asked to agree or disagree on a scale whose
 * direction was only ever a picture. The ends now carry an id per question
 * instance, the group is `aria-describedby` that element, and the two end radios
 * carry the end words in their names. The middle points stay digits: a scale
 * that named every one of them would be five sentences read on the way past,
 * which is what the group description exists to avoid.
 *
 * **The unchecked dot's ring names the token it is drawn from**
 * (`data-pulse-ring-token`, E2-17 item 3). SC 1.4.11 asks 3:1 of the boundary of
 * a control a person has to find, the ring measured 1.92:1 as rendered, and the
 * attribute is how `tests/e2e/student-survey-accessibility.spec.ts` reads which
 * token the stylesheet chose without this repository's tests choosing the
 * palette. The colour itself is `styles.css`'s; nothing here holds one.
 */

/** The custom property the unchecked ring is drawn from, published for the spec. */
const RING_TOKEN = '--spruce-60';

export function LikertInput({
  question,
  name,
  value,
  onSelect,
}: {
  readonly question: SurveyQuestion;
  /**
   * The radio group's name; unique per section and question.
   *
   * It is also the id of the group's first radio, which is how the screen puts
   * the keyboard on this question when a submission stops at it (E2-17 item 1):
   * a radio group has no element of its own for a caller to focus, and focusing
   * its first point lands inside the group whichever point is chosen.
   */
  readonly name: string;
  /** The chosen value as it will be submitted, or `null` when unanswered. */
  readonly value: string | null;
  readonly onSelect: (value: string) => void;
}): JSX.Element {
  const scale = scaleOf(question);
  const endsId = `${name}-ends`;
  const low = copy('student_survey.likert_low_label');
  const high = copy('student_survey.likert_high_label');
  return (
    <fieldset className="pulse-likert" aria-describedby={endsId}>
      <legend>{question.prompt}</legend>
      <div className="pulse-likert-scale">
        {scale.map((point, at) => (
          <label className="pulse-likert-point" key={point}>
            {/* The dot *is* the input — `appearance: none` and a border, rather
                than a hidden control beside a styled span. The focus ring, the
                arrow keys and the announced position in the group are then the
                platform's rather than something this file reimplements. */}
            <input
              type="radio"
              id={at === 0 ? name : undefined}
              name={name}
              value={point}
              checked={value === point}
              aria-label={endWordsFor(point, at, scale.length, low, high)}
              data-pulse-ring-token={RING_TOKEN}
              onChange={() => {
                onSelect(point);
              }}
            />
            <span className="pulse-likert-value">{point}</span>
          </label>
        ))}
      </div>
      <div className="pulse-likert-ends" id={endsId}>
        <span>{low}</span>
        <span>{high}</span>
      </div>
    </fieldset>
  );
}

/**
 * What one point is called to a screen reader, when the digit alone is not enough.
 *
 * The two ends carry their words — "1 — Strongly disagree" — and every point
 * between them answers to its digit, which is what the group's description
 * covers. `undefined` rather than the digit for those, so the name keeps coming
 * off the label the person is looking at and there is no second spelling of it
 * to drift.
 */
function endWordsFor(
  point: string,
  at: number,
  points: number,
  low: string,
  high: string,
): string | undefined {
  if (points < 2) return undefined;
  if (at === 0) return `${point} — ${low}`;
  if (at === points - 1) return `${point} — ${high}`;
  return undefined;
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
