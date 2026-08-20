# E0-26 — Review debt from E0-10

**ID:** E0-26
**Branch:** `e0/review-debt-e0-10`
**Depends on:** E0-10

## Status — what is left here

**Nothing moved into a batch**, because three of the five need a thing that does
not exist until E10. What changed on **2026-08-20** is that the remaining two got
dates: item 1 is built inside this epic rather than carried, and item 5's spec
line is drafted below and waiting on Todd.

| Item | Now |
|---|---|
| 1 — the audit row and the identity read come apart on rollback | **Decided 2026-08-18: restructure the reveal** so it returns nothing until a separately committed record exists. Not `dblink`, not `postgres_fdw` — both put a credential inside a `SECURITY DEFINER` function. **Scheduled 2026-08-20: built here, in E0, before ticket 18**, rather than carried to E10. |
| 2 — the reveal writes no conflict-of-interest marking | **Carried to E10** |
| 3 — the acting person is a parameter, not a property of the connection | **Carried to E10**, which is the first thing with a request-bound actor to bind |
| 4 — the Care sweep does not cover the module's own public entry point | **Carried to E10**, which supplies the second legitimate caller the rule needs to name |
| 5 — §4.1 item 1's deferral to E2 has no home in a document E2 will read | **Drafted 2026-08-20, awaiting Todd.** The proposed wording is in item 5 below; nothing has been written to `docs/SPEC.md`. Half discharged by the README's carried-out table. |

Item 5 is partly discharged in the meantime: the README now carries a
carried-out-of-E0 table, which is the bookkeeping half of what item 5 asks for.
The spec half is still owed.

Item 1 is the only item anywhere in E0-19 to E0-37 whose subject is a live gap in
a guarantee the spec states rather than a missing assertion. It blocks nothing in
E0 and it is not hardening — and that is exactly why it was at risk of being
carried indefinitely, which is why on **2026-08-20** it was scheduled here
instead: everything the fix needs exists at this revision, and E10 is a long way
off. It is the next thing built in this epic, ahead of E0-22's constraint and
ahead of ticket 18.

**It gets the full review treatment**, decided the same day: the gated reviewer
agents that fire on its diff, both security passes — the specialist and the
generic one — and a review from a session with no prior context. On E0-38 the
cleared-context pass was the one that found what the other two missed, and this
is a `SECURITY DEFINER` function that two earlier rounds already found holes in.


## Context

What E0-10's review found and could not close in place, collected the way E0-21
collects E0-05's, E0-24 collects E0-07's and E0-08's, and E0-25 collects E0-09's,
E0-12's and E0-14's. The findings that could be closed in PR #29 were, and they
are indexed at the bottom so this file is a complete record of the round.

**One item here is different from anything in the earlier debt tickets.** Items
2 to 5 harden a guard or settle a record and block nothing. Item 1 is a live gap
in the guarantee SPEC §4 states — "every identity access is automatically
audit-logged" — and it was measured, not argued. It does not block E0's exit,
because nothing in E0 opens the Care queue, and its deadline was **before E10
builds the queue that calls the door** — which is now moot, since it is built
here. The credential narrowing that came with it in PR #29 is a reduction of the
exposure rather than a fix for it.

Three of the five are the same shape as each other: **the reveal function trusts
what it is handed and records what it is told.** The actor is a parameter rather
than a property of the connection, the audit row's survival is the caller's
choice, and the row itself carries no marking that would let a reviewer see a
conflict of interest. Each was found by a different reviewer, and together they
describe one thing: the door works, and the record of who went through it is
weaker than the door.

## Scope

### 1. The audit row and the identity read come apart when the caller rolls back

**Mechanism decided 2026-08-18: the third option.** The reveal returns nothing
until a separately committed record exists — a change to the function's shape
rather than its plumbing. Neither `dblink` nor a loopback `postgres_fdw` is
taken, because both put a database credential *inside* a `SECURITY DEFINER`
function, which is a new privilege surface of exactly the kind
[ADR 0043](../../adr/0043-the-reveal-function-has-an-owner-of-its-own.md) exists
to keep small. Its own ADR still says what the chosen shape costs.

The deadline was **before E10 builds the queue that calls the door**, and it is
now earlier than that: this is built in E0, before ticket 18.

