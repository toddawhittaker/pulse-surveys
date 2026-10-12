"""The seal's statement count does not grow with the reader's purview — E9-05's fix round, P3.

> P3 (data MED). Widening `known` to the whole leadership purview makes the
> default-set resolution N+1 over the purview. … TEST: the number of statements
> issued for one section's benchmarks by a teaching leader does not grow with the
> size of her purview (a narrow and a wide purview of different sizes issue the
> same number).

**The world.** Two chairs, each teaching a section (`hero-…`) of a course in her
own department that nobody else leads, so the reported section's own default set
is empty. Each department also holds:

  - `alone` one-section courses, each led by a person who leads nothing else, so
    each is a section of the purview whose default set is empty; and
  - one course with `led` sections, whose lead also leads a three-section
    course in a shared `away` department, so every one of those sections is a
    section of the purview with a default set, and all of them leave the same
    remainder (`away-…`) once the reader's known set is taken out.

The narrow chair has one of each. The wide chair has six of one kind and one of
the other, by parameter: six more courses whose default sets must be resolved
(**`more-courses`**, the per-section resolution the review measured), or six
more sections behind the one lead (**`more-sections-of-one-lead`**, the
aggregate per lead set the review named). Each chair reads her own section's
benchmarks with herself as the reader — a teaching leader in both of the seal's
seats.

**Every piece clears both minimums**, in both reads, so neither read takes a
shorter path for having found a thin piece first; the two reads are required to
answer the same number of figures in the same states before their statements are
compared.

**The counting device** is E9-01's (`fixtures.statements.statements_recorded`,
whose own control lives in
`test_the_purview_walk_is_transitive_and_batched_by_level.py`). The scopes are
resolved and the session flushed *before* recording, so the purview walk —
batched by depth, not width, under E9-01 — is not in the count; a warm-up read of
each runs first, so a one-time statement is counted against neither.

**Which failure a red is, before the fix:** an assertion that the wide read sent
more statements than the narrow one, listing the wide read's statements.
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.named_set_figures import (
    SECTION_BENCHMARKS,
    SECTION_CUTOFFS,
    STREAMS,
    THE_COURSE_WEEK,
    PurviewWorld,
    benchmarks_symbol,
    every_figure,
    one_section_course,
    shown_count,
    suppressed_count,
    the_hero_answers,
)
from fixtures.statements import statements_recorded

pytestmark = pytest.mark.integration

NARROW = 1
WIDE = 6
AWAY_SECTIONS = 3


def a_teaching_chair(world: PurviewWorld, tag: str, *, alone: int, led: int) -> str:
    """A chair of department `tag` who teaches `hero-<tag>`; answers the chair's name.

    The department holds `hero-<tag>`, `alone` courses led by nobody else, and
    course `c-<tag>` with `led` sections, whose lead also leads `away-<tag>`
    (three sections, in the shared `away` department).
    """
    respondents = world.respondents_minimum
    chair = f"chair {tag}"
    hero = f"hero-{tag}"
    one_section_course(world, hero, tag, alone=True)
    alone_labels = [f"{tag}-alone{index}" for index in range(1, alone + 1)]
    for label in alone_labels:
        one_section_course(world, label, tag, alone=True)
    led_course, away_course = f"c-{tag}", f"away-{tag}"
    world.course(led_course, department=tag)
    led_labels = [f"{led_course}{index}" for index in range(1, led + 1)]
    for label in led_labels:
        world.section(label, course=led_course)
    world.course(away_course, department="away")
    away_labels = [f"{away_course}{index}" for index in range(1, AWAY_SECTIONS + 1)]
    for label in away_labels:
        world.section(label, course=away_course)
    world.lead(f"lead {tag}", led_course, away_course)
    world.chair(chair, tag)
    world.teach(chair, hero)

    the_hero_answers(world, hero)
    for group, labels in (("alone", alone_labels), ("led", led_labels), ("away", away_labels)):
        world.answer(
            labels,
            respondents=respondents,
            prefix=f"e9-05-p3-{tag}-{group}",
            rating=Decimal("4"),
            hours=Decimal("6.5"),
        )
    return chair


def benchmarks_read_by(world: PurviewWorld, section_id: Any, scope: Any) -> Any:
    """`section_benchmarks` for one section's course week 2, with `scope` as the reader."""
    read = benchmarks_symbol(SECTION_BENCHMARKS)
    return read(
        world.session,
        section_id=section_id,
        course_week=THE_COURSE_WEEK,
        streams=STREAMS,
        cutoffs=SECTION_CUTOFFS,
        scope=scope,
    )


