# Carried from E0 into E1

Things E0 decided that E1 has to know before it writes code, and that live
nowhere else. One entry per thing, each with what it looks like to be finished.
This is a hand-off note, not a ticket: E1's breakdown is what schedules the work,
and an entry here is what that breakdown has to have read first.

Created by E0-18. `docs/tickets/e0/E0-28-review-debt-from-e0-15.md` item 6 asks
for this file by name; it wrote "The client-credentials grant, and the four
things that move with it" on 2026-08-21, and the pointer to E0-35 inside it.

E0-42 added the last five entries on 2026-08-22, out of the epic-boundary threat
model and invariant-coverage review. Those five are findings rather than
hand-offs: nothing in E0 is broken by them, and each one is a thing E1 or a later
epic makes live.

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

E0-15 left NRPS and AGS unauthenticated on the mock platform, deliberately, and
`app-security` reviewed that deferral and agreed it is safe for this mock as
deployed. **The problem is not risk. It is that E1 cannot build a conformant
service client against the current surface at all**, so it would build an
unauthenticated one against the mock and rewrite it against the first real LMS.

`pylti1p3`'s `ServiceConnector` issues no NRPS request and no AGS request
without two things: an `auth_token_url` to ask for an access token, and a
tool-signed `client_assertion` to ask with. It obtains a token first and attaches
it to every service call. There is no mode in which it calls a roster URL
unauthenticated, so the tool-side code for a mock that needs no token and the
tool-side code for a platform that does are not the same code.

Four parts therefore move together, and a surface carrying some of them cannot
be built against any better than a surface carrying none:

1. **A `token_endpoint` in the mock's OIDC discovery document.** Today
   `/.well-known/openid-configuration` advertises none, because E0-14 built none
   and a discovery document that advertised an endpoint answering nothing would
   be a record asserting something untrue.
