// @vitest-environment node
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

/**
 * No wire type in `api/` is declared by hand (ADR 0185).
 *
 * Every exported type in the client modules is either an alias of, or a pick
 * from, the generated `components['schemas']`, or one of the frontend's own
 * outcome unions, which by convention are named `…Read` or `…Outcome`. An
 * `interface` of any kind is refused outright: there is no wire shape one could
 * describe that the generated module does not already describe.
 *
 * The search reads source text, so it carries a canary per module: a type it
 * must find on each side of the rule. A pattern that has stopped matching would
 * otherwise pass by finding nothing to object to.
 */

const API_DIR = dirname(fileURLToPath(import.meta.url));

/** The client modules: everything in `api/` except tests and the generated file. */
function clientModules(): string[] {
  return readdirSync(API_DIR)
    .filter((name) => name.endsWith('.ts'))
    .filter((name) => !name.endsWith('.test.ts') && name !== 'wire.gen.ts')
    .sort();
}

/** The exported type declarations of one source text, each with its right-hand side. */
function exportedTypes(source: string): { name: string; rhs: string }[] {
  const found: { name: string; rhs: string }[] = [];
  const declaration = /^export type (\w+)(?:<[^=]*>)?\s*=/gm;
  for (let match = declaration.exec(source); match !== null; match = declaration.exec(source)) {
    const name = match[1];
    if (name === undefined) continue;
    const start = match.index + match[0].length;
    // A declaration here runs to the blank line after it; a union or an object
    // type spans several lines and contains semicolons of its own.
    const end = source.indexOf('\n\n', start);
    found.push({ name, rhs: source.slice(start, end === -1 ? undefined : end) });
  }
  return found;
}

function isOutcome(name: string): boolean {
  return name.endsWith('Read') || name.endsWith('Outcome');
}

function readsTheGeneratedModule(rhs: string): boolean {
  return rhs.includes("components['schemas']") || rhs.includes('Schemas[');
}

/** One wire alias and one outcome type each module certainly declares. */
const CANARIES: Record<string, { alias: string; outcome: string }> = {
  'instructor.ts': { alias: 'InstructorReportView', outcome: 'ReportRead' },
  'leadership.ts': { alias: 'ComparisonSetDetailView', outcome: 'ComparisonSetDeleteOutcome' },
  'student.ts': { alias: 'StudentSurveyView', outcome: 'SubmitOutcome' },
};

describe('the wire types in api/', () => {
  it('are read from every client module, and the sweep can see each side of its rule', () => {
    expect(clientModules()).toEqual(Object.keys(CANARIES).sort());
    for (const [module, canary] of Object.entries(CANARIES)) {
      const types = exportedTypes(readFileSync(join(API_DIR, module), 'utf8'));
      const alias = types.find((type) => type.name === canary.alias);
      const outcome = types.find((type) => type.name === canary.outcome);
      expect(alias && readsTheGeneratedModule(alias.rhs), `${module}: ${canary.alias}`).toBe(true);
      expect(outcome && isOutcome(outcome.name), `${module}: ${canary.outcome}`).toBe(true);
    }
  });

  it.each(clientModules())('%s declares no interface', (module) => {
    const source = readFileSync(join(API_DIR, module), 'utf8');
    expect(source.match(/^[ \t]*(?:export\s+)?interface\s+\w+/gm) ?? []).toEqual([]);
  });

  it.each(clientModules())('%s declares every exported wire type from the generated module', (module) => {
    const handWritten = exportedTypes(readFileSync(join(API_DIR, module), 'utf8'))
      .filter((type) => !isOutcome(type.name))
      .filter((type) => !readsTheGeneratedModule(type.rhs))
      .map((type) => type.name);
    expect(handWritten).toEqual([]);
  });
});
