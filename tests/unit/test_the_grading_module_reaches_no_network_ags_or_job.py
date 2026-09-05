"""The participation formula is pure computation over the database — ticket E3-03, criterion 8.

E3-03's eighth criterion: "No network call, no AGS type, and no job import appears
in the module." The ticket's context says why the line is drawn there: "SPEC
§3.4's score, computed and nothing else: no AGS, no job, no network, no posting."
The value of the rule is that the arithmetic can be measured without a platform —
no mock LMS, no broker, no HTTP.

**The sweep's subject changed in E3-05, and the old one was wrong.** Until then
this module asserted criterion 8 over the *whole file*, and E3-05 — which puts the
line-item creation service in `backend/app/services/grading.py`, where SPEC §13
already says it goes — made that assertion false. `docs/disputes/E3-05-01.md`
carries the objection and the ruling of 2026-09-04:

> **The test is at fault, in scope rather than in property.** SPEC §13's services
> tree names the module's contents as "participation formula + AGS passback
> (§3.4)", so the spec itself places the passback half in this module and the
> sweep's subject — the whole file, in perpetuity — asserts something the spec
> never promised. … The property criterion 8 protects is kept, not dropped: the
> formula's own functions still reach nothing beyond the database, and the
> repaired sweep must go on proving that.

So the old assertion was incorrect: it read a true statement about E3-03's own
deliverable ("this file holds only the formula, today") as a permanent property of
the file, which contradicts §13. This is `docs/MISTAKES.md` entry 1 arriving on
the test side. The rejected repair is recorded too, because it is the one a reader
will think of: rehoming the passback service to keep the sweep intact would let a
guard dictate architecture against §13, and it does not even work — a closed-set
guard defeated one level out, since importing `grading` would pull the AGS client,
Celery and `requests` in transitively while the sweep reported the module clean.

**What is asserted now.** The sweep starts at the formula's entry point,
`participation_scores`, follows every function defined in the same module that it
uses, and refuses a network, AGS or job reach anywhere in that set — whether the
reach is an import written inside one of those functions or a use of a name the
module imported at the top. Everything the module holds that the formula does not
reach is outside the sweep, which is where E3-05's `request_line_item_creation`,
`ensure_line_item` and `outbound_transport` live, by §13's own description of this
file.

**What that scoping cannot see, said out loud rather than left looking like
coverage** (`docs/MISTAKES.md` entry 14):

  - **A second public formula function that `participation_scores` does not
    reach** is not swept. `FORMULA_ENTRY_POINTS` below is the inventory, it lives
    in this file where the guarded module cannot shrink it (`docs/MISTAKES.md`
    entry 35), and adding an entry point is a one-line visible diff here.
  - **Reachability is syntactic.** A helper reached through a dispatch table, a
    `getattr`, or a callable passed in by a caller is invisible to the walk. What
    closes that is review of what the formula calls, not another path here.
  - **A forbidden reach in module-level code** — executed at import, outside every
    function — is not flagged, because the passback half legitimately has module-
    level names of its own (D3 puts `SANCTION = sanction_for("grade_passback")`
    there) and this file cannot tell one module-level statement's owner from
    another's.

**An absence is asserted, so the detector is run against what it claims to
catch** (`docs/MISTAKES.md` entry 3, and entry 35's rule that a guard which only
ever reports absence cannot say which mechanisms it can see). Four of the five
tests here are that control, and two of them are **mutations of the real module**
rather than synthetic samples: a forbidden import planted inside the real
`participation_scores` has to be caught, and — the pair that proves the new scope
is a scope rather than a blindness — an identical helper planted into the real
module has to be caught when the formula calls it and *not* caught when nothing
does.

The sweep parses rather than searching text, so a library named in a docstring is
not counted as a dependency and `from x import y` counts the same as `import x`.
It is the shape `tests/unit/test_provider_library_is_confined_to_the_gateway.py`
established for the same question one epic earlier.

The second criterion in this file is criterion 6's other half — "with no constant
`5` anywhere in the module". The behavioural proof that the denominator follows
the question set is
`tests/integration/test_the_denominator_comes_from_the_weeks_question_set.py`,
which plants a set of a different size; this is the belt beside it, and it catches
the constant that has not been reached yet because only one set version exists.
**It is deliberately left file-wide** by the E3-05 repair: the dispute above is
about the import sweep's scope and nothing else, and a literal `5` in the passback
half would be as worth a second look as one in the formula. If a later ticket
finds a legitimate one there, narrowing this second test is that ticket's change
to make, with its own reason.
"""

