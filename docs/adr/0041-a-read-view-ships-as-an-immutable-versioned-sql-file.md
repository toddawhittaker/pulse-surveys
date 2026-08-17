# 0041 — A read view ships as an immutable, versioned `.sql` file that a migration executes

**Status:** Accepted
**Date:** 2026-08-16
**Tickets:** E0-10

## Context

[SPEC §13](../SPEC.md) puts the identity-separated read views in
`backend/app/views_sql/` "as migrations + query helpers", and the paragraph under
the tree says why: "shipped as migrations, not just ORM conventions, so the
confidentiality guarantee holds at the database level even against a future
careless query". E0-10 repeats the directory and the requirement.

What neither settles is the mechanical question a first implementation has to
answer: the DDL has to reach Postgres through an Alembic revision, and a revision
is a Python module, so the SQL can live *in* the revision as a string or *beside*
it as a file the revision reads. Every other revision in this tree writes its DDL
out verbatim, and E0-05's says why in a sentence the later ones repeat: "a
migration records what was applied on the day it ran, and importing an
application class would make this revision change meaning whenever that class
did."

Two facts about Postgres decide against following that rule here.

**A view does not remember its own text.** `CREATE VIEW` is parsed once and
stored as a rewrite rule holding oids. `pg_get_viewdef` regenerates SQL from that
tree and qualifies a name only when the asking session's `search_path` does not
already make it visible — so the same view prints `public.enrollment` to one
session and `enrollment` to another. There is therefore no way to ask the
database what a view's author wrote, and the schema-qualification rule
[ADR 0027](0027-supervision-edges-are-policed-by-one-row-level-trigger.md)
established can only be checked where the author's text survives.

**A revision file is not swept.** If that text is a string literal inside
`backend/migrations/versions/`, a test would have to find and parse Python to
read it, and the natural sweep — every `.sql` under one directory — finds
nothing. E0-10's test module names this as the mutation it is built against:
"move the `CREATE VIEW` into `op.execute("...")` in a revision file and the sweep
below has nothing to read while staying green."

## Decision

**The SQL lives in `backend/app/views_sql/<object>_v<NNN>.sql`, and the revision
executes it by name.** Five files ship with E0-10 — the roles, two views, the
`SECURITY DEFINER` reveal function, and the grants — and the revision names them
in the order it runs them.

**A file is immutable once a revision executes it.** A change to a view is a new
file, `_v002.sql`, and a new revision that replaces the object. This is
[ADR 0032](0032-a-prompt-file-is-immutable-once-a-classification-cites-it.md)'s
rule for prompts, adopted for the same reason and stated in the package
docstring: a revision that reads a file at upgrade time means the file is what
ran, so editing it in place silently changes what an already-applied revision
did. The version in the name is what makes the rule visible at the point somebody
would break it.

**The order is written out, not globbed.** Roles before grants, objects before
the grants that name them; a directory listing is not a dependency order, and a
file added to the directory does nothing until a revision names it.

**`pyproject.toml` ships the directory as package data.** A wheel without it
installs an application whose migrations fail on a missing file, in a container,
at deploy time, having passed every gate on a machine where the source tree was
still there to read from — which is `docs/MISTAKES.md` entry 18 exactly, and the
glob is the wide one entry 18 argues for rather than a name-shaped one.

## Alternatives rejected

**SQL as a string inside the revision**, like every other revision here. It is
the consistent choice and it is what the objection above is really about: it
would leave this project unable to assert its own schema-qualification rule over
views at all, since the database cannot answer for the text and nothing else
holds it. The consistency argument is also weaker than it looks — the other
revisions write out `CREATE TABLE`, which `alembic check` compares against the
model on every run, so their text has a second reader. A view has none.

**A `.sql` file read at upgrade time with no immutability rule.** The cheap
version, and the one that quietly breaks the property `alembic` exists to give:
two databases at the same revision would hold different views, depending on when
each ran. The versioned name costs one suffix and makes the edit that would do
that visible in a diff.

**`alembic_utils` or a similar library that reflects views and generates
revisions for them.** Genuinely solves the drift problem this record leaves open,
and rejected on the standing rule against adding an abstraction over the two
things that cost time here (`CLAUDE.md`), plus a dependency and a second
autogenerate mechanism to understand. Worth revisiting if the number of views
grows past a handful and drift becomes a real incident rather than a described
one.

**A view declared as a `Table` on `Base.metadata`.** Rejected by E0-10's
criterion in as many words — "not as ORM constructs" — and for the failure it
causes rather than the rule: `alembic check` compares metadata against the
database, so a view on the metadata either churns a `create_table` forever or
agrees for the wrong reason, and every ORM write path then believes it can insert
into a relation that cannot take one.

## Consequences

**Nothing compares a view against anything.** `alembic check` reads neither
`pg_class` for views nor `pg_proc`, so dropping a view, changing one by hand in a
database, or deleting the `CREATE FUNCTION` from a file leaves the check green.
The tests are the only reader: `test_identity_separated_views.py` asserts the
views exist in a migrated database, that each is named in a file here, and that
every relation in every file is schema-qualified. Any later change to these
objects needs a test run, not a drift check — the same consequence
[ADR 0027](0027-supervision-edges-are-policed-by-one-row-level-trigger.md)
records for its trigger, for the same reason.

**A revision imports application code, which no other revision here does.** That
is the exception this record buys, and it has a cost: `backend/migrations/env.py`
already imports `app.models`, so the package is importable during a migration,
but a future reorganisation of `app/` can now break a migration that has already
run everywhere. `read_sql` is deliberately the smallest possible surface — one
function, no models, no `Settings` — so what a revision depends on is a directory
of text files and one path lookup.

**The immutability rule is a convention, and only half of it is enforced.** The
test suite asserts that every view in the database is named in some file here; it
does not assert that a file cited by an applied revision has not changed. A
content hash recorded in the revision would close it, and was left out as more
machinery than the risk carries today — the same trade ADR 0032 made for prompts,
where the file-naming scheme is enforced and the no-edit rule is not.

**The name-mention sweep is weaker than it reads.**
`test_every_read_view_is_created_from_a_sql_file_under_views_sql` looks for the
view's *name* anywhere in the combined text of these files, so a view whose
`CREATE VIEW` moved into a revision string still passes as long as some file
mentions it — and `identity_grants_v001.sql` mentions both views, because it
grants on them. Measured, not reasoned: with `section_roster_v001.sql` deleted
and its `CREATE VIEW` inlined into the revision, all seven tests in that module
stayed green. So the file-based layout is a decision this record holds, not one
the suite enforces; tightening the sweep to require a `CREATE` of the object is
noted for whoever owns that test.
