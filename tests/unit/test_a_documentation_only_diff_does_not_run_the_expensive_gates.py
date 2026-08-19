"""A documentation-only diff does not run the expensive gates — ticket E0-38.

`.github/workflows/ci.yml` has no path filtering, so a pull request touching only
Markdown runs pytest against testcontainers, builds both images, brings up the
Compose stack, runs Playwright, runs the eval floors and audits the supply chain.
About fifteen minutes of runner time to establish that no Python changed, on a
shape this epic has produced six times.

**The shape is a short-circuit, not a job-level `if:`, and that is settled rather
than open.** E0-36 item 1 made the aggregate `ci` check treat `skipped` as a
failure, because a job whose dependency failed reports `skipped` and a row of them
was printing "All gates green". That was verified against the real pipeline: a
deliberate drift produced `Results: skipped, skipped, skipped, skipped, skipped,
skipped, skipped` and the required check reported failure. So a job switched off
by an `if:` on a documentation-only pull request arrives at that verdict as
`skipped` and **fails the one check branch protection points at**, on every such
pull request. Every expensive job therefore stays in `ci`'s `needs`, stays
unconditional, and switches its own work off at the *step* level — which is the
tolerance mechanism ADR 0002 already uses throughout this file. `skipped` keeps
exactly one meaning and the verdict step needs no new case.

**Trap 1 is that `docs/**` is not a safe skip set.** `tests/unit/test_ai_contracts.py`
reads `docs/SPEC.md` at test time, parsing §7.4's task table and verdict sets out
of the file rather than copying them into the test, so that changing a verdict
takes an edit to the spec. PR #39 edited `SPEC.md` and pytest was the one job that
had any business running. The rule is "documentation except the documentation
something parses", the skip set is an allowlist, and a path nobody has classified
runs everything.

**What this module asserts, and what it cannot.** Two of E0-38's criteria say to
verify by pushing to a scratch branch rather than by reading YAML — that a real
failure is still reported as a failure with the filter in place, and that a
documentation-only pull request completes with `CI` reporting success. Neither is
here, deliberately; nothing in pytest can watch GitHub schedule a job. What is
here is the classification, executed as the code it is, and the wiring that
decides which jobs consult it.

The wiring half asserts that each expensive gate's own work is *conditioned on*
the classification. It does not evaluate the condition, so it cannot tell a guard
with the right sense from one with the wrong sense — a step reading
`inert == 'true'` where it meant `!= 'true'` passes here and fails on the scratch
branch. That division is stated rather than papered over: this module is what
notices a gate that gained no guard at all, which is the failure the ticket would
otherwise ship, and the push is what notices a guard that reads backwards.

**The sweep, and what it can see.** `docs/SPEC.md` is the only document any test
reads today, and a hand-maintained exclusion beside it goes stale the first time
somebody teaches another test to read another document. So the requirement is
derived from the suite instead: every repository file a test module builds a path
to must be classified not-inert. That reads `/` chains out of the parsed source —
`REPO_ROOT / "docs" / "SPEC.md"`, and a name assigned one earlier in the same
module — and it deliberately does **not** collect bare string literals. It cannot:
`docs/MISTAKES.md` appears as prose in most modules in this suite, and
`test_prompt_directory_layout.py` holds `"README.md"` in a tuple of build inputs.
A literal sweep would demand that the mistakes file and the root README leave the
inert set, which is most of what the ticket exists to skip. The cost of the
narrower rule is that a document read through a form this does not model — an
`open()` on a literal, a path assembled at runtime, a constant imported from
`conftest.py` — is invisible, and the module says so where it fails rather than
implying coverage it does not have.

Because it is derived, it can also go quiet. `docs/MISTAKES.md` entry 35's
corollary is the one that applies: a control is only as complete as the list it
iterates, and this list comes from the tests rather than from anything the
workflow cannot shrink. Hence a written-down floor beside it — `docs/SPEC.md`
gets its own case, asserted whether or not the sweep can still see it, and the
sweep is required to find it before its verdict about anything else is believed.

**One module rather than two**, unlike the split between the `detect` probe
battery and the aggregate verdict. Both halves here depend on the same guessed
name for the same script, and splitting them would write that guess down twice —
`docs/MISTAKES.md` entry 13, a hazard worked around in one of the two places
facing it. Rename `CLASSIFIER` and both halves follow.
"""

import ast
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_TREE = REPO_ROOT / "tests"

# ---------------------------------------------------------------------------
# The interface, which is the one thing in this module that is a guess.
#
# E0-38 says a cheap classification step answers one question — does this diff
# touch anything outside the inert set? — and does not say what runs it or how it
# answers. Nothing existed to read when these tests were written, so the contract
# below is written down here, in one place, and it is **the implementer's to
# change**: point `CLASSIFIER` somewhere else, or teach `classify()` another
# calling convention, and every assertion in this module follows. What is not
# negotiable is the behaviour the cases assert, which comes from the acceptance
# criteria rather than from this shape.
#
# The contract:
#
#   python scripts/ci/classify_changed_paths.py <changed path>...
#     exit 0 — every path is inert, the expensive gates may short-circuit
#     exit 1 — something outside the inert set changed, run everything
#     any other exit — an error, and this module reports it rather than reading
#                      it as an answer
#
# **The polarity is argued rather than picked.** A script that is missing, that
# crashes, or that meets an argument it cannot parse exits non-zero, and non-zero
# is "run everything". So every way this can go wrong in the pipeline fails toward
# the full run, which is the direction the ticket demands of the classification
# itself. Reversing the two exits would make a crash indistinguishable from a
# documentation-only diff and skip every gate on it.
#
# **Inside this module the same tolerance is a hazard, and it is closed here.**
# Six of the cases below assert *not inert*, and a missing script satisfies all
# six by exiting 2 — a suite that goes green before anything is built, which is
# `docs/MISTAKES.md` entry 3 in its purest form. `classify()` therefore fails
# loudly on a missing file and on any exit code outside the two the contract
# names, so a not-inert verdict here can only come from a classifier that ran and
# decided.
# ---------------------------------------------------------------------------
CLASSIFIER = REPO_ROOT / "scripts" / "ci" / "classify_changed_paths.py"

