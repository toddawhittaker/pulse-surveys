"""E5-06 — the named-set API: the names it is asked through, and the world it is asked over.

Seven test modules ask the same questions of the same seven routes, so the
driving lives here and each module asserts (`docs/MISTAKES.md` entry 13). Four
things are needed and nothing in this repository answers any of them:

  - **A leadership session at the door, and every session that is not one.**
    Criterion 1 is "each route refuses an unauthenticated call and a student or
    instructor session, and answers a leadership session — both directions, per
    route, driven over HTTP against the built application". The launched
    sessions are `tests/fixtures/report_api.py`'s three roles; the two-hat
    person criterion 2's known trap asks for holds an `INSTRUCTOR` **and** a
    `DEAN` assignment at once, and each of her two sessions is minted through
    the module both doors issue through, exactly as
    `tests/fixtures/instructor_sections.py` mints E4-18's two.

  - **Two leaders and a set each.** Work-order decision 1 settles the scope:
    list, GET-by-id and preview answer every set to any leadership session,
    while PUT and DELETE are allowed only to the set's own definer. So the
    world holds one set defined by the session's person and one defined by
    somebody else, and every scope assertion has both directions available.

  - **Courses and sections a set resolves over.** The preview's `section_count`
    is `len(resolve_named_set(...))`, so a positive control needs member
    courses with sections at the set's declared length **and** near misses that
    must not be counted: a member course's section at another length, and a
    section of a course the set does not name. `member_count` and
    `section_count` are deliberately two different numbers in this world, so a
    preview answering one in the other's place is red rather than plausible.

  - **The names the work order settles**, spelled once. The module homes
    (`app.api.leadership`, `app.services.comparison_sets`,
    `app.schemas.comparison_sets`, the two new dependencies in
    `app.api.deps`), the seven paths, and the wire members. A name the work
    order settles is transcribed; a name it does not settle is **discovered**,
    and an ambiguous discovery is a failure naming the ambiguity rather than a
    guess.

**The refusal sentences are discovered, not spelled.** The work order settles
that each refusal carries "a one-sentence `detail` constant the tests pin" and
that the copy constants "live in `backend/app/copy/` beside the existing modules
there" — it settles the constants' *names* and neither the module they sit in
nor the sentences themselves. So `refusal_sentence` walks `app.copy`'s modules
for a constant of that name, requires every place that holds it to hold the same
string, and requires at least one of those places to be under `app.copy`. A
sentence transcribed here would be this suite writing the product's copy, and a
test comparing a body against a string it invented would pass against a route
that refused for another reason entirely.

**Why the sentence is what a refusal test pins.** A status alone cannot say
which layer refused: 422 is what a Pydantic validation error and a translated
constraint violation both answer with, and 404 is what an unregistered router
and an unknown set both answer with. Each sentence belongs to exactly one layer
— `NOT_LEADERSHIP` to the dependency, `SET_UNAVAILABLE` and
`NOT_THE_SETS_DEFINER` to the service's scope read, the five write sentences to
the constraint translation — so a body carrying it names the layer that spoke.

**Nothing here decides what a route should answer.** This file seeds rows,
mints sessions and makes requests; every count, every order and every expected
sentence is written out in the module that asserts it (`docs/MISTAKES.md`
entries 19 and 30). In particular it never computes a member count, a section
count or a label: the counts are planted as a plan the test module states, and
the label is composed by `tests/fixtures/student_read.py`'s own reader, which is
the one reader this suite has for that form.

**Every guard is a plain function called from a test body, never a fixture**
(`docs/MISTAKES.md` entry 44). On a tree where E5-06 is unbuilt each module goes
red as a FAILED naming the missing deliverable — the router, the dependency, the
schema module, the copy constant — rather than as an ERROR in somebody's setup.
`named_set_world` is the exception that proves it: everything it builds is
E4-07's, E5-01's and E1's machinery, all of which exists on this tree, and it
names nothing E5-06 owes.

**The environment** (`docs/MISTAKES.md` entries 40 and 52): everything rides
`report_door_as`, and therefore `launch_driver_in`, `tool_doors` and
`configured_env` — the development name, laid down before the application is
imported. The minted sessions are signed with the secret out of that same
mapping rather than out of `os.environ`, so the token this suite mints and the
token the application verifies cannot come from two readings of the environment.
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import timedelta
from typing import Any, NamedTuple
from uuid import uuid4

import pytest

from fixtures.comparison_sets import (
    COMPARISON_SET_TABLE,
    LENGTH_COLUMN,
    LEVEL_COLUMN,
    NAME_COLUMN,
    SPEC_LENGTHS,
    SPEC_LEVELS,
    member_of,
    membership_table,
    one_key_column_to,
)
from fixtures.report_api import (
    AFTER_THE_LAST_WINDOW,
    INSTRUCTOR_ROLE,
    LEADERSHIP_ROLE,
    STUDENT_ROLE,
    ReportDoor,
    every_object,
    strings_in,
)
from fixtures.student_read import (
    AUTHENTICATE_HEADER,
    AUTHENTICATE_SCHEME,
    COURSE_NUMBER_COLUMN,
    COURSE_TABLE,
    COURSE_TITLE_COLUMN,
    PREFIX_TABLE,
    StudentReadWorld,
    decoded,
)
from fixtures.submit import session_secret
from fixtures.supervision import (
    foreign_key_columns,
    require_table,
    single_primary_key,
)
from fixtures.survey_windows import (
    COHORT_SECTION_MODALITY,
    SECTION_CODE_COLUMN,
    SECTION_END_COLUMN,
    SECTION_LENGTH_COLUMN,
    SECTION_START_COLUMN,
    SECTION_TABLE,
    SEEDED_COHORTS,
    TERM_TABLE,
)
from fixtures.web_identity import PERSON_ID_CLAIM, USER_ID_CLAIM, claims_in_session

# E1-08's own subject claim, and the `LandingRole` member the work order names as
# the gate: "the role gate is `session.role is not LandingRole.LEADERSHIP`".
# `LEADERSHIP_ROLE` above is the *assignment* role a launch is seeded with
# (`DEAN`), which is a different vocabulary — `tests/fixtures/supervision.py`'s
# `ROLE_ALIASES` — and conflating the two is how a session is minted for a role
# no enum has.
SUBJECT_CLAIM = "sub"
LEADERSHIP_LANDING_ROLE = "LEADERSHIP"

# ---------------------------------------------------------------------------
# The names E5-06's work order settles, transcribed once.
# ---------------------------------------------------------------------------

# Work order, "The API contract": "Router: `backend/app/api/leadership.py`,
# `APIRouter(tags=["leadership"])`, registered in `main.py` after
# `instructor.router`."
LEADERSHIP_API_MODULE = "app.api.leadership"

# Decision 7: "the write/scope service in a NEW
# `backend/app/services/comparison_sets.py` — nothing existing fits"; "Wire
# schemas in a new `backend/app/schemas/comparison_sets.py`."
SERVICE_MODULE = "app.services.comparison_sets"
SCHEMA_MODULE = "app.schemas.comparison_sets"

# The contract again: "reads carry `require_leadership`, writes carry
# `csrf_verified_leadership` (both new, mirroring the student/instructor pair
# exactly — declared as dependencies, never called)".
DEPS_MODULE = "app.api.deps"
REQUIRE_LEADERSHIP = "require_leadership"
CSRF_VERIFIED_LEADERSHIP = "csrf_verified_leadership"

# Decision 7: "Copy constants (the refusal sentences) live in
# `backend/app/copy/` beside the existing modules there." The package is settled
# and the module inside it is not, so `refusal_sentence` searches the package.
COPY_PACKAGE = "app.copy"

# The seven paths, settled outright by the work order's contract block — unlike
# E4-07's two, whose URLs no record named and which are therefore discovered.
# E5-09 builds its client against this exact text.
SETS_PATH = "/leadership/comparison-sets"
OPTIONS_PATH = f"{SETS_PATH}/options"


def set_path(set_id: Any) -> str:
    """`/leadership/comparison-sets/{set_id}`."""
    return f"{SETS_PATH}/{set_id}"


def preview_path(set_id: Any) -> str:
    """`/leadership/comparison-sets/{set_id}/preview`."""
    return f"{set_path(set_id)}/preview"


# The wire members, member by member, from the contract block.
SETS_MEMBER = "sets"
ID_FIELD = "id"
NAME_FIELD = "name"
LENGTH_FIELD = "length_weeks"
LEVEL_FIELD = "level"
MEMBER_COUNT_FIELD = "member_count"
EDITABLE_FIELD = "editable"
MEMBER_COURSE_IDS_FIELD = "member_course_ids"
CREATED_AT_FIELD = "created_at"
UPDATED_AT_FIELD = "updated_at"
SECTION_COUNT_FIELD = "section_count"
LENGTHS_FIELD = "lengths"
LEVELS_FIELD = "levels"
COURSES_FIELD = "courses"
COURSE_ID_FIELD = "id"
COURSE_LABEL_FIELD = "label"
COURSE_LEVEL_FIELD = "level"

# Every field `SetWrite` carries, which is how the write model is found in a
# module whose class names the work order does not settle.
SET_WRITE_FIELDS = frozenset({NAME_FIELD, LENGTH_FIELD, LEVEL_FIELD, MEMBER_COURSE_IDS_FIELD})

# The two members the preview may carry, and nothing else (criterion 5).
PREVIEW_FIELDS = (MEMBER_COUNT_FIELD, SECTION_COUNT_FIELD)

# The statuses the contract fixes, each named where a failure can quote it.
LIST_OK = 200
CREATED = 201
NO_CONTENT = 204
ROLE_REFUSED = 401
NOT_THE_DEFINER = 403
UNKNOWN_SET = 404
DUPLICATE_NAME = 409
REFUSED_VALUE = 422

# Route conventions the work order names beside `_unavailable`: every answer
# carries `Cache-Control: no-store`.
CACHE_CONTROL_HEADER = "Cache-Control"
NO_STORE = "no-store"

# The refusal constants, by name. The sentences themselves are read out of
# `app.copy` — see `refusal_sentence` and this module's docstring.
NOT_LEADERSHIP = "NOT_LEADERSHIP"
SET_UNAVAILABLE = "SET_UNAVAILABLE"
NOT_THE_SETS_DEFINER = "NOT_THE_SETS_DEFINER"
NAME_ALREADY_USED = "NAME_ALREADY_USED"
LENGTH_NOT_A_CALENDAR_LENGTH = "LENGTH_NOT_A_CALENDAR_LENGTH"
LEVEL_NOT_A_COURSE_LEVEL = "LEVEL_NOT_A_COURSE_LEVEL"
MEMBER_NOT_AT_THE_SETS_LEVEL = "MEMBER_NOT_AT_THE_SETS_LEVEL"
MEMBER_NOT_A_COURSE = "MEMBER_NOT_A_COURSE"

REFUSAL_CONSTANTS = (
    NOT_LEADERSHIP,
    SET_UNAVAILABLE,
    NOT_THE_SETS_DEFINER,
    NAME_ALREADY_USED,
    LENGTH_NOT_A_CALENDAR_LENGTH,
    LEVEL_NOT_A_COURSE_LEVEL,
    MEMBER_NOT_AT_THE_SETS_LEVEL,
    MEMBER_NOT_A_COURSE,
)

# FastAPI's own member for an `HTTPException`'s message.
DETAIL_MEMBER = "detail"

ROUTER_IS_OWED = (
    "E5-06's work order settles the router: `backend/app/api/leadership.py`, `APIRouter(tags="
    '["leadership"])`, registered in `app.main.create_app` after `instructor.router`, carrying '
    f"seven routes — `GET {SETS_PATH}`, `POST {SETS_PATH}`, `GET {OPTIONS_PATH}`, `GET "
    f"{SETS_PATH}/{{set_id}}`, `PUT {SETS_PATH}/{{set_id}}`, `DELETE {SETS_PATH}/{{set_id}}` and "
    f"`GET {SETS_PATH}/{{set_id}}/preview`. Reads carry `{REQUIRE_LEADERSHIP}` and writes carry "
    f"`{CSRF_VERIFIED_LEADERSHIP}`; a router nothing registers serves nothing."
)

DEPENDENCIES_ARE_OWED = (
    f"`{DEPS_MODULE}.{REQUIRE_LEADERSHIP}` and `{DEPS_MODULE}.{CSRF_VERIFIED_LEADERSHIP}` — the "
    "work order settles both, mirroring `require_student`/`csrf_verified_student` exactly: the "
    "role comes from the session claims and never from a parameter, the gate is `session.role is "
    f"not LandingRole.LEADERSHIP`, and the refusal is the 401 + Bearer challenge carrying the "
    f"`{NOT_LEADERSHIP}` sentence."
)

SERVICE_IS_OWED = (
    f"`{SERVICE_MODULE}` — decision 7 puts the write and scope service in a module of its own: "
    "`services/benchmarks.py` is the read/figure module and its docstring forbids writes, and "
    "`services/authz.py` is the authorization chokepoint. SPEC §13 governs the placement."
)

SCHEMA_IS_OWED = (
    f"`{SCHEMA_MODULE}` — the work order settles a new schema module carrying the contract's four "
    f"shapes. `SetWrite` is the one whose fields are exactly {sorted(SET_WRITE_FIELDS)}, and "
    "decision 3's proof rests on `length_weeks` being typed `int` and `level` `str`: a Pydantic "
    "422 over an enum would prove nothing about the database constraint the route is supposed to "
    "be translating."
)

COPY_IS_OWED = (
    "E5-06's refusals each carry a one-sentence `detail` constant, and decision 7 puts the copy "
    f"constants in `backend/app/copy/` beside the existing modules there. The eight are "
    f"{list(REFUSAL_CONSTANTS)}. A refusal test pins the sentence rather than the status, because "
    "a status alone cannot say which layer refused."
)

# ---------------------------------------------------------------------------
# This world's own values. Every one is an input a test names and this file
# writes down; nothing here is read back as an answer.
# ---------------------------------------------------------------------------

# The length and level the sets in this world declare. Six weeks because SPEC
# §2.2 makes it the commonest length and because three of `SEEDED_COHORTS`'
# start letters carry it, so several six-week sections can be planted under
# different courses of one term; `UG` because §8's band for it is the widest and
# leaves room for three distinct course numbers under one prefix.
DECLARED_LENGTH = 6
DECLARED_LEVEL = "UG"

# The near-miss length a member course's other section carries. Eight weeks is
# in SPEC §2.2's set — so a section at it is a legal section rather than a
# broken row — and it is not the declared length, which is the whole point: a
# resolution that ignored the set's declared length would count it.
ANOTHER_LENGTH = 8

# The level a course outside the set's level sits at, for criterion 3's
# cross-level member refusal. `GR` rather than `UGGR`, because §5.1 forbids
# folding any level into another and `GR` is the one a reader is likeliest to
# think of as "near" `UG`.
ANOTHER_LEVEL = "GR"

# Three `UG` course numbers and one `GR` one, all inside SPEC §8's bands and all
# distinct, because `uq_course_prefix_id_lms_number` scopes a number to its
# prefix and every course here hangs off the world's one prefix.
COURSE_NUMBERS = {
    "first_member": "301",
    "second_member": "302",
    "outsider": "303",
    "wrong_level": "701",
}

# The titles those courses carry. Distinctive enough that finding one in a
# preview body is unmistakable — which is exactly what criterion 5's denial
# sweep looks for — and long enough not to occur inside a uuid.
COURSE_TITLES = {
    "first_member": "E5-06 first member course: the one two of this set's sections hang off",
    "second_member": "E5-06 second member course: the one carrying this set's third section",
    "outsider": "E5-06 outsider course: named by no set and counted by no preview",
    "wrong_level": "E5-06 graduate course: the member a UG set may not hold",
}

# The sections this world plants, as `(course key, cohort letter, ordinal)`.
# Two six-week sections under the first member course, one under the second, one
# eight-week near miss under the first, and one six-week section under a course
# no set names. The cohort letter carries the length (`SEEDED_COHORTS`), so the
# length is the seed's fact rather than this file's, and the ordinal keeps the
# codes distinct from each other and from the report world's own `F1WW`.
PLANTED_SECTIONS = (
    ("first_member", "E", "2"),
    ("first_member", "H", "2"),
    ("second_member", "E", "3"),
    ("first_member", "X", "2"),
    ("outsider", "H", "3"),
)

# The names the two planted sets carry. Written out because criterion 5 sweeps
# a preview body for them and because the duplicate-name refusal needs a name
# that is certainly already used.
HER_SET_NAME = "E5-06 the set this session's leader defined"
THEIR_SET_NAME = "E5-06 the set another leader defined"

# **The two-hat person's own set**, planted by the ruling on
# `docs/disputes/E5-06-01.md`. The two-hat test's subject is the role gate — the
# same person admitted through one hat and refused through the other — and for
# `edit` and `delete` that question can only be asked of a set she is entitled to
# write, because decision 1 scopes those two by creator. Driving her at another
# leader's set asked the role question and a scoping question at once, and the
# scoping module answers the second one the other way; no tree satisfied both.
# So she gets a set of her own, and her two sessions are pointed at it.
TWO_HAT_SET_NAME = "E5-06 the set the two-hat leader defined"

# The subjects the minted sessions name. Neither is a subject any launch in this
# suite signs, so a session carrying one cannot be confused with a session a
# door issued.
THE_TWO_HAT_SUBJECT = "e5-06-instructor-and-dean"

# How far from the development clock an instant may sit and still be that clock's
# rather than the wall clock's. The pretended instant is months away from today,
# so an hour is wide enough for the drift ADR 0109's `real + (pretend_now -
# anchored_at)` accumulates while a test runs and far narrower than the gap a
# `datetime.now(UTC)` would show.
CLOCK_TOLERANCE = timedelta(hours=1)


# ---------------------------------------------------------------------------
# The deliverables, named where a test can fail on them rather than error.
# ---------------------------------------------------------------------------


def _module(name: str, owed: str) -> Any:
    """One module, imported where a test can fail on it rather than error.

    A `ModuleNotFoundError` at a test module's top level is a collection error,
    which survives the implementation landing and reads to a hurried eye as a
    red suite (`docs/MISTAKES.md` entry 44). This is a FAILED naming the file.
    An import error raised from *inside* the module is re-raised rather than
    reported as this module's absence: the two are different defects.
    """
    from importlib import import_module

    try:
        return import_module(name)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        absent = missing.name
        if absent is not None and not (absent == name or name.startswith(f"{absent}.")):
            raise
        pytest.fail(f"`{name}` does not exist. {owed}")


def leadership_api_module() -> Any:
    """`app.api.leadership`, or a failure naming the router E5-06 owes."""
    return _module(LEADERSHIP_API_MODULE, ROUTER_IS_OWED)


def comparison_sets_service() -> Any:
    """`app.services.comparison_sets`, or a failure naming it."""
    return _module(SERVICE_MODULE, SERVICE_IS_OWED)


def comparison_sets_schema() -> Any:
    """`app.schemas.comparison_sets`, or a failure naming it."""
    return _module(SCHEMA_MODULE, SCHEMA_IS_OWED)


def leadership_dependency(name: str) -> Any:
    """One of E5-06's two new dependencies, as the object routes are swept for."""
    module = _module(
        DEPS_MODULE,
        "E1-13 puts this project's door pages there, E2-09 the student-session dependency and "
        "E4-07 the instructor one; E5-06 adds the leadership pair beside them.",
    )
    found = getattr(module, name, None)
    if not callable(found):
        pytest.fail(
            f"`{DEPS_MODULE}` exposes no callable `{name}`; it exposes "
            f"{sorted(entry for entry in vars(module) if not entry.startswith('_'))}.\n\n"
            f"{DEPENDENCIES_ARE_OWED}"
        )
    return found


