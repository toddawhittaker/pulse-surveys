"""The read views, where they come from, and the SQL that binds late — ticket E0-10.

Two of E0-10's acceptance criteria live here:

  - "Views ship as Alembic migrations under `views_sql/`, not as ORM constructs;
    `alembic upgrade head` creates them";
  - "Every relation named in a view or function is schema-qualified, and every
    such function sets a `search_path` naming `pg_temp` last. Qualification is
    asserted over the `views_sql/` source files and over `pg_proc.prosrc`, **not**
    over `pg_get_viewdef`".

The grants, the roles and the Care door are next door in
`test_identity_grants.py`; the identity-column enumeration and the sweep for a
view that reads a marked column are in `test_identity_column_marker.py`, beside
the marker convention they are built on, so that widening the convention widens
both (`docs/MISTAKES.md` entry 13).

**Nothing here names a view.** E0-10's scope asks for "a section-roster view and
an enrollment-count view" and spells neither, so every view in `public` is
discovered out of the catalog and the rules below are asserted over all of them.
A test that named one would make the implementer build to this file.

**Why the catalog cannot answer for a view, which is why two of these tests read
files.** Postgres parses a view's query at `CREATE VIEW` and stores a rewrite
rule holding **oids**, not names. Two consequences, both settled by measurement
in the ticket rather than argued here:

  - `pg_get_viewdef` does not report what the migration wrote. It regenerates SQL
    from that parse tree and qualifies a name only when the asking session's
    `search_path` does not already make it visible — so the same view prints
    `public.enrollment` or `enrollment` depending on who asks, and an assertion
    taken from there would measure the deparser. It is green against every input,
    which is `docs/MISTAKES.md` entry 3 in a new place. So the qualification rule
    is asserted over the `.sql` files under `backend/app/views_sql/`, where the
    author's text survives, and over `pg_proc.prosrc`, which retains it too.
  - **A view is early-bound, so no shadowed-relation test belongs in this file.**
    The ticket carries the measurement: shadowing a base table redirects a
    `plpgsql` body and leaves a view reading `public`. A test that stands up a
    shadow and asserts a view is unchanged therefore cannot fail — it is the
    shape this ticket exists to stop shipping. The late-bound SQL E0-10 adds is
    the `SECURITY DEFINER` reveal function, and that test lives in
    `test_identity_grants.py` beside the machinery that calls it:
    `test_a_shadowed_table_does_not_change_what_the_reveal_function_returns`.

For views the two rules below are hygiene rather than a guard, and the ticket
says so in as many words. They are still asserted, because the file is the model
the next view is copied from and because a later function that reads a view
inherits that view's text into its own plan.
"""

import re
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]

# SPEC §13 and E0-10's scope both spell this directory: "`backend/app/views_sql/`
# with the first identity-separated views shipped as Alembic migrations". It is
# the one path in this module that is named rather than discovered, because the
# ticket names it.
VIEWS_SQL_DIR = REPO_ROOT / "backend" / "app" / "views_sql"

# Every view in the application schema. `m` is included so that a materialised
# view — a reasonable answer for an enrollment count — is held to the same rules
# rather than quietly exempt.
READ_VIEWS = """
    SELECT c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('v', 'm')
    ORDER BY c.relname
"""

# Every relation name the sweeps below look for. Read out of the catalog so that
# a table added by a later ticket is swept without this file being edited.
PUBLIC_RELATION_NAMES = """
    SELECT c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm')
"""

# Every function this project defines in `public`, with the source text and the
# `SET` clauses attached to it. Extension-owned functions are excluded — they are
# somebody else's code and this ticket's rule is about ours. `prokind` keeps
# aggregates and window functions out, which carry no body to sweep.
SCHEMA_FUNCTIONS = """
    SELECT p.oid::regprocedure::text, p.prosrc, p.proconfig, p.prosecdef
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public'
      AND p.prokind IN ('f', 'p')
      AND NOT EXISTS (
          SELECT 1 FROM pg_depend d
          WHERE d.objid = p.oid
            AND d.classid = 'pg_proc'::regclass
            AND d.deptype = 'e'
      )
    ORDER BY 1
"""

