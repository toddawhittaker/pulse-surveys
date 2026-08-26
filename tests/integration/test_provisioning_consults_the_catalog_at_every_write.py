"""Each guarded write asks the guard, not just the module — ticket E1-10.

E0-35's sweep asks whether a module *names* `guard_write` anywhere in it, and
[ADR 0069](../../docs/adr/0069-three-rules-held-by-a-docstring-are-swept-out-of-the-source.md)
states the limit in as many words: "the grain is the module, not the path. A
module that guards one function and writes in another passes here." E1-10 is the
first ticket where that limit costs something, because its writer writes three
guarded tables from one module — so a `provisioning.py` that guards `user` and
writes `course` unguarded is, to that sweep, the same file as one that guards all
three.

**Measured rather than reasoned about.** E1-10's mutation battery deleted
`guard_write(table="course", sanction=…)` from the site that upserts a course and
the whole suite stayed green: 1683 passed. Deleting all three calls *was* caught,
by the sweep, which is what makes this per-site routing rather than routing at
all. Nothing behavioural saw the single deletion either, and the reason is worth
stating because it is the reason a second sweep would not have helped: the
sanction the launch writer holds grants `course`, so a write that skips the guard
and a write the guard permits produce the same row.

**So the catalog is narrowed instead.** Each test below removes one table from
`launch_provisioning`'s entry in `authz.SANCTIONED_WRITERS`, drives an ordinary
staff launch, and requires the row not to appear. A site that consults the guard
is refused; a site whose `guard_write` call has been deleted writes the row
regardless of what the catalog says, which is the difference this file exists to
see. The mutation each one kills is named in its own message.

**Why this is not a second sweep.** A syntactic check per write site would have to
decide what a "write site" is, which is the thing ADR 0069 already declined to do
for good reasons — it would fail a refactor that moved a write into a private
helper, and pass a write assembled at run time. Narrowing the catalog asks the
running code the question directly, and it asks it about the one property that
matters: that this particular write consulted this particular grant.

**The near miss is not duplicated here.** "With the catalog intact the same launch
writes the row" is already asserted, per table, in
`tests/integration/test_launch_time_provisioning.py`; each test below names the
one that covers it rather than driving a second launch to prove the same thing.
Without those, every assertion here would be equally true of a writer that writes
nothing at all — which is what `test_a_catalog_that_grants_this_writer_nothing_
stops_every_write` at the foot of this file is the standing control for.
"""

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# The three tables `launch_provisioning`'s catalog entry grants, which are the
# three write sites this file is about. Read from the entry itself in each test
# before it is narrowed, so this tuple decides which cases run and never decides
# what the catalog holds — `tests/unit/test_a_sanctioned_writer_satisfies_the_
# chokepoint.py` is where the catalog's contents are pinned.
GUARDED_WRITES = ("course", "section", "user")

LAUNCH_PROVISIONING = "launch_provisioning"

# The catalog constant `guard_write` consults, by the name E1-10's work order
# settles: "`SANCTIONED_WRITERS: Mapping[str, frozenset[str]]` in authz.py".
CATALOG = "SANCTIONED_WRITERS"

# Which existing test proves the *other* direction for each table — that with the
# catalog intact this same launch does write the row. Cited rather than repeated:
# a second launch here would assert what those already assert, and the pair is
# what makes a refusal mean the catalog rather than mean a writer that does
# nothing.
PROVED_TO_HAPPEN_BY = {
    "course": "test_a_staff_launch_creates_the_course_its_context_label_names",
    "section": "test_a_staff_launch_creates_the_section_with_the_calendar_its_terms_map_gives_it",
    "user": "test_a_launch_creates_the_launching_subjects_user_row_once",
}


def catalog_without(authz: Any, table: str | None) -> dict[str, frozenset[str]]:
    """The real catalog with one table — or every table — taken out of one writer's entry.

    Built from the catalog the module actually holds rather than written down
    here, so this file cannot drift from it and cannot quietly decide what it
    contains (`docs/MISTAKES.md` entry 19). Every other writer's entry is carried
    across untouched, because the subject is one grant and not the mechanism.

    `table=None` empties `launch_provisioning`'s table set and leaves the writer
    itself in place. That is deliberately not the same as deleting the key:
    `sanction_for` raises for a writer the catalog does not name, and what
    provisioning does with that exception is not something this ticket settles —
    so the narrowing is expressed as a grant of nothing, which every write site is
    required to consult and be refused by.
    """
    held = {writer: frozenset(tables) for writer, tables in dict(authz.SANCTIONED_WRITERS).items()}
    granted = held.get(LAUNCH_PROVISIONING, frozenset())
    held[LAUNCH_PROVISIONING] = frozenset() if table is None else granted - {table}
    return held