def _copy_modules() -> list[Any]:
    """Every module under `app.copy`, imported.

    Walked with `pkgutil` rather than named, because decision 7 settles the
    package and leaves the module to the implementer. A package that is not
    there at all is reported as this failure rather than as an empty walk: an
    empty walk would make `refusal_sentence` say "the constant is nowhere",
    which sends a reader looking for a constant instead of for a package.
    """
    import pkgutil
    from importlib import import_module

    package = _module(
        COPY_PACKAGE,
        "E2 ships the copy package; every user-facing sentence in this application lives under it.",
    )
    paths = list(getattr(package, "__path__", []) or [])
    if not paths:
        pytest.fail(
            f"`{COPY_PACKAGE}` is not a package (it declares no `__path__`), so this suite cannot "
            f"walk it for E5-06's refusal sentences.\n\n{COPY_IS_OWED}"
        )
    found = [package]
    for entry in pkgutil.iter_modules(paths):
        found.append(import_module(f"{COPY_PACKAGE}.{entry.name}"))
    return found


def refusal_sentence(name: str) -> str:
    """The sentence E5-06 refuses with, read out of the copy package.

    **Discovered rather than transcribed.** The work order settles each
    constant's *name* and neither the module it sits in nor the words in it, so
    a sentence written here would be this suite choosing the product's copy —
    and a body compared against a string a fixture invented would be red against
    a correct route and green against one that refused for a different reason.

    Three things are required, and each is a way this could go quietly wrong:
    the constant exists somewhere the application can be read from; every place
    holding it holds the *same* string, so a route importing a stale second copy
    is a failure rather than a passing comparison against whichever one this
    found first; and at least one of those places is under `app.copy`, which is
    where decision 7 puts it.
    """
    homes: dict[str, str] = {}
    searched = [
        *_copy_modules(),
        _module(DEPS_MODULE, DEPENDENCIES_ARE_OWED),
        leadership_api_module(),
        comparison_sets_service(),
        comparison_sets_schema(),
    ]
    for module in searched:
        value = getattr(module, name, None)
        if isinstance(value, str):
            homes[module.__name__] = value
    if not homes:
        pytest.fail(
            f"No module this suite can reach declares a string `{name}`. Searched: "
            f"{sorted(module.__name__ for module in searched)}.\n\n{COPY_IS_OWED}"
        )
    distinct = sorted(set(homes.values()))
    if len(distinct) != 1:
        pytest.fail(
            f"`{name}` is spelled {len(distinct)} different ways in this application: {homes}. One "
            "refusal is one sentence; two copies mean a route can answer with a string no test is "
            "pinning."
        )
    under_copy = [home for home in homes if home.startswith(COPY_PACKAGE)]
    if not under_copy:
        pytest.fail(
            f"`{name}` is declared in {sorted(homes)} and nowhere under `{COPY_PACKAGE}`. Decision "
            "7 puts the refusal sentences with the rest of this application's user-facing copy, "
            "which is also what puts them inside the copy inventory E5-13 sweeps (SPEC §4.1 items "
            "4 and 5)."
        )
    return distinct[0]


