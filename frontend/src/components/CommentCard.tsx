import { useId, useState } from 'react';
import type { JSX } from 'react';

import './instructorReportComments.css';
import type { CommentDecisionView } from '../api/instructor';
import { copy, fillCopy } from '../copy/instructorReportCommentCopy';

/**
 * One comment as the report payload carries it, in the card's vocabulary.
 *
 * Still no timestamp, no author and no decider at any depth (SPEC §4, ADR
 * 0189). `decidedByYou` is the only attribution a card can carry, and it is a
 * yes or no about the reader rather than a name.
 */
export type ReportComment = {
  readonly text: string;
  readonly status: 'published' | 'flagged' | 'excluded' | 'kept';
  /** The classifier's word for why it was flagged (§5.2), on a flagged comment only. */
  readonly flagReason?: string;
  /** Whether the latest decision on this comment was the reader's own. */
  readonly decidedByYou?: boolean;
};

/** One of SPEC §5.2's three moderation actions, as the wire carries it. */
export type CommentDecision = CommentDecisionView;

/**
 * What a decision answered, as the card needs it: the comment's new state, or
 * the one sentence to show beside the control that was pressed.
 */
export type DecisionAnswer =
  | { readonly kind: 'decided'; readonly comment: ReportComment }
  | { readonly kind: 'refused'; readonly detail: string };

/** The bound SPEC §5.2's stated reason is held to, and the server checks too. */
export const REASON_MAX_LENGTH = 500;

/**
 * One de-identified comment, as the instructor's Monday report shows it —
 * SPEC §7.6's `CommentCard`, one component with variants rather than copies.
 *
 * **What this component is given is all it can ever show.** SPEC §4 forbids
 * timestamps and identity with comments and forbids anything that reveals
 * submission order; the guarantee here is structural rather than careful —
 * there is no prop for a timestamp, an author, an id or a position, so no
 * caller can pass one and no future edit can start rendering one without
 * changing the type. Order is the order the array arrived in; the
 * randomization is the server's (§4), and nothing here sorts or groups.
 *
 * **The variants** (§7.6): `default`, `flagged-collapsed`, `flagged-expanded`
 * and `excluded`, and SPEC §5.2's `kept`. Four of them are `status`; the fifth
 * is the disclosure's own state, because collapsing and expanding a flagged
 * comment is UI state and not a lifecycle event. §5.2's moderation lifecycle —
 * exclude, keep, undo, the stated reason — is offered only when the caller
 * gives the card `decide`; a card without it is read-only.
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
 *
 * **After a decision the card shows the card the server answered**, never one
 * guessed in advance: the answer is the record of what was decided, and a
 * refusal leaves the earlier card exactly as it was, with the server's sentence
 * beside it.
 */
export function CommentCard({
  stream,
  decide,
  ...given
}: ReportComment & {
  readonly stream?: 'instructor' | 'course';
  /** Sends one decision on this comment. Absent, the card offers no controls. */
  readonly decide?: (decision: CommentDecision) => Promise<DecisionAnswer>;
}): JSX.Element {
  const [comment, setComment] = useState<ReportComment>(given);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  async function send(decision: CommentDecision): Promise<void> {
    if (decide === undefined) return;
    setSending(true);
    setRefusal(null);
    const answer = await decide(decision);
    setSending(false);
    if (answer.kind === 'refused') {
      setRefusal(answer.detail);
      return;
    }
    setComment(answer.comment);
  }

  return (
    <article className="pulse-comment-card" aria-label={copy('instructor_report_comments.comment.aria_label')}>
      <CardBody
        // Keyed by the status, so a disclosure or a reason prompt left open
        // belongs to the state it was opened in and closes when that changes.
        key={comment.status}
        comment={comment}
        stream={stream}
        controls={decide !== undefined}
        sending={sending}
        refusal={refusal}
        send={send}
      />
    </article>
  );
}

