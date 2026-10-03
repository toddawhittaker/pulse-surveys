"""The hero section's default comparison set, over the world the demo seed leaves.

`scripts/seed_benchmark_history.py` says in its own opening comment that after it
runs "the hero section's comparison set has something in it", and ADR 0167 argues
the same. Asked of `app.services.benchmarks.resolve_default_set`, that sentence is
false today: the default set is the hero course's Lead Faculty, their courses, and
those courses' sections of the hero's length and level — so a hero course with no
lead-faculty mapping has an empty default set however many prior-term sections were
launched under it, and `scripts/seed.py` maps a lead to every demo course except
BIOL 310.

**This module asks the service, not the world.** Every other test of the prior-term
world counts rows or section codes, and a count by code cannot see this defect at
all: the sections are there, they are the right length, they are in the right term,
and the set is still empty. The only reading that answers the claim is the resolver's
own, which is why these tests reach through `app.services.benchmarks` rather than
through a query of their own.

**Two directions, both real.** BIOL 310's sections must resolve into the hero's set;
`BIOL-215-R3WW`'s must not resolve into anything, because BIOL 215 deliberately has
no lead and E5-10's browser spec uses it as the suppressed direction. A fix that gave
every course a lead would turn the first test green and the third red, which is the
pair working.

**The world is planted rather than launched, and the seeder is not run.** What the
resolvers need is the sections, and the sections are what a staff launch and a roster
sync leave behind — `plant_one_launch` in `tests/fixtures/benchmark_history.py` writes
exactly those rows. Nothing here needs a response, so the benchmark-history seeder is
not run at all: it fills weeks that no resolution reads, and a world built out of its
refusals would make these tests depend on a program whose claim they exist to check.

**What that choice costs, and the guard that pays it.** Naming the seven placements here
means a rename in the mock platform's seed would leave this module planting a world
nobody launches, green and meaningless. The last test is that guard: every label
planted here has to appear in `mock-lms/app/seed.py`, which is where the placements are
declared, and a label that is certainly not there has to be absent — a canary, so a
sweep that has gone blind says so (`docs/MISTAKES.md` entry 3).

**Guards are in the test bodies** (`docs/MISTAKES.md` entry 44). The builder never
raises: it hands back a world carrying `problem`, and `require_the_world` is the first
statement of every test that reads one.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
from fixtures.benchmark_history import (
    SECTION_TABLE,
    PlantedLaunch,
    fall_2026,
    plant_one_launch,
    prior_term,
    rows_of,
)
from fixtures.benchmark_views import (
    RESOLVE_DEFAULT_SET,
    RESOLVE_UNIVERSITY,
    benchmarks_api,
)
from fixtures.repo import REPO_ROOT
from fixtures.supervision import require_table, single_primary_key
from fixtures.survey_windows import SECTION_LENGTH_COLUMN

pytestmark = pytest.mark.integration

# The seven placements, transcribed from the contexts the mock platform offers in
# `mock-lms/app/seed.py` — the file that declares them — and held to that file by the
# last test in this module. A label is the whole `BIOL-310-R7FF` a person writes; the
# bare `R7FF` is what `section.lms_section_code` stores, and `plant_one_launch` makes
# the conversion.
#
#   - `BIOL-310-R7FF` is the hero: the demo section every report screen is driven
#     against, twelve weeks from the current term's `R` start.
#   - The three prior-term BIOL 310 sections are the set the hero is supposed to be
#     compared with. All three are twelve weeks, which the controls below read back
#     from the database rather than assume.
#   - `BIOL-215-E5WW` is the prior term's short cohort — six weeks under the `E`
#     letter — and is the length half of the exclusion.
#   - `BIOL-215-R3WW` is the current-term section E5-10's browser spec uses as its
#     suppressed direction, and BIOL 215 has no lead faculty on purpose.
#   - `BIOL-215-U8FF` is the fifth prior-term section, added by E5-14's exit-demo
#     fix: twelve weeks, undergraduate, on BIOL 215, which has no lead. It is in the
#     hero's university population and not in its default set, so the demo's
#     university line differs from its comparison line (the freeze's earliest-close
#     cutoff otherwise reduced the university to exactly the default set).
HERO_LABEL = "BIOL-310-R7FF"
PRIOR_SET_LABELS = ("BIOL-310-U5FF", "BIOL-310-U6WW", "BIOL-310-R5FF")
PRIOR_SHORT_LABEL = "BIOL-215-E5WW"
PRIOR_UNLED_LABEL = "BIOL-215-U8FF"
UNLED_LABEL = "BIOL-215-R3WW"

PRIOR_LABELS = (*PRIOR_SET_LABELS, PRIOR_SHORT_LABEL, PRIOR_UNLED_LABEL)
CURRENT_LABELS = (HERO_LABEL, UNLED_LABEL)
EVERY_LABEL = (*PRIOR_LABELS, *CURRENT_LABELS)

# Where those placements are declared. Read as text by the last test, never imported.
MOCK_PLATFORM_SEED = REPO_ROOT / "mock-lms" / "app" / "seed.py"

# A label in the same shape that no platform offers, for the sweep's canary. `Z9` is
# not a start letter any seeded map holds, so a search that matches this has stopped
# being a search for these placements.
A_LABEL_NO_PLATFORM_OFFERS = "BIOL-310-Z9WW"

# How many students each planted section carries. **One, and it is a cost decision
# rather than a statement about the world**: nothing here reads an enrollment, a
# response or a roster, and the twenty of the real world would be a hundred and forty
# rows this module never looks at. `tests/fixtures/benchmark_history.py` carries the
# roster-shaped default for the tests that do read one.
STUDENTS_PER_PLANTED_SECTION = 1

# The length the hero's cohort runs, and the length the three prior sections have to
# share for §5.1 to make them comparable. **Not assumed**: every one of those four is
# read back out of the database and checked against this before any resolution is
# asserted, so a prior term whose start-letter map gives `U` or `R` some other length
# is reported as a world that does not match the ticket rather than as a service that
# resolved wrongly.
COHORT_LENGTH_WEEKS = 12


@dataclass
class ComparisonWorld:
    """A seeded demo institution with seven placements planted into it.

    **`problem` rather than a raised failure**, because this is built in a
    module-scoped fixture and a `pytest.fail` there is an ERROR in setup that proves
    nothing about any criterion (`docs/MISTAKES.md` entry 44). Every test calls
    `require_the_world` as its first statement instead.
    """

    demo: Any = None
    launches: dict[str, PlantedLaunch] = field(default_factory=dict)
    problem: str | None = None

    def section_id(self, label: str) -> Any:
        """The id of the section planted for one label, or a failure naming the gap."""
        launch = self.launches.get(label)
        if launch is None:
            pytest.fail(
                f"This world planted no section for {label}; it planted {sorted(self.launches)}."
            )
        return launch.section_id


def require_the_world(world: ComparisonWorld) -> ComparisonWorld:
    """Stop with the build's own sentence unless the planted world is there."""
    if world.problem is not None:
        pytest.fail(world.problem)
    return world


