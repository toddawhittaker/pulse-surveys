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
from fixtures.named_sets import (
    COURSE_NUMBERS,
    COURSE_TITLES,
    NamedSetDoor,
    plant_a_section_of_length,
)

pytestmark = pytest.mark.integration

# A section length no start letter in the seed carries and SPEC §2.2 does not
# list — the owner's own example of a length that is data rather than code.
A_LENGTH_NO_LETTER_CARRIES = 4


def the_section_lengths_that_exist(world: Any) -> list[int]:
    """Every distinct `section.length_weeks` in the database, ascending — read back directly.

    This *is* the owner's rule rather than a copy of an implementation: "`definition_options`
    offers the distinct `section.length_weeks` values that exist in the database, sorted"
    (E5-14, 2026-09-22). It is read after the fixture's commit, on the test's own
    connection.
    """
    from fixtures.survey_windows import SECTION_LENGTH_COLUMN, SECTION_TABLE
    from sqlalchemy import text

    world.refresh()
    rows = world.session.execute(
        text(f"SELECT DISTINCT {SECTION_LENGTH_COLUMN} FROM public.{SECTION_TABLE}")  # noqa: S608
    )
    return sorted(int(row[0]) for row in rows)


def test_the_options_offer_the_section_lengths_that_exist_and_spec_8s_levels(
    named_sets: NamedSetDoor, named_set_contract: Any
) -> None:
    """The owner's ruling on lengths (E5-14), and §8's five levels in band order.

    **Lengths: the distinct section lengths present, sorted** — the owner's ruling
    of 2026-09-22 that a named set's length is data. Until E5-14 this compared the
    offer against SPEC §2.2's eight lengths, which the migration's `CHECK`
    hard-coded; the adr-docs review found that list contradicted §2.2's "the
    academic calendar is institution configuration, not code". A 4-week section —
    a length no calendar list names — is planted here, so the offer has to follow
    the data rather than a list.

    **The mutations this kills:** `CALENDAR_LENGTHS` left in the options service
    (4 is missing, and §2.2 lengths no section runs are offered); the distinct
    lengths unsorted; and a level list
    folding `UGGR` into `UG` or `GR`, or in alphabetical order, which puts `DEV`
    after `DR`.
    """
    plant_a_section_of_length(named_sets.world, A_LENGTH_NO_LETTER_CARRIES, ordinal="9")
    expected_lengths = the_section_lengths_that_exist(named_sets.world)
    # The premise rests only on what this test planted: the 4-week length is in the
    # database. That alone is what makes the comparison below discriminate — SPEC
    # §2.2's list does not carry 4, so an offer built from `CALENDAR_LENGTHS` differs
    # from the distinct lengths read back whatever else the world holds. (An 18-week
    # section can exist in this world; the first version of this guard assumed it did
    # not and fired before the comparison.)
    assert A_LENGTH_NO_LETTER_CARRIES in expected_lengths, (
        f"The database's section lengths are {expected_lengths}; this test planted a "
        f"{A_LENGTH_NO_LETTER_CARRIES}-week section and it is not among them, so the comparison "
        "below would not tell an offer built from a calendar list from one built from the data."
    )

    answered = named_sets.options()
    body = named_set_contract.body_of(
        answered, "The set-definition options", named_set_contract.list_ok
    )

    assert body.get(named_set_contract.lengths_field) == expected_lengths, (
        f"The options offer lengths {body.get(named_set_contract.lengths_field)!r}; the sections "
        f"in the database run {expected_lengths} weeks. The owner's ruling: the options offer the "
        "distinct `section.length_weeks` values that exist, sorted — a length no section runs is a "
        "cohort that resolves to nothing, and a length a section runs is one a leader may name."
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
