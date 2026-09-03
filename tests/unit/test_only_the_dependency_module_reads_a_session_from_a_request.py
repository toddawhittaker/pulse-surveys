"""E2-14 item 5 — one module reads a session out of a request, and it is `app.api.deps`.

**Why this sweep exists, and it is about a blind spot in another test rather than
about a defect.** SPEC §4.1 item 1's student-visible surface is swept over an
*inventory* of routes, built in
`tests/integration/test_the_student_read_path_names_nothing_outside_the_enrollment.py`
by `student_visible_routes`: it keeps the routes whose dependency graph contains
`app.api.deps.require_student`. That inventory has two blind spots, and the E2
boundary review confirmed and sharpened both:

  - **A handler that reads the session itself is invisible to it.** A route that
    calls `app.services.session.session_from_request` directly, rather than
    depending on `require_student`, is a student-visible route with no
    `require_student` in its dependency graph — so it is not in the inventory, and
    every §4.1 assertion made over that inventory passes over it in silence.
  - **The walk does not descend a `Mount`.** `tests/fixtures/routing.py::every_route`
    follows FastAPI's `_IncludedRouter` and says so in its own docstring — "a
    plain `starlette.routing.Route`, a `Mount` and a `WebSocketRoute` all pass
    through unchanged" — and `backend/app/main.py` mounts the single-page
    application. Routes under a mount are not reached by the inventory at all.

Today the reading happens in `app/api/deps.py` and nowhere else, which is the
state this sweep pins. It is not a rule against reading a session — it is a rule
that the reading happens in the one module the inventory is derived from, so that
a route which is student-visible is a route the inventory can see.

**The walk is the whole `backend/app/` package, and the first version of this
sweep walked only `backend/app/api/`.** This pull request's security review
defeated that one level out, concretely rather than in principle: a
`backend/app/services/student_session.py` defining `current_student(request)`
that calls `session_from_request`, used from a route as
`Depends(current_student)`, is flagged by an api-only walk nowhere at all — and
that route is missing from the `require_student` inventory for exactly the same
reason a direct caller was. `docs/MISTAKES.md` carries the class: a closed-set
guard is defeated one level further out each round, and the answer is to attack
the whole class rather than the level that was demonstrated. So the walk is the
application package, recursively, and the exemptions are two named modules rather
than a directory.

**The two exemptions, and why each is one.** `app/api/deps.py` is the sanctioned
caller — E2-09's work order settles the shared student-session dependency there,
"It reads the session through `app.services.session`" — and it is the module the
route inventory is derived from. `app/services/session.py` is where the reader is
*defined*; a rule that flagged its own definition could be satisfied by no
implementation (`docs/MISTAKES.md` entry 24). Nothing else is exempt, and a third
exemption is a decision somebody has to write down rather than a line to add here.

**What is matched, and what deliberately is not.** The match is on the syntax
tree, by exact identifier: an `import` of `session_from_request` from
`app.services.session` under any alias, an attribute access spelled
`<anything>.session_from_request`, a bare reference to the name, and a definition
of a function by that name. A text search would be the wrong instrument twice
over — `app/api/auth.py` defines an unrelated `verified_session`, which any
matcher reading for a fragment of the word "session" would flag, and a module
that *mentions* `session_from_request` in a docstring while calling nothing would
be flagged by a grep and is not flagged here. Both cases are planted in the
controls below and both must stay green.

**Its disclosed limits** (`docs/MISTAKES.md` entry 14, on an enumeration reported
as an impossibility), now that the walk is the package rather than one directory.
Two things remain outside it, and neither is closed by widening again:

  - **String indirection.** A module that reaches the function through a computed
    name — `getattr(session_module, "session_from_" + "request")` — is not
    matched, and nothing short of running the code would match it.
  - **Anything outside `backend/app/` entirely.** The walk is the application
    package. A reader factored into a module the application imports from
    somewhere else is not swept, and the honest answer to that is the same one
    this docstring gives above: it is found by review of what a new route depends
    on, not by widening a path here.

What is closed is the ordinary way a handler would come to read a session — the
four spellings a Python author would write, anywhere in the application package,
in a handler or in a helper one directory out.

**Every claim the reader and the walk make is proven in both directions before
the tree is judged with them.** The planted offenders must be flagged and the
planted near misses must not; a planted *tree* mirroring the real layout must
flag a services-side wrapper and spare both exempt modules. All of it under
`tmp_path` rather than against real files — a control built out of the tree it is
controlling moves when the tree moves, and the day somebody deletes the last real
example it reports success for having found nothing to find. And the reader is
required to *find* the call `app/api/deps.py` really makes (`docs/MISTAKES.md`
entry 35: require the guard to find the thing on a subject that certainly has
it), because a reader that can see nothing reports a clean sweep over everything.

**A red in any of the three controls means these tests are broken, not that the
code is.** Each says so in its own docstring. They are inside the isolated §4.1
pass along with the sweep, deliberately: an instrument that has gone blind inside
that pass would otherwise report silence as compliance, which is the state this
whole module exists to stop being mistaken for a guarantee.

**This module's file name kept its singular after the widening**, and it is still
true: one module *reads* a session out of a request, and the second exemption is
the module that *defines* the reading rather than a second reader.

**Its stem carries none of the denial sweep's name shapes**, and it does not need
to: it holds its `invariant` marker at module level, which is the form
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`
demands, so the shape would add nothing but a claim about what it denies.
"""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.invariant