# A relation name that exists nowhere, used to check the sweep before it is
# believed. A pattern searched against text is a test that can go blind and
# report success (`docs/MISTAKES.md` entry 3), and the samples below are the
# cheapest way to notice — one of each shape the sweep must catch, and one of
# each it must allow. `test_the_text_sweeps_in_this_file_catch_what_they_claim_to`
# runs them.
CANARY = "canary_relation"

# Every sample below is a *subject* for the regex sweep, never a query. Nothing
# in this module executes one, and `CANARY` names a relation that exists in no
# database. Ruff reads them as SQL built by interpolation, which is what S608 is
# for; the suppression is per line rather than per file so that a sample which
# ever does reach a cursor is flagged again.
SWEEP_MUST_CATCH = (
    f"SELECT 1 FROM {CANARY} WHERE id = NEW.id",  # noqa: S608
    f'SELECT 1 FROM "{CANARY}"',  # noqa: S608
    f"SELECT 1 FROM enrollment JOIN {CANARY} ON true",  # noqa: S608
    f"PERFORM pg_advisory_xact_lock('{CANARY}'::regclass::oid::bigint)",
    f"UPDATE {CANARY} SET note = 'x'",  # noqa: S608
)

SWEEP_MUST_ALLOW = (
    f"SELECT 1 FROM public.{CANARY} WHERE id = NEW.id",  # noqa: S608
    f'SELECT 1 FROM public."{CANARY}"',  # noqa: S608
    f'SELECT 1 FROM "public".{CANARY}',  # noqa: S608
    f"PERFORM pg_advisory_xact_lock('public.{CANARY}'::regclass::oid::bigint)",
    f"-- walks upward from {CANARY}, one row per {CANARY}",
    f"RAISE EXCEPTION '{CANARY} % would report to itself', NEW.id",
    f"SELECT 1 FROM {CANARY}s",  # noqa: S608
)

# The same treatment for the other text sweep in this file, `creates_view`, and
# here the must-allow samples are the ones that carry the weight: each is a way a
# real `views_sql/` file names a view it does not define, and the first version of
# that sweep — a search for the bare name — accepted every one of them as evidence
# that the view was defined there. Subjects, never queries, as above.
CANARY_VIEW = "canary_view"

VIEW_CREATE_MUST_CATCH = (
    f"CREATE VIEW public.{CANARY_VIEW} AS SELECT 1",
    f"create or replace view {CANARY_VIEW} as select 1",
    f'CREATE MATERIALIZED VIEW IF NOT EXISTS public."{CANARY_VIEW}" AS SELECT 1',
    f"CREATE OR REPLACE VIEW\n    public.{CANARY_VIEW} AS\nSELECT 1",
)

VIEW_CREATE_MUST_ALLOW = (
    f"GRANT SELECT ON public.{CANARY_VIEW} TO pulse_app",
    f"REVOKE ALL ON public.{CANARY_VIEW} FROM PUBLIC",
    f"DROP VIEW IF EXISTS public.{CANARY_VIEW}",
    f"COMMENT ON VIEW public.{CANARY_VIEW} IS 'section membership, no identity'",
    f"-- {CANARY_VIEW} is the section roster; the migration that creates it is next door",
    f"CREATE VIEW public.{CANARY_VIEW}_totals AS SELECT 1",
)


def read_views(connection: Any) -> list[str]:
    """Every view and materialised view in `public`, by name."""
    return [row[0] for row in connection.execute(text(READ_VIEWS))]


def creates_view(sql: str, view: str) -> bool:
    """Does `sql` contain a statement that *creates* the view called `view`?

    A mention is not a creation, and the difference is the whole of what this
    helper exists for. The first version of the test that uses it searched for the
    view's name anywhere under `views_sql/`, and the mutation the test's own
    docstring named — delete `section_roster_v001.sql` and inline its
    `CREATE VIEW` into the revision — kept it green, because the grants file names
    every view in order to `GRANT SELECT` on it. So `GRANT`, `DROP`, `COMMENT ON`
    and a name in a comment all have to fail here, and each is a sample in
    `VIEW_CREATE_MUST_ALLOW` below.
    """
    pattern = re.compile(
        r"\bcreate\s+(?:or\s+replace\s+)?(?:materialized\s+)?view\s+"
        r"(?:if\s+not\s+exists\s+)?"
        r'(?:"?\w+"?\s*\.\s*)?'
        rf'(?:"{re.escape(view)}"|{re.escape(view)}\b)',
        re.IGNORECASE,
    )
    return pattern.search(without_comments(sql)) is not None


