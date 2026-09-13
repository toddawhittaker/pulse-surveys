"""A comment's moderation state is resolved in one place — E4's deferral, owned by E4-07.

`docs/tickets/e4/deferred.md` carries the entry and names the owner and the
condition, and E4-07's work order takes it as an acceptance criterion of this
ticket. The gap it closes:

> E4-04 wrote it once, as `_reported_status_of` in
> `backend/app/services/report_comments.py`, and both of that module's reads go
> through it. E4-06's summary job gathers the same week's comments and resolves
> the same state for its own purposes, in a parallel branch built off the same
> head — so after this wave merges the resolution exists twice, in two modules
> neither of which imports the other.

**Done when**, verbatim from that file:

> one helper in `app.services` resolves a comment's moderation state — the latest
> row by its decision instant, or the initial state where there is none — and both
> the comment read path and the summary job's gather call it, with no second copy
> of the ordering or of the default anywhere under `backend/app/`.

**The currency this sweep counts, and its disclosed limit.** "No second copy of
the ordering" is not directly readable, so what is counted instead is which
modules *name the moderation-state relation in executable code at all* — the model
class or the table name, outside docstrings and outside comments, which the AST
does not carry. A module that resolves the state has to name the relation; a
module that calls the shared helper does not. So one naming module is the
consolidated state and two is the duplication the deferral describes.

That is an inventory of a currency rather than a closure over the class
(`docs/MISTAKES.md` entry 14, on an enumeration reported as an impossibility): a
second copy written against a differently-named view, or against a raw SQL string
built by concatenation, is not reached here. What is reached is the shape the
deferral actually records, on the two modules it names.

**The model layer is excluded, and the exclusion is planted rather than
asserted in prose.** `backend/app/models/` is where the table is *declared*; a
declaration is not a second reading of the ordering, and a sweep that counted it
could never reach one whatever the services did.

**Its instrument is controlled in both directions before the tree is judged with
it** (`docs/MISTAKES.md` entries 3 and 9): a planted module naming the relation
in code is counted, one naming it only in its docstring is not, one naming it
only in a comment is not, and one that does not name it at all is not. A red in
that control means these tests are broken, not that the code is — fix the sweep,
never the assertion below it.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"

# Where the moderation-state declaration lives, and why it is not a copy of the
# ordering. ADR 0145 puts the report schema in its own model module; the table has
# to be named there or there is no table.
MODEL_ROOT = APP_ROOT / "models"

# The relation in the two currencies application code holds it in: E4-02's model
# class, and the table name a Core query or a view definition spells. Both,
# because `docs/MISTAKES.md` entry 35 is the record of a guard that enumerated the
# currencies a thing can be held in and missed the one the design uses — a service
# written against `select(ModerationState)` and one written against
# `text("… from moderation_state …")` are the same second copy.
RELATION_NAMES = ("ModerationState", "moderation_state")

# What the consolidated state looks like: exactly one module under `backend/app/`,
# outside the model layer, names the relation in code.
HOMES_ALLOWED = 1

# The planted tree for the control. Written under `tmp_path` rather than pointed
# at real files, because a control built out of the tree it is controlling stops
# demonstrating anything the day that tree changes — it reports success for having
# found nothing to find.
A_RESOLUTION = (
    "from sqlalchemy import select\n\n"
    "from app.models.report import ModerationState\n\n\n"
    "def status_of(answer_id):\n"
    "    return select(ModerationState).order_by(ModerationState.decided_at.desc()).limit(1)\n"
)

PLANTED = {
    # Counted: it names the model class in executable code. This is the shape the
    # deferral is about — a second module resolving the state for itself.
    "a_second_resolution.py": f'"""A gather of its own."""\n\n{A_RESOLUTION}',
    # Counted: the other currency, a table name in a string the module executes.
    # Without this sample the sweep could be blind to every raw-SQL copy and this
    # file would never say so.
    "a_second_resolution_in_sql.py": (
        '"""A gather written in SQL."""\n\n'
        "from sqlalchemy import text\n\n\n"
        "def status_of(answer_id):\n"
        '    return text("select state from moderation_state order by decided_at desc limit 1")\n'
    ),
    # Not counted: the relation is named only in the module's docstring, which is
    # how a module that *calls* the shared helper explains what it is reading.
    # A sweep counting docstrings would demand that every such module stop
    # describing itself, which is a property no implementation should satisfy
    # (`docs/MISTAKES.md` entry 24) — and `docs/MISTAKES.md` entry 43 is the
    # record of a broad guard matching ordinary prose.
    "a_caller_that_documents_itself.py": (
        '"""Reads a comment\'s moderation_state through `app.services`\' one helper.\n\n'
        "The latest ModerationState row governs; this module does not resolve it.\n"
        '"""\n\n'
        "from app.services.report_comments import reported_status_of\n\n\n"
        "def gather(session):\n"
        "    return reported_status_of(session)\n"
    ),
    # Not counted: the relation is named only in a comment. Comments are not in
    # the AST at all, so this sample is what proves the sweep reads a tree rather
    # than the file's text — a text search would count it.
    "a_caller_with_a_comment.py": (
        '"""A gather."""\n\n'
        "from app.services.report_comments import reported_status_of\n\n\n"
        "def gather(session):\n"
        "    # the latest moderation_state row governs; ModerationState is not read here\n"
        "    return reported_status_of(session)\n"
    ),
    # Not counted: it names nothing of the kind.
    "a_module_about_something_else.py": (
        '"""Rates."""\n\n\ndef divide(numerator, denominator):\n'
        "    return None if not denominator else numerator / denominator\n"
    ),
}

