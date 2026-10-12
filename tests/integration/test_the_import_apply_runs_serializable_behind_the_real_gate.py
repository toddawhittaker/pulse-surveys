"""The apply's writes run at SERIALIZABLE through the real admin gate, and a write landing mid-apply is refused — E9-06 fix round, Q2.

ADR 0204: "inside a `SERIALIZABLE` transaction it reads the state again, refuses
(409) if the digest differs, and otherwise applies and commits. A serialization
failure at any point is the same refusal." The finding: the gate
(`require_admin` and the revocation check) has already queried through the
request's session, so asking that session for `SERIALIZABLE` afterwards is
ignored and the apply runs at READ COMMITTED; a write landing between the digest
check and the apply's writes is then overwritten instead of refused.

**The instrument.** A SQLAlchemy `after_cursor_execute` listener on every
`Engine`, installed only for the length of one request, asks the same database
connection `current_setting('transaction_isolation')` right after each statement
it is told to watch. The apply's mapping writes go through E9-02's settled
definers (`admin_map_lead_course`, `admin_unmap_lead_course`), so a statement
naming either is one of the apply's writes; the test decides nothing about what
else the apply runs. Every request rides the built application on `pulse_app`'s
production connection through the real gate (`people_editor`; `docs/MISTAKES.md`
entries 46 and 47).

**The interleaving is deterministic**: it is triggered by the apply's first
mapping write (`before_cursor_execute`), not by a timer, and lands on another
connection after the apply's digest re-check and before any of its writes.

**Which failure a red is, at 09778dc5.** The apply runs at READ COMMITTED, so
the isolation test fails on the level it reads, and the interleaving's apply
overwrites the other write and answers 200 where 409 is required. The control
on an ordinary read is green there. All FAILED on an assertion.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fixtures.people_editor import PeopleEditor
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from test_an_applied_import_leaves_one_audit_row_with_its_dry_run_diff import import_rows
from test_the_people_editor_imports_after_a_dry_run import (
    MAPPINGS,
    _apply,
    _dry_run,
    _Mapped,
    _text,
)

pytestmark = pytest.mark.integration

MAPPING_WRITES = ("admin_map_lead_course", "admin_unmap_lead_course")
ISOLATION = "SELECT current_setting('transaction_isolation')"


def _names_a_write(statement: str) -> bool:
    return any(name in statement for name in MAPPING_WRITES)


@contextmanager
def isolation_seen(watch: Callable[[str], bool]) -> Iterator[list[tuple[str, str]]]:
    """(statement, isolation level) for each watched statement run while the block is open."""
    seen: list[tuple[str, str]] = []

    def after(conn: Any, cursor: Any, statement: str, *_rest: Any) -> None:
        if not watch(statement):
            return
        probe = cursor.connection.cursor()
        try:
            probe.execute(ISOLATION)
            seen.append((statement, str(probe.fetchone()[0])))
        finally:
            probe.close()

    event.listen(Engine, "after_cursor_execute", after)
    try:
        yield seen
    finally:
        event.remove(Engine, "after_cursor_execute", after)


def test_an_ordinary_admin_read_is_seen_at_read_committed(people_editor: PeopleEditor) -> None:
    """CONTROL — green at 09778dc5. The instrument sees an ordinary admin read, and at READ COMMITTED.

    A red here means the isolation test below measures nothing: either the
    listener does not see the application's statements, or every statement
    reads as SERIALIZABLE whatever the apply does.
    """
    editor = people_editor
    _Mapped(editor)

    with isolation_seen(lambda _statement: True) as seen:
        answer = editor.ask("GET", f"{MAPPINGS}/export")

    assert answer.status_code == 200, answer.text
    assert seen, "The listener saw no statement during an admin read: the instrument is blind."
    levels = sorted({level for _statement, level in seen})
    assert levels == ["read committed"], f"An ordinary admin read ran at {levels}."


def test_the_apply_writes_at_serializable_behind_the_real_gate(
    people_editor: PeopleEditor,
) -> None:
    """Every mapping write the apply makes runs in a SERIALIZABLE transaction.

    **The mutations it kills:** the isolation requested on a session the gate
    has already used (ignored, READ COMMITTED — the finding); the gate's
    transaction not ended before the request; `SET TRANSACTION` issued after
    the digest re-check, where PostgreSQL refuses it, or not at all. **The near
    miss:** the control above, an ordinary admin read at READ COMMITTED on the
    same instrument.
    """
    editor = people_editor
    world = _Mapped(editor)
    body = world.edited()
    digest = _dry_run(editor, MAPPINGS, body).json()["digest"]

    with isolation_seen(_names_a_write) as seen:
        applied = _apply(editor, MAPPINGS, body, digest)

    assert applied.status_code == 200, applied.text
    assert seen, (
        f"The apply made no statement naming {MAPPING_WRITES}, so there is nothing to read the "
        "isolation of. The file changes three courses."
    )
    levels = sorted({level for _statement, level in seen})
    assert levels == ["serializable"], (
        f"The apply's mapping writes ran at {levels}. ADR 0204: the apply re-reads and writes "
        "inside a SERIALIZABLE transaction."
    )


def test_a_write_landing_after_the_digest_check_refuses_the_apply_and_changes_nothing(
    people_editor: PeopleEditor,
) -> None:
    """Another write lands between the apply's re-check and its first write: 409, nothing applied, no import row.

    The file moves course 1 from lead A to lead B. Just before the apply's
    first mapping write, another connection commits course 1 to lead C. At
    SERIALIZABLE the apply's unmap of course 1 meets a row deleted since its
    snapshot and fails to serialize, which ADR 0204 makes the stale refusal; at
    READ COMMITTED it deletes C's mapping and writes B, overwriting a write the
    admin never saw.

    **The mutations it kills:** the apply at READ COMMITTED (the finding); a
    serialization failure answered as a line refusal (422) or a 500 rather than
    the stale 409; the apply's writes or its import record committed despite the
    failure. **What it does not decide:** the order of the apply's writes — the
    other write lands before the first of them, whichever it is.
    """
    editor = people_editor
    world = _Mapped(editor)
    body = world.edited()
    digest = _dry_run(editor, MAPPINGS, body).json()["digest"]
    a, b, c = world.leads
    first = world.courses[0]
    landed: dict[str, Any] = {}

    def before(conn: Any, cursor: Any, statement: str, *_rest: Any) -> None:
        if landed or not _names_a_write(statement):
            return
        landed["at"] = statement
        session = editor.review.rows.session
        try:
            session.rollback()
            session.execute(text("SET LOCAL lock_timeout = '5s'"))
            session.execute(
                text("DELETE FROM public.lead_faculty_mapping WHERE course_id = CAST(:c AS uuid)"),
                {"c": str(first)},
            )
            editor.review.graph.lead_mapping(person=c, course=first)
            editor.review.rows.commit()
        except Exception as failure:  # reported below rather than raised inside the app
            session.rollback()
            landed["failure"] = failure

    event.listen(Engine, "before_cursor_execute", before)
    try:
        refused = _apply(editor, MAPPINGS, body, digest)
    finally:
        event.remove(Engine, "before_cursor_execute", before)

    assert (
        "at" in landed
    ), f"The apply made no statement naming {MAPPING_WRITES}, so the other write never landed."
    assert "failure" not in landed, (
        f"The other write could not land before the apply's first write: {landed['failure']!r}. "
        "If the apply locks the named mappings when it re-reads them, this interleaving cannot "
        "happen and the test needs revisiting."
    )
    moved = [c, b, c, None]
    assert refused.status_code == 409, (
        f"An apply whose course was re-mapped after its digest check answered "
        f"{refused.status_code} ({refused.text}); ADR 0204 refuses it as stale (409)."
    )
    assert refused.json() == {"detail": _text("import_stale")}
    assert world.state() == moved, (
        f"After the refused apply the mappings are {world.state()}, not the other write's {moved}: "
        f"lead A was {a}, B {b}, C {c}."
    )
    assert import_rows(editor) == [], "The refused apply left an import row."