/** The body of one card in its current state. */
function CardBody({
  comment,
  stream,
  controls,
  sending,
  refusal,
  send,
}: {
  readonly comment: ReportComment;
  readonly stream: 'instructor' | 'course' | undefined;
  readonly controls: boolean;
  readonly sending: boolean;
  readonly refusal: string | null;
  readonly send: (decision: CommentDecision) => Promise<void>;
}): JSX.Element {
  const [expanded, setExpanded] = useState(false);
  const [prompting, setPrompting] = useState(false);
  const { text, status, flagReason, decidedByYou = false } = comment;
  const undo = controls && decidedByYou;

  if (status === 'excluded') {
    return (
      <>
        <p className="pulse-comment-card__text pulse-comment-card__text--muted">{text}</p>
        <div className="pulse-comment-card__decision-row">
          <span className="pulse-comment-card__notice">
            {copy('instructor_report_comments.comment.excluded_notice')}
          </span>
          {undo ? <UndoButton sending={sending} send={send} /> : null}
        </div>
        <Refusal refusal={refusal} />
      </>
    );
  }

  if (status === 'kept') {
    return (
      <>
        {stream === undefined ? null : <StreamChip stream={stream} />}
        <p className="pulse-comment-card__text">{text}</p>
        <div className="pulse-comment-card__decision-row">
          <span className="pulse-comment-card__notice">
            {copy(
              decidedByYou
                ? 'instructor_report_comments.comment.kept_by_you'
                : 'instructor_report_comments.comment.kept',
            )}
          </span>
          {undo ? <UndoButton sending={sending} send={send} /> : null}
        </div>
        <Refusal refusal={refusal} />
      </>
    );
  }

  if (status === 'flagged') {
    return (
      <>
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
            {/* The actions sit with the words, as the mockup draws them: a
                decision is made after reading the comment, not before. A
                flagged comment needs no stated reason to be excluded (§5.2). */}
            {controls ? (
              <div className="pulse-comment-card__actions">
                <button
                  type="button"
                  className="pulse-comment-card__action"
                  disabled={sending}
                  onClick={() => void send({ action: 'keep', reason: null })}
                >
                  {copy('instructor_report_comments.comment.keep')}
                </button>
                <button
                  type="button"
                  className="pulse-comment-card__action pulse-comment-card__action--exclude"
                  disabled={sending}
                  onClick={() => void send({ action: 'exclude', reason: null })}
                >
                  {copy('instructor_report_comments.comment.exclude')}
                </button>
              </div>
            ) : null}
            <Refusal refusal={refusal} />
          </div>
        ) : null}
      </>
    );
  }

  return (
    <>
      {stream === undefined ? null : <StreamChip stream={stream} />}
      <p className="pulse-comment-card__text">{text}</p>
      {controls && prompting ? (
        <ReasonPrompt
          sending={sending}
          refusal={refusal}
          send={send}
          cancel={() => {
            setPrompting(false);
          }}
        />
      ) : null}
      {controls && !prompting ? (
        <>
          <div className="pulse-comment-card__actions">
            <button
              type="button"
              className="pulse-comment-card__action pulse-comment-card__action--exclude"
              onClick={() => {
                setPrompting(true);
              }}
            >
              {copy('instructor_report_comments.comment.exclude')}
            </button>
          </div>
          <Refusal refusal={refusal} />
        </>
      ) : null}
    </>
  );
}

/**
 * SPEC §5.2's stated reason, asked for before an unflagged comment is excluded.
 *
 * Submit stays disabled while the field holds no words, because the server
 * refuses a blank reason and there is nothing to gain by sending one. The
 * server's sentence for any refusal it does send shows under the field.
 */
function ReasonPrompt({
  sending,
  refusal,
  send,
  cancel,
}: {
  readonly sending: boolean;
  readonly refusal: string | null;
  readonly send: (decision: CommentDecision) => Promise<void>;
  readonly cancel: () => void;
}): JSX.Element {
  const fieldId = useId();
  const counterId = useId();
  const [reason, setReason] = useState('');
  const blank = reason.trim() === '';

  return (
    <form
      className="pulse-comment-card__reason"
      onSubmit={(event) => {
        event.preventDefault();
        if (!blank) void send({ action: 'exclude', reason });
      }}
    >
      <label className="pulse-comment-card__reason-label" htmlFor={fieldId}>
        {copy('instructor_report_comments.comment.reason_label')}
      </label>
      <textarea
        id={fieldId}
        className="pulse-comment-card__reason-field"
        required
        maxLength={REASON_MAX_LENGTH}
        aria-describedby={counterId}
        value={reason}
        onChange={(event) => {
          setReason(event.target.value);
        }}
      />
      <span className="pulse-comment-card__reason-counter" id={counterId}>
        {fillCopy('instructor_report_comments.comment.reason_remaining', {
          remaining: String(REASON_MAX_LENGTH - reason.length),
        })}
      </span>
      <Refusal refusal={refusal} />
      <div className="pulse-comment-card__actions">
        <button
          type="submit"
          className="pulse-comment-card__action pulse-comment-card__action--exclude"
          disabled={blank || sending}
        >
          {copy('instructor_report_comments.comment.reason_submit')}
        </button>
        <button type="button" className="pulse-comment-card__action" onClick={cancel}>
          {copy('instructor_report_comments.comment.reason_cancel')}
        </button>
      </div>
    </form>
  );
}

/** Undo, offered only on the reader's own latest decision (SPEC §5.2). */
function UndoButton({
  sending,
  send,
}: {
  readonly sending: boolean;
  readonly send: (decision: CommentDecision) => Promise<void>;
}): JSX.Element {
  return (
    <button
      type="button"
      className="pulse-comment-card__action"
      disabled={sending}
      onClick={() => void send({ action: 'undo', reason: null })}
    >
      {copy('instructor_report_comments.comment.undo')}
    </button>
  );
}

/** The server's sentence for a refused decision, shown as it was sent. */
function Refusal({ refusal }: { readonly refusal: string | null }): JSX.Element | null {
  if (refusal === null) return null;
  return (
    <p className="pulse-comment-card__refusal" role="alert">
      {refusal}
    </p>
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
