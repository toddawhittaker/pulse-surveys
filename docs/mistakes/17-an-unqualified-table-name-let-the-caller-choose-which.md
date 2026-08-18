# Entry 17. An unqualified table name let the caller choose which table a guard read

**Caught: 1**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*


**What happened.** E0-09's supervision-edge trigger names `role_assignment`
unqualified in all three of its guard queries and in `'role_assignment'::regclass`,
which keys its advisory lock. Postgres searches the temporary schema **first** for
relation names, and does so whether or not `pg_temp` is in `search_path` — being
unlisted is what puts it first, not what skips it. So a caller who creates
`pg_temp.role_assignment` and then writes `public.role_assignment` gets all three
guards reading an empty temp table.

Reproduced on the pinned Postgres as a `NOSUPERUSER NOCREATEDB NOCREATEROLE` role
with no `CREATE` on `public`, because creating a temporary table needs only the
`TEMPORARY` privilege, which Postgres grants to `PUBLIC` by default. The
two-assignment cycle and the edge into a `CARE` assignment that the same role had
been refused seconds earlier both committed. The lock key moved too, so the
serialisation ADR 0027 rests on went with it.

The generic security review found it. Nothing could reach it — `pulse_app` holds
only `CONNECT` — but E0-10 is the ticket that grants the DML, and the bypass
would have arrived with those grants, silently and in a file nobody was editing.

**Root cause.** Writing SQL that runs *later* as though it ran *now*. Everything
else in the schema — check constraints, generated columns, foreign keys,
exclusion constraints — is resolved to OIDs when the DDL runs, and is immune;
measured, five for five, with shadows in place. A `plpgsql` body is the one place
in this repository where a name is resolved on every call, and it was written in
the same style as the rest.

**Consequence.** Caught before it could be reached, so the cost was one round.
Had it landed with E0-10's grants, all three of the rules the ticket exists to
enforce would have been bypassable by any authenticated application session, with
276 tests still green — no fixture creates a temporary table, so removing the
qualification is invisible to the suite today.

**Rule.** In any SQL that is parsed at call time — a `plpgsql` body, anything
built for `EXECUTE` — **schema-qualify every relation**, and
put `SET search_path = pg_catalog, public, pg_temp` on the function. Both, not
either: the qualification survives someone dropping the `SET`, and the `SET`
survives someone adding an unqualified reference. Name `pg_temp` **explicitly and
last** — a `search_path` that merely omits it, which is the usual advice, leaves
the hijack open, and that difference was measured rather than assumed. And verify
it the way it is exploited: stand up the shadow table as a non-superuser role and
watch the write be refused, rather than reading the SQL and agreeing with it.

**A view is not in that list, and the first version of this entry said it was.**
E0-10's test author queried the clause rather than editing it, having no shell to
settle it with; it was then measured on the deployed image, and the query is
worth keeping because the result is the opposite of what both this entry and
E0-10 assumed:

| | baseline | after `CREATE TEMP TABLE` shadowing the base table |
|---|---|---|
| `plpgsql` body | `from public` | **`from pg_temp`** |
| view | `from public` | `from public` |

`pg_depend` records the view against `public.<table>`: the oid is resolved at
`CREATE VIEW` and stored, so a view is early-bound like a constraint. The
practical consequence is not that qualification stops mattering — it is that
**a test which shadows a relation and asserts a view is unchanged cannot fail**,
which is entry 3's shape wearing this entry's clothes. Point that test at the
function.

*The general lesson, and the reason this is here rather than only in the ticket:
a rule that names a list of cases invites the list being extended by analogy. Two
of the three items here were measured; the third was added because it sounded
like the other two.*

---
