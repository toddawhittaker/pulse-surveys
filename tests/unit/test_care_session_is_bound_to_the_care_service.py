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

**What is asserted here, and what is not available to assert.** No module outside
`services/safety.py` reaches for a Care session or for the credential that opens
one; that module does reach for one; the sweep deciding both is itself run over
sources it must flag and sources it must allow; every `Settings` field whose name
mentions Care is a spelling the sweep can recognise; and — at runtime, against the
imported module rather than its text — the service's public surface hands out
nothing that is, returns, or is named as one. `reveal_identity`,
`NotCareStaffError` and `RevealedIdentity` are public; the engine, the
sessionmaker and the session are `_care_engine`, `_care_sessions` and
`_care_session`, and the runtime test below is what keeps them that way.

**A credential is a session nobody has opened yet.** E0-10's whole grant model
rests on *which role a connection authenticates as*, so a module that never
touches the Care sessionmaker, reads the Care URL out of `Settings` and calls
`create_engine` on it holds the same connection under another name, and no grant
in the ticket can tell the two apart. That shape passed this file's sweeps
unflagged as E0-10 first shipped them: `care_database_url` says "care" and says
nothing `SESSION_FRAGMENTS` recognised, so `obtains_a_care_session` returned the
empty set over exactly that source. `CREDENTIAL_FRAGMENTS` below is the second
half of the vocabulary, and the canary test derived from `Settings` is what keeps
that vocabulary in step with the field it is about rather than with this file's
memory of the field.

**A local binding no longer blinds the sweep to an attribute read**, which is the
half no widened tuple reaches. The bindings a module makes used to be collected
into one set and subtracted from every load, so a single line —
`care_database_url = settings.care_database_url`, which is the idiom
`services/safety.py` itself uses — masked the attribute read for the whole module
and the sweep reported nothing with the widened tuple in place. They are now kept
apart by kind: a plain name subtracts from plain-name loads, and what subtracts
from an attribute load is an attribute *definition* — `self.care_session =
sessionmaker(...)`, or a field declared in a class body — which is what the
attribute half of the accommodation was always for. `bound_as_an_attribute` states
what that still admits.

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
a configuration value, or a factory whose name does not contain "care". Nor a
credential assembled from parts — a host, a user and a password read out of three
settings and joined into a URL — because no single identifier in that module names
the thing being built. It is a tripwire on the obvious way to write the wrong
thing, not a proof that the wrong thing is unwritable. The proof-shaped assertion
is next door in `tests/integration/test_identity_grants.py`: the
`SECURITY DEFINER` function refuses an actor with no live `CARE` assignment,
whatever session reached it.
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

# What a Care session is called, in the shapes a sweep can recognise: an
# identifier that says both "care" and "session-ish", an identifier that says both
# "care" and "credential-ish" (see `CREDENTIAL_FRAGMENTS`), and the role name
# itself in a string. **This file's choice** of vocabulary — E0-10 spells the role
# and the module and no symbol between them — and the canary tests at the foot of
# the file are what make a wrong guess fail loudly rather than quietly.
CARE_ROLE_NAME = "pulse_care"
SESSION_FRAGMENTS = ("session", "engine", "pool", "connection", "connect", "sessionmaker")

# The other half of the vocabulary: what a Care *credential* is called. A module
# holding `care_database_url` holds everything needed to open a `pulse_care`
# connection, and E0-10's grants cannot tell that connection from the service's
# own — so the credential and the session are one rule, and this is the tuple that
# was missing when the rule was first written.
#
# **The set is narrower than the obvious one, and "uri" is what it leaves out.**
# "uri" is a substring of "security", and this is the neighbourhood of a
# `SECURITY DEFINER` function, so a `care_security_...` identifier would trip the
# sweep for no reason — `docs/MISTAKES.md` entry 8 is a fragment prescribed
# without being run against the names the project already has, twice, and this is
# the cheap version of running it. What that costs is a field renamed to
# `care_database_uri`, and the cost is bounded by
# `test_every_care_setting_is_a_spelling_this_sweep_recognises` below: a rename
# goes red naming the field rather than going quiet, which is the whole reason a
# blind spot in a *derived* canary is survivable and one in a sweep is not.
CREDENTIAL_FRAGMENTS = ("url", "dsn", "credential", "password", "secret")


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
    """Does this identifier name a Care session, or the credential for one?

    Both halves, not either: "care" alone reaches `care_case` and `careful`, and
    "session" alone reaches every session in the application. The pair is what
    names the thing this rule is about.

    The second half is a session word **or** a credential word, because a module
    holding the Care URL can open the Care connection itself and no grant this
    ticket writes distinguishes the two — see `CREDENTIAL_FRAGMENTS`.
    """
    lowered = spelling.lower()
    return "care" in lowered and any(
        fragment in lowered for fragment in (*SESSION_FRAGMENTS, *CREDENTIAL_FRAGMENTS)
    )


