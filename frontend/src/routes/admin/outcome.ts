import type { Answer } from '../../api/admin';
import { copy } from '../../copy/adminPeople';
import type { Gate } from './AdminPage';

/**
 * Says what a write answered and reports whether it landed.
 *
 * A refusal is announced in the server's own sentence; a gate answer hands the
 * page over to the gate's notice; a request that never arrived says so without
 * claiming the change was or was not recorded.
 */
export function settle(
  answer: Answer<unknown>,
  done: string,
  announce: (message: string) => void,
  onGate: (gate: Exclude<Gate, null>) => void,
): boolean {
  if (answer.kind === 'ok') {
    announce(done);
    return true;
  }
  if (answer.kind === 'session-ended' || answer.kind === 'not-your-role') {
    onGate(answer.kind);
  } else if (answer.kind === 'refused') {
    announce(answer.detail);
  } else {
    announce(copy('admin_people.page.write_unavailable'));
  }
  return false;
}
