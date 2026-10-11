import type { JSX } from 'react';

import type { ResponseAuthorRole } from '../api/student';
import { fillCopy } from '../copy/studentResults';
import { institutionInstant } from '../lib/institutionTime';

/**
 * A published response to one week, and who wrote it — SPEC §7.6's
 * `ResponseCard`, with its instructor and on-behalf variants (SPEC §5.3).
 *
 * **The two variants are one layout.** A response written by the lead or the
 * chair is attributed by name and role in the same place, in the same type, as
 * one the instructor wrote; the variant changes the words of the byline and
 * nothing else, so no reader can tell by weight which kind they are reading.
 * Nothing on the card says why someone else wrote it.
 *
 * The text and the name are the API's and are shown as sent, as text: React
 * escapes them, and the text keeps its line breaks through CSS rather than by
 * being parsed. The date is the institution's day, when the page knows the
 * institution's zone; without one the card shows no date rather than the
 * browser's.
 */
export function ResponseCard({
  text,
  authorName,
  authorRole,
  publishedAt,
  timeZone,
}: {
  readonly text: string;
  readonly authorName: string;
  readonly authorRole: ResponseAuthorRole;
  /** An instant, as the wire sends it. */
  readonly publishedAt: string;
  /** The institution's IANA zone, when the page has it. */
  readonly timeZone?: string;
}): JSX.Element {
  const when = timeZone === undefined ? null : institutionInstant(publishedAt, timeZone);
  return (
    <article className="pulse-response-card" data-author-role={authorRole}>
      <p className="pulse-response-text">{text}</p>
      <p className="pulse-response-byline">
        <span className="pulse-response-author">{bylineOf(authorName, authorRole)}</span>
        {when === null ? null : (
          <span className="pulse-response-date">
            {fillCopy('student_survey.results_published_on', { day: when.day })}
          </span>
        )}
      </p>
    </article>
  );
}

function bylineOf(name: string, role: ResponseAuthorRole): string {
  if (role === 'LEAD_FACULTY') return fillCopy('student_survey.results_author_lead_faculty', { name });
  if (role === 'CHAIR') return fillCopy('student_survey.results_author_chair', { name });
  return fillCopy('student_survey.results_author_instructor', { name });
}
