import type { JSX } from 'react';

import './instructorReportComments.css';

/**
 * Why one comment group's raw comments, or one stream's ratings, are not on the
 * page — SPEC §7.6's `SmallNNotice`.
 *
 * **The words are the caller's.** The instructor's notice states the configured
 * threshold, because SPEC §4 makes it a setting; the student's states no number
 * at all, since a threshold tells a student how many classmates must write before
 * theirs shows, and a count of anyone below it is the disclosure the hold exists
 * to prevent (SPEC §5.2). A component that took a threshold or a count would be a
 * component a number could arrive through, so it takes two strings and nothing
 * else.
 *
 * The design brief asks that the state be designed explicitly with "an honest
 * explanation of why", and `design/Usage Rules.md` §4 keeps the register
 * formative and factual.
 *
 * **Where it appears is `CommentGroup`'s decision**: inside each suppressed
 * group, after its summary, because suppression is a fact about a stream
 * (ADR 0182). A week with both streams suppressed shows it twice, once per
 * group. It is not SPEC §4.1 item 5's confidentiality line, which item 5 itself
 * says of a state notice (ADR 0158), so two of them on one page is not two
 * standing promises.
 *
 * **It is a plain block, not a landmark.** Two held streams render two notices
 * with the same title, and WCAG 2.2 asks landmarks of one type to be told apart;
 * the group's own labelled section and heading already say which stream this is.
 */
export function SmallNNotice({
  title,
  body,
}: {
  /** The notice's heading line, in the audience's own words. */
  readonly title: string;
  /** Why the group is held and where its comments go; the caller's words, with any number the audience may see. */
  readonly body: string;
}): JSX.Element {
  return (
    <div className="pulse-small-n-notice">
      <FlatPulseLine />
      <p className="pulse-small-n-notice__title">{title}</p>
      <p className="pulse-small-n-notice__body">{body}</p>
    </div>
  );
}

/**
 * The signature motif in its flat variant: a mist line with a terminal dot,
 * which `docs/DESIGN_BRIEF.md` gives to states where nothing has arrived.
 * Decorative, so it is hidden from assistive technology — the words below say
 * everything it says.
 */
function FlatPulseLine(): JSX.Element {
  return (
    <svg
      className="pulse-small-n-notice__mark"
      width="120"
      height="12"
      viewBox="0 0 120 12"
      aria-hidden="true"
    >
      <line
        x1="1"
        y1="6"
        x2="108"
        y2="6"
        stroke="var(--mist)"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <circle cx="114" cy="6" r="3" fill="var(--mist)" />
    </svg>
  );
}
