"""An applied import leaves one `IMPORT_APPLIED` row carrying the diff the dry run answered — E9-06 fix round, Q1 (a) to (d).

SPEC §8: "`audit_log` is append-only and includes all re-identifications,
imports (with their dry-run diffs), and admin config edits." The fix round: the
apply calls `admin_record_import(actor, kind, diff)` inside its own transaction,
after the writes and before the commit, so one row names the session's admin,
the kind (`people` or `lead_mappings`) and "the dry run's response body's diff
member as JSON"; a dry run, and an apply that is refused or fails, leave none.

**Driven over HTTP on the built application** (`people_editor`, `pulse_app`'s
production connection; `docs/MISTAKES.md` entries 46 and 47), and read back with
the bootstrap identity. Each test's admin is minted for that test, so "the
admin's `IMPORT_APPLIED` rows" are this test's rows and nobody else's, and every
record an import touches was planted here (entry 31).

**What "the diff the dry run answered" is, here.** The dry run's body today
carries `added`, `changed`, `removed` and `unmapped` beside `digest`. The brief
names "the diff member"; if the body has a `diff` member, that is the diff,
otherwise it is the body without `digest`. Where the diff sits inside the row is
not settled, so the row is read whole (`to_jsonb`) and required to hold an
object carrying every member of that diff, equal
(`test_the_import_record_definer_answers_only_an_admin.holds_the_diff`). Each
diff here is non-empty, so a diff recomputed after the writes — empty — is red.

**Which failure a red is, at 09778dc5.** No apply writes an `IMPORT_APPLIED`
row, so (a), (b), and the twins of (c) and (d) fail on the row count; the
planted-failure test fails on the apply answering 200 and moving the mappings.
All FAILED on an assertion.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

import pytest
from fixtures.people_editor import PeopleEditor
from sqlalchemy import text
from test_the_import_record_definer_answers_only_an_admin import contains_value, holds_the_diff
from test_the_people_editor_imports_after_a_dry_run import (
    MAPPINGS,
    NO_DIGEST,
    PEOPLE,
    _apply,
    _csv,
    _dry_run,
    _exported,
    _Mapped,
)

from app.services.people import MAPPING_HEADER, PEOPLE_HEADER

pytestmark = pytest.mark.integration

DIFF_MEMBERS = ("added", "changed", "removed", "unmapped")

IMPORT_ROWS_OF = (
    "SELECT to_jsonb(a) AS whole, to_jsonb(a) -> 'detail' AS detail FROM public.audit_log a "
    "WHERE CAST(a.action AS text) = 'IMPORT_APPLIED' AND a.actor_person_id = CAST(:p AS uuid)"
)
MAPPING_ROWS_OF = (
    "SELECT count(*) AS n FROM public.audit_log a "
    "WHERE CAST(a.action AS text) = 'LEAD_MAPPING_CHANGED' AND a.actor_person_id = CAST(:p AS uuid)"
)


def import_rows(editor: PeopleEditor) -> list[dict[str, Any]]:
    """Every `IMPORT_APPLIED` row naming this test's admin as the actor."""
    return editor.rows(IMPORT_ROWS_OF, p=editor.admin.person_id)


def shown(body: dict[str, Any]) -> dict[str, Any]:
    """The diff the dry run answered (see the module docstring), required non-empty."""
    diff = body["diff"] if "diff" in body else {k: v for k, v in body.items() if k != "digest"}
    assert isinstance(diff, dict) and any(diff.get(member) for member in DIFF_MEMBERS), (
        f"The dry run answered {body}; this test needs a non-empty diff, or a recorded diff "
        "computed after the writes (empty) could not be told from the one the admin was shown."
    )
    return diff


def a_people_file(editor: PeopleEditor) -> str:
    """One planted person's category changed and one new person added."""
    tag = uuid4().hex[:8]
    edited = editor.person(f"Bo Adams {tag}", "Dean")
    rows = _exported(editor, PEOPLE, {str(edited)})
    assert len(rows) == 1, f"The export holds {len(rows)} rows for the planted person."
    rows[0][2] = "Lead Faculty"
    rows.append(["", f"New Person {tag}", "Department Chair"])
    return _csv(PEOPLE_HEADER, rows)


def a_file(editor: PeopleEditor, kind: str) -> tuple[str, str]:
    """(path, body) of a file with real changes, for `kind`."""
    if kind == "people":
        return PEOPLE, a_people_file(editor)
    return MAPPINGS, _Mapped(editor).edited()


def dry_then_apply(editor: PeopleEditor, path: str, body: str) -> dict[str, Any]:
    dry = _dry_run(editor, path, body)
    assert dry.status_code == 200, dry.text
    answered = dry.json()
    applied = _apply(editor, path, body, answered["digest"])
    assert applied.status_code == 200, applied.text
    return answered


# ---------------------------------------------------------------------------
# (a) and (b): the row an apply leaves.
# ---------------------------------------------------------------------------


