# 0098 — The landing view comes from the assignment model, and which hat wins

## Context

E1-13's brief is the second entry of `docs/tickets/e1/carried-from-e0.md`.
`backend/app/services/landing.py` mapped a verified token's roles claim to one of
five empty views. That was honest for what E0 shipped — an empty page labelled by
a signature-verified claim says only what the issuer said — and it "is not how the
system decides anything afterwards": every real capability is gated on a live
assignment in the database through `app/services/authz.py`.

The entry also recorded two orderings inside that module that were **written down
and held by no test**, measured rather than assumed: reversing both left the whole
unit suite and both door suites green (424 tests, 2026-08-21). Instructor beats
Learner on a launch; leadership beats `CARE` beats `ADMIN` on a web login.

SPEC §2 and §2.1 decide almost all of what replaces it. §2.1's table says which
door each role enters by, ADR 0026 has already put that rule on `role_assignment`
as two generated columns, and ADR 0028 says a student holds no assignment and
resolves from `enrollment`. What the spec does **not** decide, and what a
reasonable engineer would decide differently, is what happens when one person
holds two hats at one door. §2 names the problem and defers the answer: a role
switcher or a union of purviews, which SPEC §14.3 gives to E9. E1 still has to put
somebody on a screen today.

## Decision

**The landing is resolved from rows, in this order, and from nothing else.**
`app.services.authz.resolve_landing` reads the session's own `person_id` and
`user_id` — resolved from the door's verified token by ADR 0094's point functions
— and answers:

1. the person's live assignments, **filtered in SQL by the door's permission
   column** (`permits_launch` or `permits_web_login`, ADR 0026), mapped to views
   through `LANDING_FOR_ROLE` and reduced by `LANDING_PRECEDENCE`;
2. if and only if that lands nothing, and only at the launch door, whether the
   user holds an enrollment window containing the institution's current day —
   ADR 0028's student;
3. otherwise nothing, which the doors answer with a calm 200 page.

**The recorded precedence is one total ordering at both doors: leadership,
instructor, care, admin.** SPEC §2 says a launch shows the person's full purview
rather than the launch context, so the higher-standing hat's screen is the useful
one; leadership over Care over admin is E0-18's own recorded intent, which nothing
held until now.

**`STUDENT` is deliberately outside the ordering.** Enrollment is a fallback
consulted only when no assignment lands, so assignments beat enrollment and staff
who are also enrolled act as staff. Inside the ordering, a student landing would
be something an assignment could lose to, and the teaching assistant enrolled in
the course she grades would open on her own results page.

**The door rule has exactly one authority, and it is the generated column.** The
decider, `chosen_landing`, is pure and takes the filtered role set as given; it
never re-derives which door admits which role. That is what makes "a Care
assignment cannot open a launch" a property of the row that no write path can
contradict, rather than a Python branch beside a column that agrees with it today.
`assignment_scope_v002.sql` publishes the two columns so the filter can be a
`WHERE` clause.

**The enrollment window is inclusive at both ends and measured on the
institution's calendar.** `started_on <= today AND (ended_on IS NULL OR ended_on
>= today)`, with `today` computed as
`datetime.now(ZoneInfo(settings.institution_timezone)).date()` — Todd's ruling on
E1-11, applied to a second read. ADR 0020 makes an end date the last *included*
day, so the day somebody dropped is still an enrolled day.

**A role `LANDING_FOR_ROLE` does not name contributes no landing**, skipped rather
than defaulted and never raising — the same fail-closed shape as `_OWN_GRANT_ROOT`
and as ADR 0026's positive door lists.

## Alternatives rejected

- **Per-door orderings — instructor first on a launch, leadership first on the
  web.** The intuitive reading of "the launch context", and it makes one person's
  two doors answer two different screens for reasons neither screen explains. §2
  says the opposite in as many words: a launch shows the full purview rather than
  the launch context. It also doubles the thing E9's switcher has to supersede.
- **Keeping the roles claim as a fallback when no assignment lands.** The shape
  that survives a rewrite, because every door test in the repository goes on
  passing. It also keeps the whole of the hole: the person who administers an LMS
  writes what its launches claim, so a fallback is a claim-granted view wearing a
  condition (E0-09 criterion 10).
- **Intersecting the claim with the assignments — "believe the rows, but only
  where the token agrees".** Cautious-looking, and it hands the LMS a veto over
  Pulse's own records: a platform that stops sending a roles claim takes every
  instructor's view away.
- **Deferring the whole question to E9's switcher.** It leaves the landing
  claims-derived for another epic, with two orderings nothing holds, and it leaves
  the Care exception in `test_care_is_not_reachable_from_a_claim.py::EXCEPTIONS`
  standing — which the carried entry names as the signal this is unfinished.
- **Deriving the door rule in Python beside the column.** ADR 0026 already
  rejected "no column at all"; this is the version that keeps the column and adds
  a second copy of what it means. Two authorities for one rule, and the one an
  operator can read off the row is the one that stops being consulted
  (`docs/MISTAKES.md` entry 13).
- **Answering a person with no view with a 4xx**, as both doors did for "no role
  this tool has a view for". They authenticated correctly and nothing went wrong:
  a member of staff whose assignment has not been entered yet, or a student
  between terms. A refusal sends them to fix something that is not broken.
- **One resolver function doing the reads and the decision.** It makes the
  ordering reachable only through a database, so criterion 4's mutation proof
  needs rows for a rule that is about a set and a boolean.

## Consequences

- **The ordering is pinned twice and dies on any transposition**:
  `tests/unit/test_chosen_landing.py` over every ordered pair in both input
  orders, and `tests/integration/test_landing_resolves_from_assignments.py` over
  a dean-and-Care person and a Care-and-admin person at a real door.
- **E9's role switcher supersedes this precedence.** When a person can choose
  which hat they are acting under, `LANDING_PRECEDENCE` becomes the default
  selection rather than the answer, and this record is amended rather than
  deleted.
- **`app/services/landing.py` is deleted**, and with it the last code path under
  `app/` that read a claim beside the Care role: `EXCEPTIONS` in
  `tests/unit/test_care_is_not_reachable_from_a_claim.py` is empty, and its canary
  is now the whole of what stands between that sweep and vacuity.
- **`authz.py` reads one base table.** `public.enrollment`, for the student
  predicate, over a `SELECT` E1-11 already granted `pulse_app`. The module's
  "five views and no base table at all" sentence was already false and is
  corrected; every read that could reach identity still goes through a view.
- **Each door costs one query more than it did**, and a launch by somebody with no
  assignment costs two. Both are indexed reads keyed by a primary key.
- **The LIS vocabulary moves to `app/lti/launch.py`.** §7.3's provisioning and
  E1-11's roster sync read the roles claim lawfully and still need somewhere to
  import it from; what stops is its authority over the landing.
- **A ninth `AssignmentRole` gets no view until somebody writes one**, and reports
  itself the first time a holder tries to enter.