def bound_as_a_name(tree: ast.Module) -> set[str]:
    """Plain names this module binds: `x = ...`, `x: T = ...`, `def x`, `class x`."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            bound.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bound.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            bound.add(node.target.id)
    return bound


def bound_as_an_attribute(tree: ast.Module) -> set[str]:
    """Attributes this module defines, of the two kinds a module can define one.

    An **assignment through a target**, `self.care_session = sessionmaker(...)`,
    which is how a class that owns both pools would spell it. Without this, every
    later `self.care_session` in the defining module would read as that module
    reaching for somebody else's session.

    And an **annotated declaration in a class body**, `care_database_url:
    SecretStr | None = None`, which is what a field on `Settings` is. A class that
    declares an attribute reads it back as an attribute — `self.care_database_url`
    — and that read is the class using its own declaration, not a module reaching
    for a credential somebody else holds. Only the annotated form counts: a plain
    `x = ...` in a class body is indistinguishable from stashing a value read from
    elsewhere, and this set is subtracted from the sweep, so the narrower rule is
    the safe one.

    **What that admits**, stated rather than left to be discovered: a module that
    declares its own Care credential field in a class body may read it back
    unreported. Today that module is `app/config.py` and declaring the field is
    its job. A second module declaring one is a problem this sweep will not name.
    """
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute):
                    bound.add(target.attr)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Attribute):
            bound.add(node.target.attr)
        elif isinstance(node, ast.ClassDef):
            for statement in node.body:
                if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                    bound.add(statement.target.id)
    return bound


def defined_here(tree: ast.Module) -> set[str]:
    """Every name this module binds itself, of either kind — a definition is not a use.

    The union is what "does this module *name* a Care session at all" asks about.
    What subtracts from a *use* is one half or the other and never the union, and
    that distinction is the finding this function used to hide: a module writing
    `care_database_url = settings.care_database_url` binds a plain name, and
    subtracting it from attribute loads as well masked the attribute read — the
    one line in the file that reaches the credential — for the whole module.
    """
    return bound_as_a_name(tree) | bound_as_an_attribute(tree)


def obtains_a_care_session(tree: ast.Module) -> set[str]:
    """Every way this module reaches for a Care session, or its credential, that it did not define.

    An import is counted, and it is the sharpest of the three: `from app.db
    import care_session` in a reporting module is the defect in one line, before
    anything is called with it.

    **Each kind of load is measured against its own kind of binding**, which is
    what makes the attribute read visible. `settings.care_database_url` is an
    attribute load, so what can be a local definition of it is an attribute
    definition — see `bound_as_an_attribute` for the two shapes those take.
    Subtracting plain names from it as well let any module hide the read behind
    one ordinary assignment of the same name, and that assignment is the natural
    way to write the code rather than a contrivance, so the sweep was blind by
    default rather than on request.
    """
    names = bound_as_a_name(tree)
    attributes = bound_as_an_attribute(tree)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            for alias in node.names:
                for spelling in (alias.name.rsplit(".", maxsplit=1)[-1], alias.asname or ""):
                    if spelling and reads_as_a_care_session(spelling):
                        found.add(spelling)
        elif isinstance(node, ast.Name):
            if node.id not in names and reads_as_a_care_session(node.id):
                found.add(node.id)
        elif isinstance(node, ast.Attribute):
            if node.attr not in attributes and reads_as_a_care_session(node.attr):
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
    whatever it is called. Everything else is matched by name, and by the same
    name rule the source sweeps use: a factory's return type is not visible until
    it is called, and calling one here would open a connection this test has no
    business opening — while a public `care_database_url`, which is a string and
    is not callable at all, hands out the connection just as completely as a
    factory would. That last shape is why the name rule and not `callable` decides
    this: the module's docstring has the argument in full.
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
        if holds_a_session(value) or reads_as_a_care_session(name)
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
        f"session, an engine, a sessionmaker, or a name that reads as one of those or as the "
        f"credential that opens one (it keeps {private} private). E0-10: 'A caller can never "
        "choose its own pool, and no general-purpose helper "
        "hands out a `pulse_care` session.' A public one is a single import away from every "
        "reporting path in the application, and the person it would be misused for is the two-hat "
        "case §2.1 permits and §6.2 spends a paragraph on — a Care staffer who also teaches, whose "
        "instructor requests must run on `pulse_app` with no path to identity. `reveal_identity`, "
        "`NotCareStaffError` and `RevealedIdentity` are the surface this module is meant to have."
    )


# ---------------------------------------------------------------------------
# The sweep, run against sources whose answer is known.
#
# Everything above is the sweep applied to the tree as it stands today, and every
# one of those assertions is satisfied by a sweep that has gone blind: no module
# reaches for a Care session is exactly what an `obtains_a_care_session` that
# returns the empty set reports, for every module, forever. That is not
# hypothetical here — it is the review finding this section answers, measured by
# running the sweep over a module that reads `Settings.care_database_url` and
# watching it report nothing.
#
# So the sweep gets the treatment `docs/MISTAKES.md` entry 3 prescribes for a
# pattern searched against a file: run it against the text you claim it catches
# **and** against the text you claim it allows. The samples below are sources, not
# modules — they are never imported, only parsed — so each one states a rule in
# the smallest program that can hold it, and the failure names the rule.
# ---------------------------------------------------------------------------

# Sources that must be reported. Each is a way a second module gets a `pulse_care`
# connection; the two that read the credential off `Settings` are the ones this
# file could not see.
REACHES_FOR_CARE = {
    "the credential read straight off Settings": """