REPO_ROOT = Path(__file__).resolve().parents[2]

# SPEC §13's tree: the application package, walked whole. Not `app/api/` — see the
# module docstring for the evasion that widened it, and for why the exemptions are
# two named modules rather than a directory.
APP_ROOT = REPO_ROOT / "backend" / "app"

# The sanctioned caller: E2-09's work order settles the shared student-session
# dependency there, and it is the module `student_visible_routes` filters on.
SANCTIONED_CALLER = Path("api/deps.py")

# Where the reader is defined. Exempt because a rule that flagged the definition
# of the thing it is about is a property no implementation could satisfy
# (`docs/MISTAKES.md` entry 24).
DEFINITION_MODULE = Path("services/session.py")

EXEMPT = frozenset({SANCTIONED_CALLER, DEFINITION_MODULE})

# The reader every session in this product arrives through, and the module ADR
# 0089 puts it in: "`session_from_request` reads the Bearer header before the
# cookie, so the Bearer path carries the session with no cookie required".
SESSION_MODULE = "app.services.session"
SESSION_MODULE_TAIL = "services.session"
SESSION_READER = "session_from_request"

# The near miss that has to stay green, named here because it is a real symbol in
# a real file rather than a hypothesis: `app/api/auth.py` defines an unrelated
# `verified_session`. Any matcher reading for a fragment of "session" flags it.
A_NEAR_MISS_NAME = "verified_session"

# ---------------------------------------------------------------------------
# The reader.
# ---------------------------------------------------------------------------


def reads_the_session(source: str, where: str) -> list[str]:
    """Every way `source` refers to `session_from_request`, as sentences naming each.

    Reasons rather than a boolean, so a failure says *how* a module reaches the
    reader — an import, an alias, a dotted call — instead of only that it does.

    A module that does not parse fails here rather than being passed over: it
    would drop silently out of the swept set, and silence is what this module
    exists to stop being mistaken for compliance.
    """
    try:
        tree = ast.parse(source, filename=where)
    except SyntaxError as failure:  # pragma: no cover - a broken source tree
        pytest.fail(
            f"{where} does not parse ({failure}), so this sweep cannot read it and would report it "
            "clean having read nothing."
        )

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == SESSION_MODULE or module.endswith(f".{SESSION_MODULE_TAIL}"):
                for alias in node.names:
                    if alias.name == SESSION_READER:
                        bound = alias.asname or alias.name
                        found.add(f"imports `{SESSION_READER}` from `{module}` as `{bound}`")
                    elif alias.name == "*":
                        found.add(
                            f"imports everything from `{module}` with `*`, which binds "
                            f"`{SESSION_READER}` without naming it"
                        )
        elif isinstance(node, ast.Attribute) and node.attr == SESSION_READER:
            found.add(f"reaches `.{SESSION_READER}` as an attribute")
        elif isinstance(node, ast.Name) and node.id == SESSION_READER:
            found.add(f"refers to the name `{SESSION_READER}`")
        elif (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == SESSION_READER
        ):
            found.add(f"defines a function called `{SESSION_READER}`")
    return sorted(found)