def narrow_the_catalog(monkeypatch: Any, authz: Any, table: str | None) -> None:
    """Replace `SANCTIONED_WRITERS` on the module the running application imported.

    `authz.module` resolves through `sys.modules`, and `tool_doors` has already
    imported the application by the time a test body runs, so this is the same
    module object the request path calls `guard_write` on. `guard_write` reads the
    catalog as a module global, so replacing the attribute is enough — and if it
    ever stops being enough, the control at the foot of this file is what says so
    rather than every test here quietly passing.
    """
    monkeypatch.setattr(authz.module, CATALOG, catalog_without(authz, table))


def require_granted(authz: Any, table: str) -> None:
    """The catalog grants `table` to this writer *before* the narrowing.

    Without this the narrowing can be a no-op — a table the entry never held is a
    table removing it changes nothing about — and "no row was written" would be
    asserted against an unmodified system. `docs/MISTAKES.md` entry 3 in the form
    a patch takes.
    """
    granted = frozenset(dict(authz.SANCTIONED_WRITERS).get(LAUNCH_PROVISIONING, ()))
    assert table in granted, (
        f"`{CATALOG}[{LAUNCH_PROVISIONING!r}]` is {sorted(granted)} and does not grant {table!r}, "
        "so removing it changes nothing and this test would be driving an ordinary launch against "
        "an unmodified catalog. The catalog's contents are pinned in "
        "`tests/unit/test_a_sanctioned_writer_satisfies_the_chokepoint.py`, which is where a "
        "genuine change to them is recorded."
    )


def launch_reporting_an_escape(driver: Any, offer: Any) -> tuple[Any, BaseException | None]:
    """Drive a staff launch, answering the response, or the exception that escaped instead.

    Answering rather than raising, so that the assertion this file is about — the
    row did not appear — is made either way. A guard refusal that escapes the
    request is a real outcome to report and it is not the subject: the write
    still did not happen, which is what these tests claim, and the landing is
    asserted separately with a message that says which of the two failed.
    """
    try:
        response, _ = driver.launch(offer)
    except Exception as escaped:
        return None, escaped
    return response, None


def assert_the_write_did_not_happen(rows: Any, table: str, when: str) -> None:
    """Nothing at all is in `table` — the forbidden state, over the whole table.

    Over the whole table rather than filtered by the key the writer was supposed
    to use, because a refused write and a write stored under a key this test did
    not predict are different failures and only one of them is the subject.
    `launch_ground` seeds no course, no section and no user, so an empty table is
    exact rather than approximate.
    """
    stored = rows.all_of(table)
    assert not stored, (
        f"A staff launch wrote {stored} into `{table}` {when}.\n\n"
        f"`guard_write(table={table!r}, sanction=…)` consults `authz.{CATALOG}`, and this test "
        f"took {table!r} out of `{LAUNCH_PROVISIONING}`'s entry before launching. A write that "
        "happened anyway is a write that never asked — the site in "
        "`app.services.provisioning` that writes this table is not routed through the guard, "
        "whatever else in the module is.\n\n"
        "**This is the mutation this test exists to kill**: deleting "
        f"`guard_write(table={table!r}, sanction=…)` from the site that writes {table!r}. E1-10's "
        "mutation battery made exactly that deletion for `course` and the whole suite stayed "
        "green, because the E0-35 sweep's grain is the module — a file that guards one write and "
        "not another passes it (ADR 0069) — and because the sanction permits the table anyway, so "
        "nothing behavioural could tell the two apart until the grant was narrowed.\n\n"
        f"The other direction is `{PROVED_TO_HAPPEN_BY[table]}` in "
        "`tests/integration/test_launch_time_provisioning.py`: with the catalog intact, this same "
        "launch writes this row. Both, not either — without it, a refusal here would be equally "
        "true of a writer that writes nothing at all."
    )