import ast
from collections.abc import Iterable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GRADING_PATH = REPO_ROOT / "backend" / "app" / "services" / "grading.py"

# A module under `backend/app/services/` that certainly exists and certainly
# imports something, so a sweep that reads nothing says so rather than reporting a
# clean module (`docs/MISTAKES.md` entry 3).
SWEEP_CANARY = REPO_ROOT / "backend" / "app" / "services" / "clock.py"

# Where the sweep starts. E3-03's scope names one entry point — "`participation_
# scores(session, section, *, settings)`" — and `tests/fixtures/grading.py` spells
# it as `PARTICIPATION_FUNCTION` for that ticket's behavioural suite.
#
# **Spelled here rather than imported from that fixtures module**, which is a
# second copy and is chosen deliberately: this is a unit test and importing a
# pytest plugin module for one string would drag that plugin's whole import graph
# into a unit run. A rename that misses this file fails here with a message naming
# the function, and the failure says where the other spelling lives.
#
# **It is an inventory, not a name**, and it is here because `docs/MISTAKES.md`
# entry 35's rule is that the guarded structure must not be able to shrink the
# guard: a formula function added later is swept only if it is reachable from one
# of these, and adding one is a visible diff in a test rather than a line in a
# module nobody re-reads.
FORMULA_ENTRY_POINTS = ("participation_scores",)
FORMULA_ENTRY_POINTS_ALSO_SPELLED_IN = "tests/fixtures/grading.py::PARTICIPATION_FUNCTION"

# The three families criterion 8 names, as import roots and as dotted fragments.
#
# **Roots** are matched against the top-level package of every import: a module
# that reaches a network at all imports one of these, whatever it does with it.
# **Fragments** are matched against the whole dotted path, because the AGS client
# and the job modules are this project's own and are named rather than rooted —
# `app.jobs.tasks` shares its root with everything else here.
NETWORK_ROOTS = frozenset(
    {
        "httpx",
        "httpx2",
        "requests",
        "urllib",
        "urllib3",
        "aiohttp",
        "socket",
        "smtplib",
        "http",
        "ssl",
    }
)
JOB_ROOTS = frozenset({"celery", "kombu", "redis"})
JOB_FRAGMENTS = ("app.jobs",)

# AGS is LTI Advantage's Assignment and Grade Services. E3-04 built the client and
# E3-05 the creation path; both are in this module's own file now, which is why the
# sweep is scoped to the formula rather than to the file. The words are matched
# against a module path's segments so the rule holds whatever those tickets called
# their files.
#
# **A segment matches a word, not a substring.** `ags`, `ags_client` and
# `post_ags` are the module this refuses; `flags` is a module that merely ends in
# the same three letters, and a substring test would refuse it. The near miss is
# asserted in `test_the_detector_allows_what_the_formula_legitimately_needs`.
AGS_WORDS = ("ags", "lti", "line_item", "lineitem", "score_post")

FORBIDDEN_CATEGORIES = ("network", "ags", "job")

# The name the planted-control mutations give the helper they add to the real
# module. Nothing in `backend/` may be called this, which is what makes a hit in
# the report attributable to the plant rather than to the module.
PLANTED_HELPER = "_a_helper_this_control_planted"

# The three statements the mutation controls plant, one per family, written the way
# each would really appear. `import requests` is E3-05's own transport type, the
# AGS one is E3-04's client entry point, and the job one is the publish D2 routes
# every enqueue through — so each sample is the exact reach the formula must not
# grow, rather than an invented one.
PLANTED_REACHES = {
    "network": "import requests",
    "ags": "from app.lti.ags import find_or_create_line_item",
    "job": "from app.jobs.celery_app import publish_once",
}

