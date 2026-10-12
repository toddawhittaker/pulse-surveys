"""E9-12 — the §4.1 pass over E9's read paths: the routes, the readers, and what a body holds.

Eight test modules ask E9's four read routes the same questions, so the driving
and the readers live here and each module asserts (`docs/MISTAKES.md` entry 13).
This module holds **no fixtures**, so it is imported by name rather than listed
in `tests/conftest.py`'s `pytest_plugins` (the conftest docstring indexes it with
the other import-only modules).

**The four routes, as the pull requests that built them spell them** (E9-12's
work order names the bodies):

  - E9-07: `GET /leadership/rollup?term_id=` answers `{term_id, hierarchy,
    by_lead}`, tree nodes carrying `kind`, `id`, `name`, `label`,
    `section_count` and `children`; `GET /leadership/rollup/{kind}/{node_id}
    ?term_id=` answers one node's `cohorts` and §5.6's `attention` cards (each
    card carrying `rule`, `section_id`, `course_week`). A node outside the
    purview and a node that does not exist get one 404 and one sentence.
  - E9-05: `GET /leadership/comparison-sets/{set_id}/series?term_id=` answers
    `{cohorts: [{section_start_date, weeks: [...]}]}`.
  - E9-09: `GET /leadership/sections/{section_id}/weeks/{course_week}/report`
    answers the instructor's own report payload, read-only; a section outside
    the purview and one that does not exist get the same 404 and sentence.

Every scope comes only from `leadership_scope` (E9-01), so every request here is
a Bearer request carrying one leadership session and nothing else, through the
built application as `pulse_app` (`docs/MISTAKES.md` entries 46 and 47).

**Nothing here decides an answer.** It builds URLs, plants rows, swaps the one
shared owed read for a test that needs a card on every section, and reads bodies
as plain data; every expectation is written in the test that makes it
(`docs/MISTAKES.md` entries 19 and 30). Every guard is a plain function a test
body calls, so a missing deliverable is a FAILED naming it (entry 44).
"""

import json
import re
from collections.abc import Iterator, Mapping
from typing import Any

import pytest

from fixtures.named_sets import series_path

TREE_PATH = "/leadership/rollup"

# The node kinds a figures read is asked for: every level of the tree above a
# section. A section has no figures route of its own in E9-07's pull request.
FIGURE_KINDS = ("college", "department", "prefix", "course")

# The by-lead groups a chair's tree offers (E9-07: `by_lead` holds `lead` and
# `no_lead` groups), which the figures route also answers for chair and above.
BY_LEAD_KINDS = ("lead", "no_lead")

# The owed card's rule token (E9-07's attention test spells it).
OWED_RULE = "response_owed"

# Stems ruling 2 forbids on any roll-up response: a comment (and so a comment
# count), a summary, a theme. The same three E9-07's schema sweep reads, here read
# off the wire rather than off the models.
COMMENT_STEMS = ("comment", "summar", "theme")

# A cohort label: "{letters} sections · started M/D" (SPEC §2.2; the ruling on
# `docs/disputes/E9-07-01.md`), copied from E9-07's seeded cohort test.
COHORT_LABEL = re.compile(r"(?P<letters>[^ ]+) sections · started (?P<month>\d+)/(?P<day>\d+)")

UUID_TEXT = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


# ---------------------------------------------------------------------------
# URLs.
# ---------------------------------------------------------------------------


def tree_url(term_id: Any) -> str:
    return f"{TREE_PATH}?term_id={term_id}"


def figures_url(kind: str, node_id: Any, term_id: Any) -> str:
    return f"{TREE_PATH}/{kind}/{node_id}?term_id={term_id}"


def series_url(set_id: Any, term_id: Any) -> str:
    return f"{series_path(set_id)}?term_id={term_id}"


def drill_down_url(section_id: Any, course_week: int) -> str:
    return f"/leadership/sections/{section_id}/weeks/{course_week}/report"


