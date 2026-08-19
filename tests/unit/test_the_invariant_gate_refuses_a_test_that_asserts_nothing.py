"""An `invariant`-marked test that asserts nothing is refused — ticket E0-36, item 3.

`scripts/ci/check_invariants.py` reads the JUnit XML a run produced. In a green
checkmark a skipped invariant looks exactly like a passing one, so that checker
treats a skip, an xfail and an empty collection as failures. **A test that ran and
asserted nothing looks exactly like a passing one too**, and the XML cannot say
otherwise: it carries no assertion count, so the test is counted toward the
"N invariant test(s) ran, none skipped, none failed" the checker prints. Found by
`spec-conformance` against a planted fixture whose marked test body ends after a
call.

**The rule, as E0-36 §3 states it.** An `invariant`-marked test's own body must
contain at least one of: an `assert` statement, a `with pytest.raises(...)` block,
or a `pytest.fail(...)` call. A body whose only statements are calls is refused.

**Helpers are not chased, and that is the decision rather than an oversight.** A
test that delegates its whole control to a module-level helper which asserts is
correct, and this rule refuses it. Chasing calls means choosing a depth — one
level, two, an imported helper — and every choice of depth is arbitrary. The
refusal is loud and the fix is one line in the test. The refused-by-design case is
planted below precisely because it is the near miss that tells the rule as written
apart from something looser: a checker that greps the whole *file* for an `assert`
allows it, and that checker would also allow the planted fixture the item came
from if a helper happened to sit above it.

The rule was chosen for what it permits next, not to accommodate anything already
here. All 20 `invariant`-marked tests in the tree carry an `assert` in their own
body, none inside a nested function, and every one that uses `pytest.raises` also
asserts directly — measured before the rule was picked, so no existing test moves.

**The interface this test assumes, said out loud because the ticket names the
checker and not its arguments.** `scripts/ci/check_invariant_assertions.py` takes
one or more paths, and exits non-zero when a marked test under them breaks the
rule. That is the shape of every other checker in `scripts/ci/` — a path in, an
exit status out — and the directory grain is the one the gate itself uses, since
both callers will point it at the test tree. A red on the *allowed* half is
therefore a message about the contract rather than about the rule, and it says so.

**On the duplication with `scripts/ci/test_ci_scripts.py`.** That file holds the
checker's own behavioural self-test, written by whoever writes the checker, and it
runs in the `ci-selftest` job. This runs in the `test` job, and it is written from
the rule rather than from the implementation — the two are the same subject
approached from opposite sides, which is the point of the test wall standing
between them. The checker being wired into both callers is asserted next door, in
`tests/unit/test_invariant_gate_is_strict.py`, whose subject is the gate's two
callers.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "ci" / "check_invariant_assertions.py"

# The name of the test inside a planted sample, used to attribute a refusal to the
# thing that was planted rather than to the checker having fallen over.
PLANTED_TEST = re.compile(r"^def (?P<name>test_\w+)", re.MULTILINE)

# Every sample the rule permits. Four of the five are shapes that exist in the
# invariant suite today — an assert inside a `with` and a `for` is how
# `tests/integration/test_identity_grants.py` writes every one of its refusals —
# and a checker that reads only the top level of a body would refuse them. The
# fifth is the boundary of the rule's subject: it is about `invariant`-marked
# tests, and a checker that refused every assertion-free function would be red
# against most of the suite and against every helper in it. That fifth sample
# carries a compliant marked test beside the unmarked one on purpose, so that a
# checker which — by analogy with `check_invariants.py` — treats a scan finding no
# marked test at all as a failure is not read here as having applied the rule.
ALLOWED = {
    "an assert in the body": """
import pytest


@pytest.mark.invariant
def test_a_student_never_sees_a_benchmark(reporting, student):
    payload = reporting.student_results(student)
    assert "benchmark" not in payload
