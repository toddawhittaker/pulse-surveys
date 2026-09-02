import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { RouterProvider } from '@tanstack/react-router';

// The three faces docs/DESIGN_BRIEF.md names, self-hosted (ADR 0116). Latin
// subset, normal style, and only the weights the brief gives each face a job at:
// Literata 600/700 for display, Schibsted Grotesk 400/500 for body, Spline Sans
// Mono 400/500 for every number. They are imported here rather than linked from
// `index.html` so the bundler emits them beside the bundle and the browser
// fetches them from this origin — a `<link>` to a font host would be a
// third-party request made on a student's behalf from inside their institution's
// page, which is the alternative that record rejects. `design/tokens.css` is
// still where the families are named; nothing here declares a family.
import '@fontsource/literata/latin-600.css';
import '@fontsource/literata/latin-700.css';
import '@fontsource/schibsted-grotesk/latin-400.css';
import '@fontsource/schibsted-grotesk/latin-500.css';
import '@fontsource/spline-sans-mono/latin-400.css';
import '@fontsource/spline-sans-mono/latin-500.css';

import { captureSessionFromFragment } from './lib/session';
import { router } from './router';
import './styles.css';

/**
 * The entry point — SPEC §13's `main.tsx`.
 *
 * **There is still no generated client and no query cache.** E1 had nothing to
 * fetch and left the question to E2's first real screen; E2-10 answered it, and
 * ADR 0117 is the record: the weekly survey calls two endpoints by hand from
 * `api/student.ts`, and neither an OpenAPI generator nor TanStack Query is in
 * the closure. What is here is the fetch each screen makes for itself.
 *
 * The one thing that happens before the router mounts is capturing the session
 * an entry door handed over in the URL fragment (E1-08): it is lifted into
 * `sessionStorage` and stripped from the address bar first, so the token is out
 * of the history entry the router then reads. See `lib/session.ts`.
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
