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
module nobody re-reads. E1-11's roster sync added the second entry, deliberately, and
that pull request edited this constant and said why — including the two tables
E1-10 predicted for it and it did not take. **E3-05's grade passback is the third**,
holding `section` alone so that SPEC §3.4's line-item id has a writer; that pull
request edited this constant too, and moved `UNCATALOGUED_WRITER` on to the next
writer nobody has granted yet, since the forged-sanction tests below need a name the
catalog really does not hold.

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

# E1-10's work order settled the catalog at one entry — "today exactly
# `{"launch_provisioning": frozenset({"course", "section", "user"})}`. E1-11 adds
# its own entry later, deliberately" — and **E1-11 is that ticket**, adding
# `roster_sync` under its work order's decision D2 and ADR 0090's own consequence
# ("E1-11 adds the `INSTRUCTOR` write it needs by adding an entry, deliberately, in
# the pull request that needs it").
#
# The roster sync's three: `user`, because a member the deployment has never seen
# needs a row before anything can be enrolled; `enrollment`, which is the whole
# subject of SPEC §3.4's windows; and `role_assignment`, for the teaching
# instructor's row, which is the first entry in this catalog that is not a table
# at all but a row-grain rule — see `ROLE_ASSIGNMENT_TABLE` below.
#
# `course` and `section` are **not** in it, and the absence is the interesting
# part: SPEC §7.3 makes launch-time ingestion the only thing that discovers a
# section ("it has no way of its own to learn that a section exists"), so a sync
# that could create one would be inventing a section from a roster it was only
# able to fetch because a section already existed.
#
# Held here rather than read out of `authz` for the reason `docs/MISTAKES.md`
# entry 19 gives: a constant compared against itself asserts nothing, and a writer
# quietly added to the guard would take this file's assertion with it.
#
# **E3-05 adds the third entry, `grade_passback`, and it holds one table.** SPEC
# §3.4 gives every section one AGS line item "created by the tool on first
# launch", and the id of that line item lives on `section.ags_line_item_url` (ADR
# 0128) — a column E3-02 created and deliberately left unwritten. So the grade
# passback path is a writer of `section`, which `LMS_OWNED_TABLES` names, and it
# satisfies the chokepoint the same way the other two do rather than being excused
# from it.
#
# The *rest* of `section` is not in the entry and that is the load-bearing half.
# `lms_section_code`, `lms_context_id`, the binding columns and ADR 0021's derived
# calendar columns are a launch's discovery and this writer has no business
# anywhere near them; the database says the same thing one layer down, where
# ADR 0136 spends a column-scoped `UPDATE` on `ags_line_item_url` alone rather
# than a table-wide one (`RUNTIME_COLUMN_PRIVILEGES` in
# `tests/integration/test_identity_grants.py`). The catalog cannot express a
# column, so the two controls are not the same control and neither replaces the
# other.
SANCTIONED_WRITERS_EXPECTED: dict[str, frozenset[str]] = {
    "launch_provisioning": frozenset({"course", "section", "user"}),
    "roster_sync": frozenset({"user", "enrollment", "role_assignment"}),
    "grade_passback": frozenset({"section"}),
}

LAUNCH_PROVISIONING = "launch_provisioning"
ROSTER_SYNC = "roster_sync"
GRADE_PASSBACK = "grade_passback"

# The one table the grade passback writer is granted, and one guarded table it is
# not. `user` is the interesting refusal: SPEC §4 keys every response to
# `user.lms_user_id`, a passback reads that value to address a score, and a
# sanction that reached the table would let the grading path edit the identity the
# whole confidentiality model is built on.
GRADE_PASSBACK_TABLE = "section"
UNSANCTIONED_FOR_THE_PASSBACK = "user"

# The tables each writer is granted, and one guarded table each is not.
# `enrollment` against the launch writer is the interesting pair: it is in
# `LMS_OWNED_TABLES`, E1-11's roster sync is the writer that needs it (SPEC §2.1
# makes a launch prove one person's presence, not a roster), and a sanction that
# reached it from the launch path would hand one ticket another's grant.
SANCTIONED_TABLES = ("course", "section", "user")
UNSANCTIONED_GUARDED_TABLE = "enrollment"
ROSTER_SYNC_TABLES = ("user", "enrollment")
UNSANCTIONED_FOR_THE_SYNC = "section"

