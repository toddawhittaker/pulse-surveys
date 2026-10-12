import type { JSX, ReactNode } from 'react';

import type { AttentionCardView } from '../api/leadership';
import { copy, fillCopy } from '../copy/leadershipRollupCopy';
import './leadershipRollup.css';

/**
 * SPEC §7.6's `AttentionList`: §5.6's cards for one node, or its calm empty state.
 *
 * `design/AttentionList.dc.html` is the contract: one card per rule met by one
 * section, each naming its rule in mono marigold and, for a trend rule, its
 * stream in a quiet chip; the section beneath; and a link to that section's
 * Monday report. **Never ranked**: the cards are in the server's order, by
 * course, section and rule, and nothing here reorders them (§4.1 item 4).
 *
 * **Every word on a card is the server's or this surface's frame.** The rule's
 * name (`rule_name`) and the empty sentence (`attention_empty`) arrive in the
 * payload, so §5.6's four names are written once, in `app/copy/leadership_rollup.py`.
 * A stream chip is the payload's own token, `INSTRUCTOR` or `COURSE`, which the
 * mockup draws upper-case anyway.
 *
 * **No figure on a card.** The mockup's detail line ("8 of 23 responded", "3.9
 * → 3.6 → 3.4") is not in the payload: a card says which rule a section meets
 * and where its report is, and the report is where its figures are read.
 */
export function AttentionList({
  cards,
  empty,
  reportLink,
}: {
  /** The node's cards, in the payload's order. */
  readonly cards: readonly AttentionCardView[];
  /** The calm sentence the payload sends when no card is due. */
  readonly empty: string | null;
  /** The link to one card's section-week report. */
  readonly reportLink: (card: AttentionCardView, children: ReactNode) => JSX.Element;
}): JSX.Element {
  if (cards.length === 0) {
    return (
      <div className="pulse-attention-empty">
        <svg width="160" height="24" aria-hidden="true" focusable="false">
          <line className="pulse-attention-empty-line" x1="2" y1="12" x2="146" y2="12" />
          <circle className="pulse-attention-empty-dot" cx="153" cy="12" r="3.5" />
        </svg>
        {empty === null ? null : <p className="pulse-attention-empty-text">{empty}</p>}
      </div>
    );
  }
  return (
    <ul className="pulse-attention-list">
      {cards.map((card) => (
        <li
          key={`${card.section_id}:${card.rule}:${card.stream ?? ''}`}
          className="pulse-attention-card"
        >
          <div className="pulse-attention-head">
            {card.stream === null ? null : (
              <span className="pulse-attention-stream">{card.stream}</span>
            )}
            <span className="pulse-attention-rule">{card.rule_name}</span>
          </div>
          <p className="pulse-attention-section">
            {card.course_name} · {card.section_code}
          </p>
          <p className="pulse-attention-week">
            {fillCopy('leadership_rollup.attention.week', {
              week: String(card.course_week).padStart(2, '0'),
            })}
          </p>
          {reportLink(card, copy('leadership_rollup.attention.open'))}
        </li>
      ))}
    </ul>
  );
}