def test_applying_a_people_file_leaves_one_import_row_with_the_dry_runs_diff(
    people_editor: PeopleEditor,
) -> None:
    """(a): one `IMPORT_APPLIED` row, the session's admin, kind `people`, the diff the dry run answered.

    **The mutations it kills:** a people apply recording nothing (today: people
    writes are unaudited, ADR 0200); two rows; the row naming anyone but the
    session's admin; the diff recomputed after the writes, or the file stored
    instead of the diff; the kind written as `lead_mappings`. **The near miss:**
    the other kind's word, which must be absent.
    """
    editor = people_editor
    body = a_people_file(editor)

    diff = shown(dry_then_apply(editor, PEOPLE, body))

    rows = import_rows(editor)
    assert len(rows) == 1, f"Applying a people file left {len(rows)} `IMPORT_APPLIED` rows."
    (row,) = rows
    assert row["detail"] is not None, "The import row's `detail` is null."
    assert holds_the_diff(
        row["whole"], diff
    ), f"The import row {row['whole']} does not hold the diff the dry run answered: {diff}."
    assert contains_value(row["whole"], "people"), f"The row {row['whole']} carries no `people`."
    assert not contains_value(
        row["whole"], "lead_mappings"
    ), f"A people import's row carries `lead_mappings`: {row['whole']}."


def test_applying_a_mapping_file_leaves_one_import_row_beside_its_per_course_rows(
    people_editor: PeopleEditor,
) -> None:
    """(b): one `IMPORT_APPLIED` row, kind `lead_mappings`, the dry run's diff — and the per-course rows still there.

    The file changes course 1's lead, unmaps course 2 and maps course 4: by ADR
    0204's consequences that is four `LEAD_MAPPING_CHANGED` rows (a changed lead
    is an unmap and a map).

    **The mutations it kills:** a mapping apply recording no import row (the
    finding); the import row written *instead of* the per-course rows; the
    diff recomputed after the writes; the kind written as `people`.
    """
    editor = people_editor
    world = _Mapped(editor)
    body = world.edited()

    diff = shown(dry_then_apply(editor, MAPPINGS, body))

    rows = import_rows(editor)
    assert len(rows) == 1, f"Applying a mapping file left {len(rows)} `IMPORT_APPLIED` rows."
    (row,) = rows
    assert row["detail"] is not None, "The import row's `detail` is null."
    assert holds_the_diff(
        row["whole"], diff
    ), f"The import row {row['whole']} does not hold the diff the dry run answered: {diff}."
    assert contains_value(
        row["whole"], "lead_mappings"
    ), f"The row {row['whole']} carries no `lead_mappings`."
    assert not contains_value(
        row["whole"], "people"
    ), f"A mapping import's row carries `people`: {row['whole']}."
    (per_course,) = editor.rows(MAPPING_ROWS_OF, p=editor.admin.person_id)
    assert per_course["n"] == 4, (
        f"The apply left {per_course['n']} `LEAD_MAPPING_CHANGED` rows; ADR 0204 makes it four "
        "(one change as an unmap and a map, one unmap, one map). The import row is beside them."
    )


# ---------------------------------------------------------------------------
# (c): a dry run records nothing.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["people", "lead_mappings"])
def test_a_dry_run_leaves_no_import_row(people_editor: PeopleEditor, kind: str) -> None:
    """(c): after a dry run, no `IMPORT_APPLIED` row; after the apply of the same file, one.

    **The mutation it kills:** the record written outside the dry run's
    rolled-back transaction (or by the dry-run route), so the log shows an
    import nobody applied. **The near miss:** the apply of the same file, which
    must leave one — so "none" is not what every request leaves.
    """
    editor = people_editor
    path, body = a_file(editor, kind)

    dry = _dry_run(editor, path, body)
    assert dry.status_code == 200, dry.text
    after_dry_run = import_rows(editor)

    applied = _apply(editor, path, body, dry.json()["digest"])
    assert applied.status_code == 200, applied.text

    assert after_dry_run == [], f"A {kind} dry run left import rows: {after_dry_run}."
    assert len(import_rows(editor)) == 1, (
        f"The {kind} apply after the dry run left {len(import_rows(editor))} import rows, not one, "
        "so the empty answer above may be what every request leaves."
    )


# ---------------------------------------------------------------------------
# (d): a refused or failed apply records nothing.
# ---------------------------------------------------------------------------


def test_an_apply_refused_as_stale_leaves_no_import_row(people_editor: PeopleEditor) -> None:
    """(d), stale digest: 409, no import row; the same file dry-run again and applied leaves one.

    **The mutations it kills:** the record written before the digest check, or
    committed on its own. **The near miss:** the fresh dry run and apply.
    """
    editor = people_editor
    world = _Mapped(editor)
    body = world.edited()
    stale = _dry_run(editor, MAPPINGS, body).json()["digest"]
    editor.mapping(person=world.leads[2], course=world.courses[3])

    refused = _apply(editor, MAPPINGS, body, stale)
    assert refused.status_code == 409, refused.text
    after_refusal = import_rows(editor)

    fresh = _dry_run(editor, MAPPINGS, body)
    assert fresh.status_code == 200, fresh.text
    assert _apply(editor, MAPPINGS, body, fresh.json()["digest"]).status_code == 200

    assert after_refusal == [], f"A stale apply left import rows: {after_refusal}."
    assert len(import_rows(editor)) == 1, "The fresh apply did not leave exactly one import row."


