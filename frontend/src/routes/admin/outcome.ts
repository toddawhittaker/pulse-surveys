import { useId, useState } from 'react';

import type { AdminOutcome } from '../../api/admin';
import { copy } from '../../copy/adminPeople';
import type { Gate } from './AdminPage';

/**
 * One write control's refusal, shown beside the control that sent it.
 *
 * The page's live region announces every outcome, but an announcement is gone
 * once said; a refusal also stays next to its control, and the control names it
 * with `aria-describedby`, so a reader who returns to it finds out why
 * (WCAG 2.2 SC 3.3.1).
 */
export interface WriteRefusal {
  /** The id of the paragraph the refusal is shown in. */
  readonly id: string;
  /** The refusal, or the empty string when the last write landed or none was sent. */
  readonly text: string;
  readonly show: (text: string) => void;
}

/** A control's refusal state: empty until a write it sent is refused. */
export function useWriteRefusal(): WriteRefusal {
  const id = useId();
  const [text, show] = useState('');
  return { id, text, show };
}

/** What a control's `aria-describedby` names: its refusal, while there is one. */
export function describedBy(refusal: WriteRefusal): string | undefined {
  return refusal.text === '' ? undefined : refusal.id;
}

/**
 * Says what a write answered and reports whether it landed.
 *
 * A refusal is announced in the server's own sentence and, where the caller
 * passes its control's refusal, shown beside that control too; a gate answer
 * hands the page over to the gate's notice; a request that never arrived says
 * so without claiming the change was or was not recorded.
 */
export function settle(
  answer: AdminOutcome<unknown>,
  done: string,
  announce: (message: string) => void,
  onGate: (gate: Exclude<Gate, null>) => void,
  refusal?: WriteRefusal,
): boolean {
  if (answer.kind === 'ok') {
    refusal?.show('');
    announce(done);
    return true;
  }
  if (answer.kind === 'session-ended' || answer.kind === 'not-your-role') {
    onGate(answer.kind);
    return false;
  }
  const said = answer.kind === 'refused' ? answer.detail : copy('admin_people.page.write_unavailable');
  refusal?.show(said);
  announce(said);
  return false;
}
