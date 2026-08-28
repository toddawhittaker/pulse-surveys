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

**One test here is E0-33's** —
`test_every_object_created_under_views_sql_exists_in_the_migrated_database`, the
direction this file did not have, over the view set *and* the function set. It is
here rather than in `test_objects_the_drift_gate_cannot_compare.py` with the rest
of that ticket for the same entry-13 reason: it needs the `CREATE` sweeps below,
whose word boundary took an incident to get right, and a second copy of that
regex is worth more trouble than the file boundary is.

**The tests at the foot of this file are E0-34's** — no count, because one was
added by the review round that found the control below guarding nothing, and a
number here is a record with a scheduled expiry (`docs/MISTAKES.md` entry 1).
They close a hole this module had while looking like it did not.
`test_no_view_reads_a_column_the_identity_marker_names` next door reads
`pg_depend` out of the migrated database, so it sees only the views a migration
has executed — a file that joins `user_identity` and selects a name sits in this
directory and passes that invariant **vacuously**, until the day somebody appends
its name to a revision's `SCRIPTS` tuple in an unrelated ticket. Nothing read
these files looking for identity, and the guard that *did* fire on such a file —
`test_every_relation_a_view_sql_file_names_is_schema_qualified` — has a message
about missing `public.` prefixes, so the invited repair is four prefixes after
which the identity join is untouched and the pipeline is green. A red whose
message points away from the defect spends the one moment somebody was looking.
`test_no_view_created_under_views_sql_names_an_identity_column` is the guard, and
the two planted-file tests below it are the demonstration that neither the
`SCRIPTS` tuple nor the qualification sweep changes its answer.

**E1-01 adds a fourth mechanism to that guard and two inventories beside it.**
The reviewer self-test that found E0-34's blind spots found two more, recorded as
"The §4.1 view sweep is blind to an aliased identity column and to join keys" in
`docs/tickets/e1/carried-from-e0.md`: the three mechanisms below are all phrased
over the identity *vocabulary*, and a view's author chooses the label a column
arrives under. `ui.display_name AS respondent_display_name` matches no fragment,
carries no marker, and names a column this schema does not have — and the sweep
was measured green over the file that selects it. The `bound column` mechanism
reads what an alias is bound *to* instead: a read of any column of `user`,
`user_identity` or `person` other than the keys a view joins on. That closes
`user.lms_user_id` with it, which is the same entry's second finding and which no
rule in this repository looked at before.

**A fresh-context security review then found a third route, and it is why the
`whole row` and `star` mechanisms sweep the guarded tables and not only the
marked ones.**
`SELECT to_jsonb(u) AS platform_ref FROM public."user" u` writes no column name,
no `*` and no qualified reference, so the `column`, `star` and `bound column`
mechanisms are all silent — and the `whole row` mechanism iterated the tables
carrying a *marked* column, which `user` does not and by ADR 0001's design never
will. One statement carrying every value `user` holds, seen by four mechanisms
and reported by none. `SELECT * FROM public."user"` was open through the `star`
mechanism for the identical reason and is closed in the same change, because a
finding names one spelling and a guard owes an answer for the class. The same
review found the quoted spelling `SELECT "user".lms_user_id FROM public."user"`,
which binds no alias and puts a quote where the read pattern expected a dot.
Every one of them has a shape in the inventories below, and each has an
allow-side pair.

**The guard's two controls read their inventory from constants and not from the
table of mechanisms they control**, and that separation is load-bearing rather
than stylistic: with the controls parametrised over `IDENTITY_MECHANISMS`,
deleting a mechanism deleted its own cases and the suite passed at the smaller
size, with a planted file reading a marked identity column and nothing red. The
comment above `REQUIRED_MECHANISM_LABELS` carries what was measured. Do not
re-derive one from the other.

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
    `test_a_shadowed_table_does_not_change_what_the_care_door_returns`.