def public_relation_names(connection: Any) -> list[str]:
    """Every relation name in `public`, longest first.

    Longest first so that a sweep for `user` cannot claim the `user_identity` in
    a line the sweep for `user_identity` has already accounted for.
    """
    names = [row[0] for row in connection.execute(text(PUBLIC_RELATION_NAMES))]
    return sorted(set(names), key=lambda name: (-len(name), name))


def without_comments(body: str) -> str:
    """`body` with its SQL comments removed, so the sweep reads code and not prose.

    Copied in behaviour from `test_trigger_resists_a_shadowed_table.py`, which
    needed it for the same reason: this project's migrations are heavily
    commented, and "-- one row per enrollment" is the sentence a careful author
    writes directly above the query. A `--` inside a string literal is stripped
    too, which can only hide a reference rather than invent one — the safe
    direction for a tripwire whose other failure mode is flagging correct SQL.
    """
    return re.sub(r"--[^\n]*", " ", re.sub(r"/\*.*?\*/", " ", body, flags=re.DOTALL))


def relation_patterns(name: str) -> tuple[re.Pattern[str], ...]:
    """Where `name` is a relation *lookup*, in the two forms a review has found here.

    A table named after a SQL clause, and a name cast to `regclass` — the shape
    E0-09's advisory-lock key used, and the one that moved with the shadow. Both
    allow an optional schema and optional double quotes, and the caller requires
    that schema to be `public`.

    The clause form is anchored on the keyword rather than on the bare word so
    that a table name inside an error message cannot match; the literal form
    requires the closing quote immediately after the name, for the same reason.
    """
    quoted = re.escape(name)
    body = rf'(?:"{quoted}"|{quoted}\b)'
    schema = r'(?:(?P<schema>"?\w+"?)\s*\.\s*)?'
    return (
        re.compile(
            rf"\b(?:from|join|into|update|delete\s+from)\s+(?:only\s+)?{schema}{body}",
            re.IGNORECASE,
        ),
        re.compile(rf"'{schema}{body}'", re.IGNORECASE),
    )


def unqualified_references(sql: str, names: list[str]) -> list[str]:
    """Every place `sql` names one of `names` as a relation without `public.`.

    **What this looks for, so nobody reads it as more than it is**
    (`docs/MISTAKES.md` entry 14): a relation named after `FROM`, `JOIN`, `INTO`,
    `UPDATE` or `DELETE FROM`, and a name alone inside a string literal. It does
    not parse SQL, and a reference in some third form is not caught. It is a
    tripwire on the two shapes a security review actually found in this
    repository, checked against a sample of each before it is believed.
    """
    code = without_comments(sql)
    found: list[str] = []
    for name in names:
        for pattern in relation_patterns(name):
            for match in pattern.finditer(code):
                if (match.group("schema") or "").strip('"').lower() != "public":
                    found.append(match.group(0).strip())
    return found


def schema_functions(connection: Any) -> list[tuple[str, str, list[str], bool]]:
    """Every function this project defines in `public`: signature, body, settings, definer."""
    return [
        (signature, body or "", list(settings or []), bool(definer))
        for signature, body, settings, definer in connection.execute(text(SCHEMA_FUNCTIONS))
    ]


def view_sql_files() -> list[Path]:
    """Every `.sql` file shipped under `backend/app/views_sql/`, at any depth."""
    return sorted(VIEWS_SQL_DIR.rglob("*.sql")) if VIEWS_SQL_DIR.is_dir() else []


