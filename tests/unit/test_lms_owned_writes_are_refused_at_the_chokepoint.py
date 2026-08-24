"""The chokepoint refuses a write to data the LMS owns — ticket E0-11.

E0-11's acceptance criterion: "A write to an LMS-owned column is refused at the
chokepoint, and the refusal is asserted per column rather than once… **Choose the
grain deliberately; do not inherit it from the marker.**"

**The grain is table-grained, plus one row.** SPEC §2.1's ownership list is
*courses, sections, section codes, enrollments, teaching instructors*; four of
those five live on `course`, `section` or `enrollment`, and the fifth — the
teaching-instructor link — is an `INSTRUCTOR` row on `role_assignment`, because
§2.1's chain is over role assignments and §8 puts those there. That last row is
the one worth spelling out separately: it is not a stale attribute but a
**purview grant**, since §2.1 computes purview from exactly those rows, so an
application write path able to create one is a path that can grant somebody
oversight of a section.

**What this grain does not catch, said here so no reader has to infer it.** A
Pulse-owned writable column landing on `course`, `section` or `enrollment` later
is refused along with everything else on that table — `course.level` is already a
non-LMS column there, saved today only by being unwritable
([ADR 0015](../../docs/adr/0015-course-level-is-a-stored-generated-column.md)).
Nothing in this module asserts that ownership is *fully* enforced, and nothing in
it should be cited as if it did.
[ADR 0014](../../docs/adr/0014-lms-owned-columns-are-marked-by-a-name-prefix.md)'s
open half — an unprefixed LMS-owned column, invisible to a marker that is a name —
was closed on 2026-08-19 by
[E0-35](../../docs/tickets/e0/E0-35-the-writer-and-the-marker-nobody-routed.md),
which built the residue rather than carrying it further: on the tables in the
guarded set, `tests/unit/test_no_lms_owned_table_carries_an_unmarked_column.py`
requires every column to be marked, structural, or recorded as Pulse-owned. That
reaches those tables and no further, so a column on any other table is outside it
as it is outside this grain.

**And the other half of that ticket is the one this module cannot supply.** The
behavioural tests here call `guard_write` directly, so they assert it answers
correctly when asked; nothing here can notice a write path that never asks, which
is the objection the consequences of
[ADR 0045](../../docs/adr/0045-the-chokepoint-refuses-an-lms-owned-write-at-table-grain-plus-one-row.md)
state outright: "a caller can bypass it by not calling it".
`tests/unit/test_every_writer_of_an_lms_owned_relation_names_the_guard.py` is what
notices, by sweeping the source for a module that writes one of these relations
without calling the guard. It is a tripwire on the obvious way to write the wrong
thing and not a proof
([ADR 0069](../../docs/adr/0069-three-rules-held-by-a-docstring-are-swept-out-of-the-source.md)):
the proof-shaped instrument is a grant refusing the application role `INSERT` and
`UPDATE` on these tables, which ADR 0045 records as unavailable until E1.

**"Per column rather than once" is the last sweep below**, and it is the one that
keeps working after today: every `lms_`-prefixed column on `Base.metadata` is
checked against the refusal set, so a marked column arriving on a table nobody
added to that set fails here rather than becoming an edit path over LMS data with
nothing failing. The columns are discovered rather than listed, because a list
would need editing by the same person who forgot the table.
"""

import importlib
from typing import Any

import pytest

# SPEC §2.1's ownership list, as the tables it lands on. **Read out of the spec,
# not out of the module under test** (`docs/MISTAKES.md` entry 19): a test that
# took its expectation from `LMS_OWNED_TABLES` would be checking the constant
# against itself, and a table quietly dropped from it would take this file's
# assertion with it.
SPEC_LMS_OWNED_TABLES = ("course", "section", "enrollment")

# Tables SPEC §2.1 puts on Pulse's side of the same sentence: "Pulse-owned —
# people graph: person records (name, category) plus reports-to edges", and
# "Pulse-owned — Lead Faculty mapping". A chokepoint that refused these would
# make the admin console unable to do the job §2.1 gives it, and that failure is
# the one a refusal-only test cannot see.
PULSE_OWNED_TABLES = ("person", "lead_faculty_mapping")

# Roles a `role_assignment` row may be written with through the application. Every
# one of them is a grant of access, and every one is Pulse's to make: §2.1 builds
# the people graph "top-down in the admin console". Only the instructor link
# arrives from the LMS.
PULSE_WRITABLE_ROLES = ("LEAD_FACULTY", "CHAIR", "DEAN")