@pytest.fixture(scope="module")
def comparison_world(
    demo_databases: Any, plant_in: Any, metadata_tables: dict[str, Any]
) -> ComparisonWorld:
    """One database of its own, seeded, with the seven placements planted into it.

    A database of its own rather than the module database, because these rows are a
    launch's and the seed's idempotency tests compare a database against itself.
    Module-scoped because building it is the expensive part and every test below only
    reads.
    """
    demo = demo_databases()
    seeded = demo.run()
    if not seeded.succeeded:
        return ComparisonWorld(
            demo=demo,
            problem=(
                "`scripts/seed.py` failed against a fresh migrated database, so the world these "
                f"tests are stated over never existed.\n{seeded.report()}\nE0-17 owns whether that "
                "run succeeds and `tests/integration/test_demo_seed_script.py` is where a failure "
                "here should be read."
            ),
        )

    world = ComparisonWorld(demo=demo)
    try:
        earlier = prior_term(demo, metadata_tables, seeded)
        current = fall_2026(demo, metadata_tables, seeded)
        for label in PRIOR_LABELS:
            world.launches[label] = plant_one_launch(
                demo,
                plant_in,
                metadata_tables,
                earlier,
                label,
                students=STUDENTS_PER_PLANTED_SECTION,
            )
        for label in CURRENT_LABELS:
            world.launches[label] = plant_one_launch(
                demo,
                plant_in,
                metadata_tables,
                current,
                label,
                students=STUDENTS_PER_PLANTED_SECTION,
            )
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as broke:
        # `BaseException`, because `pytest.fail` raises `Failed`, which does not derive
        # from `Exception`: the guards inside `plant_one_launch` would otherwise come
        # back as setup ERRORs and read as a broken suite rather than as a builder with
        # a wrong idea in it (`docs/MISTAKES.md` entry 44).
        world.problem = (
            f"{broke}\n\n"
            f"(Raised while planting the seven placements: {broke!r}. That is a defect in this "
            "module's world or in a schema it no longer matches — not a failed criterion. A "
            "start letter the planted term's map does not hold is the likeliest cause, and it "
            "is a statement about the seeded calendar rather than about the benchmark service.)"
        )
    return world


