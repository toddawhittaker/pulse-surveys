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

**A third half, added after the implementation: the step in between.** The
classifier being right and the gates being wired to it are worth nothing if the
step that joins them cannot run. It hit that once already — the first version
invoked `python`, which is not on a runner's PATH in a job that declares no
`actions/setup-python`, so it exited 127 and the branch below it emitted
`inert=false` forever. The filter would never once have fired, on any pull
request, and nothing in a green pipeline would have said so. That was fixed while
building and nothing asserted the fix: reverting `python3` to `python` left all
348 tests and 100 self-test checks green, which is `docs/MISTAKES.md` entry 2
exactly. So the step is now executed here, over planted repositories, with
`python3` resolving and `python` answering 127 — the status a shell gives a
command that is not there — proved by running all three rather than by trusting
whatever the machine this suite happens to be on has installed.

**That half is executed rather than read, and it is the shape of test that pays
for itself twice.** Running the step end to end also asks what happens on every
route out of it: no base commit, a base the clone does not hold, a diff that
errors, a classifier that answers neither of its two answers. Each must emit a
classification that runs everything, and each must leave the step itself
succeeding — a step that *fails* takes the `changed` job down with it, and every
gate that needs it then reports `skipped`, which the aggregate check reads as
failure.

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
import os
import re
import shutil
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


# ---------------------------------------------------------------------------
# The step in between: the `changed` job, executed on a runner-shaped PATH.
# ---------------------------------------------------------------------------
CHANGED_JOB = "changed"

# The step that produces the job's answer is found through the job's own
# `outputs:` block rather than by position, so a job that grows a second step is
# still read correctly and a renamed output fails loudly instead of quietly.
STEP_OUTPUT_REFERENCE = re.compile(
    r"\$\{\{\s*steps\.(?P<step>[A-Za-z0-9_-]+)\.outputs\.(?P<name>[A-Za-z0-9_-]+)\s*\}\}"
)

# A `name=value` line as the step writes it into `$GITHUB_OUTPUT`.
EMITTED = re.compile(r"^(?P<name>[A-Za-z0-9_-]+)=(?P<value>.*)$")

# `python` is not on a GitHub runner's PATH in a job that declares no
# `actions/setup-python`:
#
#   $ env -i PATH=/usr/bin:/bin sh -c 'command -v python; command -v python3'
#   python: NOT FOUND
#   /usr/bin/python3
#
# The step is run with a directory of this module's own at the front of PATH,
# holding a `python` that does what a shell does for a command that is not there:
# a line on stderr and exit 127. **Simulated rather than removed**, and the choice
# is between two fragilities. A PATH rebuilt from nothing but symlinked `git` and
# `python3` is true absence, and it also changes how those two find their own
# helpers — so a failure under it would be as likely to be this module's as the
# workflow's, on a machine nobody can inspect from here. What the defect is
# observable as is an exit status, and this reproduces that exactly while leaving
# everything else the machine has where it was.
#
# It has to be planted rather than relied upon either way: a developer's machine
# may well have a working `python`, and a test that only fails on machines without
# one reports the health of the machine.
MISSING_COMMAND_STATUS = 127
ABSENT_ON_THE_RUNNER = "python"
PYTHON_SHIM = (
    f'#!/bin/sh\necho "{ABSENT_ON_THE_RUNNER}: command not found" >&2\n'
    f"exit {MISSING_COMMAND_STATUS}\n"
)

# What the job does have, and what every control below proves it still has. A PATH
# on which `python` worked would let the interpreter mutation run perfectly and
# pass every case in this section (`docs/MISTAKES.md` entry 3); a PATH on which
# `git` or `python3` had stopped resolving would fail every case for a reason that
# has nothing to do with the workflow.
RUNNER_MUST_RESOLVE = ("git", "python3")

PATH_DESCRIPTION = (
    "this machine's PATH, behind a planted directory in which `python` exits 127 "
    "exactly as a runner without `actions/setup-python` makes it"
)

# GitHub runs a `run:` block that declares no `shell:` as `bash -e {0}`. The `-e`
# is not a detail here: the step captures a deliberate non-zero exit from the
# classifier, and a script run without `-e` behaves differently from one run with
# it at exactly that line. Faithful to the runner, and the same invocation
# `test_the_detect_probes_see_the_files_their_jobs_run.py` already uses.
STEP_SHELL_FLAGS = ("-e",)

STEP_TIMEOUT_SECONDS = 120

# Enough of a repository for `git diff` to have something to say. The seed file is
# committed and never touched again, so a case that changes nothing still has a
# tree to diff.
SEED_FILE = "seed.txt"

