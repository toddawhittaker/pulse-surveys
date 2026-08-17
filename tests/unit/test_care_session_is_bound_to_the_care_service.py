"""Only the Care service may reach for a `pulse_care` session — ticket E0-10.

E0-10: "Two runtime connection pools. **The pool is bound to the service, not to
the person** — only the Care service module can obtain a `pulse_care` session,
and it independently verifies the actor holds a live `CARE` assignment before
doing anything… A caller can never choose its own pool, and no general-purpose
helper hands out a `pulse_care` session." The ticket names the module:
`backend/app/services/safety.py`, which SPEC §13 already gives the Care queue.

**Why the pool binding is a rule at all.** §2.1 permits one person to hold a Care
assignment and a reporting assignment — a Care staffer who also teaches — so
"pick the pool from the actor's role" has no answer for them. The rule is that
the *code path* decides: their instructor requests run on `pulse_app`, with no
route to identity, however many hats they hold. That is the two-hat criterion,
and this file is the half of it that can be asserted today.

**What is asserted here, and what is not available to assert.** Three things are:
no module outside `services/safety.py` names a Care session; that module does name
one; and — at runtime, against the imported module rather than its text — its
public surface hands out nothing that is or returns one. `reveal_identity`,
`NotCareStaffError` and `RevealedIdentity` are public; the engine, the
sessionmaker and the session are `_care_engine`, `_care_sessions` and
`_care_session`, and the third test below is what keeps them that way.

**The runtime two-hat call is not written, and that is a result rather than a
gap.** "A reporting-path caller cannot obtain a `pulse_care` session even when the
acting person also holds a `CARE` assignment" describes a call that has no
subject: there is no public factory to ask, which is the criterion being satisfied
by construction. A test could only reach one of two ways, and both are worse than
none — call `_care_session` itself, which asserts that a private thing works and
inverts the rule; or ask for a public factory to exist so that something can be
refused by it, which builds the door the criterion forbids. What *is* missing and
nameable is the service-side assignment check as behaviour: calling
`reveal_identity` as a person with no live `CARE` assignment and seeing
`NotCareStaffError`. That needs a `pulse_care` login credential in the test
fixture and the variable names that carry it in `.env.example`, neither of which
E0-10 settles — the migration cannot hold a password. Until it does, the function
half of that check is asserted against the database in
`tests/integration/test_identity_grants.py`, which is the half the ticket says has
to hold when the service is bypassed.

**Why the syntax tree rather than the file text**, exactly as
`test_care_is_not_reachable_from_a_claim.py` reasons: a correct implementation is
very likely to *say* "pulse_care" in a comment in the reporting module that must
not use one — "this runs on `pulse_app`, never `pulse_care`" is the sentence a
careful author writes. Searching the text would turn that sentence into a failure
and teach the next person to delete the comment.

**A definition is not a use, and the difference is the whole test.** The module
that builds the pool has to name it; that is not the defect. The defect is a
second module reaching for it — an import, a call, an attribute — which is what
`obtains_a_care_session` looks for. That also covers "no general-purpose helper
hands out a `pulse_care` session" from the only side a source sweep can see: a
helper that hands them out is harmless while nothing outside the Care service
calls it, and the moment something does, this goes red naming the module.

**What it cannot see** (`docs/MISTAKES.md` entry 14): a session obtained through a
registry keyed by a string, a dependency-injection container, an engine chosen by
a configuration value, or a factory whose name does not contain "care". It is a
tripwire on the obvious way to write the wrong thing, not a proof that the wrong
thing is unwritable. The proof-shaped assertion is next door in
`tests/integration/test_identity_grants.py`: the `SECURITY DEFINER` function
refuses an actor with no live `CARE` assignment, whatever session reached it.
"""

import ast
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"

# The module E0-10 names, and the only one allowed to obtain a Care session.
CARE_SERVICE = APP_ROOT / "services" / "safety.py"
CARE_SERVICE_MODULE = "app.services.safety"

# What a Care session is called, in the two shapes a sweep can recognise: an
# identifier that says both "care" and "session-ish", and the role name itself in
# a string. **This file's choice** of vocabulary — E0-10 spells the role and the
# module and no symbol between them — and the canary below is what makes a wrong
# guess fail loudly rather than quietly.
CARE_ROLE_NAME = "pulse_care"
SESSION_FRAGMENTS = ("session", "engine", "pool", "connection", "connect", "sessionmaker")


def holds_a_session(value: Any) -> bool:
    """Is this object a database connection, or a thing that makes one?

    By type rather than by name, so the runtime test below catches a public
    `engine` whatever it is called. Classes are deliberately not matched — a
    module doing `from sqlalchemy.orm import Session` has imported a type, not
    acquired a session — so this asks about instances.
    """
    from sqlalchemy.engine import Connection, Engine
    from sqlalchemy.orm import Session, sessionmaker

    return isinstance(value, Engine | Connection | Session | sessionmaker)


