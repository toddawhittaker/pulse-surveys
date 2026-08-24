"""The Care service's own check on the acting person — ticket E0-10.

E0-10 settles a design its first draft left contradictory, and the sentence is
the whole subject of this module:

> The `SECURITY DEFINER` function **takes the acting person as an argument and
> verifies a live `CARE` assignment itself**, and `services/safety.py` verifies
> independently before calling it. Neither alone; a caller reaching the function
> by any other route still gets nothing, and a routing mistake inside the service
> still gets nothing.

The function's half is asserted against the database, with no service anywhere in
the picture, in `test_identity_grants.py`. **This is the service's half**, and it
had no behavioural assertion in CI until now — which for a design whose whole
argument is "two conditions, both required" is one condition asserted and one
described.

**The two halves are told apart by the *type* of the refusal.** The service
raises `NotCareStaffError`; the function raises a database error. So a service
that skipped its own check and let the function's refusal surface fails the test
below with a different exception and a different message. The one case this
cannot separate is a service that catches the database error and re-raises
`NotCareStaffError` — the two checks then look identical from here, and the pull
request owes a sentence saying which it did (`docs/MISTAKES.md` entry 14: this is
the boundary of the search, not a proof).

**Why this module needs machinery no other database test needs.** ADR 0001 binds
the Care pool to the service module rather than to the actor, so
`app.services.safety` opens its own connection from `CARE_DATABASE_URL` — and it
therefore cannot see a single row written inside `db_session`'s transaction. The
rows have to be committed, which is `committed_rows` in
`tests/fixtures/authz_data.py`, and
the environment has to point at this container, which is
`care_service_environment` beside it. Both undo themselves: the teardown removes
whatever *appeared*, including the audit row the service writes on its own
connection, which nothing on this side could have tracked by key.

**Nothing here reaches for a private name.** `_care_engine`, `_care_sessions` and
`_care_session` are private because a caller may never choose its own pool, and a
test that imported one to make itself easier would be asserting the opposite of
the rule it is here to check. The public surface — `reveal_identity`,
`NotCareStaffError`, `RevealedIdentity` — is the whole interface this module uses,
and `tests/unit/test_care_session_is_bound_to_the_care_service.py` is what holds
the line between the two.
"""

import inspect
from typing import Any, NamedTuple

import pytest

pytestmark = pytest.mark.integration

# SPEC §13 gives `services/safety.py` the Care queue and E0-10 names it again —
# "Do not add a module for this" — so this is the ticket's choice of module, not
# this file's. The three names are its public surface.
CARE_SERVICE_MODULE = "app.services.safety"
REVEAL = "reveal_identity"
NOT_CARE_STAFF_ERROR = "NotCareStaffError"

# Which value fills which parameter of `reveal_identity`, matched against a
# fragment of the parameter's name. **This used to be a copy of
# `REVEAL_ARGUMENT_ROLES` in `tests/integration/test_identity_grants.py`, and it is
# now the only one of the pair.** That module bound the SQL function's arguments
# this way because E0-10 spelled no signature; E0-26 item 1 settles both halves of
# the door in the ticket, so the guessing there is gone and the calls are written
# out. This copy stays because the question it asks is still open: E0-26 leaves
# `reveal_identity` in `services/safety.py` with its own signature — "it keeps its
# signature and stays one call" — and no ticket has written that signature down.
# Order matters: `care_person_id` is the actor, `student_user_id` is the subject,
# and a bare `person` is read as the actor only after both.
REVEAL_PARAMETER_ROLES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("session", "connection", "db"), "session"),
    (("case",), "case"),
    (("note", "reason", "justification", "disposition"), "note"),
    (("actor", "care", "staff", "revealer", "requester", "requested_by"), "actor"),
    (("user", "subject", "student", "sub", "identity"), "subject"),
    (("person",), "actor"),
)

REVEAL_NOTE = "E0-10 proof of mechanism"

