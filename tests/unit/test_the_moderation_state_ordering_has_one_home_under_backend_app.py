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
module that calls the shared helper does not. Until E6-03, one naming module was
the consolidated state and two was the duplication the deferral describes.

**E6-03 admits a second naming module, and moves the ordering to a reader of its
own.** Its decision service in `services/moderation.py` writes the relation, and a
writer has to name what it writes. So the module count admits exactly the reader
and that writer, by path, and a second reader — `orders_the_relation` — holds the
ordering itself to the one home: a module scope that names the relation *and*
orders (an `order_by`, a `desc`, the `sequence` column, an `ORDER BY` in SQL) is a
copy of the ordering, and only `report_comments.py` may hold one. That reader is
controlled in both directions like the first.

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

# What the consolidated state looks like, since E6-03: two modules under
# `backend/app/`, outside the model layer, name the relation in code — the reader,
# where E4-07 consolidated the ordering, and the one writer, where E6-03's ticket
# puts the instructor's exclude, keep and undo. And of those two, **only the reader
# orders the rows**: the writer appends, and anything it needs to know about which
# row is latest it asks the reader for. So the deferral's done-when — "no second
# copy of the ordering or of the default anywhere under `backend/app/`" — still
# holds, measured by a second reader below rather than by the module count alone.
READER_HOME = APP_ROOT / "services" / "report_comments.py"
WRITER_HOME = APP_ROOT / "services" / "moderation.py"
HOMES_ALLOWED = frozenset({READER_HOME, WRITER_HOME})

# What ordering the relation looks like in code: a call or attribute that orders,
# or the column E6-01 orders by (SPEC §8: "'Latest' is the order the rows were
# inserted in, held in a database-assigned sequence column"), or `ORDER BY` in a
# SQL string. Counted only where it shares a function with a mention of the
# relation, so a writer that also orders some *other* table — E6-02's attempt cap,
# in the same module — is not a second copy of this ordering.
ORDERING_NAMES = ("order_by", "desc", "row_number", "sequence")
ORDERING_SQL = ("order by", "row_number", "sequence")

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

# The ordering reader's own planted tree. Every one of these names the relation, so
# the first reader counts all of them; the second must tell which ones *order* it.
PLANTED_FOR_ORDERING = {
    # Not ordering: a writer that appends a decision and asks the reader what is
    # latest — the shape E6-03's decision service is meant to have.
    "a_writer_that_appends.py": (
        '"""A decision writer."""\n\n'
        "from app.models.report import ModerationState\n"
        "from app.services.report_comments import reported_status_of\n\n\n"
        "def decide(session, answer_id, state):\n"
        "    current = reported_status_of(session, answer_id)\n"
        "    session.add(ModerationState(answer_id=answer_id, state=state))\n"
        "    return current\n"
    ),
    # Not ordering: the same writer, in a module that also orders another table in a
    # function of its own — E6-02's attempt cap shares `services/moderation.py`.
    "a_writer_beside_an_unrelated_order.py": (
        '"""A decision writer beside an attempt cap."""\n\n'
        "from sqlalchemy import select\n\n"
        "from app.models.ai import ModerationAttempt\n"
        "from app.models.report import ModerationState\n\n\n"
        "def decide(session, answer_id, state):\n"
        "    session.add(ModerationState(answer_id=answer_id, state=state))\n\n\n"
        "def attempts(session, answer_id):\n"
        "    return select(ModerationAttempt).order_by(ModerationAttempt.attempted_at.desc())\n"
    ),
    # Ordering: a writer that finds the latest row for itself, by the model.
    "a_writer_that_orders.py": (
        '"""A decision writer with its own copy of the ordering."""\n\n'
        "from sqlalchemy import select\n\n"
        "from app.models.report import ModerationState\n\n\n"
        "def latest(session, answer_id):\n"
        "    return select(ModerationState).order_by(ModerationState.sequence.desc()).limit(1)\n"
    ),
    # Ordering: the same copy written in SQL.
    "a_writer_that_orders_in_sql.py": (
        '"""A decision writer with its own copy of the ordering, in SQL."""\n\n'
        "from sqlalchemy import text\n\n\n"
        "def latest(session, answer_id):\n"
        '    return text("SELECT state FROM moderation_state ORDER BY 1 LIMIT 1")\n'
    ),
}

PLANTED_ORDERING = {"a_writer_that_orders.py", "a_writer_that_orders_in_sql.py"}


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