INERT_EXIT = 0
NOT_INERT_EXIT = 1

INERT = "inert"
NOT_INERT = "not inert"

# The classification is meant to be cheap — the whole ticket is about not spending
# minutes to learn that no Python changed. A run longer than this is not slow, it
# is doing something the contract does not describe.
CLASSIFIER_TIMEOUT_SECONDS = 60

# Diffs that touch nothing but inert documentation, one per case. These are the
# three families E0-38's scope names: `docs/**` except what a test parses,
# `design/**`, and root `*.md`.
#
# The ticket calls them candidates, so a narrower allowlist is a decision somebody
# may make — and it is a decision, to be made in the ticket rather than by editing
# a test. A red here from a deliberately narrower inert set is a conversation, not
# a repair.
INERT_DIFFS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "a ticket, which is what most of this epic's documentation changes touch",
        ("docs/tickets/e0/README.md",),
    ),
    ("the mistakes file", ("docs/MISTAKES.md",)),
    ("an architecture decision record", ("docs/adr/0002-ci-gates-ship-tolerant.md",)),
    (
        "a record that is not in the tree, as a new file and a deleted one both appear in a diff",
        ("docs/adr/0071-a-record-this-test-invented.md",),
    ),
    (
        "a design file, including one whose name has a space in it",
        ("design/tokens.css", "design/Usage Rules.md"),
    ),
    ("a root Markdown file", ("README.md",)),
    ("several families at once", ("README.md", "docs/MISTAKES.md", "design/tokens.css")),
)

# Paths in neither set. The classification fails toward running everything, so a
# path nobody has classified runs the full pipeline.
#
# `backend/app/ai/prompts/validity.v1.md` is here on purpose and is not a stray
# Markdown file. It is a prompt, versioned in-repo under SPEC §7.4, and editing it
# changes what every eval floor in §9.3 measures. A classification written as "a
# `.md` file is documentation" gets every other case in this module right and this
# one catastrophically wrong, which is what makes it the case worth carrying.
UNCLASSIFIED_PATHS: tuple[tuple[str, str], ...] = (
    (
        "the workflow that decides which gates run at all",
        ".github/workflows/ci.yml",
    ),
    ("the project metadata and lint configuration", "pyproject.toml"),
    ("a hash-pinned lockfile", "requirements.txt"),
    ("the Compose file the build gate brings up", "docker-compose.yml"),
    (
        "a prompt, which is Markdown and is not documentation",
        "backend/app/ai/prompts/validity.v1.md",
    ),
    ("a path of a kind nobody has met yet", "ops/whatever/thing.unheard-of"),
)

# The document `tests/unit/test_ai_contracts.py` parses at test time, and the case
# the naive version of this ticket gets wrong. Written down rather than left to
# the sweep below, because a sweep derived from the suite goes quiet when the
# suite changes and this criterion does not.
PARSED_SPEC = "docs/SPEC.md"

# A Python file whose diff is entirely docstring. The classifier is given paths
# and never contents, so this is the same question as "did any `.py` change" —
# which is the phrasing E0-38 says gets it right, against a filter that asks
# whether a change "felt like docs". This epic's documentation pull requests have
# repeatedly included docstring edits inside Python files.
DOCSTRING_ONLY_EDIT = "backend/app/services/authz.py"

# ---------------------------------------------------------------------------
# The workflow half.
# ---------------------------------------------------------------------------
AGGREGATE_JOB = "ci"

# The five jobs E0-38's scope names, each with a search for the work the ticket
# says must not run on a documentation-only diff. The pattern is a floor rather
# than an inventory: a job may guard more steps than these, and it may not guard
# fewer.
#
# Anchored at the start of a line so a `pip install "pip-audit==…"` is not read as
# an audit and a commented-out command is not read as a command.
EXPENSIVE_GATES: dict[str, tuple[str, re.Pattern[str]]] = {
    "test": (
        "pytest, the §4.1 invariant pass included",
        re.compile(r"^\s*pytest\b", re.MULTILINE),
    ),
    "docker": (
        "the image build and the Compose stack",
        re.compile(r"^\s*docker\s+compose\b[^\n]*\b(?:build|up)\b", re.MULTILINE),
    ),
    "e2e": (
        "Playwright",
        re.compile(r"^\s*npx\b[^\n]*\bplaywright\b", re.MULTILINE),
    ),
    "evals": (
        "the eval runner, and with it SPEC §9.3's threat and self-harm recall floor",
        re.compile(r"^\s*python\s+-m\s+tests\.evals\.runner\b", re.MULTILINE),
    ),
    "supply-chain": (
        "the dependency audit and the licence scan",
        re.compile(r"^\s*(?:pip-audit|pip-licenses)\b", re.MULTILINE),
    ),
}

# The three fast jobs E0-38 leaves alone, and why each one.
UNCONDITIONAL_GATES: dict[str, tuple[str, re.Pattern[str]]] = {
    "lint-python": (
        "197s, and this epic's documentation pull requests have repeatedly included docstring "
        "edits inside `.py` files — which look like documentation and are not a documentation-only "
        "change",
        re.compile(r"^\s*ruff\s+(?:check|format)\b", re.MULTILINE),
    ),
    "migration-drift": (
        "41s, and E0-38 says to leave it",
        re.compile(r"^\s*alembic\s+check\b", re.MULTILINE),
    ),
    "ci-selftest": (
        "5s, and E0-38 says to leave it",
        re.compile(r"test_ci_scripts\.py"),
    ),
}

# A `${{ }}` comparison against a quoted literal, which is the idiom every
# condition in this workflow already uses. The literal is required to be non-empty
# where this is applied: `steps.classify.outputs.inert != ''` mentions the
# classification and can never switch anything off, so a containment check alone
# would accept a guard that does nothing.
COMPARISON = re.compile(
    r"(?P<reference>[A-Za-z_][A-Za-z0-9_.\-]*)\s*(?:==|!=)\s*(?P<quote>['\"])(?P<literal>[^'\"]*)(?P=quote)"
)

GUARDED = "guarded"
UNRECOGNISED = "unrecognised"
ABSENT = "absent"