# Where a `user` row keeps the LMS subject, if the reveal names its student that
# way rather than by key. This was a copy of `LMS_USER_ID_COLUMNS` in
# `test_identity_grants.py`, which went with the argument-guessing there when
# E0-26 item 1 settled `record_identity_reveal(… in_subject_user_id uuid …)` on the
# key; the service's own signature is still unwritten, so the question survives
# here. SPEC §4 keys responses to "the LMS user ID (`sub`
# from the launch)". A prefix match on `lms` alone would not do: `user` also
# carries the platform reference, and revealing "the student whose id is that
# platform" is a call that would succeed and mean nothing.
LMS_USER_ID_COLUMNS = ("lms_user_id", "lms_sub", "lms_subject", "lms_id", "sub")


class Revealable(NamedTuple):
    """One student to reveal, and two people who might ask."""

    subject_user_id: Any
    subject_lms_id: Any
    identity_values: set[str]
    care_person: Any
    reporting_person: Any


def role_of(parameter: str) -> str | None:
    """Which value a parameter called `parameter` wants, or `None` if this cannot tell."""
    lowered = parameter.lower()
    for fragments, role in REVEAL_PARAMETER_ROLES:
        if any(fragment in lowered for fragment in fragments):
            return role
    return None


def value_for(role: str, parameter: inspect.Parameter, revealable: Revealable, actor: Any) -> Any:
    """The value this test offers for one parameter, chosen by role and by annotation."""
    if role == "case":
        # There is no case model until E10 — E0-10 ships "a minimal proof of
        # mechanism" — so a case identifier can only be absent here.
        return None
    if role == "note":
        return REVEAL_NOTE
    if role == "actor":
        return actor
    annotation = str(parameter.annotation).lower()
    if "str" in annotation and "uuid" not in annotation:
        return revealable.subject_lms_id
    return revealable.subject_user_id


def bind(function: Any, revealable: Revealable, *, actor: Any) -> dict[str, Any]:
    """The keyword arguments `function` needs, filled from what this test has seeded.

    Bound by parameter *name* rather than by position, and never by trying call
    shapes until one stops raising: a `TypeError` swallowed that way could have
    come from inside the service, and the test would report a design the ticket
    never chose as working (`docs/MISTAKES.md` entry 3 — `SectionCodeService.call`
    in `tests/fixtures/section_codes.py` refuses the same shortcut for the same
    reason).

    A parameter this cannot fill stops the test with a message naming it. E0-10
    spells `reveal_identity` and neither its signature nor its argument order, so
    guessing would settle an interface the ticket leaves to the implementer.
    """
    parameters = list(inspect.signature(function).parameters.values())
    arguments: dict[str, Any] = {}
    for parameter in parameters:
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        role = role_of(parameter.name)
        if role == "session":
            pytest.fail(
                f"`{REVEAL}` takes a parameter `{parameter.name}` that reads as a database "
                "session, and this test cannot supply one. The Care session is deliberately "
                "private — E0-10: 'A caller can never choose its own pool, and no general-purpose "
                "helper hands out a `pulse_care` session' — so a caller that has to pass one in "
                "is the pool bound to the caller after all. If the parameter is there for a "
                "different reason, that is an interface question for the ticket rather than "
                "something to fill in here."
            )
        if role is None:
            if parameter.default is not parameter.empty:
                continue
            pytest.fail(
                f"`{REVEAL}` requires a parameter `{parameter.name}` that this test has nothing to "
                "fill from. It can supply the user whose identity is being revealed, the person "
                "acting, a null case id — there is no case model until E10 — and a short note. A "
                "parameter outside that set is an interface question for the ticket: say what it "
                "is for in the pull request and add it to `REVEAL_PARAMETER_ROLES` in this file."
            )
        arguments[parameter.name] = value_for(role, parameter, revealable, actor)

    positional_only = [
        parameter.name for parameter in parameters if parameter.kind is parameter.POSITIONAL_ONLY
    ]
    assert not positional_only, (
        f"`{REVEAL}` declares {positional_only} positional-only, so this test cannot bind them by "
        "name — and binding by position would be this file deciding which of the two people goes "
        "first, which is the one thing that must not be guessed: the arguments are 'a student' and "
        "'the staff member asking about them', and swapping them is a reveal that succeeds and "
        "audits the wrong person."
    )
    return arguments


