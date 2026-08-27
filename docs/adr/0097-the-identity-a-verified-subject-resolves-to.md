# 0097 — The identity a verified subject resolves to, at both doors

## Context

E1-12's brief is the first entry of `docs/tickets/e1/carried-from-e0.md`, and its
"done when" is the criterion verbatim: one test drives the seeded two-hat person
through both doors and asserts that both resolve to the **same stored identity —
one row, by its primary key, not two rows that happen to agree on an email
address**.

Three tables could be meant by "the stored identity". `user` is the LMS key and
the platform reference (ADR 0001), and there is one per registration, so the same
human on two platforms is two rows. `person` is SPEC §2.1's Pulse-owned people
graph — the node `role_assignment` hangs off and the thing purview is computed
over — and ADR 0024 links it to at most one `user`. Nothing at all held an
identity provider's subject before this ticket.

The constraint that bounds the decision is stated in the ticket: **a merge is
never inferred from a mutable claim**, with email equality named as the
anti-pattern. And an unlinked web login is a defined state rather than an error
page: SPEC §2 puts every role in Pulse's own records, and an identity provider
asserts that somebody authenticated, not that they belong here.

ADR 0094 decides *how* a subject reaches a row id — point resolution through
`SECURITY DEFINER` functions — and is deliberately a separate record, because it
is shared with E1-11 and it answers a privilege question rather than an identity
one. This ADR decides what the rows are and what each door does with them.

## Decision

**The identity is the `person` row.** Both doors resolve to `person.id`, and the
session carries it as `person_id` from here on; E1-13 reads assignments through
it. A `user` row is a *subject at a platform*, which is the wrong grain — the
two-hat person's two doors could never reach one `user` row, because one of them
never touches an LMS at all.

- **The launch door** resolves `sub` → `user` → `person`:
  `public.resolve_platform_user(lti_platform_id, lms_user_id)` and then
  `public.resolve_person_for_user(user_id)`. The second may answer NULL and that
  is a state the session carries rather than a refusal — ADR 0028 gives a student
  a `user` row and no person, and so does anybody an administrator has not put in
  the people graph yet. A launch by such a person still lands.
- **The web door** resolves `(iss, sub)` → `person` through a new table,
  `public.web_login_subject`, read by `public.resolve_web_person`. NULL is the
  no-account state below. `user_id` is left unset at this door: a web login
  identifies nobody at any LMS.

**The linkage is a table of its own, not two columns on `person`.** A person may
hold no web account, the pair `(idp_issuer, idp_subject)` is what has to be
unique rather than either half, and a nullable pair on `person` makes "no
account" and "half a row written" the same shape. The table carries two unique
constraints:

- `UNIQUE (idp_issuer, idp_subject)` — one subject is one person. Without it,
  which person a login resolves to depends on which row the plan reads first.
- `UNIQUE (person_id)` — one web account per person, mirroring ADR 0024's
  one-user rule so the two doors are symmetric. **This is the conservative half
  rather than a fact about people**: a deployment federating a second identity
  provider needs it dropped, which is one migration, no data change and no code
  change, and doing it now would be building for a need nobody has.

**Rows are provisioned, never inferred.** The demo seed writes them (below), and
an administrator writes them by hand until E9 or E11 builds a surface: connect as
the migration identity and
`INSERT INTO public.web_login_subject (idp_issuer, idp_subject, person_id) VALUES (…);`
`pulse_app` holds **no grant of any kind** on the table — not even SELECT — so
the application cannot read it except through `resolve_web_person` and cannot
write it at all. That is what makes "a web login writes nothing" a property of
the database rather than of the code.

**An unlinked web login gets a calm page.** HTTP 200, server-rendered, plain
words, `data-testid="no-account"` — the same mechanism, status and register as
the cancelled login E1-09 built, and a third testid because it is a third event.
No session is issued and no row of any kind is written. A 4xx would tell somebody
who signed in correctly that their sign-in failed.

**Identity is resolved before the role, at both doors.** A web subject with no
linkage gets the no-account page whatever its roles claim says. "This system has
no record of you" is true earlier and more simply than "no view for the role you
state", and it is the answer E1-13 will still be giving once roles come out of
the assignment model — which cannot ask anything at all without a person.

**§7.3's leadership limb activates here.** E1-10 shipped the instructor limb from
the launch's LIS claim and left the other dormant (ADR 0091), because reaching
"any leadership role" means reaching a `role_assignment` row. It now resolves the
launching subject to a person and asks `public.assignment_scope` whether that
person holds a role in `LEADERSHIP_ROLES`. The claim test runs first and
short-circuits, so an ordinary instructor launch costs no query. This is an
authorization decision made outside `app/services/authz.py`, deliberately: that
chokepoint scopes a *read* to an actor's purview, and this asks whether a launch
may trigger a write of the tool's own — a different question, on a path with no
purview in it and no data to scope.

**What a launch from the platform that authenticates nobody now reaches.** The
seed registers `mock-lms` as a trusted issuer on a development box (ADR 0068),
and that platform signs a launch as whatever subject the caller picks (ADR 0038).
E0-31 made the reachable set empty and said so; E1-12 makes it **exactly two, by
name** — `mock-lms-user-instructor` and `mock-lms-user-dean` — because the merge
has to be demonstrable on the running stack and in E1-15's browser proof, and
§7.3's leadership limb needs a launchable subject whose person holds a live
leadership assignment. So, stated rather than implied: **on a development box,
anyone who can reach the mock container can launch as a subject on that
registration and hold whatever its person holds, a dean's purview over the seeded
institution included.**

