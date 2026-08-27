"""How a *sanctioned* writer satisfies `guard_write` — ticket E1-10.

[ADR 0045](../../docs/adr/0045-the-chokepoint-refuses-an-lms-owned-write-at-table-grain-plus-one-row.md)
left this open in as many words: "This record names the launch path that creates
a `user` row, and E1's roster sync for the other three, as sanctioned writers, and
nothing anywhere says what that means operationally: `guard_write(table='course')`
refuses unconditionally, with no argument, context or flag that makes it return."
E1-10 is the ticket that arrives with a real writer to design against, and this
module is that design asserted.

**Two properties, and they are opposite.** The mechanism has to let the launch
writer through for the tables it is granted, and it has to leave the refusal for
everything else exactly as unconditional as it is today. A module that only
asserted the first would be satisfied by a bypass flag; one that only asserted the
second would be satisfied by a mechanism that does not work. So every test below
is half of a pair, and both halves are here.

**The catalog is the authority, not the argument.** E1-10's design makes a
`WriteSanction` a value a caller can construct, which means a caller can construct
a *wrong* one — naming a writer nobody sanctioned, or naming more tables than the
sanctioned writer holds. `SANCTIONED_WRITERS` is what `guard_write` consults, so a
forged sanction is refused; the two forged-sanction tests below are the whole
difference between a sanction and a bypass flag, and each is asserted beside the
genuine sanction it is a near miss of.

**The catalog's contents are pinned here, exactly, and that is `docs/MISTAKES.md`
entry 35's rule applied to this mechanism.** The inventory of sanctioned writers
has to come from somewhere the guarded structure cannot shrink, so it is written
in this file — as an equality, in the shape
`RUNTIME_BASE_TABLE_PRIVILEGES` in `tests/integration/test_identity_grants.py`
uses — and widening it is a visible diff in a test rather than a line added to a
module nobody re-reads. E1-11's roster sync adds its own entry, deliberately, and
that pull request edits this constant and says why.

**What this module does not assert.** Whether the writer *calls* the guard is next
door, in `tests/unit/test_every_writer_of_an_lms_owned_relation_names_the_guard.py`
— these tests call `guard_write` directly, so they say it answers correctly when
asked and can say nothing about a write path that never asks. That is the same
division ADR 0045's consequences draw between the two modules, and neither implies
the other.
"""

import importlib
from typing import Any

import pytest

# E1-10's work order settles the catalog: "today exactly `{"launch_provisioning":
# frozenset({"course", "section", "user"})}`. E1-11 adds its own entry later,
# deliberately." Held here rather than read out of `authz` for the reason
# `docs/MISTAKES.md` entry 19 gives: a constant compared against itself asserts
# nothing, and a writer quietly added to the guard would take this file's
# assertion with it.
SANCTIONED_WRITERS_EXPECTED: dict[str, frozenset[str]] = {
    "launch_provisioning": frozenset({"course", "section", "user"}),
}

LAUNCH_PROVISIONING = "launch_provisioning"

# The tables the launch writer is granted, and the guarded table it is not.
# `enrollment` is the interesting one: it is in `LMS_OWNED_TABLES`, E1-11's roster
# sync is the writer that will need it (SPEC §2.1 makes a launch prove one
# person's presence, not a roster), and a sanction that reached it would hand this
# ticket a table its own scope excludes.
SANCTIONED_TABLES = ("course", "section", "user")
UNSANCTIONED_GUARDED_TABLE = "enrollment"

# A writer nobody has put in the catalog. E1-11's name is used on purpose: it is
# the writer that will legitimately be added later, so a `guard_write` that
# accepted it today would be accepting the *next* ticket's grant a ticket early —
# which is exactly the failure a catalog exists to make visible.
UNCATALOGUED_WRITER = "roster_sync"

# SPEC §2.1's fifth owned item, and the one that is a purview grant rather than an
# attribute. E1-10 grants nothing on it: the INSTRUCTOR assignment arrives from
# NRPS in E1-11, and this ticket's own scope puts it out.
ROLE_ASSIGNMENT_TABLE = "role_assignment"
INSTRUCTOR_ROLE = "INSTRUCTOR"
PULSE_WRITABLE_ROLE = "LEAD_FACULTY"