def test_an_apply_refused_for_a_bad_line_leaves_no_import_row(people_editor: PeopleEditor) -> None:
    """(d), a bad line: 422 naming it, no import row; a good file applied after leaves one.

    **The mutation it kills:** the record written when the file is received,
    before its lines are read. **The near miss:** the good file.
    """
    editor = people_editor
    world = _Mapped(editor)
    rows = world.exported()
    rows[2][2] = rows[2][2].upper()
    bad = _csv(MAPPING_HEADER, rows)

    refused = _apply(editor, MAPPINGS, bad, NO_DIGEST)
    assert refused.status_code == 422, refused.text
    after_refusal = import_rows(editor)

    dry_then_apply(editor, MAPPINGS, world.edited())

    assert (
        after_refusal == []
    ), f"An apply refused for a bad line left import rows: {after_refusal}."
    assert len(import_rows(editor)) == 1, "The good apply did not leave exactly one import row."


PLANTED_SQLSTATE = "E9006"


@contextmanager
def import_record_fails_for(editor: PeopleEditor, engine: Any) -> Iterator[str]:
    """A committed `BEFORE INSERT` trigger on `audit_log` raising for this admin's `IMPORT_APPLIED` rows only.

    `PeopleGraphWorld.audit_insert_fails_for`'s instrument, narrowed to the one
    action, so the apply's per-course rows still insert and only the import's
    record fails. Dropped however the block ends.
    """
    suffix = uuid4().hex[:12]
    name = f"e9_06_planted_import_failure_{suffix}"
    message = f"e9-06 planted import failure {suffix}"
    actor = editor.admin.person_id
    editor.review.rows.session.rollback()
    with engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE FUNCTION public.{name}() RETURNS trigger LANGUAGE plpgsql AS $$ "
                f"BEGIN IF NEW.actor_person_id = '{actor}'::uuid "
                "AND CAST(NEW.action AS text) = 'IMPORT_APPLIED' THEN "
                f"RAISE EXCEPTION '{message}' USING ERRCODE = '{PLANTED_SQLSTATE}'; END IF; "
                "RETURN NEW; END $$"
            )
        )
        connection.execute(text(f"REVOKE ALL ON FUNCTION public.{name}() FROM PUBLIC"))
        connection.execute(
            text(
                f"CREATE TRIGGER {name} BEFORE INSERT ON public.audit_log "
                f"FOR EACH ROW EXECUTE FUNCTION public.{name}()"
            )
        )
    try:
        yield message
    finally:
        editor.review.rows.session.rollback()
        with engine.begin() as connection:
            connection.execute(text(f"DROP TRIGGER IF EXISTS {name} ON public.audit_log"))
            connection.execute(text(f"DROP FUNCTION IF EXISTS public.{name}()"))


def test_an_apply_whose_import_record_fails_changes_no_mapping(
    people_editor: PeopleEditor, migrated_engine: Any
) -> None:
    """(d), the record fails: the apply does not answer 200 and every mapping is as it was; without the trigger it applies.

    The record is written inside the apply's transaction, after the writes and
    before the commit, so its failure takes the writes with it.

    **The mutations it kills:** the record written after the commit, or on a
    connection of its own, so an import can apply with no record; a handler
    around the record call that swallows its failure. **The near miss:** the
    same file, dry-run again and applied after the trigger is dropped, which
    succeeds and moves the mappings — so the failure was the planted one.
    """
    editor = people_editor
    world = _Mapped(editor)
    body = world.edited()
    before = world.state()
    digest = _dry_run(editor, MAPPINGS, body).json()["digest"]

    with import_record_fails_for(editor, migrated_engine):
        try:
            outcome: Any = _apply(editor, MAPPINGS, body, digest)
        except Exception as raised:  # the test client re-raises an unhandled server error
            outcome = raised
    after_failure = world.state()

    answered_ok = getattr(outcome, "status_code", None) == 200
    assert not answered_ok, (
        "The apply answered 200 while its `IMPORT_APPLIED` insert was made to fail: the record "
        "is not in the apply's transaction, or a handler swallowed its failure."
    )
    assert after_failure == before, (
        f"The import's record failed and the mappings moved from {before} to {after_failure}: the "
        "writes committed without the record."
    )
    assert import_rows(editor) == [], "An import row exists for the failed apply."

    dry_then_apply(editor, MAPPINGS, body)
    a, b, c = world.leads
    assert world.state() == [b, None, c, a], "Without the trigger the same file did not apply."
    assert len(import_rows(editor)) == 1, "The apply without the trigger left no single import row."