# A statement that reaches nothing, for the negative half of every mutation pair:
# it is planted exactly where the forbidden ones are and must never be reported.
AN_INNOCENT_REACH = "from app.models.flags import Flag"


def segment_names(segment: str, word: str) -> bool:
    """Whether one dotted-path segment names `word`, as a whole word rather than a substring."""
    return segment == word or segment.startswith(f"{word}_") or segment.endswith(f"_{word}")


def categories_of(path: str) -> list[str]:
    """Which of criterion 8's three families one dotted import path belongs to.

    The one place the classification is written, so the path sweep, the binding
    sweep and the synthetic controls cannot drift apart (`docs/MISTAKES.md`
    entry 13).
    """
    lowered = path.lower()
    segments = lowered.split(".")
    root = segments[0]
    found: list[str] = []
    if root in NETWORK_ROOTS:
        found.append("network")
    if any(segment_names(segment, word) for segment in segments for word in AGS_WORDS):
        found.append("ags")
    if root in JOB_ROOTS or any(fragment in lowered for fragment in JOB_FRAGMENTS):
        found.append("job")
    return found


def imported_paths(source: str, *, filename: str) -> list[str]:
    """Every dotted module path one source file imports, parsed rather than searched."""
    return paths_imported_by(ast.walk(ast.parse(source, filename=filename)))


def paths_imported_by(nodes: Iterable[ast.AST]) -> list[str]:
    """Every dotted module path the import statements among `nodes` name."""
    paths: list[str] = []
    for node in nodes:
        if isinstance(node, ast.Import):
            paths.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                paths.append(node.module)
            elif node.level:
                paths.append("." * node.level)
    return paths


def forbidden_imports(source: str, *, filename: str = "<sample>") -> dict[str, list[str]]:
    """The imports in `source` that criterion 8 refuses, by category.

    Returns a mapping rather than a boolean so a failure names the import and the
    reason it is refused, instead of saying that something somewhere is wrong.
    This is the *path classifier* over a whole file, which the two synthetic
    controls below exercise; what the criterion is asserted with is
    `forbidden_reaches`, which applies the same classification inside the formula's
    own reachable functions.
    """
    found: dict[str, list[str]] = {category: [] for category in FORBIDDEN_CATEGORIES}
    for path in imported_paths(source, filename=filename):
        for category in categories_of(path):
            found[category].append(path)
    return {category: names for category, names in found.items() if names}


# ---------------------------------------------------------------------------
# The formula, and what it reaches.
# ---------------------------------------------------------------------------