def parsed_modules() -> dict[Path, ast.Module]:
    """Every module under `backend/app`, parsed.

    A file that does not parse is a failure of the sweep rather than a module to
    skip: it would drop silently out of both halves below, and the half that
    matters is the one that reports what it did *not* find.
    """
    found: dict[Path, ast.Module] = {}
    for path in sorted(APP_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            found[path] = ast.parse(source, filename=str(path))
        except SyntaxError as failure:  # pragma: no cover - a broken source tree
            pytest.fail(
                f"{path.relative_to(REPO_ROOT)} does not parse ({failure}), so this sweep cannot "
                "read it and would report success having skipped it."
            )
    return found


def reads_as_a_care_session(spelling: str) -> bool:
    """Does this identifier name a Care session — both halves, not either?

    Both, because "care" alone reaches `care_case` and `careful`, and "session"
    alone reaches every session in the application. The pair is what names the
    thing this rule is about.
    """
    lowered = spelling.lower()
    return "care" in lowered and any(fragment in lowered for fragment in SESSION_FRAGMENTS)


def defined_here(tree: ast.Module) -> set[str]:
    """Names this module binds itself — a definition is not a use.

    Attribute targets are collected as well as plain names, because
    `self.care_session = sessionmaker(...)` is how a class that owns both pools
    would spell it, and without that every later `self.care_session` in the
    defining module would read as a module reaching for somebody else's session.
    """
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            bound.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bound.add(target.id)
                elif isinstance(target, ast.Attribute):
                    bound.add(target.attr)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                bound.add(node.target.id)
            elif isinstance(node.target, ast.Attribute):
                bound.add(node.target.attr)
    return bound


def obtains_a_care_session(tree: ast.Module) -> set[str]:
    """Every way this module reaches for a Care session it did not define itself.

    An import is counted, and it is the sharpest of the three: `from app.db
    import care_session` in a reporting module is the defect in one line, before
    anything is called with it.
    """
    bound = defined_here(tree)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            for alias in node.names:
                for spelling in (alias.name.rsplit(".", maxsplit=1)[-1], alias.asname or ""):
                    if spelling and reads_as_a_care_session(spelling):
                        found.add(spelling)
        elif isinstance(node, ast.Name):
            if node.id not in bound and reads_as_a_care_session(node.id):
                found.add(node.id)
        elif isinstance(node, ast.Attribute):
            if node.attr not in bound and reads_as_a_care_session(node.attr):
                found.add(node.attr)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.strip().lower() == CARE_ROLE_NAME
        ):
            found.add(node.value)
    return found


def names_a_care_session(tree: ast.Module) -> bool:
    """Does this module name a Care session at all, defined here or not?"""
    if obtains_a_care_session(tree):
        return True
    return any(reads_as_a_care_session(spelling) for spelling in defined_here(tree))


def test_no_module_outside_the_care_service_obtains_a_care_session() -> None:
    """Criterion: requesting a `pulse_care` session from outside `services/safety.py` fails.

    The two-hat case is what this is for, and E0-10 calls it "expected in
    production" rather than hypothetical: a Care staffer who also teaches holds
    both assignments, so nothing about *the person* can decide which pool their
    request runs on. Only the path can. If `api/instructor.py` or
    `services/reporting.py` can reach a `pulse_care` session, then that person's
    instructor screen is one refactor away from a connection that can execute the
    reveal — and every grant in this ticket is intact while it happens, because
    the reveal is a legitimate function called by a legitimate role.

    **The canary is the first assertion.** Until some module names a Care session,
    "no module outside the Care service names one" is true of an application that
    has no second pool at all, which is the state this criterion exists to leave
    behind (`docs/MISTAKES.md` entry 3).
    """
    modules = parsed_modules()
    assert modules, (
        f"There are no Python modules under {APP_ROOT.relative_to(REPO_ROOT)}, so this sweep "
        "looked at nothing and would report success. E0-01 ships the backend package."
    )

    naming = {path: tree for path, tree in modules.items() if names_a_care_session(tree)}
    assert naming, (
        f"No module under {APP_ROOT.relative_to(REPO_ROOT)} names a Care session, across "
        f"{len(modules)} modules. E0-10 asks for two runtime connection pools, the second of them "
        f"on the `{CARE_ROLE_NAME}` role, so until one exists this assertion is about an "
        "application that cannot reach identity at all — which is not the same guarantee. The "
        "sweep looks for an identifier carrying both 'care' and one of "
        f"{list(SESSION_FRAGMENTS)}, or the string {CARE_ROLE_NAME!r}; if the factory is spelled "
        "some other way, that spelling is what this file needs to be told."
    )

    offenders = sorted(
        f"{path.relative_to(REPO_ROOT)}: {sorted(obtains_a_care_session(tree))}"
        for path, tree in modules.items()
        if path != CARE_SERVICE and obtains_a_care_session(tree)
    )
    assert not offenders, (
        f"{offenders} reach for a Care session outside {CARE_SERVICE.relative_to(REPO_ROOT)}. "
        "E0-10: 'only the Care service module can obtain a `pulse_care` session… A caller can "
        "never choose its own pool, and no general-purpose helper hands out a `pulse_care` "
        "session.' The module that *builds* the pool is not this — a name it binds itself is a "
        "definition, and this sweep subtracts those — so what is listed above is a second module "
        "importing, calling or attributing one. If it is a legitimate second home for the Care "
        "queue, the ticket names one module and that is the line to move in the ticket rather "
        "than here."
    )


