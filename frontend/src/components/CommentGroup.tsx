import { useId } from 'react';
import type { JSX } from 'react';

import { AiPanel } from './AiPanel';
import { CommentCard } from './CommentCard';
import type { ReportComment } from './CommentCard';
import './instructorReportComments.css';
import { copy } from '../copy/instructorReportCommentCopy';

/**
 * One comment stream as SPEC §5.1 lays it out: comments "grouped under 'About
 * the instructor' / 'About the course', each group led by its own AI summary",
 * and "empty groups show a one-line notice, not a hidden heading".
 *
 * The composable unit E4-11 places twice — once per stream — so that the
 * report page decides *where* the groups sit and this decides what a group is.
 *
 * **Three states, and two of them look alike until you read them.** A group
 * with comments shows its summary and its cards. A group whose week produced
 * none shows §5.1's one-line notice under its heading. A group whose week is
 * below the response threshold shows §4's small-N framing instead: the summary,
 * and no cards. Nothing written here blurs the second into the third: a week
 * nobody wrote in and a week whose comments are withheld are different facts
 * about the class, and an instructor who is told the wrong one draws the wrong
 * conclusion about their students — so a suppressed group renders neither the
 * cards nor the empty-week line.
 *
 * **A group with no summary is a fourth state, and it is honest rather than
 * empty** (E4-11). `summary` is nullable because `StreamReport.summary` is: a
 * week the Monday job has not run over — or one it failed on — has no row, and
 * §5.1 makes the summary the thing a group is led by. So the panel is replaced
 * by one line saying no summary was written, and everything else about the group
 * renders exactly as it would have. An empty `AiPanel` was the alternative and
 * is worse: the brief's chalk inset with its mono "AI" label is a claim that
 * generated prose is inside it, and a reader meeting an empty one concludes the
 * model had nothing to say about their week rather than that nothing ran.
 *
 * **Suppression is fail-closed, and it covers the summary's held note as well
 * as the cards.** When the payload says the week is suppressed, no card renders
 * — whatever the comment array happens to hold — and the summary goes out
 * without its held note, which names a flag type §5.2 conceals below the
 * threshold. The array should be empty and the note should be absent (§4 hides
 * both in the payload, not in the browser); if either ever is not, the
 * concealment is still what happens.
 *
 * **The notice explaining the suppression is not this component's** (E4-21). A
 * suppressed week suppresses both of a report's groups, so the explanation is
 * one statement about the week rather than one per group, and
 * `design/InstructorMondayReport.dc.html:69-73` places it under both of them.
 * This component is told the week is suppressed and conceals accordingly; where
 * the sentence about it goes is the surface's, which is also what keeps SPEC
 * §4.1 item 5's once-per-surface count a fact about a placement rather than
 * about which group happened to render first.
 *
 * **`suppressed` is required rather than defaulted**, so the choice is made out
 * loud at every call site: a caller who forgot it would be a caller showing a
 * below-threshold week's raw comments, and that is not a default anything should
 * have.
 *
 * **Order is the order given.** The randomization SPEC §4 requires is the
 * server's; nothing here sorts, shuffles, groups or numbers, and the cards
 * carry no position a reader could read submission order out of.
 */
export function CommentGroup({
  stream,
  summary,
  comments,
  suppressed,
}: {
  readonly stream: 'instructor' | 'course';
  /** The stream's generated summary, or `null` for a week none was written for. */
  readonly summary: {
    readonly text: string;
    readonly responseCount: number;
    readonly heldNote: string | null;
  } | null;
  readonly comments: readonly ReportComment[];
  /** Whether this week is below SPEC §4's threshold, as the payload declares it. */
  readonly suppressed: boolean;
}): JSX.Element {
  const headingId = useId();
  const instructorStream = stream === 'instructor';

  return (
    <section className="pulse-comment-group" aria-labelledby={headingId}>
      <h3 className="pulse-comment-group__heading" id={headingId}>
        {copy(
          instructorStream
            ? 'instructor_report_comments.group.instructor_heading'
            : 'instructor_report_comments.group.course_heading',
        )}
      </h3>
      {summary === null ? (
        <p className="pulse-comment-group__absent-summary">
          {copy('instructor_report_comments.ai.absent')}
        </p>
      ) : (
        <AiPanel
          heading={copy(
            instructorStream
              ? 'instructor_report_comments.ai.instructor_heading'
              : 'instructor_report_comments.ai.course_heading',
          )}
          text={summary.text}
          responseCount={summary.responseCount}
          // The held note names a flag type, and §5.2 hides flagged comments
          // from the instructor entirely below the threshold — "no chip, no
          // count, no flag-type hint" — while §5.1 permits the note only above
          // small-N. So a suppressed week's summary goes out without it. This is
          // the same fail-closed move the card list makes below, applied to the
          // one other thing on this panel that could carry a hint: it obeys the
          // suppression the payload already declared, and decides no threshold
          // of its own.
          heldNote={suppressed ? null : summary.heldNote}
        />
      )}
      {suppressed ? null : <GroupComments comments={comments} />}
    </section>
  );
}

/** The cards a group holds, or §5.1's one-line notice when the week produced none. */
function GroupComments({ comments }: { readonly comments: readonly ReportComment[] }): JSX.Element {
  if (comments.length === 0) {
    return (
      <p className="pulse-comment-group__empty">
        {copy('instructor_report_comments.group.empty_notice')}
      </p>
    );
  }

  return (
    <ul className="pulse-comment-group__cards">
      {comments.map((comment, position) => (
        // The payload gives a comment no id — by design, since an id is a
        // handle on one student's words — so the key is the position in the
        // array the server randomized. It is not rendered anywhere.
        <li key={position}>
          <CommentCard
            text={comment.text}
            status={comment.status}
            flagReason={comment.flagReason}
          />
        </li>
      ))}
    </ul>
  );
}