def identity_values(result: Any) -> set[str]:
    """Every string the reveal handed back, however `RevealedIdentity` carries them.

    A dataclass, a Pydantic model and a `NamedTuple` all answer to one of these,
    and E0-10 names the type without saying which it is.
    """
    if hasattr(result, "_asdict"):
        carried = dict(result._asdict())
    elif isinstance(result, dict):
        carried = dict(result)
    elif getattr(result, "__dict__", None):
        carried = dict(result.__dict__)
    else:
        # A class with `__slots__` carries no `__dict__`, and `vars()` raises on
        # one rather than answering empty — so the last resort reads the
        # attributes off the object itself.
        carried = {
            name: getattr(result, name, None) for name in dir(result) if not name.startswith("_")
        }
    return {value for value in carried.values() if isinstance(value, str) and value}


@pytest.fixture
def care_service(care_service_environment: dict[str, str], import_app_module: Any) -> Any:
    """`app.services.safety`, imported against this container's Care connection."""
    module = import_app_module(CARE_SERVICE_MODULE)
    assert module is not None, (
        f"There is no `{CARE_SERVICE_MODULE}` module. E0-10 names it — 'The Care service module "
        "is `backend/app/services/safety.py`, which SPEC §13 already names for the Care queue. Do "
        "not add a module for this.' — and it is where the second connection pool and the actor's "
        "assignment check both live."
    )
    for name in (REVEAL, NOT_CARE_STAFF_ERROR):
        assert hasattr(module, name), (
            f"`{CARE_SERVICE_MODULE}` exposes no `{name}`; it exposes "
            f"{sorted(n for n in vars(module) if not n.startswith('_'))}. The Care path is a "
            "requirement of this ticket rather than an oversight (§4, §6.2), and its refusal has "
            "to be a named error rather than whatever the database raised — that is what tells "
            "the service's own check apart from the function's."
        )

    refusal = getattr(module, NOT_CARE_STAFF_ERROR)
    assert isinstance(refusal, type) and issubclass(refusal, BaseException), (
        f"`{CARE_SERVICE_MODULE}.{NOT_CARE_STAFF_ERROR}` is {refusal!r}, which is not an exception "
        "class. The refusal test below catches it by type, and a name that is not raisable would "
        "stop that test inside `pytest.raises` rather than at an assertion."
    )
    return module


@pytest.fixture
def revealable(committed_rows: Any) -> Revealable:
    """A student with an identity, a Care staffer, and a lead who is not one.

    Committed, because the service reads on its own connection and would
    otherwise be asked to reveal a student that, from where it is standing, does
    not exist.

    The Care staffer is E0-09's two-hat person — a `CARE` assignment and a
    teaching assignment on one person, which §2.1 permits and §6.2 spends a
    paragraph on — so the positive case below is the awkward one rather than the
    easy one.
    """
    graph = committed_rows.graph
    hats = graph.care_and_instructor_person()
    chain: dict[str, Any] = {}
    identity = committed_rows.seed("user_identity", chain)
    committed_rows.commit()

    user = chain.get("user")
    assert user is not None, (
        "Seeding `user_identity` did not seed a `user` with it, so there is no student to ask "
        "about. ADR 0001 splits the key onto `user` and the name and email onto `user_identity`, "
        "one row per user, which makes the link a NOT NULL foreign key the seeding helper follows."
    )

    values = {
        value
        for key, value in identity.items()
        if isinstance(value, str) and value and not key.endswith("_id")
    }
    assert values, (
        f"The seeded `user_identity` row carries no non-key string value: {dict(identity)}. There "
        "is then nothing for a reveal to return that could be recognised, and the test below would "
        "assert that a call returned something rather than that it returned the identity."
    )

    key = next((name for name in user if name in {"id", "user_id"}), None)
    assert key is not None, (
        f"The seeded `user` row has columns {list(user.keys())} and none reads as its primary key. "
        "ADR 0016 makes every primary key one server-generated uuid."
    )
    lms = next((name for name in LMS_USER_ID_COLUMNS if name in user), None)
    return Revealable(
        subject_user_id=user[key],
        subject_lms_id=user[lms] if lms else None,
        identity_values=values,
        care_person=hats["person"],
        reporting_person=hats["lead"][graph.person_column],
    )


