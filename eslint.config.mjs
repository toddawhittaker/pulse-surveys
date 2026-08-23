// The eslint flat config for the TypeScript this repository holds — the
// Playwright harness and the SPEC §9.2 specs (E0-40 decision 2).
//
// The checked file set is the same one `tsconfig.json` includes, deliberately:
// two checkers reading two different lists is how one of them ends up green
// over a file nobody checks, which is the finding E0-40 exists for.
//
// Flat config has no allowlist for traversal — `npx eslint .` walks the working
// directory and asks this file what to do with each file it meets — so the
// scoping is done twice, and both halves are load-bearing. `ignores` keeps the
// walk out of directories that hold JavaScript this repository did not write
// (a Python virtualenv vendors some, and so do the generated report trees), and
// the `files` list on the rule sets below is what decides which files are
// actually checked.

import eslint from '@eslint/js';
import tseslint from 'typescript-eslint';

const CHECKED = ['playwright.config.ts', 'tests/e2e/**/*.ts'];

export default tseslint.config(
  {
    ignores: [
      '**/node_modules/**',
      // A local Python virtualenv. Not in the repository, but `eslint .` walks
      // it, and the JavaScript coverage.py ships inside it is not ours to lint.
      '.venv/**',
      'venv/**',
      // Generated: the Playwright HTML report, its raw results, and the CI
      // report directory.
      'playwright-report/**',
      'test-results/**',
      'reports/**',
      // The E1 scaffold, when it lands, brings its own eslint config. This
      // config is about the root TypeScript, which is the split E0-40 makes.
      'frontend/**',
    ],
  },
  {
    files: CHECKED,
    extends: [eslint.configs.recommended, tseslint.configs.recommendedTypeChecked],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
);