# A diff of only inert documentation, and one that touches code. Real paths in a
# planted tree, so the classifier under them is answering the question this whole
# module is about rather than one invented for this test.
INERT_CHANGE = "docs/MISTAKES.md"
CODE_CHANGE = "backend/app/services/authz.py"

# A stand-in for the classifier that answers neither of its two answers, for the
# one case the real one cannot produce on demand. Everything else below runs the
# real script.
CLASSIFIER_THAT_ANSWERS_NEITHER = "import sys\n\nsys.exit(3)\n"

# A base that looks like a commit and is not in the clone. Forty hex digits, so
# the emptiness checks above it pass it through to `git cat-file`.
ABSENT_BASE_SHA = "b" * 40

# `git`'s own environment for the commits this module makes. The two
# `GIT_CONFIG_*` variables keep a developer's global configuration out of it —
# a global `commit.gpgsign` would otherwise fail the commit and this test with it.
GIT_ENVIRONMENT = {
    "GIT_AUTHOR_NAME": "E0-38 test",
    "GIT_AUTHOR_EMAIL": "e0-38@example.invalid",
    "GIT_COMMITTER_NAME": "E0-38 test",
    "GIT_COMMITTER_EMAIL": "e0-38@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
}


def git(root: Path, *arguments: str) -> str:
    """Run one git command in `root`, or fail saying what it said."""
    executable = shutil.which("git")
    if executable is None:
        pytest.fail(
            "git is not on PATH, so no repository can be planted and the `changed` job's step "
            "cannot be given a diff to classify. This fails rather than skipping: a skip here is "
            "indistinguishable from a step that classified correctly."
        )
    # S603: the executable is a resolved absolute path and the arguments are
    # literals from this module.
    completed = subprocess.run(  # noqa: S603
        [executable, *arguments],
        cwd=root,
        env=os.environ | GIT_ENVIRONMENT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.fail(
            f"`git {' '.join(arguments)}` exited {completed.returncode} in the planted repository "
            f"at {root}.\n  {completed.stderr.strip()}\n"
            "\nThis is the test's own fixture failing rather than the workflow "
            "(`docs/MISTAKES.md` entry 13)."
        )
    return completed.stdout.strip()


def planted_repository(root: Path, touched: Sequence[str]) -> str:
    """A repository with two commits, the second touching `touched`. Answers the base SHA.

    The files exist in both commits, so what the diff reports is a modification —
    the ordinary shape of a pull request, rather than the additions a fresh tree
    would produce.
    """
    root.mkdir(parents=True)
    git(root, "init", "--quiet")

    for relative in [SEED_FILE, *touched]:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("planted by E0-38's tests\n", encoding="utf-8")
    git(root, "add", SEED_FILE, *touched)
    git(root, "commit", "--quiet", "-m", "base")

    for relative in touched:
        (root / relative).write_text("planted by E0-38's tests, edited\n", encoding="utf-8")
    if touched:
        git(root, "add", *touched)
        git(root, "commit", "--quiet", "--allow-empty", "-m", "the change under test")
    else:
        git(root, "commit", "--quiet", "--allow-empty", "-m", "nothing at all")

    return git(root, "rev-parse", "HEAD~1")


def install_real_classifier(root: Path) -> None:
    """Point the planted repository at this repository's own scripts and tests.

    Symlinked rather than copied, and the whole directories rather than the one
    file, so that whatever the classifier reads — a sibling module, the suite it
    derives the parsed documents from — it reads the real thing. A copy of one
    file into an empty tree would test the classifier against a repository that
    does not exist.

    Neither symlink is committed, so neither appears in the diff the step
    computes.
    """
    (root / "scripts").symlink_to(REPO_ROOT / "scripts", target_is_directory=True)
    (root / "tests").symlink_to(TEST_TREE, target_is_directory=True)


def install_classifier_source(root: Path, source: str) -> None:
    """Put a stand-in classifier where the step will look for it."""
    directory = root / CLASSIFIER.parent.relative_to(REPO_ROOT)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / CLASSIFIER.name).write_text(source, encoding="utf-8")


