import { useEffect, useRef, useState, type JSX } from 'react';

import {
  decideOnQueuedComment,
  readReviewQueue,
  type QueueItemView,
  type ReviewQueueRead,
} from '../../api/leadership';
import {
  CommentCard,
  type CommentDecision,
  type DecisionAnswer,
} from '../../components/CommentCard';
import { StateNotice } from '../../components/StateNotice';
import { copy } from '../../copy/leadershipModerationCopy';
import './leadershipComparisonSets.css';
import './leadershipModeration.css';

/** The address of the review queue, under the leadership area. */
export const REVIEW_QUEUE_ROUTE = '/leadership/review-queue';

/** Where a spec finds the page. */
export const REVIEW_QUEUE_TESTID = 'pulse-leadership-review-queue';

/** Where a spec finds the list itself, as opposed to one of the page's states. */
export const REVIEW_QUEUE_LIST_TESTID = 'pulse-leadership-review-queue-list';

const HEADING_ID = 'pulse-review-queue-heading';

/**
 * Every queued comment carries a harmful verdict: that is what puts it in the
 * queue (SPEC §5.2, ADR 0190), so the card's flag chip says so without the wire
 * having to repeat it on every item.
 */
const QUEUED_FLAG = 'harmful';

type Load =
  | { readonly kind: 'loading' }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'error'; readonly detail: string | null }
  | { readonly kind: 'queue'; readonly items: readonly QueueItemView[] };

/**
 * `/leadership/review-queue` — the comments a Lead Faculty member or a chair is
 * asked to decide on (SPEC §5.2).
 *
 * **Each item is its text and its section, and nothing else.** The wire carries
 * no week, time or count (ADR 0190), and this page adds none: it does not number
 * the items, sort them or say how many there are. The order is the one the
 * server drew for this read.
 *
 * **The card is the instructor report's `CommentCard`**, in its flagged variant,
 * so Exclude and Keep are the same controls with the same words. The card's
 * `decide` is the leader's door here; a lead has no undo, and the card offers
 * undo only on a decided comment, which never stays on this page: a decision the
 * server accepted (204) removes the item, and a refusal leaves it with the
 * server's sentence beside the control that was pressed.
 *
 * **Focus goes to the heading when an item leaves**, because the control that
 * was pressed leaves with it, and the status line says what happened once.
 */
export function ReviewQueueRoute(): JSX.Element {
  const [load, setLoad] = useState<Load>({ kind: 'loading' });
  const [announcement, setAnnouncement] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    let live = true;
    void readReviewQueue().then((read) => {
      if (live) setLoad(loadFrom(read));
    });
    return () => {
      live = false;
    };
  }, []);

  async function decide(item: QueueItemView, decision: CommentDecision): Promise<DecisionAnswer> {
    // The card offers undo only on a comment the reader already decided, and
    // such a comment has left this page, so this is unreachable from the card.
    if (decision.action === 'undo') {
      return { kind: 'refused', detail: copy('leadership_moderation.queue.decision_unavailable') };
    }
    setAnnouncement(null);
    const outcome = await decideOnQueuedComment(item.answer_id, {
      action: decision.action,
      reason: decision.reason ?? null,
    });
    if (outcome.kind === 'decided') {
      setLoad((held) =>
        held.kind === 'queue'
          ? { kind: 'queue', items: held.items.filter((it) => it.answer_id !== item.answer_id) }
          : held,
      );
      setAnnouncement(
        copy(
          decision.action === 'exclude'
            ? 'leadership_moderation.queue.excluded'
            : 'leadership_moderation.queue.kept',
        ),
      );
      headingRef.current?.focus();
      return {
        kind: 'decided',
        comment: { text: item.text, status: decision.action === 'exclude' ? 'excluded' : 'kept' },
      };
    }
    if (outcome.kind === 'session-ended') {
      return { kind: 'refused', detail: copy('leadership_moderation.session_ended_body') };
    }
    return {
      kind: 'refused',
      detail:
        (outcome.kind === 'refused' ? outcome.detail : null) ??
        copy('leadership_moderation.queue.decision_unavailable'),
    };
  }

  return (
    <main className="pulse-set-page" data-testid={REVIEW_QUEUE_TESTID} aria-labelledby={HEADING_ID}>
      <h1 className="pulse-set-title" id={HEADING_ID} ref={headingRef} tabIndex={-1}>
        {copy('leadership_moderation.queue.heading')}
      </h1>
      <p className="pulse-set-intro">{copy('leadership_moderation.queue.intro')}</p>
      {/* In the page from the first render, so what arrives in it is announced. */}
      <p className="pulse-set-announcement" role="status">
        {announcement}
      </p>

      {load.kind === 'loading' ? (
        <p className="pulse-set-status" role="status">
          {copy('leadership_moderation.queue.loading')}
        </p>
      ) : load.kind === 'session-ended' ? (
        <StateNotice
          variant="flat"
          title={copy('leadership_moderation.session_ended_title')}
          body={copy('leadership_moderation.session_ended_body')}
        />
      ) : load.kind === 'error' ? (
        <StateNotice
          variant="flat"
          body={load.detail ?? copy('leadership_moderation.queue.unavailable')}
        />
      ) : load.items.length === 0 ? (
        <StateNotice
          variant="flat"
          title={copy('leadership_moderation.queue.empty_title')}
          body={copy('leadership_moderation.queue.empty_body')}
        />
      ) : (
        <ul
          className="pulse-moderation-list"
          data-testid={REVIEW_QUEUE_LIST_TESTID}
          aria-label={copy('leadership_moderation.queue.list_label')}
        >
          {load.items.map((item) => (
            <li className="pulse-moderation-item" key={item.answer_id}>
              <p className="pulse-moderation-section">{item.section_label}</p>
              <CommentCard
                text={item.text}
                status="flagged"
                flagReason={QUEUED_FLAG}
                decide={(decision) => decide(item, decision)}
              />
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

/** What a read of the queue means for the page. A refusal is never the empty state. */
function loadFrom(read: ReviewQueueRead): Load {
  if (read.kind === 'session-ended') return { kind: 'session-ended' };
  if (read.kind === 'unavailable') return { kind: 'error', detail: read.detail };
  return { kind: 'queue', items: read.items };
}