# ---------------------------------------------------------------------------
# Reading an answer.
# ---------------------------------------------------------------------------


def answer(response: Any) -> tuple[int, Any]:
    """The status and the whole body, as the reader receives them."""
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text
    return response.status_code, body


def body_of(response: Any, what: str) -> Any:
    """The decoded body of a 200, or a FAILED saying what came instead.

    A body decoded off a refusal is one every later absence is vacuously true of
    (`docs/MISTAKES.md` entry 3), so the status is required first.
    """
    if response.status_code != 200:
        pytest.fail(
            f"{what} answered {response.status_code}, not 200. Body begins "
            f"{response.text[:400]!r}."
        )
    return response.json()


def dumped(value: Any) -> str:
    """One answer as canonical text, keys and values alike, for a substring search."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def found_in(value: Any, needles: Mapping[str, str]) -> dict[str, str]:
    """Which of `needles` (what -> text) occur anywhere in `value`'s text, keys included."""
    text = dumped(value)
    return {what: needle for what, needle in needles.items() if needle and needle in text}


def keys_in(value: Any) -> set[str]:
    """Every mapping key at any depth."""
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            found.add(str(key))
            found |= keys_in(item)
    elif isinstance(value, list | tuple):
        for item in value:
            found |= keys_in(item)
    return found


def comment_shaped_keys(value: Any) -> list[str]:
    """Every key in `value` naming a comment, a summary or a theme, by stem."""
    return sorted(
        key for key in keys_in(value) if any(stem in key.lower() for stem in COMMENT_STEMS)
    )


