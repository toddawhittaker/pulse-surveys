# E2-17 — The survey form works for every student who can open it

**ID:** E2-17
**Branch:** `e2/student-surface-repairs`
**Depends on:** E2-14, E2-15 (the boundary batch this ticket's review ran against)
**Lane:** heavy
**Security-relevant:** item 7 (the CSRF client half); item 5 adds a field to a
student read path.

## Context

The epic-boundary a11y-copy review, verified by independent re-measurement
against the live stack, found the form unusable for a screen-reader student who
has not answered everything, unreadable in three places for a low-vision
student, and silent where the design brief demands an announcement; the
lti-oidc review found the CSRF double-submit's client half was never built. The
record is `docs/tickets/e2/boundary-review.md`, second round.

## Scope

1. **An incomplete form says so instead of going dark.** The submit button is
   `disabled` until every non-comment question is answered, leaving the tab
   order entirely (verified: the sequence ends at the slider; no `<form>`, no
   `[required]`, no message anywhere). Settled construction: the button stays
   enabled and focusable always; activating it with answers missing submits
   nothing, writes a message naming the first unanswered question into the
   form's live region and into visible text tied to the button by
   `aria-describedby`, and moves focus to that question's control. The message
   text comes from the frontend copy module.
2. **The Likert scale's polarity becomes programmatic.** Each scale's ends
   ("Strongly disagree" / "Strongly agree") get an id and the radio group an
   `aria-describedby` to it, and the 1 and 5 radios carry the end words in
   their accessible names. Verified today: the accessibility tree offers bare
   digits.
3. **The unchecked Likert dot clears SC 1.4.11.** The rendered ring measures
   1.92:1 against the white card (token value 2.58:1 before antialiasing).
   Pick the existing token nearest the design intent with a computed ratio
   ≥ 3:1, at ≥ 2px width so the rendered ring holds it; change
   `design/LikertInput.dc.html` to match; record the computed ratio in the PR.
   Give the workload slider's track the same treatment while in the file
   (measured 1.30:1 — a design-fidelity fix, not a WCAG failure; the thumb
   reads at 12.45:1).
4. **The required-comment flip is announced.** Choosing a rating of 1–2 flips
   `aria-required`, the flag, and the helper silently (verified). Announce the
   change through the live region with a copy-module sentence.
5. **The page names the course.** Headings render bare section codes ("E1FF");
   the wire (`GET /student/survey`) carries no course name (verified: four
   members per section entry). Add the course's human label to the read answer
   (backend: `survey_read` + schema; the course table's fields say what exists
   — verify before settling the exact label) and render it in each `h2` with
   the section code. The label is the student's own enrollment metadata; §4.1
   is not in play, but the read-path test must still pin the field.
6. **The confidentiality line renders once per page** (the 2026-09-03 ruling:
   "once per surface" reads once per screen). Lift the sentence out of the
   per-section submit bar to one per-page placement consistent with
   `docs/DESIGN_BRIEF.md`; the enforcing e2e test runs at a TWO-window clock
   (2026-09-11T19:00 shows two on the seeded world) and asserts exactly one.
   Sharpen SPEC §4.1 item 5's parenthetical to say per screen, in this PR.
   The component docstring arguing the per-survey reading is corrected.
7. **The CSRF client half exists.** `csrf_verified_student` requires
   `X-Pulse-CSRF` from the cookie carrier; the SPA never reads the
   `pulse_csrf` cookie (verified: zero csrf matches under `frontend/src`), so
   a cookie-borne student can read but never submit. The API client sends
   `X-Pulse-CSRF` from the cookie on every POST when the cookie is readable.
   Trap: dev cookies are SameSite=None without Secure and browsers refuse
   them from the server in the e2e environment, and the session normally
   rides Bearer — so the proof plants the cookie client-side (or intercepts
   the request) rather than driving the whole cookie flow.
8. **The idle live region stays in the accessibility tree.**
   `.pulse-bounce-announcement:empty { display: none }` makes Chromium ignore
   the node (`notRendered`, verified via the accessibility protocol) exactly
   against the comment's stated intent. Replace hiding-by-display with a
   visually-hidden treatment that keeps the region rendered.

## Acceptance criteria

1. With nothing answered, the submit control is reachable by keyboard,
   activating it submits nothing, the missing-answer message is announced and
   visible, and focus lands on the first unanswered control — asserted in the
   e2e suite.
2. The accessibility tree carries the scale's polarity (group description and
   end-radio names asserted).
3. The chosen dot and track tokens compute ≥ 3:1 (dot) against the card, and
   the design files agree with the CSS.
4. The required flip is announced (live-region text asserted after choosing a
   low rating).
5. The read answer carries the course label, pinned by an integration test;
   the headings render it.
6. At a two-window clock the page renders the confidentiality sentence exactly
   once (e2e), and SPEC §4.1 item 5 says per screen.
7. A POST assembled while a `pulse_csrf` cookie is readable carries
   `X-Pulse-CSRF` (asserted by interception or planted cookie); the Bearer
   path is unchanged.
8. The idle live region is rendered and unignored (accessibility-tree
   assertion), and the bounce path still announces.

## Out of scope

- Everything in E2-16 and E2-18. The copy-registry convention sweep (carried
  to E4). Any Care-surface change.
