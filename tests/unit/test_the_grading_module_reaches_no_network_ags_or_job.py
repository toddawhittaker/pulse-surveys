"""The participation formula is pure computation over the database — ticket E3-03, criterion 8.

E3-03's eighth criterion: "No network call, no AGS type, and no job import appears
in the module." The ticket's context says why the line is drawn there: "SPEC
§3.4's score, computed and nothing else: no AGS, no job, no network, no posting."
E3-04 and E3-05 own the posting and E3-06 owns the schedule, and the value of
having the arithmetic in a module none of them can reach is that the arithmetic
can be tested without any of them.

The sweep parses the module rather than searching its text, so a library named in
a docstring is not counted as a dependency and `from x import y` is counted the
same as `import x`. It is the shape
`tests/unit/test_provider_library_is_confined_to_the_gateway.py` established for
the same question one epic earlier.

**An absence is asserted, so the detector is run against what it claims to
catch** (`docs/MISTAKES.md` entry 3, and entry 35's rule that a guard which only
ever reports absence cannot say which mechanisms it can see). Two of the four
tests here are that control: a synthetic module carrying each forbidden import in
turn has to be caught, and one carrying only what this module legitimately needs
has to be allowed.

The second criterion in this file is criterion 6's other half — "with no constant
`5` anywhere in the module". The behavioural proof that the denominator follows
the question set is
`tests/integration/test_the_denominator_comes_from_the_weeks_question_set.py`,
which plants a set of a different size; this is the belt beside it, and it catches
the constant that has not been reached yet because only one set version exists.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GRADING_PATH = REPO_ROOT / "backend" / "app" / "services" / "grading.py"

# A module under `backend/app/services/` that certainly exists and certainly
# imports something, so a sweep that reads nothing says so rather than reporting a
# clean module (`docs/MISTAKES.md` entry 3).
SWEEP_CANARY = REPO_ROOT / "backend" / "app" / "services" / "clock.py"

# The three families criterion 8 names, as import roots and as dotted fragments.
#
# **Roots** are matched against the top-level package of every import: a module
# that reaches a network at all imports one of these, whatever it does with it.
# **Fragments** are matched against the whole dotted path, because the AGS client
# and the job modules are this project's own and are named rather than rooted —
# `app.jobs.tasks` shares its root with everything else here.
NETWORK_ROOTS = frozenset(
    {
        "httpx",
        "httpx2",
        "requests",
        "urllib",
        "urllib3",
        "aiohttp",
        "socket",
        "smtplib",
        "http",
        "ssl",
    }
)
JOB_ROOTS = frozenset({"celery", "kombu", "redis"})
JOB_FRAGMENTS = ("app.jobs",)

# AGS is LTI Advantage's Assignment and Grade Services. E3-04 and E3-05 build the
# client and the line item; nothing of theirs exists yet, so the words are matched
# against a module path's segments rather than against a file this ticket cannot
# know the name of — which is what makes the rule hold for whatever those tickets
# call their files.
#
# **A segment matches a word, not a substring.** `ags`, `ags_client` and
# `post_ags` are the module this refuses; `flags` is a module that merely ends in
# the same three letters, and a substring test would refuse it. The near miss is
# asserted in `test_the_detector_allows_what_the_formula_legitimately_needs`.
AGS_WORDS = ("ags", "lti", "line_item", "lineitem", "score_post")

FORBIDDEN_CATEGORIES = ("network", "ags", "job")


def segment_names(segment: str, word: str) -> bool:
    """Whether one dotted-path segment names `word`, as a whole word rather than a substring."""
    return segment == word or segment.startswith(f"{word}_") or segment.endswith(f"_{word}")


def imported_paths(source: str, *, filename: str) -> list[str]:
    """Every dotted module path one source file imports, parsed rather than searched."""
    tree = ast.parse(source, filename=filename)
    paths: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            paths.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                paths.append(node.module)
            elif node.level:
                paths.append("." * node.level)
    return paths


def forbidden_imports(source: str, *, filename: str = "<sample>") -> dict[str, list[str]]:
    """The imports in `source` that criterion 8 refuses, by category.

    Returns a mapping rather than a boolean so a failure names the import and the
    reason it is refused, instead of saying that something somewhere is wrong.
    """
    found: dict[str, list[str]] = {category: [] for category in FORBIDDEN_CATEGORIES}
    for path in imported_paths(source, filename=filename):
        lowered = path.lower()
        segments = lowered.split(".")
        root = segments[0]
        if root in NETWORK_ROOTS:
            found["network"].append(path)
        if root in JOB_ROOTS or any(fragment in lowered for fragment in JOB_FRAGMENTS):
            found["job"].append(path)
        if any(segment_names(segment, word) for segment in segments for word in AGS_WORDS):
            found["ags"].append(path)
    return {category: names for category, names in found.items() if names}


def grading_source() -> str:
    """The module's text, or a failure saying which deliverable is absent.

    A failure rather than an error, and inside the test rather than in a fixture,
    so that an unbuilt E3-03 reads as this module's own red with a sentence
    attached.
    """
    if not GRADING_PATH.is_file():
        pytest.fail(
            f"{GRADING_PATH} does not exist. E3-03's scope: 'The whole ticket is one module, "
            "`backend/app/services/grading.py` (the home SPEC §13 already names for it)', holding "
            "`participation_scores(session, section, *, settings)` and nothing that reaches a "
            "network, an AGS type or a job."
        )
    return GRADING_PATH.read_text(encoding="utf-8")


def test_the_detector_catches_each_family_criterion_eight_names() -> None:
    """The must-catch half of the control: a sample carrying each import is reported.

    Without this the assertion below is satisfied by a detector that can see
    nothing — which is exactly how a guard passes over a module full of the thing
    it was written to refuse (`docs/MISTAKES.md` entry 35).

    Each sample is written the way the import would really appear: an HTTP client
    for the network, this project's own job module for the schedule, and both
    spellings an AGS client is likely to take, since E3-04 has not named its files
    yet.
    """
    assert "network" in forbidden_imports("import httpx\n"), "A plain `import httpx` was not seen."
    assert "network" in forbidden_imports(
        "from urllib.request import urlopen\n"
    ), "A `from urllib.request import …` was not seen; the root is what makes it a network reach."
    assert "job" in forbidden_imports(
        "from app.jobs.tasks import ping\n"
    ), "An import from this project's own job module was not seen."
    assert "job" in forbidden_imports("import celery\n"), "A direct `import celery` was not seen."
    assert "ags" in forbidden_imports(
        "from app.services.ags import post_score\n"
    ), "An import of a service module named for AGS was not seen."
    assert "ags" in forbidden_imports("from app.lti.line_item import LineItem\n"), (
        "An import of a line-item type was not seen; E3-05 owns the line item and E3-03 may not "
        "name it."
    )
    assert "ags" in forbidden_imports("from app.services.ags_client import AgsClient\n"), (
        "A module whose name begins with the word — the spelling E3-04 is as likely to choose as "
        "the bare one — was not seen."
    )


def test_the_detector_allows_what_the_formula_legitimately_needs() -> None:
    """The must-allow half: the imports a pure computation over the database really has.

    A detector that refused these would make criterion 8 unsatisfiable and the
    ticket impossible — which is `docs/MISTAKES.md` entry 24's shape, a test
    asserting a property no implementation can meet. The sample is what E3-03's
    work order says the module reads: the clock, the window derivation, the
    submission path's question rule, the validity module's refused set, and the
    ORM.
    """
    sample = "\n".join(
        [
            "from dataclasses import dataclass",
            "from decimal import ROUND_HALF_UP, Decimal",
            "from uuid import UUID",
            "from sqlalchemy import select",
            "from sqlalchemy.orm import Session",
            "from app.config import Settings",
            "from app.models.survey import Response",
            "from app.services import clock",
            "from app.services.submissions import current_questions",
            "from app.services.survey_windows import windows_for_section",
            "from app.services.validity import REFUSED_VERDICTS",
            "",
        ]
    )
    assert forbidden_imports(sample) == {}, (
        f"The detector refuses {forbidden_imports(sample)} in a module doing exactly what E3-03's "
        "work order describes. Every one of those is something the formula has to read."
    )
    assert forbidden_imports("from app.models.flags import Flag\n") == {}, (
        "A module whose name merely ends in the same three letters as AGS is refused. The word "
        "test exists so that a real module named `flags`, `multi` or `messages` is not read as an "
        "AGS or LTI import."
    )


def test_the_grading_module_imports_no_network_ags_or_job_name() -> None:
    """Criterion 8, over the module itself.

    **The mutations this kills:** an AGS type imported "just for the annotation" on
    a return value, which makes the arithmetic untestable without a platform; a
    Celery task imported so the module can enqueue its own re-post, which is
    E3-06's job and would make every call to the formula a side effect; and an
    HTTP client, which turns a pure function into something that can time out
    inside a gradebook sync.

    The canary is read first: a sweep that cannot see any import at all in a module
    that certainly has several is broken, and would report this module clean
    whatever it holds.
    """
    canary = SWEEP_CANARY.read_text(encoding="utf-8") if SWEEP_CANARY.is_file() else ""
    assert imported_paths(canary, filename=str(SWEEP_CANARY)), (
        f"This sweep read no imports at all from {SWEEP_CANARY}, which E2-04 shipped and which "
        "certainly imports several. That is a defect in the sweep rather than a clean tree, and "
        "everything it says below is a statement it is not in a position to make."
    )

    found = forbidden_imports(grading_source(), filename=str(GRADING_PATH))

    assert found == {}, (
        f"`{GRADING_PATH.relative_to(REPO_ROOT)}` imports {found}. E3-03's eighth criterion: no "
        "network call, no AGS type and no job import appears in the module. Posting is E3-04's and "
        "E3-05's, the schedule is E3-06's, and the whole value of keeping them out is that the "
        "formula can be measured without a platform."
    )


def test_the_grading_module_holds_no_literal_question_count() -> None:
    """Criterion 6's other half: no constant `5` anywhere in the module.

    SPEC §3.4: the week's total "is never a constant: the set is versioned
    precisely so a week's item count can change, and a formula holding a literal
    count would be wrong the first time it does."

    **The mutation this kills** is the one the system cannot currently notice: a
    denominator written as `5`, or a `QUESTIONS_PER_WEEK = 5` beside it, is correct
    against every question set that exists today and wrong the day E2's versioned
    table gets its second row. The behavioural pair in
    `test_the_denominator_comes_from_the_weeks_question_set.py` is the primary
    proof; this catches the constant that is present but not yet reachable — a
    fallback for a missing set, say, or a default argument.

    Integer literals only. A `5` inside a docstring or a comment is prose and is
    not read here.
    """
    tree = ast.parse(grading_source(), filename=str(GRADING_PATH))
    literals = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, int) and node.value == 5
    ]
    assert literals == [], (
        f"`{GRADING_PATH.relative_to(REPO_ROOT)}` holds the integer literal 5 on line(s) "
        f"{[node.lineno for node in literals]}. SPEC §3.2's set has five questions today and the "
        "table is versioned so that it need not tomorrow; the denominator comes from the set."
    )