@contextmanager
def resolving(world: ComparisonWorld) -> Iterator[Any]:
    """A session on the planted database, opened as the identity production uses.

    **The application role, not the migrating one** (`docs/MISTAKES.md` entry 46): the
    default set is resolved through `public.lead_faculty_course`, a view E0-10 grants
    to `pulse_app` and to nobody else, and a suite that drove this service through the
    superuser connection would report a missing grant as a passing resolution.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(world.demo.database.application_url)
    try:
        with Session(bind=engine) as session:
            yield session
    finally:
        engine.dispose()


def resolved(world: ComparisonWorld, name: str, section_id: Any) -> list[Any]:
    """One resolver's answer for one section, as a list of section ids."""
    api = benchmarks_api()
    with resolving(world) as session:
        return list(api[name](session, section_id=section_id))


def section_row(world: ComparisonWorld, tables: dict[str, Any], label: str) -> dict[str, Any]:
    """The `section` row one label was planted as, read back out of the database.

    Read by primary key rather than by the bare §2.2 code, which is the currency that
    column stores and is **not** unique: `U5FF` names a section in every term whose map
    holds a `U`, and a lookup by code alone would answer about whichever one it met
    first. The id came from the plant, so the row it names is the placement's own —
    course, term and code together.
    """
    key = single_primary_key(require_table(dict(tables), SECTION_TABLE))
    found = rows_of(world.demo, tables, SECTION_TABLE, **{key: world.section_id(label)})
    assert len(found) == 1, (
        f"The database holds {len(found)} `{SECTION_TABLE}` rows at the id this module planted "
        f"{label} as. Every assertion below is about that row, and there is no such row to be "
        "about."
    )
    return found[0]


def require_the_planted_world(world: ComparisonWorld, tables: dict[str, Any]) -> None:
    """The readable-something control: the seven placements are there, and the four cohorts match.

    Called as the second statement of every test that asserts a resolution, and it is
    not ceremony. A resolution that answers nothing is the correct answer over a world
    that holds nothing, so "the set is empty" and "the set is missing its members" are
    the same sentence until the sections are known to exist; and the three prior
    sections belong in the hero's set only while they run the hero's length, which is a
    property of the seeded start-letter maps rather than of this module.
    """
    absent = [label for label in EVERY_LABEL if label not in world.launches]
    assert not absent, (
        f"This world planted no section for {absent}; it planted {sorted(world.launches)}. Every "
        "assertion below names those placements, so a missing one makes the answer meaningless "
        "rather than wrong."
    )

    lengths = {
        label: section_row(world, tables, label)[SECTION_LENGTH_COLUMN] for label in EVERY_LABEL
    }
    cohort = (HERO_LABEL, *PRIOR_SET_LABELS, PRIOR_UNLED_LABEL)
    wrong = {
        label: lengths[label] for label in cohort if int(lengths[label]) != COHORT_LENGTH_WEEKS
    }
    assert not wrong, (
        f"{wrong} do not run {COHORT_LENGTH_WEEKS} weeks, and every section in the hero's own "
        f"cohort does: the lengths planted are {lengths}. SPEC §2.2 derives a section's length "
        "from its term's start-letter map, so this is the seeded calendar disagreeing with the "
        "world E5-12 describes rather than the benchmark service resolving wrongly — and §5.1 "
        "makes the hero's set the sections matching it on length, so the assertion below would "
        "be demanding a section the service is right to leave out."
    )
    assert int(lengths[PRIOR_SHORT_LABEL]) != COHORT_LENGTH_WEEKS, (
        f"{PRIOR_SHORT_LABEL} runs {lengths[PRIOR_SHORT_LABEL]} weeks, which is the hero's own "
        "length. It is planted here to be the section §5.1 excludes for its length, and at the "
        "hero's length its exclusion below would be satisfied by a service that never looked."
    )


