"""SPEC §4.1 item 6 for the comment path — ticket E4-04, criterion 7.

> No view may ever widen a student's visibility relative to these rules.

The criterion turns that into two checkable things:

> the path takes no student-facing parameters, and a sweep proves no
> student-facing module imports it.

**Why both, and why neither alone.** The signature half makes the widening
impossible to *ask for*: a `user_id`, a `viewer`, a `subject` or an `as_student`
flag is how a report read becomes a student read — a caller fills it from the
launching student's own claim, the query narrows to one author, and a path built
to conceal becomes one that discloses on request. The sweep half makes it
impossible to *reach*: a student-facing module that imported this service could
call `visible_comments` with the section a student launched from and put a whole
week's comments on a student's own page, where SPEC §5.4 says students see "the
published comments grouped under the same two headings as everywhere else" and
only what §4 and §5.2 permit — a rule this service does not implement, because it
is written for the instructor's report.

**What the sweep can and cannot see**, stated so nothing here is cited as more
than it is (`docs/MISTAKES.md` entry 14). It reads import statements out of the
syntax tree of four named modules. It does not follow a call into a helper in a
fifth module, it cannot see a `__import__` built from a string, and its list of
student-facing modules is a list somebody maintains rather than a structure the
guarded set cannot shrink. The proof-shaped assertion for student visibility is
E8's own, when a student-facing comment surface exists to assert it about; this
is a tripwire on the obvious way to write the wrong thing, at the moment the
service that would be misused is created.

**Read out of the syntax tree, not out of the file text**, for the reason
`tests/unit/test_no_service_reads_an_identity_table_directly.py` gives: a correct
implementation is very likely to *say* `report_comments` in a docstring, because
"this never reads the instructor's comment path" is the sentence a careful author
writes next to the query. Searching the text would punish the explanation and
teach the next person to delete it.

**Marked `invariant` at the module level**, which puts it in the isolated §4.1
pass and satisfies
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`.
"""

import ast
import inspect
from pathlib import Path
from typing import Any

import pytest
from fixtures.report_comments import COMMENT_SERVICE_MODULE

pytestmark = pytest.mark.invariant

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

# The modules that serve a student, named by the records that name them. Each is
# a path a launching student's own session reaches, and none of them has any
# business reading the instructor's comment path.
#
#   - `app/api/student.py` — SPEC §13: "survey fetch/submit, loop-closure view".
#     The loop-closure view is §5.4's page, which is the student surface that
#     will one day render comments.
#   - `app/services/survey_read.py` — E2-09's assembly and FIX-01's "§4.1 read
#     path"; `tests/e2e/student-survey.spec.ts` names it as one of the two
#     services behind the student's own page.
#   - `app/services/submissions.py` — the other one it names, and E2-14's
#     confidentiality subject.
#   - `app/schemas/student.py` — FIX-01's chain, "survey_read.py -> schemas/
#     student.py -> frontend/src/api/student.ts": the contract that decides what
#     reaches a student's browser.
#
# **Each is required to exist**, and that is the control rather than a
# convenience: a sweep over four paths of which three were renamed reads exactly
# like a sweep that found nothing wrong (`docs/MISTAKES.md` entry 3).
STUDENT_FACING_MODULES = (
    "app/api/student.py",
    "app/services/survey_read.py",
    "app/services/submissions.py",
    "app/schemas/student.py",
)

# What the two reads and the cutter take, from E4-04's work order. Spelled here
# because the work order settles all three signatures; a test that discovered
# them would be asserting that the code does what it does.
SETTLED_SIGNATURES = {
    "visible": ("session", "section_id", "week_id", "stream", "rng"),
    "released": ("session", "section_id", "term_id", "stream", "rng"),
    "cut": ("session",),
}

# Samples the import reader is run against before it is believed, in both
# directions. Nothing here is executed — they are subjects for a parser.
IMPORTS_MUST_CATCH = (
    f"import {COMMENT_SERVICE_MODULE}",
    f"from {COMMENT_SERVICE_MODULE} import visible_comments",
    "from app.services import report_comments",
    f"import {COMMENT_SERVICE_MODULE} as comments",
)

