# 0083 — Node lives in a root npm workspace, with `frontend/` as a member

## Context

[SPEC §13](../SPEC.md) draws a `frontend/` directory holding `package.json`,
`vite.config.ts`, `index.html` and `src/`. The repository does not look like
that. PR #61 committed the first TypeScript — `playwright.config.ts` and the
§9.2 end-to-end specs — at the repository root, along with the first
`package.json` and `package-lock.json`, and E0-40 then pointed every Node-facing
CI gate at the root: `npm audit`, the licence scan, `tsc`, `eslint`, and the
`Makefile`'s copies of all four.

E1-04 lands the frontend scaffold. Before it does, one decision settles where
Node lives, because the alternative is deciding it inside E1-04 and moving the
gates a second time in the same epic. Moving a gate is not free here: E0-40 is
the third recorded instance of `docs/MISTAKES.md` entry 36, a probe answering
false over a tree that has the thing, and each instance arrived through
something moving while the thing reading for it stayed still. Four gates ran
green over an unread tree for the length of E0.

The constraints are the ticket's (E1-02), and they are the spec's and
`CLAUDE.md`'s written out: §13's `frontend/` package has to exist for E1-04 to
fill; the end-to-end tooling has to go on working exactly as it does; there has
to be **exactly one `package-lock.json`** afterwards, because two lockfiles
resolving one package to two versions is `docs/MISTAKES.md` entry 25 and it has
already happened in this repository's Python lockfiles; and every probe and gate
that reads a Node path has to read the true path in the same change.

The spec is silent on all of it — §13 draws a tree, not a package topology —
and the choice is contestable, which is why this record exists.

## Decision

The root `package.json` declares `"workspaces": ["frontend"]`. `frontend/`
becomes a workspace member with a private manifest of its own, landed empty by
E1-02 for E1-04 to fill. The end-to-end tooling — `playwright.config.ts`,
`tsconfig.json`, `eslint.config.mjs`, `tests/e2e/` — stays with the root
package, where E0-40's gates already read it.

There is one `package-lock.json`, at the root, and npm resolves the whole
workspace into it. A member has no lockfile of its own; `npm ci` at the root
installs every member, and `npm run build --workspace frontend` runs a member's
script.

**The `frontend` detect probe narrows with the layout, in the same change.**
That probe gates the production build and the bundle budget, and it asked
whether `frontend/package.json` exists. From this decision onwards it exists on
every branch, so the question it was asking is answered "yes" by the layout
itself rather than by there being anything to build. What the job runs is
`npm run build` in that workspace, so the probe now asks whether the workspace
declares a `build` script — in `.github/workflows/ci.yml` and in the `Makefile`
copy of the same condition, which `CLAUDE.md` requires to agree.

This is not the gate flip. The production build and the bundle budget stay
tolerant, exactly as [0002](0002-ci-gates-ship-tolerant.md)
intends, and E1-04 makes them enforcing along with `tsc` and `eslint`. Nor is it
a coverage reduction: the gate ran over no tree before this change and runs over
no tree after it, and the narrowed probe is true of exactly the trees
`npm run build` works on.

## Alternatives rejected

**Move all the Node tooling under `frontend/`.** The tidiest-looking option and
the most expensive one. `playwright.config.ts`, `tsconfig.json`, the eslint flat
config and `tests/e2e/` would move, and with them every path E0-40 pointed at
the root three tickets ago: two probes, four workflow gates, four `Makefile`
recipes, a `cache-dependency-path`, and the two test modules that assert all of
it. That is the largest possible instance of the move-and-forget failure entry
36 is about, spent on a rearrangement this epic needs for nothing — the §9.2
suite is not a frontend artifact, and putting it inside the frontend package
would make `npm ci` for the browser application a precondition of running the
end-to-end tests.

**Two unrelated package trees: the root toolchain and an independent
`frontend/`.** Rejected on the lockfile. Two `package-lock.json` files resolving
the same package to two versions is `docs/MISTAKES.md` entry 25, which cost this
repository a full suite run green against a `charset-normalizer` the image does
not ship. `typescript`, `@types/node` and the eslint packages are exactly the
overlap that would drift: `tsc` in the root gate and `tsc` in the frontend build
would be free to be different compilers, and each pull request would show one
half of the pair. It also doubles the Dependabot surface for a repository with
one Node toolchain in it.

**Leave `frontend/package.json` for E1-04 and declare only the workspace.** npm
accepts a `workspaces` entry naming a directory that is not there, so this
works, and it is the smallest possible diff: nothing flips, no probe moves, and
the `frontend` probe stays literally correct until E1-04 replaces it. Rejected
because it defers the interesting half rather than deciding it. The reason to
settle the layout before the scaffold is that E1-04 should not be choosing a
package topology while it is also writing five views and flipping four gates,
and a declaration with no member is a decision that has not yet met the tree —
in particular it does not meet the `frontend` probe, which is the one thing this
layout genuinely costs. Paying that here is the point of doing it here.

**Give the stub a no-op `build` script so the existing probe keeps working.**
Rejected outright. It makes the production build and the bundle budget run on
every pull request, over a package that produces nothing, and
`scripts/ci/check_bundle_size.py` reports a missing `frontend/dist` as a note
and exits 0 — so two gates would report green having measured an empty tree.
That is a gate turned on and made meaningless, which is worse than a gate
honestly declaring itself tolerant.

## Consequences

- **`frontend/package.json` is committed from now on, so its presence stops
  being evidence of anything.** Any future control tempted to read it — a
  probe, a `Makefile` branch, a script — has to name what it actually needs, the
  way the `frontend` probe now names the `build` script. This is the ordinary
  cost of a placeholder file and it is worth stating, because the failure it
  produces is silent.
- **The `frontend` probe reads the manifest's text with `grep`**, since the
  `detect` job installs no toolchain. It can be wrong in one direction only: a
  dependency literally named `build` makes it answer true, the production build
  then fails loudly on the next pull request, and somebody fixes it. It cannot
  answer false over a package that declares a build, which is the direction
  entry 36 is about.
- **`npm ci` inside `frontend/` still works**, because npm walks up to the root
  lockfile, and it installs the whole workspace at the root while writing no
  lockfile of its own. Convenient, and worth knowing about: a reader who sees
  that command in a script cannot tell from the command what it installs.
- **The frontend build gates read the root lockfile.** `actions/setup-node`
  fails the step when `cache-dependency-path` resolves to no file, so this was
  not a tolerated miss but a red job; the path moved with the layout in the same
  commit.
- **Dependabot keeps one npm entry, and the E1 scaffold's React major-version
  ignores belong in it.** The comment in `.github/dependabot.yml` predicted a
  second entry for `/frontend`; there is no second lockfile for one to watch.
- **A future package that is genuinely not part of this workspace has nowhere
  obvious to go.** Nothing needs one today. If one arrives, it is a decision of
  its own and this record is the thing it has to argue with.
