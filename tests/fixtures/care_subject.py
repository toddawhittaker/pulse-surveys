"""E4-01 — the record a Care reveal derives its subject from, and who may ask.

Two modules need the same three things and neither may own them
(`docs/MISTAKES.md` entry 13, one helper reached from both places):
`tests/integration/test_care_service_reveal.py`, which is E0-10's service-side
door moved onto E4-01's signature, and
`tests/integration/test_the_reveal_derives_its_subject.py`, which is E4-01's own
subject.

**What is planted, and why through the model layer.** E4-01's guard derives the
student from the comment Care is acting on — `answer_id` → `answer.response_id`
→ `response.user_id` — and no production path writes a threat or self-harm
classification today, because the moderation task is E6's. The ticket says so in
its own trap section and says what to do about it: plant the rows the way the
§4.1 suite already plants them, through `seed_row`, and do not invent a dev route
to write them. So `plant_a_comment_answer` seeds a student, a section and week of
one term, that student's response, and one comment answer on it — and commits,
because `app.services.safety` opens its own `pulse_care` connection and sees
nothing written inside another transaction (ADR 0001).

**No classification row is planted, and that is deliberate rather than an
omission.** The work order settles that the threat-set predicate waits for E6:
the guard this ticket builds is subject-from-record, not subject-from-verdict, so
a fixture that planted a verdict would be encoding a decision the ticket
explicitly defers — and the day E6 lands, a fixture holding a made-up verdict
vocabulary is the thing nobody updates.

**Nothing here asserts a deliverable.** `require_the_reveal_interface` is a plain
helper a test calls as its **first statement**, never a fixture, because a guard
that raises in a fixture turns a tests-first module's reds into setup errors —
`docs/MISTAKES.md` entry 44, which is exactly the shape this ticket would
otherwise take: `UnknownRevealSubjectError` does not exist until the
implementation lands, and a wall of ERRORs reads to a hurried eye as a broken
suite rather than as a criterion nobody has met yet.

**One thing this module cannot do anything about, and every caller should know
it.** `pulse_care` holds `SELECT` on exactly one base table — `role_assignment`
— and on no view at all (`RUNTIME_BASE_TABLE_PRIVILEGES` in
`tests/integration/test_identity_grants.py`, asserted there as an equality in
both directions). The derivation runs on that connection and reaches `answer` and
`response` through the door's third `SECURITY DEFINER` function,
`reveal_subject_for_answer` — ruled at build time, recorded in ADR 0144, and
listed in `THE_CARE_DOOR` in the grants module beside the other two. Until it
exists, every legitimate-path test here fails on that rather than on the guard.
**The Care role's own privileges do not move**, and nothing here is licence to
seed differently or to read on another connection to make a test pass.
"""

import inspect
from typing import Any, NamedTuple
from uuid import uuid4

import pytest

# SPEC §13 gives `services/safety.py` the Care queue and every ticket since E0-10
# has named it again; these four names are the module's public surface after
# E4-01, and the fourth is the one this ticket adds.
CARE_SERVICE_MODULE = "app.services.safety"
REVEAL = "reveal_identity"
NOT_CARE_STAFF_ERROR = "NotCareStaffError"
UNKNOWN_SUBJECT_ERROR = "UnknownRevealSubjectError"
REVEALED_IDENTITY = "RevealedIdentity"

# The signature E4-01's work order settles, written out rather than discovered.
# E0-10 spelled no signature, so `test_care_service_reveal.py` used to bind by
# matching parameter names against fragments; this ticket spells all three
# parameters and deletes the fourth, so the guessing goes the way E0-26 item 1's
# went — "the shape, settled before any test was written".
ACTOR_PARAMETER = "actor_person_id"
ANSWER_PARAMETER = "answer_id"
CASE_PARAMETER = "case_id"
REVEAL_PARAMETERS = (ACTOR_PARAMETER, ANSWER_PARAMETER, CASE_PARAMETER)

# The parameter this ticket deletes. Named here because three modules ask about
# it — the signature tests, the vocabulary test, and the static sweep over
# `backend/` — and a fourth spelling of it would be a fourth thing to keep in
# step.
DELETED_SUBJECT_PARAMETER = "subject_user_id"

# SPEC §8's table and the four columns §4 requires of a re-identification record:
# "actor, timestamp, and case", plus the subject the reveal was about. The names
# are the ones `tests/integration/test_identity_column_marker.py` records
# `audit_log` as carrying, which is a record of the schema rather than a guess at
# it.
AUDIT_TABLE = "audit_log"
AUDIT_ACTOR_COLUMN = "actor_person_id"
AUDIT_SUBJECT_COLUMN = "subject_user_id"
AUDIT_CASE_COLUMN = "case_id"
AUDIT_TIMESTAMP_COLUMN = "occurred_at"
AUDIT_COLUMNS = (
    AUDIT_ACTOR_COLUMN,
    AUDIT_SUBJECT_COLUMN,
    AUDIT_CASE_COLUMN,
    AUDIT_TIMESTAMP_COLUMN,
)


