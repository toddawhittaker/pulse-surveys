"""A confidentiality-denial module carries the `invariant` marker at module level.

The re-review of 2026-08-31 (`docs/tickets/e1/boundary-review.md`, "Re-review
disposition") found M6's own defect recurring: the boundary fix round wrote three
new confidentiality-denial test modules and marked none of them `invariant`, so
all three sit outside the isolated pass CLAUDE.md says may never be skipped.
M6 was closed by marking the seven modules that existed that day. Nothing stopped
the eighth, and nothing would stop the ninth.

**This is the closure over that list.** `scripts/ci/check_invariants.py` enforces
the rule CLAUDE.md states — a skip, an xfail or an empty collection in the §4.1
pass is a failure — but only over tests that already carry the marker. A denial
test with no marker is not skipped; it is invisible, and invisible is the state
the checker cannot report. So the question this module asks is the one no gate in
this repository asks today: **which modules ought to be in the marked set?**

**The set is derived from the filename, and that is the whole trick.** This
project names a denial module after what it denies — `..._names_nobody`,
`..._repeats_nothing...`, `..._names_nothing...` — so the name is a claim the
author already made, in the one place a reviewer of the diff certainly reads. A
sweep over those names needs no list anybody maintains, which is what M6 cost and
what a hand-written inventory would cost again.

**What the shapes cannot see**, stated so nothing here is cited as more than it
is (`docs/MISTAKES.md` entry 14). A §4.1 denial written under some other name is
not demanded by this sweep and never will be: `tests/integration/
test_the_launch_views_name_nobody.py` says `name_nobody`, not `names_nobody`, and
is outside these shapes. The remedy when a new denial module wants covering is
to name it in one of these shapes or to add a shape here, in the pull request
that adds the module. This closes the naming convention the fix round used; it
does not close §4.1.

**One currency, and the module-level form is it.** A test can be marked two ways
and only one of them is demanded here. That is deliberate, and it is this
repository's own lesson: E0-36's first measurement of the marked set walked
`decorator_list` and answered 20 where the collector answered 24, because a
module-level `pytestmark` is invisible to a decorator walk —
`tests/unit/test_the_invariant_gate_refuses_a_test_that_asserts_nothing.py`
carries that incident in full. `docs/MISTAKES.md` entry 35's rule is that a guard
enumerating the currencies a privilege can be held in misses the one the design
uses; the answer taken here is not a longer enumeration but a shorter one. **The
sweep demands the module-level form and refuses every other**, so a module that
holds its marker in some other currency is red rather than quietly approved.

**So a per-test-decorated module is red here by design.** `tests/integration/
test_the_dev_console_names_nobody.py` is in exactly that state today: its one
denial test carries `@pytest.mark.invariant` and the module carries none. Nothing
is wrong with that test. What is wrong is that the module's *next* denial test
inherits nothing, which is the shape of the defect this file exists for — a
module half inside the pass reads, to every later reader, exactly like a module
inside it. The repair is one line in that module, not a widening here.

**The module-level form includes the list spelling**, and it has to. Two of the
three modules the re-review found already carry `pytestmark = [pytest.mark.
integration, pytest.mark.lti]`, and demanding the bare `pytestmark = pytest.mark.
invariant` of them would be demanding they drop the markers that place them in
the suite — a property no implementation could satisfy (`docs/MISTAKES.md` entry
24). What is pinned is *where* the mark sits, not how the assignment is written:
a module-level `pytestmark`, carrying `invariant` among its marks.

**This module is itself marked**, and it is not a term in its own set: its name
carries none of the shapes above, so the sweep does not demand itself and the
green does not come from the guard approving the guard.
"""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.invariant

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = REPO_ROOT / "tests"

MARKER = "invariant"

# The name of the module-level variable pytest reads marks out of.
MODULE_MARKS = "pytestmark"