def test_the_care_service_is_the_module_that_obtains_the_care_session() -> None:
    """The other direction: the door exists, and it is behind the service that checks the actor.

    A wall passes the test above. E0-10 wants a door in a named place: the Care
    service obtains the session *and* "independently verifies the actor holds a
    live `CARE` assignment before doing anything. Two conditions, both required,
    so neither a routing mistake nor a stale assignment is enough on its own."
    This asserts the first condition is wired where the ticket puts it. The second
    is asserted where it can be: the function's own check, against the database,
    in `test_identity_grants.py`. The service's independent copy of that check
    needs `reveal_identity` to be *called*, which needs a `pulse_care` login
    credential the test fixture does not have and a variable name for it that
    `.env.example` does not carry — see this module's docstring.
    """
    assert CARE_SERVICE.is_file(), (
        f"{CARE_SERVICE.relative_to(REPO_ROOT)} does not exist. E0-10 names it — 'The Care service "
        "module is `backend/app/services/safety.py`, which SPEC §13 already names for the Care "
        "queue. Do not add a module for this.' — and it is the one place allowed to obtain a Care "
        "session, so the rule has no subject until the module is there."
    )

    tree = ast.parse(CARE_SERVICE.read_text(encoding="utf-8"), filename=str(CARE_SERVICE))
    assert obtains_a_care_session(tree) or any(
        reads_as_a_care_session(spelling) for spelling in defined_here(tree)
    ), (
        f"{CARE_SERVICE.relative_to(REPO_ROOT)} never names a Care session, so nothing in this "
        "application obtains one from the place the ticket puts it. Either the Care path is not "
        "built yet — E0-10 requires it to be, because 'the Care path must remain open, and this "
        "ticket proves it' — or it is reached under a name this sweep does not recognise, in "
        f"which case `SESSION_FRAGMENTS` in this file needs that spelling and the test above is "
        "currently blind in the same way."
    )


def test_the_care_service_exposes_nothing_that_hands_out_a_care_session(
    configured_env: dict[str, str],
    import_app_module: Any,
) -> None:
    """The pool is private, asserted against the imported module rather than its text.

    E0-10: "A caller can never choose its own pool, and no general-purpose helper
    hands out a `pulse_care` session." The two sweeps above say no *other module*
    reaches for one; this says there is nothing for another module to reach for.
    They are different failures — an import that has not been written yet is not
    the same as a door that is locked — and this is the one that stays true as the
    application grows, because it constrains the surface rather than the current
    set of callers.

    **Public means importable, and that is the whole rule.** A `care_session` with
    no underscore is `from app.services.safety import care_session` away from any
    reporting path, and the two-hat case is why that matters: §2.1 permits a Care
    staffer who also teaches, so nothing about the person can decide which pool
    their request runs on. Only the path can, and a public factory is a path
    anybody can take.

    **The canary is that something private *is* a session.** Without it, a module
    that had not built the second pool at all would pass this cleanly — which is
    the state E0-10 exists to leave behind, and reads identically in a green run
    (`docs/MISTAKES.md` entry 3).

    Objects are matched by *type* as well as by name, so a public engine is caught
    whatever it is called; callables are matched by name, because a factory's
    return type is not visible until it is called and calling one here would open
    a connection this test has no business opening.
    """
    module = import_app_module(CARE_SERVICE_MODULE)
    assert module is not None, (
        f"There is no `{CARE_SERVICE_MODULE}` module. E0-10 names it — SPEC §13 already gives "
        "`services/safety.py` the Care queue — and it is where the second connection pool and the "
        "actor's assignment check both live."
    )

    exposed = {
        name: value
        for name, value in vars(module).items()
        if holds_a_session(value) or (callable(value) and reads_as_a_care_session(name))
    }
    private = sorted(name for name in exposed if name.startswith("_"))
    public = sorted(name for name in exposed if not name.startswith("_"))

    assert private, (
        f"`{CARE_SERVICE_MODULE}` holds nothing private that is a database session, engine or "
        f"sessionmaker: it exposes {sorted(vars(module))}. Then 'the pool is private' is true of a "
        "module with no pool, and this test would go on passing after the Care path was deleted. "
        "E0-10 asks for two runtime connection pools, the second reachable only from here."
    )
    assert not public, (
        f"`{CARE_SERVICE_MODULE}` exposes {public} without a leading underscore, and each is a "
        f"session, an engine, a sessionmaker, or a callable named like one (it keeps {private} "
        "private). E0-10: 'A caller can never choose its own pool, and no general-purpose helper "
        "hands out a `pulse_care` session.' A public one is a single import away from every "
        "reporting path in the application, and the person it would be misused for is the two-hat "
        "case §2.1 permits and §6.2 spends a paragraph on — a Care staffer who also teaches, whose "
        "instructor requests must run on `pulse_app` with no path to identity. `reveal_identity`, "
        "`NotCareStaffError` and `RevealedIdentity` are the surface this module is meant to have."
    )
