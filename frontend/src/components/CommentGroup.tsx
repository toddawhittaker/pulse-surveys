import { useId } from 'react';
import type { JSX } from 'react';

import { AiPanel } from './AiPanel';
import { CommentCard } from './CommentCard';
import type { ReportComment } from './CommentCard';
import { SmallNNotice } from './SmallNNotice';
import './instructorReportComments.css';
import { copy } from './instructorReportCommentCopy';

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
 * no cards, and — where the surface has not already stated it — the notice
 * explaining why. Nothing written here blurs the second into the third: a week
 * nobody wrote in and a week whose comments are withheld are different facts
 * about the class, and an instructor who is told the wrong one draws the wrong
 * conclusion about their students.
 *
 * **Suppression is fail-closed.** When the payload says the week is suppressed,
 * no card renders — whatever the comment array happens to hold. The array
 * should be empty (§4 hides the comments in the payload, not in the browser),
 * and if it ever is not, the concealment is still what happens.
 *
 * **`smallN.withNotice` is not a style option.** SPEC §4.1 item 5 requires
 * confidentiality copy to appear exactly once per surface, and a suppressed
 * week suppresses both of a report's groups — so exactly one of them carries
 * the notice and the other does not, and the surface placing them is the only
 * thing that can know which. The field is required rather than defaulted so the
 * choice is made out loud at the call site.
 *
 * **Order is the order given.** The randomization SPEC §4 requires is the
 * server's; nothing here sorts, shuffles, groups or numbers, and the cards
 * carry no position a reader could read submission order out of.
 */
export function CommentGroup({
  stream,
  summary,
  comments,
  smallN,
}: {
  readonly stream: 'instructor' | 'course';
  readonly summary: {
    readonly text: string;
    readonly responseCount: number;
    readonly heldNote: string | null;
  };
  readonly comments: readonly ReportComment[];
  /** Present only on a week below the threshold, per the sketch's `small_n` member. */
  readonly smallN?: {
    readonly threshold: number;
    /** Whether this group is the one carrying the surface's confidentiality copy. */
    readonly withNotice: boolean;
  };
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
      <AiPanel
        heading={copy(
          instructorStream
            ? 'instructor_report_comments.ai.instructor_heading'
            : 'instructor_report_comments.ai.course_heading',
        )}
        text={summary.text}
        responseCount={summary.responseCount}
        heldNote={summary.heldNote}
      />
      {smallN === undefined ? (
        <GroupComments comments={comments} />
      ) : smallN.withNotice ? (
        <div className="pulse-comment-group__notice">
          <SmallNNotice threshold={smallN.threshold} />
        </div>
      ) : null}
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