def module_level_import_bindings(tree: ast.Module) -> dict[str, str]:
    """Every name the module binds by importing it at module level, and the path it came from.

    Module level rather than everywhere, deliberately: a function-local import
    belongs to the function that wrote it, and folding one into a module-wide map
    would let a name bound inside the passback half be attributed to a use of the
    same name inside the formula. Function-local imports are read where they sit,
    by `reaches_of` below.

    `if TYPE_CHECKING:` and `try: … except ImportError:` are descended into,
    because both are module level in every sense that matters here and a guard that
    stopped at the first `if` would miss the annotation-only import criterion 8's
    own docstring names as a mutation to kill.
    """
    bindings: dict[str, str] = {}

    def bind(statement: ast.stmt) -> None:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                bindings[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(statement, ast.ImportFrom):
            prefix = "." * statement.level + (statement.module or "")
            for alias in statement.names:
                bindings[alias.asname or alias.name] = f"{prefix}.{alias.name}".lstrip(".")

    def visit(body: list[ast.stmt]) -> None:
        for statement in body:
            if isinstance(statement, ast.Import | ast.ImportFrom):
                bind(statement)
            elif isinstance(statement, ast.If | ast.Try | ast.With):
                visit(list(statement.body))
                visit(list(getattr(statement, "orelse", [])))
                visit(list(getattr(statement, "finalbody", [])))
                for handler in getattr(statement, "handlers", []):
                    visit(list(handler.body))

    visit(list(tree.body))
    return bindings


def module_level_definitions(tree: ast.Module) -> dict[str, ast.stmt]:
    """Every function and class the module defines at its top level, by name."""
    holders = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    return {node.name: node for node in tree.body if isinstance(node, holders)}


def names_used_in(node: ast.AST) -> set[str]:
    """Every bare name read or written anywhere under `node`.

    Bare names, because that is what a call to a module-local helper and a use of
    an imported binding both look like: `total(...)` and `requests.get(...)` are an
    `ast.Name` each, the second under an `ast.Attribute`. A method call on an
    object — `session.execute(...)` — contributes the name `session`, which is a
    parameter and binds to no import, so it costs nothing.
    """
    return {inner.id for inner in ast.walk(node) if isinstance(inner, ast.Name)}


def formula_functions(tree: ast.Module) -> dict[str, ast.stmt]:
    """The formula's entry points and every module-local definition they reach.

    Breadth-first from `FORMULA_ENTRY_POINTS`, following a name only where the
    module defines it itself: an imported name is not followed, because its body is
    not in this file and the sweep is about what this module's own functions do.

    An entry point the module does not define contributes nothing here rather than
    failing — the test bodies check for that and fail naming it, so an unbuilt or
    renamed formula reads as this module's own red with a sentence attached rather
    than as an error inside a helper (`docs/MISTAKES.md` entry 44).
    """
    defined = module_level_definitions(tree)
    reached: dict[str, ast.stmt] = {}
    queue = [name for name in FORMULA_ENTRY_POINTS if name in defined]
    while queue:
        name = queue.pop()
        if name in reached:
            continue
        node = defined[name]
        reached[name] = node
        queue.extend(
            used for used in names_used_in(node) if used in defined and used not in reached
        )
    return reached


def reaches_of(node: ast.stmt, bindings: dict[str, str]) -> list[str]:
    """Every forbidden import path one function reaches, by either route.

    Two routes, and a sweep with one of them is a sweep with a hole. A function may
    write the import itself — `import requests` inside a body is the shape a
    "temporary" reach takes — and it may use a name the module imported at the top,
    which is the ordinary shape and the one E3-05 makes possible, since the
    passback half now imports exactly these families into this file.
    """
    found: list[str] = []
    for path in paths_imported_by(ast.walk(node)):
        if categories_of(path):
            found.append(path)
    for used in names_used_in(node):
        path = bindings.get(used)
        if path is not None and categories_of(path):
            found.append(path)
    return sorted(set(found))


def forbidden_reaches(source: str, *, filename: str = "<sample>") -> dict[str, list[str]]:
    """Every function in the formula's reachable set that reaches a forbidden family.

    Keyed by function name rather than by category, so a failure says *where* the
    reach is — which is the question a reader of this red has, now that the file
    legitimately holds a half that reaches all three.
    """
    tree = ast.parse(source, filename=filename)
    bindings = module_level_import_bindings(tree)
    reported: dict[str, list[str]] = {}
    for name, node in formula_functions(tree).items():
        found = reaches_of(node, bindings)
        if found:
            reported[name] = found
    return reported


def grading_source() -> str:
    """The module's text, or a failure saying which deliverable is absent.

    A failure rather than an error, and inside the test rather than in a fixture,
    so that an unbuilt E3-03 reads as this module's own red with a sentence
    attached.
    """
    if not GRADING_PATH.is_file():
        pytest.fail(
            f"{GRADING_PATH} does not exist. E3-03's scope: 'The whole ticket is one module, "
            "`backend/app/services/grading.py` (the home SPEC §13 already names for it)', holding "
            "`participation_scores(session, section, *, settings)`; SPEC §13 puts E3-05's AGS "
            "passback in the same file, and this sweep is scoped to the first of the two."
        )
    return GRADING_PATH.read_text(encoding="utf-8")


def the_formulas_tree() -> tuple[str, ast.Module]:
    """The real module's source and its tree, with the entry point required to be there.

    The requirement is here rather than inside `formula_functions` so that it is a
    failed assertion in a test body naming the deliverable, never an exception out
    of a helper (`docs/MISTAKES.md` entry 44). It is also the non-emptiness guard
    every assertion below rests on: a sweep whose reachable set is empty reports a
    clean formula over nothing at all (`docs/MISTAKES.md` entry 3).
    """
    source = grading_source()
    tree = ast.parse(source, filename=str(GRADING_PATH))
    defined = module_level_definitions(tree)
    missing = [name for name in FORMULA_ENTRY_POINTS if name not in defined]
    if missing:
        pytest.fail(
            f"`{GRADING_PATH.relative_to(REPO_ROOT)}` defines no {missing} at module level; it "
            f"defines {sorted(defined)}. E3-03's scope names "
            "`participation_scores(session, section, *, settings)` as the formula, and this sweep "
            "starts there — with no entry point the reachable set is empty and everything below "
            "would be a clean report over nothing.\n\n"
            f"The same name is spelled in {FORMULA_ENTRY_POINTS_ALSO_SPELLED_IN}; a rename moves "
            "both, and `FORMULA_ENTRY_POINTS` at the head of this file is the line that changes "
            "here."
        )
    return source, tree


def with_a_planted_statement(source: str, statement: str, *, inside: str) -> str:
    """The real module with one statement planted at the top of one of its functions.

    A mutation of the subject rather than a synthetic sample, which is what
    `docs/MISTAKES.md` entry 35 asks for: a control built out of a module of this
    file's own invention proves the detector can read *that*, and says nothing
    about whether it can read the module it is pointed at.

    The statement is parsed and inserted as an AST node and the whole tree is
    unparsed again, so nothing here depends on the module's text, its indentation
    or where its functions happen to start.
    """
    tree = ast.parse(source, filename=str(GRADING_PATH))
    holders = (ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if isinstance(node, holders) and node.name == inside:
            node.body.insert(0, ast.parse(statement).body[0])
            return ast.unparse(ast.fix_missing_locations(tree))
    pytest.fail(
        f"`{GRADING_PATH.relative_to(REPO_ROOT)}` defines no function `{inside}`, so this control "
        "could not plant anything and proves nothing about the detector."
    )


def with_a_planted_helper(source: str, statement: str, *, called: bool) -> str:
    """The real module with a new helper carrying `statement`, called by the formula or not.

    The instrument the scoping property is proven with, in both directions. The
    helper is identical in the two cases and the only difference is whether
    `participation_scores` calls it — so a detector that reported the same answer
    for both would be sweeping the file rather than the formula, which is exactly
    the assertion `docs/disputes/E3-05-01.md` ruled incorrect.
    """
    tree = ast.parse(source, filename=str(GRADING_PATH))
    helper = ast.parse(f"def {PLANTED_HELPER}():\n    {statement}\n    return 0\n").body[0]
    tree.body.append(helper)
    if called:
        holders = (ast.FunctionDef, ast.AsyncFunctionDef)
        planted = False
        for node in ast.walk(tree):
            if isinstance(node, holders) and node.name == FORMULA_ENTRY_POINTS[0]:
                node.body.insert(0, ast.parse(f"{PLANTED_HELPER}()").body[0])
                planted = True
                break
        if not planted:
            pytest.fail(
                f"`{GRADING_PATH.relative_to(REPO_ROOT)}` defines no `{FORMULA_ENTRY_POINTS[0]}`, "
                "so the called half of this control could not be built."
            )
    return ast.unparse(ast.fix_missing_locations(tree))


# ---------------------------------------------------------------------------
# Controls. **A red in this section means these tests are broken, not the code.**
# ---------------------------------------------------------------------------


def test_the_detector_catches_each_family_criterion_eight_names() -> None:
    """The must-catch half of the classifier's control: a sample carrying each import is reported.

    Without this the assertion below is satisfied by a detector that can see
    nothing — which is exactly how a guard passes over a module full of the thing
    it was written to refuse (`docs/MISTAKES.md` entry 35).

    Each sample is written the way the import would really appear: an HTTP client
    for the network, this project's own job module for the schedule, and two
    spellings an AGS client can take.

    This is the *path* classifier, which the scoped sweep uses on every path it
    meets. That the sweep applies it in the right place, and only there, is the
    subject of the two mutation controls below.
    """
    assert "network" in forbidden_imports("import httpx\n"), "A plain `import httpx` was not seen."
    assert "network" in forbidden_imports(
        "from urllib.request import urlopen\n"
    ), "A `from urllib.request import …` was not seen; the root is what makes it a network reach."
    assert "job" in forbidden_imports(
        "from app.jobs.tasks import ping\n"
    ), "An import from this project's own job module was not seen."
    assert "job" in forbidden_imports("import celery\n"), "A direct `import celery` was not seen."
    assert "ags" in forbidden_imports(
        "from app.services.ags import post_score\n"
    ), "An import of a service module named for AGS was not seen."
    assert "ags" in forbidden_imports("from app.lti.line_item import LineItem\n"), (
        "An import of a line-item type was not seen; the formula may not name the line item, which "
        "is E3-04's and E3-05's."
    )
    assert "ags" in forbidden_imports("from app.services.ags_client import AgsClient\n"), (
        "A module whose name begins with the word — as likely a spelling as the bare one — was not "
        "seen."
    )


def test_the_detector_allows_what_the_formula_legitimately_needs() -> None:
    """The must-allow half: the imports a pure computation over the database really has.

    A detector that refused these would make criterion 8 unsatisfiable and E3-03
    impossible — which is `docs/MISTAKES.md` entry 24's shape, a test asserting a
    property no implementation can meet. The sample is what E3-03's work order says
    the module reads: the clock, the window derivation, the submission path's
    question rule, the validity module's refused set, and the ORM.
    """
    sample = "\n".join(
        [
            "from dataclasses import dataclass",
            "from decimal import ROUND_HALF_UP, Decimal",
            "from uuid import UUID",
            "from sqlalchemy import select",
            "from sqlalchemy.orm import Session",
            "from app.config import Settings",
            "from app.models.survey import Response",
            "from app.services import clock",
            "from app.services.submissions import current_questions",
            "from app.services.survey_windows import windows_for_section",
            "from app.services.validity import REFUSED_VERDICTS",
            "",
        ]
    )
    assert forbidden_imports(sample) == {}, (
        f"The detector refuses {forbidden_imports(sample)} in a module doing exactly what E3-03's "
        "work order describes. Every one of those is something the formula has to read."
    )
    assert forbidden_imports(f"{AN_INNOCENT_REACH}\n") == {}, (
        "A module whose name merely ends in the same three letters as AGS is refused. The word "
        "test exists so that a real module named `flags`, `multi` or `messages` is not read as an "
        "AGS or LTI import."
    )


def test_the_scoped_sweep_catches_a_forbidden_reach_planted_in_the_formula_itself() -> None:
    """The mutation control, on the real module, one family at a time and both routes.

    Four plants, each into the real `participation_scores` and each unparsed back
    from the tree so nothing depends on the module's text. Three are a forbidden
    import written inside the function, one per family, spelled as the reach would
    really appear — E3-05's own transport type, E3-04's client entry point and D2's
    publish. The fourth is the *other* route and the one E3-05 makes possible: a
    module-level `import requests` used by name inside the formula, which is what a
    reach looks like once the passback half has already imported the family into
    this file.

    Without this control the criterion below is a clean report from a sweep that
    might be reading nothing — and after the E3-05 repair the reachable set is a
    subset of the file, so "it read nothing" is a real possibility rather than a
    remote one (`docs/MISTAKES.md` entry 35).

    The innocent plant is in the same test, in the same place, so a detector that
    fired on everything it was handed is caught here rather than by a red in a
    module somebody then deletes the sweep to fix.
    """
    source, _tree = the_formulas_tree()
    entry = FORMULA_ENTRY_POINTS[0]

    for family, statement in sorted(PLANTED_REACHES.items()):
        mutated = with_a_planted_statement(source, statement, inside=entry)
        found = forbidden_reaches(mutated, filename=str(GRADING_PATH))
        assert entry in found, (
            f"`{statement}` planted inside `{entry}` was not reported ({found}). This sweep is the "
            "only thing asserting that the participation formula reaches no network, no AGS type "
            f"and no job, and against the {family!r} family it currently sees nothing at all — so "
            "its clean report over the real module means nothing."
        )

    used_by_name = with_a_planted_statement(source, "requests.get('http://x')", inside=entry)
    used_by_name = "import requests\n" + used_by_name
    found = forbidden_reaches(used_by_name, filename=str(GRADING_PATH))
    assert entry in found, (
        f"A module-level `import requests` used as `requests.get(...)` inside `{entry}` was not "
        f"reported ({found}). That is the shape a reach takes now that this file legitimately "
        "imports all three families for its passback half: the import is at the top and looks like "
        "the passback's, and only the *use* says the formula reached it."
    )

    innocent = with_a_planted_statement(source, AN_INNOCENT_REACH, inside=entry)
    assert forbidden_reaches(innocent, filename=str(GRADING_PATH)) == {}, (
        f"`{AN_INNOCENT_REACH}` planted inside `{entry}` was reported as a forbidden reach. A "
        "sweep that is red against a correct module is one somebody deletes."
    )


def test_the_scoped_sweep_follows_the_formula_into_a_helper_and_stops_outside_it() -> None:
    """The scope, in both directions, on one helper that differs only in whether it is called.

    This is the assertion the E3-05 repair turns on, and
    `docs/disputes/E3-05-01.md` is why it exists. The old sweep read the whole
    file, which SPEC §13 says holds "participation formula + AGS passback", so it
    refused the passback half the imports that half is made of. The new one reads
    the formula's own reachable set. Both halves have to be shown or the change is
    not a narrowing, it is a hole:

      - **Called**, the helper's forbidden import is reported, and reported against
        the helper. Without this the narrowed sweep would be satisfied by a formula
        that moved its network reach one function down — which is the cheapest way
        to defeat a scoped guard and the first thing to try.
      - **Not called**, the identical helper is reported by nothing. Without this
        the sweep is still file-wide and the dispute's finding is unfixed: E3-05's
        `request_line_item_creation`, `ensure_line_item` and `outbound_transport`
        would go on being refused the imports §13 puts in this file.

    The helper is planted into the real module rather than into a sample, so what
    the two halves differ by is one call statement in the real
    `participation_scores` and nothing else.
    """
    source, _tree = the_formulas_tree()
    statement = PLANTED_REACHES["network"]

    called = forbidden_reaches(
        with_a_planted_helper(source, statement, called=True), filename=str(GRADING_PATH)
    )
    assert PLANTED_HELPER in called, (
        f"A helper carrying `{statement}` and called by `{FORMULA_ENTRY_POINTS[0]}` was not "
        f"reported ({called}). The walk does not follow the formula into what it calls, so the "
        "whole criterion is satisfied by moving a network reach one function down — and nothing "
        "else in this project would notice."
    )

    uncalled = forbidden_reaches(
        with_a_planted_helper(source, statement, called=False), filename=str(GRADING_PATH)
    )
    assert PLANTED_HELPER not in uncalled, (
        f"The same helper, called by nothing, was still reported ({uncalled}). Then this sweep is "
        "file-wide rather than scoped to the formula, and `docs/disputes/E3-05-01.md`'s finding "
        "stands: SPEC §13 puts the AGS passback in this very file, so a file-wide sweep refuses "
        "the module the imports the spec says it holds."
    )


# ---------------------------------------------------------------------------
# The criteria.
# ---------------------------------------------------------------------------


def test_the_participation_formula_reaches_no_network_ags_or_job_name() -> None:
    """Criterion 8, over the formula and everything it reaches.

    E3-03's eighth criterion, read as `docs/disputes/E3-05-01.md`'s ruling reads
    it: "the formula's own functions still reach nothing beyond the database, and
    the repaired sweep must go on proving that."

    **The mutations this kills:** an AGS type imported "just for the annotation" on
    a value the formula returns, which makes the arithmetic untestable without a
    platform; a Celery task reached so the formula can enqueue its own re-post,
    which is E3-06's job and would make every call to the arithmetic a side effect;
    and an HTTP client, which turns a pure function into something that can time
    out inside a gradebook sync. Since E3-05 the likeliest of the three is none of
    those: it is the formula quietly *using* one of the passback half's own
    module-level imports, which is now one name away and which the binding sweep is
    what catches.

    **Three things are read before the report is believed**, and each is a way this
    could be a clean answer over nothing. The canary: a parse that sees no import
    at all in a module that certainly has several is broken. The entry point:
    resolved by `the_formulas_tree`, which fails naming it. And the reachable set,
    required to be non-empty — a formula whose helpers this walk cannot see reports
    nothing whatever the module holds.
    """
    canary = SWEEP_CANARY.read_text(encoding="utf-8") if SWEEP_CANARY.is_file() else ""
    assert imported_paths(canary, filename=str(SWEEP_CANARY)), (
        f"This sweep read no imports at all from {SWEEP_CANARY}, which E2-04 shipped and which "
        "certainly imports several. That is a defect in the sweep rather than a clean tree, and "
        "everything it says below is a statement it is not in a position to make."
    )

    source, tree = the_formulas_tree()
    reachable = formula_functions(tree)
    assert reachable, (
        f"The walk from {list(FORMULA_ENTRY_POINTS)} reaches no function in "
        f"`{GRADING_PATH.relative_to(REPO_ROOT)}`, so the report below is about an empty set. "
        "`the_formulas_tree` has already required the entry point to be defined, so this is the "
        "walk itself having gone wrong rather than the module lacking a formula."
    )

    found = forbidden_reaches(source, filename=str(GRADING_PATH))

    assert found == {}, (
        f"In `{GRADING_PATH.relative_to(REPO_ROOT)}`, the participation formula reaches {found}. "
        "E3-03's eighth criterion: no network call, no AGS type and no job import appears in the "
        "formula. Posting is E3-04's and E3-05's and the schedule is E3-06's — all of which SPEC "
        "§13 puts in this same file — and the whole value of the line is that the arithmetic can "
        "be measured without a platform, a broker or a mock LMS.\n\n"
        f"The functions swept are {sorted(reachable)}: "
        f"{list(FORMULA_ENTRY_POINTS)} and everything they reach. Anything this file holds that "
        "the formula does not reach is outside this sweep by decision — see "
        "`docs/disputes/E3-05-01.md` and the module docstring."
    )


def test_the_grading_module_holds_no_literal_question_count() -> None:
    """Criterion 6's other half: no constant `5` anywhere in the module.

    SPEC §3.4: the week's total "is never a constant: the set is versioned
    precisely so a week's item count can change, and a formula holding a literal
    count would be wrong the first time it does."

    **The mutation this kills** is the one the system cannot currently notice: a
    denominator written as `5`, or a `QUESTIONS_PER_WEEK = 5` beside it, is correct
    against every question set that exists today and wrong the day E2's versioned
    table gets its second row. The behavioural pair in
    `test_the_denominator_comes_from_the_weeks_question_set.py` is the primary
    proof; this catches the constant that is present but not yet reachable — a
    fallback for a missing set, say, or a default argument.

    **Still file-wide after the E3-05 repair, and that is a decision.**
    `docs/disputes/E3-05-01.md` is about the import sweep's scope and says nothing
    about this one, and a literal `5` in the passback half of the file would be as
    worth a second look as one in the formula. If a later ticket finds a legitimate
    one there — a page size, a retry count — narrowing this to the formula's own
    reachable set is that ticket's change, with its own reason; `formula_functions`
    above is the machinery it would use.

    Integer literals only. A `5` inside a docstring or a comment is prose and is
    not read here.
    """
    tree = ast.parse(grading_source(), filename=str(GRADING_PATH))
    literals = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, int) and node.value == 5
    ]
    assert literals == [], (
        f"`{GRADING_PATH.relative_to(REPO_ROOT)}` holds the integer literal 5 on line(s) "
        f"{[node.lineno for node in literals]}. SPEC §3.2's set has five questions today and the "
        "table is versioned so that it need not tomorrow; the denominator comes from the set."
    )
