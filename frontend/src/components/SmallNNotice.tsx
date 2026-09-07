import { useId } from 'react';
import type { JSX } from 'react';

import './instructorReportComments.css';
import { copy, fillCopy } from './instructorReportCommentCopy';

/**
 * Why a week's raw comments are not on the page — SPEC §7.6's `SmallNNotice`,
 * in its **instructor** audience. The student audience is E8's, and its words
 * are a different sentence to a different person, so it is not stubbed here.
 *
 * SPEC §4 hides raw comments below the response threshold; the design brief
 * asks that the state be designed explicitly with "an honest explanation of
 * why", and `design/Usage Rules.md` §4 keeps the instructor register formative
 * and factual. So this says what is hidden, why, and that the summary above
 * still drew on everything received.
 *
 * **The threshold is a number the payload carries** (the sketch's
 * `small_n.threshold`), because SPEC §4 makes it configurable and a 5 written
 * into a component is a second, wrong copy of a configured value the day
 * anybody changes it.
 *
 * **Nothing here counts what was withheld.** §5.2 forbids a count or a flag
 * hint below the threshold, and this component is given neither — there is no
 * prop for a number of hidden comments, so nothing can render one.
 *
 * **Where it appears is the caller's decision, and §4.1 item 5 governs it:**
 * confidentiality copy appears exactly once per surface. A report whose two
 * comment groups are both suppressed shows this notice once, which is why
 * `CommentGroup` is told whether it is the group that carries it rather than
 * deciding for itself.
 */
export function SmallNNotice({ threshold }: { readonly threshold: number }): JSX.Element {
  const titleId = useId();

  return (
    <section className="pulse-small-n-notice" aria-labelledby={titleId}>
      <FlatPulseLine />
      <p className="pulse-small-n-notice__title" id={titleId}>
        {copy('instructor_report_comments.small_n.title')}
      </p>
      <p className="pulse-small-n-notice__body">
        {fillCopy('instructor_report_comments.small_n.body', { threshold: String(threshold) })}
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
