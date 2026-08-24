# E1-02 — Node workspace layout, and `@types/node` tracks the runtime

**ID:** E1-02
**Branch:** `e1/node-workspace-layout`
**Depends on:** nothing
**Security-relevant:** none line-by-line; gate fidelity is the risk here
(MISTAKES entries 36 and 25), not confidentiality.

## Context

E0 left the Node toolchain at the repository root — `package.json`,
`package-lock.json`, `playwright.config.ts`, `tsconfig.json`, eslint — because
PR #61 put the first TypeScript there and E0-40 then pointed every Node-facing
CI gate at the root. SPEC §13 plans `frontend/` with its own `package.json`.
Before the frontend scaffold (E1-04) exists, one decision settles where Node
lives, because moving it later moves the gates again and every move is a chance
for a probe to answer over a tree that no longer holds the thing (MISTAKES
entry 36).

Separately, Dependabot #81 (`@types/node` 20 → 26) was green because nothing
ties `@types/node` to the Node 20 CI runs. The triage decision (entry 4 of
[`../deps-triage-2026-08-24.md`](../deps-triage-2026-08-24.md), whose "done
when" governs) is that types track the runtime's Node major.

Read first: SPEC §13 (the target tree); `docs/tickets/e0/E0-40-*.md` (which
gates probe what today); MISTAKES entries 36, 25, 13; ADR 0005 (one lockfile
discipline); the triage record entry 4.

## Scope

- **Decide the layout once, with an ADR.** The constraint set: §13's
  `frontend/` package exists for E1-04 to fill; the e2e tooling keeps working;
  there is **exactly one `package-lock.json`** in the repository afterwards —
  two lockfiles resolving the same package differently is MISTAKES entry 25 —
  and every CI probe and gate that reads a Node path reads the path where the
  thing now is, in the same change. An npm-workspaces root with `frontend/` as
  a member satisfies all four and is the expected shape; if the builder chooses
  differently, the ADR says what that bought.
- **`@types/node` is tied to `NODE_VERSION`** by a guard in the shape of
  `tests/unit/test_image_pins_agree.py`: the major of the pinned `@types/node`
  must equal the major of the `NODE_VERSION` CI uses, read from both files
  structurally, and proven by mutation (change either side, watch it fail).
- **`dependabot.yml` ignores `@types/node` semver-majors**, so the bump arrives
  only when `NODE_VERSION` moves. This is an ignore rule — a coverage
  reduction — so the commit that adds it says what is given up and why
  (CLAUDE.md's gate rule), and the guard above is what makes the reduction
  safe.
- Every moved config keeps its exact pins (E0-40's toolchain pinning survives
  the move byte-for-byte, or the diff says which pin moved and why).

## Acceptance criteria

1. After the change: one lockfile, all Node gates and detect probes green, and
   `npx playwright test --list` (or the repo's equivalent collection command)
   still finds the three e2e specs.
2. The `@types/node` guard fails when either side's major moves alone; both
   directions proven.
3. The Dependabot ignore exists, scoped to `@types/node` majors only.
4. If any file a CI probe reads moved, the probe moved in the same commit, and
   the probe's negative case was re-proven (plant nothing → require a no; the
   full rule is MISTAKES entry 36).

## Out of scope

- The frontend application itself, and the four gate flips (E1-04).
- The TypeScript 7 / typescript-eslint bump (E1-03).
- Any change to Python tooling or the Python 3.14 question (unscheduled;
  triage entry 5).
