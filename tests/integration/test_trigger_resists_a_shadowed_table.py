"""The supervision trigger cannot be aimed at a table the writer chose — ticket E0-09.

A generic security review of this ticket found a HIGH, and this module is what
holds the fix. The trigger [ADR 0027](../../docs/adr/0027-supervision-edges-are-policed-by-one-row-level-trigger.md)
adds named `role_assignment` without a schema, and **Postgres searches the
temporary schema first for relation names whether or not `pg_temp` appears in
`search_path`** — being unlisted is what puts it first. So a writer who creates
`pg_temp.role_assignment` and then writes `public.role_assignment` had every
guard query, and the advisory-lock key with them, resolve against an empty shadow
table of their own making. Measured on the pinned Postgres as a `NOSUPERUSER`
role with no `CREATE` on `public`: a two-assignment cycle and an edge into a
`CARE` assignment both committed, seconds after the same writes had been refused.

The fix ships two mechanisms deliberately, and ADR 0027 records why: every
relation is schema-qualified, *and* the function carries
`SET search_path = pg_catalog, public, pg_temp`. The qualification survives
somebody dropping the `SET`; the `SET` survives somebody adding an unqualified
reference.

**That is why there are three tests here rather than one.** ADR 0027's own
measurement table says either mechanism closes the hole alone, so a behavioural
test cannot tell you which one did the work — remove the qualifications and the
`SET` still refuses the write, remove the `SET` and the qualifications still do.
This is `docs/MISTAKES.md` entry 3's second rule exactly: where two rules can
refuse the same row, assert that each rule is *stated*, out of what the catalog
reports, as well as that the row is refused. Both, not either. So:

  - the behavioural test holds the property — with a shadow in place, the cycle
    is still refused — and goes red only when **both** mechanisms are gone, which
    is the state that is actually exploitable;
  - one catalog test holds the `search_path`, and in particular that `pg_temp` is
    named **last**. A `search_path` that merely omits it is the usual advice and
    is the variant ADR 0027 measured as vulnerable;
  - one catalog test holds the qualification, which is the half the behavioural
    test cannot see while the `SET` is there.

**Nothing here reads the migration.** The trigger's function is discovered
through `pg_trigger`, so this module knows no name the implementation chose.

**The shadow is built with `LIKE public.role_assignment` rather than a hand-written
column list**, which is a deliberate departure from the sketch in ADR 0027, and
the reason is `docs/MISTAKES.md` entry 3. The guard queries select from whatever
`role_assignment` resolves to; if the shadow were missing a column one of them
names, the *vulnerable* function would fail with "column does not exist", the
write would be refused, and the behavioural test below would pass green against
the exact defect it exists to catch. `LIKE` copies the column list from the real
table and keeps doing so as the table changes, so a refusal here is a refusal by
the guard.

**One limit, stated rather than implied.** These tests connect as the bootstrap
identity, because that is the identity `db_session` provides
(`tests/fixtures/database.py` says why: the application role holds only
`CONNECT`, so it can seed nothing). The
vulnerability is reachable by a far weaker role — creating a temporary table needs
only the `TEMPORARY` privilege, which Postgres grants to `PUBLIC` — and ADR 0027
reproduced it that way. What this module asserts is that the guard resists the
shadow, which does not depend on who created it; what it does not assert is the
privilege boundary itself. E0-10 is the ticket that grants `pulse_app` the DML
that would make this reachable in a deployment.
"""

import re
from typing import Any

import pytest
from sqlalchemy import Column, MetaData, Table, text

pytestmark = pytest.mark.integration

ASSIGNMENTS = "role_assignment"

# The attack, as one statement. Written as a literal rather than assembled from a
# constant so that it reads here exactly as it would in an attacker's session,
# and so that no test of this project builds SQL out of a name.
CREATE_SHADOW = "CREATE TEMPORARY TABLE role_assignment (LIKE public.role_assignment)"

# How each name resolves for *this session*. `to_regclass` answers NULL rather
# than raising for a name that resolves to nothing, so a missing table is a
# failed assertion naming it rather than an error inside the query.
RESOLVE_BOTH = (
    "SELECT to_regclass('role_assignment')::oid, to_regclass('public.role_assignment')::oid"
)

# Every non-internal trigger on the table, with the function behind it. Discovered
# rather than named: no ticket spells the trigger or its function, and naming one
# here would make the implementer build to this file.
TRIGGER_FUNCTIONS = """
    SELECT DISTINCT p.oid::regprocedure::text, p.prosrc, p.proconfig
    FROM pg_trigger t
    JOIN pg_proc p ON p.oid = t.tgfoid
    WHERE t.tgrelid = to_regclass('public.role_assignment')
      AND NOT t.tgisinternal
"""

