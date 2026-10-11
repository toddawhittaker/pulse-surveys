import { useId, type JSX } from 'react';

import { copy } from '../copy/leadershipResponseCopy';
import './policyToggle.css';

/**
 * One response-required switch — SPEC §7.6's `PolicyToggle`, editable variant.
 *
 * `design/PolicyToggle.dc.html` is the contract: a title, a quiet line naming
 * what the switch covers, a 44 by 24 track and the sentence saying what "on"
 * does. **There is no read-only variant here on purpose.** A course the reader
 * cannot set is drawn by the page as text with the setter's role, because a
 * disabled switch is still a control the server would refuse (ticket done-when
 * 1); this component is only ever the reader's own to press.
 *
 * It is a button with `role="switch"`, so Space and Enter work and a screen
 * reader hears the state. It holds no state of its own: whether it is on is the
 * server's last answer, and `busy` marks it `aria-disabled` and ignores presses while a change is in
 * flight; it stays focusable, so a keyboard user's place is not lost.
 */
export function PolicyToggle({
  detail,
  ariaLabel,
  checked,
  busy,
  onToggle,
}: {
  /** What the switch covers, in the page's words. */
  readonly detail: string;
  readonly ariaLabel: string;
  readonly checked: boolean;
  readonly busy: boolean;
  readonly onToggle: (next: boolean) => void;
}): JSX.Element {
  const helpId = useId();
  return (
    <div className="pulse-policy-toggle">
      <div className="pulse-policy-toggle__row">
        <div>
          <p className="pulse-policy-toggle__title">{copy('leadership_response.policy.toggle_label')}</p>
          <p className="pulse-policy-toggle__detail">{detail}</p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          aria-label={ariaLabel}
          aria-describedby={helpId}
          aria-disabled={busy}
          className="pulse-policy-toggle__track"
          onClick={() => {
            if (busy) return;
            onToggle(!checked);
          }}
        >
          <span className="pulse-policy-toggle__knob" />
        </button>
      </div>
      <p className="pulse-policy-toggle__help" id={helpId}>{copy('leadership_response.policy.toggle_help')}</p>
    </div>
  );
}