# A table SPEC §2.1 puts on Pulse's side, used as the control that a sanction
# argument has not inverted the rule for everything the chokepoint permits.
PULSE_OWNED_TABLE = "person"

# Where `AssignmentRole` might be reachable from, most likely first — the same
# candidate list, for the same reason, as
# `tests/unit/test_lms_owned_writes_are_refused_at_the_chokepoint.py`. A copy
# rather than an import: a test module importing another test module depends on
# where pytest put `tests/` on `sys.path`, and an import error is not a red.
ROLE_ENUM_HOLDERS = ("app.models", "app.models.identity")


def assignment_role(authz: Any, name: str) -> Any:
    """The `AssignmentRole` member called `name`, wherever the enum lives."""
    holders: list[Any] = [authz.module]
    for holder in ROLE_ENUM_HOLDERS:
        try:
            holders.append(importlib.import_module(holder))
        except ImportError:
            continue
    for module in holders:
        enumeration = getattr(module, "AssignmentRole", None)
        member = getattr(enumeration, name, None) if enumeration is not None else None
        if member is not None:
            return member
    pytest.fail(
        f"Neither the chokepoint nor {list(ROLE_ENUM_HOLDERS)} exposes an `AssignmentRole` with a "
        f"`{name}` member. `ROLE_ENUM_HOLDERS` in this file is the one line that changes if it "
        "moved."
    )


def guard(authz: Any, **arguments: Any) -> None:
    """Call `guard_write`, turning a missing `sanction` keyword into a named failure.

    Without this, every test below that passes a sanction to a `guard_write` which
    has not grown the parameter yet reports a `TypeError` from inside the call —
    which reads as a broken test rather than as the deliverable this ticket is
    about not being there. `docs/MISTAKES.md` entry 16's distinction, in miniature:
    an error is not a red, it is a run that proved nothing.
    """
    try:
        authz.guard_write(**arguments)
    except TypeError as failure:
        if "sanction" not in str(failure):
            raise
        pytest.fail(
            f"`guard_write(**{sorted(arguments)})` raised {failure}. E1-10 gives the chokepoint an "
            "optional `sanction: WriteSanction | None = None` keyword: with no sanction the "
            "behaviour is exactly today's, and with one the catalog decides. ADR 0045 records the "
            "gap this closes — 'nothing anywhere says what that means operationally'."
        )


def refused(authz: Any, what: str, **arguments: Any) -> None:
    """Require `guard_write` to refuse, saying what a pass would mean."""
    refusal = authz.LmsOwnedWriteRefused
    try:
        guard(authz, **arguments)
    except refusal:
        return
    pytest.fail(
        f"`guard_write` permitted {what}. SPEC §8: 'LMS-owned data is never hand-edited in "
        "Pulse.' A sanction mechanism that permits this is a bypass flag with a longer name."
    )


def must_raise(action: Any, what: str, consequence: str) -> None:
    """Require `action()` to raise something, whatever it raises.

    The exception type is deliberately not named. E1-10 settles that
    `sanction_for` "raises for a writer not in the catalog" and that
    `WriteSanction` is frozen, and neither says which exception either produces —
    so requiring a particular one here would pin an interface the ticket leaves
    open. What is asserted is that the call did not quietly succeed, which is the
    property in both cases.

    `pytest.fail`'s own `Failed` is a `BaseException` rather than an `Exception`,
    so a failure raised *inside* `action` — a missing symbol, say — travels
    through this untouched instead of being read as the refusal under test.
    """
    try:
        action()
    except Exception:
        return
    pytest.fail(f"{what} did not raise. {consequence}")


def permitted(authz: Any, what: str, **arguments: Any) -> None:
    """Require `guard_write` to return, saying what a refusal would mean.

    Both names are resolved before the call, so a module missing one of them
    reports *that* rather than reporting it from inside an `except` clause while
    another failure is already propagating.
    """
    refusals = authz.AuthzError
    try:
        guard(authz, **arguments)
    except refusals as refusal:
        pytest.fail(
            f"`guard_write` refused {what} with {refusal!r}. Refusing too much is this mechanism's "
            "other failure mode and the one no denial test can see: E1-10's writer is the first "
            "code in this project that writes an LMS-owned relation at all, and a chokepoint that "
            "refuses it leaves launch-time ingestion — one of SPEC §2.1's two arrival paths for "
            "courses and sections — unable to write anything."
        )