def test_the_hero_sections_default_set_holds_the_prior_sections_of_its_own_course(
    comparison_world: ComparisonWorld, metadata_tables: dict[str, Any]
) -> None:
    """The claim `scripts/seed_benchmark_history.py` makes: the hero's set has something in it.

    SPEC §5.1 makes the default set "the same Lead Faculty's courses filtered to
    matching length+level", past-referencing into prior terms. The three prior-term
    BIOL 310 sections are the hero's own course, the hero's own length and the hero's
    own level, so a hero course with a lead resolves to all three of them.

    **The mutation this kills**: the lead-faculty mapping for the hero's course gone —
    which is the state the repository is in today, with `scripts/seed.py` mapping a lead
    to BIOL 101, MATH 040, MATH 210, MATH 505, STAT 250, CSCI 240 and PSYC 110 and to no
    BIOL 310. Nothing else in the suite sees it: the sections exist, carry the right
    codes, sit in the right term and run the right length, so every recount by section
    code reports a world that is complete while the product draws no comparison line at
    all.

    **The controls, and why each one is load-bearing.** The seven placements are read back
    out of the database first, so an empty set cannot be an empty world. Then the
    university population for the same section is required to hold the three: it is
    resolved over the same rows without consulting the lead-faculty mapping, so it says
    the service can see this world and reached these sections — and an empty default set
    beside a populated university line is the mapping and nothing else.

    **Containment rather than equality, said plainly.** This asserts that the three are
    in the set, not that the set is exactly the three. Which person leads BIOL 310 is
    the implementer's to choose, and a lead who also leads another course running a
    twelve-week section of the same level would add it to this set legitimately; an
    equality here would make that choice for them. The sections that must *not* be in
    the set are asserted by the test below, which is where the over-broad resolutions
    are caught.
    """
    world = require_the_world(comparison_world)
    require_the_planted_world(world, metadata_tables)

    hero = world.section_id(HERO_LABEL)
    wanted = {world.section_id(label) for label in PRIOR_SET_LABELS}

    university = set(resolved(world, RESOLVE_UNIVERSITY, hero))
    assert wanted <= university, (
        "The control failed before the assertion it protects: the university population for the "
        f"hero holds {sorted(map(str, university))}, which does not cover the three prior-term "
        f"BIOL 310 sections {sorted(map(str, wanted))}. That population is resolved over the same "
        "rows without reading the lead-faculty mapping, so until it finds them, an empty default "
        "set says nothing about the mapping — it says the service cannot see this world."
    )

    default_set = set(resolved(world, RESOLVE_DEFAULT_SET, hero))
    missing = {
        label: str(world.section_id(label))
        for label in PRIOR_SET_LABELS
        if world.section_id(label) not in default_set
    }
    assert not missing, (
        f"The hero's default comparison set resolves to {sorted(map(str, default_set))} and is "
        f"missing {missing}. `scripts/seed_benchmark_history.py` says that after it runs 'the hero "
        "section's comparison set has something in it' and ADR 0167 rests on the same sentence; "
        "through the service it is false while no Lead Faculty is mapped to the hero's course, "
        "because §5.1 resolves the default set as that lead's courses filtered to the hero's "
        "length and level. An empty set here is a demo whose headline screen draws no comparison "
        "line, with every count of sections and respondents still reporting a complete world."
    )


