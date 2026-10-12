# E9-15 — Boundary UI fixes

**ID:** E9-15
**Branch:** `e9/boundary-ui-fixes`
**Depends on:** 01–12
**Lane:** light
**Why this lane:** the frontend, the roll-up's leadership context read in
`services/rollups.py`, and one copy string. Nothing here touches purview,
sessions, a view or a migration; a diff that needs `services/authz.py`,
`api/deps.py`, `views_sql/` or a migration stops and re-lanes.
**Size:** M

## Context

The E9 epic-boundary review found these against the epic head: one spec
finding (the roll-up trend draws one start cohort at a time, where SPEC §2.2
and `design/LeadershipRollup.dc.html` draw every cohort's line on one term
axis, "All starts" by default), accessibility findings (the shell's Sign out
above a student's survey in the LMS frame; admin refusals heard only in the
page's top live region, WCAG 2.2 SC 3.3.1; a judgmental attention rule name;
the tree moving focus on every press; lazy routes without a pending state),
and code and record findings (the leadership context re-implementing the
current-term rule and opening a future term; route paths written twice; stale
router comments; the roll-up stylesheet loaded on every page). Rulings made at
the boundary: the shell shows on a student page only when the person has
another view to switch to, and the attention rule's name is neutral wording
(SPEC §5.6 defines the rule, not its text).

Read first: SPEC §2.2, §5.5, §5.6, §7.6; `docs/DESIGN_BRIEF.md`;
`design/tokens.css`; `design/LeadershipRollup.dc.html`.

## Done when

1. The roll-up's trend draws every start cohort's line on one term axis by
   default, with an "All starts" chip first and one chip per cohort after it;
   choosing a cohort chip draws only that cohort. Each drawn cohort has its own
   data table in the chart's numbers view. The named-set overlay is drawn
   beside a single chosen cohort; with all starts shown and a set chosen, the
   page says to choose one start to see the set's line. Workload and
   participation follow the chips: one block per shown cohort.
2. The app shell is not drawn on a student page unless the person holds
   another view to switch to. The shell asks `GET /session/landings` whether
   or not the tab holds a Bearer session, so a new tab riding a cookie session
   still gets logout; a 401 draws nothing.
3. On the admin pages, every write's refusal is shown in a paragraph beside the
   control that sent it, and that control names the paragraph with
   `aria-describedby`; the page's polite live region still announces it.
4. The attention rule SPEC §5.6 item 4 names reads "Response required, not yet
   published after 48 hours" (the copy key's text only; the rule is
   unchanged).
5. `leadership_context` takes the term containing today from provisioning's
   current-term function rather than its own query; when no term contains
   today it falls back to the latest term that has begun, and to none before
   the first term begins. The page opens `current_term_id` and nothing else.
6. Pressing a tree row keeps focus on that row and says "Showing {name}" in
   the content pane's status region; only a breadcrumb press moves focus to
   the node's heading. The admin lazy routes have a pending component, and a
   pending or loading status region mounts empty and receives its text a tick
   later.
7. The shell's styles live in their own small stylesheet, so a student or
   instructor page does not download the roll-up's stylesheet.
8. Route paths live in `frontend/src/routes/paths.ts`, imported by the router
   and by the pages; the router's stale comments are corrected, and
   `main.tsx`'s cascade comment points at `public/layer-order.css` as the place
   that decides the layer order.