def a_name() -> str:
    """One name belonging to exactly one seeded student.

    Unique per call, and stated here rather than left to `seed_row`: E1-11's D7
    made `user_identity.identity_name` nullable, so the seeding helper correctly
    leaves it null and a test comparing a reveal's answer against it would be
    comparing `None` with `None` (`docs/MISTAKES.md` entry 3, and dispute
    E1-11-02 for the occasion).
    """
    return f"E4-01 Student {uuid4().hex[:12]}"


def an_address() -> str:
    """One address belonging to exactly one seeded student, for the same reason."""
    return f"e4-01-{uuid4().hex[:12]}@example.invalid"


def a_comment() -> str:
    """One comment belonging to exactly one seeded answer.

    Unique per call so that a test which plants two answers cannot pass by
    reaching the wrong one: the comment text is what tells them apart in a
    failure message.
    """
    return f"e4-01 comment {uuid4().hex[:12]}"


def identity_values(result: Any) -> set[str]:
    """Every string a reveal handed back, however `RevealedIdentity` carries them.

    A dataclass, a Pydantic model and a `NamedTuple` all answer to one of these,
    and no ticket says which of the three it is — so this reads the object rather
    than deciding its shape. Moved here from
    `tests/integration/test_care_service_reveal.py` when a second module needed
    it (`docs/MISTAKES.md` entry 13).
    """
    if hasattr(result, "_asdict"):
        carried = dict(result._asdict())
    elif isinstance(result, dict):
        carried = dict(result)
    elif getattr(result, "__dict__", None):
        carried = dict(result.__dict__)
    else:
        # A class with `__slots__` carries no `__dict__`, and `vars()` raises on
        # one rather than answering empty.
        carried = {
            name: getattr(result, name, None) for name in dir(result) if not name.startswith("_")
        }
    return {value for value in carried.values() if isinstance(value, str) and value}


def require_the_reveal_interface(module: Any) -> None:
    """Stop with a named missing deliverable unless E4-01's surface is there.

    **Called as a test's first statement and never from a fixture**, which is
    `docs/MISTAKES.md` entry 44: a guard that raises in a fixture turns every red
    in the module into a setup ERROR, which proves nothing about the assertion the
    test exists to make and survives the implementation landing.

    Two things are required and they fail with different messages. The three
    public names are E0-10's surface plus the one E4-01 adds; the `answer_id`
    parameter is the whole of what this ticket changes, and asserting it here
    means a test written against the new call reports "the parameter is not there
    yet" rather than an uncaught `TypeError` from a call the implementation cannot
    yet accept.

    What it deliberately does **not** assert is the *whole* signature — that the
    subject parameter is gone, that the three parameters are keyword-only, that
    nothing else names a student. Those are criteria with tests of their own, and
    a guard that checked them would supply the value those tests measure
    (`docs/MISTAKES.md` entry 30).
    """
    for name in (REVEAL, NOT_CARE_STAFF_ERROR, UNKNOWN_SUBJECT_ERROR, REVEALED_IDENTITY):
        assert hasattr(module, name), (
            f"`{CARE_SERVICE_MODULE}` exposes no `{name}`; it exposes "
            f"{sorted(n for n in vars(module) if not n.startswith('_'))}.\n\n"
            f"`{UNKNOWN_SUBJECT_ERROR}` is E4-01's: the ticket requires the subject-derivation "
            "refusal to be 'its own distinguishable error, so E10's queue can tell \"not Care\" "
            "from \"not a legitimate subject\" without string-matching', and the work order puts "
            f"it in `safety.py` beside `{NOT_CARE_STAFF_ERROR}`. The other three are E0-10's "
            "surface and predate this ticket."
        )

    for name in (NOT_CARE_STAFF_ERROR, UNKNOWN_SUBJECT_ERROR):
        refusal = getattr(module, name)
        assert isinstance(refusal, type) and issubclass(refusal, BaseException), (
            f"`{CARE_SERVICE_MODULE}.{name}` is {refusal!r}, which is not an exception class. The "
            "tests below catch it by type, and a name that is not raisable would stop them inside "
            "`pytest.raises` rather than at an assertion."
        )

    parameters = inspect.signature(getattr(module, REVEAL)).parameters
    assert ANSWER_PARAMETER in parameters, (
        f"`{REVEAL}` takes no `{ANSWER_PARAMETER}` parameter — it takes {list(parameters)}. E4-01 "
        "derives the subject server-side from the record Care is acting on: the identifier of a "
        "comment, whose author is the student. Until the parameter exists there is no call to "
        "make, and every test in this module is about what happens when it is made."
    )


