# E1 — Entering the app: build order

Fifteen tickets decomposing SPEC §14.3's E1 entry. Each is sized for a single
focused session and leaves the repository in a working state: CI green, Compose
stack healthy, nothing half-wired at a boundary. E1 is a **⚠ epic**: every
security-relevant diff gets line-by-line human review (§14.2 item 3), and each
ticket below names what in it is security-relevant, so the reviewer's scope is
declared before the diff exists.

Say **"build E1, ticket 5"** and it means E1-05.

Branch names follow `CONTRIBUTING.md`: cut `e1/<slug>` from
`epic/e1-entering-the-app`, one ticket per branch, one pull request into the
epic branch.

**Read before building anything here:** `docs/tickets/e1/carried-from-e0.md`
(all ten entries — this breakdown schedules them, and the mapping is below),
the "What the built tickets settled" section of
[`docs/tickets/e0/README.md`](../e0/README.md) (all of it still binds — model
imports, `Base` from `app.models.base`, naming conventions, the database
fixtures, migration identity, `.env.example` readers, `pulse_app` read-path
tests, view rules, the Care session bound, synchronous sessions), and
`docs/MISTAKES.md` whole.

## Build order

| # | Ticket | Branch | Depends on | Summary |
|---|---|---|---|---|
| 01 | [Close the §4.1 view sweep over aliases and join keys](E1-01-view-sweep-closure.md) | `e1/view-sweep-closure` | none | Identity columns caught by lineage rather than output label; the set of columns `pulse_app` may read enumerated, so a new grant on a join key fails rather than passes. ⚠ |
| 02 | [Node workspace layout, and `@types/node` tracks the runtime](E1-02-node-workspace-layout.md) | `e1/node-workspace-layout` | none | Decide root-vs-`frontend/` once, keep one lockfile and honest detect probes, and tie `@types/node` to `NODE_VERSION` with a guard and a Dependabot ignore. |
| 03 | [TypeScript 7 with typescript-eslint, one change](E1-03-typescript-7-pair.md) | `e1/typescript-7-pair` | 02 | The pair Dependabot #83 could not move alone; both majors together, gates stay green. |
| 04 | [Frontend scaffold and the five empty landing views](E1-04-frontend-scaffold-landing-views.md) | `e1/frontend-scaffold-landing-views` | 02, 03 | Vite + React + TS per §13 under the §7.6 contract; five role landings; the four frontend gates (tsc, eslint, build, bundle budget) turn enforcing here. |
| 05 | [Registration owns its endpoints and its keys](E1-05-registration-columns.md) | `e1/registration-columns` | none | Per-registration authorization and token endpoints, the tool's own key pair, and a constrained `jwks_url`; `LTI_PLATFORM_AUTHORIZATION_ENDPOINT` is deleted. ⚠ |
| 06 | [The mock platform learns the client-credentials grant — all four parts](E1-06-mock-client-credentials-grant.md) | `e1/mock-client-credentials-grant` | 05 | Token endpoint, advertised scopes, `auth_token_url` in `/registration`, and the platform fetching the tool's key set — one change, because partial is worse than absent. ⚠ on the tool-side JWKS route |
| 07 | [The mock platform mints deliberately wrong launches](E1-07-mock-wrong-launches.md) | `e1/mock-wrong-launches` | none | Bad signature, `alg: none` and the HS256 confusion case, wrong audience, unregistered deployment, replayed nonce, tampered state, stale timestamps, the TeachingAssistant near-miss, and the title-less context — the fixtures E1's negative tests need and E0 never built. |
| 08 | [The launch door on `pylti1p3`](E1-08-launch-door-pylti1p3.md) | `e1/launch-door-pylti1p3` | 05, 07 | State, nonce, replay, and clock skew validated; cookieless-iframe storage; the launch-session JWT; the session module both doors will share. ⚠ line-by-line |
| 09 | [The web door: OIDC login and the branch the user cancels](E1-09-oidc-web-door.md) | `e1/oidc-web-door` | 08 | Authlib code flow against the mock IdP per ADR 0077; the error redirect Batch F made reachable ships tested; same session module as the launch door. ⚠ line-by-line |
| 10 | [Launch-time provisioning, and how a sanctioned writer satisfies `guard_write`](E1-10-launch-provisioning-guard-write.md) | `e1/launch-provisioning-guard-write` | 07, 08 | Course/section/user rows from a validated launch; the roster service address stored from staff launches only; the `lms_title` fallback; ADR 0069's open half settled with the first real writer. ⚠ |
| 11 | [The roster sync is a conformant service client](E1-11-roster-sync-service-client.md) | `e1/roster-sync-service-client` | 06, 10 | Token requested with a tool-signed assertion, attached to every NRPS call; hourly beat job plus debounced staff-launch trigger; enrollment windows incl. the member with none; enrollment and INSTRUCTOR assignment writes through the sanctioned-writer mechanism. ⚠ |
| 12 | [Dual-door identity merge](E1-12-dual-door-identity-merge.md) | `e1/dual-door-identity-merge` | 09, 10 | Both doors resolve the two-hat person to one stored identity row by primary key; the constant-pinning test E0-18 left is deleted the same day. ⚠ line-by-line |
| 13 | [Role resolution from assignments; `landing.py` retires](E1-13-role-resolution-from-assignments.md) | `e1/role-resolution-from-assignments` | 12 | The landing view comes from live role assignments (students from enrollment, per ADR 0028), the claims-derived mapping is deleted with its `EXCEPTIONS` entry, and any surviving precedence gets a two-role fixture person and a pinning test. ⚠ |
| 14 | [`/healthz` and `/dev` get one verdict about the environment name](E1-14-healthz-dev-verdict.md) | `e1/healthz-dev-verdict` | none | The carried entry's three honest options; whichever is chosen reaches both routes, with an ADR. |
| 15 | [E1 exit: five clauses, both doors, in a browser](E1-15-e1-exit.md) | `e1/e1-exit` | 04, 08, 09, 11, 12, 13, 14 | Playwright proves every clause of §14.3 E1's exit line against the running stack, including the refusals; writes `carried-from-e1.md` for anything E1 hands on. |