ROLE_ASSIGNMENT_TABLE = "role_assignment"
INSTRUCTOR_ROLE = "INSTRUCTOR"

LMS_PREFIX = "lms_"

# Where `AssignmentRole` might be reachable from, most likely first. E0-11's
# surface types `guard_write`'s second parameter with it and no ticket says which
# module defines it, so it is looked for rather than imported from a path this
# file would be choosing. The chokepoint itself is tried before any of these,
# since it has to name the type to annotate the parameter.
ROLE_ENUM_HOLDERS = ("app.models", "app.models.identity")

# The three refusals E0-11 defines. Their common base is what makes the chokepoint
# catchable at an entry point: a router that means to turn a refusal into a 403
# has to be able to name one exception and get all of them.
AUTHZ_ERRORS = (
    "CareIsNotComposableError",
    "OutOfPurviewError",
    "LmsOwnedWriteRefused",
)


def declarative_metadata() -> Any:
    """`Base.metadata` with every model module registered on it, or `None`.

    Answers `None` rather than raising for the reason `marked_lms_columns` below
    gives: this runs at collection time, and a collection error takes a module
    down instead of failing a test. Reached through `app.models` and not through
    one model module, because `migrations/env.py` imports the package and a module
    nobody imported is on no metadata.
    """
    try:
        importlib.import_module("app.models")
        base_module = importlib.import_module("app.models.base")
    except Exception:  # broad on purpose — reported by the assertions that use this
        return None
    base = getattr(base_module, "Base", None)
    return getattr(base, "metadata", None)


def declared_tables() -> set[str]:
    """The name of every table on `Base.metadata`."""
    metadata = declarative_metadata()
    return set(metadata.tables) if metadata is not None else set()


def marked_lms_columns() -> list[tuple[str, str]]:
    """Every `lms_`-prefixed column on `Base.metadata`, as `(table, column)`.

    Discovered at collection time so that each column is a case of its own, which
    is what the criterion's "per column rather than once" asks for. An import
    that fails answers with an empty list rather than raising: a collection error
    takes the whole module down and reads as a broken suite, and
    `test_the_metadata_walk_finds_the_marked_columns_it_sweeps` below is what
    turns the empty list into a failed assertion naming the cause.
    """
    metadata = declarative_metadata()
    if metadata is None:
        return []
    return sorted(
        (table.name, column.name)
        for table in metadata.tables.values()
        for column in table.columns
        if column.name.startswith(LMS_PREFIX)
    )


MARKED_LMS_COLUMNS = marked_lms_columns()


def assignment_role(authz: Any, name: str) -> Any:
    """The `AssignmentRole` member called `name`, wherever the enum lives.

    Looked for rather than imported under a path this file picks, and it fails
    saying so if no candidate holds it — E0-11 types `guard_write` with the enum
    and no ticket says which module defines it, so a guess here would be this
    suite deciding where a model lives.
    """
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
        f"`{name}` member. "
        "E0-11's `guard_write` takes `assignment_role: AssignmentRole | None`, so the enum has to "
        "be reachable from somewhere a caller can import it — a router calling the chokepoint "
        "needs the same value this test does. If it is spelled differently or lives elsewhere, "
        "say so in the pull request and `ROLE_ENUM_HOLDERS` in this file is the one line that "
        "changes."
    )


def permitted(authz: Any, **arguments: Any) -> None:
    """Call `guard_write` where a refusal is the failure, not the assertion.

    Both names are resolved before the call, so a module that is missing one of
    them reports *that* rather than reporting it from inside an `except` clause
    while another failure is already propagating.
    """
    guard_write = authz.guard_write
    refusals = authz.AuthzError
    try:
        guard_write(**arguments)
    except refusals as refused:
        pytest.fail(
            f"`guard_write({arguments})` was refused with {refused!r}. Refusing too much is this "
            "criterion's other failure mode and the one no denial test can see: SPEC §2.1 makes "
            "the people graph and the lead-faculty mapping Pulse's own, 'built top-down in the "
            "admin console' with 'CSV import/export', and a chokepoint that refuses them leaves "
            "§6.3's People editor unable to write anything."
        )


