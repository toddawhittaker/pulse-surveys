"""The benchmark seal counts a leadership reader, with her purview as what she knows — E9-05.

> 5. **The seal counts a leadership reader.** For a reported section read with a
>    leadership reader, a comparison or university figure is suppressed when
>    what is left after removing the reader's known set (purview and taught
>    sections) is non-empty and below either minimum, and shown when that
>    remainder is empty or meets both; tested one respondent either side of the
>    minimum. … Marked `invariant`.
> 7. **The university line's first extra piece, for a leader.** U less the
>    reader's known set meets both minimums, but one default comparison set of a
>    section in the purview, less the known set, is non-empty and thin; U is
>    suppressed. The shown twin … One respondent either side. Marked `invariant`.
> 8. **The university line's second extra piece, for a leader.** U less the
>    known set meets both minimums, but U less the known set and less every such
>    default set is non-empty and thin; U is suppressed. The shown twin … One
>    respondent either side. Marked `invariant`.

SPEC §5.1: "A leadership reader is sealed against too … the seal treats the
leader exactly as it treats an instructor, with every section in the person's
leadership purview together with every section the person teaches in place of
the sections the instructor teaches." The reader is passed to
`section_benchmarks` as her `ActorScope`, resolved by E9-01's chokepoint.

**Every world is read twice: by the instructor alone, and with the reader.**
The instructor of the reported section holds no leadership assignment, and every
world is built so her own seal hides nothing that the reader's must — so each
suppression is asserted beside the same figure *shown* in the same world, to a
read that differs only in whether the reader was passed (`docs/MISTAKES.md`
entry 3). That read is also done-when 5's last sentence: an instructor with no
leadership assignment is sealed exactly as before.

**How a figure is told apart without its member names.** The interface leaves
`SectionBenchmarks`' members to the implementer and says the tests observe the
seal through figures. So the default set's figures are recognised by the numbers
this module planted for them, written out by hand; and where a world gives the
reported section an empty default set (one whose course has no other course
under its lead), every figure that is *shown* is a university figure, and the
count of shown figures is what a test compares. The two reads of one world have
the same shape, so their counts are comparable.

**Every world is cohort F at level UGGR**, one section per course, answered at
course week 2, cut off after every window (`tests/fixtures/named_set_figures.py`
says why).

**Which failure a red is, before E9-05 lands:** every read FAILS naming the
missing `scope` parameter of `section_benchmarks` — the instructor-only reads
too, since they pass `scope=None` explicitly (E9-05's fix round, P2).
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.named_set_figures import (
    PurviewWorld,
    a_lead_straddling_the_readers_department,
    any_carries,
    every_figure,
    one_section_course,
    shown_count,
    suppressed_count,
    the_hero_answers,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]


# ---------------------------------------------------------------------------
# Done-when 5, the comparison figure: the default set less the reader's purview.
# ---------------------------------------------------------------------------

S0_RATING, S0_HOURS = Decimal("2"), Decimal("9.5")
REST_RATING, REST_HOURS = Decimal("4"), Decimal("6.5")


def a_default_set_the_reader_holds_one_section_of(world: PurviewWorld, *, remainder: int) -> Any:
    """Lead A's courses: the hero, `s0` in the reader's department, `s1…` outside it.

    The hero's default set is `s0` and `s1…` (A's other courses). The reader
    chairs the department holding `s0` alone, so the default set less what she
    knows is `s1…`: the section minimum's worth of sections, answered by
    `remainder` people. `s0` is answered by the respondent minimum, so the
    default set itself always clears both minimums, and so does everything the
    hero's instructor can subtract. Answers the default set's rating mean and
    hours mean, by hand.
    """
    world.build()
    sections, respondents = world.sections_minimum, world.respondents_minimum
    rest = [f"s{index}" for index in range(1, sections + 1)]
    one_section_course(world, "hero", "home", alone=False)
    one_section_course(world, "s0", "side", alone=False)
    for label in rest:
        one_section_course(world, label, "home", alone=False)
    world.lead("lead A", "hero", "s0", *rest)
    world.teach("the teacher", "hero")
    world.chair("the reader", "side")

    the_hero_answers(world)
    world.answer(
        ["s0"], respondents=respondents, prefix="e9-05-seal-s0", rating=S0_RATING, hours=S0_HOURS
    )
    world.answer(
        rest, respondents=remainder, prefix="e9-05-seal-rest", rating=REST_RATING, hours=REST_HOURS
    )
    total = respondents + remainder
    return (
        (S0_RATING * respondents + REST_RATING * remainder) / total,
        (S0_HOURS * respondents + REST_HOURS * remainder) / total,
    )


def test_a_default_set_figure_is_withheld_from_a_reader_who_knows_all_but_a_thin_remainder(
    purview_world: PurviewWorld,
) -> None:
    """The default set less the reader's purview is one respondent short: withheld from her.

    **The control, same world:** the hero's instructor reads the same report
    without the reader and is served the default set's figures, and nothing is
    suppressed for her.

    **The mutations this kills:** the reader not added to the seal at all; the
    reader added with her *teaching* sections only (she teaches none here); her
    purview resolved and then dropped before `_section_populations`.
    **The near miss:** the twin below, one more respondent, shown.
    """
    world = purview_world
    rating, hours = a_default_set_the_reader_holds_one_section_of(
        world, remainder=world.respondents_minimum - 1
    )

    control = world.section_benchmarks("hero")
    read = world.section_benchmarks("hero", reader="the reader")

    assert any_carries(control, rating) and any_carries(control, hours), (
        f"The control failed: the hero's instructor, with no reader passed, is not served the "
        f"default set's figures ({rating}, {hours} hours). The default set clears both minimums "
        "and so does everything she can subtract, so a figure withheld from her is withheld for a "
        "reason this world did not plant."
    )
    assert suppressed_count(control) == 0, (
        f"The control failed: the instructor-only read suppresses {suppressed_count(control)} "
        "figures in a world where nothing she knows leaves a thin remainder."
    )
    assert len(every_figure(read)) == len(every_figure(control)), (
        "The read with a reader answers a different number of figures than the read without one; "
        "a withheld figure is a suppressed figure, never a missing one."
    )
    assert not any_carries(read, rating) and not any_carries(read, hours), (
        f"The reader is served the default set's figures ({rating}, {hours} hours). She chairs the "
        "department holding one of its sections and reads that section's own figures, so the "
        "default set less it is a figure over one respondent fewer than the minimum (SPEC §5.1)."
    )
    assert suppressed_count(read) >= 1, "The read with the reader carries no suppressed figure."


def test_a_default_set_figure_is_shown_to_a_reader_when_the_remainder_meets_both_minimums(
    purview_world: PurviewWorld,
) -> None:
    """The twin: the remainder at exactly the respondent minimum — shown to the reader.

    **The mutation this kills:** a seal that withholds every figure from any
    reader whose purview touches the population, or reads the minimum as "more
    than". It is also the control that the read with a reader can serve a
    figure at all.
    """
    world = purview_world
    rating, hours = a_default_set_the_reader_holds_one_section_of(
        world, remainder=world.respondents_minimum
    )

    read = world.section_benchmarks("hero", reader="the reader")

    assert any_carries(read, rating) and any_carries(read, hours), (
        f"The reader is not served the default set's figures ({rating}, {hours} hours) although "
        "what is left after removing her purview meets both minimums."
    )
    assert suppressed_count(read) == 0, (
        f"The read with the reader suppresses {suppressed_count(read)} figures where every "
        "remainder meets both minimums."
    )


# ---------------------------------------------------------------------------
# Done-when 5, the university figure: U less the reader's purview.
# ---------------------------------------------------------------------------

SET_RATING, SET_HOURS = Decimal("4"), Decimal("6.5")
NEAR_RATING, NEAR_HOURS = Decimal("2"), Decimal("3.5")
FAR_RATING, FAR_HOURS = Decimal("3"), Decimal("11.5")


def a_university_the_reader_knows_all_but_a_far_department_of(
    world: PurviewWorld, *, far: int
) -> tuple[Decimal, Decimal]:
    """The reader chairs `home` (the hero, its default set, and `near…`); `far…` is elsewhere.

    Everything in the university except `far…` is in the reader's purview, so U
    less what she knows is `far…`: the section minimum's worth of sections and
    `far` people. `near…` (unled, in `home`) meets both minimums, so the hero's
    instructor — who knows the hero only — can subtract nothing thin. Answers
    the default set's rating and hours, which every read must serve.
    """
    world.build()
    sections, respondents = world.sections_minimum, world.respondents_minimum
    default = [f"d{index}" for index in range(sections)]
    near = [f"near{index}" for index in range(sections)]
    far_labels = [f"far{index}" for index in range(sections)]
    one_section_course(world, "hero", "home", alone=False)
    for label in default:
        one_section_course(world, label, "home", alone=False)
    for label in near:
        one_section_course(world, label, "home", alone=True)
    for label in far_labels:
        one_section_course(world, label, "far", alone=True)
    world.lead("lead A", "hero", *default)
    world.teach("the teacher", "hero")
    world.chair("the reader", "home")

    the_hero_answers(world)
    world.answer(
        default, respondents=respondents, prefix="e9-05-seal-d", rating=SET_RATING, hours=SET_HOURS
    )
    world.answer(
        near,
        respondents=respondents,
        prefix="e9-05-seal-near",
        rating=NEAR_RATING,
        hours=NEAR_HOURS,
    )
    world.answer(
        far_labels, respondents=far, prefix="e9-05-seal-far", rating=FAR_RATING, hours=FAR_HOURS
    )
    return SET_RATING, SET_HOURS


def test_the_university_line_is_withheld_from_a_reader_whose_purview_leaves_a_thin_remainder(
    purview_world: PurviewWorld,
) -> None:
    """U less the reader's purview is one respondent short: the university figures are withheld.

    **The controls, same world:** the reader is still served the default set
    (its remainder after her purview is empty), so the read is not a seal that
    withholds everything; and the hero's instructor alone is served everything.

    **The mutations this kills:** the reader counted against the comparison
    figure and not the university one; the reader's remainder computed from the
    university *less the reported section* only (E5-14's instructor rule
    without her purview).
    """
    world = purview_world
    rating, hours = a_university_the_reader_knows_all_but_a_far_department_of(
        world, far=world.respondents_minimum - 1
    )

    control = world.section_benchmarks("hero")
    read = world.section_benchmarks("hero", reader="the reader")

    assert suppressed_count(control) == 0 and any_carries(control, rating), (
        f"The control failed: the instructor-only read suppresses {suppressed_count(control)} "
        f"figures or does not serve the default set's {rating}, in a world where she can subtract "
        "nothing thin."
    )
    assert any_carries(read, rating) and any_carries(read, hours), (
        f"The reader is not served the default set's figures ({rating}, {hours} hours); its "
        "remainder after her purview is empty, which §5.1 counts as safe. A seal that withholds "
        "it is withholding everything, and the assertion below would mean nothing."
    )
    assert len(every_figure(read)) == len(every_figure(control))
    assert suppressed_count(read) > suppressed_count(control), (
        "The university figures are served to the reader although the university less her "
        "purview is one department's sections answered by one respondent fewer than the minimum "
        "— a figure she computes by subtracting the sections she reads (SPEC §5.1)."
    )


def test_the_university_line_is_shown_to_a_reader_whose_remainder_meets_both_minimums(
    purview_world: PurviewWorld,
) -> None:
    """The twin: U less the reader's purview at exactly the respondent minimum — shown.

    **The mutation this kills:** a reader who chairs anything has every
    university figure withheld (the remainder written as "must be empty").
    """
    world = purview_world
    a_university_the_reader_knows_all_but_a_far_department_of(world, far=world.respondents_minimum)

    read = world.section_benchmarks("hero", reader="the reader")

    assert suppressed_count(read) == 0, (
        f"The read with the reader suppresses {suppressed_count(read)} figures although the "
        "university less her purview meets both minimums."
    )
    assert shown_count(read) == len(every_figure(read)) > 0


# ---------------------------------------------------------------------------
# Done-when 7 and 8: the university line's two extra pieces, for a leader.
# ---------------------------------------------------------------------------


def test_a_thin_default_set_of_a_section_in_the_purview_withholds_the_university_line(
    purview_world: PurviewWorld,
) -> None:
    """Done-when 7: `s0`'s default set less the reader's purview is one respondent short.

    U less what the reader knows is `l…` and `r…`, which meets both minimums; U
    less that and less `l…` is `r…`, which meets both too. Only the first extra
    piece, `l…`, is thin — and the reader reads `s0`'s own report, whose default
    set line is over exactly those sections.

    **The control, same world:** the hero's instructor, who holds no leadership
    assignment and knows only the hero, is served the university figures. The
    hero's default set is empty, so every shown figure is a university figure.

    **The mutations this kill:** the reader's `lead_sets_seen` built from her
    *taught* sections only (empty here), or from the reported section's default
    set only; the first extra piece dropped for a reader.
    **The near miss:** the twin below, one more respondent in `l…`, shown.
    """
    world = purview_world
    a_lead_straddling_the_readers_department(
        world,
        lead_set=world.respondents_minimum - 1,
        rest=world.respondents_minimum,
        chair="the reader",
    )

    control = world.section_benchmarks("hero")
    read = world.section_benchmarks("hero", reader="the reader")

    assert shown_count(control) >= 1, (
        "The control failed: the hero's instructor alone is served no university figure in a "
        "world where nothing she knows leaves a thin remainder."
    )
    assert len(every_figure(read)) == len(every_figure(control))
    assert shown_count(read) == 0, (
        f"The reader is served {shown_count(read)} university figures. The default set of `s0`, "
        "a section in her purview, less what she knows is one respondent short of the minimum, "
        "and she reads that default set's line on `s0`'s own report (SPEC §5.1's first extra "
        "piece of the university line)."
    )


def test_the_university_line_is_shown_when_that_default_set_meets_both_minimums(
    purview_world: PurviewWorld,
) -> None:
    """Done-when 7's shown twin: `l…` at exactly the respondent minimum."""
    world = purview_world
    a_lead_straddling_the_readers_department(
        world,
        lead_set=world.respondents_minimum,
        rest=world.respondents_minimum,
        chair="the reader",
    )

    control = world.section_benchmarks("hero")
    read = world.section_benchmarks("hero", reader="the reader")

    assert shown_count(control) >= 1, "The control failed: the instructor-only read shows nothing."
    assert shown_count(read) == shown_count(control), (
        f"The reader is served {shown_count(read)} figures and the instructor alone "
        f"{shown_count(control)}; every piece the reader can subtract meets both minimums."
    )