def test_alembic_upgrade_head_creates_the_identity_separated_read_views(
    migrated_engine: Any,
) -> None:
    """The views exist in a database `alembic upgrade head` built, and nothing else built them.

    `migrated_engine` is a connection to the database the session fixture
    migrated, so "the views are there" is the same sentence as "the migration
    created them" — which is the half of the criterion that rules out an ORM
    construct or a helper the application calls at start-up. A view declared in
    Python and created by application code is absent here.

    **Two, because the scope names two**: "a section-roster view and an
    enrollment-count view that expose section membership and counts with no
    identity columns reachable". This asserts the count and not which is which —
    it cannot tell a roster view from a count view, and does not try to. If one
    view is genuinely meant to serve both purposes, that is a question for the
    ticket rather than a number to soften here.
    """
    with migrated_engine.connect() as connection:
        views = read_views(connection)

    assert len(views) >= 2, (
        f"The migrated database holds {views} in `public`. E0-10 ships "
        "`backend/app/views_sql/` with 'a section-roster view and an enrollment-count view that "
        "expose section membership and counts with no identity columns reachable', as Alembic "
        "migrations rather than ORM constructs (SPEC §13: they ship as migrations 'so the "
        "confidentiality guarantee holds at the database level even against a future careless "
        "query'). Every other test in this module and the structural sweep in "
        "`test_identity_column_marker.py` are asserted over this set, so an empty one makes them "
        "vacuous rather than passing."
    )


def test_every_read_view_is_created_from_a_sql_file_under_views_sql(
    migrated_engine: Any,
) -> None:
    """The view's SQL lives in `views_sql/`, which is what the qualification sweep reads.

    Two things rest on this. SPEC §13 puts the read views in
    `backend/app/views_sql/` "as migrations + query helpers", and E0-10's
    criterion repeats it; and — the reason it is asserted rather than assumed —
    the catalog cannot report the text a migration wrote, so a view whose SQL
    exists only as a string inside a migration module is a view whose
    schema-qualification nothing in this suite can see. The mutation this is
    built for is exactly that: move the `CREATE VIEW` into
    `op.execute("...")` in a revision file and the sweep below has nothing to
    read while staying green.

    The search is by name and the canary is the word `select`: a directory of
    view SQL certainly contains it, so a search that has gone blind against these
    files says so here rather than passing (`docs/MISTAKES.md` entry 3).
    """
    with migrated_engine.connect() as connection:
        views = read_views(connection)

    assert views, (
        "The migrated database holds no view in `public`, so this test would report success "
        "having checked nothing. `test_alembic_upgrade_head_creates_the_identity_separated_read_"
        "views` is where that is diagnosed."
    )
    assert VIEWS_SQL_DIR.is_dir(), (
        f"{VIEWS_SQL_DIR} does not exist. SPEC §13 puts the identity-separated read views there — "
        "'`views_sql/` — identity-separated read views (§8) as migrations + query helpers' — and "
        f"the database already holds {views}, so the SQL for them is somewhere this file cannot "
        "sweep for the schema-qualification rule."
    )

    files = view_sql_files()
    assert files, f"{VIEWS_SQL_DIR} holds no `.sql` file, so there is no view SQL to check."

    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert re.search(r"(?i)\bcreate\b", combined), (
        f"None of the {len(files)} file(s) under {VIEWS_SQL_DIR} contains the word `create`. "
        "That is the canary for this test's own search: if it cannot find a word certain to be in "
        "a file that defines a view, the search below proves nothing."
    )

    missing = [view for view in views if not creates_view(combined, view)]
    assert not missing, (
        f"{missing} exist as views in the migrated database and no file under {VIEWS_SQL_DIR} "
        f"contains a `CREATE VIEW` for them (it holds {[path.name for path in files]}). SPEC §13 "
        "ships the read views as SQL there rather than as ORM convention, and this suite's "
        "qualification rule is asserted over those files because Postgres does not keep the text a "
        "`CREATE VIEW` was written with — it keeps a parse tree of oids, and `pg_get_viewdef` "
        "regenerates names against whatever `search_path` asks. A view defined inline in a "
        "migration is therefore a view whose `public.` prefixes nothing checks.\n\n"
        "**This requires the `CREATE`, not a mention**, and that is a repair rather than a "
        "preference: the first version searched for the view's *name* anywhere under `views_sql/`, "
        "and the mutation this test's own docstring named — delete the view's file, inline the "
        "`CREATE VIEW` into the revision — left it green, because the grants file names every view "
        "in order to grant on it. `docs/MISTAKES.md` entry 3's sixth incident."
    )