PLANTED_COUNTED = {"a_second_resolution.py", "a_second_resolution_in_sql.py"}


def docstring_nodes(tree: ast.AST) -> set[int]:
    """The identity of every string constant that is a docstring rather than a value."""
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = getattr(node, "body", [])
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            found.add(id(body[0].value))
    return found


def names_the_relation_in_code(path: Path) -> set[str]:
    """Which of `RELATION_NAMES` a module names in executable code, docstrings aside.

    A module that does not parse is a failure of this sweep rather than a file to
    pass over: it would drop silently out of the counted set, and silence is what
    this whole module exists to stop being mistaken for consolidation.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as failure:  # pragma: no cover - a broken tree
        pytest.fail(f"{path} does not parse ({failure}), so this sweep read nothing of it.")

    docstrings = docstring_nodes(tree)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in RELATION_NAMES:
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in RELATION_NAMES:
            found.add(node.attr)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            found.update(name for name in RELATION_NAMES if name in node.value)
    return found


def modules_resolving_the_state() -> list[Path]:
    """Every module under `backend/app/`, outside the model layer, that names the relation."""
    return sorted(
        path
        for path in APP_ROOT.rglob("*.py")
        if MODEL_ROOT not in path.parents and names_the_relation_in_code(path)
    )


def test_the_sweep_counts_a_planted_second_copy_and_spares_its_near_misses(
    tmp_path: Path,
) -> None:
    """The instrument, both directions, before the tree is judged with it.

    **A red here means these tests are broken, not that the code is.** This test
    asserts nothing about `backend/app/`; it asserts that the reader below can
    tell a module resolving the moderation state from one that merely mentions it,
    in both of the currencies a resolution is written in and in both of the places
    a mention is harmless. Repair the reader, never the assertion in the test
    beside it.

    **The mutations this kills:** a reader written as a text search, which counts
    the comment sample and the docstring sample and reports two copies over a
    consolidated tree; and a reader that looks only for the model class, which
    misses every raw-SQL copy and reports one copy over a duplicated one.
    """
    for name, source in PLANTED.items():
        (tmp_path / name).write_text(source, encoding="utf-8")

    planted = sorted(tmp_path.glob("*.py"))
    assert len(planted) == len(PLANTED), (
        f"{len(planted)} of {len(PLANTED)} planted modules were written to {tmp_path}, so this "
        "control is not the tree it describes."
    )

    counted = {path.name for path in planted if names_the_relation_in_code(path)}
    assert counted == PLANTED_COUNTED, (
        f"The reader counted {sorted(counted)}; the planted modules that resolve a moderation "
        f"state are {sorted(PLANTED_COUNTED)}.\n\n"
        "Too few and the sweep below is silent about the duplication it exists for — a reader that "
        "sees only `ModerationState` misses the raw-SQL copy. Too many and it is red over a "
        "consolidated tree: the docstring sample and the comment sample are modules that *call* "
        "the shared helper and say so in prose, and demanding they stop saying so is a property no "
        "implementation should satisfy."
    )


def test_exactly_one_module_under_backend_app_resolves_a_comments_moderation_state() -> None:
    """The deferral's done-when: one helper, one home, no second copy.

    ADR 0145 makes `moderation_state` append-only with the latest row governing
    and the initial state the *absence* of a row, and names the consequence: "a
    reader of a comment's moderation state has to write a window function, or its
    equivalent … That is E4-04's and E6's to write once, in `app.services`, not
    per call site." Two copies of "the latest row, or published" disagree the
    first time somebody changes one — an `ORDER BY` dropped on one side, or a
    default that is not published — and §5.2's whole lifecycle is about which
    decision is current, so the disagreement is a comment shown on one surface and
    hidden on the other.

    **The mutation this kills:** E4-06's copy left in place beside E4-04's, which
    is the state this branch inherits and the state the deferral records. It also
    kills the next one: a third reader written by whichever ticket next needs a
    status, which is how a duplication becomes a convention.

    **The canary:** the sweep must find at least one module. Zero is not
    consolidation, it is a sweep looking at the wrong tree or a reader that has
    gone blind, and `docs/MISTAKES.md` entry 3 is the record of that reading as a
    pass.
    """
    assert APP_ROOT.is_dir(), (
        f"{APP_ROOT} is not a directory, so this sweep walked nothing and every assertion below is "
        "true of an empty tree."
    )

    homes = modules_resolving_the_state()
    assert homes, (
        f"No module under {APP_ROOT.relative_to(REPO_ROOT)} outside "
        f"{MODEL_ROOT.relative_to(REPO_ROOT)} names {list(RELATION_NAMES)} in executable code. "
        "Something has to read a comment's moderation state — `visible_comments` reports each "
        "comment's status — so zero means this reader is blind rather than that the code is clean."
    )
    assert len(homes) == HOMES_ALLOWED, "\n".join(
        [
            f"{len(homes)} modules under backend/app/ resolve a comment's moderation state for "
            "themselves:",
            *(f"  {path.relative_to(REPO_ROOT)}" for path in homes),
            "",
            "`docs/tickets/e4/deferred.md` owns this to E4-07 and states the done-when: one helper "
            "in `app.services` resolves a comment's moderation state — the latest row by its "
            "decision instant, or the initial state where there is none — and both the comment read "
            "path and the summary job's gather call it, with no second copy of the ordering or of "
            "the default anywhere under `backend/app/`.",
            "",
            "E4-07's work order settles how: promote `report_comments.py`'s `_reported_status_of` "
            "to a public helper, have the summary gather in `reporting.py` call it, and delete "
            "E4-06's duplicate. That edits merged code deliberately, and E4-06's own tests stay "
            "green unmodified.",
        ]
    )