@pytest.mark.parametrize("table", GUARDED_WRITES)
def test_a_write_whose_table_the_catalog_no_longer_grants_does_not_happen(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    authz: Any,
    monkeypatch: pytest.MonkeyPatch,
    table: str,
) -> None:
    """Per write site, not per module: this table's write consults this table's grant.

    An ordinary staff launch into a fully seeded environment — prefix, a term
    containing today, a start-letter map row for this code — with one table
    removed from `launch_provisioning`'s catalog entry. Everything else about the
    launch is what `test_a_staff_launch_creates_the_course_its_context_label_names`
    drives, and the only difference is the grant.

    **The mutation each case kills**, named per table because that is what the
    battery found: deleting `guard_write(table="<table>", sanction=…)` from the
    site in `app.services.provisioning` that writes it. That deletion leaves the
    module still naming the guard, so the E0-35 sweep passes it; leaves the row
    identical, because the sanction permits the table; and is invisible to every
    other test in this ticket's suite. Measured, on `course`: 1683 passed.

    **What is asserted is the forbidden state**, and it is asserted first. The
    table stays empty. Whether the refusal reaches the person as a landing or as
    an error is the second assertion and it is separate, so a failure says which
    of the two happened rather than reporting one as the other.

    **The near miss is next door**, cited rather than repeated — see
    `PROVED_TO_HAPPEN_BY`. A test that only ever narrowed the catalog would be
    satisfied by a writer that never writes.
    """
    require_granted(authz, table)
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    launch_ground(label)

    narrow_the_catalog(monkeypatch, authz, table)
    response, escaped = launch_reporting_an_escape(launch_driver, offer)

    assert_the_write_did_not_happen(
        provisioned_rows, table, f"with {table!r} removed from the catalog's grant"
    )
    assert escaped is None, (
        f"The write to `{table}` did not happen, which is this test's subject and holds — but the "
        f"refusal escaped the launch request as {escaped!r}. E1-10's work order: a provisioning "
        "refusal 'NEVER fails the launch or the person's landing: the write is skipped, the "
        "defect row is written and committed'. A `LmsOwnedWriteRefused` that reaches the door "
        "turns a data-quality problem into a person who cannot get in, and it does it on the one "
        "path where the guard is working."
    )
    launch_driver.landed(
        response, f"an instructor's launch whose {table!r} write the catalog no longer grants"
    )


def test_a_catalog_that_grants_this_writer_nothing_stops_every_write(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    authz: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control on this file's own machinery: the patch is visible to `guard_write`.

    **A red here means these tests are broken, not that the code is.** Every
    assertion in this module rests on one mechanism — replacing a module attribute
    and having the guard read the replacement — and that mechanism has two ways to
    be silently useless. `guard_write` could read the catalog from somewhere other
    than its module global, a closure or a default argument, in which case the
    narrowing reaches nothing; or the module this test patches could be a
    different object from the one the running application imported, which is the
    ordinary hazard of a repository where three packages are called `app`
    (SPEC §13). Under either, every test above passes for having changed nothing.

    So the same launch is driven with `launch_provisioning` granted **no tables at
    all**, and all three writes have to stop. If any row appears, the patch did not
    reach the guard.

    **The writer's key is left in the catalog and only its table set is emptied.**
    Deleting the key outright would make `sanction_for` raise — which is its
    documented behaviour, asserted in
    `tests/unit/test_a_sanctioned_writer_satisfies_the_chokepoint.py` — and what
    provisioning does with that exception is not something E1-10 settles. A grant
    of nothing poses the question this control is actually asking: every site
    consults the catalog, and the catalog now permits none of them.

    It also generalises the three tests above into one statement about the
    mechanism rather than three about particular tables: a catalog nobody can
    widen silently is only worth having if narrowing it is what the writer obeys.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    launch_ground(label)
    for table in GUARDED_WRITES:
        require_granted(authz, table)

    narrow_the_catalog(monkeypatch, authz, None)
    response, escaped = launch_reporting_an_escape(launch_driver, offer)

    stored = {table: provisioned_rows.all_of(table) for table in GUARDED_WRITES}
    written = {table: rows for table, rows in stored.items() if rows}
    assert not written, (
        f"With `{LAUNCH_PROVISIONING}` granted no tables at all, a staff launch still wrote "
        f"{written}.\n\n"
        "This is the control for every test in this module, and it has failed, so those tests "
        "are the thing to fix rather than the code. Either `guard_write` does not read "
        f"`authz.{CATALOG}` as a module global — a closure or a default argument would make this "
        "patch reach nothing — or the module patched here is not the one the running application "
        "imported, which is the standing hazard of three packages named `app` (SPEC §13). Until "
        "this is green, a pass anywhere above means only that the narrowing changed nothing."
    )
    assert escaped is None, (
        f"No row was written, which is what this control asks — but the refusal escaped the "
        f"launch request as {escaped!r}, so the machinery works and the launch does not survive "
        "it. E1-10's work order: a provisioning refusal never fails the launch or the person's "
        "landing."
    )
    launch_driver.landed(response, "an instructor's launch whose writer is granted nothing")
