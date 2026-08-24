"""One definition of the development environment's name — E0-37 item 2.

`backend/app/config.py` declares the `environment` field, so the value that means
"this is a developer's machine" belongs beside it. Until this item it was spelled
three times: once there, once in `backend/app/db.py` where the engine decides
whether to echo SQL, and once in `scripts/seed.py` where the loader refuses to
run against a deployment. E0-18's `/docs` gating keys on the same value and
imports the constant, which is the shape the other two now take.

**Why a test rather than a convention.** Two constants in two files with nothing
comparing them is exactly the shape that produced `docs/MISTAKES.md` entry 3's
application-role incident: a fixture and a migration naming the same role
differently, each internally consistent, and nothing anywhere that could notice
they had come apart. The cost of drift here is not cosmetic. If `db.py`'s copy
and `config.py`'s copy ever disagree, one of them decides that a deployment is
development for the purpose of echoing SQL while the other decides it is not for
the purpose of anything else — and E0-37 item 1 puts the parameter-hiding
decision on precisely that comparison, so the environment that leaks bound
parameters is the one where the two spellings differ.

**What is asserted, and how it can go blind.** Two properties, read out of the
parsed source rather than grepped: no module in `backend/app` or `scripts` other
than the configuration binds the name by assignment, and neither the engine nor
the seed holds the bare string at all. Both detectors are run against
`backend/app/config.py` first, which certainly holds a definition and certainly
holds the literal — the canary `docs/MISTAKES.md` entry 3 asks for, in a form
that cannot drift out of step with the file it describes, because it is the
file. A detector that has stopped seeing an assignment or a string constant
reports the same clean sweep as a repository that has been fixed, and only the
canary tells those apart.

**The AST rather than a regex**, for the reason entry 3's third case gives: a
pattern written with a plain space matched nothing where the file held a newline
and six columns of comment continuation, and went green against the exact text it
existed to catch. `ast` has no opinion about wrapping.

**What it does not assert.** Not the import *spelling* — `from app.config import
DEVELOPMENT_ENVIRONMENT`, an attribute read off the imported module, and a call
to `app.config`'s own `is_development` predicate are all "read it from the one
place", and choosing between them is style rather than the criterion. The third
of those is the strongest form of the property and not an exception to it: the
predicate lives in `backend/app/config.py` and reads that module's own
`DEVELOPMENT_ENVIRONMENT`, so a module calling it has moved the *shape* of the
comparison into the configuration alongside the value, leaving nothing local to
drift. Not the constant's value either: what matters is that there is one of it,
and `test_config_settings.py` owns what `ENVIRONMENT` may be.

The predicate was added after this module was first written, and the paragraph
above once enumerated two spellings and so rejected a third that did not exist
yet; `docs/disputes/QUALITY-REVIEW-CLEANUPS-01.md` records why the old detector
was wrong and how it was amended.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# The single definition site, and the two modules E0-37 item 2 names as carrying
# their own copies. Repository-relative strings rather than paths, because every
# message in this module quotes them and a reader needs the path they would type.
CONFIGURATION = "backend/app/config.py"
ENGINE = "backend/app/db.py"
SEED = "scripts/seed.py"

# The two trees a second definition could plausibly appear in. `backend/app` is
# the application and `scripts` is everything that runs beside it; both are
# swept, so a third copy in a module nobody has written yet is a red rather than
# a thing somebody has to remember to look for.
SEARCHED_TREES = ("backend/app", "scripts")

# The constant's name, and the value it holds. The value is written here because
# this is the module whose subject is where that value may appear — every other
# test that needs it reads it off `app.config`.
CONSTANT = "DEVELOPMENT_ENVIRONMENT"
DEVELOPMENT = "development"

# The predicate `backend/app/config.py` exports beside the constant. It is owned
# by the configuration and it reads the configuration's own
# `DEVELOPMENT_ENVIRONMENT`, so calling it is reading the one definition — the
# same property the two import spellings have, with the comparison in one place
# as well as the value.
PREDICATE = "is_development"


def source_of(relative: str) -> str:
    """The text of one repository file, or a failure naming what is missing."""
    path = REPO_ROOT / relative
    if not path.is_file():
        pytest.fail(
            f"`{relative}` is not a file in this repository, so nothing here was read. E0-37 "
            f"item 2 is about `{CONFIGURATION}`, `{ENGINE}` and `{SEED}`; if one of them has "
            "moved, this module's constants are the one place that changes."
        )
    return path.read_text(encoding="utf-8")


def parsed(relative: str) -> ast.Module:
    """One repository file as a syntax tree, or a failure saying it does not parse."""
    try:
        return ast.parse(source_of(relative))
    except SyntaxError as error:
        pytest.fail(
            f"`{relative}` does not parse ({error}), so this module read nothing out of it. A "
            "file the sweep cannot read is a file that could hold a second definition of the "
            "development environment's name and report none."
        )


def assignments_of_the_constant(tree: ast.Module) -> list[int]:
    """Every line where `DEVELOPMENT_ENVIRONMENT` is bound by an assignment.

    Annotated assignments count: `DEVELOPMENT_ENVIRONMENT: Final = "development"`
    is a definition and so is the bare form. An import does not count, which is
    the whole distinction this module is built on — importing the name is reading
    the one definition, and assigning it is making another.
    """
    found: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id == CONSTANT:
                found.append(node.lineno)
    return sorted(found)


def literals_of_the_development_name(tree: ast.Module) -> list[int]:
    """Every line holding the bare string `"development"`.

    Every appearance, not only the assigned ones: a comparison written
    `settings.environment == "development"` is a second copy of the value with no
    assignment anywhere, and it drifts from the constant exactly as readily. A
    docstring or a message mentioning the word is not this — the value has to be
    the whole of the string for it to be a spelling of the environment's name.
    """
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value == DEVELOPMENT
    )


def reads_the_constant(tree: ast.Module) -> bool:
    """Whether the module gets the answer from somewhere rather than declaring it.

    Three spellings, because the ticket asks for one definition and not for one
    import style: the constant imported directly, the constant read as an
    attribute of the configuration module, or `is_development` — the predicate
    `backend/app/config.py` owns — imported or read the same two ways. The
    predicate satisfies the criterion more completely than the other two rather
    than by exception: it reads `config.py`'s single `DEVELOPMENT_ENVIRONMENT`,
    so a caller has both the value *and* the shape of the comparison living in
    the configuration, with no local copy of either left to drift.

    A module doing none of the three either has its own copy or does not care
    about the environment at all, and the caller says which.

    As loose as it has always been, deliberately: the name is matched wherever it
    appears, without checking that the import names `app.config`. A module that
    imports either name from somewhere else is not the failure this sweep exists
    to catch, and the assignment sweep above is what would see a local
    redefinition.
    """
    wanted = (CONSTANT, PREDICATE)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(alias.name in wanted for alias in node.names):
            return True
        if isinstance(node, ast.Attribute) and node.attr in wanted:
            return True
    return False


def swept_modules() -> list[str]:
    """Every Python file under the searched trees, repository-relative and sorted.

    The local name is `directory` rather than `root`, deliberately.
    `tests/unit/test_a_documentation_only_diff_does_not_run_the_expensive_gates.py`
    reads `root` as a name meaning the repository root — it has to, because the
    private-key sweep takes the root as a parameter called exactly that — so a
    walk written `root.rglob(...)` here would be reported as a repository-wide
    sweep and would have to be triaged into an exception set it does not belong
    in. These two trees are code, a change to either is never inert, and this
    module needs no protection from the path filter.
    """
    found: list[str] = []
    for relative_tree in SEARCHED_TREES:
        directory = REPO_ROOT / relative_tree
        if not directory.is_dir():
            pytest.fail(
                f"`{relative_tree}` is not a directory in this repository, so half of this sweep "
                "read nothing. SPEC §13 puts the application under `backend/app` and the "
                "operational scripts under `scripts`."
            )
        found.extend(
            str(path.relative_to(REPO_ROOT))
            for path in directory.rglob("*.py")
            if "__pycache__" not in path.parts
        )
    return sorted(found)


def test_the_configuration_module_is_where_the_development_environment_name_is_defined() -> None:
    """The definition exists where it belongs — and the two detectors can see one.

    This is the canary for the two sweeps below, and it is the reason their
    silence can be believed. A detector that no longer recognises an assignment,
    or one that no longer sees a string constant, reports the same clean answer
    over a repository with three copies as over a repository with one
    (`docs/MISTAKES.md` entry 3). The sample it is proved against is not a
    hand-written imitation of the offending line — it is the real file that
    certainly holds one, so it cannot be a transcription of what somebody thought
    the code said.

    It is also the first half of the criterion in its own right: "one definition"
    is unsatisfiable by zero definitions, and a repository where nothing defines
    the name would pass both sweeps below perfectly.
    """
    tree = parsed(CONFIGURATION)

    assignments = assignments_of_the_constant(tree)
    assert assignments, (
        f"`{CONFIGURATION}` assigns no `{CONSTANT}`. E0-37 item 2 puts that constant beside the "
        f"`environment` field it describes, with `{ENGINE}` and `{SEED}` importing it.\n"
        "\n"
        "Until this is true, the sweep below cannot distinguish a repository with one definition "
        "from a repository whose definitions it has stopped being able to see."
    )

    literals = literals_of_the_development_name(tree)
    assert literals, (
        f"`{CONFIGURATION}` holds no bare {DEVELOPMENT!r} string, so the detector that looks for "
        "one has nothing here to prove itself against. Either the value moved somewhere this "
        "module does not read, or the search has gone blind — and a blind search reports the "
        "engine and the seed as clean whatever they contain."
    )


def test_no_module_outside_the_configuration_defines_a_development_environment_name_of_its_own() -> (
    None
):
    """One definition, derived from the tree rather than from a list of files to check.

    Swept rather than asserted about the two modules the ticket names, because
    the ticket names the two that had a copy on the day it was written. A third
    arrives the same way the second did — somebody needs the value, the import
    crosses a module boundary their ticket did not touch, and a constant beside
    the code is one line. That is not a criticism of anybody; it is why this is a
    sweep.

    **The mutation this survives:** put `DEVELOPMENT_ENVIRONMENT = "development"`
    back in `backend/app/db.py`, or in any other module under the searched trees.
    **The near miss that must stay green:** importing the name and rebinding
    nothing, however it is spelled.
    """
    modules = swept_modules()

    for required in (CONFIGURATION, ENGINE, SEED):
        assert required in modules, (
            f"The sweep did not reach `{required}` (it read {len(modules)} modules under "
            f"{list(SEARCHED_TREES)}). Every verdict below is an absence, and an absence over a "
            "tree that was never walked is not a finding."
        )

    defined_elsewhere = {
        relative: assignments_of_the_constant(parsed(relative))
        for relative in modules
        if relative != CONFIGURATION
    }
    offenders = {relative: lines for relative, lines in defined_elsewhere.items() if lines}

    assert not offenders, "\n".join(
        [
            f"These modules assign a `{CONSTANT}` of their own, so the repository has more than "
            "one definition of what counts as development:",
            *(f"  {relative}: line(s) {lines}" for relative, lines in sorted(offenders.items())),
            "",
            f"E0-37 item 2: it belongs beside the field in `{CONFIGURATION}`, imported by "
            "everything that needs it. Two constants in two files with nothing comparing them is "
            "`docs/MISTAKES.md` entry 3's application-role incident — a fixture and a migration "
            "naming one role differently, each internally consistent, nothing able to notice.",
            "",
            "The cost is not cosmetic here. E0-37 item 1 hangs the hiding of bound parameters on "
            "'outside development', so a deployment the two spellings disagree about is a "
            "deployment whose survey answers and free-text comments reach the log (SPEC §10).",
        ]
    )


def test_the_engine_and_the_seed_read_the_development_environment_name_rather_than_spelling_it() -> (
    None
):
    """The criterion's second half, for the two modules that carried a copy.

    A module can satisfy the sweep above by holding the value without binding a
    name to it — `if settings.environment == "development":` is a copy with no
    assignment. So both files are required to hold no bare `"development"` at
    all, and to get the answer from `backend/app/config.py` — by the constant or
    by the predicate; `reads_the_constant` says which spellings count.

    Both halves, because either alone is satisfiable the wrong way. A module that
    imports the constant *and* keeps its old literal comparison has two answers
    and uses the older one; a module that holds no literal because it stopped
    caring about the environment has lost a behaviour rather than fixed a
    duplication, and the tests that own those behaviours —
    `test_db_engine_configuration.py` for the engine, `test_seed_target_is_enforcing.py`
    and `test_demo_seed_script.py` for the seed — are what would go red for that.

    **The mutation this survives:** restore either literal, in either file.
    **The near miss that must stay green:** a docstring or an error message that
    contains the word development inside a longer sentence, which is not a
    spelling of the value and is not matched.
    """
    for relative in (ENGINE, SEED):
        tree = parsed(relative)

        literals = literals_of_the_development_name(tree)
        assert not literals, (
            f"`{relative}` still spells {DEVELOPMENT!r} itself, at line(s) {literals}.\n"
            "\n"
            f"E0-37 item 2: the value belongs beside the `environment` field in "
            f"`{CONFIGURATION}` and is imported by both readers. A second copy is not wrong on "
            "the day it is written — it is wrong on the day one of the two changes, and the "
            "failure is silent, because each file is internally consistent (`docs/MISTAKES.md` "
            "entry 3).\n"
            "\n"
            "E0-37 item 1 is what makes it expensive: whether bound parameters are hidden is "
            "decided by 'is this development', so two spellings that have drifted apart are an "
            "environment that writes survey answers and free-text comments to the log (SPEC §10)."
        )

        assert reads_the_constant(tree), (
            f"`{relative}` holds no {DEVELOPMENT!r} literal and reads neither `{CONSTANT}` nor "
            f"`{PREDICATE}()`, so it has stopped asking which environment it is running in rather "
            f"than started asking `{CONFIGURATION}`.\n"
            "\n"
            f"Either spelling satisfies this: import `{CONSTANT}` and compare it yourself, or "
            f"call `{PREDICATE}(settings)`, which `{CONFIGURATION}` owns and which reads that "
            "same constant.\n"
            "\n"
            "Both readers have a rule that depends on the answer: the engine hides bound "
            "parameters outside development (E0-37 item 1) and the seed refuses to run against a "
            "deployment (ADR 0063). A module that no longer consults the environment has dropped "
            "one of those, and this assertion is here so that dropping it cannot be how the "
            "duplication above gets resolved."
        )