def runner_shaped_path(root: Path) -> str:
    """A PATH on which `python` behaves as it does on a runner with no setup-python.

    Every claim it makes is executed before it is returned: `python` must exit
    127, and `git` and `python3` must still resolve. A guard that has never been
    run is a comment (`docs/MISTAKES.md` entry 9), and this one is load-bearing in
    both directions — the whole section is vacuous if `python` still works, and
    every case in it fails for the wrong reason if the other two stop resolving.
    """
    shell = shutil.which("bash")
    if shell is None:
        pytest.fail(
            "bash is not on PATH, so the step cannot be executed as GitHub executes it. This "
            "fails rather than skipping: a skip is indistinguishable from a step that ran and "
            "classified correctly."
        )

    bin_directory = root / "runner-bin"
    bin_directory.mkdir(parents=True)
    shim = bin_directory / ABSENT_ON_THE_RUNNER
    shim.write_text(PYTHON_SHIM, encoding="utf-8")
    shim.chmod(0o755)

    path = f"{bin_directory}{os.pathsep}{os.environ.get('PATH', '')}"

    def probe(command: str) -> subprocess.CompletedProcess[str]:
        # S603: a resolved absolute path, and a command built from this module's
        # own literals.
        return subprocess.run(  # noqa: S603
            [shell, "-c", command],
            env={"PATH": path},
            capture_output=True,
            text=True,
            check=False,
        )

    invoked = probe(f"{ABSENT_ON_THE_RUNNER} --version")
    if invoked.returncode != MISSING_COMMAND_STATUS:
        pytest.fail(
            f"Running `{ABSENT_ON_THE_RUNNER}` under the PATH this module plants exited "
            f"{invoked.returncode}, and a runner with no `actions/setup-python` answers "
            f"{MISSING_COMMAND_STATUS}.\n"
            f"  planted: {shim}\n"
            f"  said:    {(invoked.stdout + invoked.stderr).strip()[:400] or '(nothing)'}\n"
            "\n"
            "Every case in this section is written to catch a step that invokes an interpreter "
            "the runner does not have. With `python` working here they would all pass against "
            "exactly that defect."
        )

    for name in RUNNER_MUST_RESOLVE:
        if probe(f"command -v {name}").returncode != 0:
            pytest.fail(
                f"`{name}` does not resolve under the PATH this module plants, so the step under "
                "test cannot run for a reason that has nothing to do with the workflow. Every "
                "case in this section would fail, and each one would look like a defect in "
                "`ci.yml`."
            )

    return path


def classification_step(
    workflow: dict[str, Any], workflow_path: Path
) -> tuple[str, dict[str, Any]]:
    """The output name the `changed` job publishes, and the step that produces it."""
    jobs = jobs_of(workflow, workflow_path)
    job = jobs.get(CHANGED_JOB)
    if not job:
        pytest.fail(
            f"{workflow_path} declares no `{CHANGED_JOB}` job (it declares {sorted(jobs)}). That "
            "job is where E0-38's classification runs; if it has been renamed, rename it here too "
            "rather than leaving this module looking for something that is gone."
        )

    published = [
        (name, match)
        for name, value in (job.get("outputs") or {}).items()
        if (match := STEP_OUTPUT_REFERENCE.search(str(value)))
    ]
    if len(published) != 1:
        pytest.fail(
            f"The `{CHANGED_JOB}` job publishes {len(published)} step outputs and this module "
            "expects exactly one — the classification every expensive gate reads.\n"
            f"  outputs: {dict(job.get('outputs') or {})}\n"
            "\n"
            "If the job now publishes several, this module has to be told which one is the "
            "verdict rather than guessing at it."
        )

    output_name, match = published[0]
    step_id = match.group("step")
    for step in steps_of(job):
        if step.get("id") == step_id:
            return output_name, step

    pytest.fail(
        f"The `{CHANGED_JOB}` job publishes `{output_name}` from a step with id `{step_id}`, and "
        "no step in that job has that id. Nothing writes the output every expensive gate reads, "
        "so it would arrive empty — and an empty output is not `'true'`, which means every gate "
        "runs and the filter has silently never fired."
    )


