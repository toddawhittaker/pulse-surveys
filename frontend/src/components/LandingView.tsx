import type { JSX } from 'react';

import type { Landing } from '../lib/landings';

/**
 * One empty landing view: a landmark, a heading, the motif, and one line.
 *
 * **The role is a property, never a derivation.** The wiring contract with
 * E1-08/E1-09/E1-13 is that the backend decides which landing a person gets and
 * hands over a route; this component renders the landing it is given and asks
 * nothing about who is looking. There is deliberately no place here for a claim,
 * a token or a role lookup — a frontend that re-derived role would be a second
 * authority on a question SPEC §2.1 gives to one.
 *
 * Accessibility is in-slice (SPEC §14.2 item 4), not deferred to E13: one
 * `main` landmark, labelled by the view's own heading, and exactly one
 * first-level heading inside it. Nothing here is interactive, so there is
 * nothing for a keyboard to reach past — the first screen with a control is
 * E2's survey, and the focus ring it will need is already in
 * `design/tokens.css`.
 */
const HEADING_ID = 'pulse-landing-heading';

export function LandingView({ landing }: { readonly landing: Landing }): JSX.Element {
  return (
    <main className="pulse-landing" data-testid={landing.testid} aria-labelledby={HEADING_ID}>
      <h1 id={HEADING_ID}>{landing.heading}</h1>
      <svg
        className="pulse-line"
        width="120"
        height="8"
        viewBox="0 0 120 8"
        aria-hidden="true"
        fill="none"
        stroke="var(--mist)"
        strokeWidth="2.5"
        strokeLinecap="round"
      >
        <path d="M2 4 H118" />
      </svg>
      <p>{landing.emptyState}</p>
    </main>
  );
}
