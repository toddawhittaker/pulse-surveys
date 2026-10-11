import type { JSX } from 'react';

import { StateNotice } from '../../components/StateNotice';
import { copy } from '../../copy/leadershipResponseCopy';

/**
 * What a leadership response page says when the server answered with a refusal
 * instead of its payload: a session that ended, or a signed-in reader in another
 * role (ADR 0196). Never the empty state, because "nothing here" is a claim
 * about the reader that a refusal does not entitle a page to make.
 */
export function ResponseRefusal({
  kind,
}: {
  readonly kind: 'session-ended' | 'not-your-role';
}): JSX.Element {
  return kind === 'session-ended' ? (
    <StateNotice
      variant="flat"
      title={copy('leadership_response.session_ended_title')}
      body={copy('leadership_response.session_ended_body')}
    />
  ) : (
    <StateNotice
      variant="flat"
      title={copy('leadership_response.not_your_role_title')}
      body={copy('leadership_response.not_your_role_body')}
    />
  );
}
