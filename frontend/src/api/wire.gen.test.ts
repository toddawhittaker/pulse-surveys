// @vitest-environment node
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

/**
 * The committed `wire.gen.ts` is what the pinned generator makes of the
 * committed `openapi.json` (ADR 0185).
 *
 * It runs the real command line, the same invocation as the package's
 * `gen:wire` script, into a temporary file and compares bytes. The
 * programmatic API would be a second way of generating that nobody runs, and
 * could agree with itself while the script disagreed.
 *
 * The backend half, that `openapi.json` is what the backend publishes now, is
 * `tests/unit/test_the_committed_openapi_json_is_current.py`.
 */

const FRONTEND_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
// The workspace's own `.bin`: the lockfile installs this package under
// `frontend/node_modules` rather than hoisting it, and `npm run gen:wire`
// finds it on the same path. If that ever moves, this fails loudly (ENOENT).
const GENERATOR = join(FRONTEND_ROOT, 'node_modules/.bin/openapi-typescript');
const INPUT = 'src/api/openapi.json';
const COMMITTED = join(FRONTEND_ROOT, 'src/api/wire.gen.ts');

describe('the generated wire types', () => {
  it('describe the API rather than nothing', () => {
    // Two empty files compare equal, so the comparison below means nothing
    // unless the committed one actually holds the schemas.
    expect(readFileSync(COMMITTED, 'utf8')).toContain('export interface components');
  });

  it('are what the generator makes of the committed openapi.json', () => {
    const scratch = mkdtempSync(join(tmpdir(), 'wire-gen-'));
    try {
      const output = join(scratch, 'wire.gen.ts');
      execFileSync(GENERATOR, [INPUT, '--immutable', '-o', output], { cwd: FRONTEND_ROOT, stdio: 'pipe' });
      const regenerated = readFileSync(output, 'utf8');
      expect(
        regenerated === readFileSync(COMMITTED, 'utf8'),
        'src/api/wire.gen.ts is stale against src/api/openapi.json. ' +
          'Regenerate it with: npm run gen:wire --workspace frontend',
      ).toBe(true);
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  });
});
