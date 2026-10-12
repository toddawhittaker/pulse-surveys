"""The seal covers what one person can subtract across every hat she wears — E9-05.

> 6. **The seal covers both hats.** A Math chair teaches Biology section T. The
>    university line U for a report the chair reads, as chair or as T's
>    instructor, is suppressed when U less Math less T is non-empty and one
>    respondent below a minimum, and shown at the minimum. The twin: the same
>    world with the chair not teaching T, where U less Math meets both minimums
>    and U is shown. Marked `invariant`.
> 16. **The two extra pieces count a two-hat instructor's purview.** The
>    instructor of the reported section also chairs department D, and a section
>    in D belongs to a course whose lead also leads a course outside D, of the
>    same term, length and level. She reads her own report with no leadership
>    reader passed. (a) … that lead's default set less her sections is non-empty
>    and one respondent below a minimum: U is suppressed, and at the minimum it
>    is shown. (b) U less her sections and every such default set is non-empty
>    and one respondent below a minimum: U is suppressed, and at the minimum it
>    is shown. A twin with the chair assignment removed shows U, which proves the
>    piece came from the purview. Marked `invariant`.

SPEC §5.1 (E9-05's replacement sentence): for each instructor of the reported
section, "her sections are every section she teaches together with, if she also
holds a leadership assignment, every section in her leadership purview"; and a
leader is sealed "with the same sections as her sections".

**How the university figures are recognised.** Every reported section here is
on a course nobody else leads, so its default set is empty and its comparison
figures are suppressed in every read; every *shown* figure is a university
figure, and two reads of one world are compared by how many they show
(`test_the_benchmark_seal_counts_a_leadership_reader.py` says why the members
are not named). Each suppression sits beside a read of the same world in which
the university line is shown (`docs/MISTAKES.md` entry 3).

**Which failure a red is, before E9-05 lands:** the reads that name a reader
FAIL naming `section_benchmarks`' missing `scope`; the reads with no reader run,
and their suppression assertions FAIL, because today an instructor's sections
are only those she teaches.
"""

from decimal import Decimal

