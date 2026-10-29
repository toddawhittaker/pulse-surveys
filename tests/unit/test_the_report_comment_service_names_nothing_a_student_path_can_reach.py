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
than it is (`docs/MISTAKES.md` entry 14). It reads **direct** import statements
out of the syntax tree of the named modules, absolute and relative alike. It does
not follow a call into a helper in another module, it cannot see a `__import__`
built from a string, and its list of student-facing modules is a list somebody
maintains rather than a structure the guarded set cannot shrink (entry 53's
disclosed limit). It is a tripwire on the obvious way to write the wrong thing.
**The proof-shaped assertions for student visibility are behavioural, and are
E8-01's**: what a student's page carries under the hold, by status, below the
threshold, in a batch and across the sequence of pages —
`tests/integration/test_a_held_week_serves_nothing_about_the_week_and_reaches_no_other_page.py`,
`test_only_published_and_kept_comments_reach_a_student.py`,
`test_a_students_stream_below_the_threshold_carries_its_small_n_state_and_no_comment_text.py`,
`test_the_release_group_shows_on_the_latest_week_only_and_only_what_was_cut_before_it_opened.py`
and `test_the_students_comment_reads_go_through_the_comment_view_and_never_the_answer_table.py`.

**Since E8-01 there is one student path that reads comments, and it is named.**
`app/services/student_results.py` serves the student's week (SPEC §5.4) — E9-08
moved that read out of `app/services/response_loop.py`, which leaves this sweep
with it, and the allowance moved unchanged — and it
reaches the comment service for exactly the two reads written for students —
`student_comments` and `student_released_comments`, which filter the
instructor's reads to `published` and `kept` and return text and stream only —
and nothing else from that module, and nothing from `app.services.moderation`.
The four modules above it keep the stricter rule: no import of either at all.

**Read out of the syntax tree, not out of the file text**, for the reason
`tests/unit/test_no_service_reads_an_identity_table_directly.py` gives: a correct
implementation is very likely to *say* `report_comments` in a docstring, because
"this never reads the instructor's comment path" is the sentence a careful author
writes next to the query. Searching the text would punish the explanation and
teach the next person to delete it.