def run_classification_step(
    step: dict[str, Any],
    repository: Path,
    workspace: Path,
    event: dict[str, str],
) -> tuple[int, dict[str, str], str]:
    """Execute the step over a planted repository. Answers its status, outputs and log.

    Run the way GitHub runs it — `bash -e`, the context values arriving through
    the environment the step's own `env:` block puts them in — and with `python`
    answering 127, which is what the job's empty `uses:` list leaves on a runner.
    """
    shell = shutil.which("bash")
    if shell is None:
        pytest.fail("bash is not on PATH, so the step cannot be executed as GitHub executes it.")

    declared_shell = step.get("shell")
    if declared_shell is not None and str(declared_shell).split()[0] != "bash":
        pytest.fail(
            f"The step declares `shell: {declared_shell}`, which this module cannot run. It "
            "executes the block with bash and `-e`, as GitHub does by default on Linux; a step "
            "that has moved to another shell has to teach this module the new form before its "
            "answer means anything."
        )

    script = step.get("run")
    if not isinstance(script, str) or not script.strip():
        pytest.fail(
            "The classification step runs no script, so it emits nothing. Every gate conditioned "
            "on its output then reads an empty string, which is not `'true'` — so every gate runs, "
            "the filter has silently never fired, and E0-38 has shipped as a comment."
        )

    path = runner_shaped_path(workspace)
    output_file = workspace / "github-output"
    output_file.write_text("", encoding="utf-8")
    home = workspace / "home"
    home.mkdir()
    script_file = workspace / "classification-step.sh"
    script_file.write_text(script, encoding="utf-8")

    environment = {
        "PATH": path,
        "HOME": str(home),
        "TMPDIR": str(workspace),
        "GITHUB_OUTPUT": str(output_file),
        "LC_ALL": "C",
        **GIT_ENVIRONMENT,
        **event,
    }

    try:
        # S603: a resolved absolute path, and a script this test just wrote out of
        # the repository's own workflow file.
        completed = subprocess.run(  # noqa: S603
            [shell, *STEP_SHELL_FLAGS, str(script_file)],
            cwd=repository,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=STEP_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"The classification step ran for more than {STEP_TIMEOUT_SECONDS}s over a planted "
            "repository. E0-38 asks for a cheap step whose whole point is being cheaper than the "
            "gates it switches off."
        )

    emitted: dict[str, str] = {}
    for line in output_file.read_text(encoding="utf-8").splitlines():
        match = EMITTED.match(line.strip())
        if match:
            emitted[match.group("name")] = match.group("value")

    log = (completed.stdout + completed.stderr).strip()
    return completed.returncode, emitted, log


def described(status: int, emitted: dict[str, str], log: str) -> str:
    """One block of diagnosis, for a reader who is looking at this in the dark."""
    return "\n".join(
        [
            f"    step exit status: {status}",
            f"    emitted:          {emitted or 'nothing at all'}",
            f"    ran with:         {PATH_DESCRIPTION}",
            f"    log:              {log[:800] or '(nothing)'}",
        ]
    )


