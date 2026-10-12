"""The staff-name door passes purview sections only, seen at the definer — E9-12 done-when 8.

> 8. **The staff-name door passes purview sections only (ruling 3).** A
>    leadership page's call to the door never passes a section outside the
>    reader's purview, asserted at the definer's boundary (the ids it received).
>    Marked `invariant`.

README ruling 3: "The staff-name definer answers any live leadership holder, and
the Python door passes only sections from the reader's resolved purview." For
chair and above (decision 16), the database answers for **any** section the door
passes — so the only thing between a chair and a staff name outside her purview
is what the door hands the definer. That is why this is asserted at the
definer's boundary: every statement the built application sends while a page is
served is recorded with its parameters (`tests/fixtures/
staff_names_for_sections.py::statements_sent`), every call of
`section_staff_names(` is picked out, and every section id among its bound
parameters must be in the reader's purview.

**The purview is computed here from the base tables**, never from `authz`
(`docs/MISTAKES.md` entry 19): for a lead, the sections of the course she leads;
for a chair, the sections of every course under a prefix of her department. **The
world** is E9-03's (`staff_names_for_sections`), E6-05's lead-review world with a
section in a **second department that has no chair** (`Z`). Every page is driven
over HTTP as the reader meets it (`docs/MISTAKES.md` entry 47).

**Present twins:** each page's definer calls include a section of the reader's
own purview (the boundary was observed, not merely silent); and a dean of the
college, whose purview holds `Z`, has `Z` passed — so `Z` is a section the pages
do hand the definer when the reader holds it.

**Expected green on today's branch**; each test names its mutation and near miss.
"""

from typing import Any

import pytest
from fixtures.e9_invariant_pass import (
    body_of,
    column,
    drill_down_url,
    term_of,
    tree_url,
    uuids_in,
)
from fixtures.lead_review import Reader
from fixtures.report_api import FULL_WEEK, TAUGHT_COHORT
from fixtures.staff_names_for_sections import SetWorld, definer_calls, statements_sent

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

DEAN_ROLE = "DEAN"

SECTIONS_OF_A_COURSE = "SELECT id FROM section WHERE course_id = :course"
SECTIONS_OF_A_DEPARTMENT = (
    "SELECT s.id FROM section s JOIN course c ON c.id = s.course_id "
    "JOIN prefix p ON p.id = c.prefix_id WHERE p.department_id = :department"
)
EVERY_SECTION_AMONG = "SELECT id FROM section WHERE id = ANY(CAST(:ids AS uuid[]))"


def sections_passed(sets: SetWorld, reader: Reader, url: str) -> tuple[set[str], int]:
    """The section ids every definer call received while `url` was served to `reader`; the call count."""
    review = sets.review
    with statements_sent() as recorded:
        body_of(review.ask("GET", url, token=reader.token), f"{reader.label} at {url}")
    calls = definer_calls(recorded)
    bound: set[str] = set()
    for call in calls:
        bound |= uuids_in(call.parameters)
    if not bound:
        return set(), len(calls)
    sections = column(review.session, EVERY_SECTION_AMONG, ids=sorted(bound))
    return {str(section).lower() for section in sections}, len(calls)


def ids(values: list[Any]) -> set[str]:
    return {str(value).lower() for value in values}


def test_a_leads_pages_pass_the_definer_only_the_sections_she_leads(
    staff_names_for_sections: SetWorld,
) -> None:
    """Lead A's tree and drill-down: every section the definer received is a section of her course.

    **The present twin:** the tree's definer call received a section of her own
    course. **The forbidden pair named:** the sibling lead's `Y` and the
    chairless department's `Z`.

    **The mutation it kills:** a leadership page calling the door with
    `scope=None` and every section of the prefix (or term) it shows — "pass the
    whole section list to the door"; the door's narrowing to `scope`'s purview
    dropped while a page hands it more. **The near miss it spares:** the page
    passing exactly its held sections, with the scope.
    """
    sets = staff_names_for_sections
    review = sets.review
    assert review.lead is not None
    chairless = ids([sets.a_section_in_a_department_with_no_chair()])
    purview = ids(column(review.session, SECTIONS_OF_A_COURSE, course=review.own_course))
    sibling = ids([review.world.section_id("Y")])
    term = term_of(review)

    tree_passed, tree_calls = sections_passed(sets, review.lead, tree_url(term))
    drill_url = drill_down_url(review.world.section_id(TAUGHT_COHORT), FULL_WEEK)
    drill_passed, _drill_calls = sections_passed(sets, review.lead, drill_url)

    assert tree_calls >= 1 and tree_passed & purview, (
        f"The present twin failed: the lead's tree made {tree_calls} definer calls passing "
        f"{sorted(tree_passed)}, none of them a section of her course {sorted(purview)}."
    )
    outside = {
        "the tree": sorted(tree_passed - purview),
        "the drill-down": sorted(drill_passed - purview),
    }
    outside = {page: found for page, found in outside.items() if found}
    assert not outside, (
        f"The definer received sections outside lead A's purview: {outside} (the sibling lead's "
        f"section is {sorted(sibling)}, the chairless one {sorted(chairless)}). README ruling 3: "
        "the door passes only sections from the reader's resolved purview."
    )


def test_a_chairs_tree_passes_the_definer_only_sections_of_her_department(
    staff_names_for_sections: SetWorld,
) -> None:
    """The chair's tree: every section the definer received is in her department; `Z` is not.

    Decision 16: for chair and above the definer answers any section passed, so
    this boundary is the whole of the protection. **The present twin:** the
    call received sections of her department. **The control:** a dean of the
    college has `Z` passed, so `Z` reaches the definer from a tree that holds it.

    **The mutation it kills:** the tree calling the door with `scope=None` and the
    sections of the college (or term); the door's narrowing dropped. **The near
    miss it spares:** the chair's own department's sections, all of them.
    """
    sets = staff_names_for_sections
    review = sets.review
    assert review.chair is not None
    chairless = ids([sets.a_section_in_a_department_with_no_chair()])
    dean = review.a_leader("e9-12-door-dean", grants=((DEAN_ROLE, review.college),))
    purview = ids(column(review.session, SECTIONS_OF_A_DEPARTMENT, department=review.department))
    term = term_of(review)

    chairs, chair_calls = sections_passed(sets, review.chair, tree_url(term))
    deans, _dean_calls = sections_passed(sets, dean, tree_url(term))

    assert chairless & deans, (
        f"The control failed: the dean's tree passed the definer {sorted(deans)}, not the "
        f"chairless section {sorted(chairless)} her purview holds."
    )
    assert chair_calls >= 1 and chairs & purview, (
        f"The present twin failed: the chair's tree made {chair_calls} definer calls passing "
        f"{sorted(chairs)}, none in her department."
    )
    outside = sorted(chairs - purview)
    assert not outside, (
        f"The chair's tree passed the definer sections outside her department: {outside}. For a "
        "chair the definer answers any section passed (decision 16), so this is a staff name "
        "outside her purview."
    )