def modules_under(root: Path) -> list[Path]:
    """Every Python module under `root`, at any depth."""
    return sorted(root.rglob("*.py"))


def offenders_under(root: Path, exempt: frozenset[Path]) -> dict[str, list[str]]:
    """Every module under `root` that reads the session, keyed by its path within `root`.

    The root is a parameter so that the walk itself — which directories it
    descends, and which modules it lets through — is proven against a planted tree
    rather than only against the real one. That is the half the first version of
    this module had no control for, and it is the half its security review
    defeated: the reader was right and the root was too small.
    """
    return {
        str(path.relative_to(root)): reasons
        for path in modules_under(root)
        if path.relative_to(root) not in exempt
        and (reasons := reads_the_session(path.read_text(encoding="utf-8"), str(path)))
    }


def named(path: Path) -> str:
    """A path as this repository writes it in a message."""
    return str(path.relative_to(REPO_ROOT))


# ---------------------------------------------------------------------------
# The planted modules for the reader's control. Four it must flag and three it
# must not, written under `tmp_path` rather than pointed at real files.
# ---------------------------------------------------------------------------

PLANTED_OFFENDERS = {
    # The plain spelling: import the name, call it.
    "planted_plain_import.py": (
        f"from {SESSION_MODULE} import {SESSION_READER}\n\n\n"
        f"def read(request):\n    return {SESSION_READER}(request)\n"
    ),
    # The same thing under another name. A matcher that looked for a call to a
    # bare `session_from_request` and nothing else reports this module clean.
    "planted_aliased_import.py": (
        f"from {SESSION_MODULE} import {SESSION_READER} as read_the_session\n\n\n"
        "def read(request):\n    return read_the_session(request)\n"
    ),
    # The dotted spelling: import the package, reach the attribute. No `from`
    # import to see, so the import rule alone does not cover it.
    "planted_dotted_attribute.py": (
        f"import {SESSION_MODULE}\n\n\n"
        f"def read(request):\n    return {SESSION_MODULE}.{SESSION_READER}(request)\n"
    ),
    # The module imported by its own name and then reached through. This is the
    # spelling that carries neither the function's name in an import nor a fully
    # dotted call, and it is why the attribute rule is written on the attribute
    # rather than on the dotted prefix.
    "planted_module_import.py": (
        "from app.services import session\n\n\n"
        f"def read(request):\n    return session.{SESSION_READER}(request)\n"
    ),
}

PLANTED_NEAR_MISSES = {
    # The real near miss, by name: `app/api/auth.py` defines a `verified_session`
    # of its own. A matcher reading for a fragment of "session" flags it, and it
    # is nothing to do with reading a session out of a request.
    "planted_verified_session.py": (
        f"from {SESSION_MODULE} import {A_NEAR_MISS_NAME}\n\n\n"
        f"def check(token, secret):\n    return {A_NEAR_MISS_NAME}(token, secret)\n"
    ),
    # The reader's name in prose and in a comment, and no call anywhere. This is
    # the case that distinguishes a syntax-tree reader from a text search, and it
    # is the shape a module explaining *why* it does not read the session takes.
    "planted_mentions_it_in_prose.py": (
        f'"""This route depends on `require_student` and never calls {SESSION_READER}."""\n\n'
        f"# See {SESSION_READER} in app/api/deps.py for where the session is read.\n\n\n"
        "def read(claims):\n    return claims\n"
    ),
    # An ordinary route module: the dependency, and nothing else.
    "planted_ordinary_route.py": (
        "from app.api.deps import require_student\n\n\n"
        "def read(claims=require_student):\n    return claims\n"
    ),
}

# ---------------------------------------------------------------------------
# The planted *tree* for the walk's control: the real layout in miniature, with
# the evasion this pull request's security review proved sitting one directory
# out of where the first version of this sweep looked.
# ---------------------------------------------------------------------------

# The evasion, verbatim from the finding: a services-side wrapper that reads the
# session, used from a route as `Depends(current_student)`. An api-only walk
# flags it nowhere, and the route that depends on it is missing from the
# `require_student` inventory for the same reason a direct caller was.
THE_EVASION = "services/student_session.py"