# A writer nobody has put in the catalog. **This constant has moved twice, and
# each move is the same event**: E1-11's name used to be here, on the ground that
# it was "the writer that will legitimately be added later", and E1-11 added it;
# E3-05's `grade_passback` took its place and E3-05 has now added that. So the
# name moves again, to the next writer this repository knows it will want and does
# not yet have.
#
# E11's registration and repair console is that writer. `docs/tickets/e3/carried-from-e2.md`
# names it twice — it is "the first surface that writes `lti_platform` from outside
# the seed", and it is what a squatted `(course, term, lms_section_code)` binding
# would be repaired through, which is a write to `section`. It writes nothing
# today, and a `guard_write` that accepted its name would be accepting a later
# ticket's grant early — exactly the failure a catalog exists to make visible.
UNCATALOGUED_WRITER = "admin_console"

# SPEC §2.1's fifth owned item, and the one that is a purview grant rather than an
# attribute. It is a *row* rather than a table — the teaching instructor is an
# `INSTRUCTOR` assignment and every other role on that table is Pulse's to write —
# so the catalog entry that names it is unlike the other four in the file, and
# `test_every_table_the_catalog_grants_is_a_table_the_chokepoint_actually_guards`
# below carries the consequence.
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

    **It went red for a good reason once already, and that is the cost being paid
    on purpose.** E1-10 wrote this constant with one entry and predicted the
    second; E1-11 adds `roster_sync` — `user`, `enrollment` and the `INSTRUCTOR`
    `role_assignment` row — and this constant moved in the pull request that made
    the change, with the sentence each table rests on beside it. A grant recorded
    in a test diff is the deliverable; a grant that arrives unnoticed is what this
    refuses. (E1-10's own prediction named `course` and `section` for the sync as
    well; they are deliberately not there — SPEC §7.3 gives a section only one way
    to be discovered, and it is not the roster of a section that must already
    exist for the roster to be fetchable.)

    **The mutation it exists to survive**: adding `"enrollment"` to
    `launch_provisioning`'s set — a table E1-10's scope explicitly left to
    E1-11 — and adding `"course"` or `"section"` to `roster_sync`'s. Neither
    changes the behaviour of any other test in this file, because every one of them
    names its table.
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


