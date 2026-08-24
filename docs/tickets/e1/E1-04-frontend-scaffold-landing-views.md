# E1-04 — Frontend scaffold and the five empty landing views

**ID:** E1-04
**Branch:** `e1/frontend-scaffold-landing-views`
**Depends on:** E1-02, E1-03
**Security-relevant:** the gate flips (fidelity, not confidentiality); no
line-by-line pass expected, but the landing views' strings are governed copy —
see the last scope item.

## Context

SPEC §13 plans `frontend/` (React 19 + TypeScript + Vite, TanStack
Router/Query, Tailwind 4); §7.6 makes the design prototype the visual contract
and `design/tokens.css` the single source for palette, type, spacing, and
focus; §14.3 E1's exit needs "the right (empty) view" for a student, an
instructor, and a Dean from either door. E0-18 shipped server-rendered landing
pages; this ticket is the application those pages hand over to, and it is where
the four frontend CI gates stop being tolerant (ADR 0002: landing the ticket
includes removing the tolerance).

Read first: SPEC §7.6, §13 (frontend tree), §4.1 items 4 and 5 (copy rules —
enforced by review until E2's inventory); `docs/DESIGN_BRIEF.md` whole;
`design/tokens.css`; `design/CLAUDE.md` if present; CONTRIBUTING's CI table.

## Scope

- The `frontend/` application per §13's tree: `main.tsx`, `router.tsx`, `lib/`,
  `components/`, and `routes/` with one route group per role area (student,
  instructor, leadership, care, admin), each rendering an intentionally empty
  landing view — role-labelled, token-styled, keyboard-reachable, nothing else.
- `tokens.css` imported as the only source of color/type/spacing; no raw hex
  (§7.6). The empty states carry calm copy consistent with §4.1 items 4 and 5:
  no "underperforming"-class vocabulary anywhere, confidentiality copy nowhere
  (these surfaces carry none), no shield or lock iconography.
- The two doors' post-entry redirects land on these routes. The wiring contract
  with E1-08/E1-09/E1-13: the backend decides the landing *role* and redirects;
  the frontend renders whatever route it is handed and never re-derives role
  from anything client-side.
- **All four gate flips:** `tsc`, `eslint`, the production build, and the
  bundle budget become enforcing, each proven by breaking what it now guards
  (a type error, a lint error, a build break, a budget breach — planted,
  watched failing, removed; MISTAKES entry 9). The bundle budget's number is
  set here and recorded where the gate reads it, with one sentence on how it
  was chosen.
- Accessibility in-slice (§14.2 item 4): keyboard operability and labelled
  landmarks on every landing view now, not in E13.

## Acceptance criteria

1. `docker compose up` serves the built SPA through the `api` service exactly
   as §13 describes (static serve from the app factory), and each of the five
   routes renders its empty landing.
2. The four gates fail on their planted defects and pass on the real tree;
   the tolerance branches for them are gone from `ci.yml`.
3. No component carries a raw hex value; tokens only.
4. Playwright still passes; a spec asserts each landing view renders its role
   label from a served route (not a fixture string).

## Out of scope

- Any data fetching, any API client generation, any TanStack Query usage
  beyond scaffolding — there is no data to fetch in E1.
- Any real screen from the design prototype (E2's survey is the first).
- Session/auth logic in the frontend — the backend owns entry (E1-08/09/13).