def test_the_changed_job_classifies_the_diff_on_a_runner_that_has_only_python3(
    ci_workflow_path: Path, ci_workflow: dict[str, Any], tmp_path: Path
) -> None:
    """The step reaches the classifier and reports its answer, on the PATH a runner has.

    The `changed` job deliberately declares no `actions/setup-python` — the
    classifier is standard library only and does not need one, and that is the
    property worth keeping, since the job's whole value is being cheaper than what
    it switches off. The cost of that choice is that **`python` does not exist on
    the runner**:

        $ env -i PATH=/usr/bin:/bin sh -c 'command -v python; command -v python3'
        python: NOT FOUND
        /usr/bin/python3

    The step's first version invoked `python`. It exits 127, which is neither of
    the classifier's two answers, so the branch below emitted `inert=false` — and
    would have gone on emitting it on every pull request forever. Every gate would
    have run every time, exactly as before the ticket, with `CI` green and the job
    reporting success. That was found and fixed while building, and reverting
    `python3` to `python` afterwards left all 348 tests and 100 self-test checks
    green. A fix with nothing asserting it is `docs/MISTAKES.md` entry 2, and the
    behaviour it would let back in is this ticket's own subject: a gate that never
    runs, indistinguishable in a green checkmark from one that passed.

    **Three cases, and they need each other.** The documentation-only diffs are
    what the interpreter mutation breaks — under it they emit `false` and this goes
    red. The code diff is what stops the whole thing being satisfied by a step that
    emits `true` unconditionally, which would skip every gate on every pull request
    and is the worse failure of the two. And the two events are separate cases
    because the step reads a different context value for each: a step that took
    `github.event.before` on a pull request would emit `false` on every pull
    request, which is the same silent never-fires shape reached by a different
    route.

    **Executed, not read.** The step is pulled out of the parsed workflow and run
    under `bash -e` — GitHub's default for a block that declares no `shell:` —
    against a real git repository with a real diff, with the classifier reached
    through a symlink to this repository's own `scripts/`. A test that read the
    line and objected to the word `python` would be asserting the spelling; what
    is asserted here is that whatever it invokes exists in the environment the job
    actually has.

    **The mutation this survives:** change `python3` back to `python` in the
    `changed` job. **The near miss that must stay green:** any other way of naming
    an interpreter the job has — an absolute path, `"${{ env.PYTHON }}"` resolved
    to something present, or adding `actions/setup-python` and going back to
    `python`, which would be a slower job and not a broken one.
    """
    output_name, step = classification_step(ci_workflow, ci_workflow_path)

    cases: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
        (
            "a documentation-only pull request, the shape this epic produced six times",
            "pull_request",
            (INERT_CHANGE,),
            "true",
        ),
        (
            "a documentation-only push to an epic branch",
            "push",
            (INERT_CHANGE,),
            "true",
        ),
        (
            "a pull request that touches Python",
            "pull_request",
            (CODE_CHANGE,),
            "false",
        ),
    )

    wrong: list[str] = []
    for index, (case, event_name, touched, expected) in enumerate(cases):
        workspace = tmp_path / f"case-{index}"
        workspace.mkdir()
        repository = workspace / "repo"
        base = planted_repository(repository, touched)
        install_real_classifier(repository)

        event = {
            "EVENT_NAME": event_name,
            "PR_BASE_SHA": base if event_name == "pull_request" else "",
            "PUSH_BEFORE": base if event_name != "pull_request" else "",
        }
        status, emitted, log = run_classification_step(step, repository, workspace, event)

        if emitted.get(output_name) != expected:
            wrong.append(
                f"  {case}\n"
                f"    changed:          {list(touched)}\n"
                f"    expected:         {output_name} = {expected}\n"
                + described(status, emitted, log)
            )

    assert not wrong, "\n".join(
        [
            "The classification step did not answer for these diffs, run on a PATH shaped like "
            "the runner's:",
            *wrong,
            "",
            "These ran with `python` answering 127, which is what a GitHub runner does with it in "
            "a job that declares no `actions/setup-python`:",
            "",
            "    $ env -i PATH=/usr/bin:/bin sh -c 'command -v python; command -v python3'",
            "    python: NOT FOUND",
            "    /usr/bin/python3",
            "",
            "`git` and `python3` resolve normally, and both were proved to before any case ran.",
            "",
            "An exit status of 127 in the log means the step invoked an interpreter the runner "
            "does not have. It is not a crash anybody sees: the branch below it emits a "
            "classification that runs every gate, so the pipeline stays green and the filter "
            "never fires once. That is the defect this test exists for, and it was live in the "
            "first version of this step.",
            "",
            "A non-zero step status with nothing emitted means something else: the step died "
            "before writing its output. `bash -e` is what GitHub runs a `run:` block with, and "
            "under `-e` a bare command that exits non-zero ends the script — so a classifier "
            "answering 1 for 'not inert' would abort the step unless its status is captured in a "
            "tested position. The step would then fail, the `changed` job with it, every gate "
            "that needs it reports `skipped`, and the aggregate `ci` check reads that as failure.",
        ]
    )


