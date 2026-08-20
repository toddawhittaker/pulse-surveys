# 0071 — The reveal answers only a record that is already committed

**Status:** Accepted
**Date:** 2026-08-20
**Ticket:** [E0-26](../tickets/e0/E0-26-review-debt-from-e0-10.md), item 1
**Relates to:** [ADR 0001](0001-identity-separation-by-database-role.md), whose
"one transaction" consequence this replaces;
[ADR 0043](0043-the-reveal-function-has-an-owner-of-its-own.md), whose grant
budget this widens by one; and
[ADR 0042](0042-the-care-pool-has-its-own-credential-and-opens-on-first-use.md),
which decides who may call the door.

## Context

SPEC §4 states a guarantee: "Re-identification is possible only through the Care
queue (§6.2), only by the Care role, and **every identity access is automatically
audit-logged** with actor, timestamp, and case."

E0-10 built that as one `SECURITY DEFINER` function which wrote the `audit_log`
row and read `public.user_identity` in one transaction — the caller's. Postgres
has already streamed the result rows to the client by the time the caller decides
what to do with that transaction, so

```
BEGIN;
SELECT * FROM public.reveal_student_identity(<a real CARE person id>, <any user id>, NULL);
ROLLBACK;
```

returned the student's name and email address and left `audit_log` empty.
Reproduced twice on the pinned image during E0-10's review, each time with the
controls that make it a finding rather than a coincidence: a non-CARE actor was
still refused, and the identical call without the `ROLLBACK` did write the row, so
the rollback alone was the difference. The party who can separate the read from
the record is the one holding the `pulse_care` credential — which is exactly the
party §4's sentence is about.

E0-10's own acceptance criterion encoded the flaw rather than catching it. It
asked for a test that "rolling back the transaction discards both the read and
the audit row, so the two cannot come apart"; the test asserted that and passed,
because the rollback does discard both *inside the database*, after the identity
has reached the client. That is `docs/MISTAKES.md` entry 3's shape, in the
criterion rather than in the test.

`plpgsql` has no autonomous transaction, so nothing inside one function can write
a row the surrounding transaction cannot take back. The fix is structural.

## Decision

**The door is two calls, and the second one answers only against a record whose
writing transaction has committed.**

```sql
public.record_identity_reveal(
    in_actor_person_id uuid, in_subject_user_id uuid, in_case_id uuid
) RETURNS uuid                       -- the audit_log row's id

public.reveal_student_identity(in_reveal_id uuid)
    RETURNS TABLE (identity_name text, identity_email text)
```

The recording call refuses an actor with no live `CARE` assignment, writes the
row, and hands back its id and nothing else — it is declared `RETURNS uuid`, so
there is no path on which it can return a name. The reveal takes only that id,
reads its subject and its actor **out of the record**, re-checks that the actor
still holds `CARE` and that the record is an `IDENTITY_REVEAL`, and returns
identity. A caller that rolls back therefore keeps nothing: the rollback destroys
the record, and without a committed record the reveal raises.

The three-argument function is **dropped** rather than kept beside the new one.
Postgres overloads on argument types, so creating the one-argument reveal does
not replace the old one, and a door that still opens the old way is not closed.

**Every refusal raises**, with its own SQLSTATE, and none returns zero rows. Zero
rows is already the answer for a student who has no `user_identity` row at all —
an ordinary state, which `services/safety.py` hands back as `None` — so a refusal
that returned nothing would reach §6.2's queue as "no identity on file" about a
student the queue is open on. A refusal indistinguishable from an absence is a
wrong answer wearing the right one's clothes.