# Where a relation name is a relation *lookup*, in the two forms the review found
# in this function: a table named after a SQL clause, and a name cast to
# `regclass` for the advisory-lock key. Both allow an optional schema, and the
# test requires that schema to be `public`.
#
# The clause form is anchored on the keyword rather than on the bare word so that
# `role_assignment` inside an error message cannot match. The literal form
# requires the closing quote immediately after the name, for the same reason: it
# matches `'role_assignment'::regclass` and cannot match
# `RAISE EXCEPTION 'role_assignment % would report to itself'`.
RELATION_LOOKUPS = (
    re.compile(
        r"\b(?:from|join|into|update|delete\s+from)\s+(?:only\s+)?(?:(?P<schema>\w+)\s*\.\s*)?"
        r"role_assignment\b",
        re.IGNORECASE,
    ),
    re.compile(r"'(?:(?P<schema>\w+)\.)?role_assignment'", re.IGNORECASE),
)

# Three samples the sweep is run against before it is believed: one it must
# catch, and two it must allow. A pattern searched against text is a test that can
# go blind and report success (`docs/MISTAKES.md` entry 3), and this is the
# cheapest way to notice. The comment sample is here because this project's
# migrations are heavily commented and "-- walks upward from role_assignment" is
# the sentence a careful author writes directly above the query — a sweep that
# read it as a reference would report a correct function as vulnerable and teach
# the next person to delete the comment.
SWEEP_MUST_CATCH = "SELECT reports_to FROM role_assignment WHERE id = NEW.reports_to"
SWEEP_MUST_ALLOW = "SELECT reports_to FROM public.role_assignment WHERE id = NEW.reports_to"
SWEEP_MUST_ALLOW_COMMENT = "-- update role_assignment, walking upward from role_assignment"


def without_comments(body: str) -> str:
    """`body` with its SQL comments removed, so the sweep reads code and not prose.

    A `--` inside a string literal would be stripped too, which can only hide a
    reference rather than invent one — the safe direction for a tripwire whose
    other failure mode is flagging a correct function.
    """
    return re.sub(r"--[^\n]*", " ", re.sub(r"/\*.*?\*/", " ", body, flags=re.DOTALL))


def unqualified_references(body: str) -> list[str]:
    """Every place `body` names `role_assignment` as a relation without `public.`."""
    code = without_comments(body)
    found: list[str] = []
    for pattern in RELATION_LOOKUPS:
        for match in pattern.finditer(code):
            if (match.group("schema") or "").lower() != "public":
                found.append(match.group(0).strip())
    return found


def trigger_functions(session: Any) -> list[tuple[str, str, list[str]]]:
    """Every function behind a trigger on `role_assignment`: signature, body, settings."""
    rows = session.execute(text(TRIGGER_FUNCTIONS)).all()
    return [(signature, body, list(settings or [])) for signature, body, settings in rows]


def qualified_assignment_table(graph: Any) -> Table:
    """A `public.role_assignment` this test can write through while a shadow exists.

    Two columns and no constraints, because an `UPDATE` needs no more, and built
    against a `MetaData` carrying `schema="public"` so SQLAlchemy renders the
    qualification. The builder's own statements name the table unqualified — which
    is correct for it and fatal here: once the shadow exists, an unqualified
    `UPDATE` would edit the *temp* table, the trigger would never fire, and the
    test would report the guard as broken when nothing had been asked of it.

    The column names and types are read off the real table rather than spelled, so
    this stays correct under any of the shapes E0-09 left open.
    """
    real = graph.assignments
    key = graph.assignment_key
    edge = graph.reports_to_column
    return Table(
        ASSIGNMENTS,
        MetaData(schema="public"),
        Column(key, real.c[key].type),
        Column(edge, real.c[edge].type),
    )