# The near misses, and each is a shape a correct student module really has.
# `app.services.reporting` is SPEC §13's own module name one letter away from
# nothing, and a relative import of a *sibling* under `app.services` is how
# `submissions.py` reaches `validity.py`.
IMPORTS_MUST_ALLOW = (
    "from app.services import validity",
    "from app.services.reporting import weekly_distribution",
    "from app.schemas.student import SurveyPage",
    "import app.services.survey_read",
    # Prose, which is where this module name is *supposed* to appear.
    '"""This never reads app.services.report_comments; the instructor path is not a student one."""',
)


@pytest.fixture(autouse=True)
def _a_stated_environment(configured_env: dict[str, str]) -> None:
    """The signature test imports `app.services.report_comments`, which reaches `app.db`.

    `app.db` builds `Settings()` at module scope, so a module that imports it
    needs the environment laid down first — `docs/MISTAKES.md` entry 40, and the
    incident E3-06's unit module records: green on a developer's machine off
    `.env`, red on whichever xdist worker ran it first. Declared for the module
    rather than test by test, because the next test added here would have to
    remember.
    """


def imports_of(source: str, path: str = "<sample>") -> set[str]:
    """Every module name a source imports, from its syntax tree.

    Both statement forms are read and reduced to a dotted module name:
    `import a.b.c` and `from a.b import c`, the second joined so that
    `from app.services import report_comments` answers
    `app.services.report_comments` — which is the spelling somebody actually
    writes, and the one a reader looking only at `node.module` would miss.

    A file that does not parse is a failure of the sweep rather than a file to
    skip: it would drop silently out of the walk, and silence is what this module
    exists to stop being mistaken for compliance.
    """
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as failure:  # pragma: no cover - a broken source tree
        pytest.fail(
            f"{path} does not parse ({failure}), so this sweep cannot read its imports and would "
            "report it clean having read nothing."
        )

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def reaches_the_comment_service(source: str, path: str = "<sample>") -> bool:
    """Whether a source imports the comment service, by either statement form."""
    return any(
        name == COMMENT_SERVICE_MODULE or name.startswith(f"{COMMENT_SERVICE_MODULE}.")
        for name in imports_of(source, path)
    )


def test_the_import_reader_catches_what_it_claims_to_and_spares_what_it_must() -> None:
    """The instrument, both directions, before the tree is judged with it.

    `docs/MISTAKES.md` entry 3's rule for a matcher: run it against the text you
    claim it catches *and* against the text you claim it allows. The allow side is
    the one that costs something here — every student-facing module in this
    repository imports several `app.services.*` siblings, and a reader that fired
    on any of them would be red against every correct implementation, and the fix
    somebody reaches for is to delete the sweep.

    **The catch side's discriminating case is `from app.services import
    report_comments`.** A reader that looked only at an `ImportFrom`'s `module`
    attribute sees `app.services`, which is not the service, and reports the file
    clean — and that is the spelling somebody writing inside `app/services/` is
    most likely to use.

    **The allow side's discriminating case is the docstring.** Naming the module
    in prose is what a careful author does beside a query that deliberately does
    not use it, and a text search would turn that sentence into a failure.

    Green today: this is arithmetic on strings.
    """
    for sample in IMPORTS_MUST_CATCH:
        assert reaches_the_comment_service(sample), (
            f"The import reader found no reference to `{COMMENT_SERVICE_MODULE}` in {sample!r}, "
            "which imports it. A reader that has gone blind reads exactly like a sweep that found "
            "nothing wrong."
        )
    for sample in IMPORTS_MUST_ALLOW:
        assert not reaches_the_comment_service(sample), (
            f"The import reader read `{COMMENT_SERVICE_MODULE}` out of {sample!r}, which does not "
            "import it. Every student-facing module imports several `app.services` siblings and "
            "one of them names this module in prose; a reader that matches either is red against "
            "every correct implementation."
        )