def set_write_model() -> Any:
    """The schema model whose fields are exactly `SetWrite`'s four.

    **Discovered by its field set, because the work order settles the wire
    contract and not the class name.** Zero or several is a failure naming the
    ambiguity, which is the device `tests/fixtures/report_api.py` uses for the
    suppression helper and for the same reason.
    """
    module = comparison_sets_schema()
    found = [
        value
        for name, value in vars(module).items()
        if not name.startswith("_")
        and isinstance(value, type)
        and set(getattr(value, "model_fields", None) or {}) == set(SET_WRITE_FIELDS)
    ]
    if len(found) != 1:
        pytest.fail(
            f"`{SCHEMA_MODULE}` declares {len(found)} models whose fields are exactly "
            f"{sorted(SET_WRITE_FIELDS)} ({[model.__name__ for model in found]}); it declares "
            f"{sorted(name for name in vars(module) if not name.startswith('_'))}.\n\n"
            f"{SCHEMA_IS_OWED}"
        )
    return found[0]


# ---------------------------------------------------------------------------
# Reading an answer.
# ---------------------------------------------------------------------------


def detail_of(answered: Any) -> str:
    """The `detail` string one refusal carries, or a failure saying what came instead.

    A named failure rather than a `KeyError`: a refusal that carries no detail
    at all is a different defect from one carrying the wrong sentence, and only
    one of the two is fixed by looking at the copy module.
    """
    body = decoded(answered, f"The {answered.status_code} refusal")
    if not isinstance(body, dict) or not isinstance(body.get(DETAIL_MEMBER), str):
        pytest.fail(
            f"The {answered.status_code} answer carries no `{DETAIL_MEMBER}` string: "
            f"{answered.text[:400]!r}. Every refusal here carries the one sentence saying which "
            "layer refused, and a refusal test reading the status alone would be satisfied by a "
            "401 from anywhere in the stack."
        )
    return body[DETAIL_MEMBER]


