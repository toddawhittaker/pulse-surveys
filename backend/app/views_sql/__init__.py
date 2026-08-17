"""Identity-separated read views, as SQL an Alembic migration executes (SPEC §8, §13).

§13 puts the read views here — "`views_sql/` — identity-separated read views (§8)
as migrations + query helpers" — and says why in the paragraph under the tree:
"shipped as migrations, not just ORM conventions, so the confidentiality
guarantee holds at the database level even against a future careless query".

**Every `.sql` file here is executed by a revision, and never edited afterwards.**
The file name carries a version — `section_roster_v001.sql` — and a change to a
view ships as `_v002.sql` plus a revision that replaces the object. That rule is
[ADR 0041](../../../docs/adr/0041-a-read-view-ships-as-an-immutable-versioned-sql-file.md),
and it follows [ADR 0032](../../../docs/adr/0032-a-prompt-file-is-immutable-once-a-classification-cites-it.md),
which made a prompt immutable once a classification cites it, for the same
reason: a migration that reads a file at upgrade time means the file is what ran,
so editing it in place silently changes what an already-applied revision did.

**Why the SQL is a file rather than a string in the revision.** Postgres does not
keep the text a `CREATE VIEW` was written with. It stores a parse tree of oids,
and `pg_get_viewdef` regenerates names against the asking session's
`search_path` — so the same view prints `public.enrollment` or `enrollment`
depending on who asks. The schema-qualification rule these files follow is
therefore only checkable where the author's own text survives, which is here.
`tests/integration/test_identity_separated_views.py` sweeps these files for it,
and asserts that every view in the database is named in one of them, so a view
whose SQL exists only inside a revision fails rather than escaping the sweep.

**Two rules every file here follows** (ADR 0027, measured there):

* every relation is schema-qualified — `public.enrollment`, never `enrollment`;
* every function sets `search_path = pg_catalog, public, pg_temp`, with
  `pg_temp` named and named **last**. Omitting it is the usual advice and is the
  variant that does not work: Postgres searches the temporary schema first for
  relation names, and leaving it out of the path is what puts it first.

For a view the first rule is hygiene rather than a guard — a view binds its
relations at `CREATE VIEW` — and for the `SECURITY DEFINER` reveal function it is
the guard itself, because that body is parsed on every call and runs with its
owner's privileges.
"""

from importlib.resources import files

__all__ = ["read_sql"]


def read_sql(name: str) -> str:
    """The text of one `.sql` file in this package.

    Read through `importlib.resources` rather than by building a path from
    `__file__`, so the lookup goes through the same mechanism that decides
    whether the file is in the installed distribution at all. `pyproject.toml`
    ships `views_sql/**/*` as package data for that reason —
    `docs/MISTAKES.md` entry 18 is a directory that existed in the source tree
    and in no built artifact.
    """
    return (files(__package__ or "app.views_sql") / f"{name}.sql").read_text(encoding="utf-8")