# ---------------------------------------------------------------------------
# The sweep's own controls. Run against these before the real tree is swept, so a
# reader that has gone blind says so instead of reporting that the suite parses no
# documents at all (`docs/MISTAKES.md` entry 3).
# ---------------------------------------------------------------------------
READS_A_DOCUMENT_DIRECTLY = '''"""A module shaped like `tests/unit/test_ai_contracts.py`."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "docs" / "SPEC.md"
'''

READS_A_DOCUMENT_THROUGH_A_DIRECTORY = '''"""A module that names the directory first, which is the obvious next form."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"
BRIEF_PATH = DOCS / "DESIGN_BRIEF.md"
'''

MENTIONS_A_DOCUMENT_IN_PROSE = '''"""A module that cites `docs/MISTAKES.md` entry 3 and reads nothing."""


def test_something() -> None:
    """Cites `docs/SPEC.md` §4.1 in prose, as most modules in this suite do."""
    assert True, "see docs/MISTAKES.md entry 3, and docs/SPEC.md §4.1"
'''


def classify(paths: Sequence[str]) -> str:
    """What the classifier answers about a diff that touched exactly `paths`.

    `INERT` or `NOT_INERT`. Any other outcome — a missing script, a crash, an exit
    code the contract does not name — is a failure here rather than an answer,
    because the pipeline's fail-safe reading of a non-zero exit would otherwise
    make every not-inert assertion in this module pass against nothing at all.
    """
    if not CLASSIFIER.is_file():
        pytest.fail(
            f"{CLASSIFIER.relative_to(REPO_ROOT)} does not exist, so nothing classifies a diff.\n"
            "\n"
            "That path is this module's guess at where E0-38's classification step lives; the "
            "ticket describes what it must answer and does not name it. If it is built somewhere "
            "else or invoked some other way, change `CLASSIFIER` and `classify()` at the top of "
            "this file — they are written in one place so that the guess costs one edit.\n"
            "\n"
            "This fails rather than reading the missing file as 'not inert'. A missing script "
            "exits non-zero, which the pipeline is meant to read as 'run everything', and every "
            "not-inert case below would then pass over a ticket nobody had started."
        )

    try:
        # S603: the executable is this interpreter and the argument list is a
        # script from this repository plus literal paths written in this file.
        completed = subprocess.run(  # noqa: S603
            [sys.executable, str(CLASSIFIER), *paths],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=CLASSIFIER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"The classification ran for more than {CLASSIFIER_TIMEOUT_SECONDS}s over "
            f"{list(paths)}. E0-38 asks for a cheap step whose whole point is to be cheaper than "
            "the gates it switches off, so this is a broken contract rather than a slow machine."
        )

    if completed.returncode == INERT_EXIT:
        return INERT
    if completed.returncode == NOT_INERT_EXIT:
        return NOT_INERT

    pytest.fail(
        f"The classification exited {completed.returncode} over {list(paths)}, and the contract "
        f"this module assumes names only {INERT_EXIT} (inert) and {NOT_INERT_EXIT} (not inert).\n"
        f"  stdout: {completed.stdout.strip()[:600] or '(nothing)'}\n"
        f"  stderr: {completed.stderr.strip()[:600] or '(nothing)'}\n"
        "\n"
        "Reported rather than read as 'not inert'. In the pipeline any non-zero exit should send "
        "the run down the everything-runs path, and that tolerance is right there and wrong here: "
        "it would let a classifier that crashes on every input satisfy six of the cases in this "
        "module."
    )


def is_repository_root(node: ast.expr) -> bool:
    """Whether `node` is the `…parents[N]` idiom every module here uses for the root."""
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "parents"
    )


def repository_paths_named_in(source: str) -> set[str]:
    """Every repository file `source` builds a path to, repository-relative.

    Reads `/` chains only — `ROOT / "docs" / "SPEC.md"`, and a name assigned such
    a chain earlier in the same module — and requires the result to be a file that
    exists. Bare string literals are deliberately not collected; the docstring at
    the top of this module says why, and the short version is that `README.md` and
    `docs/MISTAKES.md` both appear as literals in this suite for reasons that have
    nothing to do with reading them.
    """
    tree = ast.parse(source)
    resolved: dict[str, str] = {}

    def joined(node: ast.expr) -> str | None:
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            left = joined(node.left)
            right = node.right
            if left is None:
                return None
            if not isinstance(right, ast.Constant) or not isinstance(right.value, str):
                return None
            return f"{left}/{right.value}".lstrip("/")
        if isinstance(node, ast.Name):
            return resolved.get(node.id)
        if is_repository_root(node):
            return ""
        return None

    for statement in tree.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if not isinstance(target, ast.Name):
            continue
        built = joined(statement.value)
        if built is not None:
            resolved[target.id] = built

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            built = joined(node)
            if built and (REPO_ROOT / built).is_file():
                found.add(built)
    return found