# ---------------------------------------------------------------------------
# The catalog.
# ---------------------------------------------------------------------------


def test_the_catalog_of_sanctioned_writers_is_exactly_the_one_entry_this_ticket_grants(
    authz: Any,
) -> None:
    """`docs/MISTAKES.md` entry 35: the inventory lives where the guarded module cannot shrink it.

    An equality rather than a floor, and the difference is the whole point. A
    `>=` comparison is satisfied by a catalog that has grown a second writer, or
    by an entry that has grown a fourth table, and either is a widening of what
    may write LMS-owned data with nothing anywhere going red — the same shape
    `test_the_runtime_roles_hold_no_privilege_on_a_base_table_beyond_the_reveals_own`
    exists for on the grant axis, and it is here for the same reason.

    **This will go red for a good reason**, and that is the cost being paid on
    purpose: E1-11's roster sync is a sanctioned writer for `course`, `section`,
    `enrollment` and the `INSTRUCTOR` `role_assignment` row, and the pull request
    that adds it edits this constant and says so. A grant recorded in a test diff
    is the deliverable; a grant that arrives unnoticed is what this refuses.

    **The mutation it exists to survive**: adding `"enrollment"` to
    `launch_provisioning`'s set — a table this ticket's scope explicitly leaves to
    E1-11 — and adding a second key to the mapping. Neither changes the behaviour
    of any other test in this file, because every one of them names its table.
    """
    catalog = authz.SANCTIONED_WRITERS
    held = {writer: frozenset(tables) for writer, tables in dict(catalog).items()}

    assert held == SANCTIONED_WRITERS_EXPECTED, (
        f"`SANCTIONED_WRITERS` is {held} and this ticket's record says it is "
        f"{SANCTIONED_WRITERS_EXPECTED}.\n\n"
        "Every entry in it is permission to write a relation SPEC §2.1 makes LMS-owned and §8 "
        "says is 'never hand-edited in Pulse', so the set is an authorization boundary and not "
        "a configuration detail. A writer or a table added here without a record is the "
        "convenience grant this equality exists to force a conversation about.\n\n"
        "If the addition is legitimate — E1-11's roster sync is the one already foreseen — the "
        "constant at the head of this file is where it is recorded, in the pull request that "
        "makes the change, with the sentence it rests on."
    )


def test_sanction_for_answers_the_catalog_and_refuses_a_writer_it_does_not_name(
    authz: Any,
) -> None:
    """The lookup, both ways: a catalogued writer resolves, an uncatalogued one raises.

    The refusing half is what stops `sanction_for` becoming a factory that hands
    out a sanction for any name it is given, which would make the catalog
    decorative — the caller would simply ask for what it wanted. The resolving
    half is what stops it refusing everything, which no test of the refusal alone
    could tell apart.

    What `sanction_for` answers is required to *be* the catalog's entry rather
    than merely to exist: a lookup that returned an empty table set would satisfy
    "it raised for the wrong name" and grant nothing.
    """
    sanction = authz.sanction_for(LAUNCH_PROVISIONING)

    assert getattr(sanction, "writer", None) == LAUNCH_PROVISIONING, (
        f"`sanction_for({LAUNCH_PROVISIONING!r})` answered {sanction!r}, whose `writer` is "
        f"{getattr(sanction, 'writer', None)!r}. The sanction has to carry the name it was looked "
        "up under, or `guard_write` cannot check it against the catalog."
    )
    assert (
        frozenset(getattr(sanction, "tables", ()))
        == SANCTIONED_WRITERS_EXPECTED[LAUNCH_PROVISIONING]
    ), (
        f"`sanction_for({LAUNCH_PROVISIONING!r})` answered tables "
        f"{sorted(getattr(sanction, 'tables', ()))}, and the catalog grants "
        f"{sorted(SANCTIONED_WRITERS_EXPECTED[LAUNCH_PROVISIONING])}."
    )

    must_raise(
        lambda: authz.sanction_for(UNCATALOGUED_WRITER),
        f"`sanction_for({UNCATALOGUED_WRITER!r})`",
        "A lookup that invents a sanction for any name it is handed makes `SANCTIONED_WRITERS` a "
        "comment: the caller asks for the writer it wants to be, and gets it.",
    )