**Marked `invariant` at the module level**, which puts it in the isolated §4.1
pass and satisfies
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`.

**Since E6-09 the same sweep watches `app.services.moderation` as well** (its
done-when 10), with planted imports of its own; the signature half stays the
comment path's alone.
"""

import ast
import importlib
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
#
# **`rng` is gone from both reads, and its absence is part of the assertion now.**
# It was a public parameter in the first draft and the security round removed it:
# a seed a caller can supply is a seed an attacker can fix, and a fixed seed makes
# two reads of one week produce the same permutation — so diffing them re-derives
# the order the rows arrived in, which with no `ORDER BY` under it is heap order,
# which is insertion order, which is who answered first. The source is `_make_rng`,
# private to the module, and
# `tests/integration/test_the_comment_order_is_randomized_rather_than_stored.py`
# is where it is driven and where the refusal of an `rng=` argument is asserted.
SETTLED_SIGNATURES = {
    "visible": ("session", "section_id", "week_id", "stream"),
    "released": ("session", "section_id", "term_id", "stream"),
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

# **The moderation service is watched too, since E6-09** (done-when 10). The E6
# boundary review found that `app.services.moderation` — which holds the
# decision service and the exclusion log (E6-03, E6-05, E6-08), reads of flagged
# text a student never sees — was reachable from these four modules with nothing
# to say so. Same reader, same
# four modules, its own planted samples.
MODERATION_SERVICE_MODULE = "app.services.moderation"

MODERATION_IMPORTS_MUST_CATCH = (
    f"import {MODERATION_SERVICE_MODULE}",
    f"from {MODERATION_SERVICE_MODULE} import route_verdict",
    "from app.services import moderation",
    f"import {MODERATION_SERVICE_MODULE} as moderation",
)

# The near misses: a sibling whose name *starts* with the service's (a prefix
# match on the bare string would take it), the copy module whose name ends in
# `moderation`, and prose.
MODERATION_IMPORTS_MUST_ALLOW = (
    "from app.services.moderation_rules import something",
    "from app.copy import leadership_moderation",
    "from app.services import validity",
    '"""Students never reach app.services.moderation; this page shows published text only."""',
)

# **E8-01's one named caller** (done-when 8), its package, and what it may take
# from the comment service: the two reads written for students, and nothing else.
# Since E9-08 (its done-when 2) the caller is `student_results.py`, the module the
# student's week read moved into, with the allowance `response_loop.py` had.
# **Direct imports only**, so a re-export does not satisfy this: the real-file test
# below requires the two reads to be imported *by this module*, and a student read
# that reached them through `response_loop` would show neither (`docs/MISTAKES.md`
# entry 53).
STUDENT_COMMENT_CALLER = "app/services/student_results.py"
SERVICES_PACKAGE = "app.services"
ALLOWED_FROM_THE_COMMENT_SERVICE = frozenset({"student_comments", "student_released_comments"})

# What the allowance reader reports for an import of the whole module, which
# reaches every function in it and so is never inside an allowance of names.
THE_WHOLE_MODULE = "<the whole module>"

# The planted imports into the named caller (`student_results`), each a breach:
# the instructor's two card reads by name (done-when 8's own plants), one beside
# an allowed name, one hiding under an allowed name's alias, a star, the module by
# both spellings, and the relative spellings a module inside `app/services/` is
# likeliest to use.
CALLER_IMPORTS_MUST_REFUSE = (
    "from app.services.report_comments import visible_cards",
    "from app.services.report_comments import released_cards",
    "from app.services.report_comments import student_comments, visible_cards",
    "from app.services.report_comments import released_cards as student_released_comments",
    "from app.services.report_comments import *",
    "from app.services import report_comments",
    "import app.services.report_comments",
    "from .report_comments import visible_cards",
    "from . import report_comments",
    "from app.services import moderation",
    "from app.services.moderation import route_verdict",
    "from .moderation import route_verdict",
    "import app.services.moderation",
)

# The near misses: the two allowed reads, together, alone, aliased, relative, and
# prose naming everything the plants import.
CALLER_IMPORTS_MUST_ALLOW = (
    "from app.services.report_comments import student_comments, student_released_comments",
    "from app.services.report_comments import student_comments",
    "from .report_comments import student_released_comments",
    "from app.services.report_comments import student_comments as read_the_week",
    "from app.services import reporting, survey_read",
    "from app.services.moderation_rules import something",
    '"""Never visible_cards from app.services.report_comments, nor app.services.moderation."""',
)

# The two student reads' signatures. The ticket: "a section, a week or term, a
# stream and, for the released read, an as-of instant"; the work order (decision
# 3) names the instant `as_of`; the rest are spelled as the two reads they filter
# already spell them (`SETTLED_SIGNATURES` above).
STUDENT_READ_SIGNATURES = {
    "student_comments": ("session", "section_id", "week_id", "stream"),
    "student_released_comments": ("session", "section_id", "term_id", "stream", "as_of"),
}


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


def parsed(source: str, path: str) -> ast.Module:
    """A source's syntax tree, or a failure of the sweep.

    A file that does not parse is a failure of the sweep rather than a file to
    skip: it would drop silently out of the walk, and silence is what this module
    exists to stop being mistaken for compliance.
    """
    try:
        return ast.parse(source, filename=path)
    except SyntaxError as failure:  # pragma: no cover - a broken source tree
        pytest.fail(
            f"{path} does not parse ({failure}), so this sweep cannot read its imports and would "
            "report it clean having read nothing."
        )


def package_of(name: str) -> str:
    """The dotted package a backend file sits in: `app/services/x.py` is in `app.services`."""
    return ".".join(Path(name).with_suffix("").parts[:-1])


def module_named_by(node: ast.ImportFrom, package: str | None) -> str | None:
    """The absolute module a `from … import` names, resolving a relative one against `package`.

    **Since E8-01**: `from .report_comments import visible_cards` is the spelling a
    module inside `app/services/` is likeliest to use, and a reader that skipped
    every relative import read it as nothing (the enclosure one level out,
    `docs/MISTAKES.md` entry 53). With no package — a sample — a relative import
    is left unresolved, which the samples that need one supply.
    """
    if node.level == 0:
        return node.module
    if package is None:
        return None
    parts = package.split(".")
    base = parts[: len(parts) - (node.level - 1)]
    return ".".join([*base, node.module] if node.module else base)


def imports_of(source: str, path: str = "<sample>", package: str | None = None) -> set[str]:
    """Every module name a source imports, from its syntax tree.

    Both statement forms are read and reduced to a dotted module name:
    `import a.b.c` and `from a.b import c`, the second joined so that
    `from app.services import report_comments` answers
    `app.services.report_comments` — which is the spelling somebody actually
    writes, and the one a reader looking only at `node.module` would miss.
    Relative imports are resolved against `package` (see `module_named_by`).
    """
    found: set[str] = set()
    for node in ast.walk(parsed(source, path)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = module_named_by(node, package)
            if module is not None:
                found.add(module)
                found.update(f"{module}.{alias.name}" for alias in node.names)
    return found


def reaches(source: str, module: str, path: str = "<sample>", package: str | None = None) -> bool:
    """Whether a source imports `module` (or anything under it), by either statement form."""
    return any(
        name == module or name.startswith(f"{module}.")
        for name in imports_of(source, path, package)
    )


def taken_from(
    source: str, module: str, path: str = "<sample>", package: str | None = None
) -> set[str]:
    """The names a source takes from `module`, or `THE_WHOLE_MODULE` for an import of all of it.

    `from module import a, b` takes `a` and `b` — the names *imported*, not the
    aliases they are bound to, so `released_cards as student_released_comments`
    takes `released_cards`. Every other way of reaching the module (`import
    module`, `from parent import module`, a star) takes the whole of it.
    """
    taken: set[str] = set()
    for node in ast.walk(parsed(source, path)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module or alias.name.startswith(f"{module}."):
                    taken.add(THE_WHOLE_MODULE)
        elif isinstance(node, ast.ImportFrom):
            named = module_named_by(node, package)
            if named is None:
                continue
            for alias in node.names:
                if named == module:
                    taken.add(THE_WHOLE_MODULE if alias.name == "*" else alias.name)
                elif named.startswith(f"{module}.") or f"{named}.{alias.name}" == module:
                    taken.add(THE_WHOLE_MODULE)
    return taken


def caller_breaches(
    source: str, path: str = "<sample>", package: str = SERVICES_PACKAGE
) -> list[str]:
    """What the named caller takes beyond its allowance: comment-service names, or moderation."""
    taken = taken_from(source, COMMENT_SERVICE_MODULE, path, package)
    breaches = sorted(name for name in taken if name not in ALLOWED_FROM_THE_COMMENT_SERVICE)
    if reaches(source, MODERATION_SERVICE_MODULE, path, package):
        breaches.append(MODERATION_SERVICE_MODULE)
    return breaches


def reaches_the_comment_service(
    source: str, path: str = "<sample>", package: str | None = None
) -> bool:
    """Whether a source imports the comment service, by either statement form."""
    return reaches(source, COMMENT_SERVICE_MODULE, path, package)


def reaches_the_moderation_service(
    source: str, path: str = "<sample>", package: str | None = None
) -> bool:
    """Whether a source imports the moderation service, by either statement form."""
    return reaches(source, MODERATION_SERVICE_MODULE, path, package)


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
            (BACKEND_ROOT / name).read_text(encoding="utf-8"),
            str(BACKEND_ROOT / name),
            package_of(name),
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


def test_the_import_reader_catches_a_planted_moderation_import_and_spares_its_near_misses() -> None:
    """E6-09 done-when 10's instrument, both directions, before the tree is judged with it.

    The planted imports are the four spellings a student module could use to reach
    `app.services.moderation`, `from app.services import moderation` among them —
    the spelling a reader looking only at an `ImportFrom`'s `module` misses.

    **The mutation this kills:** the moderation sweep below written as a text
    search, or as a bare `startswith("app.services.moderation")` — the near miss
    `app.services.moderation_rules` is what the second takes. **Green today**: this
    is arithmetic on strings, and it is what makes the sweep's green mean anything.
    """
    for sample in MODERATION_IMPORTS_MUST_CATCH:
        assert reaches_the_moderation_service(sample), (
            f"The import reader found no reference to `{MODERATION_SERVICE_MODULE}` in "
            f"{sample!r}, which imports it, so the sweep below would read a student module that "
            "did this as clean."
        )
    for sample in MODERATION_IMPORTS_MUST_ALLOW:
        assert not reaches_the_moderation_service(sample), (
            f"The import reader read `{MODERATION_SERVICE_MODULE}` out of {sample!r}, which does "
            "not import it; the sweep below would then be red against a correct student module."
        )


def test_no_student_facing_module_imports_the_moderation_service() -> None:
    """E6-09 done-when 10: the student-path tripwire watches `app.services.moderation`.

    That module holds the decision service and the exclusion log (E6-03, E6-05,
    E6-08): flagged text, reasons and excerpts that SPEC §5.2 collapses from
    students. A student-facing module that imported it could put any of them on
    a student's page. Same four modules, each required to exist first, as the
    comment-service sweep above requires them.

    **The mutation this kills:** `from app.services.moderation import ...` added
    to any of the four student-facing modules. **The near miss** is the instrument
    test above: a reader that cannot see `from app.services import moderation`
    would leave this green over exactly that import.
    """
    missing = [name for name in STUDENT_FACING_MODULES if not (BACKEND_ROOT / name).is_file()]
    assert not missing, (
        f"{missing} are not in {BACKEND_ROOT.relative_to(REPO_ROOT)}, so this sweep judged fewer "
        "modules than it names."
    )
    offenders = sorted(
        name
        for name in STUDENT_FACING_MODULES
        if reaches_the_moderation_service(
            (BACKEND_ROOT / name).read_text(encoding="utf-8"),
            str(BACKEND_ROOT / name),
            package_of(name),
        )
    )
    assert not offenders, (
        f"{offenders} import `{MODERATION_SERVICE_MODULE}`. SPEC §4.1 item 6: no view may ever "
        "widen a student's visibility, and that module reads flagged text, reasons and excerpts "
        "that §5.2 collapses from students."
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
    instructor's cases all leave it `None`. And, since the security round, `rng`
    put back on either read: the equality names it, because a caller-supplied seed
    is a caller-controlled permutation and two reads under one seed re-derive the
    order the rows arrived in.

    **What this equality cannot see** is a `**kwargs` on either signature, which
    declares no parameter and accepts every one.
    `tests/integration/test_the_comment_order_is_randomized_rather_than_stored.py`
    calls both reads with `rng=` and requires `TypeError`, which is the half that
    catches it; neither test implies the other.

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


# ---------------------------------------------------------------------------
# E8-01, done-when 8: the one named caller, and the two student reads.
# ---------------------------------------------------------------------------


def test_the_import_reader_resolves_a_relative_import_inside_the_services_package() -> None:
    """The reader one level out: `from .report_comments import …` inside `app/services/`.

    **The mutation this kills:** the reader's original shape, which read
    `node.module` only when it was absolute and so read every relative import as
    nothing — the spelling a module beside the service is likeliest to write.
    **The near misses:** a relative import of a sibling (`.reporting`), and a
    relative import read with no package, which stays unresolved.
    """
    sample = "from .report_comments import visible_cards"
    assert reaches_the_comment_service(
        sample, package=SERVICES_PACKAGE
    ), f"The reader did not resolve {sample!r} inside `{SERVICES_PACKAGE}` to the comment service."
    assert reaches_the_moderation_service("from . import moderation", package=SERVICES_PACKAGE)
    assert not reaches_the_comment_service("from .reporting import x", package=SERVICES_PACKAGE)
    assert not reaches_the_comment_service(sample), "A relative import resolved with no package."
    assert package_of(STUDENT_COMMENT_CALLER) == SERVICES_PACKAGE


def test_the_allowance_reader_refuses_every_plant_and_spares_the_two_reads() -> None:
    """Done-when 8's plants, read by the instrument before the caller is judged with it.

    Every planted import into the named caller (`student_results`, since E9-08) is
    a breach — `visible_cards`,
    `released_cards`, a star, the module whole, `moderation` by every spelling —
    and the two allowed reads, together, alone, aliased or relative, are not.

    **The mutations this kills:** an allowance read off the alias (so
    `released_cards as student_released_comments` passes); `import
    app.services.report_comments` counted as no name rather than as every name;
    and a reader blind to relative imports. **The near misses:** the allowed
    imports, which every correct caller writes one of.
    """
    for sample in CALLER_IMPORTS_MUST_REFUSE:
        assert caller_breaches(
            sample
        ), f"The allowance reader found no breach in {sample!r}, which done-when 8 plants as one."
    for sample in CALLER_IMPORTS_MUST_ALLOW:
        assert caller_breaches(sample) == [], (
            f"The allowance reader found {caller_breaches(sample)} in {sample!r}, which is inside "
            f"the caller's allowance ({sorted(ALLOWED_FROM_THE_COMMENT_SERVICE)})."
        )
    both = CALLER_IMPORTS_MUST_ALLOW[0]
    assert taken_from(both, COMMENT_SERVICE_MODULE) == ALLOWED_FROM_THE_COMMENT_SERVICE


def test_the_one_student_caller_takes_the_two_student_reads_and_nothing_else() -> None:
    """E9-08's done-when 2: `services/student_results.py` is in the sweep, with its allowance.

    E8-01 named `services/response_loop.py`; E9-08 moved the student's week read
    into `services/student_results.py`, and the allowance moved with it. It takes
    exactly `student_comments` and `student_released_comments` from the comment
    service — both, because it is the one module that reaches the student's
    comment read (E8-01's "Comments a student may read") — and nothing else from
    it, and nothing from `app.services.moderation`. **Direct imports only**
    (entry 53's disclosed limit): a helper elsewhere that reached `visible_cards`
    for it is invisible here, and the behavioural modules named in this file's
    docstring are the proof.

    **The mutations this kills:** `from app.services.report_comments import
    visible_cards` added to `student_results` to build the week from the
    instructor's cards; the moderation service imported there; the student read
    reached through another module — `reporting.student_streams`, which no sweep
    watches — rather than through the named caller; and, since E9-08, the move
    done as a re-export, with the two reads still imported by `response_loop` and
    handed on (the new module then imports neither, and `taken` below is empty).
    **The near miss:** the two allowed imports.

    **Which failure a red is, before E9-08's move lands:** the first assertion,
    `student_results.py is not in the backend`.
    """
    path = BACKEND_ROOT / STUDENT_COMMENT_CALLER
    assert path.is_file(), f"{STUDENT_COMMENT_CALLER} is not in the backend; the sweep names it."
    source = path.read_text(encoding="utf-8")
    package = package_of(STUDENT_COMMENT_CALLER)

    breaches = caller_breaches(source, str(path), package)
    assert breaches == [], (
        f"{STUDENT_COMMENT_CALLER} takes {breaches} beyond its allowance. Done-when 8: exactly "
        f"{sorted(ALLOWED_FROM_THE_COMMENT_SERVICE)} from `{COMMENT_SERVICE_MODULE}`, and nothing "
        f"from `{MODERATION_SERVICE_MODULE}`."
    )
    taken = taken_from(source, COMMENT_SERVICE_MODULE, str(path), package)
    assert taken == ALLOWED_FROM_THE_COMMENT_SERVICE, (
        f"{STUDENT_COMMENT_CALLER} takes {sorted(taken)} from `{COMMENT_SERVICE_MODULE}`. E8-01: "
        "it is the one module that reaches the student's comment read, through both student reads."
    )


def test_a_signature_comparison_refuses_a_read_widened_by_a_person_parameter() -> None:
    """The signature equality's instrument. **A red here means this module is broken.**

    **The mutation this kills:** a comparison written as "the settled names are
    present", which a read widened by one optional `user_id` satisfies.
    """

    def settled(session: Any, *, section_id: Any, week_id: Any, stream: Any) -> None: ...

    def widened(
        session: Any, *, section_id: Any, week_id: Any, stream: Any, user_id: Any = None
    ) -> None: ...

    expected = STUDENT_READ_SIGNATURES["student_comments"]
    assert tuple(inspect.signature(settled).parameters) == expected
    assert tuple(inspect.signature(widened).parameters) != expected


def test_the_two_student_reads_take_no_parameter_that_could_name_a_person() -> None:
    """Done-when 8: the signature equality covers both student reads.

    `student_comments(session, *, section_id, week_id, stream)` and
    `student_released_comments(session, *, section_id, term_id, stream, as_of)`:
    a section, a week or a term, a stream and an instant, and no position a person
    could go in. `as_of` is allowed by name (the ticket), and it is an instant.

    **The mutations this kills:** a `user_id`, `viewer` or `student` added "so the
    page can mark the reader's own comment" — which turns a read built to conceal
    into one that discloses on request; and `as_of` dropped or renamed, which
    leaves the release unbounded. **What this cannot see:** a `**kwargs`, which
    declares no parameter; the behavioural modules call each read by keyword.
    """
    module = importlib.import_module(COMMENT_SERVICE_MODULE)
    for name, expected in STUDENT_READ_SIGNATURES.items():
        function = getattr(module, name, None)
        assert callable(function), (
            f"`{COMMENT_SERVICE_MODULE}` exposes no `{name}`. E8-01's ticket adds it, filtering the "
            "instructor's read to `published` and `kept` and returning text and stream only."
        )
        taken = tuple(inspect.signature(function).parameters)
        assert taken == expected, (
            f"`{COMMENT_SERVICE_MODULE}.{name}` takes {list(taken)}; E8-01 settles "
            f"{list(expected)}. SPEC §4.1 item 6: a parameter naming a person is how a view widens "
            "a student's visibility."
        )
