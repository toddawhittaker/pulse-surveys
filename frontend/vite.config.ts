import { fileURLToPath } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// The repository root, one level above this package. `design/tokens.css` lives
// there and `src/styles.css` imports it, which is the whole reason this path is
// needed: SPEC §7.6 makes that file the single source for palette, type,
// spacing, radii, shadow and the focus ring, so the frontend reads the real file
// rather than keeping a copy of it in step.
const REPOSITORY_ROOT = fileURLToPath(new URL('..', import.meta.url));

export default defineConfig({
  // The application is served by the app factory under `/app` (ADR 0086), so
  // every asset URL the build writes has to carry that prefix. Getting this
  // wrong produces a page that loads and then asks for `/assets/…`, which the
  // API answers 404 — a blank screen with a green health check behind it.
  base: '/app/',
  plugins: [react(), tailwindcss()],
  server: {
    fs: {
      // Only the dev server enforces this; `vite build` resolves the import
      // through the CSS pipeline either way. Without it `npm run dev` refuses to
      // read `design/tokens.css` because it sits outside this package.
      allow: [REPOSITORY_ROOT],
    },
  },
});
