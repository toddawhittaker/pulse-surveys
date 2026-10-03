"""An invalid set is refused by the database and translated by the route — E5-06.

Criterion 3: "Create and edit surface the database's constraint refusals as 4xx
with §5.1-vocabulary messages, proven by attempting the invalid writes (the
constraint fires; the route translates)." The work order settles the mechanism
that makes the proof possible: `SetWrite` types `length_weeks` as `int` and
`level` as `str` — **not** the enum — because a Pydantic 422 would prove nothing
about the constraint; the service attempts the write, catches the integrity
error, maps it by constraint name to one sentence, and rolls back.

**Five refusals, each with its valid twin, on both writing routes.** Every
invalid body is the valid body with exactly one field replaced, so the refusal
is attributable to that field and the twin says the write path works at all. The
four values are near misses rather than nonsense (`tests/fixtures/comparison_sets.py`
chose them for E5-01 and they are chosen again here): `0` is the one length below
the `length_weeks >= 1` rule the owner set at E5-14 (it was `17`, against §2.2's
list, until then), `ug` is the right token in the wrong case
that a `lower()` check accepts, a graduate course is a real course of the wrong
level, and a fresh uuid is a member key that is simply nobody.

**The status alone would prove nothing here, and 422 is why.** A Pydantic
validation error and a translated constraint violation are both 422, and they
differ only in the body: one is FastAPI's list of field errors and the other is
the one sentence §5.1's vocabulary is written in. So each refusal pins the
sentence, and the schema test below pins the types that make the refusal the
database's rather than the wire model's.

**Nothing may be left behind by a refused write.** A create that inserted the
set row and then failed on a member is a set with no members sitting in the
institution's list; a refused edit that had already deleted the old membership
is a set that resolves to nothing. Both would pass a status-only test, so every
refusal here reads the stored rows back afterwards.

**Which failure a red here is, before E5-06 lands.** The refusal cases fail on
`refusal_sentence`, naming a copy constant nothing declares yet; the twins fail
on their status, naming the router; the schema test fails naming
`app.schemas.comparison_sets`. All FAILEDs (`docs/MISTAKES.md` entry 44).
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.named_sets import NamedSetDoor

pytestmark = pytest.mark.integration

WRITING_ROUTES = ("create", "edit")


def write(door: NamedSetDoor, route: str, body: Any) -> Any:
    """One `POST` of `body`, or one `PUT` of it over the set this session defined."""
    if route == "create":
        return door.create(body)
    return door.edit(door.world.hers.set_id, body)


def invalid_and_valid(door: NamedSetDoor, contract: Any, case: str) -> tuple[Any, Any, str, int]:
    """One refused body, its accepted twin, the constant it is refused with, and the status.

    The pair is built here so the two bodies can differ in exactly one field —
    which is what makes the refusal attributable — and the sentences are looked
    up by the caller, from `app.copy`, rather than written out.
    """
    world = door.world
    if case == "length":
        # E5-14: the owner ruled a set's length is data — the `CHECK` is
        # `length_weeks >= 1` — so `17` is storable now and the refusal's near miss
        # is zero weeks, beside a 4-week twin no calendar list names. The refusal
        # constant keeps its name (it is keyed by the constraint); whether its
        # sentence still reads right for "zero weeks" is a copy question the E5-14
        # manifest raises rather than this test answering.
        return (
            world.a_write(length_weeks=0),
            world.a_write(length_weeks=4),
            contract.length_not_a_calendar_length,
            contract.refused_value,
        )
    if case == "level":
        return (
            world.a_write(level="ug"),
            world.a_write(level=contract.declared_level),
            contract.level_not_a_course_level,
            contract.refused_value,
        )
    if case == "cross-level member":
        return (
            world.a_write(member_course_ids=[str(world.course_id("wrong_level"))]),
            world.a_write(member_course_ids=[str(world.course_id("first_member"))]),
            contract.member_not_at_the_sets_level,
            contract.refused_value,
        )
    if case == "member that is no course":
        return (
            world.a_write(member_course_ids=[str(uuid4())]),
            world.a_write(member_course_ids=[str(world.course_id("first_member"))]),
            contract.member_not_a_course,
            contract.refused_value,
        )
    if case == "duplicate name":
        return (
            world.a_write(name=world.theirs.name),
            world.a_write(),
            contract.name_already_used,
            contract.duplicate_name,
        )
    raise AssertionError(f"{case!r} is not one of {CASES}")


CASES = ("length", "level", "cross-level member", "member that is no course", "duplicate name")


@pytest.mark.parametrize("case", CASES, ids=CASES)
@pytest.mark.parametrize("route", WRITING_ROUTES, ids=WRITING_ROUTES)
def test_an_invalid_write_is_refused_with_the_sentence_naming_the_rule(
    named_sets: NamedSetDoor, named_set_contract: Any, route: str, case: str
) -> None:
    """Each invalid write, refused with §5.1's vocabulary and storing nothing.

    **The mutations this kill, one per case.** A length check that lets a set of
    zero weeks through (`>= 0`, or no check at all since E5-14 replaced §2.2's
    list with `>= 1`); a level check written with
    `lower()`, which accepts `ug` and stores a token no other read recognises; a
    membership insert that names the course and not the level, which lets a
    graduate course into an undergraduate set and produces a benchmark averaging
    exactly what §5.1 forbids averaging; a member key nothing checks, which
    stores a set resolving to fewer sections than its definer chose; and a name
    uniqueness check done with a `SELECT` first, which passes review and races.

    **The near miss each one is:** every invalid value here is one step from a
    value the schema accepts, and the twin below is that step taken. A refusal
    of `"banana"` would be satisfied by a check this test cannot distinguish
    from a type error.

    **Nothing stored, asserted.** A refused create must leave no set behind —
    including the half-built one a service leaves when it inserts the set, fails
    on a member and does not roll back — and a refused edit must leave the set
    exactly as it was, membership included.

    **Expected red before E5-06 lands:** a FAILED naming the copy constant this
    case is refused with.
    """
    world = named_sets.world
    invalid, _valid, constant, status = invalid_and_valid(named_sets, named_set_contract, case)
    expected = named_set_contract.sentence(constant)
    before = world.set_rows()
    hers_before = world.set_row(world.hers.set_id)
    members_before = len(world.members_of(world.hers.set_id))

    answered = write(named_sets, route, invalid)

    assert answered.status_code == status, (
        f"A `{route}` carrying the {case} case answered {answered.status_code} rather than "
        f"{status}. Body begins {answered.text[:400]!r}."
    )
    assert named_set_contract.detail_of(answered) == expected, (
        f"The {case} case was refused with {named_set_contract.detail_of(answered)!r} rather than "
        f"with {constant} — {expected!r}.\n\n"
        "A body carrying a list of Pydantic field errors means the wire model refused the value "
        "before the database saw it, which is the one thing criterion 3 says this route must not "
        "be doing: the API 'refuses nothing the database already makes unstorable — it translates'."
    )

    after = world.set_rows()
    assert len(after) == len(before), (
        f"The refused `{route}` left the database holding {len(after)} comparison sets where it "
        f"held {len(before)}. A refused write that stored a row is worse than one that stored "
        "nothing and answered 200, because the row is in every leader's list and nobody chose it."
    )

    def carrying_the_name(rows: list[Any]) -> list[Any]:
        return [row for row in rows if row[named_set_contract.name_field] == invalid["name"]]

    assert len(carrying_the_name(after)) == len(carrying_the_name(before)), (
        f"The refused `{route}` changed how many sets are named {invalid['name']!r}: "
        f"{len(carrying_the_name(before))} before, {len(carrying_the_name(after))} after. The "
        "service attempts the write and rolls back; a partially committed create is a set the "
        "constraint refused and the transaction kept. (The duplicate-name case starts at one, "
        "which is why this is a count rather than an absence.)"
    )
    if route == "edit":
        assert world.set_row(world.hers.set_id) == hers_before, (
            f"The refused edit changed the set anyway.\n  before: {hers_before}\n  after:  "
            f"{world.set_row(world.hers.set_id)}"
        )
        assert len(world.members_of(world.hers.set_id)) == members_before, (
            f"The refused edit left the set holding "
            f"{len(world.members_of(world.hers.set_id))} membership rows where it held "
            f"{members_before}. Membership is replaced wholesale on a `PUT`, so a refusal after "
            "the delete and before the insert is a set that resolves to nothing."
        )


@pytest.mark.parametrize("case", CASES, ids=CASES)
@pytest.mark.parametrize("route", WRITING_ROUTES, ids=WRITING_ROUTES)
def test_the_valid_twin_of_each_refused_write_is_accepted(
    named_sets: NamedSetDoor, named_set_contract: Any, route: str, case: str
) -> None:
    """The twin: one step from the refused body, and it is stored.

    Without this, every refusal above is satisfied by a route that refuses every
    write — which is the shape a constraint translator takes when it maps *any*
    `IntegrityError` to a sentence and the write path never worked
    (`docs/MISTAKES.md` entry 3).

    **The mutations it kills:** a length check refusing 4, which no calendar list
    names and the owner's E5-14 ruling makes storable; a level check refusing `UG`; a membership insert that refuses a
    course of the set's own level; and a name-uniqueness check that refuses
    every name because it compares against the whole table rather than against
    other rows.

    **Expected red before E5-06 lands:** a FAILED naming the router.
    """
    world = named_sets.world
    _invalid, valid, _constant, _status = invalid_and_valid(named_sets, named_set_contract, case)
    expected = named_set_contract.created if route == "create" else named_set_contract.list_ok

    answered = write(named_sets, route, valid)

    assert answered.status_code == expected, (
        f"The valid twin of the {case} case was refused by `{route}` with "
        f"{answered.status_code} rather than answered {expected}. Body begins "
        f"{answered.text[:400]!r}.\n\n"
        "Every value in this body is one the schema allows (§8's levels; since E5-14 any length "
        "of at least one week), and the refused body differs from "
        "it in exactly one field — so a refusal here means the rule under test refuses the legal "
        "half as well as the illegal one, and its twin above passes for a reason nobody chose."
    )
    name_field = named_set_contract.name_field
    stored = [row for row in world.set_rows() if row[name_field] == valid["name"]]
    assert len(stored) == 1, (
        f"The accepted `{route}` left {len(stored)} sets named {valid['name']!r} in the database. "
        "An answer of 201 or 200 is a claim that the row is there."
    )


def test_the_write_schema_takes_a_plain_length_and_a_plain_level(
    named_set_contract: Any,
) -> None:
    """The types that make criterion 3's proof a proof at all.

    The work order settles it in a sentence: "`SetWrite` types `length_weeks:
    int` and `level: str` (NOT the enum — a pydantic 422 would prove nothing
    about the constraint)". This is the structural half of every refusal above:
    with `level` typed as `CourseLevel`, `"ug"` never reaches the database, the
    422 comes from the wire model, and the criterion — "the constraint fires;
    the route translates" — is asserted by nothing while every status stays
    green.

    **The mutation it kills:** exactly that substitution, which reads in a diff
    as stricter typing and is the one change that would make this module's five
    refusals pass without any constraint firing.

    **Expected red before E5-06 lands:** a FAILED naming
    `app.schemas.comparison_sets`.
    """
    model = named_set_contract.write_model()
    fields = model.model_fields

    assert fields[named_set_contract.length_field].annotation is int, (
        f"`{model.__name__}.{named_set_contract.length_field}` is annotated "
        f"{fields[named_set_contract.length_field].annotation!r} rather than `int`. A constrained "
        "type here refuses the out-of-set length before the database sees it, and the criterion "
        "is that the database refuses it and the route translates."
    )
    assert fields[named_set_contract.level_field].annotation is str, (
        f"`{model.__name__}.{named_set_contract.level_field}` is annotated "
        f"{fields[named_set_contract.level_field].annotation!r} rather than `str`. With the enum "
        "here, `'ug'` is refused by Pydantic and the `course_level` cast this route is supposed to "
        "be translating is never reached."
    )