def canonical(value: Any) -> Any:
    """`value` with every list sorted by its own canonical text, for order-free equality.

    Comment display order is randomised (SPEC §4), so two reads of one report are
    equal as sets and not as sequences; this is the comparison "answered from the
    same scope" needs, and nothing here uses it to compare orders.
    """
    if isinstance(value, Mapping):
        return {str(key): canonical(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return sorted((canonical(item) for item in value), key=dumped)
    return value


def every_node(nodes: Any) -> Iterator[dict[str, Any]]:
    """Every tree node at any depth, parents before children."""
    for node in nodes or []:
        if isinstance(node, Mapping):
            yield dict(node)
            yield from every_node(node.get("children"))


def tree_nodes(tree: Any) -> list[dict[str, Any]]:
    """Every node of a tree answer: the hierarchy, and the by-lead groups when offered."""
    found = list(every_node(tree.get("hierarchy")))
    found += list(every_node(tree.get("by_lead") or []))
    return found


def node_with_id(tree: Any, node_id: Any) -> dict[str, Any] | None:
    matched = [node for node in tree_nodes(tree) if str(node.get("id")) == str(node_id)]
    return matched[0] if matched else None


def descendants(node: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every node below `node`, not `node` itself."""
    return list(every_node(node.get("children")))


def cohort_letters(figures: Any) -> set[str]:
    """Every start letter the cohort labels of one figures answer carry."""
    letters: set[str] = set()
    for cohort in figures.get("cohorts") or []:
        matched = COHORT_LABEL.fullmatch(str(cohort.get("label", "")))
        if matched:
            letters |= set(matched.group("letters").split("/"))
    return letters


def uuids_in(text: str) -> set[str]:
    return {found.lower() for found in UUID_TEXT.findall(text)}


# ---------------------------------------------------------------------------
# The shared owed read, swapped so every section a page hands it is owed.
# ---------------------------------------------------------------------------


def owe_every_section(monkeypatch: pytest.MonkeyPatch, course_week: int = 1) -> list[list[str]]:
    """Make `rollups.owed_section_weeks` answer every section it is handed as owed.

    E9-07's settled interface: `app.services.rollups` imports `owed_section_weeks`
    by name, and §5.6's rule 4 card is made from what it answers. Swapping it is
    how a test puts a card on every section a node's figures were computed over —
    so a card naming a section is evidence that the page *handed the section to
    the owed read*, which is exactly "the page computed over it". The rule itself
    is E9-07's subject and is not tested here. Answers the list the calls are
    recorded on (the section ids each call was handed), so a test can show the
    swap was reached.
    """
    import app.services.rollups as rollups

    if not hasattr(rollups, "owed_section_weeks"):
        pytest.fail(
            "`app.services.rollups` has no `owed_section_weeks`; E9-07's settled interface "
            "imports the shared owed read there by name."
        )
    calls: list[list[str]] = []

    def owed(*args: Any, **kwargs: Any) -> set[tuple[Any, int]]:
        sections = kwargs.get("section_ids")
        if sections is None and len(args) > 1:
            sections = args[1]
        sections = list(sections or [])
        calls.append([str(section) for section in sections])
        return {(section, course_week) for section in sections}

    monkeypatch.setattr(rollups, "owed_section_weeks", owed)
    return calls


# ---------------------------------------------------------------------------
# Worlds.
# ---------------------------------------------------------------------------


def term_of(review: Any) -> Any:
    """The lead-review world's one term, by key."""
    from fixtures.supervision import require_table, single_primary_key
    from fixtures.survey_windows import TERM_TABLE

    world = review.world
    return world.calendar.term[single_primary_key(require_table(world.tables, TERM_TABLE))]


def scalar(session: Any, sql: str, **values: Any) -> Any:
    """One value read on the seeding session, after ending its old snapshot."""
    from sqlalchemy import text

    session.rollback()
    found = session.execute(text(sql), values).scalar_one()
    session.rollback()
    return found


def column(session: Any, sql: str, **values: Any) -> list[Any]:
    """One column read on the seeding session, after ending its old snapshot."""
    from sqlalchemy import text

    session.rollback()
    found = list(session.execute(text(sql), values).scalars())
    session.rollback()
    return found


def a_named_set(review: Any, *course_keys: Any, length: int, level_of: Any) -> Any:
    """A named set declaring `length` weeks at `level_of`'s level, over `course_keys`; its key.

    Planted with `tests/fixtures/comparison_sets.py`'s own helpers, the way
    E9-05's series-route test plants one, and committed (the tool connects for
    itself).
    """
    from sqlalchemy import select

    from fixtures.comparison_sets import (
        COMPARISON_SET_TABLE,
        LENGTH_COLUMN,
        LEVEL_COLUMN,
        member_of,
        membership_table,
    )
    from fixtures.supervision import require_table, single_primary_key

    world = review.world
    tables = world.tables
    courses = require_table(tables, "course")
    course_key = single_primary_key(courses)
    session = review.session
    session.flush()
    level = session.execute(
        select(courses.c["level"]).where(courses.c[course_key] == level_of)
    ).scalar_one()
    stored = world.seed(COMPARISON_SET_TABLE, {}, **{LENGTH_COLUMN: length, LEVEL_COLUMN: level})
    for key in course_keys:
        statement = select(courses).where(courses.c[course_key] == key)
        row = dict(session.execute(statement).mappings().one())
        member_of(world.seed, membership_table(tables), stored, row)
    review.rows.commit()
    return stored[single_primary_key(require_table(tables, COMPARISON_SET_TABLE))]


def readers_at_the_report_door(
    report_door: Any, committed_rows: Any, web_identity: Any, configured: Mapping[str, str]
) -> Any:
    """`LeadReviewWorld`'s session minting and asking, over the bare report world.

    The benchmark worlds (`tests/fixtures/report_benchmarks.py`) map their own lead
    to the report world's course, so they cannot sit beside the lead-review world,
    which maps lead A to the same course (one lead per course). This builds the
    reader machinery without that world: no sibling course, no lead A, no chair —
    a test names every reader it mints.
    """
    from fixtures.instructor_decisions import DecisionDoor
    from fixtures.lead_review import LeadReviewWorld

    door = DecisionDoor(report_door, configured)
    return LeadReviewWorld(door, committed_rows, web_identity, configured)