def test_every_way_the_diff_can_fail_still_emits_a_classification_that_runs_everything(
    ci_workflow_path: Path, ci_workflow: dict[str, Any], tmp_path: Path
) -> None:
    """Every route out of the step ends in a classification, and none of them ends in a failure.

    The step has four ways not to know what changed — no base commit, a base the
    clone does not hold, a diff that errors, and a classifier that answers neither
    of its two answers — and the only safe reading of all four is the full
    pipeline. Each must therefore emit the classification that runs everything.

    **And each must leave the step succeeding, which is the half worth saying out
    loud.** The tempting alternative is to let the step fail: it is honest, it is
    loud. It is also a red pipeline on a green repository — the `changed` job
    fails, every gate that needs it reports `skipped`, and E0-36 made the aggregate
    check read `skipped` as failure. So an unreachable base commit would block
    every merge rather than costing fifteen minutes of runner time. The workflow
    chose to run everything and say so in a notice; this holds it to both halves.

    **The emptiest case is the one that pays.** A step that emitted nothing at all
    — because it died, because the output name changed — leaves every gate reading
    an empty string, which is not `'true'`, so every gate runs and the pipeline
    looks exactly like a working filter over a busy repository. That is why these
    assert the *value* rather than merely that nothing was `true`.

    **The mutation this survives:** drop the `emit` from any one of the early exits
    in the `changed` job, or turn one of them into a non-zero exit. **The near miss
    that must stay green:** changing the notice text, or reordering the checks, or
    replacing the `case` with an `if` — nothing here reads how the step decides.
    """
    output_name, step = classification_step(ci_workflow, ci_workflow_path)

    # `(case, event, touched, base, classifier source or None for the real one)`.
    cases: tuple[tuple[str, str, tuple[str, ...], str, str | None], ...] = (
        (
            "a pull request whose base sha did not arrive",
            "pull_request",
            (INERT_CHANGE,),
            "",
            None,
        ),
        (
            "a first push to a new branch, whose `before` is all zeroes",
            "push",
            (INERT_CHANGE,),
            "0" * 40,
            None,
        ),
        (
            "a base commit this clone does not hold, as a shallow fetch would leave it",
            "pull_request",
            (INERT_CHANGE,),
            ABSENT_BASE_SHA,
            None,
        ),
        (
            "a classifier that answers neither of its two answers",
            "pull_request",
            (INERT_CHANGE,),
            "",
            CLASSIFIER_THAT_ANSWERS_NEITHER,
        ),
    )

    wrong: list[str] = []
    for index, (case, event_name, touched, base, source) in enumerate(cases):
        workspace = tmp_path / f"case-{index}"
        workspace.mkdir()
        repository = workspace / "repo"
        planted_base = planted_repository(repository, touched)
        if source is None:
            install_real_classifier(repository)
        else:
            install_classifier_source(repository, source)

        # An empty `base` in the table means "this case is about the base being
        # missing"; the stub case wants a real one, so that what it exercises is
        # the exit status and not the base check three branches above it.
        given = base if source is None else planted_base
        event = {
            "EVENT_NAME": event_name,
            "PR_BASE_SHA": given if event_name == "pull_request" else "",
            "PUSH_BEFORE": given if event_name != "pull_request" else "",
        }
        status, emitted, log = run_classification_step(step, repository, workspace, event)

        if status != 0 or emitted.get(output_name) != "false":
            wrong.append(
                f"  {case}\n"
                f"    expected:         exit 0, {output_name} = false\n"
                + described(status, emitted, log)
            )

    assert not wrong, "\n".join(
        [
            "These routes out of the classification step do not end in a classification that "
            "runs every gate:",
            *wrong,
            "",
            "Each of them means 'we do not know what changed', and the only safe reading of that "
            "is the full pipeline. A route that emits nothing is not equivalent: an unset output "
            "reaches every gate as an empty string, which is not `'true'`, so the gates do run — "
            "and the pipeline is then indistinguishable from a working filter over a repository "
            "where every pull request happens to touch code.",
            "",
            "A non-zero exit status is not equivalent either, and it is the more attractive "
            "mistake. A step that fails takes the `changed` job with it; every gate that needs "
            "that job then reports `skipped`; and E0-36 item 1 made the aggregate `ci` check read "
            "`skipped` as failure. So a base commit missing from a shallow clone would block the "
            "merge instead of costing runner time.",
        ]
    )


