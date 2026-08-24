# E1-03 — TypeScript 7 with typescript-eslint, one change

**ID:** E1-03
**Branch:** `e1/typescript-7-pair`
**Depends on:** E1-02
**Security-relevant:** none line-by-line; supply-chain review of the two new
majors per the standing dependency rules.

## Context

Dependabot #83 (typescript 6.0.3 → 7.0.2) was genuinely red: `npm ci` refuses
because `typescript-eslint@8.67.0` peers on `typescript >=4.8.4 <6.1.0`. The
triage verdict (entry 3 of
[`../deps-triage-2026-08-24.md`](../deps-triage-2026-08-24.md), whose "done
when" governs) is that the two move together or not at all. This lands after
E1-02 so the pair moves once, in the final layout, and before E1-04 so the
scaffold is generated under the toolchain it will live with rather than
migrated a week later.

Read first: the triage record entry 3; E0-40's exact-pin rules; MISTAKES
entry 25 (one lockfile).

## Scope

- `typescript` to 7.x and `typescript-eslint` to a major that peers on it, in
  one change, both exact-pinned.
- `npm ci` resolves cleanly from the committed lockfile — no `--legacy-peer-deps`,
  no overrides; if the ecosystem genuinely cannot satisfy the pair yet, the
  ticket closes with that finding recorded in the triage file instead of
  shipping a forced resolution.
- Any new compiler or lint errors the majors surface in existing files are
  fixed in their own commit, separate from the version bump, so the bump diff
  stays reviewable.

## Acceptance criteria

1. `npm ci` from the lockfile succeeds; the exact-pin equality guard and all
   Node-facing gates stay green.
2. Both packages are exact-pinned at their new majors; no other package moved
   except as their lockfile consequence.
3. The Playwright specs still collect and pass under the new toolchain.

## Out of scope

- The frontend scaffold (E1-04).
- Any eslint rule-set changes beyond what the majors force — rule tuning is
  its own decision, not a version bump's rider.
