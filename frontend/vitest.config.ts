import { defineConfig, mergeConfig } from 'vitest/config';

import viteConfig from './vite.config';

/**
 * The frontend's unit-test configuration — ticket E4-16.
 *
 * `mergeConfig` layers a `test` block onto the real build configuration
 * rather than duplicating it, so the plugins, the `/app/` base and the
 * `server.fs.allow` reach into `design/tokens.css` (all load-bearing for the
 * application, none of it for a test run) stay exactly what `vite.config.ts`
 * says they are. Nothing here is a second copy of that file.
 *
 * `environment: 'jsdom'` gives every test a DOM to render into — plain
 * Node has no `document` — and is scoped to this package rather than the
 * root, which runs the SPEC §9.2 Playwright suite against a real browser and
 * has no unit tests of its own to want one.
 *
 * No `globals: true`: every test file imports `describe`, `it`, `expect` and
 * friends from `vitest` explicitly, the same way every other module in this
 * repository names what it depends on rather than reading it off an ambient
 * global.
 */
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
      globals: false,
    },
  }),
);
