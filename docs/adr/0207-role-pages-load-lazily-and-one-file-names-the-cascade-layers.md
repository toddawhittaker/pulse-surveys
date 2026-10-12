# 0207 — The leadership and admin pages load lazily, and one file names the cascade layers

**Status:** Accepted
**Date:** 2026-10-12
**Ticket:** [E9-16](../tickets/e9/E9-16-boundary-records-and-tidy-up.md)

## Context

The roll-up, drill-down and admin pages pushed the entry chunk past the 128 KB
gzipped budget in `ci/bundle-budget.json`. Every student and instructor opens
Pulse inside an LMS iframe and would have downloaded pages only leaders and
admins can open. SPEC §7.6 sets the component inventory, not how the bundle is
split. Once pages are split, Vite also splits the stylesheet per page, and a
lazy page's sheet can be linked before the entry's; a cascade layer's
precedence is the order it is first named, so `components` could be named
before Tailwind's `base` and lose to its preflight.

## Decision

- **The leadership landing, the drill-down and the three admin pages load
  lazily** (`lazyRouteComponent` in `frontend/src/router.tsx`), each with the
  shared pending component. Student and instructor pages stay in the entry
  chunk.
- **`frontend/public/layer-order.css` names every layer once**, and
  `index.html` links it before any other stylesheet, so the layer order is a
  statement rather than an accident of which sheet the bundler emits first. It
  is a file, not an inline `<style>`, because the Content-Security-Policy
  allows same-origin stylesheets only.
- The shell's styles live in their own small sheet (`appShell.css`), so the
  roll-up's sheet loads only with the roll-up.

## Alternatives rejected

- **Raising the bundle budget.** It would make every student download the
  leadership and admin pages on every survey, and the budget exists to catch
  exactly that growth.
- **Turning off CSS code splitting** (one stylesheet for the whole app). It
  removes the ordering hazard but puts every page's styles back in the first
  paint, which is the cost the lazy routes were split to avoid.

## Consequences

- A leader's or admin's first visit to a page waits for one more request; the
  pending component covers it.
- A new cascade layer must be added to `layer-order.css`, or its precedence
  falls back to load order.
- A new role-only page should be lazy for the same reason; one left in the
  entry chunk shows up as a budget failure.