def test_a_write_sanction_cannot_be_widened_in_place(authz: Any) -> None:
    """A sanction is a value, not a handle onto the catalog.

    E1-10 makes `WriteSanction` a frozen dataclass, and frozen is load-bearing
    rather than stylistic: a caller holding a mutable sanction could add
    `enrollment` to the very object `sanction_for` handed it, and if the catalog
    hands out its own `frozenset` the mutation could reach the catalog itself and
    widen the grant for every later caller in the process.

    **The mutation it exists to survive**: dropping `frozen=True` from the
    dataclass. The near miss it must not fire on is a sanction that is merely
    *unused* — nothing here asserts anything about what a sanction is for, only
    that it cannot be edited once made.
    """
    sanction = authz.sanction_for(LAUNCH_PROVISIONING)

    def widen() -> None:
        sanction.tables = frozenset({UNSANCTIONED_GUARDED_TABLE})  # type: ignore[misc]

    def rename() -> None:
        sanction.writer = UNCATALOGUED_WRITER  # type: ignore[misc]

    must_raise(
        widen,
        "Reassigning a `WriteSanction`'s `tables`",
        "A caller can widen the grant it was handed. If `sanction_for` returns the catalog's own "
        "value, that widening reaches every later caller in the process and nothing records it.",
    )
    must_raise(
        rename,
        "Reassigning a `WriteSanction`'s `writer`",
        "A caller holding one sanction can become any writer it likes.",
    )


# ---------------------------------------------------------------------------
# With no sanction: exactly today's behaviour, and it is asserted rather than
# assumed.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table", (*SANCTIONED_TABLES, UNSANCTIONED_GUARDED_TABLE))
def test_a_write_with_no_sanction_is_still_refused_on_every_guarded_table(
    authz: Any, table: str
) -> None:
    """The half of this mechanism that must not change, asserted table by table.

    E1-10's work order: "With no sanction, behaviour is exactly today's:
    unconditional refusal on the guarded set. That property is load-bearing and
    tested." It is load-bearing because every caller in the project that is *not*
    the launch writer passes no sanction, and the day one of them starts writing
    `course` this refusal is the only thing between it and LMS-owned data.

    **The mutation it exists to survive**: a `sanction` parameter that defaults to
    something permissive rather than to `None`, or a guard rewritten so the
    refusal is reached only when a sanction was supplied. Both leave every test in
    the paired file above green.

    Its near miss is the test directly below, which passes a genuine sanction for
    three of these four tables and requires a return.
    """
    refused(authz, f"a write to `{table}` with no sanction at all", table=table)


@pytest.mark.parametrize("table", SANCTIONED_TABLES)
def test_a_sanctioned_writer_may_write_each_table_its_catalog_entry_names(
    authz: Any, table: str
) -> None:
    """The half that has to work, table by table — the pair to the test above.

    ADR 0045 names the launch path as a sanctioned writer for `user` and E1-10
    adds `course` and `section` to it, because launch-time ingestion is one of
    SPEC §2.1's two arrival paths for a course and a section and there is no other
    way for either to be discovered before a roster sync has an address to call.

    **Parametrised per table rather than asserted once**, so a mechanism that
    happens to work for `user` and not for `section` names which one — and so a
    grant that quietly stopped covering one of the three is a red naming it
    instead of a single test with a longer message.
    """
    permitted(
        authz,
        f"a write to `{table}` by the sanctioned launch writer",
        table=table,
        sanction=authz.sanction_for(LAUNCH_PROVISIONING),
    )


