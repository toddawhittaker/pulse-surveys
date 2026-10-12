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

// **The cascade layer order is decided by `public/layer-order.css`**, which
// `index.html` links before any other stylesheet and which names every layer
// once: a layer's precedence is the order it is first named, and the build
// splits the stylesheet per page, so a lazily loaded page's sheet can be linked
// ahead of this one. That file is the place to change the order. Importing the
// application's stylesheet (which pulls in `design/tokens.css` and Tailwind)
// before the router still keeps the entry chunk's own sheets in a readable order.
import './styles.css';

import { captureSessionFromFragment } from './lib/session';
import { router } from './router';

/**
 * The entry point — SPEC §13's `main.tsx`.
 *
 * **There is no generated client and no query cache.** ADR 0117 settled
 * this, and ADR 0185 superseded it in part: each screen's calls are
 * written by hand in `api/`, and only their wire types are generated from the
 * backend's OpenAPI document. TanStack Query is not in the closure. What is
 * here is the fetch each screen makes for itself.
 *
 * The one thing that happens before the router mounts is capturing the session
 * an entry door handed over in the URL fragment: it is lifted into
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
