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

**A file is immutable once any database but your own can be at that revision —
in practice, once the branch is pushed for review.** After that, a change to a
view is a new file, `_v002.sql`, and a new revision that replaces the object.
This is
[ADR 0032](0032-a-prompt-file-is-immutable-once-a-classification-cites-it.md)'s
rule for prompts, adopted for the same reason and stated in the package
docstring: a revision that reads a file at upgrade time means the file is what
ran, so editing it in place silently changes what an already-applied revision
did. The version in the name is what makes the rule visible at the point somebody
would break it.

**A superseded file is history, and its prose is read that way.** This follows
from immutability and was left unwritten until E0-26 hit it, so it is stated here
rather than rediscovered. A `views_sql/` file is a record of what one revision
applied, exactly like the migration that names it — so once a `_v002.sql` replaces
it, the older file goes on describing a schema the database no longer has, and
**that is correct rather than stale**. `identity_roles_v001.sql` says the reveal
"runs with three grants"; it does now hold four, and the v001 sentence must not be
corrected, because it was true of the revision that ran it. The repair for a
reader who lands on the old file through a grep is a forward pointer, not an edit:
**the superseding file's header names what it supersedes and restates the fact
that moved**, so `identity_grants_v002.sql` says in its first paragraph that it
replaces v001's grant list and that the count is four. Nothing outside
`views_sql/` gets this exemption — an ADR, a README or a module docstring
describing the *current* schema is a live claim and is repaired
(`docs/MISTAKES.md` entry 1).

**The freeze covers the statements a revision executes, not the header prose
above them.** Stated here because E0-26 hit it and the rule as written did not
answer it. The property this record protects is that two databases at the same
revision must not hold different objects, and the header comment block above a
file's first `CREATE` is not part of any object: Postgres discards it at parse
time and `pg_proc` never sees it. So correcting a *false* statement in that block
is permitted after the push, and correcting one inside a `$$ … $$` body is not —
that text is the function's stored source, and editing it makes two databases at
the same revision differ, which is exactly what the rule forbids. The line is the
file's first executed statement, and it is a narrow permission rather than a
softening: it exists because a header comment beside a `SECURITY DEFINER` body
describing the *current* schema is a live claim by the test three paragraphs
above, and the alternative was shipping a migration whose only purpose is prose.
An accurate statement that has merely been *superseded* is still history and
still must not be edited; this permits repairing what was never true, not
updating what has stopped being true. PR #53 used it once, for a sentence that
told a maintainer the safety log errs only in the safe direction when review had
measured that it errs both ways.

**The boundary is the push and not the first `alembic upgrade head`**, and the
distinction is not a softening — it is where the property the rule protects
starts to matter. What must never be true is that two databases at the same
revision hold different objects. While the branch exists only on your machine,
the only database that has applied the revision is your own and you can rebuild
it; the moment it is pushed, a reviewer can pull it and run `alembic upgrade
head`, and from then on there is a database holding the old file that nobody else
can fix. **Merging is not the line — review is**, and the same recovery applies
to a reviewer who is caught by it: `alembic downgrade -1 && alembic upgrade head`,
or `docker compose down -v`.

So an unpushed revision is edited freely, exactly like the `op.create_table`
calls beside it, and the author owes their own database that downgrade-and-
upgrade when they change a file it has already run. E0-10 edited three of these
files after applying them locally, for a finding that arrived during review
(ADR 0043), and stating the rule as "once a revision executes it" would have
forbidden that while protecting nothing.

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
views exist in a migrated database, that each is named in a file here, that every
relation in every file is schema-qualified, and — since E0-34 — that no view
these files create reads an identity column. Any later change to these
objects needs a test run, not a drift check — the same consequence
[ADR 0027](0027-supervision-edges-are-policed-by-one-row-level-trigger.md)
records for its trigger, for the same reason.

**This record is no longer the only thing standing between a view file and an
identity column, and E0-34 is what changed that.** Until then, a `.sql` file in
this directory that joined `user_identity` and selected a name was caught by
review and by nothing else: the rule above puts it in a diff somebody reads, and
the `pg_depend` invariant in `test_identity_column_marker.py` cannot see it,
because it reads the migrated database and no revision has named the file yet.
`test_no_view_created_under_views_sql_names_an_identity_column` in
`test_identity_separated_views.py` now reads these files as text and fails on
that ground, naming the column, whether or not a revision executes the file — so
the immutable versioned name remains the reason the change is *legible* in a
diff, and is no longer the reason it is *caught*. The rule in this record is
unchanged; what has gone is its being alone.

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

**What the E0-34 guard does not cover, and what stands there instead.** The rule
it enforces is scoped to statements that *create a view*, not to files, because
this directory also ships the `SECURITY DEFINER` reveal function, which reads
identity by [ADR 0001](0001-identity-separation-by-database-role.md)'s design — a
file-grained rule would be red on landing, and an exemption list keyed on a
filename is worse than a property. The consequence is that **a second
identity-reading function shipped into this directory has nothing behind it but
the grant model**, and `identity_grants_v001.sql` says in as many words that the
grant model does not protect the view files themselves. What stands there is this
record's review rule, plus `test_identity_grants.py`'s sweep asserting that
`pulse_app` may execute no `SECURITY DEFINER` function in `public`, which fires
on the day such a file joins a `SCRIPTS` tuple. `CREATE TABLE … AS SELECT` in one
of these files is outside the guard for the same reason and has its own followup.

**The name-mention sweep was weaker than it read, and E0-33 closed it.**
`test_every_read_view_is_created_from_a_sql_file_under_views_sql` looks for the
view's *name* anywhere in the combined text of these files, so a view whose
`CREATE VIEW` moved into a revision string still passes as long as some file
mentions it — and `identity_grants_v001.sql` mentions both views, because it
grants on them. Measured, not reasoned: with `section_roster_v001.sql` deleted
and its `CREATE VIEW` inlined into the revision, all seven tests in that module
stayed green. So the file-based layout was a decision this record held rather than
one the suite enforced. **E0-33 tightened it**: `creates_view` now requires a
`CREATE` of the object, and E0-34 widened that to every spelling Postgres
accepts, including `RECURSIVE` and `TEMP`. The paragraph below described the
older, weaker state and is kept for the measurement it records; tightening the
sweep to require a `CREATE` of the object was
noted for whoever owns that test.