def test_the_cycle_guard_refuses_a_cycle_while_a_temp_table_shadows_role_assignment(
    supervision_graph: Any,
) -> None:
    """The property: a shadow in the writer's own session does not disarm the guard.

    Two two-assignment cycles are prepared before the shadow exists, and both are
    closed by the *same* statement — a qualified `UPDATE public.role_assignment`.
    The only difference between the two attempts is that a shadow exists for the
    second, which is what makes the second refusal attributable to the guard
    surviving rather than to the write being invalid for some other reason.

    **The hijack is asserted to be live**, between the two, rather than assumed.
    Before the shadow, both spellings of the name resolve to the same oid; after
    it, the bare name resolves somewhere else while the qualified one does not
    move. Without that pair of assertions this test would pass on the day the
    shadow silently failed to be created — a temp table on another connection, a
    fixture that stopped sharing a session — and it would then be asserting
    nothing at all while looking exactly as it looks now.

    The temp table is dropped by `db_session`'s rollback, which its docstring
    states: "Postgres puts DDL inside the transaction too, so a table created in a
    test is gone with the rest of it." Nothing here leaks onto the pooled
    connection.
    """
    graph = supervision_graph
    session = graph.session
    key = graph.assignment_key
    edge = graph.reports_to_column
    qualified = qualified_assignment_table(graph)

    def close(child: Any, parent: Any) -> Any:
        """Point `child` at `parent` through the schema-qualified name."""
        return graph.refusal(
            lambda: session.execute(
                qualified.update()
                .where(qualified.c[key] == child[key])
                .values(**{edge: parent[key]})
            )
        )

    control_top = graph.node("CHAIR")
    control_below = graph.node("LEAD_FACULTY", reports_to=control_top[key])
    shadowed_top = graph.node("CHAIR")
    shadowed_below = graph.node("LEAD_FACULTY", reports_to=shadowed_top[key])

    refused_plainly = close(control_top, control_below)
    assert refused_plainly is not None, (
        "With no shadow present, the guard did not refuse a two-assignment cycle written through "
        "`public.role_assignment`. That is the control: until the ordinary case is refused, the "
        "refusal under a shadow below would say nothing about the shadow. "
        "`test_a_two_assignment_cycle_is_refused` in `test_role_assignment_graph.py` is where "
        "this is diagnosed."
    )

    before_bare, before_qualified = session.execute(text(RESOLVE_BOTH)).one()
    assert before_bare is not None and before_bare == before_qualified, (
        f"Before any shadow exists, `role_assignment` resolves to {before_bare} and "
        f"`public.role_assignment` to {before_qualified}. They have to be the same table, and "
        "non-null: if they already differ, something else in this session is shadowing the table "
        "and the comparison after the shadow is created would prove nothing."
    )

    session.execute(text(CREATE_SHADOW))

    after_bare, after_qualified = session.execute(text(RESOLVE_BOTH)).one()
    assert after_qualified == before_qualified, (
        f"After creating the shadow, `public.role_assignment` resolves to {after_qualified} "
        f"rather than to {before_qualified}. The qualified name is what the trigger and this test "
        "both rely on; if it moved, neither is writing where it thinks it is."
    )
    assert after_bare is not None and after_bare != before_bare, (
        f"Creating a temporary table called `{ASSIGNMENTS}` did not change what the bare name "
        f"resolves to — it is {after_bare}, and it was {before_bare}. The hijack this test exists "
        "to defend against is therefore not set up, and the refusal below would be the ordinary "
        "refusal the control already proved. Postgres searches the temporary schema first for "
        "relation names, so a bare name that has not moved means no temp table was created on "
        "*this* session — most likely because the statement ran on a different connection."
    )

    refused_under_shadow = close(shadowed_top, shadowed_below)
    assert refused_under_shadow is not None, (
        "A two-assignment cycle was stored while an empty `pg_temp.role_assignment` shadowed the "
        "real table. Every guard in the trigger read the writer's own empty table instead of the "
        "supervision graph, so it found no cycle — and the advisory lock ADR 0027 relies on moved "
        "with them, because `'role_assignment'::regclass` resolved to the shadow's oid too. SPEC "
        "§2.1 makes purview a transitive union over this graph and E0-09 requires cycles refused "
        "at write time; a guard the writer can aim elsewhere enforces neither. The fix is ADR "
        "0027's: qualify every relation the function names as `public.role_assignment`, and set "
        "`search_path = pg_catalog, public, pg_temp` on the function — naming `pg_temp` last, "
        "because omitting it is what puts it first."
    )


