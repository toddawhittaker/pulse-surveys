import { useState } from 'react';
import type { JSX } from 'react';

import './instructorReportComments.css';
import { copy, fillCopy } from './instructorReportCommentCopy';

/**
 * One de-identified comment, as the instructor's Monday report shows it —
 * SPEC §7.6's `CommentCard`, one component with variants rather than copies.
 *
 * **What this component is given is all it can ever show.** SPEC §4 forbids
 * timestamps and identity with comments and forbids anything that reveals
 * submission order; the guarantee here is structural rather than a habit —
 * there is no prop for a timestamp, an author, an id or a position, so no
 * caller can pass one and no future edit can start rendering one without
 * changing the type. Order is the order the array arrived in; the
 * randomization is the server's (§4), and nothing here sorts or groups.
 *
 * **The four variants** (§7.6): `default`, `flagged-collapsed`,
 * `flagged-expanded` and `excluded`. Three of them are `status`; the fourth is
 * the disclosure's own state, because collapsing and expanding a flagged
 * comment is UI state and not a lifecycle event. SPEC §5.2's moderation
 * lifecycle — exclude, keep, undo, the typed reason — is **E6's**, and there is
 * deliberately no button here that offers any of it: a control that promised a
 * decision the backend cannot yet record would be worse than its absence.
 *
 * **The collapsed state has no text in the DOM at all.** The prototype
 * collapses by height, which leaves a flagged comment's words readable to a
 * screen reader while the screen says they are hidden. The words appear when
 * the disclosure is opened and not before; the 200ms height ease the brief asks
 * for is a CSS animation on the revealed region
 * (`instructorReportComments.css`), so `design/tokens.css`'s reduced-motion
 * switch removes it like everything else.
 *
 * **`flagReason`** is the classifier's word (§5.2: harmful / privacy /
 * nonsense) and is filled into the chip's governed sentence. Below the
 * threshold there is no chip, no count and no flag-type hint to render, because
 * §5.2's concealment happens in the payload: a suppressed week's comments do
 * not reach this component.
 *
 * **The stream chip is off unless a stream is given**, per §7.6's "optional
 * stream chip, default off". Nothing in E4 gives it one — the report groups by
 * stream, so a chip inside a group would only repeat the heading above it.
 */
/**
 * One comment as the report payload carries it.
 *
 * `docs/tickets/e4/README.md`'s sketch gives a comment `text` and `status` and
 * nothing else — no timestamp and no author field at any depth, on purpose.
 * `flagReason` is added here because §5.2's chip has to name the reason it was
 * flagged for; E4-07's schema is the authority the moment it merges, and E4-11
 * is the ticket that resolves any divergence (README decision 5).
 */
export type ReportComment = {
  readonly text: string;
  readonly status: 'published' | 'flagged' | 'excluded';
  /** The classifier's word for why it was flagged (§5.2), on a flagged comment only. */
  readonly flagReason?: string;
};

export function CommentCard({
  text,
  status,
  flagReason,
  stream,
}: ReportComment & {
  readonly stream?: 'instructor' | 'course';
}): JSX.Element {
  const [expanded, setExpanded] = useState(false);

  if (status === 'excluded') {
    return (
      <article className="pulse-comment-card" aria-label={copy('instructor_report_comments.comment.aria_label')}>
        <p className="pulse-comment-card__text pulse-comment-card__text--muted">{text}</p>
        <span className="pulse-comment-card__notice">
          {copy('instructor_report_comments.comment.excluded_notice')}
        </span>
      </article>
    );
  }

  if (status === 'flagged') {
    return (
      <article className="pulse-comment-card" aria-label={copy('instructor_report_comments.comment.aria_label')}>
        {stream === undefined ? null : <StreamChip stream={stream} />}
        <div className="pulse-comment-card__flag-row">
          <span className="pulse-comment-card__flag-chip">
            {fillCopy('instructor_report_comments.comment.flag_chip', { reason: flagReason ?? '' })}
          </span>
          <span className="pulse-comment-card__flag-note">
            {copy('instructor_report_comments.comment.flag_pending')}
          </span>
          <button
            type="button"
            className="pulse-comment-card__disclosure"
            aria-expanded={expanded}
            onClick={() => {
              setExpanded(!expanded);
            }}
          >
            {copy(
              expanded
                ? 'instructor_report_comments.comment.collapse'
                : 'instructor_report_comments.comment.expand',
            )}
          </button>
        </div>
        {expanded ? (
          <div className="pulse-comment-card__body">
            <p className="pulse-comment-card__text">{text}</p>
          </div>
        ) : null}
      </article>
    );
  }

  return (
    <article className="pulse-comment-card" aria-label={copy('instructor_report_comments.comment.aria_label')}>
      {stream === undefined ? null : <StreamChip stream={stream} />}
      <p className="pulse-comment-card__text">{text}</p>
    </article>
  );
}

/** The optional stream chip: a mono eyebrow naming which question the comment answered. */
function StreamChip({ stream }: { readonly stream: 'instructor' | 'course' }): JSX.Element {
  return (
    <span className="pulse-comment-card__stream-chip">
      {copy(
        stream === 'instructor'
          ? 'instructor_report_comments.comment.stream_instructor'
          : 'instructor_report_comments.comment.stream_course',
      )}
    </span>
  );
}