PLANTED_TREE = {
    # Exempt: the definition module. It certainly refers to the reader — it *is*
    # the reader — so a walk that flagged it would be red against an
    # implementation nobody could write.
    "services/session.py": (
        f"def {SESSION_READER}(request):\n    return request.headers.get('authorization')\n"
    ),
    # Exempt: the sanctioned caller, which really does import and call it.
    "api/deps.py": (
        f"from {SESSION_MODULE} import {SESSION_READER}\n\n\n"
        f"def require_student(request):\n    return {SESSION_READER}(request)\n"
    ),
    # The evasion. One directory out of where the first version of this sweep
    # looked, and the whole reason the walk moved.
    THE_EVASION: (
        f"from {SESSION_MODULE} import {SESSION_READER}\n\n\n"
        f"def current_student(request):\n    return {SESSION_READER}(request)\n"
    ),
    # Not an offender: an ordinary route module, which is what a route using that
    # wrapper looks like from the outside. It is here so that "the walk flags the
    # wrapper" is not satisfied by a walk that flags everything near it.
    "api/routes.py": (
        "from app.services.student_session import current_student\n\n\n"
        "def read(claims=current_student):\n    return claims\n"
    ),
    # Not an offender: the `verified_session` near miss, planted inside the tree
    # as well as flat, because the widened walk is where it now has to survive.
    "api/auth.py": (
        f"from {SESSION_MODULE} import {A_NEAR_MISS_NAME}\n\n\n"
        f"def check(token, secret):\n    return {A_NEAR_MISS_NAME}(token, secret)\n"
    ),
    # Not an offender, and nowhere near either of them. It is what makes "the walk
    # descends the whole package" a statement with a cost rather than a free one.
    "jobs/tasks.py": "def ping():\n    return 'pong'\n",
}


def test_the_session_reader_finds_the_call_the_dependency_module_really_makes() -> None:
    """The control on the sweep below: the reader can see a real one (entry 35).

    `docs/MISTAKES.md` entry 35: "When a guard enumerates mechanisms, require it
    to *find* each one on a subject that certainly has it, as a control. A guard
    that only ever reports absence cannot tell you which mechanisms it can see."
    This one enumerates four spellings, and every assertion it makes about the
    tree is an absence. So it is required to find the one call this repository
    certainly makes: `app/api/deps.py` imports `session_from_request` and calls
    it, which is exactly what the sweep below exempts it for.

    **A red here means these tests are broken, not that the code is** — or that
    `deps.py` has stopped reading the session, which would make the sweep below a
    statement about a rule nothing needs any more. Either way it is this module's
    business and not a defect in a route.

    **The mutation it kills:** the reader narrowed until it matches nothing — a
    module name compared against a spelling `deps.py` does not use, a walk that
    never reaches an `ImportFrom`. Under it the sweep below reports every module
    in the application clean and says nothing at all.
    """
    exempt = APP_ROOT / SANCTIONED_CALLER
    assert exempt.is_file(), (
        f"{named(exempt)} does not exist. E2-09's work order settles the shared student-session "
        "dependency there — 'It reads the session through `app.services.session`' — and it is one "
        "of the two modules the sweep below exempts. If it has moved, `SANCTIONED_CALLER` at the "
        "top of this file is the one line that changes."
    )

    reasons = reads_the_session(exempt.read_text(encoding="utf-8"), named(exempt))
    assert reasons, (
        f"The reader found no reference to `{SESSION_READER}` in {named(exempt)}, which imports it "
        "and calls it. It can therefore see none of the four spellings it enumerates, and the "
        "sweep below would report every module in the application package clean having read "
        "nothing (`docs/MISTAKES.md` entry 35).\n\n"
        "The other honest reading is that `deps.py` no longer reads the session at all — in which "
        "case the exemption below is an exemption for nothing, and this module's rule needs "
        "restating rather than its reader fixing."
    )