def test_the_trigger_function_names_pg_temp_last_in_its_search_path(db_session: Any) -> None:
    """One half of the fix, asserted where the behavioural test cannot see it.

    ADR 0027 measured all four combinations, and two of them matter here: with the
    relations unqualified, `SET search_path = pg_catalog, public, pg_temp` refuses
    the hijacked write and `SET search_path = pg_catalog, public` stores it. The
    difference is the whole subtlety — **omitting `pg_temp` does not skip it, it
    leaves it first** — so "the function sets a `search_path`" is not the property.
    The property is that `pg_temp` is named, and named last.

    Requiring *last* rather than merely present is deliberate and is stricter than
    the mechanism strictly needs: `pg_temp` after every schema that could be
    shadowed is enough, and today `public` is the only one. Nothing wants to sit
    after it, so the stricter rule costs nothing and does not have to be
    re-derived by the next reader.
    """
    functions = trigger_functions(db_session)
    assert functions, (
        f"No non-internal trigger exists on `public.{ASSIGNMENTS}`, so this test swept nothing "
        "and would report success. ADR 0027 puts the three cross-row supervision rules in one "
        "`AFTER INSERT OR UPDATE … FOR EACH ROW` trigger; `test_role_assignment_graph.py` is "
        "where its absence is diagnosed as behaviour."
    )

    for signature, _, settings in functions:
        configured = dict(
            entry.partition("=")[::2]
            for entry in settings  # "name=value" → (name, value)
        )
        search_path = configured.get("search_path")
        assert search_path is not None, (
            f"`{signature}` carries no `SET search_path`, and it is a trigger function on "
            f"`{ASSIGNMENTS}`. Its settings are {settings}. ADR 0027 ships the `SET` alongside "
            "schema-qualified relations so that either one closes the hijack alone: this is the "
            "half that survives somebody later adding an unqualified table reference. If it is "
            "being dropped deliberately, that is an ADR amendment rather than a test edit."
        )

        schemas = [name.strip().strip('"') for name in search_path.split(",")]
        assert schemas[-1] == "pg_temp", (
            f"`{signature}` sets `search_path = {search_path}`, whose last entry is "
            f"{schemas[-1]!r}. `pg_temp` has to be named, and named last. Leaving it out is the "
            "usual advice and is the variant ADR 0027 measured as **vulnerable**: Postgres "
            "searches the temporary schema first for relation names, and omitting it from the "
            "path is what puts it first rather than what skips it. Naming it anywhere but last "
            "has the same effect against any schema listed after it."
        )


def test_every_relation_the_trigger_function_names_is_schema_qualified(db_session: Any) -> None:
    """The other half, and the one the behavioural test is blind to.

    While the `SET search_path` is in place, removing every `public.` prefix from
    the function body leaves the guard working and the whole suite green —
    including the behavioural test in this module. ADR 0027's measurement table
    says so in a row of its own. So the qualification needs an assertion of its
    own, or it is a convention rather than a guarantee (`docs/MISTAKES.md` entry
    2), and the next contributor removes it during a tidy-up with nothing going
    red.

    **What this sweep looks for**, so nobody reads it as more than it is
    (`docs/MISTAKES.md` entry 14): a relation named after `FROM`, `JOIN`, `INTO`,
    `UPDATE` or `DELETE FROM`, and a name in a string literal on its own, which is
    the `'role_assignment'::regclass` shape the advisory-lock key used. It does not
    parse plpgsql, and a reference in some third form would not be caught. It is a
    tripwire on the two shapes the review actually found, checked against a sample
    of each before it is believed.
    """
    assert unqualified_references(SWEEP_MUST_CATCH), (
        f"The sweep in this file does not flag {SWEEP_MUST_CATCH!r}, which is the exact shape it "
        "exists to catch. It has gone blind, and every assertion below would pass against a "
        "function that names the table unqualified everywhere."
    )
    assert not unqualified_references(SWEEP_MUST_ALLOW), (
        f"The sweep in this file flags {SWEEP_MUST_ALLOW!r}, which is the fixed form. It would "
        "report a correct function as vulnerable."
    )
    assert not unqualified_references(SWEEP_MUST_ALLOW_COMMENT), (
        f"The sweep in this file flags {SWEEP_MUST_ALLOW_COMMENT!r}, which is a comment rather "
        "than a relation reference. `without_comments` is what should have removed it; a sweep "
        "that reads prose as code makes the correct function fail and the comment the casualty."
    )

    functions = trigger_functions(db_session)
    assert functions, (
        f"No non-internal trigger exists on `public.{ASSIGNMENTS}`, so this test swept nothing "
        "and would report success. ADR 0027 puts the three cross-row supervision rules in one "
        "trigger on this table."
    )

    for signature, body, _ in functions:
        assert ASSIGNMENTS in body, (
            f"`{signature}` is a trigger function on `{ASSIGNMENTS}` and its body never names the "
            "table, so this sweep has nothing to check and the assertion below is vacuous. Either "
            "the guards moved somewhere this file cannot see them, or the body was read wrongly."
        )

        unqualified = unqualified_references(body)
        assert not unqualified, (
            f"`{signature}` names `{ASSIGNMENTS}` without a schema at {unqualified}. Postgres "
            "searches the temporary schema first for relation names, so each of those is a table "
            "the *writer* chooses: a security review of this ticket reproduced a stored cycle and "
            "a stored edge into a `CARE` assignment by creating `pg_temp.role_assignment` first. "
            "ADR 0027 ships the qualification as the half that survives somebody dropping the "
            "function's `SET search_path`, so removing it leaves one control where the record "
            "says there are two — and the suite stays green either way, which is why this "
            "assertion is here rather than in the behavioural test above."
        )
