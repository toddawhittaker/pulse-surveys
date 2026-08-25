// The frontend's own eslint flat config (ADR 0086, and ADR 0083 for why the
// packages are the root's).
//
// The root `eslint.config.mjs` ignores `frontend/**` and reads the Playwright
// harness and the SPEC §9.2 specs; this one reads the application. Two configs
// rather than one because the two trees are different languages in practice —
// JSX, the DOM and the React rules here, Node and Playwright there — and E0-40
// is the ticket about a checker pointed at the wrong tree.
//
// `eslint`, `@eslint/js` and `typescript-eslint` are the root package's
// dependencies and resolve by npm workspace hoisting. One eslint and one
// TypeScript for the whole repository is the point of ADR 0083's single
// lockfile, so nothing is pinned twice here.
//
// The rule sets are scoped with `files:` for the same reason the root config
// gives: flat config has no allowlist for traversal, so `eslint .` walks this
// directory and asks this file what to do with everything it meets.

import eslint from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import tseslint from 'typescript-eslint';

const CHECKED = ['src/**/*.ts', 'src/**/*.tsx', 'vite.config.ts'];

export default tseslint.config(
  {
    ignores: [
      '**/node_modules/**',
      // The production build's output. It is gitignored, it is generated, and
      // linting it would report on the closure rather than on this repository.
      'dist/**',
    ],
  },
  {
    files: CHECKED,
    extends: [eslint.configs.recommended, tseslint.configs.recommendedTypeChecked],
    languageOptions: {
      parserOptions: {
        // The typed rules need a program. `projectService` finds this package's
        // `tsconfig.json`, so the file set eslint type-checks is the file set
        // `npm run typecheck` reads — the two checkers reading two different
        // lists is how one of them ends up green over a file nobody checks.
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
  {
    files: ['src/**/*.tsx', 'src/**/*.ts'],
    ...reactHooks.configs.flat.recommended,
  },
);
