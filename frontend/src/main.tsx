import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { RouterProvider } from '@tanstack/react-router';

import { captureSessionFromFragment } from './lib/session';
import { router } from './router';
import './styles.css';

/**
 * The entry point — SPEC §13's `main.tsx`.
 *
 * There is no data fetching, no client generated from the OpenAPI schema and no
 * query cache: E1 has nothing to fetch, and the ticket says so. What goes here
 * when there is something is E2's decision to make against a real screen.
 *
 * The one thing that does happen before the router mounts is capturing the
 * session an entry door handed over in the URL fragment (E1-08): it is lifted
 * into `sessionStorage` and stripped from the address bar first, so the token is
 * out of the history entry the router then reads. See `lib/session.ts`.
 */

captureSessionFromFragment();

const container = document.getElementById('root');

// Loud rather than blank. Vite writes `index.html` and this element is in it, so
// a missing root means the served document is not the built one — which is the
// shape a misconfigured static mount produces, and a page that quietly rendered
// nothing would look like an application that loaded and had nothing to say.
if (container === null) {
  throw new Error(
    'No #root element in the served document, so the application cannot mount. The document ' +
      'being served is not the one Vite built.',
  );
}

createRoot(container).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
