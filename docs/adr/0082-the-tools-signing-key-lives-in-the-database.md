# 0082 — The tool's signing key lives in a one-row database table

## Context

LTI 1.3 is asymmetric in both directions. A platform signs a launch and this
tool verifies it against keys fetched from the platform's JWKS URL — that half
has existed since E0-18. The other half arrives with E1-06: to call a platform's
Names and Role Provisioning or Assignment and Grade service, this tool presents
a **client assertion** it has signed with a key of its own, and the platform
verifies it against a public key set the tool publishes. So the tool needs a key
pair. E1-05's fourth acceptance criterion is that it exists in a development
bring-up with no private key committed anywhere in the repository, and the
ticket says in as many words that custody — "settings variable, file path, or
database" — is a real decision that gets an ADR.

**The fact that decides it: two processes, one tool.** SPEC §7.2 runs an `api`
container and a `celery` worker, and §14.3 puts the roster sync on the worker
while the launch flow is on the api. Both will sign, and a platform holds the
public half of exactly **one** key. Two processes signing with two keys means
half the assertions are rejected, by a platform, with an error about a signature
rather than about custody — and the half that works keeps working, so nothing
looks broken until it is somebody else's incident.

That rules out anything per-process or per-container before the options are even
compared, and it is worth stating first because the obvious implementation —
generate a key at startup — is exactly the shape it kills.

## Decision

**A one-row `tool_signing_key` table holding `private_key_pem` and nothing
else.** The seed generates RSA 2048 in PKCS#8 PEM, unencrypted, behind ADR
0063's development guard, checked at the write itself the way `seed_mock_platform`
checks it (ADR 0068).

**Only the private half is stored.** The public key and the RFC 7638 `kid` are
both derived from it on read. A stored copy of something derivable is a copy that
can drift out of step with what it was derived from (`docs/MISTAKES.md` entry
19), and here the drift would be a JWKS document advertising a key that no longer
signs anything.

**At most one row, enforced by the database**, as a unique index on the constant
expression `(true)` — the shape ADR 0072 chose for `institution`, for the reason
it gives: a check constraint sees one row at a time and cannot count its own
table. The index is **not** on `private_key_pem`; unique key material would
permit any number of rows holding *different* keys, which is precisely the state
this exists to refuse. Two rows is not an untidy state to reconcile later, it is
two identities for one tool, and whichever row a process reads first decides
whether its assertions verify.

**An existing key is kept, never rotated.** Rotation is the dangerous failure
because it is invisible at the moment it happens: a fresh key signs perfectly,
and nothing goes wrong until a platform that already fetched the old public half
rejects an assertion hours later.

**Unencrypted, deliberately.** A passphrase would have to come from somewhere the
signing process can reach unattended. In the same database it is not a second
factor; in the environment it moves custody back to the option this record
rejects. What protects the column is the grant on it.

**No `pulse_app` grant in E1-05.** Nothing reads the key until E1-06 signs with
it, and a runtime role holding read access to a private key it never opens is a
credential at rest with no owner. The grant lands in E1-06 with the code that
spends it, which is also where the §4.1 grant equality has its loud-red
conversation about it.

**No configuration variable and no `.env.example` line.** Custody is the
database, so there is no value for an operator to supply and no
`app.config.Settings` field resolves to one — which is what the epic README's
rule keys that line on.

## Alternatives rejected

**A PEM in a settings variable.** It satisfies the shared-key requirement:
every process reads the same `.env`. It fails on three other counts. A
multi-line PEM in an environment variable is awkward enough that people
single-line it and get the escaping wrong, and the failure is at first use. It
puts the tool's private key in the process environment, where `/proc`, a crash
reporter and any `env`-dumping diagnostic can read it, and where this project's
own `.env.example` rule would have to carry a placeholder for a private key —
the one thing E1-05's criterion 4 says must never be in the repository, even in
placeholder form, because a placeholder is what somebody replaces with a real
one and commits. And it makes rotation a redeploy rather than a row.

**A key file at a configured path.** The conventional answer, and it is what a
single-container deployment would reach for. It breaks the deciding fact: two
containers is two filesystems, so either the file is baked into an image — the
same key in every deployment and in every fork, which is the exact failure
`test_no_private_key_material_is_committed_to_the_repository` exists to prevent,
relocated — or it is a mounted secret, which makes the tool's identity a
deployment-topology problem before this project has a deployment topology. It
also adds a configuration variable and a filesystem dependency to a service that
otherwise has neither.

**Generating a key per process at startup.** Zero configuration and no custody
question at all. It gives the api and the worker different keys, and the tool a
new identity on every restart, so a platform that fetched the key set five
minutes ago rejects the next assertion. Rejected outright by the deciding fact,
and named here because it is the cheapest thing to write and reads as fine
until there are two processes.

**Deferring the key to E1-06 entirely.** The signing code is there, so the key
could be. Rejected because E1-05 is the ticket that owns the registration's
schema and this is a schema decision; splitting it would put the table, the
one-row rule and the seeding in the same change as the first thing that reads
them, which is a larger and less reviewable diff, and would leave E1-05's fourth
criterion unmet.

## Consequences

**A non-development deployment has no signing key.** The seed generates it and
the seed runs only in development, so nothing outside a developer's machine has
one — and nothing outside development signs, because E1-06 and E1-11 run against
the mock platform in development. That is a deliberate gap rather than an
oversight, and it has an entry with a "done when" in
`docs/tickets/e1/deferred.md`, owned by the epic that first registers a real
platform. The first deployment that needs to sign will need a supply route
before it needs anything else in this record.

**The key is readable by whoever can read the database as a superuser**, which
is the same set that can read `user_identity`. That is the custody this buys and
it is not a strong one; what it buys over the alternatives is that there is
exactly one key, that no process has to be told where it is, and that the runtime
role holds no grant on it at all until a ticket deliberately adds one.

**Rotation is unbuilt.** Deleting the row and re-seeding produces a new key with
no overlap window, so every assertion signed by the old one fails from that
moment. A real rotation needs two keys published at once with `kid` selecting
between them, which the one-row rule forbids by design — the rule is right for
now and is the thing a rotation ticket must revisit first.

**`tool_signing_key` is not a person table.** It holds no subject, no name and
no address, so SPEC §4.1's `PERSON_TABLES` does not change. That is the question
`docs/tickets/e1/deferred.md` item 2 asks of this ticket, answered.

**The PEM must stay out of every output.** `make seed` runs in a terminal, in
CI and inside `docker compose logs`, and a private key printed once is in a
scrollback buffer, a CI artefact and whatever gets pasted when somebody asks for
help (SPEC §10). Two tests hold it: one asserts the seed's own output carries
neither the stored value nor PEM armour of any kind, and the repository-wide
sweep for committed key material now names E1-05 as its second subject rather
than a second sweep being written.
