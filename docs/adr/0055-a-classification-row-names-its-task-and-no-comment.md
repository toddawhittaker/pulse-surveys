# 0055 — A classification row names its task, carries its verdict as a token, and names no comment yet

**Status:** Accepted
**Date:** 2026-08-17
**Tickets:** E0-13

## Context

SPEC §8 lists `classification` among the core tables and says one thing about it:

> `classification` is append-only (re-runs create new rows) with prompt/model
> versioning

E0-13's scope asks for "a minimal `classification` table storing the verdict with
prompt version and model ID, append-only (re-runs create new rows, per §8)".
Three things are left open by both, and each has a defensible answer either way.

**What the row is about.** `response` and `answer` — the tables that will hold a
student's submission — are E2's. There is nothing for a foreign key to point at
today.

**How the verdict is typed.** Two of §7.4's five tasks produce a verdict, and
their vocabularies overlap without agreeing: `nonsense` is a comment-validity
verdict *and* a moderation verdict, `substantive` belongs only to the first, and
`threat` only to the second. One Postgres enum cannot be both sets, and a single
enum holding the union would permit `harmful` on a validity row.

**What makes append-only true.** §8 states it as a property of the table. Nothing
in the schema enforced it, and the two runtime roles held no privilege on any
base table at all before this ticket — E0-10 and E0-11 granted `pulse_app`
`SELECT` on five read views and nothing else. E0-13 is the first ticket in which
application code writes application data.

## Decision

**One `task` column, typed as an enum with one member today.** `COMMENT_VALIDITY`
is the only value anything writes, and each later ticket adds its member in the
same change as the code that writes it — the shape `AuditAction` already uses in
`app/models/audit.py`. The column is not speculative: without it a stored
`nonsense` says two different things and can be read as neither.

**The verdict is `text`, closed per task by a check constraint.** The constraint
is `task <> 'COMMENT_VALIDITY' OR verdict IN ('substantive', 'insufficient',
'nonsense')`, and `app/models/ai.py` builds that list from `ValidityVerdict` in
`app/ai/contracts.py` rather than spelling it again — ADR 0030 makes the enum
member's value "the token stored, serialised and compared everywhere outside
Python", so the vocabulary has one source. E2 extends the constraint with its own
arm when moderation lands.

**The row names no comment.** No `answer_id`, no `response_id`, no fingerprint of
the text. E2 adds the column, `NOT NULL`, with the foreign key it can finally
point at.

> **Amended 2026-09-01 (E2-08).** The column landed, and it landed **nullable**
> rather than `NOT NULL`. The reason is this record's own rejected alternative seen
> from the other side: there is nothing to backfill the rows written before E2-08
> from, so a `NOT NULL` column would either refuse the migration on any database
> holding one or invent a subject for it. Every row this system writes from E2-08
> onward carries the reference, and the sweep that finds floored verdicts filters
> on its presence. Nothing else here changes: the reference is real, it names an
> `answer` and not a person, and append-only is still a grant. The `ON DELETE
> RESTRICT` on it turned out to decide more than this record anticipated — see
> [ADR 0115](0115-a-resubmission-revises-its-answers-in-place.md).

**Append-only is a grant.** `classification_grants_v001.sql` gives `pulse_app`
`SELECT, INSERT` on the table and nothing else, so the connection the API and the
worker hold cannot `UPDATE` or `DELETE` a row however the application is written.
The grant ships in this ticket because the write does.

## Alternatives rejected

**A nullable `answer_id` now, filled in by E2.** Rejected: a column nothing writes
is a column every reader has to check for, and it would be `NULL` on every row in
existence when E2 arrived — so E2 would face the same backfill it faces without
the column, having carried a field that documented an intention for a whole epic.
`docs/MISTAKES.md` entry 23 is the same shape from the other side: a value
validated and read by nothing.

**A hash of the comment text as a subject key.** Tempting, because it would let a
re-run be recognised as a re-run and would survive until E2 gave it a real
reference. Rejected on confidentiality. A comment is short and often formulaic —
"it was okay", "no complaints, thanks" — so a digest of one is recoverable by
dictionary in seconds, and equal digests link the same sentence across sections
and terms. §4 permits re-identification only through the audited Care reveal
(§6.2), and this would be a join key sitting in a table every application read
path can see.

**A Postgres enum for the verdict, holding comment validity's three values.**
The instinct this project usually follows — make illegal states unrepresentable —
and here it makes the *next* state unrepresentable too: E2's moderation verdicts
do not fit, so the type is altered or a second column appears, and either way the
table's shape is decided by which task happened to be built first. The check
constraint gives the same closure per task and extends by adding an arm.

**No `task` column, one table per task, or a verdict column per task.** All three
are ways of avoiding the overlap. §8 names one table, and a schema with
`classification_validity` and `classification_moderation` makes "every
classification stores prompt version and model ID" a claim about two places —
and §6.1's drift panel, which samples across tasks, a union.

**Leaving `UPDATE` and `DELETE` grantable and enforcing append-only in code.**
Rejected on the same reasoning ADR 0001 gives for identity separation: a rule the
application enforces is a rule the next writer has to know about. E2's async
re-classification is precisely the code most tempted to update the row it is
re-running, and it will meet a permission error instead of a reviewer.

## Consequences

**The `classification` rows E0 produces cannot be attributed to a comment.** They
prove the round trip, the audit pair and the append-only property, and they
answer no question about a particular student's submission. That is the honest
state of the system before there is a submission to point at, and E2's migration
adds the column against a table holding only rows written by tests and by
whoever ran the gateway by hand.

**The check constraint is invisible to `alembic check`.** On the pinned Alembic
the constraint's *name* is compared and its expression is not — E0-08's revision
measured that and its docstring records it. So changing `ValidityVerdict` in
`app/ai/contracts.py` moves the model's constraint and not the database's, with
no drift reported. What notices is a write: a verdict outside the stored
vocabulary is refused by the server. E2 adding a task must write a migration that
replaces the constraint, and this consequence is where that is written down.

**`pulse_app` now holds a privilege on a base table**, which was not true before.
It is `SELECT, INSERT` on one table with no identity columns in it, and
`tests/integration/test_identity_grants.py`'s enumeration of what the runtime
roles hold is pinned to E0-10's revision, so this grant is outside its window by
construction. The test that asserts this one is
`test_the_application_role_may_write_a_classification_row`.