# The filename shapes this project gives a confidentiality-denial module, as
# substrings of the module's stem. Written as the re-review names them, and each
# one is a sentence an author wrote about what the module proves: the page
# repeats nothing it was handed, the log names nobody, the refused write names
# nothing from the launch.
DENIAL_NAME_SHAPES = ("_names_nobody", "repeats_nothing", "names_nothing")

# Two real modules that certainly carry the module-level marker, used as the
# control that the reader below can find one on this tree rather than only on a
# planted file. `docs/MISTAKES.md` entry 35: a guard that only ever reports
# absence cannot tell you which mechanisms it can see. Neither carries a denial
# shape in its name, so neither is a member of the swept set — they are subjects
# the reader is required to succeed on, not offenders it is required to spare.
CERTAINLY_MARKED = (
    TESTS_ROOT / "unit" / "test_no_service_reads_an_identity_table_directly.py",
    TESTS_ROOT / "unit" / "test_the_org_views_are_read_only_through_the_grant.py",
)

# ---------------------------------------------------------------------------
# The planted tree for the control. Six modules: three the shapes must demand
# and three they must not, and among the demanded three every marking state a
# module can be in — the module-level form, the list form, per-test decoration,
# and nothing at all.
#
# Planted under `tmp_path` rather than pointed at real files, because a control
# built out of the tree it is controlling moves when the tree moves: the day
# somebody marks the last real offender, a control written over it stops
# demonstrating anything and reports success for having found nothing to find.
# ---------------------------------------------------------------------------

A_DENIAL_TEST = (
    "def test_the_page_names_nobody(page):\n"
    '    assert "somebody@example.invalid" not in page.body\n'
)

PLANTED_MODULES = {
    # Demanded, and marked the way the rule asks. The bare form.
    "test_a_planted_page_repeats_nothing_it_was_handed.py": (
        f"import pytest\n\npytestmark = pytest.mark.{MARKER}\n\n\n{A_DENIAL_TEST}"
    ),
    # Demanded, and marked in the list form — which is what a module already
    # carrying `integration` and `lti` has to use, and therefore what two of the
    # three real offenders will look like once they are fixed.
    "test_a_planted_write_names_nothing_from_the_launch.py": (
        f"import pytest\n\npytestmark = [pytest.mark.{MARKER}, pytest.mark.integration]\n\n\n"
        f"{A_DENIAL_TEST}"
    ),
    # Demanded, and the discriminating offender: the marker is held per test, in
    # the currency this rule refuses, beside a module-level `pytestmark` that
    # carries other marks. A sweep that accepted a decorator reads this as
    # compliant and goes on reading the *next* test in such a module — the one
    # nobody remembered to decorate — as compliant too.
    "test_a_planted_log_names_nobody.py": (
        "import pytest\n\npytestmark = [pytest.mark.integration]\n\n\n"
        f"@pytest.mark.{MARKER}\n{A_DENIAL_TEST}"
    ),
    # Demanded, and marked with nothing at all: the state all three real
    # offenders are in as this is written.
    "test_a_planted_console_names_nobody_at_all.py": f"import pytest\n\n\n{A_DENIAL_TEST}",
    # Not demanded: the name carries no denial shape. Unmarked, so a sweep that
    # demanded it would fail on it and this module would be red against a test
    # that is nobody's §4.1 invariant.
    "test_a_planted_module_about_something_else.py": f"import pytest\n\n\n{A_DENIAL_TEST}",
    # Not demanded, and the near miss that matters: `asserts_nothing` is not
    # `names_nothing` or `repeats_nothing`. The real
    # `test_the_invariant_gate_refuses_a_test_that_asserts_nothing.py` is a guard
    # on the gate's machinery and deliberately outside the §4.1 pass, and a
    # shape matcher reading for a bare "nothing" would drag it in.
    "test_a_planted_gate_refuses_a_test_that_asserts_nothing.py": (
        f"import pytest\n\n\n{A_DENIAL_TEST}"
    ),
}