2. **The AGS and NRPS scopes in `scopes_supported`.** Today it is `["openid"]`.
   A tool asks its token endpoint for the exact scope strings the service
   claims name (`app.ags::ADVERTISED_SCOPES` and NRPS's own), so a platform that
   advertises only `openid` is one no service token can be requested from.
3. **`auth_token_url` in `/registration` and a column for it in
   `lti_platform`.** The registration document is what a developer pastes into
   the table in one step, and its keys are the column names — so the endpoint
   has to exist on both sides or the "one step" stops being literal. Note this
   lands beside the authorization-endpoint column the section above already
   requires, and for the same reason: it is a property of a registration, not of
   the process.
4. **Somewhere for the platform to fetch the tool's key set.** The
   `client_assertion` is signed by the *tool*, and the platform verifies it — so
   the platform needs the tool's public JWKS, and `lti_platform` today has no
   column for the tool's key pair and the tool publishes no key set for a
   platform to fetch.

**Done when** the grant lands as **one change covering all four parts**, before
the first conformant service client is written. Partial is worse than absent
here: a token endpoint with no scopes, or scopes with no `auth_token_url`, still
leaves `ServiceConnector` unable to make a single call, and it looks finished
from a discovery document. The test that says it is done is a roster read
performed the way `pylti1p3` performs one — token requested with a tool-signed
assertion, token attached, container returned — rather than an unauthenticated
`GET` that happens to answer.

**Also read E0-35 before writing the roster sync** — a pointer rather than a
copy, because that ticket owns the question and restating it here would give it
two homes.
[`docs/tickets/e0/E0-35-the-writer-and-the-marker-nobody-routed.md`](../e0/E0-35-the-writer-and-the-marker-nobody-routed.md)
item 3 is "a writer nobody routed": `services/authz.py::guard_write` is called by
nothing today, and E1's roster sync is the first code that writes `course`,
`section`, `enrollment` and the `INSTRUCTOR` `role_assignment` row — every
relation the guard names, in one module. E0-35 names E1 as its deadline for
exactly that reason, and it records what its static sweep cannot see.

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

## The reveal's actor check and an instructor's read scope compose

**Found 2026-08-22 by the epic-boundary threat model.** Nothing is broken today
and E0 has no surface that does this; what E1 and E4 build is the surface that
would.

Three facts that are individually correct compose into one that is not.
`ActorScope` (`backend/app/services/authz.py`, `resolve_scope`) carries
`holds_care` **beside** the purview, deliberately, so that a Care capability can
never be unioned into a scope. `section_roster` hands instructor-scoped code the
`user_id` of every enrolled student — that is the whole point of the view, and the
key is what makes a de-identified response addressable. And
`safety.reveal_identity(actor_person_id=…, subject_user_id=…)` checks only that
the **actor** holds Care; it asks nothing about where the subject came from.

So a reporting surface built for the two-hat person §2.1 explicitly permits — a
Care officer who also teaches — can render roster rows through her instructor
purview, take a `user_id` straight off one of those rows, call the reveal with it,
and pass every check there is. The audit row that results is indistinguishable
from a legitimate Care access: right actor, real subject, no case. The capability
and the read scope are separated in the value and joined in the caller.

The other half of this is already recorded and owned: the Care-session sweep does
not see `from app.services.safety import reveal_identity` in a reporting module
(E0-26 item 4, carried to E10). What is new here is the composition — that the
reveal's parameter is exactly the identifier an instructor-scoped view hands out.

**Done when** the capability cannot be exercised against a subject the actor
reached through a reporting scope — the reveal takes its subject from a Care case
rather than from any caller-supplied id, or an equivalent guard — proved by a test
that fails on the composition itself: a two-hat actor, a roster row from her own
section, a reveal that must be refused. It lands **before any instructor-facing
surface renders roster rows**, because that surface is what makes the path
reachable.

## `own_grant` and `resolve_scope` verify nothing about their caller

**Found 2026-08-22 by the epic-boundary threat model.** Both take an arbitrary
person or assignment id and answer for it. Neither asks whether the caller is that
person, because in E0 there is no authenticated caller to ask about — and the
views they read (`public.assignment_scope`, `public.lead_faculty_course`,
`public.containment_path`) are granted to `pulse_app` unscoped, so the answer is
available to anything running as the application role.

That is correct for a resolver and dangerous for a route. The rule that has to
land with the purview walk is: **a request resolves only the scope of its own
authenticated subject**, and any other id is a refusal rather than an answer.

**Done when** that rule holds at the chokepoint with a test that fails on
resolving another person's id, and `transitive_purview` no longer raises — the two
belong together, because the union is what makes a resolved scope worth anything,
and E9 owns both.

## Hypothesis has no purview properties, only graph-storage ones

**Found 2026-08-22 by the epic-boundary coverage audit.** The suite's only
generated graph property — the supervision-graph property module E0-09 left
behind — generates *storage* shapes: that a cycle is refused whatever its length,
and that an arbitrary acyclic forest inserts and reads back as it was asked for.
Nothing generates a supervision forest and asserts a property of the **purview
computed over it**.

The property that matters is §4.1 invariant 2 — sibling-lead disjointness — over
shapes nobody chose by hand: two leads under one chair, a lead who also teaches,
an assistant dean inserted mid-chain. It cannot be written in E0, because the
union it would quantify over is E9's and raises today.

**Done when** E9's purview service ships with a Hypothesis property over generated
supervision forests asserting that no lead's resolved purview contains a course
another lead leads.

## `/healthz` tells an unauthenticated caller which environment this is

**Found 2026-08-22 by the epic-boundary threat model. Recorded as an open
decision, not as a defect.** `backend/app/api/health.py` answers with the service
name, the version and `settings.environment`, to anybody, with no credential.

The environment name is the value every environment-keyed guard in this system
rests on: whether `/docs` is served (ADR 0074), whether `/dev` exists (ADR 0079),
whether the login cookie carries `Secure` (ADR 0078), whether SQL is echoed into
the log, and whether the demo seed will run at all (ADR 0063). Publishing it opens
none of those, and it does tell a caller which of them to try first.

There are three honest answers and E0 chose none of them deliberately: drop the
field, gate it behind whatever authentication E1 builds, or keep it and record
that a deployment's environment name is not a secret. The third is defensible — an
orchestrator's health check is the field's only consumer today, and the value is
`production` in production, which surprises nobody.

**The `/dev` console leaks the same fact through a second door.** `GET /dev`
answers `404` outside development, but the route is registered for `GET` in every
environment and only the handler is gated, so `POST /dev` answers `405` with
`Allow: GET` while any unregistered path answers `404` — measured against the
pinned Starlette 1.6.0. One unauthenticated request therefore confirms both that
this build ships the console and that `ENVIRONMENT` is not `development`, which is
this entry's disclosure arriving by another route; ADR 0079 records it in its
decision section. The code-side fix is to register the route for every method, or
to gate at registration, and it belongs to whichever decision closes this entry
rather than to the documentation ticket that found it.

**Done when** one of the three is chosen in E1 and written down: the field is
gone, the field is gated, or a record says it stays and why the list of
environment-keyed guards above is acceptable to publish — **and the same verdict
reaches `/dev`'s method mismatch**, because a decision that the environment name
may be published makes the `405` acceptable too, while a decision that it may not
leaves that route still answering the question.

## §4.1 items 4 and 5 are enforced by review only

**Found 2026-08-22 by the epic-boundary coverage audit.** §4.1's preamble names
items 1 and 7 as the two invariants carrying no assertion. There are four.

Item 4 — aggregate language counts sections rather than instructors, "needs
attention" rather than "underperforming", no ranking, no composite scores, no
score-sorting — and item 5 — confidentiality copy appears exactly once per
surface, in plain words, no shield or lock iconography — are both rules about
*shipped copy*, and nothing in the suite reads a shipped surface against either.
The only string in the tree either rule touches is
`backend/app/services/landing.py`'s "Nothing needs attention.", which happens to
comply. Every screen those items govern arrives in E2 and E4, and each will be
reviewed by a person who has read §4.1 — which is exactly the enforcement model
§4.1's own preamble says is not enough.

**Done when** either a copy-inventory test exists — every user-facing string
collected from the shipped surfaces and asserted against the forbidden vocabulary
and the once-per-surface rule — or §4.1's preamble stops saying two and names
items 4 and 5 beside items 1 and 7 as invariants that carry no assertion yet.

**Closed 2026-08-24 by the second branch.** §4.1's preamble no longer counts its
unasserted items, and items 4 and 5 now carry their own *asserted from* notes
beside items 1 and 7. The copy-inventory test itself is scheduled rather than
abandoned: SPEC §14.3 puts it in E2, growing with each later UI epic. This entry
stops tracking it because the spec now does.
