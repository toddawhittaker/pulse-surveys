"""The options route offers exactly the lengths and levels the spec allows — E5-06.

E5's exit line includes "a named set with an invalid combination cannot be
created", and the ticket's scope puts half of that here: "the form offers only
valid choices (decision 3) so an invalid length/level combination cannot be
expressed, not merely erroring" is E5-09's, and the list it offers comes from
this route. So what is asserted is the *contents* of the offer against the
spec's own two sets — SPEC §2.2's "Course lengths in weeks: 3, 6, 8, 10, 12, 15,
16 (plus an 18-week dissertation length)" and §5.1's five levels, `DEV`, `UG`,
`UGGR`, `GR`, `DR`, in §8's band order.

**The expectation is the spec's, never the application's.** Both sets are read
from `tests/fixtures/comparison_sets.py`, where E5-01 transcribed them from the
two spec sentences. Comparing this payload against `CALENDAR_LENGTHS` or
`CourseLevel` — the constants the route is built from — would agree with an
implementation that got either wrong (`docs/MISTAKES.md` entry 19).

**The label's composition is deliberately not pinned.** The work order settles
the *shape* ("BIOL 215 — Title") and settles that it comes from the one helper
the report already uses rather than from a second copy; the exact separator is
the implementer's. So each entry's label is required to name its course's number
and its title, and the list is required to be in its own label order — which is
what E5-09 renders and what the contract fixes.

**`GET /leadership/comparison-sets/options` is also the route-ordering trap.**
Declared after `{set_id}`, the path parses as a set id, and the answer is a
validation error or a 404 rather than the options. The status assertion here is
what catches that, and it catches it as a red on this route rather than as a
puzzling failure in E5-09's fixtures.

**Which failure a red here is, before E5-06 lands:** a FAILED naming the router
(`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest
from fixtures.named_sets import COURSE_NUMBERS, COURSE_TITLES, NamedSetDoor

pytestmark = pytest.mark.integration


def test_the_options_offer_spec_2_2s_lengths_and_spec_8s_levels(
    named_sets: NamedSetDoor, named_set_contract: Any
) -> None:
    """The two closed sets, against the spec's own transcription of them.

    **The mutations this kill:** a length list that drops 18, which SPEC §2.2
    carries in a parenthesis a reader skims past and which is the dissertation
    length every doctoral section has; a level list folding `UGGR` into `UG` or
    `GR`, which §5.1 forbids in as many words and which would let a definer
    build the one cohort the spec says must never be averaged together; and a
    level list in alphabetical order, which puts `DEV` after `DR` and hands
    E5-09 a selector whose order says nothing about the bands it comes from.

    **Expected red before E5-06 lands:** a FAILED naming the router.
    """
    answered = named_sets.options()
    body = named_set_contract.body_of(
        answered, "The set-definition options", named_set_contract.list_ok
    )

    assert body.get(named_set_contract.lengths_field) == list(named_set_contract.spec_lengths), (
        f"The options offer lengths {body.get(named_set_contract.lengths_field)!r}; SPEC §2.2's "
        f"set is {list(named_set_contract.spec_lengths)}. A length this list omits is a cohort "
        "leadership cannot define at all, and one it adds is a set the database will refuse at "
        "the moment of saving — which is the opposite of decision 3's 'invalid combinations "
        "impossible rather than erroring'."
    )
    assert body.get(named_set_contract.levels_field) == list(named_set_contract.spec_levels), (
        f"The options offer levels {body.get(named_set_contract.levels_field)!r}; SPEC §5.1 names "
        f"five and §8 bands them in the order {list(named_set_contract.spec_levels)}."
    )


def test_the_options_list_every_course_by_label_in_label_order(
    named_sets: NamedSetDoor, named_set_contract: Any
) -> None:
    """Each course is offered once, named the way a definer would recognise it.

    **The mutations this kills:** a course list restricted to the courses some
    set already names, which makes a new cohort undefinable; a list carrying the
    course's key and no label, which E5-09 can only render as a uuid; a label
    built from the course number alone, which is ambiguous across prefixes; and
    a list in insertion order, which is the order this world's four courses were
    seeded in and disagrees with their label order.

    **Each entry carries a level**, because the form pairs a level with its
    courses: an entry without one leaves E5-09 unable to offer only the courses
    a chosen level admits, and the cross-level refusal in
    `test_the_named_set_writes_translate_the_databases_refusal.py` is the
    database catching what the form should never have allowed.

    **Expected red before E5-06 lands:** a FAILED naming the router.
    """
    world = named_sets.world
    answered = named_sets.options()
    body = named_set_contract.body_of(
        answered, "The set-definition options", named_set_contract.list_ok
    )

    entries = body.get(named_set_contract.courses_field)
    assert isinstance(entries, list) and entries, (
        f"The options carry {entries!r} for `{named_set_contract.courses_field}`. A definer picks "
        "the member courses off this list; an empty one makes the whole surface unusable."
    )
    by_id = {str(entry.get(named_set_contract.course_id_field)): entry for entry in entries}

    for which, number in COURSE_NUMBERS.items():
        entry = by_id.get(str(world.course_id(which)))
        assert entry is not None, (
            f"The options do not offer the {which} course (number {number}); they offer "
            f"{[entry.get(named_set_contract.course_label_field) for entry in entries]}."
        )
        assert sorted(entry) == sorted(
            (
                named_set_contract.course_id_field,
                named_set_contract.course_label_field,
                named_set_contract.course_level_field,
            )
        ), (
            f"The {which} course's entry carries {sorted(entry)}; the contract gives every course "
            "three members and no more."
        )
        label = entry[named_set_contract.course_label_field]
        assert number in label and COURSE_TITLES[which] in label, (
            f"The {which} course is labelled {label!r}, which does not name both its number "
            f"({number}) and its title ({COURSE_TITLES[which]!r}). The work order's shape is "
            '"BIOL 215 — Title"; the separator is the implementer\'s and the two values are not.'
        )

    labels = [entry.get(named_set_contract.course_label_field) for entry in entries]
    assert labels == sorted(labels), (
        f"The courses came back in the order {labels}, which is not label order. The contract "
        "sorts them, and this world's four courses are seeded in an order their labels disagree "
        "with — so a list that never sorted anything answers them the other way round."
    )


def test_the_options_path_is_not_read_as_a_set_id(
    named_sets: NamedSetDoor, named_set_contract: Any
) -> None:
    """The route-ordering trap, asserted where it is cheap to diagnose.

    `/leadership/comparison-sets/options` and
    `/leadership/comparison-sets/{set_id}` are the same shape, and FastAPI
    matches in declaration order: with `{set_id}` first, this request is a set id
    that is not a uuid and the answer is a 422 from the path parser. The work
    order settles the order ("`options` is declared BEFORE the `{set_id}`
    routes") and this is what holds it.

    **The mutation it kills:** the two routes declared the other way round — a
    one-line reordering during a refactor, invisible in review, which takes the
    whole set-definition form out with it.

    **The pair** is every other test in this module: they assert what the options
    say, this asserts that asking for them reaches the options route at all.

    **Expected red before E5-06 lands:** a FAILED naming the router.
    """
    answered = named_sets.options()

    assert answered.status_code == named_set_contract.list_ok, (
        f"`GET {named_set_contract.options_path}` answered {answered.status_code}. A "
        f"{named_set_contract.refused_value} here is the path being parsed as a set id, which "
        "means `{set_id}` is declared first; a "
        f"{named_set_contract.unknown_set} is either that or a router nothing registered. Body "
        f"begins {answered.text[:400]!r}."
    )