from app.config import Settings
from sqlalchemy import create_engine

engine = create_engine(Settings().care_database_url.get_secret_value())
""",
    "the credential by way of a local of the same name": """
from app.config import Settings
from sqlalchemy import create_engine

settings = Settings()
care_database_url = settings.care_database_url
engine = create_engine(care_database_url.get_secret_value())
""",
    "an import of the session factory": """
from app.db import care_session


def roster():
    return care_session()
""",
    "a session reached as an attribute of another module": """
from app import db


def roster():
    return db.care_sessions()
""",
    "the role name in a string": """
from app.db import engine_for

CARE_ROLE = "pulse_care"


def roster():
    return engine_for(CARE_ROLE).connect()
""",
}

# Sources that must **not** be reported. Each is a shape a correct module is
# written in, and each holds a rule this file states in prose somewhere above. A
# repair that starts reporting one of them has widened the rule rather than closed
# a hole in it, and the difference is invisible in the offender sweep on today's
# tree — where both look like "no offenders" until the module that trips it is
# written. `docs/MISTAKES.md` entry 3 asks for exactly this half.
DOES_NOT_REACH_FOR_CARE = {
    "the module that builds the pool": """
from sqlalchemy.orm import sessionmaker

_care_sessions = sessionmaker()


def _care_session():
    return _care_sessions()
""",
    "a class that owns both pools": """
class Pools:
    def __init__(self, factory):
        self.care_session = factory()

    def open(self):
        return self.care_session()
""",
    "prose naming the role": '''
def roster():
    """Runs on `pulse_app`, never on `pulse_care` — see E0-10."""
    # Nothing here may reach a pulse_care session.
    return None
''',
    "an identifier that only says care": """