**Of the two, one is launchable today and the other is not, and that was measured
rather than assumed.** `mock-lms/app/launch.py::resolve_launch` refuses a
`login_hint` naming no user its own seed holds, and that seed holds two people —
a learner and `mock-lms-user-instructor`. So the two-hat person's subject is
live now, and the dean's `user` row is a Pulse-side row waiting for the mock to
seed a matching person; adding it there is a `mock-lms` change with its own
inventory tests, recorded in `docs/tickets/e1/deferred.md` with a done-when.
Nothing about this ADR's decision turns on which of the two is drivable — the
reachable set is what it is the moment the mock seeds one — and the cost above is
stated at its eventual size on purpose.

Three things bound it. The container is a development one and the seed refuses to
run anywhere else (ADR 0063). The data behind that purview is fictional. And the
set is pinned as an inventory by
`test_the_only_users_on_the_mock_platform_are_the_mock_worlds_own`, so a third
subject is a red rather than a quiet widening. The two-hat person also holds a
`CARE` assignment, which no launch can act under: `role_assignment.permits_launch`
is generated from the role and is false for `CARE` (ADR 0026), which is exactly
what that column exists for.

**Mock-world people are new `person` rows, never the demo eighteen re-linked.**
ADR 0024 gives a person at most one `user` and each demo person already has
theirs on the fictional registration; re-pointing one at a mock subject would
hand a launch from a platform that authenticates nobody a demo person's whole
purview, which is the failure E0-31's guard was written against. The seed writes
one person per mock-provider subject, links two of them to mock-platform `user`
rows, and matches them on a second run through the linkage — `person` carries no
unique column of its own, and six of the eight have no `user` row to key on.

## Alternatives rejected

- **Making `user` the identity.** It is one row per platform, so the web door
  could never reach one, and the two-hat person's two doors would resolve to two
  different things by construction. It also puts the identity at the grain SPEC
  §4 keys responses to, which is the grain that must stay per-platform.
- **Matching a web subject to a stored identity by email address.** The
  anti-pattern the done-when names. An address is a value the provider's
  administrator controls and a person can change: two people share one after a
  rename, a departmental mailbox sits on two records, an address is reassigned to
  a new hire. ADR 0024 rejected the same shape for the person-to-user link,
  because "the failure is a purview computed for the wrong person — invisible,
  because it produces a plausible answer". Every other claim fails the same way,
  which is why resolution reads no claim but the two that identify the token.
- **Auto-provisioning a person on an unlinked web login.** It makes whoever
  administers the identity provider an administrator of Pulse's people graph, and
  §2.1 makes that graph the thing purview is computed from. It is also the
  cheapest way to make the door "work", which is why the forbidden state is
  asserted directly rather than left implied by the page.
- **Refusing an unlinked web login with a 4xx.** Fail-closed is right about the
  session and wrong about the person: they signed in correctly, and a refusal
  sends them to fix a credential that is fine.
- **Two nullable columns on `person`.** Loses the uniqueness of the pair, makes a
  half-written row indistinguishable from no account, and puts an
  identity-provider subject on the table `pulse_app` must hold no grant on —
  which would have made the linkage unreadable by any mechanism at all.
- **Putting the leadership check in `app/services/authz.py`.** That module is the
  purview chokepoint, and its shape is "scope this read to this actor". A launch
  trigger has no read to scope; adding a second kind of question there would make
  the chokepoint two things.
- **Keeping the reachable set on the mock registration empty.** It is the safest
  answer and it makes the ticket's own criterion undemonstrable outside the test
  suite: the merge would be proved in integration and unprovable in the browser,
  which is where E1-15 has to prove it.

## Consequences

- **The session carries two new claims**, `person_id` and `user_id`, always
  written and `null` where there is nothing to write. A session minted before this
  ticket reads back as "no stored identity" rather than as a token this tool did
  not issue.
- **The web door takes a database session**, its first, and writes nothing on that
  path.
- **`web_login_subject` joins the §4.1 sweep's subject matter for free**: it
  carries a foreign key to `person`, so the fixed-point walk in
  `tests/integration/test_identity_column_marker.py` collects it without anybody
  adding a name to `PERSON_TABLES`. Its marker is a comment on the whole table
  (ADR 0022's third shape), because `idp_subject` matches no fragment the
  name-based sweep knows and never will. `JOIN_KEY_COLUMNS` did not have to move,
  and must not move for a view of this table: no view reads it.
- **One person, one web account, until somebody drops a constraint.** A second
  identity provider is a migration.
- **An administrator provisions a linkage by hand.** There is no surface for it in
  E1 and the psql statement above is the whole of the path. E9's People editor and
  E11's console are where one belongs; until then, a person who joins between demo
  seeds cannot sign in through the web door without a database write.
- **The launch door's ordering is now a dependency rather than a preference.**
  `provision_from_launch` writes the launching subject's `user` row and commits
  before the landing is resolved, and the resolution reads that row — which is
  what makes a leadership person's *first* launch discover their section rather
  than their second.
- **A leadership launch costs three round trips** the instructor path does not:
  two point resolutions and one read of `assignment_scope`. They are paid only on
  launches whose roles claim carries no Instructor URN.
- **ADR 0068's "the mock registration carries no `user` rows at all" is amended
  here**, to exactly the two subjects named above. That ADR's own text now points
  at this one.
