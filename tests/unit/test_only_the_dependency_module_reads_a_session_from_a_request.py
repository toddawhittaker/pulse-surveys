"""E2-14 item 5 — one API module reads a session out of a request, and it is `app.api.deps`.

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

Today the direct call exists in `app/api/deps.py` and nowhere else, which is the
state this sweep pins. It is not a rule against reading a session — it is a rule
that the reading happens in the one module the inventory is derived from, so that
a route which is student-visible is a route the inventory can see. A module that
needs the session reads it through `require_student` (or through whatever
dependency `deps.py` exposes), and the inventory keeps working.

**What is matched, and what deliberately is not.** The match is on the syntax
tree, by exact identifier: an `import` of `session_from_request` from
`app.services.session` under any alias, an attribute access spelled
`<anything>.session_from_request`, a bare reference to the name, and a definition
of a function by that name. A text search would be the wrong instrument twice
over — `app/api/auth.py` defines an unrelated `verified_session`, which any
matcher reading for a fragment of the word "session" would flag, and a module
that *mentions* `session_from_request` in a docstring while calling nothing would
be flagged by a grep and is not flagged here. Both cases are planted in the
control below and both must stay green.

**Its disclosed limit** (`docs/MISTAKES.md` entry 14, on an enumeration reported
as an impossibility): a module that reaches the function through a string —
`getattr(session_module, "session_from_" + "request")` — is not matched, and
nothing short of running the code would match it. What is closed here is the
ordinary way a handler would come to read a session, in the four spellings a
Python author would write; it is not a proof that no module can.

**Every claim the reader makes is proven in both directions before the tree is
judged with it.** The planted offenders must be flagged and the planted near
misses must not, under `tmp_path` rather than against real files — a control
built out of the tree it is controlling stops demonstrating anything the day the
tree changes. And the reader is required to *find* the call `app/api/deps.py`
really makes (`docs/MISTAKES.md` entry 35: require the guard to find the thing on
a subject that certainly has it), because a reader that can see nothing reports a
clean sweep over everything.

**A red in either control means these tests are broken, not that the code is.**
Both say so in their own docstrings. They are inside the isolated §4.1 pass along
with the sweep, deliberately: an instrument that has gone blind inside that pass
would otherwise report silence as compliance, which is the state this whole
module exists to stop being mistaken for a guarantee.

**This module's stem carries none of the denial sweep's name shapes**, and it
does not need to: it holds its `invariant` marker at module level, which is the
form
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`
demands, so the shape would add nothing but a claim about what it denies.
"""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.invariant

REPO_ROOT = Path(__file__).resolve().parents[2]

# SPEC §13's tree: the API layer, and the module E2-09's work order settles the
# shared student-session dependency in ("It reads the session through
# `app.services.session`").
API_ROOT = REPO_ROOT / "backend" / "app" / "api"
EXEMPT = Path("deps.py")

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


def api_modules() -> list[Path]:
    """Every Python module under `backend/app/api/`, at any depth."""
    return sorted(API_ROOT.rglob("*.py"))


def named(path: Path) -> str:
    """A path as this repository writes it in a message."""
    return str(path.relative_to(REPO_ROOT))


# ---------------------------------------------------------------------------
# The planted tree for the control. Four modules the reader must flag and three
# it must not, written under `tmp_path` rather than pointed at real files.
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

    **The mutation it kills:** the reader narrowed until it matches nothing —
    a module name compared against a spelling `deps.py` does not use, a walk that
    never reaches an `ImportFrom`. Under it the sweep below reports every API
    module clean and says nothing at all.
    """
    exempt = API_ROOT / EXEMPT
    assert exempt.is_file(), (
        f"{named(exempt)} does not exist. E2-09's work order settles the shared student-session "
        "dependency there — 'It reads the session through `app.services.session`' — and it is the "
        "one module the sweep below exempts. If it has moved, `EXEMPT` at the top of this file is "
        "the one line that changes."
    )

    reasons = reads_the_session(exempt.read_text(encoding="utf-8"), named(exempt))
    assert reasons, (
        f"The reader found no reference to `{SESSION_READER}` in {named(exempt)}, which imports it "
        "and calls it. It can therefore see none of the four spellings it enumerates, and the "
        "sweep below would report every module in the API layer clean having read nothing "
        "(`docs/MISTAKES.md` entry 35).\n\n"
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


def test_no_api_module_but_the_dependency_module_reads_a_session_from_a_request() -> None:
    """The rule: `app.api.deps` reads the session, and no other API module does.

    SPEC §4.1 item 1 is asserted over an inventory of student-visible routes, and
    that inventory is a filter on the `require_student` dependency. A handler that
    reads the session itself is student-visible and invisible to the filter, and
    `every_route` does not descend the `Mount` `app/main.py` puts the single-page
    application behind — so a route added under either blind spot ships with the
    §4.1 sweep passing over it in silence.

    **The mutation this kills:** a new or edited module under `backend/app/api/`
    that imports or calls `session_from_request` — in any of the four spellings
    the control above proves the reader sees. That is not a hypothetical shape: it
    is the shortest way to write a handler that needs the current student, and it
    is invisible to every §4.1 assertion this epic has.

    **The near misses that must stay green:** `app/api/deps.py` itself, which is
    where the reading belongs and which the control above requires the reader to
    find; `app/api/auth.py`'s unrelated `verified_session`; and any module that
    names the reader in a docstring or a comment while calling nothing.

    **Two controls, because a sweep for absence is satisfied by emptiness.** The
    API directory has to exist and hold more than the exempt module, or "no other
    module reads it" is a statement about nothing.
    """
    assert API_ROOT.is_dir(), (
        f"{named(API_ROOT)} is not a directory, so this sweep walked nothing and every assertion "
        "below is true of an empty tree. SPEC §13 puts the API layer there."
    )

    modules = api_modules()
    swept = [path for path in modules if path.relative_to(API_ROOT) != EXEMPT]
    assert swept, (
        f"{named(API_ROOT)} holds {[named(path) for path in modules]}, which is nothing beyond the "
        f"exempt `{EXEMPT}`. This sweep then judges no module at all, and its silence means "
        "nothing."
    )

    offenders = {
        named(path): reasons
        for path in swept
        if (reasons := reads_the_session(path.read_text(encoding="utf-8"), named(path)))
    }
    assert not offenders, "\n".join(
        [
            f"These modules under {named(API_ROOT)} read a session out of a request themselves, "
            f"which only `{EXEMPT}` may do:",
            *(f"  {path}: {'; '.join(reasons)}" for path, reasons in sorted(offenders.items())),
            "",
            "The inventory SPEC §4.1 item 1 is swept over keeps the routes whose dependency graph "
            "contains `app.api.deps.require_student` "
            "(`tests/integration/test_the_student_read_path_names_nothing_outside_the_enrollment.py"
            "::student_visible_routes`). A handler that reads the session directly has no "
            "`require_student` in its graph, so it is not in the inventory, and every §4.1 "
            "assertion made over that inventory passes over it without a word. The route walk "
            "does not descend a `Mount` either, and `app/main.py` mounts the single-page "
            "application.",
            "",
            f"The repair is to take the session from `{EXEMPT}` — `require_student`, or whatever "
            "dependency that module exposes for this surface — so that the route joins the "
            "inventory the sweep is derived from. Widening this rule is not one of the answers: "
            "the inventory is the only thing standing between a student-visible route and no §4.1 "
            "assertion at all.",
        ]
    )
