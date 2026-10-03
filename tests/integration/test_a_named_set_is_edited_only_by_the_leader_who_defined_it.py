"""A leader edits and deletes the sets they defined, and reads everybody's — E5-06.

Criterion 2: "A leader reaches only sets within their scope for edit and delete;
a planted second leader's set is refused — both directions." Work-order decision
1 settles what "within their scope" means for this ticket and records the
alternative it rejects: **ownership by creator**. A set's name and counts are not
confidential and §5.1's set-definition surface is one institution-wide list, so
list, GET-by-id and preview answer every set to any leadership session; PUT and
DELETE are allowed only where the set's creator is the session's person, and the
summary's `editable` says which is which. Purview over the supervision DAG is
E9's (breakdown decision 4).

**Both directions everywhere, because each half alone is satisfied by the wrong
thing.** "Another leader's set is refused on PUT" is satisfied by a route that
refuses every PUT, so it is paired with her own set being edited. "Her own set
is deleted" is satisfied by a route that deletes anything, so it is paired with
the other leader's set surviving. And the refusal is read through the body: a
403 carrying `NOT_THE_SETS_DEFINER` is the service's scope read, where a 404
would be the set lookup and a 401 the role gate.

**The stored row is asserted, not the return value.** A route that answered 403
and wrote anyway would pass a status-only test, and the set it changed is the
cohort some instructor is measured against. So each refusal reads the row back
on the seeding connection afterwards and requires it to be exactly what was
planted.

**Which failure a red here is, before E5-06 lands.** The paths are the work
order's own, so an application without the router answers 404 and the admitted
halves fail on their status naming the router; the refusal halves fail on the
copy constant, which no module under `app.copy` declares yet. Both are FAILEDs
naming a deliverable (`docs/MISTAKES.md` entry 44).
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.named_sets import NamedSetDoor

pytestmark = pytest.mark.integration

# The two routes decision 1 scopes by creator, and the two it does not.
WRITING_ROUTES = ("edit", "delete")
READING_ROUTES = ("read", "preview")


def write_to(door: NamedSetDoor, route: str, set_id: Any) -> Any:
    """One `PUT` or one `DELETE` against `set_id`, as the leadership session."""
    if route == "edit":
        return door.edit(set_id, door.world.a_write())
    return door.remove(set_id)


def read_of(door: NamedSetDoor, route: str, set_id: Any) -> Any:
    """One `GET` or one preview of `set_id`, as the leadership session."""
    return door.read(set_id) if route == "read" else door.preview(set_id)


@pytest.mark.parametrize("route", WRITING_ROUTES, ids=WRITING_ROUTES)
def test_another_leaders_set_is_refused_on_a_write_and_survives_it(
    named_sets: NamedSetDoor, named_set_contract: Any, route: str
) -> None:
    """The refused half of criterion 2, per writing route, with the row read back.

    The set planted for the second leader is a set this session may read and may
    not change. The refusal carries `NOT_THE_SETS_DEFINER`, which is the
    sentence the work order puts on the service's scope read — a 404 here would
    say the set could not be found and a 401 that the session is not leadership,
    and neither is the fact under test.

    **The mutations this kills:** a scope check written as "the session is
    leadership", which is the role gate over again and admits every leader to
    every set; a check comparing the session's person against the set's creator
    with `==` on two different types (a uuid and its string), which is always
    false and would refuse *everything* — caught by the twin below; and a route
    that refuses after writing, which is why the row is read back rather than
    trusted.

    **Expected red before E5-06 lands:** a FAILED naming the copy constant
    `NOT_THE_SETS_DEFINER`.
    """
    world = named_sets.world
    theirs = world.theirs
    expected = named_set_contract.sentence(named_set_contract.not_the_sets_definer)
    before = world.set_row(theirs.set_id)
    assert before is not None, (
        "The second leader's set is not in the database, so this test would be asserting a refusal "
        "of a set nobody defined. `build_named_set_world` plants it."
    )

    answered = write_to(named_sets, route, theirs.set_id)

    assert answered.status_code == named_set_contract.not_the_definer, (
        f"A `{route}` of another leader's set answered {answered.status_code}; decision 1 refuses "
        f"it with {named_set_contract.not_the_definer}. Body begins {answered.text[:400]!r}."
    )
    assert named_set_contract.detail_of(answered) == expected, (
        f"The `{route}` was refused with {named_set_contract.detail_of(answered)!r} rather than "
        f"with the `NOT_THE_SETS_DEFINER` sentence {expected!r}. The sentence is how this test "
        "says the *scope read* refused rather than the role gate or the set lookup."
    )
    assert world.set_row(theirs.set_id) == before, (
        f"The refused `{route}` changed the row anyway.\n  before: {before}\n  after:  "
        f"{world.set_row(theirs.set_id)}\nA benchmark that changes without anybody deciding it is "
        "what ADR 0164 calls the serious outcome here, and a 403 in the response does not undo it."
    )
    assert len(world.members_of(theirs.set_id)) == len(theirs.member_course_ids), (
        f"The refused `{route}` left the other leader's set holding "
        f"{len(world.members_of(theirs.set_id))} membership rows; it was planted with "
        f"{len(theirs.member_course_ids)}."
    )


@pytest.mark.parametrize("route", WRITING_ROUTES, ids=WRITING_ROUTES)
def test_her_own_set_is_written_by_the_leader_who_defined_it(
    named_sets: NamedSetDoor, named_set_contract: Any, route: str
) -> None:
    """The admitted half of criterion 2, per writing route — the twin of the refusal above.

    Without it, "another leader's set is refused" is equally satisfied by a route
    that refuses every write it is given, which is the shape a scope check
    comparing a uuid against its own string takes (`docs/MISTAKES.md` entry 3).

    **The mutation it kills:** exactly that — a comparison that is false for
    everybody, which looks maximally safe and makes the whole surface inert.

    **Expected red before E5-06 lands:** a FAILED naming the router.
    """
    world = named_sets.world
    hers = world.hers
    expected = {"edit": named_set_contract.list_ok, "delete": named_set_contract.no_content}[route]

    answered = write_to(named_sets, route, hers.set_id)

    assert answered.status_code == expected, (
        f"A `{route}` of the set this session's own person defined answered "
        f"{answered.status_code} rather than {expected}. Body begins {answered.text[:400]!r}.\n\n"
        "A 403 here means the creator comparison refuses its own creator, which would make every "
        "refusal in this module true for a reason that has nothing to do with scope."
    )


@pytest.mark.parametrize("route", READING_ROUTES, ids=READING_ROUTES)
def test_another_leaders_set_is_answered_on_every_reading_route(
    named_sets: NamedSetDoor, named_set_contract: Any, route: str
) -> None:
    """Decision 1's other half: a read is institution-wide, an edit is not.

    "List, GET-by-id and preview answer every set to any leadership session (a
    set's name and counts are not confidential; §5.1's set-definition surface is
    one institution-wide list)." This is the direction a scope check applied
    uniformly would break: the same comparison used on the read path answers 403
    here, and nothing else in this module would notice.

    **The mutation it kills:** the creator comparison lifted into a shared
    dependency or service helper that every route calls — which is the tidy
    refactor a reader would make, and it silently halves the product's set list
    for every leader in the institution.

    **Expected red before E5-06 lands:** a FAILED naming the router.
    """
    answered = read_of(named_sets, route, named_sets.world.theirs.set_id)

    assert answered.status_code == named_set_contract.list_ok, (
        f"A `{route}` of another leader's set answered {answered.status_code} rather than "
        f"{named_set_contract.list_ok}. Decision 1 scopes the *writes* by creator and leaves the "
        f"reads institution-wide. Body begins {answered.text[:400]!r}."
    )


def test_the_list_answers_every_set_sorted_by_name_and_says_which_are_editable(
    named_sets: NamedSetDoor, named_set_contract: Any
) -> None:
    """The list carries both leaders' sets, in name order, each marked editable or not.

    `editable` is decision 1 made visible: it is how E5-09 knows whether to offer
    an edit control, and it has to be true of the session's own sets and false of
    everybody else's. The order is the contract's ("sorted by name") and the two
    planted names disagree with the order the rows were written in — the second
    leader's set is written second and sorts first — so a list in insertion order
    is red here rather than plausible (`docs/MISTAKES.md` entry 3).

    **The mutations this kills:** a list scoped to the session's own sets, which
    is the natural over-reading of "scope" and which would leave a leader unable
    to see the institution's sets at all; `editable` hard-coded to `True`, which
    hands E5-09 an edit control that always 403s; and no ordering at all, which
    reads as correct for as long as Postgres happens to return rows in insertion
    order.

    **Expected red before E5-06 lands:** a FAILED naming the router.
    """
    world = named_sets.world
    answered = named_sets.list_sets()
    body = named_set_contract.body_of(answered, "The named-set list", named_set_contract.list_ok)

    entries = body.get(named_set_contract.sets_member) if isinstance(body, dict) else None
    assert isinstance(
        entries, list
    ), f"The list answered {body!r}, which carries no `{named_set_contract.sets_member}` list."
    by_id = {str(entry.get(named_set_contract.id_field)): entry for entry in entries}

    for planted, editable in ((world.hers, True), (world.theirs, False)):
        entry = by_id.get(str(planted.set_id))
        assert entry is not None, (
            f"The list does not carry the set named {planted.name!r}; it carries "
            f"{[entry.get(named_set_contract.name_field) for entry in entries]}. Every set in the "
            "institution is on this list — that is what decision 1 settles."
        )
        assert entry.get(named_set_contract.editable_field) is editable, (
            f"The set named {planted.name!r} is marked "
            f"{entry.get(named_set_contract.editable_field)!r} for "
            f"`{named_set_contract.editable_field}` and this session's person "
            f"{'did' if editable else 'did not'} define it."
        )
        assert entry.get(named_set_contract.member_count_field) == len(planted.member_course_ids), (
            f"The set named {planted.name!r} reports "
            f"{entry.get(named_set_contract.member_count_field)!r} members and was planted with "
            f"{len(planted.member_course_ids)}."
        )

    names = [entry.get(named_set_contract.name_field) for entry in entries]
    assert names == sorted(names), (
        f"The list answered its sets in the order {names}, which is not name order. The two sets "
        "this world plants are written in the opposite order to the one they sort in, so a list "
        "that never sorted anything would answer them the other way round."
    )


@pytest.mark.parametrize("route", (*READING_ROUTES, *WRITING_ROUTES), ids=lambda name: name)
def test_a_set_id_nothing_defined_is_unknown_on_every_route_that_takes_one(
    named_sets: NamedSetDoor, named_set_contract: Any, route: str
) -> None:
    """A uuid no set carries is a 404 carrying `SET_UNAVAILABLE`, on all four routes.

    The pair to it is every other test in this module, each of which drives the
    same route with a set id that *is* there and is answered — so a 404 here is
    the lookup refusing an unknown set rather than a route nobody registered.

    **A fresh uuid rather than a mangled one**, because ADR 0016 makes every key
    a uuid and a malformed value is refused by the route's own parsing before any
    lookup runs, which is a different layer and a different status.

    **The mutations this kills:** an unknown set raising out of the service as a
    500; and a 403 for an unknown set, which tells a caller that a set exists and
    belongs to somebody else — the difference between "there is no such set" and
    "there is one and it is not yours" is a fact about another leader's data.

    **Expected red before E5-06 lands:** a FAILED naming the copy constant
    `SET_UNAVAILABLE`.
    """
    expected = named_set_contract.sentence(named_set_contract.set_unavailable)
    absent = uuid4()

    answered = (
        read_of(named_sets, route, absent)
        if route in READING_ROUTES
        else write_to(named_sets, route, absent)
    )

    assert answered.status_code == named_set_contract.unknown_set, (
        f"A `{route}` of a set id nothing defined answered {answered.status_code} rather than "
        f"{named_set_contract.unknown_set}. Body begins {answered.text[:400]!r}."
    )
    assert named_set_contract.detail_of(answered) == expected, (
        f"The `{route}` of an unknown set was refused with "
        f"{named_set_contract.detail_of(answered)!r} rather than with the `SET_UNAVAILABLE` "
        f"sentence {expected!r}."
    )