def _scopes(tree: ast.Module) -> list[list[ast.AST]]:
    """Each function's own nodes, and the module's nodes outside any function, as scopes."""
    functions = [
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    inside = {id(inner) for function in functions for inner in ast.walk(function)}
    module_level = [node for node in ast.walk(tree) if id(node) not in inside]
    return [list(ast.walk(function)) for function in functions] + [module_level]


def orders_the_relation(path: Path) -> bool:
    """Whether some one scope of a module names the relation and orders, both in executable code.

    The relation is read as `names_the_relation_in_code` reads it; ordering is a
    name or attribute in `ORDERING_NAMES`, or a non-docstring string containing one
    of `ORDERING_SQL`. Both must sit in one function (or both at module level), so a
    module that writes the relation in one function and orders another table in the
    next is not counted.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = docstring_nodes(tree)

    def marks(node: ast.AST) -> tuple[bool, bool]:
        names_it = orders = False
        if isinstance(node, ast.Name):
            names_it = node.id in RELATION_NAMES
            orders = node.id in ORDERING_NAMES
        elif isinstance(node, ast.Attribute):
            names_it = node.attr in RELATION_NAMES
            orders = node.attr in ORDERING_NAMES
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            names_it = any(name in node.value for name in RELATION_NAMES)
            orders = any(fragment in node.value.lower() for fragment in ORDERING_SQL)
        return names_it, orders

    for scope in _scopes(tree):
        found = [marks(node) for node in scope]
        if any(names_it for names_it, _ in found) and any(orders for _, orders in found):
            return True
    return False


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


def test_the_ordering_reader_counts_a_writer_that_orders_and_spares_one_that_appends(
    tmp_path: Path,
) -> None:
    """The second instrument, both directions, before the tree is judged with it.

    **A red here means these tests are broken, not that the code is.** Four planted
    modules, all naming the relation: a writer that appends and asks the reader, a
    writer beside an attempt cap that orders another table, and two writers that
    find the latest row for themselves — by the model and in SQL. The reader must
    count exactly the last two.

    **The mutations this kills:** a reader that counts any module naming the
    relation and any ordering anywhere in it (the attempt-cap sample is counted —
    red over the tree E6-02 and E6-03 build together); and a reader that sees only
    the model's `order_by` (the SQL copy is missed).
    """
    for name, source in PLANTED_FOR_ORDERING.items():
        (tmp_path / name).write_text(source, encoding="utf-8")
    planted = sorted(tmp_path.glob("*.py"))
    assert len(planted) == len(PLANTED_FOR_ORDERING), "The planted tree is not as described."
    assert all(names_the_relation_in_code(path) for path in planted), (
        "The first reader does not count every planted module, so the second is being asked about "
        "modules the first would already have spared."
    )

    counted = {path.name for path in planted if orders_the_relation(path)}
    assert counted == PLANTED_ORDERING, (
        f"The ordering reader counted {sorted(counted)}; the planted modules that order the "
        f"moderation state are {sorted(PLANTED_ORDERING)}."
    )


def test_only_the_reader_and_the_one_writer_name_the_moderation_state() -> None:
    """E6-03's amendment of the deferral's done-when: the reader, the one writer, nobody else.

    ADR 0145 makes `moderation_state` append-only with the latest row governing
    and the initial state the *absence* of a row, and names the consequence: "a
    reader of a comment's moderation state has to write a window function, or its
    equivalent … That is E4-04's and E6's to write once, in `app.services`, not
    per call site." E6-03 adds the writer the record was waiting for — the
    instructor's exclude, keep and undo, in `services/moderation.py` (the ticket's
    "Owns") — and a writer has to name the table it writes. So two homes are
    admitted, by path, and a third is the duplication the deferral records.

    **The mutations this kill:** the decision service written in `api/instructor.py`
    or a new module (a third home, and a route that holds its own copy of the
    rules); E4-06's copy back in `reporting.py`; and the reader moved out of
    `report_comments.py` without this record moving with it.

    **The canary:** the reader is required to be found. Zero is a sweep looking at
    the wrong tree (`docs/MISTAKES.md` entry 3).
    """
    assert APP_ROOT.is_dir(), f"{APP_ROOT} is not a directory, so this sweep walked nothing."
    homes = set(modules_resolving_the_state())
    named = sorted(str(path.relative_to(REPO_ROOT)) for path in homes)
    assert READER_HOME in homes, (
        f"{READER_HOME.relative_to(REPO_ROOT)} does not name {list(RELATION_NAMES)} in executable "
        f"code; the modules that do are {named}. "
        "`reported_status_of` resolves every comment's state there, so its absence means this "
        "reader is blind or the reader has moved."
    )
    beyond = sorted(str(path.relative_to(REPO_ROOT)) for path in homes - HOMES_ALLOWED)
    assert not beyond, "\n".join(
        [
            "These modules under backend/app/ name the moderation state beside its reader and "
            "its one writer:",
            *(f"  {path}" for path in beyond),
            "",
            "`docs/tickets/e4/deferred.md`'s done-when: one helper in `app.services` resolves a "
            "comment's moderation state, with no second copy of the ordering or of the default "
            "anywhere under `backend/app/`. E6-03 admits `services/moderation.py` as the one "
            "writer, and nothing else.",
        ]
    )


def test_only_the_reader_orders_the_moderation_state() -> None:
    """The ordering keeps one home: the writer appends, and asks the reader which row is latest.

    E6-03's undo has to know the latest decision on a comment, and its transition
    check the current state. Both are the reader's question — SPEC §8: "'Latest' is
    the order the rows were inserted in, held in a database-assigned sequence column"
    — and `reported_status_of` already answers the second. A decision service that
    sorted the rows for itself is the second copy the deferral forbids, and the day
    the two disagree an undo reverses a decision the report does not show as latest.

    **The mutation this kills:** an `ORDER BY sequence DESC` (or `.order_by(...)`)
    over `moderation_state` written in `services/moderation.py`.

    **The canary:** the reader itself is required to be counted — it orders by
    `sequence` (E6-01 decision 9) — so a blind ordering reader cannot pass this.
    """
    homes = modules_resolving_the_state()
    ordering = {path for path in homes if orders_the_relation(path)}
    assert READER_HOME in ordering, (
        f"The ordering reader does not count {READER_HOME.relative_to(REPO_ROOT)}, which orders "
        "the moderation state by `sequence`; it is blind, and the assertion below would pass over "
        "any tree."
    )
    others = sorted(str(path.relative_to(REPO_ROOT)) for path in ordering - {READER_HOME})
    assert not others, (
        f"These modules order the moderation state for themselves: {others}. The ordering has one "
        f"home, {READER_HOME.relative_to(REPO_ROOT)}; a writer asks it which row is latest."
    )
