"""The two named-set reads, asked about a set or a term that is not there — E9-05's interface.

E9-05's interface settles both refusals, below the route:

| Read | Unknown set | Unknown term |
|---|---|---|
| `benchmarks.named_set_series` | answers `[]`, never raises | answers `[]` |
| `comparison_sets.named_set_figures` | `SetUnavailableError`, checked first | `TermUnavailableError` (new) |

The route maps the two errors to its two 404s
(`test_the_named_set_series_route_takes_its_scope_from_the_session.py`). Each
refusal here sits beside the same call for a real set and term answering a
cohort (`docs/MISTAKES.md` entry 3).

**Which failure a red is, before E9-05 lands:** FAILED naming `named_set_series`,
or `named_set_figures` in `app.services.comparison_sets`.
"""

from uuid import uuid4

import pytest
from fixtures.named_set_figures import (
    NAMED_SET_FIGURES,
    NAMED_SET_SERIES,
    SET_UNAVAILABLE_ERROR,
    TERM_UNAVAILABLE_ERROR,
    PurviewWorld,
    benchmarks_symbol,
    cohorts_of,
    comparison_sets_symbol,
)

pytestmark = pytest.mark.integration


def a_lead_and_her_set(world: PurviewWorld) -> None:
    world.build()
    world.course("a", department="home")
    world.section("a-0", course="a")
    world.lead("lead A", "a")
    world.named_set("hers", "a")


def ask(world: PurviewWorld, name: str, *, set_id: object, term_id: object) -> object:
    read = (
        benchmarks_symbol(NAMED_SET_SERIES)
        if name == NAMED_SET_SERIES
        else comparison_sets_symbol(NAMED_SET_FIGURES)
    )
    world.session.flush()
    return read(
        world.session,
        set_id=set_id,
        scope=world.scope("lead A"),
        term_id=term_id,
        settings=world.settings,
    )


def test_the_series_answers_an_empty_list_for_an_unknown_set_or_term(
    purview_world: PurviewWorld,
) -> None:
    """`named_set_series` never raises: an unknown set or term is `[]`; the real pair is not.

    **The mutation this kills:** a lookup that raises (`NoResultFound`, a
    `KeyError`) on a set deleted between the list and the read.
    """
    world = purview_world
    a_lead_and_her_set(world)
    term = world.world.term_id()

    known = ask(world, NAMED_SET_SERIES, set_id=world.set_id("hers"), term_id=term)
    unknown_set = ask(world, NAMED_SET_SERIES, set_id=uuid4(), term_id=term)
    unknown_term = ask(world, NAMED_SET_SERIES, set_id=world.set_id("hers"), term_id=uuid4())

    assert cohorts_of(known), "The control failed: the real set and term answer no cohort."
    assert cohorts_of(unknown_set) == [], f"An unknown set answered {unknown_set!r}, not []."
    assert cohorts_of(unknown_term) == [], f"An unknown term answered {unknown_term!r}, not []."


def test_the_figures_service_refuses_an_unknown_set_before_it_looks_at_the_term(
    purview_world: PurviewWorld,
) -> None:
    """`named_set_figures`: unknown set → `SetUnavailableError`, even with an unknown term.

    **The mutation this kills:** the term checked first, so a request naming a
    set that does not exist and a term that does not exist is told about the
    term — the order the interface fixes is the set first.
    """
    world = purview_world
    a_lead_and_her_set(world)
    term = world.world.term_id()
    set_unavailable = comparison_sets_symbol(SET_UNAVAILABLE_ERROR)

    known = ask(world, NAMED_SET_FIGURES, set_id=world.set_id("hers"), term_id=term)
    assert cohorts_of(list(getattr(known, "cohorts", None) or [])), (
        f"The control failed: `named_set_figures` for the real set and term answered {known!r}, "
        "with no cohort."
    )
    for term_id in (term, uuid4()):
        with pytest.raises(set_unavailable):
            ask(world, NAMED_SET_FIGURES, set_id=uuid4(), term_id=term_id)


def test_the_figures_service_refuses_an_unknown_term_for_a_real_set(
    purview_world: PurviewWorld,
) -> None:
    """`named_set_figures`: real set, unknown term → `TermUnavailableError`, a new class."""
    world = purview_world
    a_lead_and_her_set(world)
    term_unavailable = comparison_sets_symbol(TERM_UNAVAILABLE_ERROR)
    set_unavailable = comparison_sets_symbol(SET_UNAVAILABLE_ERROR)

    assert term_unavailable is not set_unavailable, (
        "`TermUnavailableError` is `SetUnavailableError`; the interface makes it a new class so "
        "the route can answer the two 404s with two sentences."
    )
    with pytest.raises(term_unavailable):
        ask(world, NAMED_SET_FIGURES, set_id=world.set_id("hers"), term_id=uuid4())