@pytest.mark.parametrize("table", SPEC_LMS_OWNED_TABLES)
def test_a_write_to_a_table_the_lms_owns_is_refused(authz: Any, table: str) -> None:
    """SPEC §8: "LMS-owned data is never hand-edited in Pulse."

    Four of §2.1's five owned items live on these three tables — courses,
    sections, section codes and enrollments — so refusing the table answers most
    of the ownership list without reading a column name, and catches an
    unprefixed LMS-owned column that a name-based check cannot see.

    The failure is quiet in a way worth stating: an edit here is not rejected by
    the LMS and does not error. It is overwritten at the next hourly roster sync
    (§2.1), so the symptom is a value that changes back by itself, which reads as
    a sync bug rather than as a write path that should not exist.
    """
    with pytest.raises(authz.LmsOwnedWriteRefused):
        authz.guard_write(table=table)


def test_a_write_to_the_teaching_instructor_link_is_refused(authz: Any) -> None:
    """The fifth item on §2.1's list, and the one that is a grant rather than an attribute.

    §2.1's chain is `INSTRUCTOR(section) → LEAD_FACULTY(course) → …` over **role
    assignments**, and §8 puts those on `role_assignment` — so the teaching
    instructor the LMS owns is a row on a table the application otherwise writes
    freely. A table-grained refusal over `{course, section, enrollment}` alone
    leaves an application write path able to create or edit one.

    That is the more dangerous omission of the two this grain has, because §2.1
    computes purview from exactly these rows: an invented `INSTRUCTOR` assignment
    is not a stale attribute, it is oversight of somebody's section, and it comes
    with the moderation view and the report that hang off it.

    **The control is next door**: the same table with a role the admin console is
    entitled to write. A chokepoint that refused `role_assignment` outright would
    satisfy this test and make §6.3's People editor useless.
    """
    with pytest.raises(authz.LmsOwnedWriteRefused):
        authz.guard_write(
            table=ROLE_ASSIGNMENT_TABLE,
            assignment_role=assignment_role(authz, INSTRUCTOR_ROLE),
        )


@pytest.mark.parametrize("role", PULSE_WRITABLE_ROLES)
def test_a_role_assignment_the_lms_does_not_own_is_permitted(authz: Any, role: str) -> None:
    """The control for the test above: only the instructor link is the LMS's.

    §2.1 builds the people graph in Pulse — "Built top-down in the admin console
    (a new person's reports-to selector lists only people already in the graph)" —
    and every leadership assignment in it is a row on this same table. So the
    refusal has to read the role rather than the table, and the cheapest wrong
    implementation refuses `role_assignment` outright and passes every denial test
    in this module.
    """
    permitted(authz, table=ROLE_ASSIGNMENT_TABLE, assignment_role=assignment_role(authz, role))


@pytest.mark.parametrize("table", PULSE_OWNED_TABLES)
def test_a_write_to_a_table_pulse_owns_is_permitted(authz: Any, table: str) -> None:
    """The other control, at table grain.

    SPEC §2.1 names both of these as Pulse's own in the same paragraph that names
    the LMS's: the people graph, "the LMS has no equivalent; purview is computed
    from this graph", and the Lead Faculty mapping, "maintained in the admin
    console with CSV import/export". A chokepoint that refused every write is
    fail-closed and useless, and nothing else in this file would notice.
    """
    permitted(authz, table=table)


def test_the_refusal_set_names_the_tables_the_spec_puts_on_the_lms_side(authz: Any) -> None:
    """`LMS_OWNED_TABLES` is the module's own statement of the rule, and it is checked.

    The behavioural tests above cannot say *why* a write was refused — a
    chokepoint that refused everything passes all three — and this one cannot say
    whether the refusal works. Both, not either (`docs/MISTAKES.md` entry 3): the
    constant states the rule, and the calls prove it fires.

    Every name in it is required to be a real table as well, because a typo is
    invisible from both sides: `"courses"` in the set refuses writes to a table
    that does not exist while permitting every write to the one that does, and
    the behavioural test above would be the only thing that noticed — which it
    would, but naming the typo is worth more than reporting "a write was
    permitted".
    """
    named = frozenset(authz.LMS_OWNED_TABLES)
    missing = sorted(set(SPEC_LMS_OWNED_TABLES) - named)
    assert not missing, (
        f"`LMS_OWNED_TABLES` is {sorted(named)} and does not name {missing}. SPEC §2.1's "
        "LMS-owned list is 'courses, sections, section codes, enrollments, teaching instructors', "
        "and §8 restates it as a constraint: 'LMS-owned data is never hand-edited in Pulse.'"
    )

    declared = declared_tables()
    assert declared, (
        "`Base.metadata` holds no tables, or the model package could not be imported, so the "
        "assertion below would pass against a set naming nothing real. E0-05 registers the "
        "containment tables and `tests/unit/test_org_models_registered.py` diagnoses their "
        "absence."
    )

    invented = sorted(named - declared)
    assert not invented, (
        f"`LMS_OWNED_TABLES` names {invented}, which are not tables on `Base.metadata` (it holds "
        f"{sorted(declared)}). A name that matches nothing refuses nothing: the guard reads as "
        "present in review, and the real table stays writable."
    )