""",
    "an assert nested inside a with block and a loop": """
import pytest


@pytest.mark.invariant
def test_the_application_role_is_refused_a_select_on_user_identity(db_session):
    with acting_as(db_session, "pulse_app"):
        for view in read_views(db_session):
            assert refused(db_session, view) is not None
""",
    "a pytest.raises block": """
import pytest


@pytest.mark.invariant
def test_a_scoped_reader_refuses_what_is_outside_the_purview(reader):
    with pytest.raises(PermissionError):
        reader.read(section_id="outside-the-purview")
""",
    "a pytest.fail call": """
import pytest


@pytest.mark.invariant
def test_care_is_not_reachable_from_a_claim(claim):
    if resolve(claim).care is not None:
        pytest.fail("a launch claim resolved to a Care capability")
""",
    "an unmarked test with no assertion, beside a marked one that has": """
import pytest


@pytest.mark.invariant
def test_a_student_never_sees_a_sibling_section(reporting, student):
    assert reporting.sections_for(student) == [student.section_id]


def test_the_seed_script_is_safe_to_run_twice(seed):
    seed.load()
""",
}

# Every sample the rule refuses. The first is the shape the item came from. The
# second is the accepted cost, stated in E0-36 §3, and it is the discriminating
# case: the helper it calls *does* assert, so a checker that searches the file
# rather than the body allows it. The third is a shape the invariant suite already
# uses — `tests/integration/test_role_assignment_graph.py` stacks `invariant` above
# `parametrize` — so a checker that reads only the first decorator would not even
# see this as a marked test.
REFUSED = {
    "a body that ends after a call": """
import pytest


@pytest.mark.invariant
def test_an_instructor_report_exposes_no_identity(reporting, seeded_section):
    reporting.section_responses(seeded_section)
""",
    "a body whose only assertion is inside a helper it calls": """
import pytest


def refuses(action, what):
    assert action() is None, what


@pytest.mark.invariant
def test_a_lead_never_holds_a_sibling_leads_course(graph):
    refuses(lambda: graph.assign("LEAD_FACULTY", scope_kind="department"), "a lead scoped wide")
""",
    "a marked test with a second decorator whose body ends after a call": """
import pytest


@pytest.mark.invariant
@pytest.mark.parametrize("wrong_kind", ["prefix", "department"])
def test_an_assignment_scoped_above_its_course_is_refused(graph, wrong_kind):
    graph.assign("LEAD_FACULTY", scope_kind=wrong_kind)
