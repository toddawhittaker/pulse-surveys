# 0127 — The published key set carries every unretired key, and the newest one signs

**Status:** Accepted
**Date:** 2026-09-04
**Tickets:** E3-01

Amends [ADR 0082](0082-the-tools-signing-key-lives-in-the-database.md) in part:
its "at most one row, enforced by the database" and "an existing key is kept,
never rotated" paragraphs are replaced by what follows, and its consequence
"rotation is unbuilt" is answered. Everything else that record decides — the
database as custody, the private PEM as the only stored half, the derived `kid`,
the unencrypted column, the withheld write grants — stands unchanged, and its
deciding fact is the reason this rule is shaped the way it is.

## Context

ADR 0082 held `tool_signing_key` to a single row with a unique index on the
constant expression `(true)`, and that was right for what it protected: two rows
were two identities for one tool, and whichever row a process read first decided
whether its assertions verified. The record says in its own consequences that the
rule is "the thing a rotation ticket must revisit first".

E3-01 is that ticket, and the reason is structural rather than a preference. A
key rotation needs a period in which the published key set carries **both** the
retiring key and its replacement, so that assertions signed before the switch
still verify while assertions signed after it verify too. Without the overlap,
replacing a key breaks every assertion in flight and every assertion any platform
has not yet re-fetched a key set for — and the failure lands hours later, at
somebody else's service, as a refused signature naming no key. A one-row table
has nowhere to put the second key, so the overlap is not merely unbuilt: it is
unrepresentable.

ADR 0082's deciding fact does not go away. SPEC §7.2 runs an `api` container and
a `celery` worker; both sign, and a platform verifies an assertion against
whichever published key its `kid` names. What the one-row rule bought was that
the two processes could not disagree about which key that is. Any replacement has
to buy the same thing.

## Decision

**The published key set is every stored key with `retired_at IS NULL`.** A
rotation is `generate`, a wait long enough for every platform to re-fetch the key
set, and then `retire` on the old key. Both keys are in the document in between,
which is the overlap.

**The signing key is the newest live key, ordered `created_at DESC, id DESC`.**
Two ordering columns, and the second is not decoration: `created_at` is
server-defaulted, Postgres gives every statement in one transaction the same
`now()`, and an ordering that stopped at the timestamp would leave the choice
between two same-instant rows to the storage layer — which is stable until an
index changes and then silently is not. That is exactly ADR 0082's deciding fact
returning, and the tie-break is what keeps the api container and the worker
agreeing.

**One implementation, in `app.lti.registration`.** `live_signing_keys` answers
the rule; the key set publishes all of it and the signer takes its first element.
A second implementation would agree until somebody changed one of them, and the
disagreement is a `kid` in an assertion header naming a key the published
document does not carry.

**Retirement sets `retired_at` and the row stays.** The key leaves the published
set immediately and the record of what this deployment used to sign with stays in
the database. Retirement is executable — `scripts/signing_key.py retire <kid>`
(ADR 0126) — because a key set that can hold two keys is otherwise a place for a
stale key to live forever.

**No usable key is still a loud refusal.** `GET /lti/jwks` answers 503 rather
than `{"keys": []}`, and the decision is keyed on the live rows rather than on the
row count: a deployment can hold several keys and have retired every one of them,
which is an ordinary mistake to make in the middle of a rotation. ADR 0085's
reasoning is unchanged — an empty key set is a document a platform accepts and
stores.

**The migration's downgrade refuses an ambiguous identity, and discards the
retired records.** Below E3-01's revision the one-row index is back, so a database
holding a rotation cannot be represented there — and the two things at stake in
that sentence get two different answers.

More than one **live** key is refused. Completing would have to choose which of
two identities survives, and the one it discarded may be the private half of a key
a platform has already fetched. The downgrade counts first and stops with a
sentence naming retirement as the way back to a single signing identity, leaving
every row and the stamped revision as it found them.

With one live key — or with none — it **deletes the retired rows** and proceeds.
Those rows are the record of what this deployment used to sign with, not an
identity anything still verifies against, and the one-row schema has nowhere to
put them.

