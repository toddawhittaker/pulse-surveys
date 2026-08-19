# 0067 — Drift in what `alembic check` cannot see is caught by rebuilding the model into a probe schema

**Status:** Accepted
**Date:** 2026-08-18
**Tickets:** E0-33
**Relates to:** [ADR 0015](0015-course-level-is-a-stored-generated-column.md),
whose generated column is the first object this compares;
[ADR 0043](0043-the-reveal-function-has-an-owner-of-its-own.md), whose owner rule
is asserted by the suite this extends; and
[ADR 0041](0041-a-read-view-ships-as-an-immutable-versioned-sql-file.md), which
is what stands where this stops.

## Context

`alembic check` compares `Base.metadata` against the database, and
`Base.metadata` holds tables and columns. A generated column's expression, a
check constraint's expression, an exclusion constraint, a role, a grant, a view
and a function are outside that comparison in both directions. E0-20 measured it
on the pinned Alembic 1.19 with a dropped column as the canary, so that "clean"
is distinguishable from a comparison that has gone blind: every one of those
mutations reported clean.

Two of them are not hardening. `GRANT SELECT ON public.user_identity TO
pulse_app` and `ALTER ROLE pulse_care SUPERUSER` are each a single statement that
voids the whole of SPEC §4.1's confidentiality model, and the gate calls both
clean.

For the objects that *are* in `Base.metadata` but whose definitions are not
compared — generated columns and constraints — the assertion needs both sides
rendered in the same dialect. Postgres does not store the SQL text you wrote; it
stores a parse tree and deparses it on request, so `pg_get_expr` returns
`CASE WHEN (lms_number ~ '^[0-9]{3}$'::text) THEN …` regardless of how the
migration spelled it. The model's side is a Python string.

## Decision

**Compare deparsed output with deparsed output, by making Postgres render both
sides.** A fixture copies `Base.metadata` into a throwaway schema with
`to_metadata` and `create_all`, inside the existing per-test transaction, and the
comparison reads `pg_get_expr` and `pg_get_constraintdef` from *both* the probe
schema and the migrated `public` schema. Nothing normalises text by hand.

Three consequences of that choice are themselves decisions:

**The objects under test are found by reflection, not by name.** Generated
columns are those where `attgenerated` is not empty; constraints are filtered by
`contype`. A generated column added in E4 is covered without anyone editing this
module, which is the difference between an assertion and a list.

**Both directions are asserted, as separate tests.** "Every rule the model
declares, the database carries" is satisfied by a model that declares nothing —
which is exactly how E0-20 measured the exclusion-constraint row, by deleting it
from the model. Each direction also carries a vacuity guard, because a comparison
between two empty sets passes and says nothing (`docs/MISTAKES.md` entry 3).

**The comparison is itself tested before anything is built on it.** Two
self-tests execute `upper(value)` against `UPPER ( ( value ) )` and require
*equal*, and against `lower(value)` and require *different*. A comparison of two
deparsed expressions is worth exactly what the deparser is worth, and that is a
claim to run rather than to assert.

**Reachability is asked per mechanism, from a table of probes.** A privilege can
be held as a grant on a table, a grant on one of its columns, by ownership, by a
role attribute, by membership, or as `EXECUTE` on something that runs as somebody
else — and a guard phrased over one of those is systematically blind to a scheme
that deliberately uses another.

Three probes cover identity, and the argument for closure is about catalogs
rather than about a list, because a list has now been wrong twice here. A
privilege that yields identity *data* is recorded in exactly one of three places:
`pg_class.relacl` for the table, `pg_attribute.attacl` for one of its columns,
and `pg_proc.proacl` for a function that reads it — which counts only when
`SECURITY DEFINER`, since an ordinary function runs as its caller and hands out
nothing the caller lacks. Each probe reads one. `pg_database.datacl` and
`pg_namespace.nspacl` are deliberately not probed: `CONNECT` and `USAGE` gate
whether an object can be *reached* and confer no read. A superuser, an owner and
a membership in a predefined role such as `pg_read_all_data` are subsumed by the
table probe rather than omitted, because each answers `has_table_privilege` with
no ACL entry existing at all.

**The probes are asked about two different questions and the answers differ.**
Asked about a role a runtime role can *become*, every mechanism is dangerous.
Asked about the runtime roles themselves, `EXECUTE` is filtered, because
`pulse_care` holds it by design and a rule reporting it would fail against a
correct schema. Missing the second question entirely is what left a direct column
grant unguarded through a whole review round while the probe that could see it
already existed.