@pytest.mark.parametrize(
    ("writer", "table"),
    [
        *((LAUNCH_PROVISIONING, table) for table in SANCTIONED_TABLES),
        *((ROSTER_SYNC, table) for table in ROSTER_SYNC_TABLES),
        (GRADE_PASSBACK, GRADE_PASSBACK_TABLE),
    ],
)
def test_a_sanctioned_writer_may_write_each_table_its_catalog_entry_names(
    authz: Any, writer: str, table: str
) -> None:
    """The half that has to work, table by table — the pair to the test above.

    ADR 0045 names the launch path as a sanctioned writer for `user` and E1-10
    adds `course` and `section` to it, because launch-time ingestion is one of
    SPEC §2.1's two arrival paths for a course and a section and there is no other
    way for either to be discovered before a roster sync has an address to call.
    ADR 0045 names E1's roster sync for the rest, and E1-11 spends `user` and
    `enrollment` of them — that ticket's other arrival path, "hourly roster sync".
    E3-05 adds `grade_passback` and `section`: SPEC §3.4's line item is "created by
    the tool on first launch" and the id it comes back with is stored on the
    section row (ADR 0128), so grade passback is a writer of an LMS-owned table and
    calls the chokepoint like everything else.

    **Parametrised per writer and table rather than asserted once**, so a mechanism
    that happens to work for `user` and not for `enrollment` names which one — and
    so a grant that quietly stopped covering one of the five is a red naming it
    instead of a single test with a longer message.
    """
    permitted(
        authz,
        f"a write to `{table}` by the sanctioned `{writer}` writer",
        table=table,
        sanction=authz.sanction_for(writer),
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


def test_the_grade_passback_writer_is_refused_the_table_the_confidentiality_model_is_keyed_to(
    authz: Any,
) -> None:
    """E3-05's entry is one table wide, asserted from the side that matters.

    The pair above says `grade_passback` may write `section`. This says what it
    may not, and the table is chosen rather than arbitrary: SPEC §4 keys every
    stored response to `user.lms_user_id`, which is the launch's `sub` claim
    verbatim, and a grade passback reads exactly that value to address a score. So
    `user` is the table this writer is nearest to and has least business in — a
    sanction that reached it would let the grading path rewrite the identity the
    confidentiality model is built on, and ADR 0045 puts `user` in the guarded set
    for that reason and no other.

    **The mutation this kills**: `grade_passback` given `LMS_OWNED_TABLES` rather
    than one name — the shape a writer takes when somebody copies the entry above
    it — and the wider one, a `guard_write` that answers "is this writer
    sanctioned?" rather than "is this writer sanctioned for this table?". The
    second is already refused for the launch writer one test up; it is asserted
    again here because a catalog gains entries and a mechanism that regressed
    would be caught on whichever entry a test happened to name.

    **The pair is inside this test**, so the refusal is known to be about the
    table: the same sanction, on the table its entry does name, has to return.
    """
    sanction = authz.sanction_for(GRADE_PASSBACK)

    refused(
        authz,
        f"a write to `{UNSANCTIONED_FOR_THE_PASSBACK}` by the grade passback writer",
        table=UNSANCTIONED_FOR_THE_PASSBACK,
        sanction=sanction,
    )
    permitted(
        authz,
        f"a write to `{GRADE_PASSBACK_TABLE}` by the same sanction",
        table=GRADE_PASSBACK_TABLE,
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


def test_the_teaching_instructor_row_is_refused_to_a_writer_the_catalog_does_not_grant_it(
    authz: Any,
) -> None:
    """SPEC §2.1's fifth owned item is not in the launch writer's grant, and a sanction is not a mood.

    An `INSTRUCTOR` `role_assignment` row is a purview grant — §2.1 computes
    purview from exactly these rows — so a write path able to create one can hand
    somebody oversight of a section, with the moderation view and the report that
    hang off it. E1-10's scope put INSTRUCTOR assignment writes in E1-11, and the
    launch writer's catalog entry names three tables and not this row. **E1-11
    grants it to the roster sync and to nothing else**, which is why this test now
    says "a writer the catalog does not grant it" rather than "even to a
    sanctioned writer": the branch is no longer an unconditional refusal, so what
    it refuses has to be stated in terms of the catalog.

    **The mutation it exists to survive**: a `guard_write` that returns early as
    soon as any sanction is present, before it reaches the role check. That leaves
    every table-grained test in this file green, and it is a much easier mistake to
    make now that one entry in the catalog legitimately passes this branch.

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


def test_the_roster_sync_may_write_the_teaching_instructor_row_its_entry_names(
    authz: Any,
) -> None:
    """Decision D2's permitting half: the branch learns a catalogued writer.

    ADR 0090 recorded the gap and named the ticket that closes it: "The
    teaching-instructor row is outside the mechanism … no catalogued writer is
    granted `role_assignment`, so a sanction never reaches that branch. E1-11 adds
    the `INSTRUCTOR` write it needs by adding an entry, deliberately, in the pull
    request that needs it." This is that write.

    **Why it has to be permitted rather than routed around.** SPEC §2.1 makes the
    teaching instructor LMS-owned — the roster is where Pulse learns who teaches a
    section — so the alternative to passing the guard is a writer that does not
    call it, which is precisely the bypass ADR 0045 names and E0-35's sweep exists
    to find.

    **The mutation this kills**: a branch that goes on refusing unconditionally,
    which leaves E1-11 unable to write the row at all and every refusal test in
    this file green. It is the failure mode a denial-only suite cannot see, and it
    is the one this project has shipped before (`docs/MISTAKES.md` entry 2's
    mirror image: a wall where the ticket asks for a door).

    **The near miss it must not fire on** is one call away and is asserted in the
    test above: the same row, under the *launch* writer's sanction, still refused.
    """
    permitted(
        authz,
        "an `INSTRUCTOR` role assignment written under the roster sync's own sanction",
        table=ROLE_ASSIGNMENT_TABLE,
        assignment_role=assignment_role(authz, INSTRUCTOR_ROLE),
        sanction=authz.sanction_for(ROSTER_SYNC),
    )


def test_the_instructor_branch_reads_the_catalog_rather_than_the_sanction_it_was_handed(
    authz: Any,
) -> None:
    """Decision D2's mirror: `sanction.tables` is never read, on this branch either.

    "Exactly mirroring the `LMS_OWNED_TABLES` branch: catalog is authority,
    `sanction.tables` is never read."

    `WriteSanction` has a public constructor, so a caller can hand the guard a
    sanction naming the launch writer and a table set of its own choosing. On the
    table-grained branch that forgery is refused and
    `test_a_sanction_that_names_more_tables_than_the_catalog_grants_is_refused`
    above is where; this is the same forgery aimed at the row-grained branch, which
    is a separate piece of code and now the more valuable of the two — the row it
    guards is a purview grant rather than a stale attribute.

    **The mutation this kills**: an implementation that writes the new branch as
    `if ROLE_ASSIGNMENT_TABLE in sanction.tables: return`. Every other test in this
    file passes against it, including the permitting one directly above, because
    `sanction_for("roster_sync")` carries exactly that table.

    **The near miss it must not fire on** is inside this test: the *catalogued*
    roster-sync sanction on the same row has to return, or this would be evidence
    that hand-built sanctions are refused outright — a different rule, which
    nothing asks for.
    """
    forged = authz.WriteSanction(
        writer=LAUNCH_PROVISIONING, tables=frozenset({*SANCTIONED_TABLES, ROLE_ASSIGNMENT_TABLE})
    )

    refused(
        authz,
        "an `INSTRUCTOR` role assignment under a sanction that named `role_assignment` itself",
        table=ROLE_ASSIGNMENT_TABLE,
        assignment_role=assignment_role(authz, INSTRUCTOR_ROLE),
        sanction=forged,
    )
    permitted(
        authz,
        "the same row under the sanction the catalog actually grants it to",
        table=ROLE_ASSIGNMENT_TABLE,
        assignment_role=assignment_role(authz, INSTRUCTOR_ROLE),
        sanction=authz.sanction_for(ROSTER_SYNC),
    )


def test_the_roster_sync_is_refused_a_guarded_table_its_own_entry_does_not_name(
    authz: Any,
) -> None:
    """The sync's grant is per table too, and `section` is the table it must not reach.

    SPEC §7.3 gives a section exactly one way to be discovered — the staff launch
    that stores its roster address, because the scheduled job "has no way of its
    own to learn that a section exists". A sync able to write `section` could
    create one from a roster, and the roster it would create it from is one it
    could only fetch because the section already existed.

    **The mutation this kills**: a catalog entry widened to the four tables ADR
    0045 loosely names for "E1's roster sync", or a guard that answers "is this
    writer sanctioned?" rather than "is this writer sanctioned for this table?".

    The pair is inside the test, so the refusal is known to be about the table: the
    same sanction, on `enrollment`, has to return.
    """
    sanction = authz.sanction_for(ROSTER_SYNC)

    refused(
        authz,
        f"a write to `{UNSANCTIONED_FOR_THE_SYNC}` by the roster sync",
        table=UNSANCTIONED_FOR_THE_SYNC,
        sanction=sanction,
    )
    permitted(
        authz,
        "a write to `enrollment` by the same sanction",
        table=UNSANCTIONED_GUARDED_TABLE,
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

    **`role_assignment` is admitted beside that set, and only because the guard
    refuses it at row grain.** SPEC §2.1's fifth owned item is the teaching
    instructor, which is an `INSTRUCTOR` row on a table Pulse otherwise owns
    outright — so it is deliberately not in `LMS_OWNED_TABLES` (every other role on
    that table would then be refused, and §6.3's People editor writes them all) and
    it is just as deliberately something a sanction can name, since E1-11 has to
    pass that branch. Admitting it here without saying so would have made this test
    blind to a typo in exactly the one entry whose blast radius is a purview grant;
    what keeps it honest is that the guard is required to have a row-grain refusal
    for it at all, which the two `INSTRUCTOR` tests above provoke in both
    directions.
    """
    assert authz.LMS_OWNED_TABLES, (
        "`LMS_OWNED_TABLES` is empty, so the comparison below is true of a catalog naming "
        "anything at all. `test_the_refusal_set_names_the_tables_the_spec_puts_on_the_lms_side` "
        "is where an empty refusal set is diagnosed."
    )
    guarded = frozenset(authz.LMS_OWNED_TABLES) | {ROLE_ASSIGNMENT_TABLE}

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
