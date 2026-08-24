#!/usr/bin/env python3
"""Refuse an `invariant`-marked test whose body asserts nothing — E0-36 item 3.

`check_invariants.py` reads the JUnit XML a run produced, so it can see a skip,
an xfail and an empty collection. It cannot see a test that ran and asserted
nothing: the XML carries no assertion count, so such a test is counted toward
the "N invariant test(s) ran, none skipped, none failed" that checker prints.
This one reads the sources instead and closes that gap. The two are halves of one
gate and both callers run both.

**The rule, as E0-36 §3 states it.** An `invariant`-marked test's own body must
contain at least one of: an `assert` statement, a `with pytest.raises(...)`
block, or a `pytest.fail(...)` call. A body whose only statements are calls is
refused.

Three things the rule deliberately does not do, and the cost of each:

- **It does not follow a call into a helper.** A test that delegates its whole
  control to a module-level helper which asserts is correct, and this refuses it.
  Chasing calls means choosing a depth — one level, two, an imported helper — and
  every choice is arbitrary. The refusal is loud and the fix is one line.
- **It reads the body statically and cannot know the assertion executed.** An
  `assert` inside a branch nothing takes satisfies it. This closes the gap
  between "no assertion is written" and "an assertion passed"; it does not close
  the one between "an assertion is written" and "it ran".
- **It reads only the attribute spellings `pytest.raises` and `pytest.fail`.**
  `from pytest import raises` is refused. Those are the only spellings in this
  repository — 60 and 211 uses, no bare imports — and a checker generous about
  spelling is generous about what passes, which is the wrong direction for a
  gate. The refusal names the test and the fix is the import.

**Both ways a test is marked are read**, because pytest honours both and a
checker that knew only one would pass silently over the tests it could not see —
which is this ticket's whole subject one level down.
`tests/unit/test_no_service_reads_an_identity_table_directly.py` marks three
invariants with a module-level `pytestmark` and no decorator anywhere.

Usage:
    check_invariant_assertions.py tests
    check_invariant_assertions.py tests/unit tests/integration/test_one.py
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

MARKER = "invariant"

# The two spellings the rule names, as attributes of something. See the docstring
# for why the bare-name forms are not accepted.
RAISES = "raises"
FAIL = "fail"


def is_marker(node: ast.expr) -> bool:
    """True for `pytest.mark.invariant`, called or not.

    `pytest.mark.invariant(...)` is unwrapped first because a marker may carry
    arguments, and the module alias is not checked: `pt.mark.invariant` is the
    same marker under a different import name, and reading it as one costs
    nothing while refusing to would be a checker that could be blinded by an
    `import pytest as pt`.
    """
    if isinstance(node, ast.Call):
        node = node.func
    return (
        isinstance(node, ast.Attribute)
        and node.attr == MARKER
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "mark"
    )


def module_is_marked(tree: ast.Module) -> bool:
    """True when a module-level `pytestmark` applies the invariant marker.

    `pytestmark = pytest.mark.invariant` marks every test in the module, and
    `pytestmark = [a, b]` is the list form. Both are read, because a checker that
    knew only the decorator would report a clean scan over a module holding three
    real invariants.
    """
    for node in tree.body:
        targets: list[ast.expr]
        value: ast.expr | None
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        else:
            continue
        if value is None:
            continue
        if not any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets):
            continue
        applied = value.elts if isinstance(value, ast.List | ast.Tuple) else [value]
        if any(is_marker(item) for item in applied):
            return True
    return False


def is_raises_block(node: ast.stmt) -> bool:
    """True for a `with pytest.raises(...):` block, async or not."""
    if not isinstance(node, ast.With | ast.AsyncWith):
        return False
    return any(
        isinstance(item.context_expr, ast.Call)
        and isinstance(item.context_expr.func, ast.Attribute)
        and item.context_expr.func.attr == RAISES
        for item in node.items
    )


def is_fail_call(node: ast.expr) -> bool:
    """True for a `pytest.fail(...)` call."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == FAIL
    )