def test_a_thin_rest_of_the_university_beyond_the_readers_default_sets_withholds_the_line(
    purview_world: PurviewWorld,
) -> None:
    """Done-when 8: U less the reader's sections and less every default set she sees is thin.

    `l…` meets both minimums, so U less what she knows (`l…` and `r…`) does, and
    so does the first extra piece; what is left after removing `l…` as well is
    `r…`, one respondent short.

    **The mutation this kills:** the second extra piece dropped for a reader, or
    computed less the reported section's default set only (empty here), which
    leaves `l…` in and clears.
    **The near miss:** the twin below.
    """
    world = purview_world
    a_lead_straddling_the_readers_department(
        world,
        lead_set=world.respondents_minimum,
        rest=world.respondents_minimum - 1,
        chair="the reader",
    )

    control = world.section_benchmarks("hero")
    read = world.section_benchmarks("hero", reader="the reader")

    assert (
        shown_count(control) >= 1
    ), "The control failed: the hero's instructor alone is served no university figure."
    assert len(every_figure(read)) == len(every_figure(control))
    assert shown_count(read) == 0, (
        f"The reader is served {shown_count(read)} university figures. The university less her "
        "sections and less `s0`'s default set is one department's sections answered by one "
        "respondent fewer than the minimum (SPEC §5.1's second extra piece)."
    )


def test_the_university_line_is_shown_when_the_rest_beyond_the_default_sets_meets_both(
    purview_world: PurviewWorld,
) -> None:
    """Done-when 8's shown twin: `r…` at exactly the respondent minimum."""
    world = purview_world
    a_lead_straddling_the_readers_department(
        world,
        lead_set=world.respondents_minimum,
        rest=world.respondents_minimum,
        chair="the reader",
    )

    control = world.section_benchmarks("hero")
    read = world.section_benchmarks("hero", reader="the reader")

    assert shown_count(control) >= 1, "The control failed: the instructor-only read shows nothing."
    assert shown_count(read) == shown_count(control), (
        f"The reader is served {shown_count(read)} figures and the instructor alone "
        f"{shown_count(control)}; every piece the reader can subtract meets both minimums."
    )
