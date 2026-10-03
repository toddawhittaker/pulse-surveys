import type { JSX } from 'react';

import { fillCopy as fillReportCopy } from '../copy/instructorReportPageCopy';
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
 * **`closesAt` is optional, which is the variant rule rather than a
 * convenience** (SPEC §7.6: one component per primitive, with variants rather
 * than copies). The student's screen shows an open window and has a close to
 * state; the instructor's Monday report shows a week whose window has already
 * shut, and "closes Sun 11:59 PM" printed over a closed week is a sentence about
 * a deadline that has passed. So the span is not rendered at all when there is
 * no instant, rather than rendered empty or filled with a dash — E4-11 is the
 * ticket that needed the variant, and the student surface passes the instant
 * exactly as before.
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
 *
 * **`closedAt` and `timeZone` are the third variant, and they are a second prop
 * pair rather than a mode of the first** (E5-02). The instructor's Monday report
 * looks back at a week that has already shut, so it states the close in the past
 * tense — `design/InstructorMondayReport.dc.html`'s "responses closed Sun 11:59
 * PM". Both halves of the pair are required together, because the two differ in
 * more than their tense: the student's instant is read in *the reader's own*
 * zone, since she is the one who has to be there before it, while a week that
 * has closed is a fact about the institution's calendar and is read in the
 * institution's zone — the `timeZone` the report payload carries beside the
 * instant, never the browser's guess. Passing one without the other renders
 * nothing rather than guessing the missing half.
 */
export function WeekEyebrow({
  courseWeek,
  termWeek,
  lengthWeeks,
  closesAt,
  closedAt,
  timeZone,
}: {
  readonly courseWeek: number;
  readonly termWeek: number;
  readonly lengthWeeks: number;
  /** When this week's window shuts. Omitted on a surface whose week has closed. */
  readonly closesAt?: string;
  /** When this week's window shut. Omitted on a surface whose week is still open. */
  readonly closedAt?: string;
  /** The IANA zone `closedAt` is read in — the institution's, off the payload. */
  readonly timeZone?: string;
}): JSX.Element {
  const closedNote =
    closedAt === undefined || timeZone === undefined
      ? null
      : formatClosedInstant(closedAt, timeZone);
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
      {closesAt === undefined ? null : (
        <span className="pulse-eyebrow-quiet">
          {copy('student_survey.closes_label')} {formatClosingInstant(closesAt)}
        </span>
      )}
      {closedNote === null ? null : (
        <span className="pulse-eyebrow-quiet">{closedNote}</span>
      )}
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

/**
 * The closed instant as the Monday report's eyebrow states it: "responses closed
 * Sun 11:59 PM".
 *
 * **The zone is named and the locale is pinned**, which is the difference from
 * the student rendering above. SPEC §3.1 closes every window at 23:59:59 in the
 * institution's zone, and a reader in another zone who was shown her own would be
 * told the week ended on the Monday — or, in the week the clocks go back, an hour
 * out from the week either side of it. `en-US` is pinned for the same reason
 * `StudentWeeklySurvey`'s `institutionInstant` pins it: the mockup's form is a
 * short weekday and a twelve-hour clock, and a locale the browser chose would
 * render the same instant as "So., 23:59".
 *
 * `null` — so the caller prints no note at all — when the instant will not parse
 * or the zone is not one `Intl` knows, since `Intl.DateTimeFormat` throws a
 * `RangeError` on an unknown zone. A half-formed sentence about when a week ended
 * is worse than no sentence.
 */
function formatClosedInstant(instant: string, timeZone: string): string | null {
  const when = new Date(instant);
  if (Number.isNaN(when.getTime())) return null;
  let formatted: string;
  try {
    formatted = new Intl.DateTimeFormat('en-US', {
      timeZone,
      weekday: 'short',
      hour: 'numeric',
      minute: '2-digit',
    }).format(when);
  } catch {
    return null;
  }
  return fillReportCopy('instructor_report_page.responses_closed_note', { when: formatted });
}
