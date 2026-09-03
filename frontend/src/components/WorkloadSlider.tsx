import type { JSX } from 'react';

import type { SurveyQuestion } from '../api/student';
import { copy, fillCopy } from '../copy/studentSurvey';

/** The keys that move a range input, so a keyboard alone can answer it. */
const ADJUSTMENT_KEYS = new Set([
  'ArrowUp',
  'ArrowDown',
  'ArrowLeft',
  'ArrowRight',
  'Home',
  'End',
  'PageUp',
  'PageDown',
]);

/**
 * SPEC §3.2's fifth question — SPEC §7.6's `WorkloadSlider`.
 *
 * §3.2: "hours spent on this course this week, numeric entry via a slider with a
 * live numeric readout (range 0-40, 0.5-hour steps; keyboard-adjustable and
 * screen-reader-labeled for accessibility)". **All three numbers come off the
 * question row** — ADR 0110 makes those columns "the only statement of the
 * ranges in the system", and a slider carrying its own copy of 0, 40 and 0.5
 * would be a second one that disagrees with the write path's check the moment a
 * set is versioned.
 *
 * **The value is carried as a string, all the way to the wire.** The column is a
 * decimal and pydantic writes a decimal to JSON as a string; half an hour is
 * exactly half an hour, and the write path checks `(value - minimum) % step`
 * against a `Decimal`. A float round-tripped through JavaScript is how an answer
 * lands between two steps and is refused for a reason nobody can see.
 *
 * **Unanswered is a state, not zero.** A slider that started at the minimum and
 * read "0.0 h" would submit a figure the student never chose, on the question
 * §5.1 reports a median of. So the readout says so until the control is moved,
 * and moving it includes pressing an adjustment key at an end where the value
 * does not change — otherwise a student who means zero hours could never say it
 * from the keyboard.
 *
 * **The track names the token it is drawn from** (`data-pulse-track-token`,
 * E2-17 item 3). The track lives in a pseudo-element, which cannot carry an
 * attribute, so it rides the input — the only node here that can hold one. It
 * measured 1.30:1 against the card before this ticket, which is a design-fidelity
 * fix rather than a WCAG failure: a track is not the control's boundary and the
 * thumb, which is, reads at 12.45:1. The colour is `styles.css`'s; nothing here
 * holds one.
 */

/** The custom property the track is drawn from, published for the spec. */
const TRACK_TOKEN = '--mist';
export function WorkloadSlider({
  question,
  id,
  value,
  onChange,
}: {
  readonly question: SurveyQuestion;
  readonly id: string;
  /** The chosen value as it will be submitted, or `null` when unanswered. */
  readonly value: string | null;
  readonly onChange: (value: string) => void;
}): JSX.Element {
  const minimum = Number(question.minimum_value);
  const maximum = Number(question.maximum_value);
  const step = Number(question.step);
  const places = decimalPlaces(question.step);

  const label = copy('student_survey.workload_label');
  const unit = copy('student_survey.workload_unit');
  const readout = value === null ? copy('student_survey.workload_unanswered') : `${value} ${unit}`;
  // The scale's ends and the spoken hint drop trailing zeros — "0 to 40 hours,
  // in steps of 0.5" rather than "0.0 to 40.0". The *readout* keeps the step's
  // precision, because that number changes under the thumb and a digit that
  // comes and goes moves everything beside it.
  const rangeHint = fillCopy('student_survey.workload_range_hint', {
    minimum: plain(minimum),
    maximum: plain(maximum),
    step: plain(step),
  });

  return (
    <div className="pulse-workload">
      <div className="pulse-workload-head">
        <label htmlFor={id}>{label}</label>
        {/* The live numeric readout §3.2 asks for. `aria-hidden`, because the
            same value reaches a screen reader through the slider's own
            `aria-valuetext` — announcing it twice on every arrow key is noise. */}
        <output className="pulse-workload-readout" htmlFor={id} aria-hidden="true">
          {readout}
        </output>
      </div>
      <input
        id={id}
        className="pulse-workload-range"
        type="range"
        min={minimum}
        max={maximum}
        step={step}
        value={value ?? String(minimum)}
        aria-describedby={`${id}-hint`}
        aria-valuetext={readout}
        data-pulse-track-token={TRACK_TOKEN}
        onChange={(event) => {
          onChange(format(Number(event.target.value), places));
        }}
        onKeyDown={(event) => {
          // A student who means the minimum has to be able to say so. At an end
          // of the range the browser fires no change event, so the first
          // adjustment key is what commits the value the thumb is already on.
          if (value === null && ADJUSTMENT_KEYS.has(event.key)) {
            onChange(format(minimum, places));
          }
        }}
      />
      <div className="pulse-workload-ends" id={`${id}-hint`}>
        <span>{`${plain(minimum)} ${unit}`}</span>
        <span className="pulse-workload-hint">{rangeHint}</span>
        <span>{`${plain(maximum)} ${unit}`}</span>
      </div>
    </div>
  );
}

/**
 * How many decimal places the question's step is written to.
 *
 * The step is what decides the precision of every number this control shows and
 * submits: a half-hour step is written to one place, an hour step to none. Read
 * off the served spelling rather than guessed at, so a set that steps in
 * quarter-hours renders and submits two places without anything here changing.
 */
function decimalPlaces(step: string | null): number {
  const fraction = (step ?? '').split('.')[1];
  return fraction === undefined ? 0 : fraction.replace(/0+$/, '').length;
}

/** One number in the question's own precision. */
function format(value: number, places: number): string {
  return Number.isFinite(value) ? value.toFixed(places) : '';
}

/** One number as it is written in prose: no trailing zeros. */
function plain(value: number): string {
  return Number.isFinite(value) ? String(value) : '';
}