@pytest.mark.invariant
def test_the_care_service_reveals_identity_to_a_person_holding_a_care_assignment(
    care_service: Any, revealable: Revealable
) -> None:
    """The door is open through the service, for the person §6.2 opens it for.

    **Marked `invariant` by E0-41.** SPEC §4 makes `reveal_identity` the single
    application-code path to a student's name — "re-identification is possible
    only through the Care queue (§6.2), only by the Care role" — and the isolated
    §4.1 pass ran none of it. This half is in that pass because the refusal beside
    it is worth nothing without it: a service that raised `NotCareStaffError` for
    everybody, or one that could not reach its own connection, satisfies the
    refusal perfectly, and inside the isolated pass the control would not even
    have been collected.

    This is the positive half of the pair, and it is a criterion in its own right
    — "the Care path must remain open, and this ticket proves it" — as well as
    the control that makes the refusal next door mean something. Without it, a
    service that could not reach the database at all, or that raised
    `NotCareStaffError` for everybody, would pass the refusal test perfectly.

    The returned object is compared against the identity that was seeded rather
    than merely being non-empty: a reveal that returns a row of nulls, or the
    user's key back, satisfies "it returned something" and reveals nobody.

    **The person here holds two hats**, a `CARE` assignment and a teaching one.
    §2.1 permits it and §6.2 expects it, and it is the case where "pick the pool
    from the actor's role" has no answer — so the service has to say yes to them
    *for their Care assignment* while every reporting path they touch stays on
    `pulse_app`.
    """
    reveal = getattr(care_service, REVEAL)
    arguments = bind(reveal, revealable, actor=revealable.care_person)

    result = reveal(**arguments)

    assert identity_values(result) & revealable.identity_values, (
        f"`{REVEAL}` returned {result!r} for a person holding a live `CARE` assignment, and the "
        f"student it was asked about carries {sorted(revealable.identity_values)}. E0-10 ships "
        "this as the proof that Care re-identification works before E10 replaces the stub — 'so "
        "that E10 inherits a door rather than a wall'. A reveal that returns no identity is a wall "
        "with a handle painted on it.\n\n"
        f"The arguments this test bound were {arguments}. If the subject is meant to arrive as the "
        "LMS subject rather than as the `user` key, that is the one thing `value_for` in this file "
        "guesses at — it reads the annotation and falls back to the key — and the pull request "
        "naming the signature is what settles it."
    )


@pytest.mark.invariant
def test_the_care_service_refuses_a_person_with_no_live_care_assignment(
    care_service: Any, revealable: Revealable
) -> None:
    """The service's own check, which has to hold when the routing is wrong.

    **Marked `invariant` by E0-41**: this is §4's "identity is never displayed to
    instructors or any leadership role" at the one door that can display it, and
    the `holds_care` pre-check is the whole of the service's half. Unmarked, it
    could be skipped without the isolated pass noticing.

    E0-10: "`services/safety.py` verifies independently before calling it…
    Neither alone; a caller reaching the function by any other route still gets
    nothing, and a routing mistake inside the service still gets nothing." This
    is the second clause. The actor is a real person in the same graph holding a
    lead-faculty assignment and no Care assignment — the shape of a routing
    mistake, where the Care code path is reached on behalf of somebody who should
    never have been sent there.

    **The control runs first, in this test, with the same call.** The same
    arguments and the same service, differing only in which person is acting, so
    the refusal is attributable to the assignment rather than to a service that
    cannot reach the database, a wrong binding, or a fixture that seeded nothing.
    That is the same discipline the grants module uses for every denial it
    asserts.

    **The exception type is the assertion**, and nothing follows the `raises`
    block on purpose: `refused.value is not None` is the obvious next line and it
    cannot fail, which is `docs/MISTAKES.md` entry 3 in the shape that reads as
    thoroughness. What the refusal *carries* is a different question and a real
    one, and it is asserted next door in
    `test_the_refusal_carries_no_part_of_the_students_identity` rather than being
    tacked on here. `NotCareStaffError` is the service's own refusal; the function's
    refusal is a database error. A service that skipped its check and let the
    function speak fails here, and fails saying what it raised instead — which is
    the whole reason the ticket asks for the two halves to be asserted separately,
    since where both can refuse a behavioural test cannot say which one did.
    """
    reveal = getattr(care_service, REVEAL)
    refusal_type = getattr(care_service, NOT_CARE_STAFF_ERROR)

    allowed = reveal(**bind(reveal, revealable, actor=revealable.care_person))
    assert identity_values(allowed) & revealable.identity_values, (
        "The control call failed: a person holding a live `CARE` assignment did not get the "
        "seeded identity back, so the refusal below would say nothing about the assignment. "
        "`test_the_care_service_reveals_identity_to_a_person_holding_a_care_assignment` is where "
        "that is diagnosed."
    )

    arguments = bind(reveal, revealable, actor=revealable.reporting_person)
    with pytest.raises(refusal_type):
        reveal(**arguments)


