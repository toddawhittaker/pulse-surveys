import { useId } from 'react';
import type { JSX } from 'react';

import { AiPanel } from './AiPanel';
import { CommentCard } from './CommentCard';
import type { CommentDecision, DecisionAnswer, ReportComment } from './CommentCard';
import { SmallNNotice } from './SmallNNotice';
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
 * with comments shows its summary and its cards. A group the payload sends with
 * no comments and not suppressed shows §5.1's one-line notice under its
 * heading. A suppressed group shows §4's small-N framing instead: the summary,
 * the notice, and no cards. Since E5.1-01 the server suppresses a stream nobody
 * commented in exactly as it suppresses a thin one (ADR 0182), so a reader
 * cannot tell nobody from one person, and the empty-week line is what an
 * inconsistent payload would get rather than an ordinary week. Nothing written
 * here blurs the two: a suppressed group renders neither the cards nor the
 * empty-week line.
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
 * as the cards.** When the payload says the stream is suppressed, no card renders
 * — whatever the comment array happens to hold — and the summary goes out
 * without its held note, which names a flag type §5.2 conceals below the
 * threshold. The array should be empty and the note should be absent (§4 hides
 * both in the payload, not in the browser); if either ever is not, the
 * concealment is still what happens.
 *
 * **The notice explaining the suppression is this component's, since E5.1-01.**
 * E4-21 had moved it under both groups because a suppressed week then
 * suppressed both of them. The threshold now counts distinct commenters per
 * stream (ADR 0182), so one group of a week can be shown while the other is
 * held, and a notice under both would claim both were. So each suppressed
 * group states it once, after its summary; a week with both streams
 * suppressed shows two. The notice is a state notice, not SPEC §4.1 item 5's
 * confidentiality line (ADR 0158), so that count is unaffected.
 *
 * **`suppressed` and `threshold` are required rather than defaulted**, so the
 * choice is made out loud at every call site: a caller who forgot `suppressed`
 * would be a caller showing a below-threshold stream's raw comments, and that is
 * not a default anything should have.
 *
 * **Decisions are the page's to send** (SPEC §5.2). Given `decide`, each card
 * whose comment carries its handle is offered the moderation controls, with
 * `decide` bound to that handle; the card itself never holds the handle, so it
 * still has nothing it could render one from.
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
  threshold,
  decide,
}: {
  readonly stream: 'instructor' | 'course';
  /** The stream's generated summary, or `null` for a week none was written for. */
  readonly summary: {
    readonly text: string;
    readonly responseCount: number;
    readonly heldNote: string | null;
  } | null;
  readonly comments: readonly GroupComment[];
  /** Sends one decision on the comment with this handle. Absent, the cards are read-only. */
  readonly decide?: (answerId: string, decision: CommentDecision) => Promise<DecisionAnswer>;
  /** Whether this stream is below SPEC §4's threshold this week, as the payload declares it. */
  readonly suppressed: boolean;
  /** The configured threshold the payload compared this stream with. */
  readonly threshold: number;
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
          // small-N. So a suppressed stream's summary goes out without it. This is
          // the same fail-closed move the card list makes below, applied to the
          // one other thing on this panel that could carry a hint: it obeys the
          // suppression the payload already declared, and decides no threshold
          // of its own.
          heldNote={suppressed ? null : summary.heldNote}
        />
      )}
      {suppressed ? (
        <div className="pulse-comment-group__small-n">
          <SmallNNotice threshold={threshold} />
        </div>
      ) : (
        <GroupComments comments={comments} decide={decide} />
      )}
    </section>
  );
}

/** One comment of a group: the card's fields, and the handle a decision is sent with. */
export type GroupComment = ReportComment & { readonly answerId?: string };

/** The cards a group holds, or §5.1's one-line notice when the week produced none. */
function GroupComments({
  comments,
  decide,
}: {
  readonly comments: readonly GroupComment[];
  readonly decide:
    | ((answerId: string, decision: CommentDecision) => Promise<DecisionAnswer>)
    | undefined;
}): JSX.Element {
  if (comments.length === 0) {
    return (
      <p className="pulse-comment-group__empty">
        {copy('instructor_report_comments.group.empty_notice')}
      </p>
    );
  }

  return (
    <ul className="pulse-comment-group__cards">
      {comments.map((comment, position) => {
        const { answerId } = comment;
        return (
          // The key is the position in the array the server randomized, not
          // the handle: a handle is never put anywhere the page renders.
          <li key={position}>
            <CommentCard
              text={comment.text}
              status={comment.status}
              flagReason={comment.flagReason}
              decidedByYou={comment.decidedByYou}
              decide={
                decide === undefined || answerId === undefined
                  ? undefined
                  : (decision) => decide(answerId, decision)
              }
            />
          </li>
        );
      })}
    </ul>
  );
}
