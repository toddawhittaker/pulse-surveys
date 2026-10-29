"""The student's week read lives in `services/student_results.py`, and only there — E9-08.

The ticket's carried split: "The student read (`student_week_results` and its
private helpers) moves to `services/student_results.py`, as one commit that
changes no behaviour". Done-when 2: the import sweep names the new module "with
the allowance `response_loop.py` had", and `response_loop.py` leaves the sweep
"if it no longer holds the student read". The settled interface makes that
explicit: `ResultsUnavailableError` and `student_week_results` move, the new
module's `__all__` is exactly those two, and there is **no re-export** from
`response_loop`.

**Why that last part needs a test of its own** (`docs/MISTAKES.md` entry 53).
`tests/unit/test_the_report_comment_service_names_nothing_a_student_path_can_reach.py`
reads direct imports out of the one module it names. If the read stayed in
`response_loop` and the new module were a shim importing it from there, or if
`response_loop` kept a copy (or a re-export) that `api/student.py` went on
importing, the student path would run through a module the sweep no longer
watches. The real-file sweep catches the shim (the new module would import
neither student comment read); this module catches the copy left behind, from
the other side.

**Which failure a red is, before E9-08 lands:** the first test fails naming the
missing module; the second fails naming the two names `response_loop` still
holds.
"""

from importlib import import_module

import pytest

NEW_HOME = "app.services.student_results"
OLD_HOME = "app.services.response_loop"
MOVED = ("ResultsUnavailableError", "student_week_results")


@pytest.fixture(autouse=True)
def _a_stated_environment(configured_env: dict[str, str]) -> None:
    """Both services reach `app.db`, which builds `Settings()` at import (entry 40)."""


def test_the_new_module_defines_the_students_week_read_and_exports_exactly_it() -> None:
    """`student_results` defines both moved names itself, and `__all__` is exactly them.

    **The mutations this kill:** the new module as a shim (`from
    app.services.response_loop import student_week_results`), whose function's
    `__module__` is still `response_loop`; and the new module exporting more than
    the two, which is where an unreviewed second student read would arrive.
    **The near miss:** the two names, defined here.
    """
    try:
        module = import_module(NEW_HOME)
    except ModuleNotFoundError as missing:
        if missing.name != NEW_HOME:
            raise
        pytest.fail(
            f"`{NEW_HOME}` does not exist. E9-08 moves `student_week_results`, its private "
            "helpers and `ResultsUnavailableError` there, unchanged."
        )

    defined_elsewhere = {
        name: getattr(getattr(module, name, None), "__module__", None)
        for name in MOVED
        if getattr(getattr(module, name, None), "__module__", None) != NEW_HOME
    }
    assert not defined_elsewhere, (
        f"`{NEW_HOME}` does not itself define {defined_elsewhere} (name: the module each is "
        "defined in, or None when absent). The interface moves both, rather than "
        "re-exporting them."
    )
    exported = sorted(getattr(module, "__all__", ()))
    assert exported == sorted(
        MOVED
    ), f"`{NEW_HOME}.__all__` is {exported}; the interface settles exactly {sorted(MOVED)}."


def test_the_response_loop_module_no_longer_holds_the_students_week_read() -> None:
    """`response_loop` has neither moved name, as an attribute or in `__all__`.

    **The mutations this kill:** a copy left behind in `response_loop` (the move
    done as a copy, so `api/student.py` can keep its old import and the student
    path never leaves the module the sweep stopped watching), and a re-export
    kept "for compatibility". **The near miss:** `section_staff_names` and
    `section_lead_name`, which stay in `response_loop` by the interface and are
    not asked about here.
    """
    module = import_module(OLD_HOME)

    held = [name for name in MOVED if hasattr(module, name)]
    exported = sorted(set(MOVED) & set(getattr(module, "__all__", ())))

    assert not held, (
        f"`{OLD_HOME}` still holds {held}. E9-08 moves the student's week read to `{NEW_HOME}` "
        "with no re-export, so the student path runs through the module the import sweep names."
    )
    assert not exported, f"`{OLD_HOME}.__all__` still lists {exported}."