def body_of(answered: Any, what: str, expected: int) -> Any:
    """One answered body, after requiring the status the contract fixes for it.

    The status is asserted here rather than in every caller, because a body
    decoded off a refusal is a body every later assertion is vacuously true of
    (`docs/MISTAKES.md` entry 3).
    """
    if answered.status_code != expected:
        pytest.fail(
            f"{what} answered {answered.status_code} rather than {expected}. Body begins "
            f"{answered.text[:400]!r}.\n\n{ROUTER_IS_OWED}"
        )
    return decoded(answered, what)


# ---------------------------------------------------------------------------
# The door: one leadership session, one of every session that is not one, and
# the seven routes driven over HTTP.
# ---------------------------------------------------------------------------


# "No token was named", which cannot be spelled `None`: `None` is a value a
# caller passes on purpose here — it is criterion 1's unauthenticated call.
NOT_GIVEN: Any = object()


class NamedSetDoor:
    """The seven routes, asked with exactly one credential each.

    The cookie jar is emptied for every call, the leadership one included, so a
    request carries the session the caller named and nothing else: E1-08
    delivers a session as a `Set-Cookie` on the landing redirect as well as in
    the URL fragment, and `httpx` sends jar cookies on every later request to
    the same host, so a read made with a minted token through the client a
    launch was driven with would otherwise carry that launch's session too
    (`docs/disputes/E2-09-01.md`).
    """

    def __init__(self, door: ReportDoor, world: "NamedSetWorld") -> None:
        self.door = door
        self.world = world

    def _ask(self, method: str, url: str, *, token: Any, json: Any = None) -> Any:
        headers = {}
        if token is not None:
            headers["authorization"] = f"{AUTHENTICATE_SCHEME} {token}"
        with self.door.carrying_no_cookie():
            return self.door.tool.request(method, url, headers=headers, json=json)

    # -- the seven routes, in the contract's order ---------------------------

    def list_sets(self, *, token: Any = NOT_GIVEN) -> Any:
        return self._ask("GET", SETS_PATH, token=self._token(token))

    def create(self, body: Any, *, token: Any = NOT_GIVEN) -> Any:
        return self._ask("POST", SETS_PATH, token=self._token(token), json=body)

    def options(self, *, token: Any = NOT_GIVEN) -> Any:
        return self._ask("GET", OPTIONS_PATH, token=self._token(token))

    def read(self, set_id: Any, *, token: Any = NOT_GIVEN) -> Any:
        return self._ask("GET", set_path(set_id), token=self._token(token))

    def edit(self, set_id: Any, body: Any, *, token: Any = NOT_GIVEN) -> Any:
        return self._ask("PUT", set_path(set_id), token=self._token(token), json=body)

    def remove(self, set_id: Any, *, token: Any = NOT_GIVEN) -> Any:
        return self._ask("DELETE", set_path(set_id), token=self._token(token))

    def preview(self, set_id: Any, *, token: Any = NOT_GIVEN) -> Any:
        return self._ask("GET", preview_path(set_id), token=self._token(token))

    def _token(self, given: Any) -> Any:
        """The caller's token, or this door's leadership one when none was named."""
        return self.door.token if given is NOT_GIVEN else given


