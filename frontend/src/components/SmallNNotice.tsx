import { useId } from 'react';
import type { JSX } from 'react';

import './instructorReportComments.css';
import { copy, fillCopy } from '../copy/instructorReportCommentCopy';

/**
 * Why one comment group's raw comments are not on the page — SPEC §7.6's
 * `SmallNNotice`, in its **instructor** audience. The student audience is E8's,
 * and its words are a different sentence to a different person, so it is not
 * stubbed here.
 *
 * SPEC §4 hides a stream's raw comments when fewer than the threshold of
 * distinct students commented in that stream that week; the design brief asks
 * that the state be designed explicitly with "an honest explanation of why",
 * and `design/Usage Rules.md` §4 keeps the instructor register formative and
 * factual. So this says what is hidden, why, where held comments go, and that
 * the summary above still drew on everything received.
 *
 * **The one number here is the threshold, and it is the payload's** — the
 * stream's `small_n.threshold`, because SPEC §4 makes it configurable and a 5
 * written into a component is a second, wrong copy of a configured value the
 * day anybody changes it.
 *
 * **Nothing here counts anybody** (E5.1-01). §5.2 forbids a count below the
 * threshold, and the notice now sits inside one group, where any count reads as
 * that group's: in a stream of one commenter, a count of commenters is the
 * whole disclosure, and a count of the week's respondents beside it is a
 * subtraction away from one. So the component takes the threshold and nothing
 * else; there is no prop a count could arrive through.
 *
 * **Where it appears is `CommentGroup`'s decision**: inside each suppressed
 * group, after its summary, because suppression is a fact about a stream
 * (ADR 0182). A week with both streams suppressed shows it twice, once per
 * group. It is not SPEC §4.1 item 5's confidentiality line, which item 5 itself
 * says of a state notice (ADR 0158), so two of them on one page is not two
 * standing promises.
 */
export function SmallNNotice({
  threshold,
}: {
  /** The configured number of distinct commenters a stream's raw comments are held until. */
  readonly threshold: number;
}): JSX.Element {
  const titleId = useId();

  return (
    <section className="pulse-small-n-notice" aria-labelledby={titleId}>
      <FlatPulseLine />
      <p className="pulse-small-n-notice__title" id={titleId}>
        {copy('instructor_report_comments.small_n.title')}
      </p>
      <p className="pulse-small-n-notice__body">
        {fillCopy('instructor_report_comments.small_n.body', {
          threshold: String(threshold),
        })}
      </p>
    </section>
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