def test_the_hero_sections_default_set_excludes_itself_a_shorter_cohort_and_an_unled_course(
    comparison_world: ComparisonWorld, metadata_tables: dict[str, Any]
) -> None:
    """The three sections that must stay out, each out for a different reason.

    E5-04's decision 5 takes the hero out of its own set; §5.1 takes out anything of
    another length; and "the same Lead Faculty's courses" takes out a section under a
    course this lead does not lead. `BIOL-215-R3WW` is the sharpest of the three: it is
    the same twelve weeks and the same level as the hero, in the same term, so the only
    thing keeping it out is whose course it is.

    **The mutations this kills**: the hero left in its own comparison set, which
    flatters or damns a section against itself; the length filter dropped, which
    averages a six-week cohort into a twelve-week one — the thing §5.1 forbids in its
    first sentence; and the lead-faculty filter dropped, which draws the university line
    twice and hands a Lead Faculty a benchmark computed over a colleague's course
    (§4.1 item 2's shape, reached through a benchmark).

    **Red today, on its own control, and that is the honest order.** The set is empty
    while the hero's course has no lead, and an exclusion asserted over an empty set is
    satisfied by the defect it is meant to catch (`docs/MISTAKES.md` entry 3). So the
    set is required to hold the three prior sections first, and only then asked what
    else is in it.
    """
    world = require_the_world(comparison_world)
    require_the_planted_world(world, metadata_tables)

    hero = world.section_id(HERO_LABEL)
    default_set = set(resolved(world, RESOLVE_DEFAULT_SET, hero))
    wanted = {world.section_id(label) for label in PRIOR_SET_LABELS}

    assert wanted <= default_set, (
        "The control failed before the assertions it protects: the hero's default set resolves to "
        f"{sorted(map(str, default_set))} and does not hold the three prior-term BIOL 310 sections "
        f"{sorted(map(str, wanted))}. Over an empty set every exclusion below is true, including "
        "against a service that resolves nothing at all — which is the state this epic's own "
        "sibling test reports."
    )

    assert hero not in default_set, (
        f"The hero section {hero} is in its own default comparison set "
        f"{sorted(map(str, default_set))}. E5-04's decision 5 excludes it: a section compared "
        "against a population containing itself is measured partly against its own responses, and "
        "the thinner the cohort the more of the line is the section itself."
    )

    short = world.section_id(PRIOR_SHORT_LABEL)
    assert short not in default_set, (
        f"{PRIOR_SHORT_LABEL} ({short}) is in the hero's default set "
        f"{sorted(map(str, default_set))}. It is the same course prefix and the same lead's "
        "department, and it runs a different number of weeks. SPEC §5.1: 'to be comparable, "
        "sections must match on both length and level' — a six-week cohort averaged into a "
        "twelve-week line is the comparison that section forbids."
    )

    unled = world.section_id(UNLED_LABEL)
    assert unled not in default_set, (
        f"{UNLED_LABEL} ({unled}) is in the hero's default set {sorted(map(str, default_set))}. It "
        "runs the hero's length in the hero's term at the hero's level, and its course has no lead "
        "faculty — so the only thing that can have put it there is a resolution that stopped "
        "asking whose courses these are. That is the university line drawn under the default "
        "set's name, and on a real institution it is a lead reading a colleague's course."
    )


def test_a_current_term_section_whose_course_has_no_lead_resolves_to_no_default_set(
    comparison_world: ComparisonWorld, metadata_tables: dict[str, Any]
) -> None:
    """The suppressed direction, and it has to stay suppressed.

    BIOL 215 has no lead-faculty mapping on purpose: SPEC §2.1's "a course with no
    mapping falls to its department chair" needs a course to be true of, E0-17 criterion
    8 asks the seed for one, and E5-10's browser spec drives `BIOL-215-R3WW` as the
    section whose comparison line is absent. So the fix that gives the hero's course a
    lead must not give this one one.

    **The mutation this kills**: a lead-faculty mapping written for every seeded course,
    or for BIOL 215 in place of BIOL 310 — either of which turns E5-10's suppressed
    direction into a section that draws a comparison line, and the browser spec asserting
    its absence would then be red for a reason nobody would look for here.

    **The control is the university population for the same section**, which must hold
    the hero: it proves the query ran against a world this service can see, so the empty
    default set is about the missing mapping rather than about a section the service
    cannot resolve anything for at all.

    **Deliberately not marked `invariant`.** This asserts an absence, and the §4.1 pass
    is for refusals — a benchmark that resolves to nothing is a scope fact, not a denial,
    and putting an absence assertion in that pass would misdescribe what it guarantees.
    """
    world = require_the_world(comparison_world)
    require_the_planted_world(world, metadata_tables)

    unled = world.section_id(UNLED_LABEL)
    hero = world.section_id(HERO_LABEL)

    university = set(resolved(world, RESOLVE_UNIVERSITY, unled))
    assert hero in university, (
        "The control failed before the assertion it protects: the university population for "
        f"{UNLED_LABEL} is {sorted(map(str, university))} and does not hold the hero section "
        f"{hero}, which runs the same length at the same level in the same term. Until it does, "
        "an empty default set below is a query that found nothing for some reason this test is "
        "not about."
    )

    default_set = resolved(world, RESOLVE_DEFAULT_SET, unled)
    assert default_set == [], (
        f"{UNLED_LABEL}'s default comparison set resolves to {sorted(map(str, default_set))}. Its "
        "course has no lead-faculty mapping, and §5.1 draws the default set from 'the same Lead "
        "Faculty's courses' — with no such person there are no such courses. E0-17 criterion 8 "
        "keeps one seeded course deliberately unmapped so SPEC §2.1's fall-to-chair path is "
        "exercised in development, and E5-10's browser spec reads this section as the one whose "
        "comparison line is absent."
    )