**"Committed" is asked of `pg_catalog.pg_xact_status`, and not of the row's
`xmin` against the current transaction.** The obvious spelling — compare
`audit_log.xmin` with `pg_current_xact_id()` and refuse where they match — is
wrong, and wrong in the direction that opens the door. A caller that wraps the
recording call in a `SAVEPOINT` gives the row a *sub*transaction id, which
differs from the top-level one, so the comparison decides the row belongs to
somebody else and answers against a record that still vanishes on `ROLLBACK`. A
savepoint is not exotic: SQLAlchemy's `begin_nested`, `plpgsql`'s own
`BEGIN … EXCEPTION` block and psql's `\set ON_ERROR_ROLLBACK` each open one.

`pg_xact_status` is not defeated by that, because it reports `in progress` for
the calling transaction *and every subtransaction of it* — measured on the pinned
image, plain and inside a released savepoint, with the top-level id and the row's
`xmin` printed side by side to show they differ. It is a `pg_catalog` function
executable by `PUBLIC`, so it costs no grant. It takes a 64-bit transaction id and
`xmin` is the 32-bit one, which carries no epoch; the epoch is taken from the
current snapshot's `xmax`, because every transaction whose row is visible to this
statement completed before that snapshot and so belongs to the same epoch.

**The definer role gains a fourth grant, `SELECT` on `public.audit_log`**, which
[ADR 0043](0043-the-reveal-function-has-an-owner-of-its-own.md) budgeted at three.
It is necessary and not incidental: the reveal reads its subject, its actor, its
action and its `xmin` out of the committed record, and reading a record it may
only write is not possible. See the consequences for what it exposes.

**`services/safety.py`'s `reveal_identity` keeps its signature and stays one call
from a caller's point of view.** §6.2 requires "a plain, one-click procedural
action", and that is about what Care staff do rather than about how many
statements the service sends. It records, commits, and then reveals in a second
transaction on the same Care session.

## Alternatives rejected

**`dblink`, or a loopback `postgres_fdw`, writing the audit row over a second
connection that commits independently of the caller's.** The two candidates
E0-10's review named, and the reason they are not taken is the same for both:
each puts a database credential *inside* a `SECURITY DEFINER` function. That is a
new privilege surface of exactly the kind ADR 0043 exists to keep small — a role
whose whole argument is that its grant list is short enough to read against the
function body would then also hold, in its body, the means to open a connection
that is not bounded by any grant at all. It also adds a contrib extension to the
image and a second credential to provision, hold and rotate. Todd's decision,
2026-08-18. What it would have bought is real and is what the accepted shape gives
up: with it, the record survives the caller's `ROLLBACK`, so the log records
accesses that happened rather than accesses that were authorised.

**Leave it, and rely on the credential being narrowed.** PR #29 did exactly this
as a stopgap and said so: `CARE_DATABASE_URL` reaches only the `api` process, so
the credential the attack needs is held by one container instead of three.
Rejected as a reduction of exposure rather than a fix — the finding is that §4's
sentence is false against a caller who holds the credential, and §6.2's whole
design is that such a caller exists and is trusted only because there is a record.

**Make the recording call return identity as well, so the queue makes one round
trip.** Rejected because it undoes the decision: a caller that obtains the name
from the first call has no reason to make the second, and the whole exchange is
back inside one transaction it can roll back. This is why the recording call is
declared `RETURNS uuid` rather than being a matter of what its body happens to
do — `test_the_recording_call_hands_back_an_identifier_and_never_identity` reads
that out of `pg_proc`, `OUT` parameters included.

**Keep the three-argument function beside the new pair**, so that nothing which
calls it has to change. Rejected: nothing calls it — `reveal_identity` is its only
caller and it is in this change — and an overload that still opens the old way
means the exact `BEGIN; SELECT …; ROLLBACK;` that was measured still works.

**Have the reveal refuse any record written by the connection now asking**, which
needs no transaction-status introspection at all. Rejected because it closes the
door on the honest path: `services/safety.py` records, commits and reveals on one
Care session, which is what a single pooled connection does. The property wanted
is that the record is *committed*, not that it belongs to somebody else.

## Consequences