`public.reveal_student_identity` writes its `audit_log` row and reads
`public.user_identity` in one transaction — the caller's. Postgres has already
streamed the result rows to the client by the time the caller decides what to do
with that transaction, so:

```
BEGIN;
SELECT * FROM public.reveal_student_identity(<a real CARE person id>, <any user id>, NULL);
ROLLBACK;
```

returns the name and the email address and leaves `audit_log` empty. Reproduced
twice on the pinned image, once by `app-security` using the function's own SQL
verbatim and once by the orchestrator against the same structure, each with the
controls that make it a finding rather than a coincidence: a non-CARE actor is
still refused, and the identical call without the `ROLLBACK` does write the row,
so the rollback alone is the difference.

E0-10's own acceptance criterion encodes the flaw rather than catching it. It
asks for a test that "rolling back the transaction discards both the read and the
audit row, so the two cannot come apart", the test asserts exactly that, and it
passes — because the rollback does discard both *inside the database*, after the
identity has already reached the client. `docs/MISTAKES.md` entry 3's shape once
more, and this time in the criterion rather than in the test.

**plpgsql has no autonomous transaction**, so the fix is structural. The two
candidates are `dblink` and a loopback `postgres_fdw`, both of which write the
audit row over a second connection that commits independently of the caller's.
Either introduces a contrib extension and, harder, a credential *inside* a
`SECURITY DEFINER` function — which is a new privilege surface and wants its own
ADR arguing what that credential may do and how it is held. A third option is on
the table and should be argued rather than assumed away: the reveal returns
nothing until a separately committed record exists, which changes the function's
shape rather than its plumbing.

What PR #29 did instead, on Todd's decision: corrected every place that claimed
the property — the SQL header, the migration docstring, ADR 0001, ADR 0042, and
`services/safety.py` — so nothing in the tree asserts a guarantee the database
does not provide, and narrowed `CARE_DATABASE_URL` to the `api` process so the
credential the attack needs is held by one container instead of three.

**Done when** a caller that rolls back keeps no name it is not recorded as having
taken, or the audit row survives the rollback; there is a test that performs the
rollback and reads the surviving row count from a *second connection*; and the
ADR says what the chosen mechanism costs.

### 2. The reveal writes no conflict-of-interest marking

SPEC §6.2 requires the audit entry to be flagged where the revealed student is
enrolled in a section inside the revealer's own purview. Today the two-hat person
E0-10's own happy-path tests use as the Care actor can reveal a student enrolled
in the section they teach, and the resulting row is indistinguishable from any
other reveal — so the periodic review outside the Care office that §6.2 relies on
sees nothing to look at.

PR #29 deferred this on the grounds that the column would be NULL until E9's
purview union lands. §6.2 separates the cases explicitly: "The narrow case
(enrollment in a section the revealer teaches) needs only enrollment data", and
`role_assignment.section_id` and `enrollment` both exist at this revision. So the
narrow case is computable inside the function today, at the cost of a fourth
grant on `public.enrollment` to `pulse_reveal_definer` — which is itself worth
weighing, since the whole argument for that role is that its grant list is short
enough to read against the function body.

The wide case — a student anywhere in the transitive purview of a leadership
assignment the revealer holds — stays E9's, and the column should leave room for
it rather than being defined as the narrow case.

### 3. The acting person is a parameter, not a property of the connection

`reveal_student_identity` validates the actor it is *handed*, not the actor who
is *connected*, and `pulse_care` holds `SELECT` on `public.role_assignment`, so a
credential holder can read a real Care staffer's `person_id` and pass it. Even on
the committed path the surviving audit row then names an innocent staffer, and
§6.2's periodic review cannot tell a genuine reveal from a borrowed one.

Not reachable from a request today — `reveal_identity` has no caller — so the
exposure is entirely via possession of the credential, which is why it is here
rather than a blocker. It compounds items 1 and 2: the same possession yields no
record at all, or a record naming somebody else.

The shape of the fix is binding the acting party to the session — an application
actor claim set with `SET LOCAL` and checked inside the function against the
parameter — which needs a decision about who sets the claim and what stops a
psql session setting it freely. That decision belongs with E10's queue, which is
the first thing with a real request-bound actor to bind.