## Dependency graph

```
01 ─────────────────────────────────────────────┐
02 ── 03 ── 04 ─────────────────────────────────┤
05 ── 06 ──────────────┐                        │
      07 ──┬───────────┼── 11 ──┐               ├── 15
05 ─────── 08 ── 09 ───┤        │               │
      07 ── 08 ── 10 ──┴── 12 ── 13 ────────────┤
14 ─────────────────────────────────────────────┘
```

Four chains run independently and can interleave: the sweep (01), the frontend
chain (02 → 03 → 04), the platform chain (05 → 06, with 07 free-standing), and
the door chain (08 → {09, 10} → 11/12 → 13). Ticket 14 is free-standing. Ticket
15 needs everything. 01 goes first on principle rather than dependency: it is
the guard that must exist "before any new view ships," and building it while no
E1 view exists is what makes its red case honest.

## Exit criterion → the tickets that prove it

§14.3 E1's exit line has five clauses. Every clause names the tickets whose work
it rests on; E1-15 is where each is proven in a browser against the stack.

| Clause | Rests on |
|---|---|
| a student, an instructor, and a Dean each land on the right (empty) view from either door | 04, 08, 09, 13 |
| the seeded two-hat person enters by both doors and resolves to the same stored identity row | 12 |
| a synced section shows correct derived dates | 10, 11 (dates via E0-07's parser) |
| a replayed or state/nonce-tampered launch is refused | 07, 08 |
| a roster read succeeds as an authenticated service call, not an unauthenticated GET | 06, 11 |

## Where the carried work landed

Every entry of `carried-from-e0.md`, every E1-owned row of E0's carried-out
table, and the two E1 rows of `docs/tickets/deps-triage-2026-08-24.md`, with
the ticket that schedules it. The entries' own "done when"s govern; the tickets
point at them rather than restating them.

| Item | Lands in |
|---|---|
| The two doors do not yet resolve to one person | E1-12 |
| The landing role is claims-derived scaffolding | E1-13 |
| `LTI_PLATFORM_AUTHORIZATION_ENDPOINT` is process-wide | E1-05 |
| The client-credentials grant, and the four things that move with it | E1-06 (grant); E1-11 (the sync that reads E0-35 first) |
| The §4.1 view sweep is blind to aliases and join keys | E1-01 |
| The reveal's actor check and an instructor's read scope compose | **Handed to E4**, deliberately — see below |
| `own_grant` and `resolve_scope` verify nothing about their caller | **E9's**, as the entry itself assigns; restated below |
| Hypothesis has no purview properties | **E9's**, as the entry itself assigns; restated below |
| `/healthz` tells an unauthenticated caller the environment | E1-14 |
| §4.1 items 4 and 5 are enforced by review only | **Closed 2026-08-24** by the spec pass; the copy-inventory test is E2's per §14.3 |
| E0-24 item 1 — `jwks_url` is credential-equivalent and unconstrained | E1-05 |
| E0-25 item 5 — the mock cannot mint a deliberately wrong launch | E1-07 |
| E0-35 / ADR 0069 — how a sanctioned writer satisfies `guard_write` | E1-10 (settled), E1-11 (follows it) |
| Triage entry 3 — TypeScript 7 with typescript-eslint | E1-03 |
| Triage entry 4 — `@types/node` tracks the runtime | E1-02 |
| E0-14 (withdrawn note) — the title-less context has no fixture anywhere | E1-07 (mints it), E1-10 (decides the fallback) |

## What E1 deliberately does not do

Named so scope creep has something to push against. Each item has an owner; none
is silently dropped.

- **The reveal-subject guard** (carried entry: the reveal's actor check and a
  reporting scope compose). Handed to **E4**, whose §14.3 entry already binds
  the deadline — "before any instructor-facing surface renders roster-derived
  rows." The justification: E1 ships no surface that renders roster rows, and
  no Care-case machinery exists yet to bind a reveal subject to; building the
  guard here would redesign the reveal against structures E6/E10 create. The
  deadline is in the spec, which is the strongest record this repo has.
- **Transitive purview, the resolve-only-your-own-subject rule, and the
  Hypothesis purview properties** — E9's, per the carried entries and §14.3.
  `transitive_purview` goes on raising by design (ADR 0003); no E1 view may
  traverse it.
- **§4.1 item 1's assertion and the copy-inventory test** — E2's, per §14.3.
  E1's landing views still comply with items 4 and 5 (they ship almost no copy;
  what they ship follows the brief), but the inventory that asserts it is E2's.
