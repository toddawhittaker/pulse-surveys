# 0126 — A signing key reaches a deployment through an operator command

**Status:** Accepted
**Date:** 2026-09-04
**Tickets:** E3-01

## Context

[ADR 0082](0082-the-tools-signing-key-lives-in-the-database.md) decided where the
tool's LTI signing key lives — a `tool_signing_key` row — and deliberately left
open where a key comes from. Its own consequence section says what that costs:
"a non-development deployment has no signing key… the first deployment that needs
to sign will need a supply route before it needs anything else in this record."
The only writer of that row today is `scripts/seed.py`, which refuses to run
anywhere but development (ADR 0063), so a deployment that is not a developer's
machine has no key at all and answers 503 at `/lti/jwks` forever.

The gap has been carried with a done-when since E1-05
(`docs/tickets/e1/deferred.md` item 1, through
`docs/tickets/e3/carried-from-e2.md`) and is owned by the epic that first
registers a real platform. That is E3, and the done-when asks for "a documented
and tested way to put a signing key in that table".

Two constraints shape the answer. The application role holds `SELECT` on that
table and no write of any kind, and ADR 0082 is emphatic about why: an
application connection that could write the column could rotate the tool's
identity, and it could do it invisibly, because a fresh key signs perfectly and
nothing goes wrong until a platform that already fetched the old public half
refuses an assertion hours later. And the key must never be printed, logged or
committed (SPEC §10, SPEC §9.1).

## Decision

**A key is supplied by `scripts/signing_key.py`, an operator command**, with
three subcommands: `generate` writes a new key and prints only its `kid`,
`retire <kid>` takes one key out of the published set, and `list` shows every
stored key with when it was supplied and whether it is still published.

**It connects as the bootstrap superuser identity**, taking the address from
`DATABASE_URL` and the identity from `DB_SUPERUSER` and `DB_SUPERUSER_PASSWORD`
— the same three variables `backend/migrations/env.py` and `scripts/seed.py`
read, for the reason ADR 0012 gives. So the write privilege the supply path needs
is held by a person running a command, not by the process serving requests, and
the grant on `tool_signing_key` is unchanged: the application role still holds
`SELECT` alone.

**No new configuration variable, and no `.env.example` line.** An operator who
has copied `.env.example` can already run this, exactly as they can already run a
migration; a fourth name that only this file read could not earn an entry there
(ADR 0008).

**No environment guard.** The demo seed refuses to run outside development
because what it writes is a demo institution; this script's entire subject is the
deployment that is not development, which is where the carried gap is.

**No key material reaches an output stream.** The `kid` is the only name printed,
which is enough because it is the RFC 7638 thumbprint — derived, never stored,
the argument `retire` takes and the name a platform selects a verification key
by. The failure path matters more than the success path here: SQLAlchemy wraps a
driver error in a `StatementError` whose text quotes the statement **and its
bound parameters**, and on the insert path one of those parameters is the private
key. So a failure that is not a refusal the script itself decided on is reported
by exception type with the message withheld.

## Alternatives rejected

**A PEM in a settings variable.** Already rejected by ADR 0082 for E1-05, and
every one of its grounds transfers unchanged: a multi-line PEM in an environment
variable is awkward enough that people single-line it and get the escaping wrong;
it puts the tool's private key in the process environment where `/proc`, a crash
reporter and any `env`-dumping diagnostic can read it; and `.env.example` would
have to carry a placeholder for a private key, which is the one thing E1-05's
fourth criterion says must never be in the repository, because a placeholder is
what somebody replaces with a real one and commits. It makes rotation a redeploy
rather than a row, which this ticket's other half is specifically about.

**A grant, so the application could write the row itself** — a `/dev` control, an
admin console button, anything on a request path. It is the shortcut the supply
path invites, because the alternative is telling an operator to hold a privileged
credential. It costs everything ADR 0082 bought: `INSERT` alone lets a compromised
request path add a key of its own to the published set, additively and invisibly;
`UPDATE` replaces the tool's identity; and the narrowest-looking version,
`GRANT UPDATE (retired_at)`, is enough to retire the last live key and take the
deployment off the air. `tests/integration/test_the_application_role_cannot_write_a_signing_key.py`
holds all four refusals as behaviour rather than as a catalog reading.

**An external key service.** Out of proportion for a pilot: it makes the tool's
identity a deployment-topology problem and adds a network dependency to the
signing path, before this project has a deployment topology at all. E13 owns the
deployment environment and its secret store, and can revisit it there.

**Teaching the demo seed to run outside development.** The cheapest edit and the
worst: ADR 0063's guard exists because that script writes a demo institution, and
weakening it to reach one row would make every other row it writes reachable in a
production database by whoever had a checkout and a `DATABASE_URL`.

## Consequences

**An operator holds the privileged database credential to supply a key.** That is
the same credential a migration needs, so it is not a new custody problem, but it
is a real one: whoever can run this can read every key the table holds. ADR 0082
already records that the key is readable by whoever can read the database as a
superuser, and this does not widen that set.

**The 503 at `/lti/jwks` names the command now.** It is a public route in every
environment (ADR 0085), so the sentence goes to anybody who asks. What it
discloses is a script in this tool's own repository and nothing about this
deployment — no path on disk, no role, no address — and what it tells an
unauthenticated reader is that this installation cannot sign yet, which the
status code already told them. The gain is that the person who *can* act on it is
told what to run instead of being left to escalate.

**Two writers of one table.** The seed still writes a key in development and the
script writes one anywhere; both hold the same privileged identity, and neither
is on a request path. The seed is unchanged in behaviour: it writes into an empty
table and never rotates, because rotation is now the operator's command rather
than a side effect of re-running a demo loader.

**The path is only as documented as its own `--help` and this record.** No
deployment runbook exists yet to put it in — E13 owns that — so the command's
docstring, its argument parser and this ADR are where an operator finds it.