""",
}


def slug(case: str) -> str:
    """A directory name for one case, so a failure names the sample it came from."""
    return re.sub(r"[^a-z0-9]+", "-", case.lower()).strip("-")


def planted(root: Path, case: str, source: str) -> Path:
    """Write one sample as the only test file in a directory of its own.

    One directory per case, because the verdict is per run: a checker handed two
    samples at once answers about the pair, and this needs to know which of them
    it answered about.
    """
    directory = root / slug(case)
    directory.mkdir(parents=True)
    path = directory / "test_planted.py"
    path.write_text(source.lstrip("\n"), encoding="utf-8")
    return directory


def verdict(directory: Path) -> subprocess.CompletedProcess[str]:
    """Run the checker over one planted directory and answer what it did."""
    # S603: the executable is this interpreter and the argument list is a checker
    # from this repository plus a directory this test just created. Nothing here
    # comes from outside.
    return subprocess.run(  # noqa: S603
        [sys.executable, str(CHECKER), str(directory)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_assertion_checker_refuses_the_shapes_the_rule_names_and_allows_their_near_misses(
    tmp_path: Path,
) -> None:
    """E0-36 criterion 3, both directions, one property.

    The two halves are not separable. A checker that exits non-zero whatever it
    is given satisfies every refusal here perfectly and fails the whole invariant
    suite on the day it lands; a checker that exits 0 whatever it is given passes
    every allowance and is the state this item exists to leave. Asserting them
    apart would let either half go green for the other's reason
    (`docs/MISTAKES.md` entry 3), so they are asserted together and the message
    says which way each case went.

    Refusals are additionally required to *name* the test they refused. A gate
    that says only "something is wrong" cannot be acted on, and — the reason it is
    asserted rather than assumed — a non-zero exit from a checker that crashed on
    its arguments is indistinguishable from one that applied the rule. The
    allowances would catch that too; this catches it with a message that says so.

    **The mutation this survives:** in `scripts/ci/check_invariant_assertions.py`,
    search the whole module for an assertion rather than the marked test's own
    body — which is the single most likely way to write it, and which allows the
    helper-delegated sample the rule refuses. **The near miss that must stay
    green:** widening the checker to recognise an assertion nested inside a `with`
    block, a `for` loop or an `if` — the rule says the body must *contain* one, and
    the invariant suite writes them that way today.
    """
    assert CHECKER.is_file(), (
        f"{CHECKER.relative_to(REPO_ROOT)} does not exist. E0-36 §3 puts the rule there: an "
        "`invariant`-marked test's own body must contain an `assert`, a `with pytest.raises(...)` "
        "or a `pytest.fail(...)`. Until it does, a marked test that runs and asserts nothing is "
        "counted as a passing invariant by the gate CLAUDE.md says may never be skipped."
    )

    wrong: list[str] = []
    unattributed: list[str] = []

    for case, source in sorted(ALLOWED.items()):
        result = verdict(planted(tmp_path, case, source))
        if result.returncode != 0:
            wrong.append(
                f"  refused {case}, which the rule allows (exit {result.returncode})\n"
                f"    {result.stdout.strip() or result.stderr.strip()}"
            )

    for case, source in sorted(REFUSED.items()):
        directory = planted(tmp_path, case, source)
        result = verdict(directory)
        if result.returncode == 0:
            wrong.append(f"  allowed {case}, which the rule refuses (exit 0)")
            continue
        match = PLANTED_TEST.search(source)
        name = match.group("name") if match else ""
        if name and name not in (result.stdout + result.stderr):
            unattributed.append(
                f"  {case}: exit {result.returncode} without naming `{name}`\n"
                f"    {result.stdout.strip() or result.stderr.strip()}"
            )

    assert not wrong, "\n".join(
        [
            "The invariant assertion checker gave the wrong verdict on planted samples:",
            *wrong,
            "",
            "E0-36 §3: an `invariant`-marked test's own body must contain an `assert` statement, "
            "a `with pytest.raises(...)` block, or a `pytest.fail(...)` call, and a body whose "
            "only statements are calls is refused.",
            "",
            "The two shapes worth reading twice. **A helper-delegated body is refused** — the "
            "helper asserts and the test does not, and the ticket accepts that cost rather than "
            "choosing how many levels of call to chase; a checker that searches the module rather "
            "than the body allows it, and allows the planted fixture this item came from whenever "
            "a helper happens to sit above it. **An assertion nested inside a `with`, a `for` or "
            "an `if` is allowed** — `tests/integration/test_identity_grants.py` writes every "
            "refusal that way, so a checker reading only the top level of a body is red against "
            "the suite it guards.",
            "",
            "If the failures above are all on the allowed half, suspect this test's assumption "
            "about the checker's arguments before suspecting the rule: it passes a directory and "
            "expects a non-zero exit only for a violation.",
        ]
    )

    assert not unattributed, "\n".join(
        [
            "The checker refused these samples without naming the test it refused:",
            *unattributed,
            "",
            "A refusal that names nothing cannot be acted on — `check_invariants.py` prints "
            "`skipped: <name>` per offender for the same reason — and it is also how a checker "
            "that fell over on its arguments looks from here. The assertions above read a "
            "non-zero exit as the rule being applied; this is what makes that reading safe.",
        ]
    )
