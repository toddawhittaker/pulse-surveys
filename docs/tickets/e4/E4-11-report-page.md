# E4-11 — The report page

**ID:** E4-11
**Branch:** `e4/report-page`
**Depends on:** E4-01 (deadline — see below), E4-07, E4-08, E4-09, E4-10,
E4-18 (the section list the page discovers its sections from — breakdown
decision 11), E4-19 (the trend points' term weeks — breakdown decision 12)
**Lane:** light
**Security-relevant:** this is the epic's first instructor-facing surface,
which is why the inherited deadline attaches here: **this ticket's PR may
not merge until E4-01 has** — the reveal-subject guard lands before any
instructor-facing surface ships, and the build order carries that rule.
The page itself adds no data access beyond calling E4-07's routes.

## Context

**InstructorMondayReport** (§7.6's screen): the route under
`frontend/src/routes/instructor/`, the API client for E4-07's two report
routes and E4-18's section list (how the page learns which sections are
hers), and the assembly — rates and stats up top, the TrendPair, then the two
comment groups each led by its summary, with week navigation across
published weeks. The instructor lands here from her LTI launch; the landing
view E1 shipped stops being empty.

States the page owns, all real in E4's data: loading; error (the API's
refusal or a network failure — one honest error state, no retry theater);
a published week with data; a zero-response week; a small-N week (notice +
summary, no cards); an absent summary (E4-06 hasn't run or failed — the
absence renders honestly, not as an empty panel); and no-published-weeks-yet
(a section before its first Monday).

Read first: `docs/DESIGN_BRIEF.md`, `design/tokens.css`, SPEC §7.6, §5.1,
§2.2; E4-07's schema (the authority over the sketch from its merge);
`frontend/src/routes/instructor/index.tsx` and `frontend/src/api/student.ts`
(the client conventions); `tests/e2e/` conventions and the e2e cookie/iframe
gotchas memory the specs already encode.

## Scope

- The route, the typed API client, and the page assembly from E4-08/09/10's
  components.
- Week navigation: pages across the published-week list, current week
  default, URL-addressable so a week can be linked.
- All the states above, each reachable and each designed (the brief governs;
  no browser-default error text).
- The in-slice Playwright e2e (§14.2 item 1): instructor launches through
  the mock LMS, lands on the report for a seeded section, sees the stacked
  pair and both groups, navigates to a prior week.
- Accessibility basics in-slice: the page is navigable by keyboard end to
  end, headings structure the two groups, focus is managed on week change.

## Acceptance criteria

1. The e2e passes against the seeded stack: launch → report → prior week,
   asserting on content the seed guarantees, not on absence of errors.
2. Every state above is driven in component tests with the schema's shapes;
   the error state never renders partial data beside an apology.
3. Week navigation offers exactly the published weeks from the API — no
   client-side week arithmetic (the axis rule from E4-08, applied to nav).
4. A small-N week end to end: the notice and summary render, no comment
   card exists in the DOM, and nothing in the page (network tab included)
   fetched suppressed content to hide it — the payload never contained it,
   and the e2e asserts the response body, not just the DOM.
5. The absent-summary state renders its honest treatment and the rest of
   the report intact.
6. URL-addressable week: a deep link to a published week renders it; to an
   unpublished week, the page treats it as not found, mirroring the API.
7. No new strings outside the copy layout; no raw hex; bundle budget gate
   still green.

## Known traps

- **The deadline is a merge gate, not a footnote** — if E4-01 is somehow
  still open when this PR is ready, this PR waits, and says so rather than
  merging on the argument that the page "doesn't render roster rows."
  Enforcing the carried deadline structurally was this breakdown's promise.
- **Asserting the response body in e2e (criterion 4)** is what makes the
  small-N proof real — a DOM-only assertion would pass with the leak
  sitting in the network response.
- **The iframe and cookie gotchas are recorded** — dev cookies are
  SameSite=None-without-Secure so the session rides Bearer, and Chromium's
  Local Network Access rules bit E1's e2e; read the memory-backed spec
  conventions before writing the launch flow.
- **Empty is a design, not a fallback** — the no-published-weeks state will
  be most instructors' first sight of Pulse mid-week; the brief's tone
  rules apply to it as much as to data.

## Out of scope

- The instructor response section — E7; the page composes without it, not
  around a stub.
- Leadership's read-only rendering — E9.
- Any new backend behavior — a gap found here files against E4-07 rather
  than being worked around in the client.