**The log over-records rather than under-records, and that is a real change in
what a row means.** A caller that commits a record and then never spends it —
because the reveal raised, because the process died, because it simply chose not
to — leaves a row saying an access was authorised when no name was read. §6.2 has
this log "reviewed periodically outside the Care office", and that review reads a
row as an access. The direction is deliberate: for a safety log, a record of an
access that did not happen is recoverable and a missing record of one that did is
not. `models/audit.py` and `AuditAction.IDENTITY_REVEAL` say "authorised" rather
than "obtained" for this reason, and E10, which builds the queue and the review
surface, inherits the distinction rather than discovering it.

**The definer can now read every row of `audit_log` — who revealed whom, and
when.** Before, it could write a record it could not read back, which was itself
part of E0-10's grant model. What bounds the widening is the two function bodies:
they read one row by primary key, take four of its columns, and return none of
them to a caller. Nothing else can spend the grant, because the role is `NOLOGIN`,
nothing gives it a password and nobody is a member of it. But ADR 0043's own
warning applies with full force here — "the fail-closed property lasts exactly as
long as nobody adds a grant beside the line that needed it" — and this is the
first time that budget has moved. `pulse_care` still holds nothing on `audit_log`:
the record it causes to be written is still not one it may read.

**A committed record is a capability, and nothing limits it to one use.** The
reveal can be called twice against the same id and will answer twice, writing
nothing the second time. Whether a record may be spent more than once is a
question this ticket deliberately leaves open and E10's queue should settle, since
that is where a reveal has a case and a disposition to be spent against. The
practical bound today is that obtaining a second name still needs a second
committed record.

**Two of E0-10's three review findings are untouched and both are E10's.** The
acting person is still a parameter rather than a property of the connection
(E0-26 item 3), so a holder of the `pulse_care` credential can record a reveal in
a real Care staffer's name and the surviving row will name them; and the row still
carries no conflict-of-interest marking (item 2). This record closes the gap
between the read and the record, and it does not make the record's *contents*
trustworthy against a credential holder.

**A caller now sees four distinct refusals from the reveal**, by SQLSTATE: no such
record (`no_data_found`), the record is not an `IDENTITY_REVEAL`
(`invalid_parameter_value`), the record is not committed
(`object_not_in_prerequisite_state`) and the record's actor no longer holds `CARE`
(`insufficient_privilege`). `services/safety.py` does not yet distinguish them —
they all surface as a database error — and E10's queue is where a caller has a
screen to show them on.

**`downgrade()` puts the defect back**, because that is what a downgrade is: the
database ends at revision `7b41d2c9e6af`, where the reveal is E0-10's
three-argument one. The revision says so at the point where it recreates it, and
the one privilege the drop cannot carry with it — the definer's new `SELECT` on
`audit_log`, on a table that outlives the revision — is revoked by hand, guarded on
the role existing, following the rule `446183e8cc5f` already sets.

**`alembic check` sees none of this.** It compares `Base.metadata` against the
database, so it reads tables and columns and neither `pg_proc` nor an ACL — the
table in ADR 0043 measured six mutations of exactly this kind, all clean. Dropping
one of these functions, restoring the three-argument one, or granting the definer
a fifth privilege all leave the drift gate green.
`tests/integration/test_the_reveal_commits_its_record.py`, five of whose tests are
`invariant`-marked so a skip is a build failure, and
`tests/integration/test_identity_grants.py` are the only readers. E0-20 item 3b
carries the gate's blindness.

**`tests/integration/test_identity_grants.py` fails against this change and has to
move onto the new interface.** Its `the_reveal_function` helper asserts that
`pulse_care` may execute exactly one `SECURITY DEFINER` function and there are now
two; four of its tests call the reveal inside a session that never commits, which
this shape refuses by design; and
`test_the_reveal_writes_its_audit_row_in_the_callers_own_transaction` asserts that
the row does *not* survive a rollback, which its own docstring already said E0-26
inverts. That migration is a partitioned round of its own
(`docs/MISTAKES.md` entry 22) and belongs to the test author, not here.