def test_no_read_view_is_also_declared_as_an_orm_table(
    migrated_engine: Any, metadata_tables: dict[str, Any]
) -> None:
    """ "Not as ORM constructs" — the view is not a `Table` on `Base.metadata`.

    A view declared as a `Table` is the shape the criterion excludes, and it
    fails in a way that does not point at itself: `alembic check` compares
    `Base.metadata` against the database, sees a relation it thinks is a table,
    and either churns a `create_table` forever or is quietly satisfied — while
    every ORM write path now believes it can insert into a view.
    """
    with migrated_engine.connect() as connection:
        views = read_views(connection)

    assert views, (
        "No view exists in `public`, so this test compares an empty set against the model and "
        "reports success having checked nothing."
    )
    assert metadata_tables, (
        "`Base.metadata` carries no tables at all, which makes the intersection below empty for a "
        "reason that has nothing to do with views."
    )

    declared = sorted(set(views) & set(metadata_tables))
    assert not declared, (
        f"{declared} exist as views in the database and as tables on `Base.metadata`. E0-10: "
        "views ship 'as Alembic migrations under `views_sql/`, not as ORM constructs'. A view on "
        "the metadata is what `alembic check` compares against the database, so it either churns "
        "or agrees for the wrong reason — and it invites an ORM write path into a relation that "
        "cannot take one. A read helper returning rows from a `text()` query or a `Table` object "
        "built on a throwaway `MetaData` is not this; being on `Base.metadata` is."
    )


# The shadowed-relation test that used to sit here has moved and changed its
# subject. It stood a `pg_temp` copy of a view's base table up and asserted the
# view was unchanged — and the ticket has since measured that a view is
# early-bound, so that test passes against unqualified SQL and cannot fail. It is
# now `test_a_shadowed_table_does_not_change_what_the_reveal_function_returns` in
# `test_identity_grants.py`, pointed at the `SECURITY DEFINER` function, which is
# the SQL in this ticket that really does resolve names on every call. It lives
# there rather than here because that is where the machinery for calling the
# reveal is, and a second copy of it would be `docs/MISTAKES.md` entry 13.


def test_the_text_sweeps_in_this_file_catch_what_they_claim_to() -> None:
    """Both sweeps are run against a sample of each shape before anything trusts them.

    A pattern searched against text is a test that can go blind and report
    success — `docs/MISTAKES.md` entry 3 records one that matched nothing because
    a comment wrapped at 80 columns, and went green against the exact text it
    existed to catch. So each sweep is run over the shapes it must catch *and* the
    shapes it must allow, in a test of its own rather than as a guard inside the
    tests that consume them, because several do and one blind sweep should not be
    reported four times under four names.

    Two samples look unnecessary and are the point of the exercise. The
    `s`-suffixed relation: `canary_relations` is a *different* table, and a sweep
    whose word boundary is wrong reports the correct spelling of one as an
    unqualified reference to the other. And `GRANT SELECT ON public.canary_view`:
    the first version of `creates_view` searched for the view's bare name, which
    that line satisfies — so deleting a view's `.sql` file and inlining its
    `CREATE VIEW` into the revision left the test green, because the grants file
    names every view in order to grant on it. That mutation was named in the
    test's own docstring and not run; entry 3's sixth incident is that a mutation
    a test names is a claim until someone runs it.
    """
    names = [CANARY]

    for sample in SWEEP_MUST_CATCH:
        assert unqualified_references(sample, names), (
            f"The relation sweep does not flag {sample!r}, which is a shape it exists to catch. It "
            "has gone blind, and every assertion built on it would pass against SQL that names "
            "its relations unqualified everywhere."
        )

    for sample in SWEEP_MUST_ALLOW:
        assert not unqualified_references(sample, names), (
            f"The relation sweep flags {sample!r}, which is either the fixed form, a comment, or a "
            "different relation. It would report correct SQL as vulnerable — and the casualty of "
            "that is usually the comment, deleted by the next person to meet a red test they "
            "cannot otherwise explain."
        )

    for sample in VIEW_CREATE_MUST_CATCH:
        assert creates_view(sample, CANARY_VIEW), (
            f"`creates_view` does not recognise {sample!r} as creating `{CANARY_VIEW}`, which is a "
            "shape it exists to catch. Every view in `views_sql/` would then look undefined, and "
            "`test_every_read_view_is_created_from_a_sql_file_under_views_sql` would be red for a "
            "reason that has nothing to do with where the views live."
        )

    for sample in VIEW_CREATE_MUST_ALLOW:
        assert not creates_view(sample, CANARY_VIEW), (
            f"`creates_view` reads {sample!r} as creating `{CANARY_VIEW}`. It names the view "
            "without defining it — a grant, a revoke, a drop, a comment, or a different view whose "
            "name begins the same way — and accepting one is exactly the defect this sweep was "
            "repaired for: with a `GRANT` counted as a definition, a view can be moved out of "
            "`views_sql/` entirely with the suite green."
        )


