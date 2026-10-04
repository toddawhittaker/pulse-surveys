import type { JSX } from 'react';

/**
 * The short marigold pulse line the brief puts under a page title.
 *
 * Decorative, so hidden from assistive technology. Its size and placement come
 * from `.pulse-line-divider` in `styles.css`, and a page may adjust it under its
 * own root class.
 */
export function PulseDivider(): JSX.Element {
  return (
    <svg
      className="pulse-line pulse-line-divider"
      width="120"
      height="14"
      viewBox="0 0 120 14"
      aria-hidden="true"
      fill="none"
    >
      <path
        d="M1 10 H52 L60 3 L68 10 H106"
        stroke="var(--marigold)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="112" cy="10" r="3.5" fill="var(--marigold)" />
    </svg>
  );
}