class PlantedAnswer(NamedTuple):
    """One comment, its author, and what a reveal of that author should return."""

    answer_id: Any
    author_user_id: Any
    identity_name: str | None
    identity_email: str | None
    identity_values: frozenset[str]
    comment_text: str
    section_id: Any
    response_id: Any


def key_of(committed_rows: Any, table_name: str, row: Any) -> Any:
    """One row's primary key, read from the metadata rather than spelled.

    ADR 0016 makes every primary key a single server-generated uuid, so there is
    exactly one column to read and this never has to choose between two.
    """
    table = committed_rows.tables.get(table_name)
    assert table is not None, (
        f"There is no `{table_name}` table in `Base.metadata` — it holds "
        f"{sorted(committed_rows.tables)}. SPEC §8 lists it."
    )
    return row[next(iter(table.primary_key.columns)).name]


def plant_a_comment_answer(committed_rows: Any, *, with_identity: bool = True) -> PlantedAnswer:
    """A student, their response in one term's section and week, and one comment on it.

    Committed, because the reveal reads on a connection of its own and would
    otherwise be asked about a comment that, from where it is standing, does not
    exist.

    **The chain is what makes the rows agree.** `seed_row` builds an ancestor only
    when the chain does not already hold one, so seeding the identity first puts
    *that* student on the response; and seeding the section before the week puts
    both in one term, which `response`'s composite keys into `section (id,
    term_id)` and `week (id, term_id)` require. The recipe is
    `tests/integration/test_the_survey_schema_survives_a_downgrade.py`'s, which is
    the module that first had to seed this shape.

    **`comment_text` is passed explicitly** because `answer` requires exactly one
    of its three value columns to be non-null and the seeding walker leaves
    nullable columns alone — a row it composed on its own is refused inside the
    fixture (`docs/MISTAKES.md` entry 13's closing sentence).

    `with_identity=False` is the third student
    `tests/integration/test_the_reveal_commits_its_record.py` names: a `user` with
    no `user_identity` row at all, for whom the reveal answers `None` rather than
    raising.
    """
    chain: dict[str, Any] = {}
    name: str | None = None
    address: str | None = None
    if with_identity:
        name, address = a_name(), an_address()
        identity = committed_rows.seed(
            "user_identity", chain, identity_name=name, identity_email=address
        )
        assert identity.get("identity_name") == name, (
            f"The seeded `user_identity` row does not carry the name this helper asked it to "
            f"({name!r}): {dict(identity)}. Every assertion built on it would then be comparing a "
            "reveal's answer against a value the database never stored."
        )
    else:
        committed_rows.seed("user", chain)

    user = chain.get("user")
    assert user is not None, (
        "Seeding did not produce a `user` row, so there is no author for the planted comment. "
        "ADR 0001 splits the key onto `user` and the name and address onto `user_identity`, one "
        "row per user, which makes the link a NOT NULL foreign key the seeding helper follows."
    )
    author = key_of(committed_rows, "user", user)

    section = committed_rows.seed("section", chain)
    week = committed_rows.seed("week", chain)
    response_columns = committed_rows.tables["response"].c
    response_values: dict[str, Any] = {
        "user_id": author,
        "section_id": key_of(committed_rows, "section", section),
        "week_id": key_of(committed_rows, "week", week),
    }
    if "term_id" in response_columns:
        response_values["term_id"] = key_of(committed_rows, "term", chain["term"])
    response = committed_rows.seed("response", chain, **response_values)

    comment = a_comment()
    answer = committed_rows.seed(
        "answer",
        chain,
        response_id=key_of(committed_rows, "response", response),
        comment_text=comment,
    )
    committed_rows.commit()

    assert response["user_id"] == author, (
        f"The planted response names {response['user_id']} as its author and the seeded student is "
        f"{author}. The whole derivation under test is `answer_id` → `answer.response_id` → "
        "`response.user_id`, so a response belonging to somebody else would make every assertion "
        "below true of the wrong student."
    )

    values = {value for value in (name, address) if value}
    return PlantedAnswer(
        answer_id=key_of(committed_rows, "answer", answer),
        author_user_id=author,
        identity_name=name,
        identity_email=address,
        identity_values=frozenset(values),
        comment_text=comment,
        section_id=key_of(committed_rows, "section", section),
        response_id=key_of(committed_rows, "response", response),
    )


class TwoHatActor(NamedTuple):
    """§2.1's permitted overlap: one person, a Care hat and a teaching hat."""

    person: Any
    care_assignment_id: Any
    taught_section_id: Any
    reporting_person: Any