### 4. The Care-service sweep does not cover the module's own public entry point

`tests/unit/test_care_session_is_bound_to_the_care_service.py` enforces the
two-hat rule by sweeping for identifiers that name a Care *session*.
`reveal_identity` is public, importable, and returns identity, and
`reads_as_a_care_session("reveal_identity")` is `False`. A later reporting module
doing `from app.services.safety import reveal_identity` for a two-hat actor
passes: the service's `CARE` check passes because the actor genuinely holds the
assignment, the function's check passes for the same reason, identity reaches an
instructor screen, and every test in E0-10 stays green.

PR #29's deferral — "there is no public factory to ask, so there is nothing to
refuse" — is sound about the *session* and incomplete about the *function*. The
sweep's settings-attribute half was closed in that PR; this half was not, because
the rule it would state is contestable: E10's Care queue router is precisely a
module outside `services/safety.py` that must import `reveal_identity`. So the
rule is not "nobody imports it" but "only the Care queue does", and the list of
who counts is E10's to write. Worth doing when there is a second legitimate
caller to name, and not before.

### 5. §4.1 item 1's deferral to E2 has no home in a document E2 will read

E0-10's ticket says §4.1 item 1 — "no student-visible path exposes another
section" — is E2's, and that is the right call: E0-10 adds no router, no
student-visible path, and none of the scoping that gives "another section" its
meaning. But SPEC §14.3's E2 entry does not mention it, no E2 ticket file exists
yet, and this epic's README records E0-10's E0-20 deferral and not this one.
Compare item 3b, which got a checklist line in `E0-20-gate-fidelity.md`.

A deferral recorded only in the ticket that deferred it is a deferral nobody
picks up. Give it a line in SPEC §14.3's E2 entry, or in the first E2 ticket file
when one exists, and a line in this README's deferral bookkeeping.

**Drafted 2026-08-20 and awaiting Todd.** Spec edits are Todd's per `CLAUDE.md`,
so this is a proposal sitting in a ticket file and *not* a change to
`docs/SPEC.md`. Three small additions to the **E2** entry in §14.3, in that
entry's existing voice:

> Add to the end of the descriptive paragraph:
>
> **§4.1 item 1 is asserted here** — no student-visible path exposes another
> section — deferred from E0, which adds no student-visible path and none of the
> scoping that gives "another section" its meaning.
>
> Add to the exit sentence, after "bounced with immediate feedback":
>
> ; and the §4.1 invariant suite carries a test for item 1 that fails when a
> student-visible path returns data from a section the student is not enrolled
> in.
>
> Add to the *Ticket breakdown* list, after "resubmission rules":
>
> §4.1 item 1 invariant.

Note that §4.1 itself is **not** silent: item 1 already carries *"(Asserted from
E2, the first epic with a student-visible path…)"*, and §4.1's preamble names it
as one of the two items with no assertion behind it. What is missing is the other
direction — somebody reading §14.3 to find out what E2 is has no way to learn
that an invariant is waiting there. The addition is bookkeeping in the document
E2 will actually be planned from, which is why it is three sentences and not a
rule.

## Out of scope

The three duplicate pairs across reviewers, all closed in PR #29 rather than
deferred: `CARE_DATABASE_URL` on the shared Compose anchor (`privacy-authz` HIGH,
`app-security` MED), the `pulse_care` grant on `role_assignment` that
`downgrade()` left in place (`data-model` HIGH, `spec-conformance` LOW), and
`queries.py`'s docstring stating the grant model backwards (`architecture` MED,
`spec-conformance` MED).

Also closed there: the identity-marker view sweep is now `invariant`-marked, the
Care-session sweep recognises `care_database_url`, the stale docstring in
`test_care_session_is_bound_to_the_care_service.py` was repaired, and the pull
request body's §4.1 accounting was corrected — the landed invariants are SPEC
§4's identity rule and §8's structural separation, not any of §4.1's six numbered
items.

## Definition of done

Per SPEC §14.2, and with the same reading as the other debt tickets: each item
either lands or is recorded as declined with a reason, and item 1 lands with a
test that reads the audit row from a connection other than the one that rolled
back.
