# E1-13 — Role resolution from assignments; `landing.py` retires

**ID:** E1-13
**Branch:** `e1/role-resolution-from-assignments`
**Depends on:** E1-12
**Security-relevant (⚠ line-by-line):** the resolution rules — what a session
may act as is authorization's first question, and the door-permission rules
(ADR 0026) become live here.

## Context

The second carried entry governs. `backend/app/services/landing.py` maps a
verified token's claims to one of five views; it was honest for E0's empty
pages and "is not how the system decides anything afterwards." Its two
precedence rules are written down and held by no test (measured: reversing
both leaves 424 tests green). The done-when: the claims-derived mapping is
**gone** — the landing view comes from the assignment model — and if a
precedence survives, a fixture person holds both roles of at least one pair
and a test pins which view she gets; deleting `landing.py`'s entry from
`tests/unit/test_care_is_not_reachable_from_a_claim.py::EXCEPTIONS` in the
same change is the signal it is finished.

The rules this resolution must embody are already in the schema and spec:
students hold no assignment — their access resolves from enrollment (§2.1,
ADR 0028); every other role acts through a live assignment; a door only
admits the assignments that permit it (ADR 0026's `permits_launch` /
`permits_web_login` generated columns — a Care assignment is unreachable from
a launch *by data*, and the test that today needs an exception should need
none). §2's multi-role note (switcher or union) is E9's full answer; E1's
answer is the minimal honest one for empty landings — pick the acting
assignment by a recorded rule, and record it.

Read first: the carried entry; ADR 0026, ADR 0028; SPEC §2 and §2.1 (the
table is authoritative on doors); `landing.py` and the EXCEPTIONS test;
`app/services/authz.py` (`resolve_scope` exists but verifies nothing about
its caller — that rule is E9's; this ticket must not reach past its own
subject: the session's identity from E1-12 is the only person resolved).

## Scope

- Resolution: session identity → that person's live assignments filtered by
  the entered door's permission column → landing view. A launch by an
  enrolled student (no assignment) resolves student via enrollment. A person
  with no assignment and no enrollment gets the calm no-access state.
- The precedence decision: keep an ordering (then seed the two-role fixture
  person and pin the ordering with a test, per the done-when) or replace it
  with an explicit chooser for multi-assignment people. Either way the rule
  is recorded — ADR if the choice is contestable, and it is.
- `landing.py` deleted; both routers resolve through the new service; the
  `EXCEPTIONS` entry deleted in the same change.
- Care remains unreachable from a launch — now proven by data (ADR 0026's
  column) rather than by an exception list, and the existing invariant test
  gets strictly stronger, never weaker.

## Acceptance criteria

1. Each seeded person lands correctly by door: student (launch), instructor
   (launch), Dean (both doors), Care (web only), admin (web only) — with the
   Dean's two doors asserted as the *same* view.
2. A launch presenting claims for a role the person's assignments do not
   hold lands by the assignments, not the claims (the token's roles claim
   stops deciding anything beyond authentication context — asserted with a
   mint whose claims lie, via E1-07).
3. `landing.py` and the EXCEPTIONS entry are gone; the care-unreachable test
   passes without exceptions.
4. If precedence survives: the two-role fixture person exists and the
   ordering test fails when the ordering flips (proven by mutation).
5. End-dated or absent assignments resolve as absent (the boundary case:
   an assignment end-dated yesterday does not land today).

## Out of scope

- Union purview, the multi-root nav, and the role switcher (E9; §2's full
  multi-role answer).
- Any change to `resolve_scope`/`own_grant` caller verification (E9's, per
  the carried entry that assigns it there).
- Any real capability behind the landings (E2 onward).