def test_every_relation_a_view_sql_file_names_is_schema_qualified(migrated_engine: Any) -> None:
    """`public.enrollment`, never `enrollment` — asserted where the text survives.

    The criterion asks for this over "the `views_sql/` source files… **not** over
    `pg_get_viewdef`, which regenerates names against the asking session's
    `search_path` and so measures the deparser rather than the stored
    definition". The files are where the author's own text survives, and
    `test_every_read_view_is_created_from_a_sql_file_under_views_sql` is what
    keeps them the whole story rather than one copy of it.

    **This is hygiene, and the ticket says so** — a view is early-bound, so an
    unqualified name in one is not a hijack the way it is in a function. It is
    asserted anyway for two reasons the ticket gives: a later function that reads
    a view inherits that view's text into its own plan, and this file is the
    model the next view is copied from. The mutation it survives is dropping the
    `public.` prefixes and leaving the `SET search_path` to carry it, which is the
    row in ADR 0027's table that is not exploitable and leaves one control where
    the record says there are two.
    """
    files = view_sql_files()
    assert files, (
        f"There is no `.sql` file under {VIEWS_SQL_DIR}, so this sweep read nothing and would "
        "report success. `test_every_read_view_is_created_from_a_sql_file_under_views_sql` is "
        "where that is diagnosed."
    )

    with migrated_engine.connect() as connection:
        names = public_relation_names(connection)
    assert names, (
        "The migrated database reports no relation in `public`, so this sweep has no name to look "
        "for and would pass over any SQL at all."
    )

    offenders: dict[str, list[str]] = {}
    for path in files:
        found = unqualified_references(path.read_text(encoding="utf-8"), names)
        if found:
            offenders[path.name] = found

    assert not offenders, (
        f"These view files name a relation without a schema: {offenders}. Postgres searches the "
        "temporary schema first for relation names — being unlisted in `search_path` is what puts "
        "it first, not what skips it — so an unqualified name is a table the *reader* can choose. "
        "A view is bound at `CREATE VIEW` time and so is not itself exploitable through this "
        "today; the rule holds anyway because ADR 0027 ships both halves deliberately, and "
        "because the same file is the model the next view is copied from. E0-10: 'Schema-qualify "
        "every relation a view or function names — `public.user`, not `user`.'"
    )