def test_the_session_reader_flags_planted_callers_and_spares_its_near_misses(
    tmp_path: Path,
) -> None:
    """The instrument, in both directions, before the tree is judged with it.

    Four spellings a handler could use to read a session itself, and three things
    that are not one. Planted under `tmp_path` rather than pointed at real files,
    for the reason the denial-module sweep gives about its own controls: a control
    built out of the tree it is controlling moves when the tree moves, and the day
    somebody deletes the last real example it reports success for having found
    nothing to find.

    **The near misses are the point of the instrument's design.** `verified_session`
    is a real function in `app/api/auth.py` and has nothing to do with reading a
    session out of a request; a matcher reading for a fragment of the word
    "session" flags it, and this rule would then be red against a module nobody
    claimed was an offender. A prose mention of `session_from_request` is what a
    module explaining its own dependency choice looks like, and a text grep flags
    that too. Neither is a name reference, so neither is matched.

    **The mutations this kills:** the reader widened to a substring or a regular
    expression over the source text, which flags both near misses; and the reader
    narrowed to the plain `from ... import` spelling, which spares three of the
    four offenders — the alias, the dotted attribute and the module import are
    each a way to make the same call while the plain spelling is absent.

    **A red here means these tests are broken, not that the code is.** Nothing in
    this test reads a real file.
    """
    for name, source in {**PLANTED_OFFENDERS, **PLANTED_NEAR_MISSES}.items():
        (tmp_path / name).write_text(source, encoding="utf-8")

    planted = sorted(tmp_path.glob("*.py"))
    assert len(planted) == len(PLANTED_OFFENDERS) + len(PLANTED_NEAR_MISSES), (
        f"{len(planted)} of {len(PLANTED_OFFENDERS) + len(PLANTED_NEAR_MISSES)} planted modules "
        f"were written to {tmp_path}, so this control is not the tree it describes."
    )

    flagged = {
        path.name
        for path in planted
        if reads_the_session(path.read_text(encoding="utf-8"), str(path))
    }
    assert flagged == set(PLANTED_OFFENDERS), (
        f"The reader flagged {sorted(flagged)}; the planted offenders are "
        f"{sorted(PLANTED_OFFENDERS)} and the planted near misses are "
        f"{sorted(PLANTED_NEAR_MISSES)}.\n\n"
        f"Missing an offender means a handler can read a session in that spelling and stay out of "
        "the route inventory SPEC §4.1 item 1 is swept over — which is the blind spot this module "
        "exists for. Flagging a near miss means the sweep below is red against a module that only "
        f"defines `{A_NEAR_MISS_NAME}` or mentions the reader in prose, which is how a correct "
        "rule gets deleted instead of fixed."
    )


def test_the_walk_reaches_a_services_side_wrapper_and_spares_the_two_exempt_modules(
    tmp_path: Path,
) -> None:
    """The control on the *walk*: the real layout in miniature, with the proven evasion in it.

    The test above proves what the reader can see in one file. This one proves
    which files the walk hands it, which is the half the first version of this
    module had no control for and the half its security review defeated:
    `backend/app/services/student_session.py` defining `current_student(request)`
    that calls `session_from_request`, used from a route as
    `Depends(current_student)`. The reader would have flagged it on sight; the
    walk never gave it to the reader, because the walk was `backend/app/api/`.

    So the planted tree carries six modules: the two exempt ones — both of which
    genuinely refer to the reader, so sparing them means something — the evasion
    one directory out, a route module that uses the wrapper, the
    `verified_session` near miss, and a module with nothing to do with any of it.
    Exactly one has to come back.

    **The mutations this kills:** the walk narrowed to one directory again, under
    which the evasion is not in the result; the exemption written as a directory
    rather than as two modules, under which `api/auth.py` and `api/routes.py` are
    exempt too and a real offender in `api/` walks free; and the exemption
    dropped, under which the definition module is reported as an offender and this
    rule becomes a property no implementation could satisfy (`docs/MISTAKES.md`
    entry 24).

    **The exemptions are matched on the path within the root**, so the planted
    `api/deps.py` and the real one are the same rule under test rather than two.

    **A red here means these tests are broken, not that the code is.** Nothing in
    this test reads a real file.
    """
    for name, source in PLANTED_TREE.items():
        planted = tmp_path / name
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text(source, encoding="utf-8")

    written = {str(path.relative_to(tmp_path)) for path in modules_under(tmp_path)}
    assert written == set(PLANTED_TREE), (
        f"The walk found {sorted(written)} where {sorted(PLANTED_TREE)} was planted, so this "
        "control is not the tree it describes — and a walk that reaches fewer files than were "
        "written is the defect it is here to detect."
    )

    found = offenders_under(tmp_path, EXEMPT)
    assert set(found) == {THE_EVASION}, (
        f"The walk returned {sorted(found)} over the planted tree; the one offender in it is "
        f"`{THE_EVASION}`.\n\n"
        f"If `{THE_EVASION}` is missing, the walk does not reach outside `api/` and the evasion "
        "this pull request's security review proved is open again: a session read factored one "
        "directory out, used from a route through `Depends`, flagged nowhere and absent from the "
        "`require_student` route inventory as well.\n\n"
        f"If `{SANCTIONED_CALLER}` or `{DEFINITION_MODULE}` is in the list, the exemptions are not "
        "being honoured, and the real sweep below is red against the module that defines the "
        "reader or the one sanctioned to call it. If `api/auth.py`, `api/routes.py` or "
        "`jobs/tasks.py` is in it, the reader is flagging something that is not a session read, "
        "and the rule would be deleted rather than fixed."
    )