**The guard counts live keys rather than stored ones, and that is what makes its
own advice reachable.** A guard counting every row would name retirement and then
refuse the retired row it had just been handed: an operator following the
instruction could never satisfy it. Counting the unretired rows makes `retire` a
route down, and the migration finishes the job by removing what retirement leaves
behind.

## Alternatives rejected

**Keeping the one-row rule and rotating by replacing the row.** What ADR 0082
described, and it is not a rotation: it changes both the `kid` and the key with no
overlap window, so every assertion signed by the old key fails from that moment.

**A partial unique index over the unretired rows** — at most one *live* key, with
retired rows unconstrained. It reads like a safer widening and it forbids exactly
the state the widening exists to create: the second key cannot be supplied while
the first is still published, so there is never an overlap.

**A discriminator column — `is_active`, or a pointer to the current key.** It
makes "which key signs" a stored fact rather than a derived one, so the two
processes read one row and cannot disagree. Rejected because a stored copy of
something derivable drifts (`docs/MISTAKES.md` entry 19), and here the drift is a
flag naming a key that has been retired, or naming none; the ordering rule
computes the same answer from the two facts that are already recorded.

**A downgrade that keeps the newest live key and discards the other one.** It
would let the revision go down unconditionally, which is what a reversible
migration is supposed to mean. Rejected because what it discards is a key a
platform may already have been registered against: nothing regenerates it, no
platform accepts a replacement without a re-registration, and the loss is silent
at the moment it happens. The refusal makes the operator decide which identity
goes, with `list` in front of them, which is the same outcome with somebody
accountable for it. The retired rows are a different question and are answered
differently above — no identity is at stake in them.

**A downgrade whose guard counts every stored row.** The first shape this took,
and it does not cohere: it advised retirement, and retirement keeps the row, so an
operator who did exactly what the message said still met the same refusal. The
choice was between advising a hand-written `DELETE` — the thing the guard exists
to prevent somebody reaching for — and counting the rows that actually make the
identity ambiguous. Counting live keys is the second.

**Ordering by `created_at` alone.** One column is simpler and is right almost
always. Rejected on the tie: a supply script that wrote a key and its replacement
in one transaction produces two rows sharing an instant, and a single run of a
single process usually answers consistently — which is what makes that defect
ship.

## Consequences

**The guarantee moves from the schema into the readers.** The database no longer
refuses a second identity; `live_signing_keys` and the `kid` on every assertion
are what make two keys two published keys rather than two identities. That is a
weaker place to hold a rule than a unique index, and it is the price of the
overlap. What holds it now is a test suite that plants a rotation and asks which
key signed, rather than a constraint that cannot be argued with.

**A stale key can accumulate.** Nothing expires a key or bounds how many the set
carries; `retire` is a command somebody has to run. `list` exists so the state a
rotation is halfway through is visible, and a deployment that never retires
anything publishes a growing set of keys it still holds the private halves of.

**A downgrade below this revision discards the retired-key records**, and that is
the price of returning to the one-row world rather than an oversight. Everything a
retired row holds — which key this deployment used to sign with, and when it
stopped — is gone from the database once the walk down completes, and only a
backup has it after that. What is *not* discarded is an identity anything still
verifies against: the published set stopped carrying those keys the moment they
were retired. The loss is not silent either, since it happens under an explicit
`alembic downgrade` an operator ran, usually after following this migration's own
refusal message.

**Deleting a retired row on a live database is a manual act with no command.**
`retire` does not delete and nothing else does, which is deliberate — the row is
the record — so shrinking the table outside a downgrade means a hand-written
statement as the privileged identity. A `signing_key.py forget <kid>` is the
obvious next command and is deliberately unbuilt: nothing needs it yet, and the
downgrade is the one place the removal has to happen.

**Two keys are two reads on a public route.** `GET /lti/jwks` now loads and
derives a JWK per live key on every request, where it loaded one. It is still
milliseconds over a table with a handful of rows, and ADR 0085's rejected
per-process cache is still the answer if it ever stops being.