def repository_paths_named_by_the_suite() -> dict[str, list[str]]:
    """Every repository file the test suite builds a path to, and which modules do."""
    named: dict[str, list[str]] = {}
    for path in sorted(TEST_TREE.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            built = repository_paths_named_in(source)
        except SyntaxError as error:
            pytest.fail(
                f"{path.relative_to(REPO_ROOT)} does not parse ({error}), so this sweep skipped "
                "it. A module the sweep cannot read is a module whose document could quietly "
                "enter the inert set, which is the whole failure this test exists for."
            )
        for relative in built:
            named.setdefault(relative, []).append(str(path.relative_to(REPO_ROOT)))
    return named


def jobs_of(workflow: dict[str, Any], workflow_path: Path) -> dict[str, Any]:
    """Every job in the workflow, or a failure naming what was read instead."""
    jobs = workflow.get("jobs") or {}
    if not jobs:
        pytest.fail(
            f"{workflow_path} declares no jobs, or did not parse. The CI pipeline is what makes "
            "the §14.2 definition of done enforceable, so it existing is a precondition of this "
            "module meaning anything."
        )
    return dict(jobs)


def needs_of(job: Any) -> list[str]:
    """The jobs one job waits on, whether it named one or several."""
    declared = (job or {}).get("needs")
    if declared is None:
        return []
    if isinstance(declared, str):
        return [declared]
    return [str(name) for name in declared]


def steps_of(job: Any) -> list[dict[str, Any]]:
    """The steps of one job, as a list of mappings."""
    return [step for step in ((job or {}).get("steps") or []) if isinstance(step, dict)]


def runs_the_classifier(step: dict[str, Any]) -> bool:
    """Whether this step is the one that answers 'was the diff inert?'."""
    return CLASSIFIER.name in str(step.get("run") or "")


def classification_prefixes(jobs: dict[str, Any], job_name: str) -> list[str]:
    """The `${{ }}` prefixes carrying the classification into this job's conditions.

    A job may classify for itself, in a step with an `id` or one that writes
    `$GITHUB_ENV`, or it may read the answer from a job it needs — which is the
    cheaper shape, since the `detect` job already exists to emit booleans and one
    classification serves every gate. Both are recognised, and neither is
    preferred: the ticket leaves the placement open.
    """
    prefixes: list[str] = []
    for step in steps_of(jobs.get(job_name)):
        if not runs_the_classifier(step):
            continue
        step_id = step.get("id")
        if step_id:
            prefixes.append(f"steps.{step_id}.outputs.")
        if "GITHUB_ENV" in str(step.get("run") or ""):
            prefixes.append("env.")
    for need in needs_of(jobs.get(job_name)):
        if any(runs_the_classifier(step) for step in steps_of(jobs.get(need))):
            prefixes.append(f"needs.{need}.outputs.")
    return prefixes


def guard_verdict(condition: str, prefixes: Sequence[str]) -> str:
    """Whether `condition` switches its step off on the classification.

    `GUARDED` when it compares one of `prefixes` against a non-empty literal,
    `ABSENT` when it does not mention the classification at all, and
    `UNRECOGNISED` when it mentions it in a form this module does not model —
    reported rather than guessed at, because a condition read wrongly is an
    assertion nobody ever made.
    """
    mentioned = [prefix for prefix in prefixes if prefix in condition]
    if not mentioned:
        return ABSENT
    for match in COMPARISON.finditer(condition):
        reference = match.group("reference")
        if any(reference.startswith(prefix) for prefix in mentioned) and match.group("literal"):
            return GUARDED
    return UNRECOGNISED


def signature_steps(job: Any, pattern: re.Pattern[str]) -> list[tuple[str, dict[str, Any]]]:
    """The steps of `job` that run the work `pattern` names, with their names."""
    found: list[tuple[str, dict[str, Any]]] = []
    for index, step in enumerate(steps_of(job)):
        script = str(step.get("run") or "")
        if pattern.search(script):
            found.append((str(step.get("name") or f"step {index}"), step))
    return found


def upstream_closure(jobs: dict[str, Any], start: str) -> set[str]:
    """Every job `start` depends on, directly or through another job."""
    found: set[str] = set()
    pending = list(needs_of(jobs.get(start)))
    while pending:
        name = pending.pop()
        if name in found or name not in jobs:
            continue
        found.add(name)
        pending.extend(needs_of(jobs[name]))
    return found


def test_a_diff_of_only_inert_documentation_is_classified_inert() -> None:
    """The criterion the whole ticket exists for, and the case that makes the rest mean something.

    Six assertions in this module say *not inert*, and a classifier that answered
    "not inert" to everything would satisfy every one of them while leaving the
    pipeline exactly as it is — fifteen minutes of runner time to establish that no
    Python changed. This is the case that refuses that classifier, so it is the
    first one here and it is not decoration.

    The three families are E0-38's own: `docs/**` except what a test parses,
    `design/**`, and root `*.md`. One case names a document that does not exist in
    the tree, because a diff shows a new file and a deleted one exactly as it shows
    an edited one — trimming `docs/mistakes/` is a real change of this shape — and
    a classifier that demanded the file be on disk would send every documentation
    deletion down the full pipeline. One names a file whose name has a space in it,
    which `design/` is full of.

    **The mutation this survives:** an implementation that answers not-inert
    unconditionally, which is what a half-finished script does and what every other
    case here accepts. **The near miss that must stay green:** any spelling of the
    allowlist — a prefix table, a glob set, a derivation from the suite — since
    this judges the verdict and not how it is reached.
    """
    misread = [(case, list(paths)) for case, paths in INERT_DIFFS if classify(paths) != INERT]

    assert not misread, "\n".join(
        [
            "These diffs touch nothing but inert documentation and were not classified inert:",
            *(f"  {case}\n    {paths}" for case, paths in misread),
            "",
            "E0-38's first criterion is that a pull request like this completes without running "
            "pytest, the image build, Playwright, the evals or the supply-chain audit. Measured on "
            "PR #38, that is about fifteen minutes of runner time and ten of wall clock to "
            "establish that no Python changed, and this epic has produced six pull requests of "
            "this shape.",
            "",
            "The families are the ones E0-38's scope names as candidates, so a deliberately "
            "narrower allowlist will fail here. That is the right failure: narrowing the inert set "
            "is a decision to make in the ticket, with the cost written down, rather than by "
            "editing the case table in a test.",
        ]
    )


def test_the_spec_a_test_parses_at_test_time_is_not_inert() -> None:
    """Trap 1, and the case the naive version of this ticket gets wrong. PR #39 is the incident.

    `tests/unit/test_ai_contracts.py` reads `docs/SPEC.md` at test time: it parses
    §7.4's task table and the verdict sets out of the file rather than copying them
    into the test, deliberately, so that changing a verdict takes an edit to the
    spec — a reviewed act with its own diff — instead of an edit to a constant
    nobody reads. PR #39 edited `SPEC.md`, and pytest was the one job that had any
    business running.

    So `docs/**` is not a safe skip set, and a rule that reads "Markdown under
    `docs/` is inert" passes every other case in this module and silently stops
    running the suite that holds SPEC §7.4's contract.

    **Written down here rather than left to the sweep below**, and the direction is
    the point. The sweep derives its list from the tests, and a derived list goes
    quiet when the thing it derives from changes — `docs/MISTAKES.md` entry 35's
    corollary, that a control is only as complete as the list it iterates. This
    criterion does not depend on `test_ai_contracts.py` continuing to look the way
    it looks today.

    **The mutation this survives:** an inert set of `docs/**` with no exception at
    all. **The near miss that must stay green:** an exception expressed as a
    derivation from the suite rather than as a literal `docs/SPEC.md` in the
    allowlist, which is E0-38's stronger form and is preferred if it is cheap.
    """
    verdict = classify([PARSED_SPEC])

    assert verdict == NOT_INERT, (
        f"`{PARSED_SPEC}` was classified {verdict}, so a pull request editing the spec would skip "
        "pytest.\n"
        "\n"
        "`tests/unit/test_ai_contracts.py` parses §7.4's task table and verdict sets out of that "
        "file at test time, so that changing a verdict takes an edit to the spec rather than to a "
        "constant nobody reads. Editing it is exactly when the contract suite has to run, and PR "
        "#39 is the pull request where it did.\n"
        "\n"
        "The skip set is an allowlist of paths known to be inert, never a denylist of paths known "
        "to matter, and 'documentation except the documentation something parses' is the rule "
        "E0-38 asks for."
    )


def test_a_python_file_is_not_inert_however_documentary_the_edit() -> None:
    """Criterion 3: a docstring-only edit inside a `.py` file runs the full pipeline.

    This epic's documentation pull requests have repeatedly included docstring
    edits *inside* Python files. They look like documentation and they are not a
    documentation-only change: `Fast · ruff + mypy` has an opinion about them, and
    so does every test that reads a docstring. E0-38 is explicit that the filter
    asks "did any `.py` change" rather than "did this feel like docs".

    **The classifier is given paths and never contents**, which is why one path is
    the whole of this case. That is not a weaker test than diffing the file — it is
    the criterion, because the only way to get the docstring case wrong is to
    classify on something other than the path.

    **The mutation this survives:** a rule that treats a diff as inert when no line
    of it changes a statement, or one that reads `.py` files under a `docs`-shaped
    directory as documentation. **The near miss that must stay green:** any rule
    phrased on the suffix alone.
    """
    verdict = classify([DOCSTRING_ONLY_EDIT])

    assert verdict == NOT_INERT, (
        f"`{DOCSTRING_ONLY_EDIT}` was classified {verdict}. A `.py` file is never inert, whatever "
        "the diff inside it looks like: E0-38 keeps `Fast · ruff + mypy` running unconditionally "
        "for precisely this shape, because a docstring edit inside Python is not a "
        "documentation-only change and this epic has shipped several."
    )


def test_a_path_nobody_has_classified_is_not_inert() -> None:
    """Criterion 4: the classification fails toward running everything.

    The skip set is an allowlist of paths known to be inert, never a denylist of
    paths known to matter. This is the case that tells the two apart — an allowlist
    answers not-inert to a path it has never heard of, and a denylist answers
    inert, and every other case in this module is satisfied by either.

    Two of the paths are worth naming. `.github/workflows/ci.yml` is the file this
    ticket edits, and a change to it that skipped every gate would be a pipeline
    verifying itself into silence. `backend/app/ai/prompts/validity.v1.md` is
    Markdown and is not documentation: it is a prompt, versioned in-repo under SPEC
    §7.4, and editing it changes what every §9.3 eval floor measures — including the
    threat and self-harm recall floor CLAUDE.md calls a hard gate whose lowering is
    a safety decision. A classification written as "a `.md` file is documentation"
    gets every other case in this module right and that one silently wrong.

    **The mutation this survives:** replace the allowlist with a denylist —
    "inert unless it is `.py`" — which passes the docstring case, the spec case and
    the mixed case below. **The near miss that must stay green:** an allowlist that
    grows to cover a family somebody deliberately adds later, since nothing here
    asserts that these particular paths stay unclassified forever.
    """
    misread = [(why, path) for why, path in UNCLASSIFIED_PATHS if classify([path]) != NOT_INERT]

    assert not misread, "\n".join(
        [
            "These paths are in neither set and were classified inert:",
            *(f"  {path} — {why}" for why, path in misread),
            "",
            "E0-38: 'Whatever is built has to fail toward running everything: the skip set is an "
            "allowlist of paths known to be inert, never a denylist of paths known to matter, and "
            "a path nobody has classified runs the full pipeline.'",
            "",
            "The prompt file is the one to read twice if it is in that list. It is Markdown, it is "
            "not documentation, and it is what SPEC §9.3's eval floors are measured against — a "
            "rule that classifies by suffix skips the eval gate on the change that most needs it.",
        ]
    )


def test_a_diff_holding_one_inert_document_and_one_python_file_is_not_inert() -> None:
    """A mixed diff runs everything, which is the shape a real pull request usually has.

    Most changes that touch documentation also touch something else — a ticket
    edited beside the code it describes, an ADR written in the same pull request as
    the decision, which `CLAUDE.md` requires. The question is asked of the diff and
    not of each file, and a classification that answered per file and took the
    majority, or the first, or the last, would skip the gates on a real change.

    Both orders are exercised because a rule written as a fold can be sensitive to
    which file it meets first, and nothing about the diff fixes that order.

    **The mutation this survives:** decide on the first path and return, or on the
    last. **The near miss that must stay green:** any order-independent rule —
    'any path outside the allowlist', 'any `.py` at all'.
    """
    misread = [
        list(paths)
        for paths in (
            (DOCSTRING_ONLY_EDIT, "docs/MISTAKES.md"),
            ("docs/MISTAKES.md", DOCSTRING_ONLY_EDIT),
            ("README.md", "design/tokens.css", DOCSTRING_ONLY_EDIT),
        )
        if classify(paths) != NOT_INERT
    ]

    assert not misread, "\n".join(
        [
            "These diffs hold a Python file beside inert documentation and were classified inert:",
            *(f"  {paths}" for paths in misread),
            "",
            "The question E0-38 asks is about the diff — 'does this diff touch anything outside "
            "the inert set?' — so one path outside the set is the whole answer, whatever it sits "
            "beside and whichever order the paths arrive in. A pull request that edits an ADR "
            "beside the decision it records is the ordinary shape here; CLAUDE.md requires it.",
        ]
    )


def test_an_empty_diff_is_not_inert() -> None:
    """The edge the ticket does not decide, decided toward running everything.

    An empty list is not a documentation-only change. It is the absence of
    evidence, and the likeliest way to produce one is not an empty commit: it is
    the diff computation failing quietly — a base ref that does not exist, a
    shallow clone with no merge base, a comparison against the wrong SHA. In every
    one of those cases "nothing changed" is false, and reading it as inert skips
    every expensive gate on a change that may be entirely Python.

    The cost of deciding it the other way round is one full pipeline run on a
    genuinely empty diff, which is rare and harmless. The cost of deciding it as
    inert is a green `CI` over an unrun suite, which is E0-36's subject arriving
    one ticket later.

    **This is the test author's call and not the ticket's**, so it is written as
    its own test: if the decision goes the other way, this is one test to delete
    with a line in the pull request saying why, rather than a row buried in a table.

    **The mutation this survives:** `if not paths: return INERT`, which reads as a
    harmless base case. **The near miss that must stay green:** refusing an empty
    argument list outright with a usage error, which is a different answer to the
    same question and still never skips a gate — though it would need `classify()`
    taught the third exit code.
    """
    verdict = classify([])

    assert verdict == NOT_INERT, (
        "An empty diff was classified inert, so a run that computed no changed paths would skip "
        "pytest, the image build, Playwright, the evals and the supply-chain audit.\n"
        "\n"
        "An empty list is most often produced by the diff failing rather than by nothing having "
        "changed: a base ref that is not there, a shallow clone with no merge base, a comparison "
        "against the wrong SHA. Treating it as inert turns a broken path computation into a green "
        "required check over an entire pipeline that never ran.\n"
        "\n"
        "E0-38 does not decide this case. The test author decided it toward running everything, "
        "which is the direction the ticket takes on every case it does decide. Reversing it is a "
        "decision to record, not a test to soften."
    )


def test_nothing_the_test_suite_opens_by_path_is_classified_inert() -> None:
    """E0-38's stronger form: a new document-reading test cannot widen the skip in silence.

    `docs/SPEC.md` is the only document any test reads today, and the exception for
    it "is true when written and false the first time somebody teaches another test
    to read another document". A hand-written exception has nothing watching it. So
    the requirement is derived from the suite: every repository file a test module
    builds a path to must be classified not-inert, whether or not anybody
    remembered to write it into the allowlist.

    **What the sweep reads.** `/` chains out of the parsed source, including one
    that goes through a name assigned earlier in the same module, filtered to paths
    that exist. Not bare string literals — `docs/MISTAKES.md` is prose in most
    modules here and `"README.md"` sits in a tuple of build inputs in
    `test_prompt_directory_layout.py`, so a literal sweep would demand that the
    mistakes file and the root README leave the inert set, which is most of what
    this ticket exists to skip.

    **What it therefore cannot see**, said plainly rather than implied away: a
    document opened from a literal, from a path assembled at run time, or from a
    constant imported out of `conftest.py`. Those forms exist nowhere in this suite
    today and nothing stops one arriving. The sweep is a floor under the allowlist,
    not a proof that no test reads anything else.

    **Both controls run before the real tree is swept.** The reader must find the
    document in a module shaped like `test_ai_contracts.py` and in one that names
    the directory first, and must find nothing in a module that only cites
    documents in prose. Then it must still find `docs/SPEC.md` in the real tree —
    the canary, because a reader that has gone blind reports that the suite parses
    no documents at all, and an empty sweep passes this test perfectly
    (`docs/MISTAKES.md` entry 3).

    **The mutation this survives:** add a module under `tests/` that reads a
    document nothing else reads — the design brief, an ADR — without touching the
    workflow. **The near miss that must stay green:** a module that cites a
    document in a docstring or an assertion message, which is nearly every module
    in this suite.
    """
    direct = repository_paths_named_in(READS_A_DOCUMENT_DIRECTLY)
    assert PARSED_SPEC in direct, (
        f"The reader in this test does not find `{PARSED_SPEC}` in a module that assigns the "
        "repository root, a docs directory and a file name into one path — the exact shape of "
        "`tests/unit/test_ai_contracts.py`. It has gone blind, and the sweep below would report "
        "that the suite reads no documents at all."
    )

    through_a_directory = repository_paths_named_in(READS_A_DOCUMENT_THROUGH_A_DIRECTORY)
    assert "docs/DESIGN_BRIEF.md" in through_a_directory, (
        "The reader in this test cannot follow a path built in two steps — a directory constant, "
        "then a file under it. That is the obvious form for the second document-reading test "
        "somebody writes, so a sweep blind to it would miss exactly the case this exists for."
    )

    prose = repository_paths_named_in(MENTIONS_A_DOCUMENT_IN_PROSE)
    assert not prose, (
        f"The reader in this test found {sorted(prose)} in a module that only cites documents in "
        "a docstring and an assertion message. Nearly every module in this suite does that, so a "
        "reader this loose would demand that `docs/MISTAKES.md` and every other cited document "
        "leave the inert set — which is most of what E0-38 exists to skip, refused by a test "
        "rather than by a decision."
    )

    named = repository_paths_named_by_the_suite()
    assert PARSED_SPEC in named, (
        f"Sweeping `tests/**` found no module that builds a path to `{PARSED_SPEC}`, and "
        "`tests/unit/test_ai_contracts.py` does exactly that — it parses SPEC §7.4's task table "
        "and verdict sets out of the file at test time.\n"
        f"  the sweep found: {sorted(named) or 'nothing at all'}\n"
        "\n"
        "Either that test has stopped reading the spec, in which case this module needs its floor "
        "re-derived and E0-38's exception re-examined, or the reader above no longer sees the form "
        "the suite uses. Both leave the sweep silent, and a silent sweep passes."
    )

    inert = {
        relative: readers for relative, readers in named.items() if classify([relative]) == INERT
    }

    assert not inert, "\n".join(
        [
            "These repository files are read by the test suite and are classified inert, so a "
            "pull request editing one would skip the suite that reads it:",
            *(f"  {relative} — read by {readers}" for relative, readers in sorted(inert.items())),
            "",
            "E0-38, on the exception for `docs/SPEC.md`: it 'is true when written and false the "
            "first time somebody teaches another test to read another document'. This is that "
            "sweep — the set of parsed documents derived from the tests rather than restated in "
            "the workflow, so a new document-reading test cannot widen the skip in silence.",
            "",
            "The repair is to exclude the file from the inert set, not to stop the test reading "
            "it. A test that parses a document rather than copying it is the pattern §7.4's "
            "contract suite is built on, and it is worth more than the runner minutes.",
        ]
    )


def test_every_expensive_gate_reaches_the_classification_and_conditions_its_work_on_it(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """E0-38's scope: the five expensive gates short-circuit, and nothing else changes shape.

    Each of `Test · pytest + invariants`, `Build · images + Compose health`,
    `Test · Playwright e2e`, `Test · AI eval floors` and
    `Supply chain · audit + licenses` has to reach the classification — its own
    step, or a job it needs — and has to switch its real work off on the answer. A
    job that gained no such step is the failure this ticket would otherwise ship:
    the classification exists, something calls it, and the gate it was meant to
    skip runs anyway.

    **The guard is at the step level and must stay there.** A job-level `if:` is
    the obvious spelling and it breaks the pipeline outright. E0-36 item 1 made the
    aggregate `ci` check treat `skipped` as a failure — verified against the real
    pipeline, where a deliberate drift produced `Results: skipped, skipped,
    skipped, skipped, skipped, skipped, skipped` and the required check reported
    failure — so a job skipped by a path filter arrives at that verdict
    indistinguishable from a job whose dependency failed, and every
    documentation-only pull request fails its required check. Exiting early at the
    step level keeps `skipped` meaning exactly one thing.
    `test_the_aggregate_ci_check_sees_an_upstream_failure.py` already fails loudly
    if any job gains a job-level `if:`, over every job in the file, so nothing here
    duplicates it.

    **The signature steps are a floor, not an inventory.** A job may guard more
    steps than the ones searched for here — the setup, the install — and it may not
    guard fewer. Each search is required to find something before its verdict
    counts, because a job whose steps have been renamed would otherwise report
    every gate correctly guarded having looked at nothing.

    **What this cannot see.** The condition is read, not evaluated, so a guard with
    the sense reversed — `== 'true'` where it meant `!= 'true'` — passes here. That
    is the half E0-38 sends to a scratch branch: a real defect pushed with the
    filter in place must still fail, and a documentation-only pull request must
    still report success. This module is what notices a gate with no guard at all.

    **The mutation this survives:** drop the short-circuit from any one of the five
    jobs — the `evals` job is the expensive one to lose, since SPEC §9.3's threat
    and self-harm recall floor stops running with `CI` green. **The near miss that
    must stay green:** moving the classification into `detect` and having each gate
    read `needs.detect.outputs.<name>`, which is one classification rather than
    five and is the shape this file's tolerances already use.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)

    missing = sorted(name for name in EXPENSIVE_GATES if name not in jobs)
    assert not missing, (
        f"{ci_workflow_path} declares no {missing} job (it declares {sorted(jobs)}). E0-38's scope "
        "names those jobs by name; if one has been renamed, rename it here too rather than leaving "
        "this module looking for something that is gone."
    )

    unseen: list[str] = []
    for name, (work, pattern) in EXPENSIVE_GATES.items():
        if not signature_steps(jobs[name], pattern):
            unseen.append(f"  {name} — nothing in it matches {pattern.pattern!r} ({work})")

    assert not unseen, "\n".join(
        [
            "These jobs run none of the work this module expects to find in them:",
            *unseen,
            "",
            "Every verdict below is 'each step that does the work is guarded', and a job with no "
            "such step satisfies that having been looked at and not read. Either the gate no "
            "longer runs the thing E0-38 is about — which is a much larger finding than this "
            "ticket — or the search needs pointing at how it is spelled now.",
        ]
    )

    unreachable: list[str] = []
    unguarded: list[str] = []
    unrecognised: list[str] = []

    for name, (work, pattern) in EXPENSIVE_GATES.items():
        prefixes = classification_prefixes(jobs, name)
        if not prefixes:
            unreachable.append(f"  {name} — runs {work}, and nothing in it consults the diff")
            continue
        for step_name, step in signature_steps(jobs[name], pattern):
            verdict = guard_verdict(str(step.get("if") or ""), prefixes)
            if verdict == ABSENT:
                unguarded.append(f"  {name} / {step_name!r} — runs {work}, guarded by nothing")
            elif verdict == UNRECOGNISED:
                unrecognised.append(f"  {name} / {step_name!r} — `if: {step.get('if')}`")

    assert not unrecognised, "\n".join(
        [
            "These steps mention the classification in a form this module does not model:",
            *unrecognised,
            f"  it understands a comparison against a non-empty literal, as in "
            f"`needs.detect.outputs.frontend == 'true'` — the idiom {ci_workflow_path} already "
            "uses everywhere.",
            "",
            "Reported rather than accepted, because a condition read wrongly is an assertion "
            "nobody ever made. The non-empty literal is not pedantry: "
            "`steps.classify.outputs.inert != ''` mentions the classification and can never "
            "switch anything off. Teach `guard_verdict` the new form, or say here why it cannot "
            "change the answer.",
        ]
    )

    assert not (unreachable or unguarded), "\n".join(
        [
            "These gates do not short-circuit on a documentation-only diff:",
            *unreachable,
            *unguarded,
            "",
            "Measured on the documentation-only run for PR #38: pytest 390s, the image build "
            "228s, and about fifteen minutes of runner time in total to establish that no Python "
            "changed. This epic has produced six pull requests of that shape.",
            "",
            "The guard belongs on the steps, not on the job. E0-36 item 1 made the aggregate `ci` "
            "check treat `skipped` as a failure — a deliberate drift produced `Results: skipped, "
            "skipped, skipped, skipped, skipped, skipped, skipped` and the required check reported "
            "failure — so a job switched off by a job-level `if:` fails the one check branch "
            "protection points at, on every documentation-only pull request. Keep the job in "
            "`needs`, keep it unconditional, and let its own steps switch off.",
            "",
            "`evals` is the expensive one to get wrong: SPEC §9.3's threat and self-harm recall "
            "floor is a hard gate, and a gate that does not run is indistinguishable in a green "
            "checkmark from a gate that passed.",
        ]
    )


def test_the_expensive_gates_are_still_among_the_jobs_the_required_check_waits_on(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """Trap 2: the short-circuit must not cost the required check its sight of these gates.

    `ci` is the single check branch protection points at, and it concludes what it
    concludes from the jobs in its `needs`. A gate removed from that graph — an
    inviting way to stop a documentation-only run reporting `skipped` — is a gate
    whose failure the required check can no longer see, which is E0-36's whole
    subject arriving one ticket later and on purpose this time.

    This is the half `test_the_aggregate_ci_check_sees_an_upstream_failure.py` does
    not cover. That module walks whatever graph the file declares and asserts every
    job in it reaches the verdict; it has no opinion about which jobs ought to be
    in the graph, so deleting one from `ci`'s `needs` leaves it green. The two
    together say: these five gates are in the graph, and everything in the graph is
    seen.

    **The mutation this survives:** remove `evals` from `ci`'s `needs:` while
    leaving the job in the file. **The near miss that must stay green:** reaching a
    gate through another job rather than naming it directly, since the closure is
    walked transitively — putting the five behind a `heavy-gates-passed` job the
    way `fast-gate` already works would keep every one of them visible.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)

    assert AGGREGATE_JOB in jobs, (
        f"{ci_workflow_path} declares no `{AGGREGATE_JOB}` job (it declares {sorted(jobs)}). That "
        "job is the single required check branch protection points at; if it has been renamed, "
        "rename it here too rather than leaving this module looking for something that is gone."
    )

    closure = upstream_closure(jobs, AGGREGATE_JOB)
    assert closure, (
        f"The `{AGGREGATE_JOB}` job waits on nothing, so there is no gate whose failure it could "
        "report and the membership check below is satisfied by an empty graph. A required check "
        "with no needs is green whatever the pipeline did."
    )

    outside = sorted(name for name in EXPENSIVE_GATES if name not in closure)

    assert not outside, "\n".join(
        [
            f"These gates are no longer among the jobs the `{AGGREGATE_JOB}` check waits on: "
            f"{outside}.",
            f"  it reaches: {sorted(closure)}",
            "",
            "A gate outside that graph cannot fail the required check. Taking a job out of "
            "`needs:` is a tempting way to stop a documentation-only run reporting `skipped`, and "
            "it buys that by making the gate invisible on every other run too — a green checkmark "
            "over a gate nobody looked at, which is exactly what E0-36 was written to end.",
            "",
            "The shape E0-38 asks for keeps every job in `needs`, keeps it unconditional, and has "
            "its steps switch themselves off. Then `skipped` still means one thing and the verdict "
            "step needs no new case.",
        ]
    )


def test_the_fast_gates_run_whatever_the_diff_touched(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """E0-38's scope, the other direction: three jobs are deliberately left alone.

    `Fast · ruff + mypy` keeps running unconditionally, and the reason is the trap
    the whole ticket is built around: this epic's documentation pull requests have
    repeatedly included docstring edits *inside* Python files, which look like
    documentation and are not a documentation-only change. `Fast · migration
    drift` and `Fast · CI checker self-test` are 41s and 5s, and E0-38 says to
    leave them.

    A filter that skips these is not a smaller version of this ticket, it is a
    different and worse one: 197s of lint is the gate most likely to have an
    opinion about the edit somebody called documentation.

    The self-test is the sharpest of the three. It is the job that checks the CI
    checkers, and E0-38 adds one — so a run in which the classification is wrong is
    exactly the run in which the job that would have caught it must not be skipped
    by the classification.

    **The mutation this survives:** add the same short-circuit step to
    `lint-python` on the grounds that Markdown cannot fail ruff. **The near miss
    that must stay green:** anything at all happening in the five expensive jobs,
    since this looks only at these three.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)

    missing = sorted(name for name in UNCONDITIONAL_GATES if name not in jobs)
    assert not missing, (
        f"{ci_workflow_path} declares no {missing} job (it declares {sorted(jobs)}). E0-38 names "
        "these three as the jobs it deliberately leaves alone; if one has been renamed, rename it "
        "here too."
    )

    unseen: list[str] = []
    for name, (why, pattern) in UNCONDITIONAL_GATES.items():
        if not signature_steps(jobs[name], pattern):
            unseen.append(f"  {name} — nothing in it matches {pattern.pattern!r} ({why})")

    assert not unseen, "\n".join(
        [
            "These jobs run none of the work this module expects to find in them:",
            *unseen,
            "",
            "The assertion below is that this work is not conditioned on the diff, and work that "
            "cannot be found is not conditioned on anything — so the test would pass over a job "
            "that had been emptied. Either the gate no longer runs what E0-38 says to leave alone, "
            "or the search needs pointing at how it is spelled now.",
        ]
    )

    switched_off: list[str] = []
    for name, (why, pattern) in UNCONDITIONAL_GATES.items():
        prefixes = classification_prefixes(jobs, name)
        if not prefixes:
            continue
        for step_name, step in signature_steps(jobs[name], pattern):
            if guard_verdict(str(step.get("if") or ""), prefixes) != ABSENT:
                switched_off.append(f"  {name} / {step_name!r} — {why}\n    if: {step.get('if')}")

    assert not switched_off, "\n".join(
        [
            "These gates are supposed to run whatever the diff touched, and now consult it:",
            *switched_off,
            "",
            "E0-38's scope: '`Fast · ruff + mypy` keeps running unconditionally. It is 197s, and "
            "this epic's documentation pull requests have repeatedly included docstring edits "
            "*inside* Python files — which look like documentation and are not a "
            "documentation-only change.' `Fast · migration drift` and `Fast · CI checker "
            "self-test` are 41s and 5s; the ticket says leave them.",
            "",
            "The self-test is the one to think about twice. It is the job that checks the CI "
            "checkers, and this ticket adds one — so the run where the classification is wrong is "
            "the run where skipping it hides the mistake.",
        ]
    )
