# 0143 — The oldest live key signs, so that `generate` publishes and `retire` switches

**Status:** Accepted
**Date:** 2026-09-05
**Tickets:** E3-08 (boundary fix round, LO-M3)

Supersedes [ADR 0127](0127-the-published-key-set-carries-every-unretired-key-and-the-newest-signs.md)
**in part**: its "the signing key is the newest live key, ordered `created_at
DESC, id DESC`" paragraph is replaced by what follows, and the rotation procedure
its Decision spells is re-ordered. Everything else that record decides — the
published set being every unretired key, one implementation in
`app.lti.registration`, retirement keeping the row, the loud refusal with no live
key, the migration's downgrade rules, and the two-column ordering itself — stands
unchanged, and its deciding fact is still the reason this rule has a tie-break.

## Context

ADR 0127 built the overlap a rotation needs: the published key set carries the
retiring key and its replacement at once. It then chose the **newest** live key as
the signer, which reads as the obvious half of "rotate to the new key".

The E3 boundary review found what that choice does to the moment it governs. A key
set is a document platforms **cache** — LTI 1.3 has each platform fetch this
tool's JWKS and hold it, and nothing in the protocol tells a platform when to look
again. Under newest-signs, `scripts/signing_key.py generate` is therefore not a
preparation: it is the switch. The instant the row lands, the tool signs every
`client_assertion` with a `kid` no platform has ever seen, and every service call
— every roster read, every grade post — fails at each platform until that platform
happens to re-fetch. The operator cannot see when that has finished, cannot bound
it, and has no way back except retiring the key they just generated.

The rotation ADR 0127 describes — generate, wait, retire — reads as if the wait
protects something. Under newest-signs the wait happens *after* the switch, so
what it protects is nothing: the outage begins at `generate` and ends whenever the
last platform re-reads.

## Decision

**The oldest live key signs, ordered `created_at ASC, id ASC`.** The tie-break is
ADR 0127's and unchanged: `created_at` is server-defaulted, Postgres gives every
statement in one transaction the same `now()`, and an ordering that stopped at the
timestamp would let the api container and the worker sign with different keys.

**The rotation procedure is therefore two acts with a wait between them, and each
act does one thing.**

1. `generate` — the new key is published beside the incumbent and **nothing
   switches**. Platforms that re-fetch during this period hold both.
2. A wait the operator chooses, long enough for the platforms this deployment
   talks to to have re-read the key set.
3. `retire <kid>` on the incumbent — the switch. The tool now signs with the key
   that has been published throughout the wait, and the retired key leaves the
   published set.

**One implementation, unchanged.** `live_signing_keys` answers the rule, the key
set publishes all of it and the signer takes its first element; only the direction
of the ordering moved.

## Alternatives rejected

**Keep newest-signs and document the outage.** The failure is at somebody else's
service, minutes to hours after the command, as a refused signature naming a `kid`
the platform does not hold. Documenting a defect whose symptom appears elsewhere
and later is not a mitigation.

**A `--switch` flag on `generate`, or a `signing_key.py use <kid>` command.** It
makes the switch explicit, which is the right instinct, and it does it by making
"which key signs" a stored fact — the discriminator column ADR 0127 already
rejected, because a stored copy of something derivable drifts and here the drift
names a key that has been retired. Oldest-signs gets the same explicitness out of
the two facts the table already holds.

**Sign with the newest key that has been published for longer than some
interval.** It automates the wait, and it does it by putting a clock in the middle
of the identity: a key becomes the signer at a moment nothing recorded, so two
processes crossing that moment sign with different keys, and the interval is a
number nobody can calibrate — platforms re-fetch on their own schedules.

**Leave it to E11's operator console.** The console will make the state visible;
it will not change which key signs, and a rotation is a thing an operator does
today with `scripts/signing_key.py`.

## Consequences

**Key material stays in use longer, and that is the price.** Under newest-signs
the replacement key starts signing at once; here it signs only after `retire`. A
rotation prompted by a *suspected compromise* is therefore two commands and a
wait, and an operator who needs the old key to stop signing immediately runs
`retire` first and accepts that assertions fail until platforms re-fetch — which
is the same outage newest-signs imposed on every rotation, now reserved for the
case that warrants it.

**A deployment that never retires anything signs with its oldest key for ever.**
ADR 0127's "a stale key can accumulate" consequence gains a sharper edge: the
accumulated keys are not merely published, the *first* of them is the one in use.
`list` is what shows it, and `retire` is what moves it.

**Nothing about the published set changes**, so a platform holding this tool's key
set is unaffected either way, and a reader of `GET /lti/jwks` cannot tell which
key signs from the document's order. The `kid` in an assertion header is what
names the signer, which was already true.

**E3-01's newest-signs tests were rewritten rather than deleted.** The behaviour
they pinned is the behaviour this record reverses, so the module that held them
now asserts oldest-signs, with the argument above written into it: the flip is a
ruled change, not a weakened assertion.