def test_a_sanctioned_writer_is_refused_a_guarded_table_its_own_entry_does_not_name(
    authz: Any,
) -> None:
    """A sanction is per table set, not per writer.

    `enrollment` is in `LMS_OWNED_TABLES` and is not in this writer's entry: SPEC
    §2.1 makes enrollments LMS-owned and E1-10's scope puts enrollment writes in
    E1-11, "from NRPS — a launch proves one person's presence, not a roster". A
    mechanism that answered "is this writer sanctioned?" rather than "is this
    writer sanctioned for this table?" would hand this ticket the next one's
    grant, and every other test in this file would stay green.

    The pair is one call away and is asserted here rather than next door, so that
    the refusal is known to be about the table: the same sanction, on a table the
    entry does name, has to return.
    """
    sanction = authz.sanction_for(LAUNCH_PROVISIONING)

    refused(
        authz,
        f"a write to `{UNSANCTIONED_GUARDED_TABLE}` by the launch writer",
        table=UNSANCTIONED_GUARDED_TABLE,
        sanction=sanction,
    )
    permitted(
        authz,
        "a write to `course` by the same sanction",
        table="course",
        sanction=sanction,
    )


# ---------------------------------------------------------------------------
# Forged sanctions: the catalog is the authority, and a caller may build one.
# ---------------------------------------------------------------------------


def test_a_sanction_naming_a_writer_the_catalog_does_not_hold_is_refused(authz: Any) -> None:
    """The difference between a sanction and a bypass flag.

    `WriteSanction` is a value with a public constructor, so a caller can build
    one naming any writer at all. If `guard_write` read the sanction it was handed
    instead of consulting `SANCTIONED_WRITERS`, then the catalog would be
    decorative and the mechanism would be `guard_write(table='course',
    please=True)` — every write path in the project could authorize itself, and
    the pinning test at the head of this file would go on passing because the
    catalog itself never changed.

    **The pair is inside this test**, because a refusal is a refusal: the same
    table, with the sanction the catalog actually holds, is required to return, so
    a chokepoint that refuses everything cannot satisfy this.
    """
    forged = authz.WriteSanction(writer=UNCATALOGUED_WRITER, tables=frozenset({"course"}))

    refused(
        authz,
        f"a write to `course` under a hand-built sanction naming {UNCATALOGUED_WRITER!r}",
        table="course",
        sanction=forged,
    )
    permitted(
        authz,
        "a write to `course` under the catalogued launch writer's sanction",
        table="course",
        sanction=authz.sanction_for(LAUNCH_PROVISIONING),
    )


def test_a_sanction_that_names_more_tables_than_the_catalog_grants_is_refused(
    authz: Any,
) -> None:
    """The second forgery: the right writer, a widened table set.

    Nearer the mark than the test above and therefore the more useful of the two.
    The writer's name is genuine, so an implementation that checked only the name
    passes; the table set is the caller's own, so an implementation that read
    `sanction.tables` rather than the catalog's entry passes as well. Only one
    that treats `SANCTIONED_WRITERS` as the authority refuses.

    **The near miss it must not fire on** is the same forged sanction used for a
    table the catalog *does* grant this writer: that has to return, or the
    refusal above would be evidence that hand-built sanctions are refused
    outright, which is a different rule and one nothing asks for.
    """
    widened = authz.WriteSanction(
        writer=LAUNCH_PROVISIONING,
        tables=frozenset({*SANCTIONED_TABLES, UNSANCTIONED_GUARDED_TABLE}),
    )

    refused(
        authz,
        f"a write to `{UNSANCTIONED_GUARDED_TABLE}` under a sanction that named it itself",
        table=UNSANCTIONED_GUARDED_TABLE,
        sanction=widened,
    )
    permitted(
        authz,
        "a write to `course`, which this writer's catalog entry does grant",
        table="course",
        sanction=widened,
    )


# ---------------------------------------------------------------------------
# The fifth owned item, and the controls on the permitted side.
# ---------------------------------------------------------------------------