PLANTED_DEMANDED = {
    "test_a_planted_page_repeats_nothing_it_was_handed.py",
    "test_a_planted_write_names_nothing_from_the_launch.py",
    "test_a_planted_log_names_nobody.py",
    "test_a_planted_console_names_nobody_at_all.py",
}

PLANTED_CARRYING_THE_MARKER = {
    "test_a_planted_page_repeats_nothing_it_was_handed.py",
    "test_a_planted_write_names_nothing_from_the_launch.py",
}


def carries_a_denial_shape(path: Path) -> bool:
    """Whether `path`'s own name claims the module denies something.

    Read off the stem rather than the whole path, so a directory that happens to
    carry one of these words does not enrol every module under it.
    """
    return any(shape in path.stem for shape in DENIAL_NAME_SHAPES)


def denial_modules() -> list[Path]:
    """Every test module under `tests/`, at any depth, whose name carries a shape.

    `rglob`, so a denial module filed in a directory that does not exist yet is
    swept the day it lands rather than the day somebody remembers this file.
    """
    return sorted(path for path in TESTS_ROOT.rglob("test_*.py") if carries_a_denial_shape(path))


def mark_name(node: ast.expr) -> str | None:
    """The marker a `pytest.mark.<name>` expression names, if it is one.

    A call is unwrapped first, because `pytest.mark.skipif(...)` and
    `pytest.mark.parametrize(...)` are marks written as calls and a reader that
    saw only bare attributes would report a module's mark list as shorter than it
    is. Matched on the `.mark.` in the middle rather than on the name `pytest`,
    so an aliased import is still read.
    """
    value = node.func if isinstance(node, ast.Call) else node
    if not isinstance(value, ast.Attribute):
        return None
    holder = value.value
    if isinstance(holder, ast.Attribute) and holder.attr == "mark":
        return value.attr
    return None