class PlantedSet(NamedTuple):
    """One `comparison_set` row as the handful of facts a test names it by."""

    set_id: Any
    name: str
    creator_person_id: Any
    member_course_ids: tuple[Any, ...]


class NamedSetWorld:
    """Two leaders, two sets, four courses and five sections — and who defined what.

    Nothing here is computed from anything under test: the sets are planted
    through the model layer (E5-06's own route is what the tests drive), the
    courses carry numbers this file chose so SPEC §8 derives the levels it wants,
    and the sections carry `SEEDED_COHORTS`' own lengths.
    """

    def __init__(
        self,
        door: ReportDoor,
        committed_rows: Any,
        tables: dict[str, Any],
        web_identity: Any,
        configured: Mapping[str, str],
    ) -> None:
        self.door = door
        self.rows = committed_rows
        self.tables = tables
        self.web_identity = web_identity
        self.configured = configured
        self.world = door.rows.world
        self.courses: dict[str, Any] = {}
        self.sections: list[Any] = []
        self.hers: PlantedSet | None = None
        self.theirs: PlantedSet | None = None
        self.the_two_hats: PlantedSet | None = None
        self.another_leader_person_id: Any = None
        self.two_hat_person_id: Any = None

    # -- keys and readers -----------------------------------------------------

    @property
    def session(self) -> Any:
        return self.world.session

    @property
    def leader_person_id(self) -> Any:
        """The `person` the leadership session names, off the session it carries."""
        return self.door.person_id

    def course_id(self, which: str) -> Any:
        return self.courses[which][self.world.key_of(COURSE_TABLE)]

    def refresh(self) -> None:
        """End this session's transaction, so a read after an HTTP call sees the database."""
        self.session.rollback()

    def set_rows(self) -> list[Any]:
        """Every `comparison_set` row in the database, whole."""
        from sqlalchemy import select

        self.refresh()
        table = require_table(self.tables, COMPARISON_SET_TABLE)
        return list(self.session.execute(select(table)).mappings().all())

    def set_row(self, set_id: Any) -> Any:
        """One `comparison_set` row by key, or `None`."""
        key = single_primary_key(require_table(self.tables, COMPARISON_SET_TABLE))
        for row in self.set_rows():
            if str(row[key]) == str(set_id):
                return row
        return None

    def membership_rows(self) -> list[Any]:
        """Every membership row in the database, whole."""
        from sqlalchemy import select

        self.refresh()
        return list(self.session.execute(select(membership_table(self.tables))).mappings().all())

    def members_of(self, set_id: Any) -> list[Any]:
        """The membership rows naming one set."""
        table = membership_table(self.tables)
        key = single_primary_key(require_table(self.tables, COMPARISON_SET_TABLE))
        column = one_key_column_to(table, COMPARISON_SET_TABLE, key)
        return [row for row in self.membership_rows() if str(row[column]) == str(set_id)]

    def creator_column(self) -> str:
        """The column on `comparison_set` keyed to `person`, found rather than named.

        The work order calls it `created_by_person_id` and E5-01 built it; the
        key is what this follows, so a spelling that differs is not this suite's
        to decide and a table with no such key is a failure saying so.
        """
        table = require_table(self.tables, COMPARISON_SET_TABLE)
        found = foreign_key_columns(table, "person")
        if len(found) != 1:
            pytest.fail(
                f"`{COMPARISON_SET_TABLE}` has {len(found)} foreign keys to `person` ({found}). "
                "ADR 0164 gives a set exactly one creator, and E5-06's decision 1 scopes every "
                "edit and delete by it."
            )
        return found[0]

    def instant_column(self, which: str) -> str:
        """`created_at` or `updated_at` on `comparison_set`, or a failure naming it."""
        table = require_table(self.tables, COMPARISON_SET_TABLE)
        if which not in table.c:
            pytest.fail(
                f"`{COMPARISON_SET_TABLE}` declares no `{which}` (it declares "
                f"{[column.name for column in table.columns]}). E5-01's ticket names 'name, "
                "declared length, declared level, creator, timestamps', and E5-06's decision 3 "
                "makes those timestamps the whole record of a create and an edit."
            )
        return which

    def planted_names(self) -> dict[str, str]:
        """Every string this world planted that a preview must not carry, by what it is.

        Criterion 5 is that a preview "returns counts, never section names or
        figures", and the honest way to ask that of a payload is to look for the
        names that exist to be leaked: the course titles, the section codes and
        the two set names. A sweep for "any string" is asserted beside this one;
        this is the half that says *which* string would have been the leak.
        """
        found = {
            f"the title of the {which} course": title for which, title in COURSE_TITLES.items()
        }
        for section in self.sections:
            found[f"the code of section {section[SECTION_CODE_COLUMN]}"] = section[
                SECTION_CODE_COLUMN
            ]
        found["the name of this leader's set"] = HER_SET_NAME
        found["the name of the other leader's set"] = THEIR_SET_NAME
        found["the name of the two-hat leader's set"] = TWO_HAT_SET_NAME
        return found

    # -- the sessions ---------------------------------------------------------

    def minted(self, *, role: str, person_id: Any, user_id: Any, subject: str) -> str:
        """One session of `role` for `person_id`, through the module both doors issue through.

        Minted rather than launched, because E1-13 resolves a landing from the
        assignment model and a two-hat person's launch lands at exactly one of
        her two views — which of the two is `LANDING_PRECEDENCE`'s business and
        not this ticket's. Criterion 1 needs *both* of her sessions, so both are
        minted, and `test_the_minted_leadership_session_carries_what_a_launched_
        one_carries` is the control that a minted token is a token this
        application accepts at all.

        Bound by signature rather than by a spelling this file chose, copied in
        shape from `tests/fixtures/instructor_sections.py::_minted` rather than
        rewritten (`docs/MISTAKES.md` entry 37).
        """
        import inspect

        import app.services.session as session_module
        from app.services.authz import Door, LandingRole

        issue = getattr(session_module, "issue_session", None)
        if not callable(issue):
            pytest.fail(
                "`app.services.session` exposes no `issue_session`. E1-08 puts the shared session "
                "module there and both doors issue through it."
            )
        member = getattr(LandingRole, role, None)
        if member is None:
            pytest.fail(
                f"`LandingRole` has no member {role!r}; it has "
                f"{sorted(entry.name for entry in LandingRole)}."
            )
        parameters = inspect.signature(issue).parameters
        naming_a_person = [name for name in parameters if "person" in name.lower()]
        if len(naming_a_person) != 1 or "user_id" not in parameters:
            pytest.fail(
                f"`issue_session{inspect.signature(issue)}` declares {naming_a_person} naming a "
                "person and no usable `user_id`; E1-12 adds both to `SessionClaims`."
            )
        registration = self.door.driver.registration
        values: dict[str, Any] = {
            "door": Door.LAUNCH,
            "role": member,
            "sub": subject,
            "iss": registration.platform_row[registration.issuer_column],
            "secret": session_secret(self.configured),
            "user_id": None if user_id is None else str(user_id),
            naming_a_person[0]: None if person_id is None else str(person_id),
        }
        unfilled = [
            name
            for name, parameter in parameters.items()
            if parameter.default is parameter.empty
            and name not in values
            and parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
        ]
        if unfilled:
            pytest.fail(
                f"`issue_session{inspect.signature(issue)}` leaves {unfilled} for this fixture to "
                "fill and it has no value for them. A further required input is an interface "
                "question for the ticket — `minted` in tests/fixtures/named_sets.py is where a "
                "spelling is taught."
            )
        return issue(**values)

    def two_hat_sessions(self) -> tuple[str, str]:
        """The instructor session and the leadership session of one two-hat person.

        Criterion 2's known trap, planted as SPEC §2.1 describes it: "Two-hat
        people hold two assignments with two edges". Scope resolves by role
        assignment and never by identity, so her instructor session must be
        refused every route here while her leadership session is admitted —
        the same person, twice, differing only in which hat the session names.
        """
        user_id = self.web_identity.user(
            platform_id=self._platform_id(), subject=THE_TWO_HAT_SUBJECT
        )
        person_id = self.two_hat_person_id
        instructor = self.minted(
            role=INSTRUCTOR_ROLE,
            person_id=person_id,
            user_id=user_id,
            subject=THE_TWO_HAT_SUBJECT,
        )
        leadership = self.minted(
            role=LEADERSHIP_LANDING_ROLE,
            person_id=person_id,
            user_id=user_id,
            subject=THE_TWO_HAT_SUBJECT,
        )
        return instructor, leadership

    def a_student_session(self) -> str:
        """A minted `STUDENT` session naming a `user` row and no person.

        Minted rather than launched because a second launch would build a second
        world — `_build_report_door` seeds a whole term per call — and this
        session is a credential to be refused rather than a world to read. ADR
        0028 gives a student no person and no assignment, so naming a `user` and
        no person is what a real student session carries.
        """
        subject = f"e5-06-student-{uuid4()}"
        user_id = self.web_identity.user(platform_id=self._platform_id(), subject=subject)
        return self.minted(role=STUDENT_ROLE, person_id=None, user_id=user_id, subject=subject)

    def an_instructor_session(self) -> str:
        """A minted `INSTRUCTOR` session for a person who teaches a section of her own.

        A real instructor rather than an empty session: the refusal under test is
        by role, and a session naming nobody could be refused for having no
        person at all — which is a different fact and would leave the role gate
        unproven (`docs/MISTAKES.md` entry 3).
        """
        subject = f"e5-06-instructor-{uuid4()}"
        person_id = self.web_identity.person()
        user_id = self.web_identity.user(platform_id=self._platform_id(), subject=subject)
        self.web_identity.link_person_to_user(person_id=person_id, user_id=user_id)
        self.rows.graph.assign(
            INSTRUCTOR_ROLE, scope=self.rows.graph.fresh_scope("section"), person=person_id
        )
        self.rows.commit()
        return self.minted(
            role=INSTRUCTOR_ROLE, person_id=person_id, user_id=user_id, subject=subject
        )

    def a_leadership_session_for_the_launched_leader(self) -> str:
        """Her own session, re-minted — the control on the minting itself.

        `docs/MISTAKES.md` entry 35. Every refusal above is a minted token, and
        a minted token this application refuses for some reason of its own would
        turn all of them into refusals that say nothing about a role. This one
        carries the same three claims her launched session carries, so a 200 on
        it and a 200 on the launched one are the same statement about the same
        machinery.
        """
        claims = claims_in_session(self.door.token)
        subject = claims.get(SUBJECT_CLAIM)
        assert isinstance(subject, str) and subject, (
            f"The launched leadership session carries no `{SUBJECT_CLAIM}` — it carries "
            f"{sorted(claims)}, and E1-08 puts the verified subject on every session either door "
            "issues."
        )
        return self.minted(
            role=LEADERSHIP_LANDING_ROLE,
            person_id=self.leader_person_id,
            user_id=claims.get(USER_ID_CLAIM),
            subject=subject,
        )

    def _platform_id(self) -> Any:
        registration = self.door.driver.registration
        return registration.platform_row[
            single_primary_key(require_table(self.tables, "lti_platform"))
        ]

    # -- request bodies -------------------------------------------------------

    def a_write(self, **overrides: Any) -> dict[str, Any]:
        """A valid `SetWrite` body, with whatever the caller changed.

        The valid body is the twin every refusal in criterion 3 is paired
        against: each invalid write is this body with exactly one field
        replaced, so a refusal is attributable to that field and the accepted
        twin proves the write path works at all.
        """
        body: dict[str, Any] = {
            NAME_FIELD: f"E5-06 a set written over HTTP {uuid4()}",
            LENGTH_FIELD: DECLARED_LENGTH,
            LEVEL_FIELD: DECLARED_LEVEL,
            MEMBER_COURSE_IDS_FIELD: [
                str(self.course_id("first_member")),
                str(self.course_id("second_member")),
            ],
        }
        body.update(overrides)
        return body