def test_the_teaching_instructor_row_is_refused_even_to_a_sanctioned_writer(authz: Any) -> None:
    """SPEC §2.1's fifth owned item is not in this writer's grant, and a sanction is not a mood.

    An `INSTRUCTOR` `role_assignment` row is a purview grant — §2.1 computes
    purview from exactly these rows — so a write path able to create one can hand
    somebody oversight of a section, with the moderation view and the report that
    hang off it. E1-10's scope puts INSTRUCTOR assignment writes in E1-11, and the
    catalog entry pinned above names three tables and not this row.

    **The mutation it exists to survive**: a `guard_write` that returns early as
    soon as any sanction is present, before it reaches the role check. That leaves
    every table-grained test in this file green.

    **The control beside it** is a `LEAD_FACULTY` assignment written with the same
    sanction, which §6.3's People editor writes and which must still be permitted.
    Without it, a chokepoint that refused `role_assignment` outright whenever a
    sanction was passed would satisfy this test.
    """
    sanction = authz.sanction_for(LAUNCH_PROVISIONING)

    refused(
        authz,
        "an `INSTRUCTOR` role assignment written under the launch writer's sanction",
        table=ROLE_ASSIGNMENT_TABLE,
        assignment_role=assignment_role(authz, INSTRUCTOR_ROLE),
        sanction=sanction,
    )
    permitted(
        authz,
        f"a `{PULSE_WRITABLE_ROLE}` role assignment written with a sanction in hand",
        table=ROLE_ASSIGNMENT_TABLE,
        assignment_role=assignment_role(authz, PULSE_WRITABLE_ROLE),
        sanction=sanction,
    )


def test_a_table_pulse_owns_is_permitted_whether_or_not_a_sanction_is_passed(
    authz: Any,
) -> None:
    """The control on the rest of the chokepoint: a new keyword must not change it.

    SPEC §2.1 names `person` as Pulse's own — "the LMS has no equivalent; purview
    is computed from this graph" — and §6.3's People editor writes it. Adding a
    parameter to `guard_write` is exactly the sort of change that inverts a
    condition by accident, and a mechanism that started refusing every unguarded
    table unless a sanction was supplied would be caught by nothing else here.

    Both directions in one test on purpose: with a sanction and without it, the
    answer for a table the chokepoint does not guard is the same answer.
    """
    permitted(authz, f"a write to `{PULSE_OWNED_TABLE}` with no sanction", table=PULSE_OWNED_TABLE)
    permitted(
        authz,
        f"a write to `{PULSE_OWNED_TABLE}` with a sanction in hand",
        table=PULSE_OWNED_TABLE,
        sanction=authz.sanction_for(LAUNCH_PROVISIONING),
    )


def test_every_table_the_catalog_grants_is_a_table_the_chokepoint_actually_guards(
    authz: Any,
) -> None:
    """A sanction for a table nobody refuses grants nothing and reads as though it did.

    The mirror of ADR 0045's "a typo in the set refuses nothing", one level up:
    `SANCTIONED_WRITERS` holds table *names*, so `"courses"` in the launch
    writer's entry would sanction writes to a table that does not exist while the
    real one stayed refused — and the failure would appear as a launch that
    cannot provision, three files away from its cause.

    Scoped to `LMS_OWNED_TABLES` rather than to `Base.metadata` because that is
    the question worth asking: a sanction is permission to pass *this* guard, and
    a name the guard never refuses is a permission for nothing.
    """
    guarded = frozenset(authz.LMS_OWNED_TABLES)
    assert guarded, (
        "`LMS_OWNED_TABLES` is empty, so the comparison below is true of a catalog naming "
        "anything at all. `test_the_refusal_set_names_the_tables_the_spec_puts_on_the_lms_side` "
        "is where an empty refusal set is diagnosed."
    )

    granted = {
        (writer, table)
        for writer, tables in dict(authz.SANCTIONED_WRITERS).items()
        for table in tables
        if table not in guarded
    }
    assert not granted, (
        f"`SANCTIONED_WRITERS` grants {sorted(granted)}, and `LMS_OWNED_TABLES` is "
        f"{sorted(guarded)} — so those grants name tables the chokepoint does not refuse. Either "
        "the name is a typo, in which case the writer it was meant for is still refused and will "
        "fail at run time; or the guard has stopped refusing a table somebody was sanctioned to "
        "write, which is a narrowing of the guard and is diagnosed by "
        "`test_the_guard_names_every_table_in_the_floor_this_sweep_may_not_fall_below`."
    )
