# 0121 — The copy inventory reads the frontend by strict text parse, from the disk

**Status:** Accepted — E2-11 (2026-09-03).

## Context

SPEC §4.1 items 4 and 5 become assertions in E2-11, checked over every shipped
user-facing string. The backend half is easy: `app.copy` is a Python package
and the collector imports it. The frontend half is a TypeScript module
(`frontend/src/copy/studentSurvey.ts`, the shape E2-10 settled), and the
assertions run inside the §4.1 invariant pass — an isolated, serial pytest run
whose job must fail on the rule, not on its instrument. The spec does not say
how a Python test reads a TypeScript file, and reasonable engineers choose
differently here.

## Decision

The collector parses the copy module as text, in Python, with a parser that
**refuses what it cannot classify** rather than skipping it: every line is an
entry, a comment, a string continuation, structure, or a refusal. Outside the
object literal, a code line passes only if it carries no quote character at
all. Escapes are decoded — surrogate pairs recombined, lone surrogates
refused — so a string is swept as the browser would render it. Enumeration is
from the directory on disk (the `.ts` family, recursively), never from git,
and a second independent any-suffix walk reddens on any file the collector did
not read.

## Alternatives rejected

- **Evaluating the module with Node.** Truest to TypeScript semantics, but it
  adds a Node runtime to the §4.1 invariant pass — a new moving part inside
  the gate that may never be skipped, failing on toolchain state rather than
  on copy.
- **Enumerating tracked files via git.** The battery proves red with planted
  files; an untracked plant is invisible to `git ls-files`, so the proof runs
  would go green for the wrong reason.
- **A hand-kept list of copy files or surfaces.** Shrinkable by an edit to the
  thing it inventories (`docs/MISTAKES.md` entry 35).

## Consequences

- A string assembled at runtime, a literal written into a component, or an
  aria label built in JSX is invisible to the inventory; these limits are
  stated in the test module's docstring rather than discovered.
- The parser is deliberately narrower than TypeScript: a legitimate future
  shape (an `import` with its quoted path, say) is refused loudly and the
  parser is extended in a reviewed change, which is the fail-closed direction.
- A copy file that drifts from the settled flat-mapping shape breaks the
  invariant pass rather than shipping unswept — the cost of the strictness is
  paid at the moment of drift, visibly.
- One residue is recorded in `docs/tickets/e2/deferred.md`: the walks do not
  descend a symlinked directory.
