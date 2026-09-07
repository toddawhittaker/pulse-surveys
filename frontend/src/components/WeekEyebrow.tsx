import type { JSX } from 'react';

import { copy, fillCopy } from '../copy/studentSurvey';

/**
 * The mono week eyebrow — SPEC §7.6's `WeekEyebrow`, one component with variants.
 *
 * `docs/DESIGN_BRIEF.md` makes this the first thing on every student and
 * instructor screen: "the term's rhythm is the product's spine, so the layout
 * states it before anything else". `design/Usage Rules.md` §1 settles which week
 * a course-level page counts in — "course week … with a quiet term-week
 * sub-label" — and SPEC §2.2 is why both travel: a 15-week section that began in
 * the term's fourth week is in its tenth week when the term is in its
 * thirteenth, and showing one in the other's place tells a student they are
 * three weeks further through their course than they are.
 *
 * **All three numbers and the closing instant are the API's** (`OpenSurvey`),
 * never derived here. The close is rendered in the reader's own timezone,
 * because the instant is absolute and the person reading it is the one who has
 * to be there before it.
 *
 * **Each axis is named in words** — "COURSE WK 04 / 12, TERM WK 07" — which is
 * the owner's ruling of 2026-09-03 (FIX-01 item 1), made after "TERM 03" had to
 * be explained to them. Both labels are governed copy filled with the API's
 * numbers, comma included, so nothing a reader sees is assembled here.
 *
 * **The brief's "WK 07 / 12" — how many weeks the section runs for — is
 * `lengthWeeks`, and it comes off the read answer** (`OpenSurvey.length_weeks`,
 * the `length_weeks` column of the section the window belongs to). It is a
 * required prop rather than an optional one, so a screen that has no total to
 * show fails to compile instead of rendering half an eyebrow. It is not
 * computed here and cannot be: SPEC §2.2 puts the length in the start letter of
 * the section code, and the letter-to-length map is the institution's, so
 * deriving it in the browser would be a second copy of a table only the server
 * holds — the owner's ruling of 2026-09-07 rejects that outright, and
 * `tests/unit/test_no_frontend_source_derives_how_long_a_section_runs.py` is
 * where the rejection is enforced.
 */
export function WeekEyebrow({
  courseWeek,
  termWeek,
  lengthWeeks,
  closesAt,
}: {
  readonly courseWeek: number;
  readonly termWeek: number;
  readonly lengthWeeks: number;
  readonly closesAt: string;
}): JSX.Element {
  return (
    <p className="pulse-eyebrow">
      <span className="pulse-eyebrow-week">
        {fillCopy('student_survey.course_week_eyebrow', {
          week: padWeek(courseWeek),
          total: padWeek(lengthWeeks),
        })}
      </span>
      <span className="pulse-eyebrow-quiet">
        {fillCopy('student_survey.term_week_eyebrow', { week: padWeek(termWeek) })}
      </span>
      <span className="pulse-eyebrow-quiet">
        {copy('student_survey.closes_label')} {formatClosingInstant(closesAt)}
      </span>
    </p>
  );
}

/**
 * A week number as the eyebrow writes it: two digits, so the mono figures line
 * up down a column and week 7 and week 12 are the same width.
 *
 * The course length goes through it too. A six-week section beside a
 * twelve-week one would otherwise read "/ 6" against "/ 12", and the column of
 * eyebrows a student with several courses reads down would stop lining up at
 * the one place the eye uses to line it up.
 */
function padWeek(week: number): string {
  return String(week).padStart(2, '0');
}

/**
 * The closing instant, as a person reads it: a weekday, an hour and a minute.
 *
 * The reader's own locale and timezone. `Intl` is in every browser this ships
 * to, so there is no formatting library here and no format string to keep in
 * step with one; an instant that cannot be parsed is shown as it arrived rather
 * than as "Invalid Date".
 */
function formatClosingInstant(instant: string): string {
  const when = new Date(instant);
  if (Number.isNaN(when.getTime())) return instant;
  return new Intl.DateTimeFormat(undefined, {
    weekday: 'short',
    hour: 'numeric',
    minute: '2-digit',
  }).format(when);
}