def _course(world: Any, chain: dict[str, Any], which: str) -> Any:
    """One course under the world's own prefix, numbered so SPEC §8 derives its level."""
    return world.seed(
        COURSE_TABLE,
        chain,
        **{
            COURSE_NUMBER_COLUMN: COURSE_NUMBERS[which],
            COURSE_TITLE_COLUMN: COURSE_TITLES[which],
        },
    )


def _section(world: Any, chain: dict[str, Any], course: Any, letter: str, ordinal: str) -> Any:
    """One section of `course`, carrying `SEEDED_COHORTS`' own length and start date.

    The calendar is transcribed from the seed and written here rather than
    derived, the way `Fall2026.section_row` writes it and for the same reason:
    a length this file computed would be a value a test then reads back through
    a section count (`docs/MISTAKES.md` entry 30).
    """
    length_weeks, _first_term_week, start = SEEDED_COHORTS[letter]
    return world.seed(
        SECTION_TABLE,
        {**chain, COURSE_TABLE: course},
        **{
            SECTION_CODE_COLUMN: f"{letter}{ordinal}{COHORT_SECTION_MODALITY}",
            SECTION_LENGTH_COLUMN: length_weeks,
            SECTION_START_COLUMN: start,
            SECTION_END_COLUMN: start + timedelta(days=length_weeks * 7 - 1),
        },
    )


