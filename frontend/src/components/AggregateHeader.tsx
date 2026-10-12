import type { JSX, ReactNode } from 'react';

import './leadershipRollup.css';

/**
 * SPEC §7.6's `AggregateHeader`: a roll-up node's name, its scope line, the
 * pulse motif, and its trend beneath.
 *
 * `design/AggregateHeader.dc.html` is the contract. The name is a second-level
 * heading here rather than the mockup's first: the roll-up page's one `h1` is
 * the page's own ("Your roll-up"), and the node a reader has chosen is a part
 * of it. The scope line is the server's row label for the node (SPEC §2.1), so
 * a count on it is a count of sections, courses, prefixes or departments and
 * never of people. The trend arrives as `children`, because which lines it
 * draws is the page's decision (the cohort and the named set).
 */
export function AggregateHeader({
  headingId,
  name,
  scopeLine,
  children,
}: {
  /** The heading's id, so the region it names can say so. */
  readonly headingId: string;
  readonly name: string;
  readonly scopeLine: string;
  readonly children?: ReactNode;
}): JSX.Element {
  return (
    <div className="pulse-aggregate-header">
      <h2 className="pulse-aggregate-name" id={headingId} tabIndex={-1}>
        {name}
      </h2>
      <p className="pulse-aggregate-scope">{scopeLine}</p>
      <svg
        className="pulse-aggregate-mark"
        width="120"
        height="14"
        aria-hidden="true"
        focusable="false"
      >
        <path d="M1 10 H52 L60 3 L68 10 H106" />
        <circle cx="112" cy="10" r="3.5" />
      </svg>
      {children}
    </div>
  );
}