def test_the_classifier_imports_nothing_the_changed_job_installs(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """The job installs nothing, so the classifier may import only the standard library.

    The `changed` job runs no `actions/setup-python` and no `pip install`, which
    is what makes it cheap enough to sit in front of everything. The bill for that
    is that whatever it runs has to work on the interpreter the runner already
    has, with nothing on `sys.path` but the standard library and the script's own
    directory.

    **An import that fails is not a crash anybody sees.** A Python script that
    raises `ModuleNotFoundError` exits 1, and 1 is one of the classifier's two
    meaningful answers — it is 'not inert, run everything'. So a third-party
    import here does not break the pipeline, it silently converts the filter into
    a step that answers 'run everything' on every pull request, forever, with the
    job reporting success. Identical in the checks interface to the `python`
    defect, arriving by a different door.

    This is asserted statically as well as by execution because the two say
    different things. The executed cases above run the classifier with no
    `PYTHONPATH` and no virtualenv, so a missing dependency shows up there as a
    documentation-only diff emitting `false` — true, and it does not say why. This
    one names the import and the line.

    **The mutation this survives:** add `import yaml` to the classifier. **The
    near miss that must stay green:** importing a module that sits beside it in
    `scripts/ci/`, which the runner resolves through the script's own directory
    and which this allows for that reason.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)
    job = jobs.get(CHANGED_JOB)
    assert job, (
        f"{ci_workflow_path} declares no `{CHANGED_JOB}` job (it declares {sorted(jobs)}). The "
        "rule below is about what that job installs; without the job there is nothing to hold the "
        "classifier to."
    )

    installs = sorted(
        str(step.get("uses"))
        for step in steps_of(job)
        if "setup-python" in str(step.get("uses") or "")
    )
    assert not installs, "\n".join(
        [
            f"The `{CHANGED_JOB}` job now uses {installs}.",
            "",
            "That makes the rule below unnecessary and this test wrong rather than red — but it "
            "also spends the runner-setup time the job exists to avoid, on every pull request, in "
            "front of every other gate. If that is a deliberate trade, say so in the workflow and "
            "delete this test with the reason attached.",
        ]
    )

    assert CLASSIFIER.is_file(), (
        f"{CLASSIFIER.relative_to(REPO_ROOT)} does not exist, so there is nothing here to read. "
        "`classify()` at the top of this module says what to change if it has moved."
    )

    tree = ast.parse(CLASSIFIER.read_text(encoding="utf-8"))
    beside_it = {path.stem for path in CLASSIFIER.parent.glob("*.py")}

    outside: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module] if node.module and not node.level else []
        else:
            continue
        for name in names:
            root = name.split(".")[0]
            if root in sys.stdlib_module_names or root in beside_it:
                continue
            outside.append(f"  line {node.lineno}: {name}")

    assert not outside, "\n".join(
        [
            f"{CLASSIFIER.relative_to(REPO_ROOT)} imports modules the `{CHANGED_JOB}` job does "
            "not install:",
            *outside,
            "",
            "That job runs no `actions/setup-python` and no `pip install`, deliberately — it "
            "sits in front of every other gate and its value is being cheap. An import it cannot "
            "satisfy raises `ModuleNotFoundError`, which exits 1, and 1 is one of this "
            "classifier's two real answers: 'not inert, run everything'.",
            "",
            "So this does not fail the build. It turns the filter into a step that answers 'run "
            "everything' on every pull request, permanently, with the job green — the same shape "
            "as invoking `python` on a runner that has only `python3`, reached through a "
            "different door.",
            "",
            f"Modules sitting beside it in {CLASSIFIER.parent.relative_to(REPO_ROOT)} are allowed: "
            "the runner puts the script's own directory on `sys.path`.",
        ]
    )


def test_the_changed_job_fetches_enough_history_to_find_the_base_commit(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """The clone has to hold the commit the diff is taken against, or the filter never fires again.

    `actions/checkout` clones one commit deep by default. The step diffs against
    the base, checks first whether the clone holds it, and emits the classification
    that runs everything when it does not — the safe direction, and a silent one:
    every gate runs on every pull request, every job reports success, `CI` is
    green, and the only symptom is that the pipeline is as slow as it was before
    this ticket. Nobody opens a green run to find out why it was green.

    So the one line that keeps the filter working at all is `fetch-depth: 0`, and
    nothing else in this suite can see it. The executed cases above plant a
    complete repository, which is exactly the condition under which a shallow-clone
    regression is invisible.

    **Zero rather than a number.** A depth of 50 works until somebody opens a pull
    request against a base 51 commits back, and then the filter stops firing for
    that pull request only — which is the same silence, arriving intermittently.

    **This passes today.** It is a regression guard for a line whose loss has no
    other symptom, not a red.

    **The mutation this survives:** delete the `with: fetch-depth: 0` from the
    `changed` job's checkout. **The near miss that must stay green:** the other
    jobs' checkouts, which do not diff against anything and are left alone.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)
    job = jobs.get(CHANGED_JOB)
    assert job, (
        f"{ci_workflow_path} declares no `{CHANGED_JOB}` job (it declares {sorted(jobs)}). If it "
        "has been renamed, rename it here too rather than leaving this module looking for "
        "something that is gone."
    )

    checkouts = [
        step for step in steps_of(job) if "actions/checkout" in str(step.get("uses") or "")
    ]
    assert checkouts, (
        f"The `{CHANGED_JOB}` job checks nothing out, so there is no working tree to diff and no "
        "`fetch-depth` to hold. Either the job no longer computes the diff here, or this module "
        "is looking at the wrong job — and the assertion below would pass over both."
    )

    shallow = [
        f"  {step.get('uses')} with {dict(step.get('with') or {})}"
        for step in checkouts
        if str((step.get("with") or {}).get("fetch-depth", "")) != "0"
    ]

    assert not shallow, "\n".join(
        [
            f"The `{CHANGED_JOB}` job's checkout does not fetch the full history:",
            *shallow,
            "",
            "`actions/checkout` clones one commit deep by default, so the base commit the step "
            "diffs against is not in the clone. The step notices, says so in a notice, and emits "
            "the classification that runs every gate — which is the safe direction and a "
            "completely silent one. Every job reports success, `CI` is green, and the filter has "
            "stopped firing permanently with nothing anywhere saying so.",
            "",
            "A finite depth is not a smaller version of this. It works until a pull request is "
            "opened against a base further back than the number, and then the filter stops firing "
            "for that pull request alone, which is the same silence arriving intermittently.",
        ]
    )


def test_a_rename_out_of_a_code_directory_is_not_read_as_a_documentation_change(
    ci_workflow_path: Path, ci_workflow: dict[str, Any], tmp_path: Path
) -> None:
    """A path the diff does not report is a path nothing classifies.

    The step asks git for the changed paths and hands them to the classifier, so
    everything downstream can only be as complete as that list. Git detects
    renames by default — `diff.renames` has been on since 2.9 — and a rename is one
    change entry rather than two. If `--name-only` reports only where the file
    landed, then moving `backend/app/services/authz.py` to `docs/` produces a diff
    that reads as documentation, the classification is inert, and **pytest does not
    run on a change that deleted a service module**.

    That is this ticket's own failure mode reached through the diff rather than
    through the allowlist: the classifier is not wrong, it is answering about a
    path list with a hole in it. `--no-renames` closes it by reporting the delete
    and the add as two entries, which is one word and costs nothing — a rename
    inside `docs/` still reports two inert paths and stays inert.

    **Not a hypothetical shape, even if this particular move is unusual.** Any
    rename whose source is outside the inert set and whose destination is inside it
    has this property, and E0-38's own rule is that anything not known to be inert
    runs everything. A path that never reaches the classifier is not known to be
    anything.

    **This test does not assume the answer.** If git reports both sides of a
    rename here, it passes and is a regression guard against somebody turning that
    off. If it reports only the destination, it is red against a real hole.

    **The mutation this survives:** whatever closes it — removing `--no-renames`,
    or setting `diff.renames` back on. **The near miss that must stay green:** a
    rename entirely inside `docs/`, which is asserted below and must stay inert:
    trimming `docs/mistakes/` moves files about and is exactly the shape this
    ticket exists to skip.
    """
    output_name, step = classification_step(ci_workflow, ci_workflow_path)

    renames: tuple[tuple[str, str, str, str], ...] = (
        (
            "a service module renamed into the documentation tree",
            CODE_CHANGE,
            "docs/moved-out-of-the-code-tree.md",
            "false",
        ),
        (
            "a record renamed within the documentation tree, which must stay inert",
            "docs/mistakes/40-a-record-this-test-invented.md",
            "docs/mistakes/41-a-record-this-test-invented.md",
            "true",
        ),
    )

    wrong: list[str] = []
    for index, (case, source, destination, expected) in enumerate(renames):
        workspace = tmp_path / f"rename-{index}"
        workspace.mkdir()
        repository = workspace / "repo"
        repository.mkdir(parents=True)

        git(repository, "init", "--quiet")
        for relative in (SEED_FILE, source):
            path = repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "planted by E0-38's tests, and long enough to be\n" * 8, encoding="utf-8"
            )
        git(repository, "add", SEED_FILE, source)
        git(repository, "commit", "--quiet", "-m", "base")

        (repository / destination).parent.mkdir(parents=True, exist_ok=True)
        git(repository, "mv", source, destination)
        git(repository, "commit", "--quiet", "-m", "the rename under test")
        base = git(repository, "rev-parse", "HEAD~1")

        install_real_classifier(repository)
        event = {"EVENT_NAME": "pull_request", "PR_BASE_SHA": base, "PUSH_BEFORE": ""}
        status, emitted, log = run_classification_step(step, repository, workspace, event)

        if emitted.get(output_name) != expected:
            wrong.append(
                f"  {case}\n"
                f"    renamed:          {source} -> {destination}\n"
                f"    expected:         {output_name} = {expected}\n"
                + described(status, emitted, log)
            )

    assert not wrong, "\n".join(
        [
            "The classification does not see both sides of a rename:",
            *wrong,
            "",
            "Git detects renames by default and reports one entry for them. If that entry is the "
            "destination alone, a file moved out of the code tree into `docs/` produces a diff "
            "that reads as pure documentation — so the classification is inert, and pytest does "
            "not run on a change that deleted a service module. The classifier is not wrong "
            "there; it is answering about a path list with a hole in it.",
            "",
            "`--no-renames` on the `git diff` closes it: the delete and the add arrive as two "
            "paths, the source is outside the inert set, and everything runs. The second case "
            "above is what it must not cost — a rename inside `docs/` reports two inert paths and "
            "stays inert, which is what trimming `docs/mistakes/` looks like.",
        ]
    )