def test_no_student_facing_module_imports_the_report_comment_service() -> None:
    """Criterion 7's sweep: the instructor's comment path is unreachable from a student path.

    This service applies SPEC §4's *instructor-side* rule — a week at or above the
    threshold returns its comments, with their moderation status. §5.4 gives a
    student a different rule: their own section only, published comments only,
    and the small-N notice in place of comments rather than a threshold test on
    the same data. A student-facing module that called `visible_comments` would
    get the instructor's answer on a student's page, including a comment §5.2
    collapses from students and shows to instructors — and there is no parameter
    it could pass to ask for anything else, which is the signature half of this
    criterion next door.

    **Each module is required to exist first.** A sweep over four paths of which
    three have been renamed judges one file and reports success
    (`docs/MISTAKES.md` entry 3), and the rename is the likelier event: this list
    is a convention, not a structure.

    **The mutation this exists to survive**: `from app.services.report_comments
    import visible_comments` added to `app/services/survey_read.py` when E8 builds
    §5.4's comment list and finds a function that already does most of it. That is
    a change somebody makes on purpose, with a ticket behind it, in a module
    nobody is auditing for this — and the answer is that E8 writes the student's
    own rule, in its own module, with its own tests.
    """
    missing = [name for name in STUDENT_FACING_MODULES if not (BACKEND_ROOT / name).is_file()]
    assert not missing, (
        f"{missing} are not in {BACKEND_ROOT.relative_to(REPO_ROOT)}, so this sweep judged fewer "
        f"modules than it names and its silence covers less than it appears to. The list is "
        "`STUDENT_FACING_MODULES` at the top of this file; a module that has been renamed is "
        "renamed here in the same change, and one that has genuinely gone away comes out with a "
        "sentence saying what serves a student instead."
    )

    offenders = sorted(
        name
        for name in STUDENT_FACING_MODULES
        if reaches_the_comment_service(
            (BACKEND_ROOT / name).read_text(encoding="utf-8"), str(BACKEND_ROOT / name)
        )
    )
    assert not offenders, (
        f"{offenders} import `{COMMENT_SERVICE_MODULE}`.\n\n"
        "SPEC §4.1 item 6: no view may ever widen a student's visibility relative to these rules, "
        "and E4-04's criterion 7 makes the sweep the enforcement. This service answers the "
        "instructor's question — a week at or above the n-threshold returns its comments with "
        "their moderation status, and §5.2 shows an instructor a flagged-collapsed comment that "
        "students never see. §5.4 gives students a different rule over the same rows, and E8 owns "
        "writing it."
    )


def test_the_comment_path_takes_no_parameter_that_could_name_a_person(
    comment_contract: Any,
) -> None:
    """Criterion 7's other half: the path takes no student-facing parameters.

    Asserted as an **equality over the parameter names** rather than as a search
    for the ones somebody thought of — a test looking for `user_id` passes against
    `viewer`, `subject`, `as_student` or `for_user`, and the widening arrives under
    whichever name the caller needed.

    A parameter this path does not have cannot be filled from a launch claim. That
    is the whole of why the signature is the assertion: the three functions take a
    section, a week or a term, a stream and a random source, and there is no
    argument position into which a person could go.

    **The mutation it kills:** `user_id: UUID | None = None` added to either read
    "so the student surface can share this code", which arrives as one optional
    keyword and is invisible to every behavioural test in this epic — the
    instructor's cases all leave it `None`.

    **A parameter *removed* is caught by the same equality, and that is
    deliberate**: E4-07's payload layer is written against this interface, and
    E4-04's work order settles it rather than leaving it to the implementer.
    """
    found = {
        "visible": comment_contract.visible(),
        "released": comment_contract.released(),
        "cut": comment_contract.cut(),
    }
    names = {
        "visible": comment_contract.visible_name,
        "released": comment_contract.released_name,
        "cut": comment_contract.cut_name,
    }

    for key, expected in SETTLED_SIGNATURES.items():
        taken = tuple(inspect.signature(found[key]).parameters)
        assert taken == expected, (
            f"`{comment_contract.service_module}.{names[key]}` takes {list(taken)} and E4-04's "
            f"work order settles {list(expected)}.\n\n"
            "SPEC §4.1 item 6: no view may ever widen a student's visibility relative to these "
            "rules. A parameter naming a person is how that happens — a caller fills it from the "
            "launching student's own claim, the query narrows to one author, and a path built to "
            "conceal becomes one that discloses on request. A parameter that does not exist cannot "
            "be filled, which is why the signature is the assertion rather than a comment."
        )