def summarise(care_case):
    return care_case.opened_at
""",
    "an ordinary application session": """
from app.db import session_scope


def roster():
    with session_scope() as session:
        return session.execute("SELECT 1")
""",
    "a Care name that only looks like a credential": """
from app.constants import CARE_SECURITY_DEFINER_OWNER


def owner():
    return CARE_SECURITY_DEFINER_OWNER
""",
    "the settings class that declares the credential": """
from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    care_database_url: SecretStr | None = None

    def care_is_configured(self) -> bool:
        return self.care_database_url is not None
""",
}


@pytest.mark.parametrize("sample", sorted(REACHES_FOR_CARE))
def test_the_sweep_reports_a_module_that_reaches_for_a_care_session(sample: str) -> None:
    """Every way of getting a `pulse_care` connection that this sweep claims to see.

    The two Settings samples are the finding. `care_database_url` is the one
    public attribute that hands out the credential, and a module doing
    `create_engine(Settings().care_database_url.get_secret_value())` and calling
    the result `engine` said "care" and said nothing the session vocabulary
    recognised — so it passed both sweeps above with nothing flagged, while
    holding a connection E0-10's grants cannot distinguish from the Care
    service's own.

    The second sample is the same read with one ordinary line in front of it, and
    it is the one a widened vocabulary alone does not catch: bindings used to be
    collected into a single set and subtracted from every load, so
    `care_database_url = settings.care_database_url` masked the attribute read for
    the whole module. It is the idiom `services/safety.py` itself uses, which
    makes it the shape a later module is most likely to copy.

    The rest are what the sweep already caught, kept here so that a repair of the
    two above cannot quietly cost them.
    """
    reported = obtains_a_care_session(ast.parse(REACHES_FOR_CARE[sample]))
    assert reported, (
        f"The sweep reports nothing for {sample!r}:\n{REACHES_FOR_CARE[sample]}\n"
        "That source obtains a `pulse_care` connection, so a module under `backend/app` written "
        "this way passes `test_no_module_outside_the_care_service_obtains_a_care_session` — and "
        "that test would report success having seen it. E0-10: 'only the Care service module can "
        "obtain a `pulse_care` session… A caller can never choose its own pool, and no "
        "general-purpose helper hands out a `pulse_care` session.' The vocabulary is "
        f"'care' plus one of {list(SESSION_FRAGMENTS) + list(CREDENTIAL_FRAGMENTS)}, or the string "
        f"{CARE_ROLE_NAME!r} on its own; a load is measured against bindings of its own kind, so a "
        "local named after the attribute it reads does not hide the read."
    )


@pytest.mark.parametrize("sample", sorted(DOES_NOT_REACH_FOR_CARE))
def test_the_sweep_allows_a_module_written_the_way_the_rule_intends(sample: str) -> None:
    """The other direction: what the rule permits, so that closing a hole cannot widen it.

    Each of these is a rule this file already states in prose, put where it can
    fail. A definition is not a use, so the module that builds the pool is not an
    offender. A class that assigns `self.care_session` may read it back — that is
    what attribute bindings are collected for, and a repair that simply stopped
    subtracting them would report the defining module against its own pool. A
    comment or a docstring naming the role is the sentence a careful author writes
    in the module that must *not* use one, which is why this sweep reads the
    syntax tree and not the file text. "care" without a session or credential word
    is `care_case`, and a session without "care" is every other session in the
    application.

    The sample importing `CARE_SECURITY_DEFINER_OWNER` marks the boundary of the
    credential vocabulary rather than of the session one: "uri" is a substring of
    "security", so it is deliberately not a credential fragment, and this sample
    is what makes that deliberate rather than forgotten. If a future field
    genuinely needs "uri", this sample is the conversation — not a silent third
    widening of a tuple.

    The settings sample is `app/config.py` reduced to the shape that matters. The
    module that *declares* the Care credential reads it back off itself, and a
    sweep that reported that would name the one file whose job is to hold the
    field — the same "a definition is not a use" rule the module docstring states,
    arriving where a class body rather than a module body does the defining.
    `bound_as_an_attribute` says what that admits.
    """
    reported = obtains_a_care_session(ast.parse(DOES_NOT_REACH_FOR_CARE[sample]))
    assert not reported, (
        f"The sweep reports {sorted(reported)} for {sample!r}:\n"
        f"{DOES_NOT_REACH_FOR_CARE[sample]}\n"
        "Nothing in that source obtains a Care session, so this is the sweep firing on the wrong "
        "thing — and every module under `backend/app` written this way is now a failure of "
        "`test_no_module_outside_the_care_service_obtains_a_care_session` with nothing wrong. A "
        "sweep that reports the shapes a correct module is written in gets its vocabulary edited "
        "until it reports nothing at all, which is how this guard is really lost."
    )


def test_every_care_setting_is_a_spelling_this_sweep_recognises(
    configured_env: dict[str, str],
    import_app_module: Any,
) -> None:
    """The canary on the vocabulary, read off `Settings` rather than written down here.

    A fragment tuple is a guess about what somebody will call something, and a
    wrong guess costs the whole guard silently: `reads_as_a_care_session` answers
    `False`, `obtains_a_care_session` returns the empty set, and every sweep in
    this file reports success having seen the offending module
    (`docs/MISTAKES.md` entry 3). This is the file's answer to that, and it is the
    same answer as the non-emptiness guards on the tests above — assert the thing
    the guard must be able to see, so that a wrong guess is a red test naming the
    field.

    **Derived, not copied.** The set is every `Settings` field whose name mentions
    Care, read off the class, so a rename in `app/config.py` goes red here rather
    than going quiet; holding the field's name in a constant beside the tuple
    would be this test checking one copy of a fact against another
    (`docs/MISTAKES.md` entry 19). The field it finds is the Care database URL,
    which is the whole of what a caller needs to open a `pulse_care` connection
    for itself, without asking `services/safety.py` for anything.

    **An empty set is a failure and not a pass**, and it is the more interesting
    of the two failures: it means the Care credential is no longer a setting whose
    name says Care — renamed, folded into another field, or removed — and every
    sweep in this file is then looking for a word that has left the codebase.
    """
    config = import_app_module("app.config")
    assert config is not None, (
        "There is no `app.config` module to read the Care setting off. E0-01 ships `Settings`, and "
        "E0-10 adds the Care database URL to it as the credential `services/safety.py` opens the "
        "second pool with."
    )
    settings_class = getattr(config, "Settings", None)
    assert settings_class is not None, (
        "`app.config` exposes no `Settings`, so this test cannot ask what the Care credential is "
        "called. E0-01's criterion 2 puts every configuration variable on it."
    )

    fields = sorted(name for name in settings_class.model_fields if "care" in name.lower())
    assert fields, (
        "No `Settings` field has 'care' in its name, out of "
        f"{sorted(settings_class.model_fields)}. E0-10 gives the Care queue its own database role "
        "and its own connection, and the credential for it is a setting — so either it has been "
        "renamed to something this file cannot find, or the second pool is gone. Both matter here "
        "rather than only in `app/config.py`: every sweep in this module recognises a Care session "
        "by the word 'care' in an identifier, so a credential that no longer says 'care' is one "
        "this file is blind to, and it would report success on a module that reads it."
    )

    unseen = [name for name in fields if not reads_as_a_care_session(name)]
    assert not unseen, (
        f"`Settings` carries {unseen}, and this file's sweeps do not recognise the name as a Care "
        "session or as the credential for one. Whatever that field is called is what a future "
        f"module writes `create_engine(Settings().{unseen[0]}...)` with, and "
        "the sweeps that are supposed to catch it match 'care' plus one of "
        f"{list(SESSION_FRAGMENTS) + list(CREDENTIAL_FRAGMENTS)}. Add the spelling to "
        "`CREDENTIAL_FRAGMENTS` or `SESSION_FRAGMENTS` above — this failure is the tuple being one "
        "word behind `app/config.py`, which is precisely the state in which "
        "`test_no_module_outside_the_care_service_obtains_a_care_session` passes while seeing "
        "nothing."
    )