def the_two_hat_actor(committed_rows: Any) -> TwoHatActor:
    """E0-09's two-hat person, plus the section she teaches and a lead who is not her.

    §2.1 permits a Care officer who also teaches and §6.2 spends a paragraph on
    her; the carried entry this ticket closes is about exactly her, so the
    composition tests use her rather than a Care-only actor. The section her
    `INSTRUCTOR` assignment is scoped to is what makes a roster row hers: it is
    the node `section_roster` would hand her every enrolled student's `user_id`
    from.

    `reporting_person` is the lead faculty in the same graph, who holds no `CARE`
    assignment. Every refusal attributed to the actor check is driven with them.
    """
    graph = committed_rows.graph
    hats = graph.care_and_instructor_person()
    reporting_person = hats["lead"][graph.person_column]
    committed_rows.commit()

    assert reporting_person != hats["person"], (
        "The graph fixture handed back one person for both the Care actor and the lead-faculty "
        "actor, so a refusal driven with the second would be the same call as the control and "
        "would prove nothing."
    )
    return TwoHatActor(
        person=hats["person"],
        care_assignment_id=hats["care"][graph.assignment_key],
        taught_section_id=graph.scope("section"),
        reporting_person=reporting_person,
    )


def a_user_id_from_the_roster_of(committed_rows: Any, section_id: Any) -> Any:
    """One enrolled student's `user_id` in `section_id`, committed.

    This is the value the carried entry is about: `section_roster` hands
    instructor-scoped code the `user_id` of every enrolled student — "that is the
    whole point of the view, and the key is what makes a de-identified response
    addressable" — and the finding is that the same key used to be exactly what
    the reveal took as its subject.

    Seeded through `enrollment` rather than read out of the view, because what the
    test needs is a real key in her section and the view is E4-11's surface. The
    row is what the view would be reading either way.
    """
    enrollment = committed_rows.seed("enrollment", {}, section_id=section_id)
    committed_rows.commit()
    assert enrollment["section_id"] == section_id, (
        f"The seeded enrollment names section {enrollment['section_id']} rather than "
        f"{section_id}. The user id below would then be a student in somebody else's section, and "
        "the composition this test is about — her own roster — would not be the thing being "
        "tested."
    )
    return enrollment["user_id"]


def audit_rows_for(migrated_engine: Any, committed_rows: Any, actor_person_id: Any) -> list[Any]:
    """Every `audit_log` row naming `actor_person_id`, read on a connection of its own.

    **A fresh connection, and rows filtered by actor rather than counted whole.**
    Fresh because the service commits on its own `pulse_care` connection and a
    snapshot taken before it ran would answer for a database that had not yet
    been written to — the "second connection" E0-26's done-when requires, and
    `docs/MISTAKES.md` entry 3's reason. Filtered by actor because "no row was
    written" has to be a statement about *this* call: a total over the table is a
    statement about whatever else the suite has left lying around.

    The bootstrap identity rather than `pulse_care`, because Care holds no
    `SELECT` on `audit_log` at all — the record it writes is not one it may read
    back, which is part of E0-10's grant model.
    """
    from sqlalchemy import select

    table = committed_rows.tables.get(AUDIT_TABLE)
    assert table is not None, (
        f"There is no `{AUDIT_TABLE}` table in `Base.metadata` — it holds "
        f"{sorted(committed_rows.tables)}. SPEC §8 names it, §4 requires a record of every "
        "identity access, and `public.record_identity_reveal` returns the id of the row it writes "
        "there."
    )
    for column in AUDIT_COLUMNS:
        assert column in table.c, (
            f"`{AUDIT_TABLE}` has no `{column}` column; it has "
            f"{[c.name for c in table.columns]}. SPEC §4 requires the record to carry the actor, "
            "the timestamp and the case, and `tests/integration/test_identity_column_marker.py` "
            "records this table as carrying exactly "
            f"{list(AUDIT_COLUMNS)} beside its key."
        )

    with migrated_engine.connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                select(table).where(table.c[AUDIT_ACTOR_COLUMN] == actor_person_id)
            )
            .mappings()
            .all()
        ]


@pytest.fixture
def care_service(care_service_environment: dict[str, str], import_app_module: Any) -> Any:
    """`app.services.safety`, imported against this container's Care connection.

    It asserts only that the module is there. **What the module must expose is
    `require_the_reveal_interface`'s, called from the test body** — E4-01 adds a
    name that does not exist yet, and a fixture asserting it would turn every red
    in two modules into a setup ERROR (`docs/MISTAKES.md` entry 44).
    """
    module = import_app_module(CARE_SERVICE_MODULE)
    assert module is not None, (
        f"There is no `{CARE_SERVICE_MODULE}` module. E0-10 names it — 'The Care service module is "
        "`backend/app/services/safety.py`, which SPEC §13 already names for the Care queue. Do not "
        "add a module for this.' — and it is where the second connection pool, the actor's "
        "assignment check and E4-01's subject derivation all live."
    )
    return module
