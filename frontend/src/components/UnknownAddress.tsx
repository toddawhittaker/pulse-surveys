import type { JSX } from 'react';

import { copy } from '../copy/unknownAddress';

/**
 * What `/app` itself, and any address under it that names no view, renders.
 *
 * Nobody is handed this address: the doors decide a landing role and redirect to
 * one of the five role routes (E1-08/E1-09). It exists because the server
 * answers `index.html` for every path under the mount so that the client router
 * can read the path, which means the client router is what has to say something
 * when the path names nothing.
 *
 * It carries no landing testid, deliberately — the same property
 * `backend/app/services/landing.py`'s refusal page has, and for the same reason:
 * a page that answered to one of the five testids would be claiming to be a view
 * somebody was sent to.
 *
 * Both sentences were written into the JSX below until E4-12, which moved them
 * into `../copy/unknownAddress.ts` — the directory the copy inventory walks —
 * and left the words alone.
 */
export function UnknownAddress(): JSX.Element {
  return (
    <main className="pulse-landing" data-testid="pulse-unknown-address">
      <h1>{copy('unknown_address.heading')}</h1>
      <p>{copy('unknown_address.body')}</p>
    </main>
  );
}