def _plant_set(
    world: NamedSetWorld,
    *,
    name: str,
    creator: Any,
    members: Sequence[Any],
) -> PlantedSet:
    """One `comparison_set` and its membership rows, written through the model layer.

    Planted rather than created over HTTP, deliberately: the scope tests are
    about what a session may do with a set that is **already there**, and a set
    created through the route under test would make every one of them rest on
    the create path being right as well.
    """
    seeded = world.world.seed(
        COMPARISON_SET_TABLE,
        {},
        **{
            NAME_COLUMN: name,
            LENGTH_COLUMN: DECLARED_LENGTH,
            LEVEL_COLUMN: DECLARED_LEVEL,
            world.creator_column(): creator,
        },
    )
    membership = membership_table(world.tables)
    for course in members:
        # `member_of` rather than a second seeding call: it passes both rows as
        # the walker's *chain*, so whatever columns the membership row carries to
        # hold E5-01's level agreement are filled from those two rows rather than
        # from a column name this file knows (`docs/MISTAKES.md` entry 13).
        member_of(world.world.seed, membership, seeded, course)
    key = single_primary_key(require_table(world.tables, COMPARISON_SET_TABLE))
    course_key = world.world.key_of(COURSE_TABLE)
    return PlantedSet(
        set_id=seeded[key],
        name=name,
        creator_person_id=creator,
        member_course_ids=tuple(course[course_key] for course in members),
    )


def build_named_set_world(
    door: ReportDoor,
    committed_rows: Any,
    tables: dict[str, Any],
    web_identity: Any,
    configured: Mapping[str, str],
) -> NamedSetWorld:
    """Seed the courses, the sections, the second leader, the two-hat person and the two sets.

    Every step is somebody's existing machinery: the launch and the leadership
    session are `tests/fixtures/report_api.py`'s, the containment chain is
    `Fall2026`'s, the assignments are E0-09's graph and the rows are committed
    because the tool connects for itself (ADR 0001).

    **The premise checks at the foot are this fixture's, deliberately.** They
    are claims about the rows written here — four distinct courses, five
    distinct sections, two sets with different creators, a person holding two
    assignments — and not about anything E5-06 owes, so a failure in them is a
    defect in this world rather than a red about a route
    (`docs/MISTAKES.md` entry 13). Without them a set whose creator silently
    failed to land would leave the scope assertions passing because *nobody*
    can edit it, which is a different fact from the one they claim to prove.
    """
    world = NamedSetWorld(door, committed_rows, tables, web_identity, configured)
    inner = world.world

    chain = dict(inner.calendar.chain)
    for level in (SECTION_TABLE, COURSE_TABLE):
        chain.pop(level, None)
    if PREFIX_TABLE not in chain or TERM_TABLE not in chain:
        pytest.fail(
            f"The world's containment chain holds {sorted(chain)}, and this needs the "
            f"`{PREFIX_TABLE}` and `{TERM_TABLE}` rows above it. Without the prefix every course "
            "here hangs off a fresh one, and the sections below them sit in a term whose weeks "
            "nothing wrote."
        )

    for which in COURSE_NUMBERS:
        world.courses[which] = _course(inner, chain, which)
    for which, letter, ordinal in PLANTED_SECTIONS:
        world.sections.append(_section(inner, chain, world.courses[which], letter, ordinal))

    world.another_leader_person_id = web_identity.person()
    committed_rows.graph.assign(LEADERSHIP_ROLE, person=world.another_leader_person_id)

    world.two_hat_person_id = web_identity.person()
    committed_rows.graph.assign(
        INSTRUCTOR_ROLE,
        scope=committed_rows.graph.fresh_scope("section"),
        person=world.two_hat_person_id,
    )
    committed_rows.graph.assign(LEADERSHIP_ROLE, person=world.two_hat_person_id)

    world.hers = _plant_set(
        world,
        name=HER_SET_NAME,
        creator=door.person_id,
        members=[world.courses["first_member"], world.courses["second_member"]],
    )
    world.theirs = _plant_set(
        world,
        name=THEIR_SET_NAME,
        creator=world.another_leader_person_id,
        members=[world.courses["outsider"]],
    )
    # Hers to write, by the ruling on `docs/disputes/E5-06-01.md`: the two-hat
    # person's leadership session needs a set of her own before "she is admitted
    # where her instructor session was refused" can be asked of `edit` and
    # `delete` without also asserting the opposite of decision 1.
    world.the_two_hats = _plant_set(
        world,
        name=TWO_HAT_SET_NAME,
        creator=world.two_hat_person_id,
        members=[world.courses["first_member"]],
    )
    committed_rows.commit()

    course_key = inner.key_of(COURSE_TABLE)
    section_key = inner.key_of(SECTION_TABLE)
    assert len({course[course_key] for course in world.courses.values()}) == len(COURSE_NUMBERS), (
        "The courses this world is built on are not four rows: "
        f"{[course[course_key] for course in world.courses.values()]}."
    )
    assert len({section[section_key] for section in world.sections}) == len(PLANTED_SECTIONS), (
        "The sections this world is built on are not five rows: "
        f"{[section[SECTION_CODE_COLUMN] for section in world.sections]}."
    )
    definers = [
        world.hers.creator_person_id,
        world.theirs.creator_person_id,
        world.the_two_hats.creator_person_id,
    ]
    assert door.person_id is not None and len({str(who) for who in definers}) == len(definers), (
        "The three planted sets do not have three different creators — the leadership session "
        f"names {door.person_id!r} and the sets were written for {definers}. Every scope assertion "
        "in this ticket is the difference between them: one set this session may write, one it may "
        "not, and one the two-hat leader may write through her leadership session alone."
    )
    held = committed_rows.graph.assignments_of(world.two_hat_person_id)
    assert len(held) == 2, (
        f"The two-hat person holds {len(held)} assignments; she is planted with two — an "
        "`INSTRUCTOR` row scoped to a section of her own and a `DEAN` row. With one of them "
        "missing, criterion 2's trap is a person with a single hat and the pair of sessions it "
        "asks for does not exist."
    )
    return world


# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------


@pytest.fixture
def named_set_world(
    report_door_as: Callable[..., ReportDoor],
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    web_identity: Any,
    configured_env: dict[str, str],
) -> NamedSetWorld:
    """The leadership session, the second leader's set, and the world a preview counts.

    `configured_env` is asked for here rather than in each module because the
    minted sessions are signed with the secret it lays down and the door
    underneath already rides it — asking for it twice is the same mapping, not a
    second environment (`docs/MISTAKES.md` entry 40).
    """
    door = report_door_as(LEADERSHIP_ROLE)
    return build_named_set_world(
        door, committed_rows, metadata_tables, web_identity, configured_env
    )


@pytest.fixture
def named_sets(named_set_world: NamedSetWorld) -> NamedSetDoor:
    """The seven routes, asked with exactly one credential each. See `NamedSetDoor`."""
    return NamedSetDoor(named_set_world.door, named_set_world)


@pytest.fixture
def named_set_contract() -> Any:
    """The names E5-06's work order settles, and the readers over them.

    Handed over as a fixture rather than imported, for the reason every fixtures
    module in this suite gives: importing a fixtures module by name depends on
    where pytest put `tests/` on `sys.path`, and an import error is not a red.
    """

    class NamedSetContract:
        api_module = LEADERSHIP_API_MODULE
        deps_module = DEPS_MODULE
        service_module = SERVICE_MODULE
        schema_module = SCHEMA_MODULE
        copy_package = COPY_PACKAGE
        require_leadership_name = REQUIRE_LEADERSHIP
        csrf_leadership_name = CSRF_VERIFIED_LEADERSHIP

        sets_path = SETS_PATH
        options_path = OPTIONS_PATH

        sets_member = SETS_MEMBER
        id_field = ID_FIELD
        name_field = NAME_FIELD
        length_field = LENGTH_FIELD
        level_field = LEVEL_FIELD
        member_count_field = MEMBER_COUNT_FIELD
        editable_field = EDITABLE_FIELD
        member_course_ids_field = MEMBER_COURSE_IDS_FIELD
        created_at_field = CREATED_AT_FIELD
        updated_at_field = UPDATED_AT_FIELD
        section_count_field = SECTION_COUNT_FIELD
        lengths_field = LENGTHS_FIELD
        levels_field = LEVELS_FIELD
        courses_field = COURSES_FIELD
        course_id_field = COURSE_ID_FIELD
        course_label_field = COURSE_LABEL_FIELD
        course_level_field = COURSE_LEVEL_FIELD
        preview_fields = PREVIEW_FIELDS
        set_write_fields = SET_WRITE_FIELDS

        list_ok = LIST_OK
        created = CREATED
        no_content = NO_CONTENT
        role_refused = ROLE_REFUSED
        not_the_definer = NOT_THE_DEFINER
        unknown_set = UNKNOWN_SET
        duplicate_name = DUPLICATE_NAME
        refused_value = REFUSED_VALUE
        cache_control_header = CACHE_CONTROL_HEADER
        no_store = NO_STORE
        authenticate_header = AUTHENTICATE_HEADER
        authenticate_scheme = AUTHENTICATE_SCHEME

        spec_lengths = SPEC_LENGTHS
        spec_levels = SPEC_LEVELS
        declared_length = DECLARED_LENGTH
        declared_level = DECLARED_LEVEL
        another_length = ANOTHER_LENGTH
        another_level = ANOTHER_LEVEL
        clock_instant = AFTER_THE_LAST_WINDOW
        clock_tolerance = CLOCK_TOLERANCE
        course_titles = COURSE_TITLES

        subject_claim = SUBJECT_CLAIM
        person_id_claim = PERSON_ID_CLAIM
        user_id_claim = USER_ID_CLAIM
        leadership_landing_role = LEADERSHIP_LANDING_ROLE

        refusal_constants = REFUSAL_CONSTANTS
        not_leadership = NOT_LEADERSHIP
        set_unavailable = SET_UNAVAILABLE
        not_the_sets_definer = NOT_THE_SETS_DEFINER
        name_already_used = NAME_ALREADY_USED
        length_not_a_calendar_length = LENGTH_NOT_A_CALENDAR_LENGTH
        level_not_a_course_level = LEVEL_NOT_A_COURSE_LEVEL
        member_not_at_the_sets_level = MEMBER_NOT_AT_THE_SETS_LEVEL
        member_not_a_course = MEMBER_NOT_A_COURSE

        api = staticmethod(leadership_api_module)
        service = staticmethod(comparison_sets_service)
        schema = staticmethod(comparison_sets_schema)
        dependency = staticmethod(leadership_dependency)
        sentence = staticmethod(refusal_sentence)
        write_model = staticmethod(set_write_model)
        detail_of = staticmethod(detail_of)
        body_of = staticmethod(body_of)
        set_path = staticmethod(set_path)
        preview_path = staticmethod(preview_path)
        every_object = staticmethod(every_object)
        strings_in = staticmethod(strings_in)
        claims_in_session = staticmethod(claims_in_session)
        course_labels = StudentReadWorld

    return NamedSetContract()