- **Term-map edits re-deriving section calendars** — E2 or E11 (ADR 0018,
  ADR 0021 name the owners).
- **Deep Linking.** §7.3 makes plain resource-link launch the default, and E0-14
  already deferred Deep Linking out of the mock. Nothing in E1..E13 names it;
  scheduling it is raised to Todd in this breakdown's PR rather than decided
  here.
- **`PlatformProfile` adapters** for Canvas/Moodle/D2L/Blackboard — E3's per
  §14.3. E1 builds against the mock only; where `pylti1p3` needs a per-platform
  answer, the mock's answer is the only one coded.
- **Supervision-graph and Lead-Faculty-mapping editing** — E9's admin surfaces.
  E1 reads assignments; the only assignment writer in E1 is the roster sync's
  INSTRUCTOR rows.
- **Notifications** of any kind — E12's.
- **Real-LMS certification** — post-v1, per §14.4.

## How CI tightens in E1

The four frontend gates are E0's last structural tolerances (besides the AI
eval floors, which are E2's). Each flip is owned by name; landing the ticket
includes removing the tolerance, per ADR 0002, and each flip is proven by
breaking the thing it now guards (MISTAKES entries 9 and 36 — a gate that has
never failed is a comment).

| Gate | Becomes enforcing in |
|---|---|
| `tsc` | E1-04 |
| `eslint` | E1-04 |
| frontend production build | E1-04 |
| bundle budget | E1-04 |
| AI eval floors | E2, unchanged |

E1-02 is not a flip but touches the same machinery: if the workspace layout
moves files the `detect` probes read, the probes move in the same change —
a probe answering over a tree that no longer holds the thing is MISTAKES
entry 36.

## Notes on the decomposition

- **01 first, though nothing depends on it.** The sweep closure guards against
  a class of view that E1 itself is the first epic capable of adding by
  accident. Building the guard before the temptation exists is the cheap
  ordering.
- **05 and 06 are one subject split at the trust boundary.** 05 is tool-side
  schema and key custody; 06 is the mock learning the grant plus the one
  tool-side route (the tool's public JWKS) the grant needs. The carried entry's
  "one change, all four parts" governs 06: the grant's four parts land
  together there. They are two tickets because key custody decisions (05) are
  reviewable separately from protocol conformance (06), and 05's columns are
  what 06's registration document names.
- **08 does not provision.** The launch door validates, issues a session, and
  renders the landing; writing course/section/user rows is 10's, so the
  validation diff a human reviews line-by-line is not diluted by ORM writes.
- **10 settles ADR 0069's open half** because it is the first sanctioned writer
  to exist. 11 follows the mechanism 10 built; if 11 finds the mechanism wrong,
  that is a dispute, not a redesign inside 11.
- **12 before 13.** Role resolution reads assignments through a person, and a
  person is only reachable from a token once the identity merge exists. The
  two-hat person exercises both.
- **Every ticket that touches the seed** (07, 10, 12, 13) stays behind the
  development-environment guard (ADR 0063, ADR 0068). No ticket registers
  anything outside it.
- **E0-28 item 6's four moving parts** are 06's four parts — that ticket asked
  for them to reach "whoever builds the roster sync … before writing the
  client," which the 06 → 11 dependency enforces.