def test_every_function_this_schema_defines_names_pg_temp_last_in_its_search_path(
    db_session: Any,
) -> None:
    """The half of the rule the behavioural tests cannot see, and the variant that fails.

    ADR 0027 measured all four combinations against E0-09's trigger. Two of them
    decide this test: with the relations unqualified,
    `SET search_path = pg_catalog, public, pg_temp` refuses the hijacked write and
    `SET search_path = pg_catalog, public` **stores** it. So "the function sets a
    `search_path`" is not the property, and the conventional advice is precisely
    the version that does not work — omitting `pg_temp` does not skip the
    temporary schema, it leaves it first.

    **The mutation this test exists to survive is therefore
    `SET search_path = pg_catalog, public`**, which is the design E0-10's own text
    rejects. A test that cannot tell that version from the correct one is not
    testing the rule.

    Requiring `pg_temp` **last** is stricter than the mechanism strictly needs —
    after every schema that could be shadowed is enough, and today `public` is
    the only one — and it costs nothing, since nothing wants to sit after it.

    This sweeps every function the project defines rather than a named one,
    because E0-10 adds the `SECURITY DEFINER` reveal and names neither it nor its
    module, and because the rule is about the class rather than the instance.
    """
    functions = schema_functions(db_session)
    assert functions, (
        "This project defines no function in `public`, so this test swept nothing and would "
        "report success. E0-10 ships one `SECURITY DEFINER` function returning identity and "
        "writing its audit row, and E0-09's supervision trigger already has a function here."
    )
    assert any(definer for _, _, _, definer in functions), (
        f"None of {[signature for signature, _, _, _ in functions]} is `SECURITY DEFINER`. E0-10: "
        "'`pulse_care` gets `EXECUTE` on a single `SECURITY DEFINER` function that returns "
        "identity and writes the audit row in the same transaction'. It is deliberately the one "
        "hole in the wall, and it is the function this rule matters most for — its whole point is "
        "to run with privileges its caller does not have."
    )

    for signature, _, settings, _ in functions:
        configured = dict(entry.partition("=")[::2] for entry in settings)
        search_path = configured.get("search_path")
        assert search_path is not None, (
            f"`{signature}` carries no `SET search_path`; its settings are {settings}. A "
            "`SECURITY DEFINER` function without one runs somebody else's `search_path` with the "
            "definer's privileges, which is the textbook escalation; and for any function it is "
            "the half of ADR 0027's fix that survives somebody later adding an unqualified table "
            "reference. If it is being dropped deliberately, that is an ADR amendment rather than "
            "a test edit."
        )
        schemas = [name.strip().strip('"') for name in search_path.split(",")]
        assert schemas[-1] == "pg_temp", (
            f"`{signature}` sets `search_path = {search_path}`, whose last entry is "
            f"{schemas[-1]!r}. `pg_temp` has to be named, and named last. Leaving it out is the "
            "usual advice and is the variant ADR 0027 measured as **vulnerable**: Postgres "
            "searches the temporary schema first for relation names, and omitting it from the "
            "path is what puts it first rather than what skips it. Naming it anywhere but last "
            "has the same effect on every schema listed after it."
        )


def test_every_relation_a_function_body_names_is_schema_qualified(db_session: Any) -> None:
    """The same rule for the SQL that really does bind late.

    A function body is parsed on every call, which is what made E0-09's trigger
    aimable at a table the writer created. E0-10 adds a `SECURITY DEFINER`
    function that reads identity, so the same defect there is not a bypassed
    guard but a caller choosing which table the definer's privileges are spent
    on.

    `test_every_relation_the_trigger_function_names_is_schema_qualified` in
    `test_trigger_resists_a_shadowed_table.py` asserts this for E0-09's trigger
    and for `role_assignment` alone. This is the general rule over every function
    and every relation name in the schema, which is what E0-10's criterion asks
    for; the overlap is deliberate, and the older test is the one that names the
    incident.

    **The mutation it exists to survive**: removing the `public.` prefixes while
    leaving the `SET search_path` in place. ADR 0027's table has a row for that
    state — it is not exploitable, and it is one control where the record says
    there are two, and no behavioural test in this repository goes red for it.
    """
    functions = schema_functions(db_session)
    assert functions, (
        "This project defines no function in `public`, so this sweep read nothing and would "
        "report success."
    )

    names = public_relation_names(db_session)
    assert names, "The database reports no relation in `public` for this sweep to look for."

    offenders: dict[str, list[str]] = {}
    for signature, body, _, _ in functions:
        found = unqualified_references(body, names)
        if found:
            offenders[signature] = found

    assert not offenders, (
        f"These functions name a relation without a schema: {offenders}. Postgres searches the "
        "temporary schema first for relation names, so each of those is a table the *caller* "
        "chooses: a security review of E0-09 reproduced a stored cycle and a stored edge into a "
        "`CARE` assignment by creating `pg_temp.role_assignment` first, as a `NOSUPERUSER` role "
        "with no `CREATE` on `public`. In a `SECURITY DEFINER` function the same trick spends the "
        "definer's privileges on the caller's table. ADR 0027 ships the qualification as the half "
        "that survives somebody dropping the `SET search_path`."
    )