def test_no_module_but_the_two_exempt_ones_reads_a_session_from_a_request() -> None:
    """The rule: `app.api.deps` reads the session, `app.services.session` defines it, nothing else.

    SPEC §4.1 item 1 is asserted over an inventory of student-visible routes, and
    that inventory is a filter on the `require_student` dependency. A handler that
    reads the session itself is student-visible and invisible to the filter, and
    `every_route` does not descend the `Mount` `app/main.py` puts the single-page
    application behind — so a route added under either blind spot ships with the
    §4.1 sweep passing over it in silence.

    **The mutation this kills:** any module under `backend/app/` other than the
    two exempt ones importing or calling `session_from_request` — in any of the
    four spellings the reader control proves it sees, at any depth the walk
    control proves it reaches. That is not a hypothetical shape twice over: a
    direct call is the shortest way to write a handler that needs the current
    student, and a services-side wrapper around it is what this pull request's
    security review wrote to walk past the first version of this sweep.

    **The near misses that must stay green:** the two exempt modules;
    `app/api/auth.py`'s unrelated `verified_session`; and any module that names
    the reader in a docstring or a comment while calling nothing.

    **Two controls, because a sweep for absence is satisfied by emptiness.** The
    application package has to exist and hold more than the two exempt modules, or
    "no other module reads it" is a statement about nothing.
    """
    assert APP_ROOT.is_dir(), (
        f"{named(APP_ROOT)} is not a directory, so this sweep walked nothing and every assertion "
        "below is true of an empty tree. SPEC §13 puts the application package there."
    )

    modules = modules_under(APP_ROOT)
    swept = [path for path in modules if path.relative_to(APP_ROOT) not in EXEMPT]
    assert len(swept) > 1, (
        f"{named(APP_ROOT)} holds {[named(path) for path in modules]}, which is next to nothing "
        f"beyond the exempt {sorted(str(path) for path in EXEMPT)}. This sweep then judges almost "
        "no module at all, and its silence means nothing."
    )

    offenders = offenders_under(APP_ROOT, EXEMPT)
    assert not offenders, "\n".join(
        [
            f"These modules under {named(APP_ROOT)} read a session out of a request themselves, "
            f"which only {sorted(str(path) for path in EXEMPT)} may do:",
            *(f"  {path}: {'; '.join(reasons)}" for path, reasons in sorted(offenders.items())),
            "",
            "The inventory SPEC §4.1 item 1 is swept over keeps the routes whose dependency graph "
            "contains `app.api.deps.require_student` "
            "(`tests/integration/test_the_student_read_path_names_nothing_outside_the_enrollment.py"
            "::student_visible_routes`). A handler that reads the session directly — or that "
            "depends on a helper which does — has no `require_student` in its graph, so it is not "
            "in the inventory, and every §4.1 assertion made over that inventory passes over it "
            "without a word. The route walk does not descend a `Mount` either, and `app/main.py` "
            "mounts the single-page application.",
            "",
            f"The repair is to take the session from `{SANCTIONED_CALLER}` — `require_student`, or "
            "whatever dependency that module exposes for this surface — so that the route joins "
            "the inventory the sweep is derived from. Widening this rule is not one of the "
            "answers: the inventory is the only thing standing between a student-visible route "
            "and no §4.1 assertion at all, and this sweep has already been widened once, after a "
            "review defeated it one directory out.",
        ]
    )