import pytest
from fixtures.named_set_figures import (
    PurviewWorld,
    a_lead_straddling_the_readers_department,
    every_figure,
    one_section_course,
    shown_count,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

MATH_RATING, MATH_HOURS = Decimal("4"), Decimal("6.5")
T_RATING, T_HOURS = Decimal("5"), Decimal("1.5")
BIO_RATING, BIO_HOURS = Decimal("3"), Decimal("11.5")
T_RESPONDENTS = 2


# ---------------------------------------------------------------------------
# Done-when 6: a Math chair who teaches Biology section T.
# ---------------------------------------------------------------------------


def a_math_chair_and_biology(world: PurviewWorld, *, biology: int, teaches_t: bool) -> None:
    """Math (`m1…`, the minimums' worth) and Biology (T, and `b1…` answered by `biology` people).

    The chair holds `CHAIR` on Math and, when `teaches_t`, an `INSTRUCTOR`
    assignment on T. `m1` is taught by a Math teacher with no leadership
    assignment, whose own seal hides nothing in this world — her read of `m1` is
    the control. Every course is led by nobody else, so no default set is in
    play and only "U less her sections" decides.
    """
    world.build()
    sections, respondents = world.sections_minimum, world.respondents_minimum
    math = [f"m{index}" for index in range(1, sections + 1)]
    bio = [f"b{index}" for index in range(1, sections + 1)]
    for label in math:
        one_section_course(world, label, "math", alone=True)
    one_section_course(world, "T", "biology", alone=True)
    for label in bio:
        one_section_course(world, label, "biology", alone=True)
    world.chair("the chair", "math")
    world.teach("the math teacher", "m1")
    if teaches_t:
        world.teach("the chair", "T")

    world.answer(
        math, respondents=respondents, prefix="e9-05-hats-m", rating=MATH_RATING, hours=MATH_HOURS
    )
    world.answer(
        ["T"], respondents=T_RESPONDENTS, prefix="e9-05-hats-t", rating=T_RATING, hours=T_HOURS
    )
    world.answer(
        bio, respondents=biology, prefix="e9-05-hats-b", rating=BIO_RATING, hours=BIO_HOURS
    )


def test_a_chair_who_teaches_t_has_the_university_line_withheld_under_both_hats(
    purview_world: PurviewWorld,
) -> None:
    """U less Math less T is one respondent short: withheld from T's report and from Math's.

    Two reads, one per hat: T's own report, which she reads as T's instructor
    with no reader passed; and `m1`'s report read with her as the reader (the
    drill-down's call). Each knows Math (her purview) and T (taught).

    **The control, same world:** the Math teacher's own read of `m1` shows the
    university line.

    **The mutations this kills:** an instructor's sections without her purview
    (T's report shows U); a reader's sections without what she teaches (the
    reader's read shows U); the reader and the instructor de-duplicated by
    something other than person, so one of the two hats is dropped.
    **The near misses:** the twin at the minimum, and the twin without T.
    """
    world = purview_world
    a_math_chair_and_biology(world, biology=world.respondents_minimum - 1, teaches_t=True)

    control = world.section_benchmarks("m1")
    as_instructor = world.section_benchmarks("T")
    as_chair = world.section_benchmarks("m1", reader="the chair")

    assert shown_count(control) >= 1, (
        "The control failed: the Math teacher's own read of `m1` shows no university figure, in a "
        "world where nothing she knows leaves a thin remainder."
    )
    assert len(every_figure(as_instructor)) == len(every_figure(control))
    assert shown_count(as_instructor) == 0, (
        f"T's report, read by its instructor — who also chairs Math — shows "
        f"{shown_count(as_instructor)} university figures. U less Math less T is Biology's other "
        "sections, one respondent short of the minimum, and she can read Math's figures and T's "
        "(SPEC §5.1: her sections include her leadership purview)."
    )
    assert shown_count(as_chair) == 0, (
        f"`m1`'s report, read with the chair as the reader, shows {shown_count(as_chair)} "
        "university figures. Her known set is Math (purview) and T (taught), and U less both is "
        "one respondent short of the minimum."
    )


def test_a_chair_who_teaches_t_is_shown_the_university_line_at_the_minimum(
    purview_world: PurviewWorld,
) -> None:
    """The twin at the minimum: Biology's other sections answered by exactly the minimum."""
    world = purview_world
    a_math_chair_and_biology(world, biology=world.respondents_minimum, teaches_t=True)

    control = world.section_benchmarks("m1")
    as_instructor = world.section_benchmarks("T")
    as_chair = world.section_benchmarks("m1", reader="the chair")

    assert shown_count(control) >= 1, "The control failed: the Math teacher's read shows nothing."
    assert shown_count(as_instructor) == shown_count(control), (
        f"T's report shows {shown_count(as_instructor)} figures and the control "
        f"{shown_count(control)}; U less Math less T meets both minimums."
    )
    assert shown_count(as_chair) == shown_count(control), (
        f"The chair's read shows {shown_count(as_chair)} figures and the control "
        f"{shown_count(control)}; U less Math less T meets both minimums."
    )


def test_a_chair_who_does_not_teach_t_is_shown_the_university_line(
    purview_world: PurviewWorld,
) -> None:
    """The twin without the teaching hat: U less Math (T and Biology) meets both — shown.

    **The mutation this kills:** a seal that withholds from a chair whatever her
    purview touches, regardless of what is left; together with the first test,
    it proves the withholding there came from T being hers.
    """
    world = purview_world
    a_math_chair_and_biology(world, biology=world.respondents_minimum - 1, teaches_t=False)

    control = world.section_benchmarks("m1")
    as_chair = world.section_benchmarks("m1", reader="the chair")

    assert shown_count(control) >= 1, "The control failed: the Math teacher's read shows nothing."
    assert shown_count(as_chair) == shown_count(control), (
        f"The chair, who does not teach T, is shown {shown_count(as_chair)} figures and the "
        f"control {shown_count(control)}. U less Math is T and Biology's other sections, which "
        "together meet both minimums."
    )


# ---------------------------------------------------------------------------
# Done-when 16: a two-hat instructor's purview reaches the university's two extra
# pieces, with no reader passed.
# ---------------------------------------------------------------------------


def the_control_read(world: PurviewWorld) -> int:
    """`r1`'s report: a section nobody teaches, so only its population is sealed.

    Same university population as the hero's, empty default set — so the count
    of figures it shows is the count of university figures a read can show.
    """
    shown = shown_count(world.section_benchmarks("r1"))
    assert shown >= 1, (
        "The control failed: `r1`'s report, which nobody teaches, shows no university figure, so "
        "the university population of this world cannot be shown to anybody."
    )
    return shown


@pytest.mark.parametrize(
    "thin_piece",
    ("the lead's default set", "the rest of the university"),
    ids=("first-extra-piece", "second-extra-piece"),
)
def test_a_two_hat_instructor_has_the_university_line_withheld_on_her_own_report(
    purview_world: PurviewWorld, thin_piece: str
) -> None:
    """Done-when 16 (a) and (b): her own report, no reader passed, withheld.

    The hero's instructor chairs `home`, which holds `s0`; `s0`'s lead also
    leads `l…` in `away`. Her sections are the hero and `home` (purview). In (a)
    `l…` — `s0`'s default set less her sections — is one respondent short; in
    (b) `l…` meets both minimums and `r…`, the university less her sections and
    less `l…`, is one short.

    **The mutation this kills:** `lead_sets_seen` and the second remainder built
    from her taught sections only — E5-14's rule, under which both pieces are
    empty here and U is shown. **The near misses:** the twins at the minimum and
    without the chair assignment.
    """
    world = purview_world
    respondents = world.respondents_minimum
    thin = thin_piece == "the lead's default set"
    a_lead_straddling_the_readers_department(
        world,
        lead_set=respondents - 1 if thin else respondents,
        rest=respondents if thin else respondents - 1,
        chair="the teacher",
    )

    control = the_control_read(world)
    own = world.section_benchmarks("hero")

    assert shown_count(own) == 0, (
        f"The hero's report, read by its instructor with no reader passed, shows "
        f"{shown_count(own)} university figures (the control shows {control}). She chairs `home` "
        f"and so reads `s0`'s figures and its default-set line; {thin_piece} less her sections is "
        "one respondent short of the minimum (SPEC §5.1, E9-05 done-when 16)."
    )


@pytest.mark.parametrize(
    "piece",
    ("the lead's default set", "the rest of the university"),
    ids=("first-extra-piece", "second-extra-piece"),
)
def test_a_two_hat_instructor_is_shown_the_university_line_at_the_minimum(
    purview_world: PurviewWorld, piece: str
) -> None:
    """Done-when 16's shown twins: each piece at exactly the respondent minimum."""
    world = purview_world
    respondents = world.respondents_minimum
    a_lead_straddling_the_readers_department(
        world, lead_set=respondents, rest=respondents, chair="the teacher"
    )

    control = the_control_read(world)
    own = world.section_benchmarks("hero")

    assert shown_count(own) == control, (
        f"The hero's report shows {shown_count(own)} figures and the control {control}; with "
        f"{piece} at the minimum every piece she can subtract meets both minimums."
    )


@pytest.mark.parametrize(
    "thin_piece",
    ("the lead's default set", "the rest of the university"),
    ids=("first-extra-piece", "second-extra-piece"),
)
def test_without_the_chair_assignment_the_same_instructor_is_shown_the_university_line(
    purview_world: PurviewWorld, thin_piece: str
) -> None:
    """Done-when 16's last sentence: the same thin world, the chair assignment removed — shown.

    Her sections are then the hero alone, both extra pieces are empty for her,
    and U less the hero meets both minimums. So the withholding above came from
    her purview and from nothing else in the world.
    """
    world = purview_world
    respondents = world.respondents_minimum
    thin = thin_piece == "the lead's default set"
    a_lead_straddling_the_readers_department(
        world,
        lead_set=respondents - 1 if thin else respondents,
        rest=respondents if thin else respondents - 1,
        chair=None,
    )

    control = the_control_read(world)
    own = world.section_benchmarks("hero")

    assert shown_count(own) == control, (
        f"With no chair assignment, the hero's instructor is shown {shown_count(own)} figures and "
        f"the control {control}. She knows the hero only, and U less the hero meets both minimums."
    )
