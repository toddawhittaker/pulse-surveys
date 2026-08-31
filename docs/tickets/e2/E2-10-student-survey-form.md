# E2-10 — StudentWeeklySurvey: the five-question form

**ID:** E2-10
**Branch:** `e2/student-survey-form`
**Depends on:** E2-08, E2-09
**Lane:** light
**Security-relevant:** low — the form renders what the API answers and posts
what the student typed; the enforcement lives server-side (E2-08, E2-09).
The copy it ships is governed surface (§4.1 items 4–5) and enters E2-11's
inventory.

## Context

The first real screen. `frontend/src/routes/student/index.tsx` is an empty
landing by design ("E2 builds the weekly survey that goes here"); this ticket
replaces it with StudentWeeklySurvey per the design contract — §7.6's
component list names the primitives: LikertInput, ConditionalTextArea
(optional / required / bounce), WorkloadSlider (0–40 in 0.5 steps, live
numeric readout, keyboard-adjustable, screen-reader-labeled), SubmitBar
(carrying the confidentiality copy, exactly once, plain words, no shield or
lock iconography — §4.1 item 5).

One carried decision is due here (`carried-from-e1.md`, "The three webfonts
are declared and not loaded"): the five landing views render in fallback
faces, and self-hosting versus shipping fallbacks is "decided against E2's
first real screen." This is that screen.

Read first: `docs/DESIGN_BRIEF.md` and `design/tokens.css` (the token source
`frontend/src/styles.css` draws from); SPEC §3.2 verbatim (question text
comes from the API's versioned set, never hard-coded), §3.3 (bounce is
coaching, one concrete example, never a shame state; optional-state helper
copy notes written feedback counts toward credit), §7.6 (motion budget,
reduced-motion kill switch), §14.2 item 4 (keyboard and screen-reader basics
at merge); ADR 0086 (the router knows paths, the backend knows roles).

## Scope

- The screen and its states, driven by E2-09's read answer: no open window
  (calm, dated, no countdown-shame), open-and-unsubmitted, bounced (field-level
  feedback on the offending comment, rest of the form intact), submitted
  (with the in-window resubmit path), window closed.
- The four primitives above as components with variants, per §7.6 — one
  component per primitive, no copies. Conditional-required wiring: Q2
  required exactly when Q1 ≤ 2, Q4 when Q3 ≤ 2, and the required state
  announced accessibly, not only colored.
- The webfont decision, applied and recorded (an ADR if self-hosting;
  either way the deferred entry's done-when closes).
- Keyboard and screen-reader basics in-slice: slider operable by keyboard
  with its value announced; the bounce announced via a live region; focus
  handling on refusal.
- User-facing strings externalized in one module the copy inventory
  (E2-11) reads, following the registry shape E2-08 established — built that
  way now so E2-11 does not refactor this screen a week after it lands.

## Acceptance criteria

1. Against the running stack with the dev clock on a Friday evening: launch
   as the seeded student, complete the form, submit, land in the submitted
   state; type "it was okay" with a low rating and see the bounce with its
   coaching copy, fix it, resubmit. (E2-13 scripts this; here it must be
   *possible* and demonstrated.)
2. Question text on screen is the API's versioned text — proven by reseeding
   with an altered set in a test and watching the screen follow.
3. `tsc`, eslint, the production build, and the bundle budget stay green;
   the webfont choice does not blow the budget silently.
4. Keyboard-only completion of the whole form works; the slider and the
   bounce meet the announced-state checks above.

## Out of scope

- Any aggregate, trend, or results content — E8's screen.
- A frontend unit-test runner (vitest) — deliberately not added this epic:
  the behavior worth asserting is covered end-to-end in E2-13, and a second
  test toolchain needs a reason stated out loud that nobody has yet.
- Care/instructor/leadership screens — later epics.