def module_level_marks(path: Path) -> frozenset[str]:
    """The marks `path` carries in a module-level `pytestmark`, by name.

    Only assignments in the module's own body: a `pytestmark` inside a class is a
    class-level mark, which is a third currency and not the one this rule pins.
    The **last** module-level assignment wins, because that is what Python
    evaluates — a reader that unioned them would count a mark that a later
    assignment had thrown away.

    A module that does not parse is a failure of this sweep rather than a file to
    pass over: it would drop silently out of the demanded set, and silence is
    what this whole module exists to stop being mistaken for compliance.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as failure:  # pragma: no cover - a broken test tree
        pytest.fail(
            f"{path.relative_to(REPO_ROOT)} does not parse ({failure}), so this sweep cannot read "
            "its markers and would report it compliant having read nothing."
        )

    found: frozenset[str] = frozenset()
    for statement in tree.body:
        assigned: ast.expr | None = None
        if isinstance(statement, ast.Assign):
            names = {target.id for target in statement.targets if isinstance(target, ast.Name)}
            if MODULE_MARKS in names:
                assigned = statement.value
        elif isinstance(statement, ast.AnnAssign):
            if isinstance(statement.target, ast.Name) and statement.target.id == MODULE_MARKS:
                assigned = statement.value
        if assigned is None:
            continue
        elements = list(assigned.elts) if isinstance(assigned, ast.List | ast.Tuple) else [assigned]
        found = frozenset(name for name in (mark_name(item) for item in elements) if name)
    return found


def test_the_denial_module_sweep_flags_a_planted_offender_and_spares_its_near_misses(
    tmp_path: Path,
) -> None:
    """The instrument, both directions, before the tree is judged with it.

    Two functions and four claims, and none of them can be believed off a green
    over the real tree — a shape matcher that matched nothing and a marker reader
    that found a marker on everything both make the sweep below silent
    (`docs/MISTAKES.md` entry 3, and entry 9 on citing a guard nobody has run).
    So the states are planted:

      - a module whose name carries a shape and whose module-level `pytestmark`
        carries `invariant` **passes**, in the bare form and in the list form.
        Without this half, a sweep that demanded the marker of nothing — or that
        could not read a `pytestmark` at all — would fail every module in the
        tree and be deleted rather than fixed, and the list form is what two of
        the three real offenders must end up in.
      - a module whose name carries a shape and holds its marker **per test** is
        **flagged**. This is the discriminating case and the reason the rule pins
        one currency: a sweep that accepted the decorator would report such a
        module compliant, and would go on reporting it compliant after somebody
        adds a second denial test to it and forgets to decorate that one.
      - a module whose name carries a shape and no marker at all is **flagged**.
      - a module whose name carries no shape is **not demanded**, marked or not,
        including `asserts_nothing`, which is neither `names_nothing` nor
        `repeats_nothing` and is the real machinery guard next door.

    **The mutation this kills:** widening `module_level_marks` to read decorators,
    or widening `carries_a_denial_shape` to a bare `"nothing"`. The first turns
    the sweep green over a module that is half inside the pass; the second drags
    the gate's own machinery guards into §4.1.
    """
    for name, source in PLANTED_MODULES.items():
        (tmp_path / name).write_text(source, encoding="utf-8")

    planted = sorted(tmp_path.glob("test_*.py"))
    assert len(planted) == len(PLANTED_MODULES), (
        f"{len(planted)} of {len(PLANTED_MODULES)} planted modules were written to {tmp_path}, so "
        "the control below is not the tree it describes."
    )

    demanded = {path.name for path in planted if carries_a_denial_shape(path)}
    assert demanded == PLANTED_DEMANDED, (
        f"The shape matcher demanded {sorted(demanded)} of the planted modules and the shapes "
        f"{list(DENIAL_NAME_SHAPES)} name {sorted(PLANTED_DEMANDED)}.\n\n"
        "Too few and the sweep below is silent over the modules it exists for. Too many and it is "
        "red against a module nobody claimed was a §4.1 denial — `asserts_nothing` is the near "
        "miss that distinguishes the shapes as written from a matcher reading for `nothing`."
    )

    marked = {path.name for path in planted if MARKER in module_level_marks(path)}
    assert marked == PLANTED_CARRYING_THE_MARKER, (
        f"The marker reader read a module-level `{MARKER}` on {sorted(marked)}; the planted "
        f"modules carrying one are {sorted(PLANTED_CARRYING_THE_MARKER)}.\n\n"
        f"`test_a_planted_log_names_nobody.py` holds `@pytest.mark.{MARKER}` on its test and a "
        "module-level `pytestmark` carrying other marks. If it is in the list above, this sweep "
        "reads decorators and cannot tell a module that is wholly inside the §4.1 pass from one "
        "that is half in — which is the state the re-review found and the reason the rule pins the "
        "module-level form.\n\n"
        "If the list form is missing instead, the sweep cannot be satisfied by two of the three "
        "modules it is about: they already carry `pytestmark = [pytest.mark.integration, "
        "pytest.mark.lti]`, and the marker joins that list rather than replacing it."
    )


def test_every_confidentiality_denial_module_carries_the_module_level_invariant_marker() -> None:
    """The closure: a module that says it denies something is inside the isolated pass.

    CLAUDE.md: "The §4.1 invariant suite may never be skipped. CI runs it in an
    isolated pass and treats a skip, an xfail, or an empty collection as a
    failure; `scripts/ci/check_invariants.py` enforces this." That enforcement
    reaches exactly the tests that carry the marker. An unmarked denial test is
    not reported as skipped — it is not reported at all, and its absence from the
    isolated pass looks the same as it never having been written.

    That is the recurrence the re-review of 2026-08-31 found. M6 marked the seven
    denial modules that existed when it was written; the fix round wrote three
    more and marked none, and no gate noticed, because the only gate on the marked
    set is one that reads the marked set.

    **The mutations this kills**: a new confidentiality-denial module landing with
    no marker, which is the defect itself and the only way it has ever arrived;
    and a marker moved from the module level onto the tests, which passes the
    collector today and leaves the module's next test outside the pass.

    **The near misses that must stay green**: a module marked in the list form
    beside `integration` and `lti`, which is what the modules in this finding will
    look like fixed; and any module whose name carries no denial shape, which this
    sweep does not reach at all — this closes a naming convention, not §4.1.

    **Two controls, because a sweep for absence is satisfied by emptiness.** The
    demanded set must be non-empty, or "every one of them is marked" is a
    statement about nothing. And the reader must find the marker on real modules
    that certainly carry it, or a reader that answers "no marks" for every file on
    disk would report every denial module as an offender — a red for the wrong
    reason, which is how a correct rule gets deleted.
    """
    assert TESTS_ROOT.is_dir(), (
        f"{TESTS_ROOT} is not a directory, so this sweep walked nothing. Every assertion below is "
        "true of an empty tree."
    )

    for path in CERTAINLY_MARKED:
        assert path.is_file(), (
            f"{path.relative_to(REPO_ROOT)} does not exist, so the control that this sweep can "
            "*find* a module-level marker at all has nothing to find. It is named here because it "
            "is wholly a §4.1 module and carries the bare `pytestmark` form; if it has been "
            "renamed, rename it here in the same change."
        )
        assert MARKER in module_level_marks(path), (
            f"The reader found no module-level `{MARKER}` on {path.relative_to(REPO_ROOT)}, which "
            f"carries one. It read {sorted(module_level_marks(path))}.\n\n"
            "A reader that cannot see a marker reports every module as an offender, so the "
            "assertion below would be red over a compliant tree and this file would be deleted "
            "rather than fixed (`docs/MISTAKES.md` entry 35: require the guard to find the thing "
            "on a subject that certainly has it)."
        )

    demanded = denial_modules()
    assert demanded, (
        f"No module under {TESTS_ROOT.relative_to(REPO_ROOT)} carries any of the denial name "
        f"shapes {list(DENIAL_NAME_SHAPES)}, so this sweep judged nothing and its silence means "
        "nothing. Either every such module has been renamed — in which case the shapes move with "
        "them, here, in the same change — or this walk is looking at the wrong tree."
    )

    outside = sorted(
        str(path.relative_to(REPO_ROOT))
        for path in demanded
        if MARKER not in module_level_marks(path)
    )
    assert not outside, "\n".join(
        [
            f"These confidentiality-denial modules carry no module-level `{MARKER}` marker, so "
            "they sit outside the isolated §4.1 pass:",
            *(f"  {path}" for path in outside),
            "",
            f"Each is named for what it denies — {list(DENIAL_NAME_SHAPES)} — which is the claim "
            "its author made in the diff. CLAUDE.md makes that pass unskippable and "
            "`scripts/ci/check_invariants.py` enforces it, but only over tests that carry the "
            "marker: an unmarked denial test is not reported skipped, it is not reported at all, "
            "and a green invariant pass says nothing about it.",
            "",
            f"The repair is one line per module: `pytestmark = pytest.mark.{MARKER}`, or "
            f"`pytest.mark.{MARKER}` added to the list a module already assigns there. Not a "
            "decorator on the one test that denies something — this rule pins the module-level "
            "form so that the module's *next* denial test inherits it, and a module holding its "
            "marker per test is red here by design until it adopts that form.",
            "",
            "The other repair, if a module named this way is genuinely not a §4.1 denial, is to "
            "rename it. Widening what this sweep accepts is not one of the answers: the re-review "
            "of 2026-08-31 found M6's own defect recurring three modules later, and a rule that "
            "accepts every currency is the rule that let it.",
        ]
    )