@pytest.mark.parametrize(
    ("alone", "led"),
    ((WIDE, NARROW), (NARROW, WIDE)),
    ids=("more-courses", "more-sections-of-one-lead"),
)
def test_a_teaching_leader_with_a_wide_purview_sends_as_many_statements_as_one_with_a_narrow_one(
    purview_world: PurviewWorld, alone: int, led: int
) -> None:
    """The narrow read and the wide read send the same number of statements.

    **The mutations this kills:** `resolve_default_set` called once per section
    of the purview (two statements per section, the review's N+1); an aggregate
    sent once per section's default set rather than once per distinct set to
    seal against; the default sets resolved again for each reader of one call.
    **The near miss it spares:** any constant number of statements per read,
    however large, so long as it does not depend on how many sections the
    reader's purview holds.

    **The controls in the body:** the two purviews are the sizes planted (so
    "wide" really is wider), both reads answer the same figures in the same
    states (so neither took a shorter path), and both counts are non-zero (so
    something was measured).
    """
    world = purview_world
    world.build()
    narrow_chair = a_teaching_chair(world, "narrow", alone=NARROW, led=NARROW)
    wide_chair = a_teaching_chair(world, "wide", alone=alone, led=led)

    narrow_scope = world.scope(narrow_chair)
    wide_scope = world.scope(wide_chair)
    narrow_purview = frozenset(narrow_scope.purview.section_ids)
    wide_purview = frozenset(wide_scope.purview.section_ids)
    for tag, purview, planted in (
        ("narrow", narrow_purview, 1 + NARROW + NARROW),
        ("wide", wide_purview, 1 + alone + led),
    ):
        in_department = {
            world.section_id(label)
            for label in world.world.sections
            if label == f"hero-{tag}" or label.startswith((f"{tag}-alone", f"c-{tag}"))
        }
        assert len(in_department) == planted and in_department <= purview, (
            f"The {tag} chair's purview does not hold the {planted} sections planted in her "
            "department; a broken world, not a red."
        )
    assert len(wide_purview) > len(narrow_purview), (
        f"The wide purview holds {len(wide_purview)} sections and the narrow one "
        f"{len(narrow_purview)}; the comparison below would measure nothing."
    )
    narrow_hero, wide_hero = world.section_id("hero-narrow"), world.section_id("hero-wide")
    world.session.flush()

    warm_narrow = benchmarks_read_by(world, narrow_hero, narrow_scope)
    warm_wide = benchmarks_read_by(world, wide_hero, wide_scope)
    assert len(every_figure(warm_narrow)) == len(every_figure(warm_wide)) > 0
    assert shown_count(warm_narrow) == shown_count(warm_wide) >= 1, (
        f"The narrow read shows {shown_count(warm_narrow)} figures and the wide read "
        f"{shown_count(warm_wide)}; every piece in this world clears both minimums, so the two "
        "reads should take the same path. A broken world, not a red."
    )
    assert suppressed_count(warm_narrow) == suppressed_count(warm_wide)

    with statements_recorded() as narrow:
        benchmarks_read_by(world, narrow_hero, narrow_scope)
    with statements_recorded() as wide:
        benchmarks_read_by(world, wide_hero, wide_scope)

    assert narrow and wide, (
        f"The narrow read sent {len(narrow)} statements and the wide read {len(wide)}. A read "
        "that sends nothing cannot have computed a figure."
    )
    assert len(wide) == len(narrow), (
        f"A teaching leader whose purview holds {len(wide_purview)} sections sent {len(wide)} "
        f"statements for one section's benchmarks, and one whose purview holds "
        f"{len(narrow_purview)} sent {len(narrow)}. E9-05 fix round, P3: the default sets are "
        "resolved for every section needed in one query, so the count does not grow with the "
        "purview. The wide read sent:\n" + "\n".join(statement.sql[:160] for statement in wide)
    )
