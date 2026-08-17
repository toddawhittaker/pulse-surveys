# 0042 — The Care pool has a credential of its own, and opens on first use

**Status:** Accepted — one rejected alternative reversed by E0-10, on a premise
measured false
**Date:** 2026-08-16 (amended 2026-08-17)
**Tickets:** E0-10, E10

> **The credential is now withheld from `worker` and `beat`, which this record
> rejected.** It rejected it on one stated fact: that possession of the Care
> credential "does not obtain a name silently, which is precisely what
> possession of `DB_SUPERUSER` does". That was reasoned from the audit row being
> written in the same transaction as the read, and it is false — a caller
> running `BEGIN; SELECT * FROM public.reveal_student_identity(...); ROLLBACK;`
> receives the identity and leaves no audit row, reproduced on the pinned image
> by two independent reviewers. With the premise gone the alternative wins on
> its own terms, so it is now the decision. The parts of this record that are
> unchanged: the credential is still separate, the pool is still bound to
> `app.services.safety`, and the engine is still built on first use. What
> changed is which processes hold the credential, and therefore that
> `CARE_DATABASE_URL` is optional rather than required. Everything that moved is
> marked where it sits: the two reversed alternatives, the lifetime paragraph in
> the decision, and the "two connections mean two transactions" consequence.

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
exactly as `DATABASE_URL` is, and `app.config.Settings` gains a
`care_database_url` field. `scripts/db-init/02-care-role.sh` creates the
role with a login and that password on a fresh Compose volume, and E0-10's
migration sets its attributes and its one grant — the same split as `pulse_app`
(ADR 0040), for the same reason: a migration cannot hold a password without
holding it in the repository.

**The engine is built on first use.** `app.services.safety` builds it behind
`functools.cache`, so importing the package opens no socket and `worker` and
`beat`, which never serve this queue, never connect as `pulse_care`.

*(Amended by E0-10. This paragraph also said the configuration was validated at
import, because `Settings` required `CARE_DATABASE_URL` in every process. It no
longer does — see the reversal below. `CARE_DATABASE_URL` is optional, an empty
value reads as absent, and `_care_engine` refuses with
`CareQueueNotConfiguredError` naming the variable. The failure moved from
start-up to first use, deliberately, because the alternative was requiring the
credential in the two processes it is now withheld from.)*

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
unset.** ***Rejected here, and now the decision — see the reversal below.***
Attractive because it keeps every existing `.env` working and keeps the
credential off `worker` and `beat`. Rejected because it makes the failure arrive
at the first reveal — which is the single worst moment in this system for a
configuration error, a Care staffer with an open threat case in front of them —
and because "the Care queue is silently unavailable" is exactly the state §6.2's
non-content apertures exist to make visible. A required setting fails at
start-up, in CI, in the Compose health check.

**Blanking `CARE_DATABASE_URL` on `worker` and `beat`, as `docker-compose.yml`
blanks the superuser pair.** ***Rejected here, and now the decision — see the
reversal below.*** Considered seriously, because ADR 0009's bound is
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

## The reversal — E0-10, 2026-08-17

**The premise was measured false.** "Possession of it does not obtain a name
silently" was reasoned from the audit row being written inside the function, in
the same transaction as the read. It is: the `INSERT` runs before the `SELECT`,
so an actor refused the `INSERT` never reaches the identity, and a failure inside
the function discards both. What it does not survive is the *caller*. Postgres
has streamed the rows back before the caller decides what to do with its
transaction, so

```sql
BEGIN;
SELECT * FROM public.reveal_student_identity(:actor, :subject, NULL);
ROLLBACK;
```

returns the name and the email address and leaves no audit row. Reproduced on the
pinned Postgres image by two independent reviewers. Possession of the Care
credential therefore *does* obtain a name silently, which is the property this
record said distinguished it from `DB_SUPERUSER`.

**And the credential was reachable without a Care assignment of one's own.**
`pulse_care` holds `SELECT` on `public.role_assignment` — this record's own last
consequence explains why — so a caller holding the credential can read a live
`CARE` assignment out of that table and pass the borrowed person as the acting
actor. The audit row that a non-rolled-back call would leave then names the
borrowed Care staffer rather than the caller. The function's own check is
answered correctly and by the wrong person.

**What the exposure was.** `CARE_DATABASE_URL` sat on the shared
`x-application` anchor, so `worker` and `beat` held it — `worker` being the
process that ships student comment text to a third-party model provider, and the
one whose compromise is most plausible. An operator with no `CARE` assignment
could `docker exec` into either and do the same by hand.

**The new shape.** `docker-compose.yml` gives `CARE_DATABASE_URL` to `api` alone
and blanks it on `worker` and `beat`, along with the `DB_CARE_USER` and
`DB_CARE_PASSWORD` parts it is built from — blanking the URL alone would be
nominal, because `env_file:` hands over the parts and `DATABASE_URL` supplies the
address. `app.config.Settings` makes the field optional and reads an empty value
as absent, because `Settings` is constructed identically in all three processes
and a required field would force the credential back into all three.
`app.services.safety._care_engine` raises `CareQueueNotConfiguredError` naming
the variable when it is absent.

**What the objections to it were worth, now that both are paid.** The one about
*where the failure lands* stands and is accepted rather than answered: a
deployment that forgets this variable learns at the first reveal instead of at
start-up. That is a real cost and it is priced against a credential reaching two
processes that never use it, which is the trade E0-19 exists to keep making the
same way. The mitigation is that the error names the variable, names the process
that should hold it, and says not to fix it by setting it locally. The one about
*two per-service `environment:` blocks* turned out not to apply: the blanking
lives in a second anchor, `x-application-environment`, which every application
service inherits by default, so the fail-safe direction is the one a copied
service falls into. `api` is the single service that adds anything, and it merges
that anchor inside its own block.

**What this does not fix.** The rollback hole itself. Closing it means writing
the audit row over a second connection — plpgsql has no autonomous transaction —
which is **E0-26 item 1**. Until then the record holds against everything except a caller
that deliberately rolls back, and this change is what narrows the set of
processes that can be that caller to one.

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
the second. The audit row is written inside `public.reveal_student_identity`,
before the identity is read and in the transaction `reveal_identity` commits, so
an actor whose `INSERT` is refused never reaches the `SELECT` and a failure
inside the function discards both.

*(Amended by E0-10. This paragraph ended "Nothing about the caller's own session
can separate them", and that is false: the rows are already streamed by the time
the caller decides, so a caller that rolls back keeps the name and discards the
record. It is the premise the reversal above rests on, and closing it is E0-26
item 1.)*

**E10 inherits an interface, not a queue.** `reveal_identity` takes the acting
person, the subject and an optional case id, and raises `NotCareStaffError`
rather than returning nothing when the actor is not Care staff — because at the
surface "refused" and "no such student" are different answers and §6.2's queue
has to show a different thing for each.