def test_the_metadata_walk_finds_the_marked_columns_it_sweeps() -> None:
    """The canary for the parametrised sweep below, which is otherwise silent when empty.

    A parametrisation over an empty list collects zero tests and reports green,
    which is `docs/MISTAKES.md` entry 3 in the form a sweep takes: the assertion
    that every marked column sits on a refused table is most thoroughly satisfied
    by finding no marked columns at all. E0-05 marks `course.lms_number`,
    `course.lms_title` and `section.lms_section_code`, so the walk has to find
    something before its silence is allowed to mean anything.
    """
    assert MARKED_LMS_COLUMNS, (
        f"No column on `Base.metadata` starts with `{LMS_PREFIX}`, or the model package could not "
        "be imported at collection time. Either way the sweep below ran no cases and reported "
        "success. E0-05 ships three marked columns and "
        "`tests/unit/test_lms_owned_column_marker.py` is where their absence is diagnosed."
    )


@pytest.mark.parametrize(("table", "column"), MARKED_LMS_COLUMNS)
def test_every_column_marked_lms_owned_sits_on_a_table_the_chokepoint_refuses(
    authz: Any, table: str, column: str
) -> None:
    """ "The refusal is asserted per column rather than once" — the half that ages well.

    Under table grain the check a column can be put to is this one: the table it
    sits on is refused. That fails the day a marked column lands on a table nobody
    added to the refusal set, which is the failure worth having — ADR 0014's
    marker is "in front of whoever writes the query", so the column arrives
    correctly marked and the *set* is what goes stale.

    **If this is red for `user.lms_user_id`, it is a question for the ticket and
    not a line to add to the set.** SPEC §2.1's ownership list does not name the
    user record, and §4 does: responses are "keyed to the LMS user ID (`sub` from
    the launch)", which the launch and the roster sync write and Pulse never
    edits. Refusing the table would be consistent with the grain and would have to
    be reconciled with the launch path that creates the row; exempting it would be
    the first hole in a rule whose whole value is that it has none. E0-11 is
    required to "say what the chosen grain does not catch", and this is the case
    where that sentence has to be written before the code is.
    """
    refused = frozenset(authz.LMS_OWNED_TABLES)
    assert table in refused, (
        f"`{table}.{column}` carries the `{LMS_PREFIX}` marker and `{table}` is not in "
        f"`LMS_OWNED_TABLES` ({sorted(refused)}). ADR 0014 says what the prefix means: the LMS "
        "supplies the value and Pulse never writes it. So either the chokepoint has a table it "
        "does not know about — an application write path over LMS-owned data, with nothing "
        "failing, which is the exact shape of `docs/MISTAKES.md` entry 2 — or this column is "
        "marked and should not be. Both are answers; neither is silence."
    )


@pytest.mark.parametrize("name", AUTHZ_ERRORS)
def test_every_refusal_the_chokepoint_raises_is_catchable_as_one_error(
    authz: Any, name: str
) -> None:
    """One base class, so an entry point can turn any refusal into one answer.

    E0-11 makes this module "the single chokepoint every entry point passes
    through — HTTP, Celery jobs, and the future MCP server". Each of those has to
    turn a refusal into something a caller sees, and a refusal that escapes the
    `except AuthzError` somebody wrote is a 500 with a stack trace — or, in a
    Celery task, a retry loop over a decision that will never change.
    """
    error = authz.symbol(name)

    assert isinstance(error, type) and issubclass(error, authz.AuthzError), (
        f"`{name}` is {error!r}, which does not subclass `AuthzError`. The chokepoint's refusals "
        "are one family on purpose: an entry point catches the base and answers, and a sibling "
        "outside it is the one that reaches a user as an unhandled error."
    )