def raised_surface(failure: BaseException) -> str:
    """Everything a caller can read off a refusal: its text, its arguments, its chain.

    The chain matters as much as the message. A service that let the database's
    own error become the `__cause__` of its refusal hands the caller whatever that
    error quoted — and a Postgres error quotes the row it was raised about — so a
    scan of `str(failure)` alone would report a clean refusal over a leaked name.
    """
    seen: list[str] = []
    current: BaseException | None = failure
    while current is not None and len(seen) < 10:
        seen.append(f"{type(current).__name__}: {current!s} {current.args!r}")
        current = current.__cause__ or current.__context__
    return "\n".join(seen)


@pytest.mark.invariant
def test_the_refusal_carries_no_part_of_the_students_identity(
    care_service: Any, revealable: Revealable
) -> None:
    """A refusal that quotes the student has revealed them while saying no — E0-41.

    SPEC §4: identity "is never displayed to instructors or any leadership role,
    in any view", and §6.2 keeps re-identification to the Care role "only via the
    audited reveal action". A `NotCareStaffError` that reads "Alex Rivera may not
    be revealed to …" has performed the reveal on the error path, where nothing is
    audited: §4's traceability record is written by the reveal, and this call did
    not get that far.

    **The mutation this kills:** a refusal built from the row the service had
    already fetched — the natural shape when a service reads the subject first and
    checks the actor second, and equally the shape of a service that lets the
    database error surface as its `__cause__`.

    **Why this is not an assertion about emptiness.** The denial itself is
    asserted next door and is what makes this meaningful; here the seeded identity
    is known, the control call proves the reveal really can produce it, and the
    scan is shown finding those very strings in a sample built from them. Without
    those three, "the message did not contain a name" would be equally true of a
    service that never ran (`docs/MISTAKES.md` entry 3).
    """
    reveal = getattr(care_service, REVEAL)
    refusal_type = getattr(care_service, NOT_CARE_STAFF_ERROR)

    allowed = reveal(**bind(reveal, revealable, actor=revealable.care_person))
    assert identity_values(allowed) & revealable.identity_values, (
        "The control call failed: a person holding a live `CARE` assignment did not get the "
        "seeded identity back, so this test does not yet know that the values it is scanning for "
        "are ones this door can produce at all."
    )
    canary = " ".join(sorted(revealable.identity_values))
    assert all(value in canary for value in revealable.identity_values), (
        "The scan below cannot find the seeded identity in a sample built out of it, so its "
        "silence about the refusal means nothing."
    )

    with pytest.raises(refusal_type) as refused:
        reveal(**bind(reveal, revealable, actor=revealable.reporting_person))

    surface = raised_surface(refused.value)
    leaked = sorted({value for value in revealable.identity_values if value in surface})
    assert not leaked, (
        f"The refusal handed back to a person with no `CARE` assignment carries {leaked}, which is "
        f"the identity it refused to reveal. What it carries:\n{surface}\n\n"
        "§6.2 gives identity access to the Care role and to no other, through the audited reveal "
        "and no other route — and this path writes no audit record, because the check that "
        "produced this error is what stops the reveal happening. A refusal that quotes the student "
        "has revealed them to exactly the person the check exists to refuse."
    )