def test_the_fifth_prior_term_section_is_in_the_heros_university_and_not_its_default_set(
    comparison_world: ComparisonWorld, metadata_tables: dict[str, Any]
) -> None:
    """E5-14's exit-demo fix: `BIOL-215-U8FF` widens the university, not the default set.

    The epic-exit review found the seeded demo's university line equal to its
    comparison line: the current-term U cohort has no answers but its windows
    close first, so the freeze's earliest-close cutoff counts no current-term
    answer, and the university reduced to the three Spring 2026 BIOL 310
    sections — exactly the default set. The fix is a fifth prior-term section on
    BIOL 215, which has no lead: the hero's length and level, so it is in the
    university population, and no lead, so it is in no default set.

    **The control** is the three BIOL 310 prior sections in the default set, so
    the absence below is not an empty set.

    **The mutations this kills:** the fifth section planted on a led course
    (BIOL 310, or any course with a mapping), which would put it in the default
    set and leave the two lines equal again; and one of another length or level,
    which would leave it out of the university. **Red first** through this
    module's last test until `mock-lms/app/seed.py` declares the placement.
    """
    world = require_the_world(comparison_world)
    require_the_planted_world(world, metadata_tables)

    hero = world.section_id(HERO_LABEL)
    fifth = world.section_id(PRIOR_UNLED_LABEL)
    university = set(resolved(world, RESOLVE_UNIVERSITY, hero))
    default_set = set(resolved(world, RESOLVE_DEFAULT_SET, hero))
    wanted = {world.section_id(label) for label in PRIOR_SET_LABELS}

    assert wanted <= default_set, (
        "The control failed: the hero's default set "
        f"{sorted(map(str, default_set))} does not hold the three prior-term BIOL 310 sections."
    )
    assert fifth in university and fifth not in default_set, (
        f"{PRIOR_UNLED_LABEL} ({fifth}) is {'in' if fifth in university else 'not in'} the hero's "
        f"university population and {'in' if fifth in default_set else 'not in'} its default set. "
        "It is planted at the hero's length and level on a course with no lead, so it belongs to "
        "the first and not the second — which is what makes the demo's two lines differ."
    )


def test_the_placements_this_module_plants_are_the_ones_the_mock_platform_offers() -> None:
    """The tripwire under this module's own world.

    These tests plant seven placements by name instead of discovering them, which is what
    makes them cheap and readable — and it means a rename in `mock-lms/app/seed.py`
    would leave this module planting sections nobody launches, still green, still
    asserting a comparison set that no demo will ever draw. So every label planted here
    has to be a label that file declares.

    **The canary is the half that makes the sweep evidence** (`docs/MISTAKES.md` entry
    3): a label in the same shape that no platform offers has to be absent, so a search
    that has stopped matching anything — a moved file, an unreadable path, a pattern
    that matches everything — says so instead of passing quietly.
    """
    assert MOCK_PLATFORM_SEED.is_file(), (
        f"{MOCK_PLATFORM_SEED} does not exist, so this sweep read nothing and the seven labels this "
        "module plants are held to nothing at all. The mock platform's placements are declared "
        "there; a move is a one-line change to `MOCK_PLATFORM_SEED` in this module."
    )
    declared = MOCK_PLATFORM_SEED.read_text(encoding="utf-8")

    missing = [label for label in EVERY_LABEL if label not in declared]
    assert not missing, (
        f"{missing} are planted by this module and are not declared in {MOCK_PLATFORM_SEED}. The "
        "world these tests reason over is the one the mock platform offers for launch; a label "
        "only this module knows about is a world nobody can drive, and the tests above would go "
        "on passing over it."
    )
    assert A_LABEL_NO_PLATFORM_OFFERS not in declared, (
        f"{A_LABEL_NO_PLATFORM_OFFERS} appears in {MOCK_PLATFORM_SEED}. It is this sweep's canary "
        "— a label in the same shape that no platform offers — and finding it means the check "
        "above cannot tell a declared placement from an undeclared one."
    )
