# 0151 — The frontend gains a unit-test runner

## Context

E2 deliberately shipped without a frontend unit-test runner. The cost was
stated at the time and carried forward in
[`docs/tickets/e3/carried-from-e2.md`](../tickets/e3/carried-from-e2.md):
component-level regressions surface only in a browser run, never in a unit
run, and the revisit trigger was named as "when a screen's logic outgrows
what the end-to-end suite pins cheaply."

E4 is that moment, structurally rather than by one screen growing large: it
schedules four component tickets — E4-08, E4-09 and E4-10 among them, three
of them building in parallel — whose acceptance criteria are component
tests, and none of which can execute a test today.
`frontend/package.json` declares `dev`, `build`, `typecheck` and `lint` and
nothing else, and the root Playwright configuration runs `tests/e2e/` only,
against a real browser, which is not where a unit test belongs.

The spec is silent on which runner the frontend uses, and a reasonable
engineer could choose differently — this record exists because the choice is
contestable, not because the spec leaves a gap it should fill. The runner
also has to arrive before those three parallel tickets start, or each writes
its own answer to how a component is rendered and asserted against, which is
the drift this ticket exists to prevent.

## Decision

**Vitest**, with **jsdom** as the DOM environment and
**`@testing-library/react`** for rendering, all added as exactly pinned
`devDependencies` of the `frontend` workspace, resolved into the repository's
one `package-lock.json` (ADR 0083 — no lockfile of `frontend/`'s own).
`frontend/package.json` gains `"test": "vitest run"`, and
`.github/workflows/ci.yml`'s `lint-frontend` job gains one step running
`npm run test --workspace frontend`, guarded by the same
`needs.changed.outputs.inert != 'true'` condition every other step in that
job already carries.

Vitest shares the Vite toolchain the frontend already builds with — its
configuration is `frontend/vitest.config.ts`, layered onto
`vite.config.ts` with `mergeConfig` rather than duplicating it, so the
plugins, the `/app/` base and the `server.fs.allow` path into
`design/tokens.css` stay exactly what the build configuration says they are.
Adding it brings no second build system and no second compiler.

One proof test, `frontend/src/components/WeekEyebrow.test.tsx`, renders an
existing component with real props and asserts the words a reader actually
sees, so the runner is shown running something real rather than an empty
suite.

**The conventions the three component tickets build to:**

- A component's test file sits beside it, named `<Component>.test.tsx`.
  `WeekEyebrow.test.tsx` beside `WeekEyebrow.tsx` is the pattern, not an
  exception to it.
- A fixture module, where one is needed, sits beside the test file it
  serves rather than in a shared top-level fixtures directory — a component
  test's data is that component's concern.
- Rendering goes through `@testing-library/react`'s `render`, into the
  jsdom environment vitest provides; no test manages a DOM root or an
  `act()` call by hand.
- Every test file imports what it uses from `vitest` explicitly —
  `describe`, `it`, `expect` and the rest. `globals` stays off, so a test
  file's dependencies are visible at its own top rather than assumed from a
  runner-wide setting.
- Assertions query by role or by visible text, the way a person or an
  assistive technology reaches the same content, rather than by a
  component's internal structure or a test-only selector.

## Alternatives rejected

**Jest.** The default choice for a React project historically, and rejected
here because it is a second build toolchain rather than a second dependency:
Jest does not read `vite.config.ts` and would need its own transform
pipeline, its own module resolution, and its own answer to the path alias
and asset-import handling Vite already does for the application. Two
bundlers agreeing about how to interpret the same source tree is exactly the
kind of drift ADR 0083 already rejected once, for the lockfile; Jest would
reopen the same question for the compiler.

**Playwright component testing.** Rejected because it ties a unit test to
the end-to-end stack's runtime — a real browser, launched per test file —
which is the cost this ticket exists to avoid paying for logic that does not
need one. The end-to-end suite already owns the browser-level guarantee;
giving component tests the same weight would make the unit run only nominally
cheaper than the suite it was meant to sit below.

**Plain `react-dom` test rendering, with no testing library.** The cheapest
possible dependency footprint, and rejected because it is not actually free:
`react-dom/client`'s `createRoot` and `act()` have to be managed by hand in
every test file, and mounting into a real `document` node has to be set up
and torn down the same way in every test file. Three component tickets
building in parallel would each get that boilerplate slightly differently
wrong, which is the same convention-drift risk this record exists to close
off for rendering, not just for tooling choice.

## Consequences

- The added dependency tree is dev-only. `frontend/package.json`'s
  `dependencies` are unchanged, and the production build's bundle is
  unchanged by this ticket — a test runner ships in no image.
- `frontend/vitest.config.ts` and `frontend/eslint.config.mjs`'s and
  `frontend/tsconfig.json`'s file lists are extended to cover it, in the
  same change, so the checked-file-set discipline those files already state
  for themselves is not quietly narrowed by a new file arriving beside them.
- The TypeScript 7 wait (carried separately, untouched by this ticket) still
  constrains nothing about *what* runs — it is a compiler version, not a
  test runner — but every package this ticket adds resolves against the
  pinned `typescript` 6.0.3 without floating a range, the same discipline
  every other Node dependency in this repository already holds to.
- No automated guard checks arbitrary devDependencies for exact pins; the
  pin discipline for `vitest`, `jsdom` and `@testing-library/react` is
  reviewed against `CLAUDE.md`'s pinning rule the way any other dependency
  addition is.
