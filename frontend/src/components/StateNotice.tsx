import type { JSX, ReactNode } from 'react';

/**
 * A calm statement of where a week stands — SPEC §7.6's `StateNotice (flat/beat)`.
 *
 * The signature motif carrying two of its four jobs (`docs/DESIGN_BRIEF.md`):
 * the **flat** line in mist marks a state where nothing has arrived — no window
 * open, a window that has shut — and the **beat** line in marigold, drawn on
 * once over 600ms, marks the week landing. One motif, and no other decoration.
 *
 * `design/Usage Rules.md` §4 governs the words this carries on a student
 * surface: "Missed weeks state facts and the next window; no guilt language."
 * Nothing here counts what was missed and nothing asks for a reason.
 *
 * The drawing is CSS, so `design/tokens.css`'s reduced-motion switch removes it
 * with everything else; there is no JavaScript animation to escape that switch.
 *
 * `title` is optional. Some of these states are a sentence the server sent —
 * a closed window, a week already recorded — and inventing a heading to sit
 * above one would be this screen writing copy for a refusal it did not decide.
 */
export function StateNotice({
  variant,
  title,
  body,
  children,
}: {
  readonly variant: 'flat' | 'beat';
  readonly title?: string;
  readonly body: string;
  readonly children?: ReactNode;
}): JSX.Element {
  return (
    <div className="pulse-state-notice" data-variant={variant}>
      {variant === 'beat' ? <BeatLine /> : <FlatLine />}
      {title === undefined ? null : <p className="pulse-state-title">{title}</p>}
      <p className="pulse-state-body">{body}</p>
      {children}
    </div>
  );
}

/** The pulse line at rest: nothing has arrived yet. */
function FlatLine(): JSX.Element {
  return (
    <svg
      className="pulse-line pulse-line-flat"
      width="160"
      height="36"
      viewBox="0 0 160 36"
      aria-hidden="true"
      fill="none"
    >
      <line x1="2" y1="24" x2="146" y2="24" stroke="var(--mist)" strokeWidth="2" strokeLinecap="round" />
      <circle cx="153" cy="24" r="3.5" fill="var(--mist)" />
    </svg>
  );
}

/** The pulse line beating: this week is in. */
function BeatLine(): JSX.Element {
  return (
    <svg
      className="pulse-line pulse-line-beat"
      width="160"
      height="36"
      viewBox="0 0 160 36"
      aria-hidden="true"
      fill="none"
    >
      <path
        d="M2 24 H62 L74 8 L86 32 L94 24 H146"
        pathLength={1}
        stroke="var(--marigold)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="153" cy="24" r="3.5" fill="var(--marigold)" />
    </svg>
  );
}