def body_asserts(body: list[ast.stmt]) -> bool:
    """True when the statements of a test body contain an assertion of any of the three kinds.

    Each statement is walked whole, so an `assert` nested inside a `with`, a
    `for` or an `if` counts — `tests/integration/test_identity_grants.py` writes
    every one of its refusals that way, and a checker reading only the top level
    of a body would be red against the suite it guards.

    That walk also descends into a function the test defines inside itself, and
    E0-36 §3 settles that as **allowed**: the assertion is lexically inside the
    test where a reader of the test can see it, and "helpers are not chased" is
    about a call leaving the function for something defined elsewhere. Nothing in
    this repository writes a test that way; refusing it would mean writing code
    to detect a shape nobody uses.

    The statements are walked rather than the function node, so a decorator's own
    contents are not mistaken for the body's.
    """
    for statement in body:
        for node in ast.walk(statement):
            if isinstance(node, ast.Assert):
                return True
            if isinstance(node, ast.stmt) and is_raises_block(node):
                return True
            if isinstance(node, ast.expr) and is_fail_call(node):
                return True
    return False


def marked_tests(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Every `invariant`-marked test function in a parsed module, nested in a class or not."""
    module_marked = module_is_marked(tree)
    found: list[ast.FunctionDef | ast.AsyncFunctionDef] = []

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                # pytest collects `Test*` classes, so a marked method inside one
                # is a marked test. Nothing in this repository writes them that
                # way yet; not descending would be a shape the gate cannot see.
                visit(child)
            elif isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                if not child.name.startswith("test_"):
                    continue
                if module_marked or any(is_marker(d) for d in child.decorator_list):
                    found.append(child)

    visit(tree)
    return found


def python_files(paths: list[Path]) -> list[Path]:
    """Every Python file under the given paths, files taken as themselves."""
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(sorted(path.rglob("*.py")))
        elif path.suffix == ".py":
            found.append(path)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        type=Path,
        nargs="+",
        help="test files or directories to read",
    )
    args = parser.parse_args()

    missing = [path for path in args.paths if not path.exists()]
    if missing:
        for path in missing:
            print(f"FAIL: {path} does not exist.", file=sys.stderr)
        return 1

    offenders: list[str] = []
    total = 0

    for path in python_files(args.paths):
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as error:
            # Red rather than skipped. A file this cannot parse is a file whose
            # invariants it has not read, and reporting a clean scan over one is
            # the failure this checker exists to prevent.
            print(f"FAIL: {path} could not be parsed: {error}", file=sys.stderr)
            return 1

        for test in marked_tests(tree):
            total += 1
            if not body_asserts(test.body):
                offenders.append(f"  {path}:{test.lineno}: {test.name}")

    # An empty scan is a failure, for the reason its sibling checker gives about
    # an empty collection: nothing distinguishes "every marked test asserts" from
    # "the marker was renamed and this read nothing" in an exit code of 0. The
    # gate points both callers at the whole test tree, which holds two dozen.
    if total == 0:
        print(
            "FAIL: no `invariant`-marked test was found under "
            f"{', '.join(str(p) for p in args.paths)}. That is not a pass — it is "
            "indistinguishable from one, which is what this checker exists to stop. "
            "Either the marker was renamed, the paths are wrong, or the §4.1 "
            "invariants are gone.",
            file=sys.stderr,
        )
        return 1

    if offenders:
        print(
            f"FAIL: {len(offenders)} `invariant`-marked test(s) assert nothing. A marked "
            "test that runs and asserts nothing is counted as a passing invariant by "
            "`check_invariants.py`, which cannot see the difference.",
            file=sys.stderr,
        )
        for line in offenders:
            print(line, file=sys.stderr)
        print(
            "\n  The body must contain an `assert`, a `with pytest.raises(...)` block, or a\n"
            "  `pytest.fail(...)` call. An assertion inside a helper the test calls does not\n"
            "  count (E0-36 §3: helpers are not chased); move one line into the test.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {total} invariant-marked test(s) each assert something.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
