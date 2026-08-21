# Carried from E0 into E1

Things E0 decided that E1 has to know before it writes code, and that live
nowhere else. One entry per thing, each with what it looks like to be finished.
This is a hand-off note, not a ticket: E1's breakdown is what schedules the work,
and an entry here is what that breakdown has to have read first.

Created by E0-18. `docs/tickets/e0/E0-28-review-debt-from-e0-15.md` item 6 asks
for this file by name and adds the last section below.

## The two doors do not yet resolve to one person, and E0 says so on purpose

E0-18's boundary section moved the same-identity assertion to E1. Both doors
open for the two-hat person E0-16 and E0-14 seed — she is a Care officer through
the web door and an instructor through an LMS launch — but nothing in E0 says
the two are one human. There is no `user` row for either subject, no database
identity resolution on either door, and no session that outlives the entry flow.
What E0 does assert is thinner and is a fact about the fixtures rather than
about the system: `mock-idp/app/seed.py::LMS_INSTRUCTOR_USER_ID` names the mock
LMS's instructor user, and a unit test pins the two constants to each other so
the cross-mock reference cannot go stale in silence.

E1's dual-door identity merge is what closes this. Until it lands, a launch and
a web login by the same person are two unrelated verified tokens.

**Done when** one test drives the two-hat person through both doors and asserts
that both resolve to the *same stored identity* — one row, by its primary key,
not two rows that happen to agree on an email address — and the constant-pinning
unit test E0-18 left behind is deleted in the same change, because the fact it
stands in for is then asserted directly.

## The landing role is claims-derived scaffolding, and two of its rules are unexercised

`backend/app/services/landing.py` maps a verified token to one of five empty
views, and it does it from the token's roles claim alone. That is E0-18's
decision and it is honest for what E0 ships — an empty page labelled by a
signature-verified claim says only what the issuer said — but it is not how the
system decides anything afterwards. Every real capability is gated on a live
assignment in the database through `app/services/authz.py`, and E1's role
resolution from claims *plus the app-owned assignment model* replaces this
mapping outright. The seam is one function, `landing_role_for`, taking which
door it is answering for; both routers call it and neither has a role rule of
its own.

Two rules inside it are **written down but not held by any test**, which was
measured rather than assumed: reversing both orderings leaves the whole unit
suite and both door suites green (424 tests, 2026-08-21).

1. **Instructor beats Learner** on a launch, for the teaching assistant enrolled
   as a learner in the course she grades. No seeded launch carries both roles.
2. **Leadership beats `CARE` beats `ADMIN`** on a web login. No seeded person
   holds two of those three; the two-hat person's second hat is on the other
   door, so she does not exercise this either.

Whoever replaces this mapping should know that the precedence in the code is a
statement of intent that nothing currently checks. If E1's assignment model
keeps a precedence at all, it needs a person holding two of these roles in the
fixtures before the ordering means anything.

**Done when** the claims-derived mapping is gone — the landing view comes from
the assignment model — and, if a precedence survives that change, a fixture
person holds both roles of at least one pair above and a test pins which view
she gets. Deleting `landing.py`'s entry from
`tests/unit/test_care_is_not_reachable_from_a_claim.py::EXCEPTIONS` in the same
change is the signal that this is finished: that exception exists only because
the mapping names the Care role while reading a claim.

## `LTI_PLATFORM_AUTHORIZATION_ENDPOINT` is process-wide and platforms are not

The security review of E0-18 named this. Platforms resolve per issuer:
`app/lti/launch.py::registered_platform` looks up the one `lti_platform` row for
the `iss` in the login initiation and takes the client ID from that row, so the
registration rather than the caller decides which tool this is. But the address
the browser is then redirected to is a single setting read from `Settings`
(ADR 0075), the same string for every platform in the process.

With one registered platform — which is all E0 has — the two agree. With two,
they do not: a launch from platform B resolves B's registration and then sends
the browser to A's authorization endpoint, carrying B's client ID and this
tool's `state` and `nonce`. The best case is a launch that fails at somebody
else's platform; it is not a case anybody should have to reason about.

ADR 0075 rejected a column for this, correctly, on the grounds that E0-23 had
already put service-address columns in E1 and E0 registers one platform. That
reasoning expires the moment a second platform is registered, so **E1's
registration columns must make the authorization endpoint a property of the
registration** rather than of the process.

**Done when** two platforms are registered at once and each one's launch
round-trips to *its own* authorization endpoint, proved by a test that would
fail if both went to the same address — and `LTI_PLATFORM_AUTHORIZATION_ENDPOINT`
is gone from `Settings` and `.env.example`, rather than left as a default the
column falls back to.

## The client-credentials grant, and the four things that move with it

**E0-28 item 6 writes this section; E0-18 leaves the heading.** It is not
E0-18's paragraph to write: the four parts that move together — the token
endpoint in discovery, the AGS and NRPS scopes in `scopes_supported`,
`auth_token_url` in `/registration` and in `lti_platform`, and somewhere for the
platform to fetch the tool's key set — belong to the ticket that reviewed the
deferral. E0-28's acceptance criteria require them to land here.

E0-28 also adds a pointer to E0-35's sanctioned-writer question, on the same
terms: a pointer, not a copy.

## The §4.1 view sweep is blind to an aliased identity column and to join keys

**Found 2026-08-21 by the reviewer self-test, not by a live defect.** The
`privacy-authz` reviewer, given a planted `views_sql` file that joins
`user_identity` and returns a person-naming column, caught it — and then ran
the repository's own §4.1 sweep (`tests/integration/test_identity_separated_views.py`)
over that same file and found it **green**. Two blind spots, measured:

- The sweep matches identity columns by name against `IDENTITY_NAME_FRAGMENTS`.
  A view that aliases `user_identity.identity_name AS respondent_display_name`
  exposes the name and matches no fragment, so the sweep passes. Spelling the
  same column `ui.identity_name` is what makes the sweep fire — the guard keys
  on the output label, which the view author chooses.
- `user.lms_user_id` is a stable per-person join key (the LTI `sub`), and it is
  flagged by nothing: `lms_` is ADR 0014's *ownership* marker, not an identity
  marker, and it matches no identity fragment. A view returning it beside a
  comment lets an instructor resolve a named student in the LMS in one step,
  with every §4.1 guard green.

Neither is live today — no such view exists — which is why this is inherited
rather than fixed now. **Done when** the identity-separation sweep is closed
over both: an aliased identity column is caught by what the column *is* (its
lineage to `user_identity`) rather than by the label the view gives it, and the
set of columns `pulse_app` may read from a view is enumerated so a new grant on
a join key fails the sweep rather than passing it. The reviewer's own writeup,
and the fixture `identity-column-in-view`, hold the reproduction.