Each sweep carries a control requiring it to *find* a route on a subject known to
have one, and the probes sit one per line in a table so that disabling one is a
single edit that still parses. That is what makes the control demonstrable rather
than merely asserted — and the control has to be asked *through* the table, not
of the probe function directly, or deleting the row leaves it green and it guards
nothing.

For roles, grants, views and functions — which are in no metadata at all — the
expectation is held as a **frozenset derived from the ticket and spec sentences
that justify each entry**, and compared as an equality. This is not a new
decision: `REVEAL_DEFINER_PRIVILEGES` in the same module made it in E0-10, and
`docs/MISTAKES.md` entry 19 is the rule ("a test held its expectation in a copy
of the thing it was checking").

## Alternatives rejected

**Write a normaliser for the model's text.** The obvious approach, and it fails
on the first argument: a normaliser that folds case, strips parentheses and
collapses whitespace enough to make `upper(value)` match `UPPER ( ( value ) )`
is a small SQL parser, maintained here, whose bugs are silent in the safe
direction. Postgres already has one and it is the same one that will render the
value in production.

**Derive the grant expectation from the `GRANT` statements in
`views_sql/*.sql`.** Superficially the stronger reading of "exactly what the
migrations wrote" — but in this repository a grant *is* a line in one of those
files, so the derived set goes green on precisely the convenience grant the
assertion exists to catch, while reading as a stronger test than the hand-derived
one. It buys zero maintenance and gives up the catch. The hand-derived set went
red on its first legitimate drift (E0-13's `classification` grant) before it was
ever committed, which is the mechanism working: a red on a legitimate change
costs one line and a sentence, and a green on a widening is silent.

**Assert the objects out of the migration that creates them.** This is the trap
E0-20 names under both 3a and 3b. An object read back from the file that wrote it
reads like coverage and is not; nothing re-reads the database in either
direction.

**Make the server refuse the drift instead of a test noticing it.** For grants
that would mean event triggers on `GRANT`, and for views it would mean
`security_invoker`, which E0-10 and E0-11 both deliberately did not choose. Out
of scope here and named as such in E0-33.

## Consequences

A generated-column expression, a check-constraint expression, an exclusion
constraint, a fourth ACL grantee on a relation or on a definer function, a
runtime role's privilege on a base table, a non-inheriting role membership, a
dropped view and a re-owned `SECURITY DEFINER` function each now fail a named
test. Thirty-eight distinct mutations were run against these assertions across
five rounds, including nine near-misses that must stay green; the table is in
E0-33's pull request.

**An earlier version of this paragraph claimed that "a non-inheriting role
membership" failed a named test, without qualification, and that was false when
written.** The first version of the sweep built its dangerous set from *table*
privileges on the identity table, so it caught a membership into a role holding
a grant there and missed a membership into `pulse_care` — which by ADR 0001's
design holds no such grant, and reaches identity by `EXECUTE` on the reveal
function instead. The independent security review found it; it was confirmed by
measurement and fixed before merge, and `docs/MISTAKES.md` entry 35 is the rule
it produced.

**The probe schema costs a `create_all` per test that uses it.** Measured on
this stack with `--durations`: 0.04s of setup per test, against 1.85s for the
first test's container start and migration, and 2.47s for the module. It is
function-scoped because at that price there is nothing to buy by caching it. If
it becomes slow the fix is a module-scoped fixture on its own connection, not a
narrower comparison.

**A grant added to a `views_sql/*.sql` file is still self-justifying to a
reader.** The equality catches it — the file is not the source of the expectation
— but nothing stops the author of that file from also adding the entry to the
frozenset. What stands there is ADR 0041's rule that a view ships as a new
immutable versioned file so the diff is read, plus E0-34's guard on the file
text. This is a review control, not a server control, and E0-33 does not change
that.

**Two properties are asserted twice**, once behaviourally and once out of the
catalog, and that is deliberate: `docs/MISTAKES.md` entry 3 records that the
catalog test cannot see whether the rule works and the behavioural test cannot
see whether it exists. For the column-grant route the pair is uneven and the
catalog half carries it alone — a behavioural `SELECT *` stays refused while
`SELECT identity_name` succeeds — which is why that catalog assertion is
`invariant`-marked.

**A constraint must now be declared on the model, not only written into a
migration.** The database-to-model direction means a check or exclusion
constraint stated in SQL alone — a legitimate choice for a rule SQLAlchemy cannot
express — fails `test_the_database_carries_no_constraint_of_this_kind_the_model_does_not_declare`.
That is a standing obligation on every future migration and the author would
otherwise meet it as a surprise. If a later migration deliberately states a rule
in SQL alone, that test is where the decision is recorded and the exemption
argued; it is not a reason to drop the direction, because the direction is what
catches a constraint removed from the model.
