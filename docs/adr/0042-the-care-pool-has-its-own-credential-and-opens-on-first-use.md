# 0042 — The Care pool has a credential of its own, and opens on first use

**Status:** Accepted
**Date:** 2026-08-16
**Tickets:** E0-10, E10

## Context

[ADR 0001](0001-identity-separation-by-database-role.md) decides that "the
connection pool is bound to the service module, not to the actor. Only the Care
service can obtain a `pulse_care` session." E0-10 builds it and gives the reason
in §2.1's terms: one person may hold a Care assignment *and* a reporting
assignment, so "pick the pool from the actor's role" has no answer for them, and
the answer it invents is the expensive one. The code path decides.

What neither settles is where the second connection's *credential* comes from,
or when the pool is opened. Both are contestable, and both were decided by the
first implementation whether or not anybody wrote them down —
[ADR 0006](0006-settings-lifetime.md) left the lifetime question open per entry
point on purpose, and
[ADR 0013](0013-the-database-session-is-synchronous.md) answered it for
`app.db` alone.

## Decision

**A credential of its own, declared like the first one.** `.env.example` gains
`DB_CARE_USER`, `DB_CARE_PASSWORD` and `CARE_DATABASE_URL`, built from the parts
exactly as `DATABASE_URL` is, and `app.config.Settings` gains a required
`care_database_url: SecretStr`. `scripts/db-init/02-care-role.sh` creates the
role with a login and that password on a fresh Compose volume, and E0-10's
migration sets its attributes and its one grant — the same split as `pulse_app`
(ADR 0040), for the same reason: a migration cannot hold a password without
holding it in the repository.

**The engine is built on first use, and the configuration is validated at
import.** `Settings` requires `CARE_DATABASE_URL`, so a deployment missing it
fails when `app.db` is imported — at start-up, in every process, naming the
variable. What is deferred is only the socket: `app.services.safety` builds its
engine behind `functools.cache`, so `worker` and `beat`, which never serve this
queue, never connect as `pulse_care`.

**Only `app.services.safety` names it.** The session factory is private, it is
not a FastAPI dependency, and nothing is exported that hands a caller a Care
session. A dependency is something a router can ask for, and a router that can
ask for one is a router choosing its own pool.

## Alternatives rejected

**One credential and `SET ROLE pulse_care` on the application connection.** No
new variable, no second role to provision, and it is the cheapest thing that
looks like it works. Rejected because it requires `pulse_app` to be a member of
`pulse_care`, and membership is inherited privilege: every instructor request
would then be running on a connection that can reach identity by writing one more
statement. It converts a grant boundary into a discipline, which is the whole of
what SPEC §8 says is insufficient.

**Deriving the Care URL from `DATABASE_URL` by substituting the role name.** Half
of the above with extra steps — it still needs a password, and if it reuses
`DB_APP_PASSWORD` then one credential opens both connections and the separation
is undone in a string substitution.

**Making `CARE_DATABASE_URL` optional, with the Care path unavailable when
unset.** Attractive because it keeps every existing `.env` working and keeps the
credential off `worker` and `beat`. Rejected because it makes the failure arrive
at the first reveal — which is the single worst moment in this system for a
configuration error, a Care staffer with an open threat case in front of them —
and because "the Care queue is silently unavailable" is exactly the state §6.2's
non-content apertures exist to make visible. A required setting fails at
start-up, in CI, in the Compose health check.

**Blanking `CARE_DATABASE_URL` on `worker` and `beat`, as `docker-compose.yml`
blanks the superuser pair.** Considered seriously, because ADR 0009's bound is
about credentials reaching containers that do not need them, and E0-19 exists
because that boundary keeps eroding. Rejected on what the credential *is*:
`pulse_care` is not superuser, owns nothing, holds no `SELECT` on
`user_identity`, and its one `EXECUTE` writes an audit row in the same
transaction as the read — so possession of it does not obtain a name silently,
which is precisely what possession of `DB_SUPERUSER` does. Blanking it would also
mean two per-service `environment:` blocks that the `x-application` anchor was
introduced to avoid, and E0-03's finding was that a service copied from another
is how blanking lines go missing. The lazy engine gives most of the benefit
without the structure: those two processes hold the value and never open a
connection with it.

**Building the engine at import, as `app.db` does.** The consistent choice, and
rejected on the same fact the option above turns on: three processes import this
package and one of them serves the Care queue. An import-time engine would have
`beat` — a scheduler that will never read a name — holding an open pool on the
one role that can.

## Consequences

**A deployment that upgrades to E0-10 must set three new variables and recreate
its database volume**, or the Care connection will not authenticate.
`scripts/db-init` runs only against an empty data directory, so an existing stack
needs `docker compose down -v` before `pulse_care` has a login. Until then the
role exists — the migration creates it — with no way to connect, so the failure
is an authentication error naming the role rather than a quiet fallback to
another one. Worth a line in E13's operator guide, alongside ADR 0001's
degradation note.

**`.env` now carries three role credentials**, and ADR 0008's "one file, several
readers" shape absorbs it unchanged: the parts are declared above the URLs that
interpolate them, and `tests/unit/test_env_example_sync.py` holds every entry to
having a reader in both directions.

**The service's own `CARE` check reads `role_assignment` on the Care
connection**, which is why `pulse_care` holds `SELECT` on that one base table.
The alternative was for the check to run on the application session, which would
mean `pulse_app` reading assignments — a decision that belongs to E0-11's
`services/authz.py`, not to this ticket. `role_assignment` carries a person key,
a role and five scope keys and no identity, so this widens what Care can see
about *access* and not about people.

**Two connections mean two transactions**, and the ticket's guarantee lives in
the second. The audit row is written inside `public.reveal_student_identity`, in
the transaction `reveal_identity` commits, so the read and the record are one
write. Nothing about the caller's own session can separate them.

**E10 inherits an interface, not a queue.** `reveal_identity` takes the acting
person, the subject and an optional case id, and raises `NotCareStaffError`
rather than returning nothing when the actor is not Care staff — because at the
surface "refused" and "no such student" are different answers and §6.2's queue
has to show a different thing for each.
