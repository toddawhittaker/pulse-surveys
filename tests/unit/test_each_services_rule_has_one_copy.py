"""Each services rule that had copies now has one, and the copies are gone.

The question set, the course week, the course label, live-on-a-day and the staff
filter each had two or three copies under `backend/app/services/`; a copy that
drifts is one rule meaning two things (`docs/MISTAKES.md` entry 13). Every search
below first finds its pattern in the file that should hold it, so a search that
has gone blind fails rather than reporting a clean tree (`docs/MISTAKES.md`
entry 3).
"""

from pathlib import Path
from types import ModuleType

import pytest

from app.services import reporting, survey_read

SERVICES = Path(__file__).resolve().parents[2] / "backend" / "app" / "services"

# (pattern, the one file allowed to hold it, files that hold it only as a definition)
ONE_HOME = [
    ("Enrollment.started_on <=", "enrollment_windows.py", ()),
    ("section_scoped_assignees(", "enrollment_windows.py", ("authz.py",)),
]


def files_holding(pattern: str) -> set[str]:
    return {path.name for path in SERVICES.glob("*.py") if pattern in path.read_text("utf-8")}


@pytest.mark.parametrize(
    ("module", "name"),
    [
        (survey_read, "_current_question_set"),
        (survey_read, "_course_week"),
        (survey_read, "_course_label"),
        (reporting, "_course_week_of"),
    ],
)
def test_the_private_copy_is_deleted(module: ModuleType, name: str) -> None:
    assert not hasattr(module, name), (
        f"`{module.__name__}.{name}` is back; the rule it copied has one home in "
        "`section_codes` or `submissions`."
    )


@pytest.mark.parametrize(("pattern", "home", "definitions"), ONE_HOME)
def test_the_pattern_appears_only_in_its_home(
    pattern: str, home: str, definitions: tuple[str, ...]
) -> None:
    holding = files_holding(pattern)
    assert home in holding, (
        f"`{pattern}` is not found in {home}, which holds the one copy. The search has gone "
        "blind or the rule moved; either way the check below would say nothing."
    )
    for definition in definitions:
        source = (SERVICES / definition).read_text("utf-8")
        assert f"def {pattern}" in source, f"{definition} no longer defines `{pattern}`."
    strays = holding - {home} - set(definitions)
    assert (
        not strays
    ), f"`{pattern}` is written again in {sorted(strays)}; call the helper in {home}."
