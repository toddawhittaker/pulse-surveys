# E2-08 — The submit path: validation, synchronous validity gating, resubmission

**ID:** E2-08
**Branch:** `e2/submit-path`
**Depends on:** E2-05, E2-06 (E2-07 for stack-level testing)
**Lane:** heavy
**Security-relevant:** the first student write path. Scoping (a student
writes only into their own enrollment's open window), the identity spelling
on `response`, and the fail-open boundary (ADR 0056) are the review surface.

## Context

SPEC §3.2 and §3.3 govern. A student submits the five answers; required
fields are enforced (comment required when its Likert is ≤ 2); each submitted
comment is classified synchronously at submit — substantive / insufficient /
nonsense — and "it was okay" is bounced immediately with coaching copy and
one concrete example, never silently penalized after the fact, never a shame
state. On a provider outage the ≥25-character floor applies and the
submission is accepted, then classified async. **ADR 0056's taxonomy governs
exactly which failures floor** — the record was rewritten after its first
"only a timeout" wording measured wrong at both ends:
`AIProviderUnavailableError` (read timeout, write timeout, HTTP
408/502/503/504) floors; `AIProviderUnreachableError` (connect timeout, DNS,
TLS, reset, pool) and `AIProviderRefusedError` (401/403/404/429/500 and any
other status) raise, and `backend/app/ai/tasks.py` says in as many words that
E2's submit path is where a caller decides what to do with one. That decision
is this ticket's, it is contestable, and it gets an ADR: the spec sanctions
the floor only for the outage shape, so accepting on a refused 500 would
widen ADR 0056 by the back door, and a raw 500 to the student is not an
answer either. Resubmission is allowed within the window; missed weeks are
not back-filled; one response per (student, section, week).

The classifier side exists (`classify_comment_validity`,
`backend/app/ai/tasks.py`, 4s budget, floor, `classification` row). What does
not exist: the API route, the submission service, the async re-classification
job, and the bounce semantics.

Read first: SPEC §3.2, §3.3 (the p95 < 2.5s submit budget in §10 measures the
whole round trip); §4.1 items 4 and 5 for every string this path serves (the
bounce copy is user-facing and enters E2-11's inventory); ADR 0054 (a floored
classification names the floor), ADR 0055, ADR 0056, ADR 0062 (parse once at
the edge); the session/roles machinery E1 landed in `backend/app/api/deps.py`;
MISTAKES entry 41 (a request path inheriting a worker dependency's retry
policy is exactly the async-reclassify enqueue this ticket writes).

## Scope

- The submit route (student session required): resolves the student's
  enrollment and the section's open window (E2-06's one function); refuses —
  with distinct, honest reasons — a closed window, a section the student is
  not enrolled in, a missing required field, and an out-of-range workload
  value. Parsed once at the edge per ADR 0062.
- Synchronous gating: submitted comments classified through the existing
  task; an `insufficient` or `nonsense` verdict on any submitted comment
  bounces the submission with the verdict's coaching copy; nothing is stored
  as submitted on a bounce. An *unavailable* provider accepts on the floor,
  stores the response, records the floored classification (ADR 0054), and
  enqueues the async re-classification — published with retries off and
  caught broadly (MISTAKES entry 41), the scheduled path covering the gap.
  For *unreachable* and *refused* (the rows ADR 0056 keeps outside the
  floor), this ticket decides and records the student-facing behavior — an
  honest retryable refusal is the lean — and tests the near-miss pair that
  distinguishes the taxonomy: a 503 floors, a 500 does not (MISTAKES
  entry 3; E2-07 gives the mock both selectors).
- Submission timestamps are written by this path through the E2-04 clock
  service, never by a server default — a dev-clock submission must be
  internally consistent with the window that accepted it, because E3's
  participation formula will read both.
- This ticket also establishes the string-externalization shape E2-11's
  inventory will read — one registry convention the backend's user-facing
  strings (bounce copy, refusals) live in, which E2-09 and E2-10 then
  follow. Three tickets inventing three shapes is how the inventory decays
  into a hand-kept list.
- Resubmission within the window replaces the prior answers and re-runs the
  gating; after close, resubmission refuses like any closed-window write.
  The (student, section, week) constraint from E2-05 is the backstop, not
  the mechanism.
- Validity state on `response` (what E3's participation formula will read):
  written by this path alone, from the classification verdicts, per §3.3 —
  optional comments left blank do not affect it.

## Acceptance criteria

1. The full §3.3 matrix, each cell a test: valid submit stores and answers
   success; "it was okay" (and a nonsense string) bounces with the copy;
   required-comment-missing refuses; blank optional comment stores as valid;
   closed window refuses; foreign section refuses; resubmit in-window
   replaces; resubmit after close refuses.
2. The failure taxonomy against the stack: mock told to stall (E2-07) —
   submit accepted on the floor, floored classification row present, async
   re-classification lands a second row, and the request returns inside the
   §10 budget rather than hanging on the worker (MISTAKES entry 41's
   near-miss is the test). Mock told to answer 503 — floors. Mock told to
   answer 500 — the recorded refused-behavior, not the floor. And the
   *unreachable* row runs too, at the integration level with the provider
   address pointed at a closed port (a mock that answers cannot mint a
   connection that fails): the recorded unreachable-behavior, **not the
   floor** — flooring on a blackholed provider is the exact defect
   ADR 0056's 2026-08-31 amendment records returning once already. All
   three cells run, and the ADR names the choices.
3. A second submission racing the first cannot produce two responses for one
   (student, section, week) — the constraint is seen refusing, not cited
   (MISTAKES entry 9).
4. Every user-facing string this path serves is externalized where E2-11's
   inventory will read it, and says what §4.1 items 4–5 permit.
5. A dev-clock submission stores the clock service's time: an integration
   test sets the override, submits, and reads the row's timestamp back
   inside the pretend window — the criterion that makes the no-server-default
   rule in E2-05 mean something.

## Out of scope

- The read path and what the form fetches — E2-09.
- The form itself — E2-10.
- Validity *rate* surfaces (instructor/leadership only, §3.3) — E4.
- Grade passback reading validity state — E3.