For views the two rules below are hygiene rather than a guard, and the ticket
says so in as many words. They are still asserted, because the file is the model
the next view is copied from and because a later function that reads a view
inherits that view's text into its own plan.
"""

import importlib.util
import re
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from sqlalchemy import inspect, text

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

# The last four arrived from E0-34's review, which measured this sweep against
# every spelling Postgres accepts and found four it did not match. They are here
# rather than beside E0-34's own samples because this is the sweep that has the
# defect, and because both tickets read it: a `CREATE RECURSIVE VIEW` file was
# simultaneously a view E0-33's set comparison did not expect and a file E0-34's
# identity guard did not sweep.
VIEW_CREATE_MUST_CATCH = (
    f"CREATE VIEW public.{CANARY_VIEW} AS SELECT 1",
    f"create or replace view {CANARY_VIEW} as select 1",
    f'CREATE MATERIALIZED VIEW IF NOT EXISTS public."{CANARY_VIEW}" AS SELECT 1',
    f"CREATE OR REPLACE VIEW\n    public.{CANARY_VIEW} AS\nSELECT 1",
    f"CREATE RECURSIVE VIEW public.{CANARY_VIEW} (n) AS SELECT 1",
    f"CREATE OR REPLACE RECURSIVE VIEW public.{CANARY_VIEW} (n) AS SELECT 1",
    f"CREATE TEMP VIEW {CANARY_VIEW} AS SELECT 1",
    f"CREATE TEMPORARY VIEW public.{CANARY_VIEW} AS SELECT 1",
)

VIEW_CREATE_MUST_ALLOW = (
    f"GRANT SELECT ON public.{CANARY_VIEW} TO pulse_app",
    f"REVOKE ALL ON public.{CANARY_VIEW} FROM PUBLIC",
    f"DROP VIEW IF EXISTS public.{CANARY_VIEW}",
    f"COMMENT ON VIEW public.{CANARY_VIEW} IS 'section membership, no identity'",
    f"-- {CANARY_VIEW} is the section roster; the migration that creates it is next door",
    f"CREATE VIEW public.{CANARY_VIEW}_totals AS SELECT 1",
)

# And the same for the drop sweep, which is what keeps
# `test_every_object_created_under_views_sql_exists_in_the_migrated_database` from
# being a tripwire on a view that was deliberately retired. The must-allow samples
# carry the weight again: `DROP TABLE` and a differently-named view both have to
# fail, or a retired view would excuse a missing one that shares a prefix with it.
VIEW_DROP_MUST_CATCH = (
    f"DROP VIEW public.{CANARY_VIEW}",
    f"drop materialized view if exists {CANARY_VIEW}",
    f'DROP VIEW IF EXISTS public."{CANARY_VIEW}"',
    f"DROP\n    VIEW\n    public.{CANARY_VIEW}",
)

VIEW_DROP_MUST_ALLOW = (
    f"CREATE VIEW public.{CANARY_VIEW} AS SELECT 1",
    f"DROP VIEW public.{CANARY_VIEW}_totals",
    f"DROP TABLE IF EXISTS public.{CANARY_VIEW}",
    f"-- drop view public.{CANARY_VIEW} when §5.5 replaces it",
    f"REVOKE ALL ON public.{CANARY_VIEW} FROM PUBLIC",
)

# What a *sequence* of statements leaves standing, which is a different question
# from either sweep above and the one an independent security review found this
# file getting wrong. Each sample is the files in execution order and whether the
# canary view has to exist at the end of them.
#
# **The first pair is the finding.** A view whose column list changes cannot be
# altered with `CREATE OR REPLACE VIEW`, so ADR 0041's `…_v002.sql` drops it and
# creates it again — and a set of creates minus a set of drops subtracts a view
# that was created twice. The consequence was not theoretical: `section_roster`
# would have dropped out of the expected set permanently, taking with it the
# mutation the test that uses this was written for (E0-20 item 3b, row five).
# The same four sample sets for the function half, which E0-33 item 3 asks for
# beside the view half and which nothing compared until now: a `views_sql/` file
# containing a `CREATE FUNCTION` and left out of every revision's `SCRIPTS` was
# measured leaving all 42 tests green, where the same file shaped as a
# `CREATE VIEW` turned the view test red.
#
# **The must-allow set is where the weight is, and every member of it is a line
# this repository really writes.** `identity_grants_v001.sql` grants and revokes on
# the reveal function by name, and ADR 0043's `ALTER FUNCTION … OWNER TO` is one
# statement in the same family. If any of those read as a creation, the expected
# set would contain a function the files never define — and the test would then be
# asserting something about the catalog on the strength of a `GRANT`, which is
# `docs/MISTAKES.md` entry 3's sixth incident in a new place.
CANARY_FUNCTION = "canary_function"

FUNCTION_CREATE_MUST_CATCH = (
    f"CREATE FUNCTION public.{CANARY_FUNCTION}(uuid) RETURNS text",
    f"create or replace function {CANARY_FUNCTION}() returns void",
    f'CREATE OR REPLACE FUNCTION public."{CANARY_FUNCTION}"(a uuid, b text)',
    f"CREATE PROCEDURE public.{CANARY_FUNCTION}()",
    f"CREATE FUNCTION\n    public.{CANARY_FUNCTION}(uuid)",
)

FUNCTION_CREATE_MUST_ALLOW = (
    f"GRANT EXECUTE ON FUNCTION public.{CANARY_FUNCTION}(uuid) TO pulse_care",
    f"REVOKE ALL ON FUNCTION public.{CANARY_FUNCTION}(uuid) FROM PUBLIC",
    f"ALTER FUNCTION public.{CANARY_FUNCTION}(uuid) OWNER TO pulse_reveal_definer",
    f"COMMENT ON FUNCTION public.{CANARY_FUNCTION}(uuid) IS 'the audited reveal'",
    f"DROP FUNCTION IF EXISTS public.{CANARY_FUNCTION}(uuid)",
    f"-- {CANARY_FUNCTION} is created by the revision, not by this file",
    f"CREATE FUNCTION public.{CANARY_FUNCTION}_v2(uuid) RETURNS text",
)

FUNCTION_DROP_MUST_CATCH = (
    f"DROP FUNCTION public.{CANARY_FUNCTION}(uuid)",
    f"drop function if exists {CANARY_FUNCTION}",
    f'DROP PROCEDURE public."{CANARY_FUNCTION}"()',
)

FUNCTION_DROP_MUST_ALLOW = (
    f"CREATE FUNCTION public.{CANARY_FUNCTION}(uuid) RETURNS text",
    f"DROP FUNCTION public.{CANARY_FUNCTION}_v2(uuid)",
    f"DROP TABLE IF EXISTS public.{CANARY_FUNCTION}",
    f"-- drop function public.{CANARY_FUNCTION}(uuid) when E10 replaces it",
    f"GRANT EXECUTE ON FUNCTION public.{CANARY_FUNCTION}(uuid) TO pulse_care",
)

VIEW_HISTORY_SAMPLES: tuple[tuple[tuple[str, ...], bool], ...] = (
    ((f"DROP VIEW public.{CANARY_VIEW};\nCREATE VIEW public.{CANARY_VIEW} AS SELECT 1;",), True),
    ((f"CREATE VIEW public.{CANARY_VIEW} AS SELECT 1;\nDROP VIEW public.{CANARY_VIEW};",), False),
    ((f"CREATE VIEW public.{CANARY_VIEW} AS SELECT 1;",), True),
    ((f"DROP VIEW public.{CANARY_VIEW};",), False),
    (
        (
            f"CREATE VIEW public.{CANARY_VIEW} AS SELECT 1;",
            f"DROP VIEW public.{CANARY_VIEW};",
        ),
        False,
    ),
    (
        (
            f"CREATE VIEW public.{CANARY_VIEW} AS SELECT 1;",
            f"DROP VIEW public.{CANARY_VIEW};\nCREATE VIEW public.{CANARY_VIEW} AS SELECT 2;",
        ),
        True,
    ),
)


def read_views(connection: Any) -> list[str]:
    """Every view and materialised view in `public`, by name."""
    return [row[0] for row in connection.execute(text(READ_VIEWS))]


# The object a `CREATE` or a `DROP` names, with an optional schema and optional
# double quotes on either part. The name is captured greedily as a whole word, so
# `canary_view_totals` reads as itself rather than as a match for `canary_view` —
# the boundary the name-anchored first version of this sweep needed a `\b` for.
# A function's argument list stops the capture on its own, because `(` is not a
# word character: `CREATE FUNCTION public.reveal(uuid, uuid)` yields `reveal`.
OBJECT_NAME = r'(?:"?(?P<schema>\w+)"?\s*\.\s*)?"?(?P<name>\w+)"?'

# **Every modifier Postgres allows between `CREATE` and `VIEW`, matched in any
# order and any combination.** The first version read `materialized` alone, and
# `CREATE RECURSIVE VIEW`, `CREATE OR REPLACE RECURSIVE VIEW`, `CREATE TEMP VIEW`
# and `CREATE TEMPORARY VIEW` all went unrecognised — measured against this
# pattern during E0-34's review. That is not a contrived spelling:
# `containment_path_v001.sql` is the walk-shaped view in `views_sql/`, and
# `CREATE RECURSIVE VIEW` is the natural way to write its `_v002`.
#
# **Two tickets' worth of effect from one repair.** E0-34's file-side identity
# guard reads this pattern to find the statements it sweeps, so a file it did not
# match was swept not at all and the guard was vacuously green — the exact pass
# that ticket exists to eliminate. E0-33's `object_history`, `creates_view` and
# `objects_standing_after` read it too, so the same file was invisible to the
# view-set comparison against the catalog: a `CREATE RECURSIVE VIEW` under
# `views_sql/` created a view nothing expected to exist.
#
# The repeated group is order-agnostic on purpose. `MATERIALIZED` cannot in fact
# be combined with `TEMPORARY` or `RECURSIVE`, and accepting the combination costs
# nothing: the server refuses the invalid spelling long before any test reads it,
# while a pattern that fixed the order would miss whichever order somebody wrote.
CREATES_A_VIEW = re.compile(
    r"\bcreate\s+(?:or\s+replace\s+)?"
    r"(?:(?:temp(?:orary)?|materialized|recursive)\s+)*view\s+"
    r"(?:if\s+not\s+exists\s+)?" + OBJECT_NAME,
    re.IGNORECASE,
)

DROPS_A_VIEW = re.compile(
    r"\bdrop\s+(?:materialized\s+)?view\s+(?:if\s+exists\s+)?" + OBJECT_NAME,
    re.IGNORECASE,
)

# `procedure` beside `function` because the catalog sweep this is compared against
# filters `prokind IN ('f', 'p')`: a rule that read one and compared against both
# would report a procedure as an object the files never created.
CREATES_A_FUNCTION = re.compile(
    r"\bcreate\s+(?:or\s+replace\s+)?(?:function|procedure)\s+" + OBJECT_NAME,
    re.IGNORECASE,
)

DROPS_A_FUNCTION = re.compile(
    r"\bdrop\s+(?:function|procedure)\s+(?:if\s+exists\s+)?" + OBJECT_NAME,
    re.IGNORECASE,
)


class ObjectKind(NamedTuple):
    """One kind of object a `views_sql/` file can create, and how to find it.

    Two kinds, one mechanism. E0-33 item 3 asks for the view set *and* the function
    set compared against the files that create them, and the fold is identical for
    both — only the keyword differs. Two near-copies of it would be
    `docs/MISTAKES.md` entry 13, and the copy is the one that does not get the next
    repair: the ordering defect this fold exists to fix was found in the view half
    and would have been written into the function half the same day.

    **Both kinds are held to the same rule, and a `must_exist` field that exempted
    functions from it has been removed.** It was added on the ground that no record
    said where a function's SQL belongs. That ground was false and a single grep
    would have shown it:
    [ADR 0041](../../docs/adr/0041-a-read-view-ships-as-an-immutable-versioned-sql-file.md)
    decides it in as many words — "the SQL lives in
    `backend/app/views_sql/<object>_v<NNN>.sql`, and the revision executes it by
    name. Five files ship with E0-10 — the roles, two views, the `SECURITY DEFINER`
    reveal function, and the grants" — and the same record's Consequences describe
    this test's job: "`alembic check` reads neither `pg_class` for views nor
    `pg_proc`, so dropping a view, changing one by hand in a database, or **deleting
    the `CREATE FUNCTION` from a file** leaves the check green. The tests are the
    only reader."

    SPEC §13 being silent about functions is not the same as no record answering,
    and the exemption cost exactly what an exemption costs: with it, moving the
    reveal's `CREATE FUNCTION` inline into a revision left the expectation empty,
    the comparison vacuous and this test green, while its docstring went on claiming
    it survives a dropped function. The identical change to a view failed loudly.
    """

    label: str
    creates: re.Pattern[str]
    drops: re.Pattern[str]


VIEW = ObjectKind("view", CREATES_A_VIEW, DROPS_A_VIEW)
FUNCTION = ObjectKind("function", CREATES_A_FUNCTION, DROPS_A_FUNCTION)
OBJECT_KINDS = (VIEW, FUNCTION)


def object_history(sql: str, kind: ObjectKind) -> tuple[tuple[str, bool], ...]:
    """Every statement in `sql` that creates or drops one of `kind`, **in source order**.

    Each entry is the object's name and whether that statement created it. Order is
    the whole point and was the defect: the first version of this file answered
    "which views are created" and "which are dropped" as two independent sets and
    subtracted one from the other, which cannot see a `DROP` *followed by* a
    `CREATE`. Under ADR 0041's versioned-file rule that is the ordinary shape of a
    view whose column list changes — `CREATE OR REPLACE VIEW` cannot alter a
    column list, so `section_roster_v002.sql` reads `DROP VIEW …;` then
    `CREATE VIEW …;` — and the subtraction would have quietly stopped expecting
    the schema's most identity-sensitive view to exist at all.

    A mention is not a creation, and the difference is the other half of what this
    helper is for. The first version of the test that consumes it searched for the
    view's name anywhere under `views_sql/`, and the mutation the test's own
    docstring named — delete `section_roster_v001.sql` and inline its
    `CREATE VIEW` into the revision — kept it green, because the grants file names
    every view in order to `GRANT SELECT` on it. So `GRANT`, `DROP`, `COMMENT ON`
    and a name in a comment all have to fail as *creations*, and each is a sample
    in `VIEW_CREATE_MUST_ALLOW` above.

    **A function is matched by name and not by signature**, which is a deliberate
    narrowing. `pg_proc` identifies a function by name *and* argument types, and a
    `DROP FUNCTION` may spell them or — since Postgres 10, where the name is
    unambiguous — omit them; the two spellings of a type (`varchar` and `character
    varying`) are a third way for a signature comparison to be wrong about
    something that is right. The property being asserted is that the function the
    file creates *exists*, so the name carries it, and the cost is stated: two
    overloads of one name are one key here.

    **What it does not catch** (`docs/MISTAKES.md` entry 14): a `DROP VIEW a, b`
    naming several objects in one statement, of which it sees only the first. One
    statement per object is what every file here writes, and the failure direction
    is safe — an unseen drop leaves a red naming the object, not a silent green.

    `without_comments` replaces each comment with a single space, which shifts
    offsets but never reorders what is left, so sorting on them is sound.
    """
    code = without_comments(sql)
    events = [(found.start(), found.group("name"), True) for found in kind.creates.finditer(code)]
    events += [(found.start(), found.group("name"), False) for found in kind.drops.finditer(code)]
    return tuple((name, created) for _, name, created in sorted(events))


def objects_standing_after(sources: Iterable[str], kind: ObjectKind) -> set[str]:
    """Which objects of `kind` `sources`, executed in the order given, leave standing.

    The last statement naming an object decides, which is what makes a drop-then-
    recreate an object that still has to exist and a create-then-drop one that does
    not. Across files, the order is the order the caller passes them in; within a
    file it is source order.

    **The cross-file order is the file name's**, and that is a limit worth
    stating. It is exact for the only case where cross-file order can matter —
    two files naming the *same* object, which under ADR 0041 are `…_v001.sql` and
    `…_v002.sql` and sort the way they run. Two different objects are independent
    keys, so nothing about their order matters. A pair of files that share a name
    and do not sort in execution order would fold wrongly, and the fix is the
    naming convention rather than this function.
    """
    standing: dict[str, bool] = {}
    for sql in sources:
        for name, created in object_history(sql, kind):
            standing[name] = created
    return {name for name, created in standing.items() if created}


def creates_view(sql: str, view: str) -> bool:
    """Does `sql` contain a statement that creates the view called `view`?"""
    return (view, True) in object_history(sql, VIEW)


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


def objects_in_catalog(connection: Any, kind: ObjectKind) -> set[str]:
    """Every object of `kind` this project defines in `public`, by bare name.

    The function side is derived from `schema_functions` rather than from a query
    of its own, so the filter that decides which functions are *this project's* —
    `public`, `prokind IN ('f', 'p')`, nothing owned by an extension — lives in one
    place (`docs/MISTAKES.md` entry 13). `regprocedure` renders as
    `[schema.]name(argtypes)`, and the name is what is compared: `object_history`
    matches a function by name for the reasons its docstring gives.

    The `else` is not unreachable defensiveness. A third `ObjectKind` added without
    a catalog reader here would otherwise be compared against whichever branch fell
    through, and an enumeration silently missing a member is the shape
    `docs/MISTAKES.md` entry 14 records.
    """
    if kind is VIEW:
        return set(read_views(connection))
    if kind is FUNCTION:
        return {
            signature.split("(")[0].rsplit(".", 1)[-1].strip('"')
            for signature, *_ in schema_functions(connection)
        }
    pytest.fail(
        f"`objects_in_catalog` has no reader for the object kind {kind.label!r}. It was added to "
        "`OBJECT_KINDS` without a way to ask the catalog about it, so the test comparing the "
        "files against the database has nothing to compare that kind with."
    )


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


@pytest.mark.invariant
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

    **`invariant`-marked, as E1-01's deferral item 4 asks.** Every §4.1 rule this
    module asserts over the `views_sql/` *files* — the schema-qualification sweep
    and the identity-column sweep both — is total only because every live view
    ships through one of those files, and this test is the whole of what says so.
    It ran in the ordinary suite alone, so the isolated §4.1 pass never collected
    the one test holding the text half's completeness: a view inlined into a
    revision would have taken both file sweeps out of reach while that pass went
    on reporting a clean run over the tests that were left. E1-01 item 1's
    text/catalog complementarity is the argument that needs it.

    The marker adds a second reader rather than a second rule: the body already
    asserts directly, which is what `scripts/ci/check_invariant_assertions.py`
    requires of a marked test under E0-36 §3, so nothing here was restructured to
    carry it.
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


@pytest.mark.parametrize("kind", OBJECT_KINDS, ids=[kind.label for kind in OBJECT_KINDS])
def test_every_object_created_under_views_sql_exists_in_the_migrated_database(
    migrated_engine: Any, kind: ObjectKind
) -> None:
    """E0-33 item 3, the view set **and the function set**: the other direction.

    The test above walks from the catalog outwards — every view in the database
    was created by a file. That direction cannot see a view that is *missing*: a
    database with one view, or with none, satisfies it perfectly. This one walks
    from the files outwards, and together they are a set equality with no object
    named anywhere in this module.

    **Both kinds, in one test parametrised over them**, because E0-33 item 3 asks
    for the function set beside the view set and the fold is identical — only the
    keyword differs. The function half was demonstrated missing: a `views_sql/`
    file containing a `CREATE FUNCTION` and left out of every revision's `SCRIPTS`
    left all 42 tests green, where the same file shaped as a `CREATE VIEW` turned
    this one red. Two near-copies of the fold would have been
    `docs/MISTAKES.md` entry 13, and the copy is the one that would not have got
    the ordering repair below.

    **Both halves require the files to create something**, and the canary is the
    same for each: an expectation that came back empty would compare an empty set
    against the catalog and report success. For views that rule is SPEC §13's; for
    functions it is
    [ADR 0041](../../docs/adr/0041-a-read-view-ships-as-an-immutable-versioned-sql-file.md),
    which puts the reveal function's SQL in this directory by name — "five files
    ship with E0-10 — the roles, two views, the `SECURITY DEFINER` reveal function,
    and the grants".

    An earlier version exempted the function half from that canary, on the stated
    ground that no record said where a function's SQL belongs. The record existed
    and says the opposite; `ObjectKind`'s docstring holds what that cost. The
    exemption is gone, and with it the field that carried it — both kinds are now
    the same rule, which is what the record decides.

    **The gap it closes is measured rather than supposed.** E0-20 item 3b dropped
    `public.section_roster` from a freshly upgraded container and `alembic check`
    reported clean — it compares `Base.metadata` against the database and
    `Base.metadata` holds tables and columns, so a `pg_class` entry for a view is
    outside it in both directions. What stands in the way today is
    `test_alembic_upgrade_head_creates_the_identity_separated_read_views`, which
    requires two views: it catches that drop now and stops catching one the day a
    third view lands, because two out of three is still two.

    **Retired views drop out, and that is what keeps this from being a tripwire on
    the directory.** A view replaced by one of another name leaves its `CREATE` in
    the file that shipped it, and `objects_standing_after` is what lets that be true
    without this test going red. It does mean a retirement has to be written under
    `views_sql/` rather than inline in a revision — the rule SPEC §13 already sets
    for a view's creation, applied to the other end of its life.

    **The expectation is a fold in execution order, not a subtraction**, and the
    difference is a MEDIUM an independent security review found here. Sets of
    creates minus sets of drops is order-blind, so a `…_v002.sql` that changes a
    view's column list — which cannot use `CREATE OR REPLACE VIEW` and therefore
    reads `DROP VIEW public.section_roster;` then `CREATE VIEW
    public.section_roster …;` — subtracted that view despite it being created
    twice. The test would then have stopped requiring the schema's most
    identity-sensitive view to exist, permanently and silently, including against
    the very mutation below. `objects_standing_after` lets the last statement naming
    a view decide, and `VIEW_HISTORY_SAMPLES` carries the drop-then-recreate pair
    so that nobody regresses it back to a subtraction.

    **The mutation it exists to survive**: `DROP VIEW public.section_roster`
    against the migrated database — E0-20 item 3b's fifth row — and `DROP FUNCTION
    public.<the reveal>`, which is that table's fourth row and the one row of the
    six never mutated. It survives, too, a revision that stops executing one of the
    files under `views_sql/`, which is how the function half was demonstrated
    missing; and **moving an object's `CREATE` out of its file and into an
    `op.execute` in the revision**, leaving the database identical and only the
    source moved, which is the arrangement ADR 0041 exists to forbid and the one
    the removed exemption made invisible for functions.
    **The near miss it tolerates**: a third object added, in a file and in the
    database together; one renamed, with the drop and the create both under
    `views_sql/`; and one dropped and recreated in a single file, which stays
    expected because it stands at the end.

    **The canary is the set of expected names itself**, for both kinds. A sweep
    that found nothing to expect would compare an empty set against the catalog and
    report success (`docs/MISTAKES.md` entry 3), so an empty expectation is a
    failure whichever kind it is — SPEC §13 requires the views to be here and ADR
    0041 requires the reveal function to be.
    """
    files = view_sql_files()
    assert files, (
        f"{VIEWS_SQL_DIR} holds no `.sql` file, so this test has nothing to expect and would "
        "report success against a database with no view in it at all. "
        "`test_every_read_view_is_created_from_a_sql_file_under_views_sql` diagnoses that."
    )

    expected = objects_standing_after((path.read_text(encoding="utf-8") for path in files), kind)
    assert expected, (
        f"No `.sql` file under {VIEWS_SQL_DIR} leaves a {kind.label} standing at the end of it — "
        f"the files are {[path.name for path in files]}. Either the object's `CREATE` has moved "
        "out of this directory and into an `op.execute` in a revision, every one of them is "
        "dropped again by a later file, or this sweep has gone blind; in all three the comparison "
        "below is between an empty set and whatever the database holds, and passes.\n\n"
        "The first of the three is the one to check first, and it is what this assertion was "
        "added for. ADR 0041 puts the SQL for every one of these objects — 'the roles, two views, "
        "the `SECURITY DEFINER` reveal function, and the grants' — in a versioned file the "
        "revision executes by name, precisely so that the text a migration ran can be read. "
        "Moving a `CREATE` into the revision leaves the database identical and this comparison "
        "with nothing to compare."
    )

    with migrated_engine.connect() as connection:
        present = objects_in_catalog(connection, kind)

    absent = sorted(expected - present)
    assert not absent, (
        f"{absent} are created as a {kind.label} by a file under {VIEWS_SQL_DIR} and are not in "
        f"the migrated database, which holds {sorted(present)}.\n\n"
        "Neither a view nor a function is visible to the drift gate, in either direction: "
        "`alembic check` compares `Base.metadata` against the database, and `Base.metadata` holds "
        "tables and columns. E0-20 item 3b measured both — a dropped view reported **clean**, a "
        "dropped function reported **clean**, and a dropped column in the same run was detected as "
        "the canary. So both ways this happens reach `main` green: the object dropped against a "
        "database, and a revision that stops executing the file that creates it.\n\n"
        f"If the {kind.label} was retired on purpose, its `DROP` belongs under {VIEWS_SQL_DIR} "
        "beside the `CREATE` it retires — which is where this test looks for it, and where the "
        "next reader will look for what happened to it."
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
# now `test_a_shadowed_table_does_not_change_what_the_care_door_returns` in
# `test_identity_grants.py`, pointed at the `SECURITY DEFINER` function, which is
# the SQL in this ticket that really does resolve names on every call. It lives
# there rather than here because that is where the machinery for calling the
# reveal is, and a second copy of it would be `docs/MISTAKES.md` entry 13.


def test_the_text_sweeps_in_this_file_catch_what_they_claim_to() -> None:
    """Every sweep, and the fold over one of them, is run against a sample of each shape.

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

    A third sample of that kind arrived from an independent security review, and
    it is the reason `VIEW_HISTORY_SAMPLES` exists at all: `DROP VIEW …;` followed
    by `CREATE VIEW …;` in one file. Both sweeps are individually correct about
    it — there *is* a create and there *is* a drop — and the fold that subtracted
    one set from the other read it as a retirement. Every sample of the pair shape
    is here rather than in the test that consumes the fold, because a sweep that
    has gone blind should be reported once, under the name of the sweep.
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

    for sample in VIEW_DROP_MUST_CATCH:
        assert (CANARY_VIEW, False) in object_history(sample, VIEW), (
            f"`object_history` does not read {sample!r} as dropping `{CANARY_VIEW}`, which is a "
            "shape it exists to catch. A view retired in `views_sql/` would then still be expected "
            "in the database, and "
            "`test_every_object_created_under_views_sql_exists_in_the_migrated_database` would be "
            "red at the next view anybody replaces."
        )

    for sample in VIEW_DROP_MUST_ALLOW:
        assert (CANARY_VIEW, False) not in object_history(sample, VIEW), (
            f"`object_history` reads {sample!r} as dropping `{CANARY_VIEW}`. It drops something "
            "else, drops nothing, or is a comment — and reading it as a drop excuses the view's "
            "absence from the database, which is the one thing that test exists to notice."
        )

    for sample in FUNCTION_CREATE_MUST_CATCH:
        assert (CANARY_FUNCTION, True) in object_history(sample, FUNCTION), (
            f"`object_history` does not read {sample!r} as creating `{CANARY_FUNCTION}`, which is "
            "a shape it exists to catch. The function half of "
            "`test_every_object_created_under_views_sql_exists_in_the_migrated_database` then "
            "expects nothing — and that test's canary would report it as a directory creating no "
            "function, which is a different defect from a pattern that cannot see one. This loop "
            "is what tells the two apart: with it green, an empty expectation there is a fact "
            "about the files rather than about the regex."
        )

    for sample in FUNCTION_CREATE_MUST_ALLOW:
        assert (CANARY_FUNCTION, True) not in object_history(sample, FUNCTION), (
            f"`object_history` reads {sample!r} as creating `{CANARY_FUNCTION}`. It names the "
            "function without defining it — a `GRANT EXECUTE`, a `REVOKE`, an `ALTER FUNCTION … "
            "OWNER TO`, a comment, or a different function whose name begins the same way. Every "
            "one of those is a line this repository really writes about the reveal function, so "
            "accepting one would put a function in the expected set on the strength of a grant, "
            "and the comparison against the catalog would be asserting something the files never "
            "said."
        )

    for sample in FUNCTION_DROP_MUST_CATCH:
        assert (CANARY_FUNCTION, False) in object_history(sample, FUNCTION), (
            f"`object_history` does not read {sample!r} as dropping `{CANARY_FUNCTION}`, which is "
            "a shape it exists to catch. A function retired in `views_sql/` would then still be "
            "expected in the database, and the test that consumes this would be red at the next "
            "function anybody replaces — E10 replaces the reveal."
        )

    for sample in FUNCTION_DROP_MUST_ALLOW:
        assert (CANARY_FUNCTION, False) not in object_history(sample, FUNCTION), (
            f"`object_history` reads {sample!r} as dropping `{CANARY_FUNCTION}`. It drops "
            "something else, drops nothing, or is a comment — and reading it as a drop excuses "
            "the function's absence from the database, which is the one thing that test exists "
            "to notice."
        )

    for sources, standing in VIEW_HISTORY_SAMPLES:
        assert (CANARY_VIEW in objects_standing_after(sources, VIEW)) is standing, (
            f"Executed in order, {sources!r} should leave `{CANARY_VIEW}` "
            f"{'standing' if standing else 'retired'}, and `objects_standing_after` says "
            "otherwise. Order is the whole of what this fold adds over the two sweeps above: a "
            "set of creates minus a set of drops cannot tell an object that was dropped and "
            "recreated — which is what a `…_v002.sql` changing a column list has to write, "
            "because `CREATE OR REPLACE VIEW` cannot alter one — from an object that was "
            "retired. Getting that backwards drops the most identity-sensitive view in the schema "
            "out of the expected set for good, and the test that consumes the fold then passes "
            "with it missing."
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

    # **The operand is a bool on purpose, and it is a repair rather than a
    # style.** Written as `assert not offenders`, pytest's assertion rewriting
    # appends the repr of the dict to the exception, so the offending file name
    # appears in `str(failure.value)` whatever this message says — and
    # `test_the_schema_qualification_failure_does_not_hide_the_identity_failure`,
    # whose whole job is to establish that this message names the file, would
    # pass against a message that had stopped naming anything. With a plain bool
    # there is nothing for the rewriter to expand: the explanation is
    # `assert False`, and the names below are the only names in the failure.
    # The same fix, in the same shape, as `agrees` in
    # `tests/integration/test_identity_grants.py`, where the mutation battery
    # measured it (E1-01, deferral item 3).
    clean = not offenders
    assert clean, (
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


# ---------------------------------------------------------------------------
# E0-34 — a view *file* that reads identity, whether or not anything ran it.
#
# The vocabulary is borrowed rather than restated. `test_identity_column_marker.py`
# is where the marker convention is defined — the three marker shapes, the
# fixed-point foreign-key walk, and the `IDENTITY_NAME_FRAGMENTS` E0-10 widened —
# and E0-34 says to reuse it rather than write a second list, because two lists in
# two files with nothing comparing them is `docs/MISTAKES.md` entry 3's shape: the
# copy is the one that does not get the next widening, and it goes on reporting
# success over a set that is quietly one column short.
# ---------------------------------------------------------------------------

# The sibling module the vocabulary comes from, and the names taken out of it.
# Named as data rather than written into an `import` statement for the reason that
# module's own docstring gives: a test module importing a sibling test module works
# only because of where pytest puts `tests/` on `sys.path`, and a collection error
# is not a failing test — it is a red with no test name in it, in a suite whose
# invariant pass treats an empty collection as a failure and would then be
# reporting the wrong thing. `identity_marker_module` loads it by file path and
# turns every way that can go wrong into a named failure.
IDENTITY_MARKER_MODULE = "test_identity_column_marker.py"
IDENTITY_MARKER_NAMES = (
    "marked",
    "database_marked_columns",
    "identity_bearing_columns",
    "IDENTITY_NAME_FRAGMENTS",
    # E1-01's two, borrowed for the same reason as the four above rather than
    # retyped here: `PERSON_TABLES` is the set of tables that hold a person by
    # construction and `JOIN_KEY_COLUMNS` is the closed list of columns a view may
    # read from one of them. Both are decided next door, where the marker
    # convention is defined, and a second copy here would be the copy that does
    # not get the next widening (`docs/MISTAKES.md` entry 3).
    "PERSON_TABLES",
    "JOIN_KEY_COLUMNS",
)

# The file planted by the two demonstration tests, and the view it creates. The
# name deliberately contains no fragment the marker sweep looks for and no word
# `identity`: one of those tests asserts that the *identity* column's name is
# absent from the schema-qualification failure, and a file name carrying it would
# satisfy that assertion for a reason that has nothing to do with either sweep.
PLANTED_VIEW = "e0_34_planted_view"
PLANTED_VIEW_FILE = f"{PLANTED_VIEW}_v001.sql"

# The identity column names this guard is **not** looking for, because a column
# holding no identity shares each of them and a sweep over the name could not tell
# the two apart. Empty, measured rather than assumed — as this schema is spelled
# today, no marked column's name is shared with an unmarked one.
#
# It is written down for the same reason `REQUIRED_MECHANISM_LABELS` is. The
# subtraction is computed from the schema, so it grows on its own: add a
# `person.email` beside an unmarked `institution.email` and `email` leaves the
# sweep, `columns` stays non-empty on the other names, every control stays green,
# and a view selecting `p.email` is looked for by nobody. Nothing in a green run
# would say so. With this constant, growing the subtraction is a red that has to
# be answered — either by marking the other column, or by writing the name here
# and saying in the pull request which reads the guard has stopped catching.
EXPECTED_AMBIGUOUS_IDENTITY_NAMES: tuple[str, ...] = ()

# The opening of a dollar-quoted string, `$$` or `$tag$`. Used by the scanner
# below rather than by a match-the-whole-body regex, and that is a repair rather
# than a preference — see `without_quoted_text`.
DOLLAR_TAG = re.compile(r"\$\w*\$")

# A `*` in a select list, in the spellings a view can use: bare, qualified by an
# alias, after a comma rather than first, and after a `DISTINCT` or a
# `DISTINCT ON (…)`. Anchored on `select` or on a comma so that `count(*)` — which
# reads no column and is what an enrollment-count view is made of — does not
# match, and neither does the multiplication in `SELECT a * b`. Every one of those
# is a sample below, including `DISTINCT ON`, which E0-34's review measured as
# passing: the parenthesised expression list sits between `select` and the `*`,
# so a pattern anchored on `select` alone steps over it.
SELECTS_A_STAR = re.compile(
    r"(?:\bselect\b|,)\s*(?:distinct\s+(?:on\s*\([^)]*\)\s*)?)?(?:\"?\w+\"?\s*\.\s*)?\*",
    re.IGNORECASE,
)

# The words that may follow a relation in a `FROM` or `JOIN` clause and are *not*
# an alias for it. Needed because an implicit alias — `FROM public.person p` — is
# how this repository writes SQL, and the whole-row mechanism has to know which
# token names the row. **The failure directions are not symmetric**, which is why
# there are samples for the common members rather than confidence: a word missing
# from this list is read as an alias and produces a false red on correct SQL,
# which is visible; a word wrongly added to it hides an alias and produces a miss,
# which is not. So it is short, and it is pinned by must-allow shapes.
ALIAS_STOP_WORDS = (
    "as where group order having limit offset fetch for union intersect except join inner left"
    " right full cross natural lateral on using window with returning tablesample into"
).split()


class IdentityVocabulary(NamedTuple):
    """What counts as identity in the files, derived from the migrated database.

    Three fields and a reason for each, because each is a decision this guard
    makes and none of them is the obvious one.

    **`columns` is the column-grained evidence only, and deliberately not every
    column `database_marked_columns` reports.** The marker convention accepts a
    *table* comment as marking that table's columns, which is a coherent reading
    of E0-08's criterion and is why the marker module accepts it — but it marks
    the table's key and its timestamps along with its names, so a sweep for those
    *names* in SQL text would flag every view file that mentions `user_id`. So a
    table-grained marker feeds `tables` and the star mechanism, where it is
    exactly right — `SELECT *` over such a table reads all of it — and the
    name-grained sweep is fed by `identity_bearing_columns` and by the marker
    shapes that name a single column.

    **`ambiguous` is subtracted, and it is the reason this guard is not a tripwire
    on legitimate SQL.** A column name that also names a column holding no
    identity — `person.name` beside `institution.name`, if that is how the schema
    spells it — cannot be told apart in text from the innocent one, and a guard
    that reds on `SELECT i.name FROM public.institution i` would be repaired by
    weakening it. The cost is stated rather than hidden: an identity column whose
    name is shared with a non-identity column is invisible to the name sweep, and
    is caught only if the file names its table and stars it.

    **`carried` is what the failure message reads from**, so that a star over a
    table names the identity columns that star reaches. E0-34's second criterion
    is about the message rather than about the red: the same file already fails
    the schema-qualification sweep, whose message is about `public.` prefixes, and
    a reader who fixes four prefixes has left the identity join in place.

    **`guarded` and `join_keys` are E1-01's, and neither is derived from the
    marker at all.** The three fields above all answer "which columns hold
    identity", which is a judgement about names and values; these two answer
    "which tables hold a person, and what may be read from one", which is a fact
    about the schema's shape. The difference is the whole of what E1-01 closes:
    `user` carries no marked column by construction — ADR 0001 puts the key and
    the platform reference there so that they are *not* identity — so it is
    absent from `tables`, present in `guarded`, and `user.lms_user_id` is a
    stable per-person key at the platform that no name-based rule sees.
    """

    tables: frozenset[str]
    columns: frozenset[str]
    ambiguous: frozenset[str]
    carried: dict[str, tuple[str, ...]]
    guarded: frozenset[str]
    join_keys: frozenset[str]


class IdentityFinding(NamedTuple):
    """One identity column, one view, and which mechanism saw it."""

    mechanism: str
    view: str
    column: str


class IdentityMechanism(NamedTuple):
    """One way a view's text can reach an identity column.

    **One line per mechanism, and the samples deliberately live somewhere else.**
    `docs/MISTAKES.md` entry 35 asks for both in as many words — "put the
    mechanisms in a table, one per line, so that disabling one is a single edit
    that still parses" — and the first version of this file put the samples inside
    this tuple, which made disabling one a multi-line deletion *and* took the
    samples away with it. `IDENTITY_SWEEP_MUST_CATCH` is where they are now, and
    the comment above it says what that cost when it was measured.

    The control that consumes them runs **the whole path** — `identity_findings`,
    over the table — rather than calling `find` directly, because a control asked
    of the probe itself stays green when the probe is deleted from the table,
    which is how E0-33 shipped one that guarded nothing.
    """

    label: str
    find: Callable[[str, IdentityVocabulary], tuple[str, ...]]


class RequiredShape(NamedTuple):
    """A shape this guard must catch, the label required to catch it, what it must name.

    **`expected` is E1-01's, and it defaults to what every shape before it
    required**, so the sixteen shapes that predate it are unchanged in meaning:
    the finding must name `{column}`, the identity column this database really
    carries. It is a field rather than a constant because the `bound column`
    mechanism reports `table.column` — it has to, since the column it catches may
    exist in no schema and mean nothing on its own — and because the reviewer's
    fixture reads two different columns off two different person tables in one
    statement, so one shape can require two findings.

    A shape that declared nothing would be one whose control asserts only that
    *something* was reported, and that is the state this file's own history warns
    about twice: a shape two mechanisms both catch kept such an assertion true
    with either one deleted.
    """

    label: str
    template: str
    expected: tuple[str, ...] = ("{column}",)


def identity_marker_module() -> Any:
    """`test_identity_column_marker.py`, loaded by path so a failure has a test's name on it.

    Loaded rather than imported, and the difference is the whole reason this
    function exists. `import test_identity_column_marker` resolves only because
    pytest puts the test directory on `sys.path` for a package with no
    `__init__.py`, so it is one conftest change away from an `ImportError` at
    *collection* time — which is a red with no test name in it, and which the
    invariant gate would report as a collection of zero rather than as a broken
    guard. Every way this can fail is turned into a named failing test instead.

    The alternative is the one the marker module itself took for
    `IDENTITY_NAME_FRAGMENTS` — copy the list and keep the copies in step by
    hand — and E0-34 rules it out in as many words: two lists in two files with
    nothing comparing them is `docs/MISTAKES.md` entry 3's shape. The copies that
    exist are named in that module's comment; this file is deliberately not a
    fourth.
    """
    path = Path(__file__).with_name(IDENTITY_MARKER_MODULE)
    if not path.is_file():
        pytest.fail(
            f"{path} does not exist. It is where the identity-marker convention is defined — the "
            "marker shapes, the fixed-point foreign-key walk and the widened name fragments — and "
            "every assertion E0-34 makes about a `views_sql/` file is phrased in that vocabulary. "
            "If the module has moved, this constant moves with it; if it has been deleted, the "
            "guard below has nothing to look for and would report success over any file at all."
        )

    spec = importlib.util.spec_from_file_location("e0_34_identity_marker_vocabulary", path)
    if spec is None or spec.loader is None:
        pytest.fail(
            f"Python could not build an import spec for {path}, so its vocabulary is out of reach "
            "and every sweep below would have nothing to look for."
        )

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as failure:
        pytest.fail(
            f"Executing {path} raised {failure!r}. That module is a test module and is expected to "
            "import cleanly at collection; if it does not, this guard cannot borrow its "
            "vocabulary. Read the error first — it is a fact about that module rather than about "
            "the view files this test sweeps."
        )

    missing = [name for name in IDENTITY_MARKER_NAMES if not hasattr(module, name)]
    if missing:
        pytest.fail(
            f"{path.name} no longer defines {missing}. E0-34 borrows the identity vocabulary from "
            "there rather than restating it, so a rename in that module has to be followed here "
            "rather than worked around with a second list — `docs/MISTAKES.md` entry 3. Until it "
            "is, the sweep below has no set of identity columns to look for."
        )
    return module


def build_identity_vocabulary(engine: Any, marker: Any) -> IdentityVocabulary:
    """What the migrated database says identity is, in the shape the file sweep needs.

    `marked` is called a second time with the table comment withheld, which is how
    the column-grained evidence is separated from the table-grained evidence
    without a second copy of the marker rules living here — the same function
    answers both questions, so widening the convention widens both halves
    (`docs/MISTAKES.md` entry 13). `IdentityVocabulary`'s docstring says why the
    two halves feed different mechanisms.
    """
    inspector = inspect(engine)
    every_column: set[tuple[str, str]] = set()
    column_grained: set[tuple[str, str]] = set()
    for table_name in inspector.get_table_names():
        for column in inspector.get_columns(table_name):
            every_column.add((table_name, column["name"]))
            if marker.marked(table_name, column["name"], column.get("comment"), None):
                column_grained.add((table_name, column["name"]))

    named = set(marker.identity_bearing_columns(engine)) | column_grained
    holding = set(marker.database_marked_columns(engine)) | named

    carried: dict[str, list[str]] = {}
    for table_name, column_name in sorted(holding):
        carried.setdefault(table_name, []).append(column_name)

    names = {column for _, column in named}
    elsewhere = {column for _, column in every_column - holding}
    ambiguous = names & elsewhere

    return IdentityVocabulary(
        tables=frozenset(carried),
        columns=frozenset(names - ambiguous),
        ambiguous=frozenset(ambiguous),
        carried={table: tuple(columns) for table, columns in carried.items()},
        guarded=frozenset(marker.PERSON_TABLES),
        join_keys=frozenset(column.lower() for column in marker.JOIN_KEY_COLUMNS),
    )


@pytest.fixture(scope="session")
def identity_vocabulary(migrated_engine: Any) -> IdentityVocabulary:
    """The identity vocabulary, read once out of the database the session migrated."""
    return build_identity_vocabulary(migrated_engine, identity_marker_module())


def without_quoted_text(sql: str) -> str:
    """`sql` with comments, string literals and dollar-quoted bodies blanked out.

    **One left-to-right scan, and not two regexes**, which is a repair with a
    measurement behind it. The first version substituted dollar-quoted bodies and
    then string literals, in that order, and the order was forced: a function body
    is dollar-quoted precisely so that it may contain apostrophes, so stripping
    literals first lets an `it's` inside one swallow everything to the next quote.
    Running the other way has the mirror defect, and it is worse. E0-34's review
    measured it: a file holding `SELECT 'p$x$1';`, then an identity-reading
    `CREATE VIEW`, then `SELECT 'q$x$2';` has two `$x$` sequences that live inside
    *different* string literals, and the dollar-quote pattern pairs them with each
    other and deletes the statement between. The view disappears before any
    mechanism runs, and because it is deleted rather than truncated no canary over
    the statements that were found can notice.

    A single scan has no order to get wrong: whichever quoting starts first
    consumes its own contents, so a `$x$` inside a literal is literal text and an
    apostrophe inside a dollar body is body text. The blanks are the same length
    as what they replace, so every offset — and every statement-ending `;` outside
    a quote — stays exactly where the author put it.

    The direction is still the one this module chose for `without_comments`:
    removing text can hide a reference but can never invent one, which is the safe
    side for a tripwire whose other failure mode is flagging correct SQL and being
    weakened for it. **An unterminated literal or dollar tag blanks the rest of
    the file**, which is the one way text can still disappear;
    `test_no_view_created_under_views_sql_names_an_identity_column` cross-checks
    the statements found here against the ones E0-33's `objects_standing_after`
    finds without this scan, which is what makes that visible.

    **A dollar-quoted body goes entirely**, and that is not tidying — it is what
    keeps this guard off `views_sql/`'s `SECURITY DEFINER` reveal function, which
    reads identity by design (ADR 0001, point 4). A guard that has to be exempted
    by name on the day it lands is a guard nobody trusts, and the exemption would
    be a file name rather than a property. The property is that the reveal is a
    function and this rule is about views; `view_bodies` is where that is applied,
    and `IDENTITY_SWEEP_MUST_ALLOW` carries the reveal's shape as a sample.
    """
    code = without_comments(sql)
    kept: list[str] = []
    position = 0
    while position < len(code):
        if code[position] == "'":
            end = position + 1
            while end < len(code):
                if code[end] != "'":
                    end += 1
                elif end + 1 < len(code) and code[end + 1] == "'":
                    end += 2
                else:
                    end += 1
                    break
            kept.append(" " * (end - position))
            position = end
            continue
        opening = DOLLAR_TAG.match(code, position)
        if opening:
            closing = code.find(opening.group(0), opening.end())
            end = len(code) if closing == -1 else closing + len(opening.group(0))
            kept.append(" " * (end - position))
            position = end
            continue
        kept.append(code[position])
        position += 1
    return "".join(kept)


class ViewStatement(NamedTuple):
    """One `CREATE … VIEW` statement: the view's name, the whole statement, its query.

    `query` is what follows the create clause, and it exists so that the canary
    over these statements can ask whether the statement was cut short *without*
    requiring it to contain the word `select`. `CREATE VIEW x AS TABLE public.y`
    and `CREATE VIEW x AS VALUES (…)` are both views and neither contains one; a
    canary that demanded `select` would have been red on a legitimate file, and —
    worse — its message would have talked about quoting while the `TABLE` form
    read every column of an identity table.
    """

    name: str
    text: str
    query: str


def view_bodies(sql: str) -> tuple[ViewStatement, ...]:
    """Every `CREATE … VIEW` statement in `sql`.

    The statement runs from the `CREATE` to the next `;`, or to the end of the
    file if there is none — and `without_quoted_text` has already blanked the
    comments, the literals and the dollar-quoted bodies, so a `;` inside any of
    those cannot end a statement early.

    `CREATES_A_VIEW` is E0-33's regex rather than a second one. Its word boundary
    took an incident to get right, it reads `CREATE OR REPLACE`, `MATERIALIZED`,
    `RECURSIVE`, `TEMPORARY`, `IF NOT EXISTS`, an optional schema, optional quotes
    and a line break between the keyword and the name — and a copy here would be
    the copy that does not get the next repair (`docs/MISTAKES.md` entry 13). Four
    of those spellings were added by E0-34's review, which found the pattern
    matching neither `RECURSIVE` nor `TEMPORARY`: a file spelled either way was
    swept not at all, and this guard was green over it.
    """
    code = without_quoted_text(sql)
    found: list[ViewStatement] = []
    for match in CREATES_A_VIEW.finditer(code):
        terminator = code.find(";", match.end())
        stop = len(code) if terminator == -1 else terminator
        found.append(
            ViewStatement(match.group("name"), code[match.start() : stop], code[match.end() : stop])
        )
    return tuple(found)


def names_a_relation(sql: str, name: str) -> bool:
    """Does `sql` name `name` in a relation position, schema-qualified or not?"""
    return any(pattern.search(sql) for pattern in relation_patterns(name))


def identity_columns_named(body: str, vocabulary: IdentityVocabulary) -> tuple[str, ...]:
    """Every identity column `body` names as a word.

    A whole word, so `identity_name_hash` is a different column and says so. Case
    is ignored and double quotes fall outside the boundary, so `"identity_name"`
    and `UI.Identity_Name` are the same reference — which is the spelling somebody
    reaches for when a review has just asked about the other one.
    """
    return tuple(
        name
        for name in sorted(vocabulary.columns)
        if re.search(rf"\b{re.escape(name)}\b", body, re.IGNORECASE)
    )


def identity_columns_a_star_reaches(body: str, vocabulary: IdentityVocabulary) -> tuple[str, ...]:
    """Every identity column a `SELECT *` in `body` reads, through a table it names.

    The mechanism the name sweep cannot have: `CREATE VIEW … AS SELECT * FROM
    public.user_identity` names no column at all, so a guard phrased over column
    names alone is green against the widest read in the schema. It is also one of
    the two places the table-grained marker is honoured, because a `*` really does
    reach every column of the table it stars.

    **It sweeps the guarded person tables too, for the reason
    `identity_rows_read_whole` below now does.** The security review that found
    `to_jsonb(u)` invisible on this side named that spelling; `SELECT * FROM
    public."user"` is the same exposure through this mechanism, and it was
    invisible for the identical reason — the iteration was over the tables
    carrying a *marked* column, and `user` carries none by ADR 0001's design.
    Widening only the mechanism the review happened to name would have left the
    wider of the two reads open, which is `docs/MISTAKES.md` entry 35's rule read
    the wrong way round: a finding names one currency and the guard owes an answer
    for the class.

    The catalog rule does catch that one — a `*` records a column dependency for
    every column, so `test_identity_column_marker.py` sees it — which makes this a
    gap only for a `views_sql/` file no revision has executed. That is precisely
    the state E0-34 exists to cover, so it is closed here rather than left to the
    other side.
    """
    if not SELECTS_A_STAR.search(body):
        return ()
    return tuple(
        sorted(
            {
                column
                for table in sorted(vocabulary.tables | vocabulary.guarded)
                if names_a_relation(body, table)
                for column in vocabulary.carried.get(table, ()) or (f"{table}.*",)
            }
        )
    )


def relation_bindings(sql: str, name: str) -> tuple[tuple[int, int, str], ...]:
    """Every `FROM`/`JOIN` of `name` in `sql`: where the clause is, and the alias it binds.

    The alias is the token after the relation, with or without `AS`, and only if
    it is not one of `ALIAS_STOP_WORDS` — `FROM public.person WHERE …` binds no
    alias, and reading `WHERE` as one would make every later `WHERE` in the file a
    whole-row reference.

    The span matters as much as the alias. It is what lets the caller tell the
    occurrence that *binds* a name from an occurrence that *uses* it: in
    `FROM public.user_identity ui`, both `user_identity` and `ui` appear, and
    neither is a read.
    """
    quoted = re.escape(name)
    stop = "|".join(ALIAS_STOP_WORDS)
    pattern = re.compile(
        rf'\b(?:from|join)\s+(?:only\s+)?(?:"?\w+"?\s*\.\s*)?(?:"{quoted}"|{quoted}\b)'
        rf'(?:\s+as\b)?(?:\s+(?!(?:{stop})\b)("?\w+"?))?',
        re.IGNORECASE,
    )
    return tuple(
        (found.start(), found.end(), (found.group(1) or "").strip('"'))
        for found in pattern.finditer(sql)
    )


def identity_rows_read_whole(body: str, vocabulary: IdentityVocabulary) -> tuple[str, ...]:
    """Every identity column `body` reads by taking the *whole row* of its table.

    **The mechanism neither half of the §4.1 pair had, found by review and
    measured on both.** `SELECT to_jsonb(ui) FROM public.user_identity ui` names
    no column and writes no `*`, so the column sweep and the star sweep are both
    silent — and Postgres records a whole-row reference at `refobjsubid = 0`,
    which the catalog invariant next door filters out with `> 0`, so it is silent
    too. Every student's name and email address travels through that view. The
    same is true of `row_to_json(ui)`, of a bare `SELECT ui`, of `(ui.*)::text`,
    and of `TABLE public.user_identity`, which is `SELECT * FROM` under another
    spelling and carries no `SELECT` at all.

    The rule: an identity table's row is read whole when its name or its bound
    alias appears **outside the `FROM`/`JOIN` clause that binds it and not
    followed by a `.`**, or when either appears as `x.*` anywhere. A qualified
    reference — `ui.identity_name` — is a column read and belongs to the column
    mechanism; the whole row is what is left.

    **It sweeps the guarded person tables as well as the marked ones, which is
    E1-01's widening and a security review's finding.** As E0-34 wrote it, this
    iterated the tables carrying a marked column and skipped any table with none
    — and `user` has none by construction, because ADR 0001 puts the key and the
    platform reference there precisely so that they are *not* identity. So
    `SELECT to_jsonb(u) AS platform_ref FROM public."user" u` was seen by no
    mechanism here and by neither dependency grain in the catalog: the shape that
    carries `lms_user_id` and everything else `user` holds, reported by nothing.
    A table with no marked column now reports `<table>.*`, because there is no
    column name to report and the star is what tells a reader which shape they
    are looking at.

    **The widening lives here rather than in `person_table_columns_bound`**, and
    the choice is entry 13's: "is this row read whole" is one question, this is
    where it is answered, and a second implementation of it inside the
    bound-column mechanism would be the copy that does not get the next repair —
    the comma-join false positive below took a review to find and is stated in one
    place.

    **A quote between the token and its dot is still a column read.** `"user".id`
    binds no row; it names a column of one. The lookahead below refuses it for the
    same reason `person_table_columns_bound` was taught to *accept* it — the two
    mechanisms have to agree about which shape a quoted reference is, or a
    quoted column read is reported as a whole-row read by one of them and the
    repair is to weaken whichever fired.

    **Its known false positive, stated rather than discovered**
    (`docs/MISTAKES.md` entry 14): an old-style comma join,
    `FROM public.a, public.user_identity ui`, binds through no `FROM` or `JOIN`
    keyword, so the table's name reads as a bare use and is reported. This
    repository writes explicit `JOIN … ON`, the shape is worth a human look
    wherever it appears over an identity table, and a comma join rewritten as a
    `JOIN` is both the repair and better SQL. It is a red on correct-if-unusual
    SQL, which is the direction that gets a guard weakened, so it is named here
    and in the guard's failure message rather than left to be found.
    """
    found: set[str] = set()
    for table in sorted(vocabulary.tables | vocabulary.guarded):
        columns = vocabulary.carried.get(table, ()) or (f"{table}.*",)
        bindings = relation_bindings(body, table)
        spans = [(start, end) for start, end, _ in bindings]
        names = {table} | {alias for _, _, alias in bindings if alias}
        for token in names:
            bare = re.compile(rf'\b{re.escape(token)}\b(?!"?\s*\.)', re.IGNORECASE)
            whole = re.compile(rf'\b{re.escape(token)}"?\s*\.\s*\*', re.IGNORECASE)
            outside = [
                match
                for match in bare.finditer(body)
                if not any(start <= match.start() < end for start, end in spans)
            ]
            if outside or whole.search(body):
                found.update(columns)
    return tuple(sorted(found))


def person_table_columns_bound(body: str, vocabulary: IdentityVocabulary) -> tuple[str, ...]:
    """Every column `body` reads off a table that holds a person, other than a join key.

    **The mechanism that does not need to know the column's name**, which is
    E1-01's whole subject. The three above are all phrased over the identity
    vocabulary — a marked column's name, a marked table's row — and a view's
    author chooses the label: the reviewer's fixture selects
    `ui.display_name AS respondent_display_name`, and the repository's own §4.1
    sweep was measured **green** over that file. `display_name` is in no schema
    here, matches no fragment, and carries no marker, so there is nothing about
    the column for a vocabulary to hold.

    What is knowable is the *lineage*: `ui` is bound to `user_identity` by the
    join two lines below, so `ui.<anything>` is a read of a table that holds a
    person, and the only such reads a view has a reason to make are the keys it
    joins on. So the rule is the other way round from its three neighbours — an
    allow-list of columns rather than a search for forbidden ones — and it fires
    on a column that does not exist in today's schema exactly as it fires on one
    that does.

    `relation_bindings` is what supplies the lineage, and it is E0-34's function
    rather than a second one: the alias it binds and the span of the clause that
    binds it took an incident to get right, and the whole-row mechanism above
    already depends on both (`docs/MISTAKES.md` entry 13).

    **The left boundary is load-bearing and is pinned by a sample.** Without it,
    any token *ending* in a bound name is read as that name — `xu.note` becomes
    `u.note` and is reported as a read of `user` — which flags correct SQL and so
    fails in the direction that gets a guard weakened rather than the direction
    that leaks. A mutation battery found nothing distinguishing the two versions,
    so `IDENTITY_SWEEP_MUST_ALLOW` now carries the two-alias shape that does.

    **It is a lookbehind rather than a `\\b`, because a quote is not a word
    character.** `SELECT "user".lms_user_id FROM public."user"` puts a `"` between
    the token and its dot and binds no alias to fall back on, so a pattern
    anchored with `\\b` and requiring the dot immediately after the name matched
    nothing at all — found by a fresh-context security review. The optional quotes
    are matched on both sides of the token and `(?<![\\w"])` keeps the left
    boundary: `"user_archive".note` still does not match, because the quote is
    consumed before the token and what follows the token is `_` rather than a dot.

    **What it cannot see**, stated here rather than found later
    (`docs/MISTAKES.md` entry 14):

      - **a read through a relation it did not see bound.** A comma join binds
        through no keyword `relation_bindings` reads, so `FROM public.a,
        public.user_identity ui` leaves `ui.identity_name` unattributed here. The
        whole-row mechanism over-reports that same shape rather than
        under-reporting it, which is stated as its known false positive, so the
        file is still red — with a message about the row rather than the column.
      - **a chain of views.** A view reading `roster.leaked` is reading a column
        of a *view*, and this mechanism is scoped to the three tables that hold a
        person. `test_identity_column_marker.py`'s strict rule folds those hops
        in the catalog, where the dependency is recorded.
      - **an unqualified read.** `SELECT identity_name FROM public.user_identity`
        names no alias and no table before the column, so this sees nothing —
        the `column` mechanism is what catches that, and it catches it only
        because the column carries a name the vocabulary knows.
      - **a name bound by a CTE.** `WITH ui AS (SELECT * FROM public.user_identity)
        SELECT ui.identity_name FROM ui` binds `ui` in a `WITH` clause rather than
        in the `FROM` this reads, so `relation_bindings` reports nothing and every
        later `ui.<column>` is unattributed. **This is deliberately not closed
        here**: following a CTE in text means resolving one query's scope from
        another's, which is parsing SQL rather than sweeping it, and a
        half-resolved scope flags correct queries.

        The backstop is **the catalog at column grain and this module's own
        whole-row mechanism at the other**, which is narrower than the first
        version of this note claimed and is measured rather than reasoned.
        `test_identity_column_marker.py`'s strict rule reads what the *stored*
        view depends on, so a CTE that reads a column records the same
        column-grain dependency a plain join does. It does **not** follow that a
        CTE leaves the same row at both grains: Postgres drops the
        `refobjsubid = 0` whole-row row as soon as the view also names any column
        of that table, so the join form of a whole-row read records only the
        column it joined on. `identity_rows_read_whole` above catches that
        spelling — it is text, and it was attacked and held.

        **The two sides no longer trade places there, and this paragraph used to
        say they did.** Batch A closed E1-01's first deferred item: the catalog
        half reads `pg_get_viewdef` as well as `pg_depend`, so
        `decompiled_whole_row_reads` in `test_identity_column_marker.py` reports
        the join-hidden whole-row form the dependency row does not survive. Each
        side now answers for the same shape in its own currency — this module for
        the spellings a human writes in a `views_sql/` file, that one for what
        Postgres decompiled a stored view back to — and neither is the guarantee
        on its own.

        A file no revision has executed is still the case that falls between the
        two at column grain, and it is the one this mechanism cannot answer for.
    """
    found: set[str] = set()
    for table in sorted(vocabulary.guarded):
        bindings = relation_bindings(body, table)
        if not bindings:
            continue
        for token in sorted({table} | {alias for _, _, alias in bindings if alias}):
            reads = re.compile(rf'(?<![\w"])"?{re.escape(token)}"?\s*\.\s*"?(\w+)"?', re.IGNORECASE)
            for match in reads.finditer(body):
                if match.group(1).lower() not in vocabulary.join_keys:
                    found.add(f"{table}.{match.group(1)}")
    return tuple(sorted(found))


# The mechanisms this guard is made of: one line each, so that disabling one is a
# single edit that still parses and can therefore be measured.
IDENTITY_MECHANISMS = (
    IdentityMechanism("column", identity_columns_named),
    IdentityMechanism("star", identity_columns_a_star_reaches),
    IdentityMechanism("whole row", identity_rows_read_whole),
    IdentityMechanism("bound column", person_table_columns_bound),
)

# ---------------------------------------------------------------------------
# The inventory: what this guard is **required** to catch. Three constants, and
# none of them is derived from the structure it describes — two from
# `IDENTITY_MECHANISMS`, and E1-01's third from the person tables the marker
# module names. That separation is the whole point and is worth stating plainly,
# because re-deriving one from the other is a tidy-looking edit that silently
# removes the guard.
#
# **Measured, on this file, before the separation existed.** The controls were
# parametrised over `IDENTITY_MECHANISMS`, so deleting the `column` mechanism did
# not fail its case — it *deleted* its case. The suite shrank to match the table
# and reported success at the smaller size: "2 passed" where there had been 3, and
# with a file planted under `views_sql/` selecting a marked identity column, the
# guard and both controls reported three green while nothing in the tree looked at
# that column. That is `docs/MISTAKES.md` entry 3's parametrised test that covers
# every member but one — where the missing member is the one that was removed —
# arriving one level above the mistake entry 35 exists to stop. A control whose
# inventory of what must be caught comes from the structure it is guarding cannot
# notice that structure getting smaller.
#
# So: `REQUIRED_MECHANISM_LABELS` is a written-down list of the mechanisms this
# module is required to have, and shrinking it is a decision to argue for in a
# pull request rather than a consequence of deleting code elsewhere.
# `IDENTITY_SWEEP_MUST_CATCH` is the shapes, each tagged with the label required
# to catch it. `{column}` and `{table}` are substituted from the live database — a
# real identity column on the real table that carries it — so the controls run
# against this schema's own vocabulary rather than a name this file invented.
# `{other}` is `CANARY`, a relation that exists in no database and is certainly
# not an identity table, which is what keeps each column shape outside the star
# mechanism's reach.
#
# **A shape may be caught by more than one mechanism, and that is now harmless.**
# It was not harmless in the version this file first shipped, where the control
# asserted only that *something* was found: a shape two mechanisms both caught
# kept that assertion true with either one deleted. The control asserts the
# *label* now, so `ui.*` being both a star and a whole-row read costs nothing and
# each mechanism still answers for itself.
# ---------------------------------------------------------------------------
REQUIRED_MECHANISM_LABELS = ("column", "star", "whole row", "bound column")

# The tables E1-01's `bound column` mechanism is required to guard, written down
# here for the reason `REQUIRED_MECHANISM_LABELS` above is: the mechanism reads
# `PERSON_TABLES` out of `test_identity_column_marker.py`, where the convention is
# defined, and a required list that came from the same place could not notice that
# set getting smaller. Deleting `"user"` from it there is one word, leaves every
# test in that module green — `user` carries no marked column, so nothing there is
# about it — and takes with it the only rule in the repository that looks at
# `user.lms_user_id`.
REQUIRED_GUARDED_PERSON_TABLES = ("user", "user_identity", "person")

IDENTITY_SWEEP_MUST_CATCH = (
    RequiredShape(
        "column",
        "CREATE VIEW public.{view} AS SELECT r.{column} FROM public.{other} r;",
    ),
    RequiredShape(
        "column",
        "CREATE VIEW public.{view} AS SELECT r.{column} AS leaked FROM public.{other} r;",
    ),
    RequiredShape(
        "column",
        "CREATE VIEW public.{view} AS SELECT 1 FROM public.{other} r"
        " WHERE r.{column} IS NOT NULL;",
    ),
    RequiredShape(
        "column",
        'CREATE OR REPLACE VIEW\n    public.{view} AS\nSELECT\n    r."{column}"\n'
        "FROM public.{other} r;",
    ),
    RequiredShape(
        "column",
        "CREATE MATERIALIZED VIEW public.{view} AS SELECT {column} FROM public.{other};",
    ),
    RequiredShape("star", "CREATE VIEW public.{view} AS SELECT * FROM public.{table};"),
    RequiredShape("star", "CREATE VIEW public.{view} AS SELECT ui.* FROM public.{table} ui;"),
    RequiredShape(
        "star", "CREATE VIEW public.{view} AS SELECT 1 AS n, ui.* FROM public.{table} ui;"
    ),
    RequiredShape("star", "CREATE VIEW public.{view} AS SELECT DISTINCT * FROM {table};"),
    RequiredShape(
        "star",
        "CREATE VIEW public.{view} AS SELECT DISTINCT ON (a, b) * FROM public.{table};",
    ),
    RequiredShape(
        "star",
        "CREATE VIEW public.{view} AS SELECT *\n"
        "FROM public.{other} r\nJOIN public.{table} ui ON ui.id = r.id;",
    ),
    # The five shapes E0-34's review measured as passing both halves of the §4.1
    # pair. Every one of them carries the whole row of an identity table, and the
    # first four write no column name and no `*` at all.
    RequiredShape(
        "whole row",
        "CREATE VIEW public.{view} AS SELECT to_jsonb(ui) AS whole FROM public.{table} ui;",
    ),
    RequiredShape(
        "whole row",
        "CREATE VIEW public.{view} AS SELECT row_to_json(t) FROM public.{table} AS t;",
    ),
    RequiredShape(
        "whole row",
        "CREATE VIEW public.{view} AS SELECT ui FROM public.{table} ui;",
    ),
    RequiredShape(
        "whole row",
        "CREATE VIEW public.{view} AS SELECT (ui.*)::text FROM public.{table} ui;",
    ),
    RequiredShape("whole row", "CREATE VIEW public.{view} AS TABLE public.{table};"),
    # The widest read of the same table, through the mechanism beside it. Not the
    # spelling the review named — it named `to_jsonb` — and it was open for the
    # identical reason, so it is closed and controlled in the same change.
    RequiredShape(
        "star",
        'CREATE VIEW public.{view} AS SELECT * FROM public."user";',
        ("user.*",),
    ),
    # The same mechanism over the person table that carries **no marked column**,
    # which is where a fresh-context security review walked around every guard in
    # this repository at once. `user` holds the LMS key and the platform reference
    # by ADR 0001's split, so it is in no marked-table set — and the row of it is
    # every one of those values under one harmless column name. The alias is the
    # reviewer's own: this is what the accident looks like.
    RequiredShape(
        "whole row",
        'CREATE VIEW public.{view} AS SELECT to_jsonb(u) AS platform_ref FROM public."user" u;',
        ("user.*",),
    ),
    RequiredShape(
        "whole row",
        'CREATE VIEW public.{view} AS SELECT u FROM public."user" u;',
        ("user.*",),
    ),
    # The quoted spelling, which binds no alias and puts a `"` between the table
    # name and its dot — so a pattern anchored on `\b` and requiring the dot
    # immediately after the name matched nothing at all. Also a security review's,
    # and the reason the read pattern carries a lookbehind rather than a boundary.
    RequiredShape(
        "bound column",
        'CREATE VIEW public.{view} AS SELECT "user".lms_user_id FROM public."user";',
        ("user.lms_user_id",),
    ),
    # E1-01's shapes, and the first of them is the reviewer's fixture. Its lines
    # are **copied** out of `.claude/review-fixtures/identity-column-in-view.diff`
    # rather than retyped, including the run of spaces before each `AS` — entry
    # 3's canary rule, whose whole point is that a sentence retyped from where you
    # think it begins is the thing the sample exists to disprove. The `FROM` is
    # the one adapted line: the fixture reads `FROM response r`, and `response`
    # arrives with the survey tables in E2, so the canary relation stands in for
    # it. Nothing about the two identity reads changes with it.
    #
    # One statement, two required findings, on two different person tables — the
    # aliased name and the LMS join key are the two blind spots the carried entry
    # measured, and the fixture writes them four lines apart.
    RequiredShape(
        "bound column",
        "CREATE OR REPLACE VIEW public.{view} AS\n"
        "SELECT\n"
        "    ui.display_name     AS respondent_display_name,\n"
        "    u.lms_user_id\n"
        "FROM public.{other} r\n"
        'JOIN "user" u        ON u.id = r.user_id\n'
        "JOIN user_identity ui ON ui.user_id = u.id;",
        ("user_identity.display_name", "user.lms_user_id"),
    ),
    # The same read moved into a `WHERE`, where nothing appears in the view's own
    # column list at all. A guard reading output labels sees a view returning one
    # integer.
    RequiredShape(
        "bound column",
        "CREATE VIEW public.{view} AS SELECT 1 AS n FROM public.{other} r\n"
        "JOIN user_identity ui ON ui.user_id = r.user_id\n"
        "WHERE ui.display_name IS NOT NULL;",
        ("user_identity.display_name",),
    ),
    # And the same rule over a column this schema really carries, aliased to a
    # name no fragment matches. Caught by the `column` mechanism too, which is
    # harmless — the control asserts per label — and it is what ties this
    # mechanism's report to the real vocabulary rather than to a name the fixture
    # invented.
    RequiredShape(
        "bound column",
        "CREATE VIEW public.{view} AS SELECT p.{column} AS respondent FROM public.{table} p;",
        ("{table}.{column}",),
    ),
)

# What the sweep must **allow**, and this is where the weight is: every member is
# a line this repository either already writes or would write next, and each one
# flagged is a red whose only available repair is to weaken the guard.
#
# The first is the whole reason `view_bodies` exists. ADR 0001 point 4 gives Care
# its access through one `SECURITY DEFINER` function that returns identity, that
# function's SQL ships in this same directory (ADR 0041), and a file-grained rule
# would be red on it the day it landed. The exemption is a property — this rule is
# about views — rather than a file name on a list.
IDENTITY_SWEEP_MUST_ALLOW = (
    "CREATE FUNCTION public.reveal_sample(uuid) RETURNS text\n"
    "    LANGUAGE sql SECURITY DEFINER AS $$\n"
    "    SELECT ui.{column} FROM public.{table} ui WHERE ui.id = $1\n"
    "$$;",
    "GRANT SELECT ON public.{table} TO pulse_care;",
    "REVOKE ALL ON public.{table} FROM PUBLIC;",
    "COMMENT ON VIEW public.{view} IS 'section membership; reads no {column}';",
    "-- {column} is deliberately not selected here\n"
    "CREATE VIEW public.{view} AS SELECT 1 FROM public.{other};",
    "CREATE VIEW public.{view} AS SELECT count(*) FROM public.{table};",
    "CREATE VIEW public.{view} AS SELECT r.{column}_hash FROM public.{other} r;",
    "CREATE VIEW public.{view} AS SELECT e.id FROM public.{table} ui"
    " JOIN public.{other} e ON e.id = ui.id;",
    "CREATE VIEW public.{view} AS SELECT 'no {column} here'::text AS note FROM public.{other};",
    # The multiplication trap, whose subject moved with E1-01 and whose purpose did
    # not. As first written it read `FROM public.{table} r` and selected `r.a *
    # r.b` — two columns of an identity table, which the strict rule forbids
    # outright, so the sample asserted something this ticket makes false and had to
    # change. **Re-pointing the `FROM` at the canary alone would have quietly
    # retired it**: the star mechanism only reports a column when the body also
    # names a table that carries one, so with no identity table in the statement,
    # widening `SELECTS_A_STAR` to any `*` would no longer show up here at all. The
    # join is what keeps the trap live — the identity table is named, its key is
    # the only thing read from it, and a `*` pattern that matched the
    # multiplication would fire.
    "CREATE VIEW public.{view} AS SELECT r.a * r.b AS scaled FROM public.{other} r"
    " JOIN public.{table} ui ON ui.id = r.id;",
    # E1-01's allow side, one per catch shape above. A view that joins a person
    # table and reads only the keys it joins on is what a read path *is*: the
    # carried entry on the reveal's composition says `section_roster` "hands
    # instructor-scoped code the `user_id` of every enrolled student… the key is
    # what makes a de-identified response addressable". The last of the three is
    # the reviewer fixture's own join line with the identity select removed, which
    # is the neighbouring shape the guard has to let through.
    "CREATE VIEW public.{view} AS SELECT ui.id, ui.user_id FROM public.{table} ui;",
    'CREATE VIEW public.{view} AS SELECT u.id FROM public."user" u;',
    "CREATE VIEW public.{view} AS SELECT r.id FROM public.{other} r\n"
    'JOIN "user" u        ON u.id = r.user_id;',
    # **The word boundary, which nothing else here distinguishes.** The bound-column
    # mechanism resolves a read by looking for `<token>.` where the token is a
    # person table or the alias it bound, and dropping the `\b` from that pattern
    # widens it to any token *ending* in one — `xu.note` reads as `u.note` and is
    # reported as `user.note`, on SQL that touches no person column at all. The
    # mutation battery found nothing telling the two versions apart.
    #
    # It fails in the direction that gets a guard weakened rather than the
    # direction that leaks, which is why the sample belongs on this side: an
    # author whose correct view is flagged for a read it never wrote repairs the
    # guard, and the cheapest repair is to stop looking at the alias at all. The
    # short alias is the realistic case — `u` beside `xu` is two joins in one
    # statement — and the same defect reaches any alias with a person table's
    # alias as its suffix.
    "CREATE VIEW public.{view} AS SELECT xu.note FROM public.{other} xu\n"
    'JOIN "user" u        ON u.id = xu.user_id;',
    # The allow half of the two shapes a security review added above.
    #
    # A whole-row read of a relation that holds **no** person: the widened
    # whole-row mechanism must stay off it, or the first legitimate `to_jsonb` in
    # the schema is a red and the repair is to narrow the mechanism back to marked
    # tables — which is the state the review found.
    "CREATE VIEW public.{view} AS SELECT to_jsonb(r) AS payload FROM public.{other} r;",
    # And a **quoted** relation whose name *ends* in a guarded one, beside a real
    # binding of that guarded table so that the read pattern actually runs. The
    # suffix is what makes this discriminate: with the quote allowed on the left
    # and no lookbehind to stop it, `"archived_user".note` matches — the optional
    # quote skips nothing, `user` matches the tail, the closing quote is consumed
    # and the dot follows — and every view naming an archive table is reported as
    # reading `user`. `"user_archive"` would not have shown this: what stops that
    # one is the `_` where a dot is required, which every version of the pattern
    # gets right.
    'CREATE VIEW public.{view} AS SELECT "archived_user".note FROM public."archived_user"\n'
    'JOIN public."user" u ON u.id = "archived_user".user_id;',
    # The clause words that may follow a relation and are not an alias for it. Each
    # of these is a line a real view writes, and each would be a false red if
    # `ALIAS_STOP_WORDS` lost a member: the word after the table would be read as
    # the row's own name, and every later use of that word as a read of the row.
    "CREATE VIEW public.{view} AS SELECT 1 FROM public.{table} WHERE id IS NOT NULL;",
    "CREATE VIEW public.{view} AS SELECT 1 FROM public.{table} GROUP BY 1;",
    "CREATE VIEW public.{view} AS SELECT ui.id FROM public.{table} ui ORDER BY ui.id LIMIT 1;",
    "CREATE VIEW public.{view} AS SELECT ui.id FROM public.{table} AS ui WHERE ui.id IS NOT NULL;",
    "CREATE VIEW public.{view} AS SELECT e.id FROM public.{other} e"
    " WHERE e.id IN (SELECT ui.id FROM public.{table} ui);",
)


def identity_findings(sql: str, vocabulary: IdentityVocabulary) -> tuple[IdentityFinding, ...]:
    """Every identity column a view created in `sql` reads, and which mechanism saw it.

    **What this cannot see**, stated here rather than discovered by a reviewer
    (`docs/MISTAKES.md` entry 14). It reads text, so:

      - **A chain of views.** `SELECT roster.leaked FROM public.some_view` reads
        identity if `some_view` does — this sees the name only if the column
        keeps it, and sees nothing at all if the intermediate view renames it.
        It does catch the case `pg_depend` missed in the other direction: a
        column-level dependency is recorded against the *intermediate* view,
        whose columns carry no marker, so the catalog sweep next door went green
        on a chain that preserves the name and this one goes red. **E1-01 closed
        the catalog side of that**, with a fixed-point fold over the one-hop
        dependency rows, so a chain is now caught there whether or not the name
        survives it — and is still not caught here.
      - **An alias assigned in the intermediate object**, for the same reason.
        An alias assigned *in this statement* is a different matter and is E1-01's
        `bound column` mechanism: `ui.display_name AS respondent_display_name` is
        read as a column of whatever `ui` was bound to, so the label the author
        chose decides nothing.
      - **A name that is never written**: dynamic SQL, a name assembled by
        `format()`, or a reference living only inside a string literal — all of
        which `without_quoted_text` removes on purpose, because the alternative
        direction flags correct SQL and gets the guard weakened.
      - **A comma join**: `FROM public.a, public.user_identity ui` names the
        second relation in a position `relation_patterns` does not read, so the
        star mechanism will not see it. The column mechanism is unaffected, since
        it does not care how the table was reached — and the whole-row mechanism
        over-reads it rather than under-reading it, which
        `identity_rows_read_whole` states as its known false positive.
      - **An identity column whose name is shared with a column holding no
        identity.** `IdentityVocabulary` says why those are subtracted and what
        it costs, and `EXPECTED_AMBIGUOUS_IDENTITY_NAMES` is what stops that
        subtraction growing silently.
      - **Any statement that is not a `CREATE … VIEW`**, and this is stated
        wider than it used to be because the narrow version was wrong. The
        residue is not "a function that reads identity"; it is every other kind
        of statement a file in this directory could hold. A function is the case
        the design intends — the reveal reads identity by design (ADR 0001,
        point 4), and what stands behind a *second* one is the grant model, which
        `test_identity_grants.py` asserts. But `CREATE TABLE public.x AS SELECT
        ui.identity_name …` is the same read into a table that outlives the
        transaction, and it is outside this rule too. That gap is deliberate for
        now rather than overlooked: widening the subject from views to every
        query-materialising statement changes what this guard is, and it belongs
        in a ticket that says so. Nothing else in the build looks at it.

    None of those makes the guard worthless and all of them make it partial. The
    one it is built for is the ordinary one: a file that joins `user_identity`
    and selects a name, sitting in the canonical directory, that no migration has
    run yet.
    """
    return tuple(
        IdentityFinding(mechanism.label, statement.name, column)
        for statement in view_bodies(sql)
        for mechanism in IDENTITY_MECHANISMS
        for column in mechanism.find(statement.text, vocabulary)
    )


def identity_pair(vocabulary: IdentityVocabulary) -> tuple[str, str]:
    """A real identity table and a real, unambiguous identity column it carries."""
    for table in sorted(vocabulary.carried):
        for column in vocabulary.carried[table]:
            if column in vocabulary.columns:
                return table, column
    pytest.fail(
        "No table in the migrated database carries an identity column this sweep can look for by "
        f"name. It found the identity tables {sorted(vocabulary.tables)}, and of the column names "
        f"on them {sorted(vocabulary.ambiguous)} were set aside as names that also belong to a "
        "column holding no identity.\n\n"
        "Two very different things look like this. Either the marker convention has stopped "
        "marking anything — `test_identity_column_marker.py` is where that is diagnosed — or every "
        "identity column in this schema is spelled with a name some other table also uses, in "
        "which case the name mechanism below can catch nothing and only a `SELECT *` over a marked "
        "table would be seen. The second is a real degradation of this guard and is worth saying "
        "out loud in a pull request rather than working around here."
    )


def sample_sql(template: str, vocabulary: IdentityVocabulary) -> str:
    """One template, spelled with this database's own identity table and column.

    Used for a sweep sample and for the finding a sample is required to produce,
    which are the same substitution over two different kinds of string. One
    function rather than two so that a sample and its expectation cannot come to
    disagree about what `{table}` means (`docs/MISTAKES.md` entry 13).
    """
    table, column = identity_pair(vocabulary)
    return template.format(table=table, column=column, view=CANARY_VIEW, other=CANARY)


@pytest.mark.invariant
def test_the_identity_sweep_holds_every_mechanism_this_module_requires() -> None:
    """The table of mechanisms is the required list — measured against a constant, not itself.

    This test exists because its absence was measured. The catch control below is
    parametrised, and it used to be parametrised over `IDENTITY_MECHANISMS`:
    deleting the `column` mechanism therefore did not fail its case, it *deleted*
    its case, and the controls reported success at the smaller size — 2 passed
    where there had been 3, which is the only trace such a deletion leaves and
    which nothing asserted. With that mechanism gone and a file planted under
    `views_sql/` selecting a marked identity column, the guard and both controls
    reported 3 passed while nothing in the tree was reading that column. A control
    whose inventory comes from the structure it guards cannot see that structure
    shrink.

    So the inventory is written down separately, and this test is the one
    assertion that compares the two. It is not parametrised, over anything.

    **The mutation it exists to survive**: delete a line from
    `IDENTITY_MECHANISMS` — with or without deleting that mechanism's shapes from
    `IDENTITY_SWEEP_MUST_CATCH`, since `REQUIRED_MECHANISM_LABELS` names it
    either way.
    **The near miss it tolerates**: adding a mechanism, which fails here until its
    label and at least one shape are written down too — deliberately, because a
    mechanism with no subject that certainly has it is the state entry 35 exists
    to stop.
    """
    provided = sorted(mechanism.label for mechanism in IDENTITY_MECHANISMS)
    assert provided == sorted(REQUIRED_MECHANISM_LABELS), (
        f"`IDENTITY_MECHANISMS` holds {provided} and this module requires "
        f"{sorted(REQUIRED_MECHANISM_LABELS)}.\n\n"
        "If a mechanism has been removed, everything it was the only guard on is now unguarded and "
        "no other test in this file will say so — the controls are asserted over the shapes in "
        "`IDENTITY_SWEEP_MUST_CATCH`, and `identity_findings` simply stops looking for what is no "
        "longer in the table. That was measured on this file: with the `column` mechanism deleted, "
        "a planted view file selecting a marked identity column left the guard and both controls "
        "green.\n\n"
        "Removing one is allowed and is a decision rather than a deletion: take its label out of "
        "`REQUIRED_MECHANISM_LABELS` and its shapes out of `IDENTITY_SWEEP_MUST_CATCH` in the same "
        "change, and say in the pull request which reads are no longer caught. Adding one fails "
        "here until it is written down with at least one subject that certainly has it."
    )

    for label in REQUIRED_MECHANISM_LABELS:
        shapes = [shape for shape in IDENTITY_SWEEP_MUST_CATCH if shape.label == label]
        assert shapes, (
            f"The {label!r} mechanism is required and `IDENTITY_SWEEP_MUST_CATCH` holds no shape "
            "for it, so nothing establishes that it can see anything. That is exactly the state "
            "`docs/MISTAKES.md` entry 35 records: a guard that only ever reports absence cannot "
            "tell you which of its mechanisms are still working."
        )

    unknown = sorted({shape.label for shape in IDENTITY_SWEEP_MUST_CATCH} - set(provided))
    assert not unknown, (
        f"`IDENTITY_SWEEP_MUST_CATCH` requires {unknown} to catch something and no mechanism in "
        "`IDENTITY_MECHANISMS` carries that label. The control below would fail on those shapes "
        "with a message about a blind pattern, which is the wrong diagnosis: the mechanism is not "
        "blind, it is absent."
    )


@pytest.mark.invariant
@pytest.mark.parametrize(
    "shape",
    IDENTITY_SWEEP_MUST_CATCH,
    ids=[
        f"{shape.label}-{position}"
        for position, shape in enumerate(IDENTITY_SWEEP_MUST_CATCH, start=1)
    ],
)
def test_the_view_file_identity_sweep_catches_the_shape_each_mechanism_names(
    shape: RequiredShape, identity_vocabulary: IdentityVocabulary
) -> None:
    """Each required shape is *found*, under the label required to find it — entry 35.

    A guard that enumerates the ways a thing can happen and only ever reports
    absence cannot tell you which of them it can still see. E0-33 shipped one:
    its sweep enumerated the currencies a privilege is held in, missed the one
    ADR 0001 deliberately uses, and 28 tests passed while a connection could read
    every student's name. So every shape in `IDENTITY_SWEEP_MUST_CATCH` is put
    through the sweep and has to come back reported.

    **It is parametrised over the inventory and not over the table**, which is
    the repair described on `IDENTITY_SWEEP_MUST_CATCH`: parametrised over the
    table, deleting a mechanism deleted its own cases and the suite passed at the
    smaller size. `test_the_identity_sweep_holds_every_mechanism_this_module_requires`
    is what makes that shrinkage visible; this test is what makes a mechanism that
    is present but blind visible.

    **It runs the whole path.** The sample goes through `identity_findings`,
    which walks the table of mechanisms, rather than through `find` — because a
    control asked of the probe directly stays green when the probe is deleted
    from the table, which is exactly how E0-33's first control came to guard
    nothing. **And the assertion is per label**, so no mechanism can answer for
    another one's blindness — a shape two mechanisms both see is harmless, which
    the comment on `IDENTITY_SWEEP_MUST_CATCH` records and which E1-01's last
    shape relies on: an aliased read of a real marked column is a `column`
    finding and a `bound column` finding at once, and each has to be made
    separately.

    **Marked `invariant` although it asserts nothing about the schema**, and the
    reason is mechanical: CI runs the invariant pass as `pytest -m invariant`, in
    isolation, so an unmarked control does not run there at all — and the guard
    it controls would then be an isolated green whose ability to see anything is
    unchecked.

    **The mutation it exists to survive**: break a pattern — drop the `,`
    alternative from `SELECTS_A_STAR`, drop the `\\b` from the column search, stop
    stripping comments — and, for a deleted mechanism, this goes red alongside the
    test above rather than instead of it.
    **The near miss it tolerates**: a new shape added for an existing mechanism,
    which extends this test rather than moving it.
    """
    table, column = identity_pair(identity_vocabulary)
    sample = sample_sql(shape.template, identity_vocabulary)
    findings = identity_findings(sample, identity_vocabulary)
    caught = {finding.mechanism for finding in findings}

    assert shape.label in caught, (
        f"The {shape.label!r} mechanism does not report {sample!r}, which reads "
        f"{sorted(sample_sql(entry, identity_vocabulary) for entry in shape.expected)} — either "
        f"`{column}` on `{table}`, which this database marks as identity, or a column of a table "
        "that holds a person, which the `bound column` mechanism refuses whatever it is called. "
        f"The sweep reported {sorted(caught)}, and `IDENTITY_MECHANISMS` holds "
        f"{sorted(mechanism.label for mechanism in IDENTITY_MECHANISMS)}.\n\n"
        "If the label is in that table, the mechanism has gone blind. If it is not, it has been "
        "deleted, and `test_the_identity_sweep_holds_every_mechanism_this_module_requires` is the "
        "test that says so in one line.\n\n"
        "`test_no_view_created_under_views_sql_names_an_identity_column` is built on this sweep and "
        "asserts an absence, so a blind mechanism there is indistinguishable from a directory of "
        "clean files — and this shape is written so that no other mechanism can answer for it."
    )
    named = {finding.column for finding in findings if finding.mechanism == shape.label}
    required = {sample_sql(entry, identity_vocabulary) for entry in shape.expected}
    assert required <= named, (
        f"The {shape.label!r} mechanism reports {sample!r} but names {sorted(named)} "
        f"rather than {sorted(required)}. E0-34's second criterion is about the message and not "
        "only about the red: the same file already fails the schema-qualification sweep, whose "
        "message is about missing `public.` prefixes, so a failure that does not name the "
        "identity column is repaired by adding four prefixes with the join left in place.\n\n"
        "What a shape requires is written on the shape itself and defaults to the identity column "
        f"this database carries, which is `{column}` on `{table}`. The `bound column` mechanism "
        "names `table.column` instead, because the column it catches may exist in no schema at "
        "all — `display_name` is the reviewer fixture's, and a bare column name that means "
        "nothing on its own would send a reader looking for a column rather than for a join."
    )


@pytest.mark.invariant
def test_the_view_file_identity_sweep_allows_the_shapes_that_read_no_identity(
    identity_vocabulary: IdentityVocabulary,
) -> None:
    """The other half: every line this repository really writes stays green.

    A tripwire that fires on correct SQL is repaired by weakening it, and the
    casualty is usually the guard rather than the file. So each sample here is a
    line that reads no identity and that somebody has a reason to write, and the
    first one is the reason `view_bodies` exists at all: ADR 0001 point 4 gives
    Care its access through one `SECURITY DEFINER` function that returns identity
    and audits itself, ADR 0041 ships that function's SQL in this same directory,
    and a file-grained rule would be red on it on the day it landed. An exemption
    granted on the day a guard ships is an exemption nobody ever revisits.

    The rest are near misses the four patterns have to get right: `count(*)`,
    which is what an enrollment-count view is made of; a multiplication; a
    grant, a revoke and a comment naming the identity table; a column whose name
    merely begins with an identity column's; a join to an identity table that
    reads no column of it; the same name inside a comment and inside a string
    literal; the clause words that may follow a relation without being an alias
    for it, which the whole-row mechanism brought; and — since E1-01 — a view
    that joins a person table and reads the keys it joined on. That last pair is
    the one that decides whether this guard can live with a real read path at
    all: a rule that flagged `ui.user_id` would be red on `section_roster`, and
    the carried entry says that key is what makes a de-identified response
    addressable.

    The clause-word group is the one to add to when a real file goes unexpectedly
    red: `FROM public.person WHERE …` binds no alias, and an `ALIAS_STOP_WORDS`
    missing a member reads the clause word as the row's name and reports every
    later use of it.

    **The mutation it exists to survive**: widening `SELECTS_A_STAR` to any `*`,
    which makes `count(*)` an identity read; dropping the word boundary from the
    column search, which makes `{column}_hash` one; dropping the dollar-quote and
    view-body handling, which makes the reveal function one; emptying
    `ALIAS_STOP_WORDS`, which makes `WHERE` a row reference; emptying
    `JOIN_KEY_COLUMNS`, which makes every join to a person table a person read;
    dropping the left boundary from the bound-column read pattern, which makes an
    alias *ending* in a person table's alias one — measured surviving everything
    else in this module, which is why the two-alias sample and the
    `"archived_user"` sample are here; and widening the whole-row mechanism to any
    `to_jsonb`, which makes a row of a table holding no person one.
    **The near miss it tolerates**: none — that is what this test is.
    """
    assert IDENTITY_SWEEP_MUST_ALLOW, (
        "There is no sample of a shape this sweep must allow, so nothing here establishes that it "
        "discriminates. A guard that flags everything passes its catch tests perfectly."
    )

    for template in IDENTITY_SWEEP_MUST_ALLOW:
        sample = sample_sql(template, identity_vocabulary)
        findings = identity_findings(sample, identity_vocabulary)
        assert not findings, (
            f"The identity sweep reports {[finding.column for finding in findings]} in "
            f"{sample!r}, which reads no identity column. It is a grant, a comment, a function "
            "body, a count, or a column whose name only begins the same way — and every one of "
            "them is a line `backend/app/views_sql/` either already holds or would hold next.\n\n"
            "A guard that flags correct SQL is repaired by weakening it, and the first exemption "
            "somebody reaches for is a file name on a list. The exemption this sweep is built "
            "with is a property instead: the rule is about views, and the reveal function that "
            "reads identity by design (ADR 0001, point 4) is not one."
        )


@pytest.mark.invariant
def test_the_bound_column_mechanism_guards_every_person_table_this_module_requires(
    identity_vocabulary: IdentityVocabulary,
) -> None:
    """The third inventory: which tables a read of *any* column is refused on.

    `REQUIRED_MECHANISM_LABELS`' argument, applied to the set E1-01 added. The
    mechanism reads `PERSON_TABLES` out of `test_identity_column_marker.py`, which
    is where the convention lives and where a widening has to happen for every
    reader to get it — and a required list read from the same place could not
    notice that set getting smaller. Deleting `"user"` from it there is one word.

    **The second assertion is why `user` has to be in the list at all**, and it is
    a measurement rather than a restatement: `user` carries no marked column, so
    it is absent from `tables` and the `star`, `whole row` and `column`
    mechanisms have nothing to say about any column it holds. That absence is
    deliberate — ADR 0001 puts the key and the platform reference there precisely
    so that they are not identity, and `marked` next door refuses a table comment
    on `user` on that ground. The consequence is the carried entry's second blind
    spot: `user.lms_user_id` is the LTI `sub`, and a view returning it beside a
    comment lets an instructor resolve a named student in the LMS in one step
    with every other guard in this file green.

    **The mutation it exists to survive**: removing a table from `PERSON_TABLES`,
    with or without removing the shapes that read it — this names it either way.
    **The near miss it tolerates**: a new person table added there, which fails
    here until it is written down, deliberately, because a table added to the
    guarded set with no shape that certainly reads it is the state entry 35
    exists to stop.
    """
    guarded = sorted(identity_vocabulary.guarded)
    assert guarded == sorted(REQUIRED_GUARDED_PERSON_TABLES), (
        f"The `bound column` mechanism guards {guarded} and this module requires "
        f"{sorted(REQUIRED_GUARDED_PERSON_TABLES)}. The set it reads is `PERSON_TABLES` in "
        "`test_identity_column_marker.py`.\n\n"
        "If a table has been removed there, every column of it is now readable by any view with "
        "nothing in this repository saying so — the marker-based mechanisms are about columns that "
        "hold identity, and the whole point of this one is the table whose columns do not. Removing "
        "one is allowed and is a decision rather than a deletion: take it out of this list in the "
        "same change, with the shapes that read it, and say in the pull request which reads are no "
        "longer caught."
    )
    assert "user" not in identity_vocabulary.tables, (
        "`user` now carries a marked identity column, so it is inside the marker-based mechanisms' "
        f"reach as well as this one's; the marked tables are {sorted(identity_vocabulary.tables)}. "
        "That contradicts ADR 0001's split — `user` holds the LMS key and the platform reference, "
        "`user_identity` holds the name and the email — and "
        "`test_the_marker_does_not_reach_columns_that_hold_no_identity` next door is where it is "
        "diagnosed. Read that first: this test is not the place to repair it, and the `bound "
        "column` mechanism is not made redundant by it either, because a marked column is still "
        "only the columns somebody marked."
    )


@pytest.mark.invariant
def test_every_join_key_the_bound_column_mechanism_allows_is_a_structural_key(
    migrated_engine: Any, identity_vocabulary: IdentityVocabulary
) -> None:
    """The allow-list, held to what an allow-list is for: joining, never reading a person.

    `JOIN_KEY_COLUMNS` is the one place this guard can be weakened without
    deleting anything. It is a list of column names a view may read off a table
    that holds a person, so a name added to it is a read nobody will be told
    about again — and the name somebody would add is exactly the one the carried
    entry names, because `user.lms_user_id` is what a view wants when a screen
    needs to identify a row in the LMS.

    So the list is required to be what it claims: every entry has to be a primary
    key or a column carrying a foreign key, on at least one of the tables the
    mechanism guards. `lms_user_id` is neither — it is a value the platform sent,
    marked `lms_` for ownership by ADR 0014 and by nothing for identity — so
    adding it turns this red on an unmutated schema, which is the only shape that
    makes the list load-bearing rather than decorative.

    **The mutation it exists to survive**: adding `lms_user_id`, or any other
    column name, to `JOIN_KEY_COLUMNS` in `test_identity_column_marker.py`.
    **The near miss it tolerates**: a genuine new key — a second foreign key
    landing on a person table with E1's roster sync — which is added to the list
    with the sentence that sanctions it and passes here.
    """
    assert identity_vocabulary.join_keys, (
        "`JOIN_KEY_COLUMNS` is empty, so the `bound column` mechanism forbids every read of every "
        "person table including the keys a read view joins on. That is not a stricter guard, it is "
        "a red on `section_roster` and on every view like it, and the repair somebody reaches for "
        "under that pressure is to widen the rule back out to marked columns only."
    )

    inspector = inspect(migrated_engine)
    present = set(inspector.get_table_names())
    absent = sorted(identity_vocabulary.guarded - present)
    assert not absent, (
        f"{absent} are guarded by the `bound column` mechanism and are not tables in the migrated "
        "database, so no view can read them and this rule guards nothing on them. Either the "
        "schema has moved or `PERSON_TABLES` next door names something that no longer exists."
    )

    structural: dict[str, list[str]] = {}
    for table in sorted(identity_vocabulary.guarded):
        keys = set((inspector.get_pk_constraint(table) or {}).get("constrained_columns") or [])
        keys |= {
            column
            for key in inspector.get_foreign_keys(table)
            for column in key.get("constrained_columns") or []
        }
        for column in sorted(identity_vocabulary.join_keys & keys):
            structural.setdefault(column, []).append(table)

    unstructural = sorted(identity_vocabulary.join_keys - set(structural))
    assert not unstructural, (
        f"{unstructural} are allowed to be read off `{sorted(identity_vocabulary.guarded)}` and "
        "are the primary key of none of them and a foreign key on none of them. What the mechanism "
        f"does recognise as structural is {structural}.\n\n"
        "A join key is a column that names a *row*: it is what a read view joins on, and reading "
        "one tells you which row without telling you whose. A column on a person table that is "
        "neither a key nor a reference is a fact about the person — `user.lms_user_id` is the LTI "
        "`sub`, which resolves that person at the platform in one step, and ADR 0014's `lms_` "
        "prefix marks where the value came from rather than what it holds.\n\n"
        "If the entry names no column at all, it is dead: it permits nothing and it will permit "
        "the first column that ever takes the name. If it names a real column that is genuinely a "
        "key, this test is where the argument goes, and the pull request that makes it says which "
        "reads are no longer caught."
    )


@pytest.mark.invariant
def test_the_identity_vocabulary_subtracts_only_the_names_this_module_expects(
    identity_vocabulary: IdentityVocabulary,
) -> None:
    """The second inventory: what the name sweep has stopped looking for.

    `IdentityVocabulary` subtracts an identity column name that a column holding
    no identity also uses, because in text the two are the same word and a guard
    that reds on `SELECT i.name FROM public.institution i` gets weakened rather
    than fixed. The subtraction is computed from the schema, so it grows on its
    own — and it grows *silently*: `columns` stays non-empty on the names that
    remain, every control stays green because their shapes are built from a name
    that survived, and the only place `ambiguous` is printed is a message that
    fires when `columns` is empty. A green run leaves no trace of a name having
    dropped out.

    This is `REQUIRED_MECHANISM_LABELS`' argument applied to the one inventory
    that did not have a written-down twin. The set is empty today, measured
    rather than assumed.

    **The mutation it exists to survive**: add an unmarked column that shares a
    marked column's name — a `person.email` beside an `institution.email` — which
    takes `email` out of the sweep with nothing else in the suite moving.
    **The near miss it tolerates**: a new *marked* identity column, which is not
    ambiguous and changes nothing here; and a new unmarked column whose name no
    marked column shares.
    """
    subtracted = sorted(identity_vocabulary.ambiguous)
    assert subtracted == sorted(EXPECTED_AMBIGUOUS_IDENTITY_NAMES), (
        f"The identity sweep is not looking for {subtracted}, and this module expects it not to be "
        f"looking for {sorted(EXPECTED_AMBIGUOUS_IDENTITY_NAMES)}.\n\n"
        "A name is dropped when a column holding no identity shares it, which makes the two "
        "indistinguishable in SQL text. Every name in the first list and not the second is a "
        "column the guard has stopped catching by name — it is still caught if a view stars its "
        "table or reads its row whole, and not otherwise.\n\n"
        "Two repairs, and they are different decisions. If the column that shares the name holds "
        "identity too, marking it is the fix and the name comes back. If it genuinely does not — "
        "`institution.name` is the name of an institution — then add the name to "
        "`EXPECTED_AMBIGUOUS_IDENTITY_NAMES` and say in the pull request which reads are no longer "
        "caught by name. What must not happen is the list growing with nobody noticing, which is "
        "exactly what this schema does on its own as it gains tables."
    )


@pytest.mark.invariant
def test_no_view_created_under_views_sql_names_an_identity_column(
    identity_vocabulary: IdentityVocabulary,
) -> None:
    """E0-34: a view file that reads identity fails **on that ground**, executed or not.

    `test_no_view_reads_a_column_the_identity_marker_names` in
    `test_identity_column_marker.py` is the same rule read out of `pg_depend`, and
    it can only see a view a migration has already created. `backend/app/views_sql/`
    is a directory of files, and nothing read them looking for identity: a file
    that joins `user_identity` and selects a name sits there and passes that
    invariant **vacuously** until somebody appends its name to a revision's
    `SCRIPTS` tuple, in an unrelated ticket, with no grant consulted on the way.
    No grant is consulted because these views run with their owner's rights and
    `security_invoker` is off — which is deliberate and load-bearing, since it is
    what lets `pulse_app` read `role_assignment` and the containment tables while
    holding no grant on any of them, and whose consequence is that **the grant
    model does not protect the view files themselves**.

    Marked `invariant` for the same reason its `pg_depend` twin is: a view runs
    with its owner's privileges rather than its reader's, so this is the one route
    to identity that ADR 0001's grants cannot close, and in a green checkmark a
    skipped assertion and a passing one are the same tick.

    **The mutation it exists to survive**: plant a file under `views_sql/` that
    creates a view joining an identity table and selecting a marked column, and
    leave it out of every revision. This goes red naming the column; nothing else
    in the tree moves. It survives, too, the same file with every relation
    correctly schema-qualified — which is the invited repair when the
    qualification sweep is the only thing that fires.
    **The near miss it tolerates**: a view file that names an identity *table* and
    reads no column of it; the reveal function, which reads identity by design;
    and the grants file, which names both the identity table and every view in
    order to grant on them.

    **The two halves of the pair disagree about the first of those, on purpose.**
    A view that names a marked table and reads nothing from it is allowed here and
    is flagged by `test_no_view_reads_a_whole_row_of_a_table_the_identity_marker_
    names` next door, because Postgres records that reference at the same grain as
    a genuine whole-row read and the catalog cannot tell the two apart. Text can:
    a bound alias used only with a `.` is a column read. The stricter half wins
    the argument if it ever fires, and that test's docstring is where the decision
    would be recorded.

    **What it cannot see** is on `identity_findings`, beside the code that
    decides it rather than here.
    """
    files = view_sql_files()
    assert files, (
        f"{VIEWS_SQL_DIR} holds no `.sql` file, so this guard swept nothing and would report "
        "success over a directory that could contain anything. "
        "`test_every_read_view_is_created_from_a_sql_file_under_views_sql` is where an empty or "
        "missing directory is diagnosed."
    )
    assert identity_vocabulary.tables, (
        "The migrated database reports no table carrying an identity column, so this sweep has "
        "nothing to look for and would pass over a file that selects every name in the schema. "
        "`test_identity_column_marker.py` is where a marker convention that has stopped marking "
        "anything is diagnosed."
    )
    assert identity_vocabulary.columns, (
        "No identity column in this schema has a name this sweep can look for: the marked columns "
        f"are on {sorted(identity_vocabulary.tables)} and the names "
        f"{sorted(identity_vocabulary.ambiguous)} were set aside because a column holding no "
        "identity shares each of them. With none left, the name mechanism can catch nothing and "
        "only a `SELECT *` would be seen — which is a real degradation of this guard rather than "
        "a passing sweep."
    )

    sources = {path: path.read_text(encoding="utf-8") for path in files}

    # The identity finding comes first, and the order is the fix for a defect this
    # test had. The canaries below used to run ahead of it, so one view statement
    # that tripped a canary made the whole directory's identity findings
    # unreachable in that run — and the canary's own message talked about quoting
    # rather than about identity. That is criterion 2's failure shape reproduced
    # inside the guard written to eliminate it: a red pointing away from the
    # defect. An empty `offenders` still means nothing until the canaries have
    # run, and they run immediately after.
    offenders: dict[str, list[str]] = {}
    for path, source in sources.items():
        findings = identity_findings(source, identity_vocabulary)
        if findings:
            offenders[path.name] = sorted(
                f"{finding.view} reads {finding.column} ({finding.mechanism})"
                for finding in findings
            )

    # **The operand is a bool on purpose, and it is a repair rather than a
    # style.** Written as `assert not offenders`, pytest's assertion rewriting
    # appends the repr of the dict to the exception, so the identity column
    # appears in `str(failure.value)` whatever this message says — and both
    # planted-file demonstrations at the foot of this module
    # (`test_a_view_sql_file_reading_a_marked_identity_column_fails_the_guard`
    # and `test_the_schema_qualification_failure_does_not_hide_the_identity_
    # failure`) exist to establish that this message names it. With a plain bool
    # there is nothing for the rewriter to expand: the explanation is
    # `assert False`, and the findings printed below are the only place the
    # column is named. The same fix, in the same shape, as `agrees` in
    # `tests/integration/test_identity_grants.py`, where the mutation battery
    # measured it (E1-01, deferral item 3).
    clean = not offenders
    assert clean, (
        f"These files under {VIEWS_SQL_DIR} create a view that reads an identity column: "
        f"{offenders}.\n\n"
        "SPEC §8 requires the instructor and leadership read paths to go through views that "
        "'structurally cannot join to `user` identity columns — enforced in the database, not just "
        "the application', and §4.1 makes the resulting rules automated assertions rather than "
        "conventions. A view is read with its **owner's** privileges rather than its reader's, so "
        "the grants ADR 0001 writes do not apply to it: `CREATE VIEW … SELECT ui.<a name> …` "
        "followed by `GRANT SELECT ON that view TO pulse_app` puts a name on an instructor screen "
        "with every one of those grants still intact.\n\n"
        "**This is asserted over the file rather than over the database on purpose.** The "
        "`pg_depend` sweep in `test_identity_column_marker.py` sees only views a migration has "
        "executed, so the same join sitting in a file that no revision names yet passes it "
        "vacuously — and goes live the day somebody adds the file to a `SCRIPTS` tuple in a ticket "
        "about something else.\n\n"
        "**A `bound column` finding names a table and a column together** — "
        "`user_identity.display_name` rather than `display_name` — because it is not a finding "
        "about the column's name at all. It says that the statement binds a table holding a "
        "person and then reads something off that binding which is not one of the keys a view "
        "joins on, whatever the column is called and whether or not this schema has it. The "
        "repair is to stop reading it, never to rename it: the label is what the guard was "
        "measured green against.\n\n"
        "**A `whole row` finding may be an old-style comma join** — "
        "`FROM public.a, public.user_identity ui` — which reads no identity and is reported anyway, "
        "because a relation bound by a comma is bound by no keyword this sweep can see. Rewriting "
        "it as an explicit `JOIN … ON` is the repair, and `identity_rows_read_whole` says why that "
        "is the direction chosen. Every other finding is a read.\n\n"
        "If the column named above is genuinely not a person's identity, the fix is at the marker "
        "convention in `test_identity_column_marker.py` rather than here, so that every reader of "
        "that enumeration changes together."
    )

    defined = [
        (path, statement) for path, source in sources.items() for statement in view_bodies(source)
    ]
    assert defined, (
        f"No file under {VIEWS_SQL_DIR} contains a statement that creates a view, so this guard "
        f"read {[path.name for path in files]} and swept nothing in them. Either every `CREATE "
        "VIEW` has moved into an `op.execute` in a revision — which ADR 0041 exists to forbid, and "
        "which `test_every_read_view_is_created_from_a_sql_file_under_views_sql` diagnoses — or "
        "the statement sweep has gone blind, in which case this test is green against a file that "
        "selects every identity column in the schema."
    )

    # The disappearance canary, and it is a comparison rather than a guess.
    # `objects_standing_after` reads the same files with comments stripped and
    # nothing else; `view_bodies` reads them through `without_quoted_text`. So a
    # view the first sees and the second does not is text that the quote scanner
    # swallowed — an unterminated literal or dollar tag blanking the rest of a
    # file is the way that happens, and it is the one way a statement can vanish
    # rather than merely be cut short. A vanished statement is invisible to every
    # canary phrased over the statements that *were* found.
    swept = {statement.name for _, statement in defined}
    standing = objects_standing_after(sources.values(), VIEW)
    vanished = sorted(standing - swept)
    assert not vanished, (
        f"{vanished} are created as a view by a file under {VIEWS_SQL_DIR} and the identity sweep "
        f"read no statement for them; it read {sorted(swept)}.\n\n"
        "The two readings differ in exactly one thing: this sweep blanks string literals and "
        "dollar-quoted bodies before looking, and `objects_standing_after` does not. So the text "
        "of that statement was consumed as if it were quoted — an unterminated literal or an "
        "unclosed `$tag$` earlier in the file will blank everything after it. The consequence is "
        "the one this test exists to prevent: the statement is not swept at all, and a `SELECT "
        "ui.identity_name` inside it is reported by nobody."
    )

    # Truncation, as opposed to disappearance: a statement found, whose query is
    # blank. Deliberately not "contains the word `select`" — `CREATE VIEW x AS
    # TABLE public.y` and `AS VALUES (…)` are both views, both read every column
    # of what they name, and a canary demanding `select` would have gone red on
    # them with a message about quoting while the identity read went unmentioned.
    cut_short = [
        f"{path.name}: {statement.name}"
        for path, statement in defined
        if not statement.query.strip()
    ]
    assert not cut_short, (
        f"{cut_short} were read as view definitions with no query text after the create clause. "
        "The statement is being cut short at a `;` — the likeliest cause is a quoting construct "
        "this sweep resolved differently from Postgres. This is the canary for the reading rather "
        "than for the files (`docs/MISTAKES.md` entry 3): with the statement text empty, every "
        "mechanism above searched an empty string and found nothing."
    )


def plant_view_sql_file(directory: Path, sql: str) -> Path:
    """Write one `.sql` file into `directory` and return its path."""
    path = directory / PLANTED_VIEW_FILE
    path.write_text(sql, encoding="utf-8")
    return path


def mentions(message: str, word: str) -> bool:
    """Does `message` name `word` as a whole word?

    A whole word rather than a substring, because both tests below ask whether a
    *failure message* names a column, and one of them asks whether the other
    message does **not**. A substring check answers that second question wrongly
    for any column whose name is a fragment of ordinary English — the
    qualification sweep's own message contains the sentence "every relation a
    view or function names", so a column called `name` would appear to be named
    there by a guard that never mentioned it.
    """
    return re.search(rf"\b{re.escape(word)}\b", message) is not None


@pytest.mark.invariant
def test_a_schema_qualified_view_file_that_reads_identity_fails_and_names_the_column(
    tmp_path: Path,
    monkeypatch: Any,
    migrated_engine: Any,
    identity_vocabulary: IdentityVocabulary,
) -> None:
    """E0-34's first criterion, with the two escape routes closed one at a time.

    The planted file reads an identity column and is **correctly
    schema-qualified**, so `test_every_relation_a_view_sql_file_names_is_schema_
    qualified` has nothing to say about it. That is the point: it establishes that
    the identity guard is a rule of its own rather than a second reading of the
    prefix rule, and it is the state the invited repair leaves behind — add four
    `public.` prefixes to the file that tripped the qualification sweep and this
    is what remains.

    It is also **in no `SCRIPTS` tuple and in no database**, which is the other
    half of the criterion. Reachability is what the existing checks test and
    reachability is what changes in an unrelated ticket, so the guard's file
    discovery is a glob over the directory rather than a list read out of a
    revision — and this test is the tripwire on that: a guard narrowed to the
    files a revision names would go green here, since nothing names this one.

    **Marked `invariant` because of what runs in the isolated pass.** CI runs
    `pytest -m invariant` on its own, and this test and its sibling are the only
    two that exercise file *discovery* and file *reading* at all — the guard
    itself is asserted over whatever `view_sql_files` returns. Unmarked, the
    mutation named below could be made and the invariant pass would stay green
    with the guard blind to exactly the unexecuted file it was built for.

    **The mutation it exists to survive**: narrowing `view_sql_files` or the guard
    to files a revision executes, and any repair of the guard that makes it
    depend on the view existing in `pg_class`.
    **The near miss it tolerates**: the real directory, which this test does not
    touch — `VIEWS_SQL_DIR` is redirected at the module for the duration and the
    planted file is written under `tmp_path`, so nothing is created, changed or
    left behind in `backend/`.
    """
    table, column = identity_pair(identity_vocabulary)
    planted = (
        "-- Planted by the test suite. No revision names this file and no database has run it.\n"
        f"CREATE VIEW public.{PLANTED_VIEW} AS\n"
        f"SELECT ui.{column} AS leaked\n"
        f"FROM public.{table} ui;\n"
    )
    path = plant_view_sql_file(tmp_path, planted)
    monkeypatch.setattr(sys.modules[__name__], "VIEWS_SQL_DIR", tmp_path)

    assert view_sql_files() == [path], (
        f"With the view directory redirected to {tmp_path}, `view_sql_files` reports "
        f"{view_sql_files()} rather than the one planted file. The redirection has not taken "
        "effect, so everything below is being asserted about the real directory and the planted "
        "file is not under test at all."
    )
    with migrated_engine.connect() as connection:
        views = read_views(connection)
    assert PLANTED_VIEW not in views, (
        f"`{PLANTED_VIEW}` exists as a view in the migrated database. It should exist only as text "
        "in a file no revision names — that is the whole subject of this test, and a real view by "
        "that name means an earlier run left one behind."
    )

    try:
        test_every_relation_a_view_sql_file_names_is_schema_qualified(migrated_engine)
    except AssertionError as refused:
        pytest.fail(
            "The planted file names every relation as `public.<name>` and the schema-qualification "
            f"sweep flagged it anyway: {refused}\n\nThis test needs that sweep silent, so that the "
            "red below is demonstrably the identity rule and not the prefix rule wearing another "
            "name. Read the sweep's message first — it is a fact about `unqualified_references` "
            "rather than about the identity guard."
        )

    with pytest.raises(AssertionError) as failure:
        test_no_view_created_under_views_sql_names_an_identity_column(identity_vocabulary)

    assert mentions(str(failure.value), column), (
        f"The identity guard failed on the planted file and its message does not name `{column}`, "
        f"the identity column the file reads. What it said: {failure.value}\n\n"
        "The message is the criterion, not a courtesy. A failure that names the file but not the "
        "column is repaired by looking at the file, and the same file fails the "
        "schema-qualification sweep with a message about `public.` prefixes — so the repair that "
        "presents itself is four prefixes, after which the identity join is untouched and the "
        "pipeline is green.\n\n"
        "It is also possible this assertion caught a *different* failure inside the guard — an "
        "empty directory, an empty vocabulary — in which case the planted file was never swept and "
        "this test would otherwise have passed for a reason unrelated to what it asserts "
        "(`docs/MISTAKES.md` entry 3). The message above says which."
    )


@pytest.mark.invariant
def test_the_schema_qualification_failure_does_not_hide_the_identity_failure(
    tmp_path: Path,
    monkeypatch: Any,
    migrated_engine: Any,
    identity_vocabulary: IdentityVocabulary,
) -> None:
    """E0-34's second criterion: one file, both reds, and the identity one names the column.

    This is the finding two reviewers reached from two directions. A file that
    joins an identity table unqualified and selects a name fails
    `test_every_relation_a_view_sql_file_names_is_schema_qualified`, whose message
    is about missing `public.` prefixes and says nothing about identity. If that
    is the only red, the author adds four prefixes, the pipeline goes green, and
    the identity join has never been mentioned — a red whose message points away
    from the defect is worse than no red, because it spends the one moment
    somebody was looking.

    So the planted file trips both, and this test asserts three things about the
    pair: the qualification sweep does fail on it, the identity guard fails on it
    *separately*, and the identity column's name appears in the second message and
    not in the first. The third is what makes "does not mask it" checkable rather
    than a claim — two failures are two lines of pytest output, and the one that
    names the column is the one that survives the prefix repair.

    **The mutation it exists to survive**: folding the identity finding into the
    qualification sweep's message, or ordering the guard so that it stops at the
    first offending file. **The near miss it tolerates**: the qualification sweep
    being repaired or renamed — this test calls it by name and would fail loudly
    rather than silently, which is the right direction for a test whose whole
    subject is a message.
    """
    table, column = identity_pair(identity_vocabulary)
    planted = f"CREATE VIEW {PLANTED_VIEW} AS\nSELECT ui.{column} AS leaked\nFROM {table} ui;\n"
    plant_view_sql_file(tmp_path, planted)
    monkeypatch.setattr(sys.modules[__name__], "VIEWS_SQL_DIR", tmp_path)

    with pytest.raises(AssertionError) as qualification:
        test_every_relation_a_view_sql_file_names_is_schema_qualified(migrated_engine)
    with pytest.raises(AssertionError) as identity:
        test_no_view_created_under_views_sql_names_an_identity_column(identity_vocabulary)

    assert PLANTED_VIEW_FILE in str(qualification.value), (
        "The schema-qualification sweep failed, and its message does not name "
        f"`{PLANTED_VIEW_FILE}`: {qualification.value}\n\nIt has failed for some other reason, so "
        "the two failures below are not about one file and this test is not demonstrating what it "
        "claims to."
    )
    assert mentions(str(identity.value), column), (
        f"The identity guard's message does not name `{column}`: {identity.value}\n\nBoth guards "
        "fired on this file. If neither message names the identity column, the repair that "
        "presents itself is the one the qualification message asks for — four `public.` prefixes — "
        "and the identity join survives it untouched."
    )
    assert not mentions(str(qualification.value), column), (
        f"The schema-qualification failure names `{column}`, the identity column. That is not the "
        "defect this test is guarding against, so read it before changing anything: this "
        "assertion is what establishes that the *identity* red is the only place the column is "
        f"named, and it is written on the assumption that `{column}` is not a substring of the "
        f"relation name `{table}`, of `{PLANTED_VIEW_FILE}`, or of the temporary directory this "
        "test plants into. If it is, this assertion is the wrong shape and needs saying so rather "
        "than deleting."
    )
