"""Whose sections the instructor section list answers — ticket E4-18, criteria 1 and 2.

E4-18 adds the one thing E4-07 left the client without: a parameterless read that
says which sections the session's person may ask a report about. Its scope is the
narrow one the report routes already carry — "exactly the sections the session's
person holds the teaching-instructor grant over" — and this module is the
assertion that it is that set and no other.

**Both directions, in one world, because either alone is satisfied by a defect.**
A list that answered *every* section would pass any test that only looked for her
own; a route that answered nobody would pass any test that only looked for a
section's absence (`docs/MISTAKES.md` entry 35). So the world holds three
sections: two she teaches, and one another instructor teaches, and the pair of
tests below reads the same answer from both ends.

**The third section is a sibling of her first under one course, and every
ancestor above them is shared.** `Fall2026` seeds both under a single containment
chain, so a read widened to the course, the prefix, the term or the week answers
with the other instructor's section too — and so does one that filters on the
role and forgets the person, which is the near miss a scope query most easily
degrades into. Its absence is therefore a statement about the grant rather than
about the rows happening to be far apart.

**Why this is an absence assertion and not a refused query, stated rather than
implied.** The rule for a §4.1 module is that asserting a name is missing from a
result set is weak, because an empty result passes it for unrelated reasons, and
that the query should instead be *refused*. This route has nothing to refuse:
it takes no parameter, so there is no way to ask it about somebody else's section
and no 404 exists on it (the ticket's public interface says so outright, and its
known traps say the refusal-pair reasoning of the two existing routes does not
transfer). What stands in for the refusal is the surrounding evidence, and it is
all asserted rather than assumed:

  - the answer is **not empty** — her own two sections come back, in the test
    above the absence one;
  - the other instructor's section **exists**, with the grant that makes it
    somebody's rather than nobody's: `tests/fixtures/instructor_sections.py`
    checks both rows before any test runs, and the absence test names the section
    it is looking for by three values read out of the database;
  - the two refusals this route *does* answer — a student session and a request
    carrying no credential at all — are asserted here as refusals, each with the
    control that the session refused is a session that reads what it may.

**Marked `invariant` at the module level**, which puts it in the isolated §4.1
pass and satisfies
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`.
The two role refusals sit here rather than beside the ordinary shape tests
because they are denials: a student session reading an instructor's section list
would be a student-visible path naming other sections, which is §4.1 item 1, and
a denial outside the isolated pass is the state that sweep exists to stop.

**Which failure a red is, before E4-18 lands.** Nothing here imports a deliverable
of this ticket. Every test drives the built application over HTTP, and on a tree
where the route is unbuilt the application answers 404 — so each red is an
assertion about a status or about a list, not an error in anybody's setup
(`docs/MISTAKES.md` entries 44 and 47).
"""

from typing import Any

import pytest
from fixtures.instructor_sections import (
    SECTIONS_PATH,
    InstructorSections,
    entries_in,
    section_ids_in,
    surface_of,
)
from fixtures.report_api import TAUGHT_COHORT, UNTAUGHT_COHORT
from fixtures.student_read import STUDENT_READ_PATH
from fixtures.survey_windows import SECTION_CODE_COLUMN, SECTION_TABLE

pytestmark = [pytest.mark.integration, pytest.mark.invariant]


def every_way_of_naming(world: Any) -> set[str]:
    """Every string that names either section of a report world, read off its rows.

    Both spellings of each uuid and each stored section code: `str(...)` is what
    anything rendering a key produces by default, and `uuid.hex` is the near miss
    that walks through a search for the first — the pair
    `tests/integration/test_the_dev_console_names_nobody.py` had to add after a
    mutation battery walked past it. Read out of the seeded rows rather than
    written here, so what is searched for is what is stored (`docs/MISTAKES.md`
    entry 30).
    """
    key = world.key_of(SECTION_TABLE)
    found: set[str] = set()
    for cohort in (TAUGHT_COHORT, UNTAUGHT_COHORT):
        row = world.section(cohort)
        written = str(row[key])
        found.update({written, written.replace("-", ""), row[SECTION_CODE_COLUMN]})
    return found


def test_her_own_two_taught_sections_come_back_from_the_section_list(
    instructor_sections: InstructorSections,
) -> None:
    """Criterion 1's first half, and the positive control the absence test rests on.

    The launching instructor holds an `INSTRUCTOR` assignment scoped to each of
    two sections — one written by her launch and one by this ticket's fixture,
    both of the shape `record_teaching_instructor` writes and the
    `teaching_instructor` view answers over — so those two are exactly what E4-18
    says she may read. If this route answered nobody, every "the list does not
    name X" assertion in this module would pass and would be a statement about a
    route that answers no one at all (`docs/MISTAKES.md` entry 35).

    **The mutation this kills:** the grant filter narrowed to nothing, or a list
    built from one assignment rather than from all of them — a read that answered
    only the section the launch itself resolved would come back one entry short.

    **The near miss it must not survive:** a list that answered every section of
    the term. That is why the count is asserted as well as the membership, and it
    is the test below that names which extra section such a read would carry.
    """
    answered = instructor_sections.taught_sections()
    ids = section_ids_in(entries_in(answered))

    expected = [str(section.section_id) for section in instructor_sections.hers]
    assert sorted(ids) == sorted(expected), (
        f"`GET {SECTIONS_PATH}` answered {sorted(ids)} for an instructor holding the "
        f"teaching-instructor grant over exactly {sorted(expected)} — the sections coded "
        f"{[section.code for section in instructor_sections.hers]}. Body begins "
        f"{answered.text[:400]!r}.\n\n"
        "Too few and the page cannot open a report for a section she teaches, which is the whole "
        "reason this route exists. Too many and it is naming a section she has no relationship "
        "with."
    )


def test_the_section_list_names_nothing_about_the_section_another_instructor_teaches(
    instructor_sections: InstructorSections,
) -> None:
    """Criterion 1's second half: a section somebody else teaches is planted, and absent.

    The planted section sits under the same course as one of hers, with the same
    term, the same prefix and the same weeks above it, and it carries an
    `INSTRUCTOR` grant of its own held by another person. The only thing that
    separates it from her two is whose grant names it.

    **The mutations this kills:** the grant filter dropped altogether, which
    answers every section in the table; and the near miss it degrades into first —
    a filter that matches on the *role* and not on the *person*, which answers
    every section anybody teaches. The third section is the only row in this world
    that tells those two apart from a correct read, and a join widened to the
    course, the prefix, the term or the week reaches it as well.

    **The whole answer is searched, not the entries.** A section can be named by a
    header, by a member nobody thought to look at, or by a label rather than by an
    id, so the scan runs over the response surface in all three currencies the
    other instructor's section has a name in.
    """
    answered = instructor_sections.taught_sections()
    entries = entries_in(answered)
    assert entries, (
        f"`GET {SECTIONS_PATH}` answered an empty list for an instructor who holds two teaching "
        "grants, so this test's scan is over a response that names nothing whatever the scope "
        "query does (`docs/MISTAKES.md` entry 3). The test above is the one that says which two "
        "should have come back."
    )

    theirs = instructor_sections.another_instructors
    surface = surface_of(answered)
    named = sorted(value for value in theirs.spellings() if value in surface)
    assert not named, (
        f"The section list names {named}, which belong to the section coded {theirs.code} — a "
        "section another person holds the teaching-instructor grant over and this session's person "
        f"does not. Surface begins {surface[:400]!r}.\n\n"
        "That section is a sibling of one of hers under the same course, so a scope query that "
        "widened to the course, or that matched on the role rather than on the person, answers "
        "with it."
    )


def test_a_student_session_is_refused_the_section_list(
    report_door_as: Any, report_api_contract: Any
) -> None:
    """Criterion 2's first half: the role gate, with the control that the session is a session.

    A student session must not read an instructor's section list. The status is
    what says the refusal was the **role** gate rather than anything downstream:
    `require_instructor` refuses a session whose role is not the instructor one
    with the 401 `require_student` uses for the mirror case, and this route has no
    404 for a scope refusal to arrive as.

    **The mutation this kills:** a route that resolves its role from anything but
    the session claims, or `require_instructor` written as "any session that is
    not a student's" and then mounted without it. **The control:** the same
    session, with the same jar emptied, reading `/student/survey` and getting 200
    (`docs/MISTAKES.md` entry 35) — until that is 200, a refusal here says the
    session is not a session rather than that the role was refused.

    **And the refusal names no section**, in either uuid spelling or by code: a
    body that repeated one back would be a student-visible path carrying a section
    the student is not enrolled in, which is §4.1 item 1 arriving through an error
    message.
    """
    door = report_door_as("STUDENT")

    with door.carrying_no_cookie():
        allowed = door.tool.get(STUDENT_READ_PATH, headers=door.credential())
    assert allowed.status_code == 200, (
        f"This student session was answered {allowed.status_code} by `{STUDENT_READ_PATH}`, which "
        "is the route its role certainly reads. Until that is 200 a refusal from the instructor "
        f"section list says nothing about roles. Body begins {allowed.text[:300]!r}."
    )

    with door.carrying_no_cookie():
        answered = door.tool.get(SECTIONS_PATH, headers=door.credential())
    assert answered.status_code == report_api_contract.role_refused_status, (
        f"A student session reading `GET {SECTIONS_PATH}` was answered {answered.status_code}, not "
        f"{report_api_contract.role_refused_status}. Body begins {answered.text[:400]!r}."
    )

    surface = surface_of(answered)
    named = sorted(value for value in every_way_of_naming(door.rows.world) if value in surface)
    assert not named, (
        f"The refusal handed to a student session names {named}. A refusal repeats nothing about "
        f"the institution's sections. Surface begins {surface[:400]!r}."
    )


def test_a_request_carrying_no_session_is_refused_the_section_list(
    instructor_sections: InstructorSections, report_api_contract: Any
) -> None:
    """Criterion 2's second half: no credential, no answer, and no section named.

    The jar is emptied as well as the header left off, so this is an anonymous
    request rather than one carrying the instructor's cookie — without that the
    request under test arrives with a valid session and is answered
    (`docs/disputes/E2-09-01.md` measured exactly that).

    **The mutation this kills:** the route mounted without the session dependency,
    which answers 200 with somebody's sections to a caller who has not signed in;
    and its near miss, a dependency that treats an absent session as a person who
    teaches nothing — which would answer 200 with an empty list rather than
    refusing, and which the status assertion tells apart from the criterion 3
    cases that legitimately answer 200.

    **The control** that this request could have been answered at all is the pair
    of tests above: the same client, the same route, one credential added, answers
    her two sections.
    """
    answered = instructor_sections.without_a_session()
    assert answered.status_code == report_api_contract.role_refused_status, (
        f"A request to `{SECTIONS_PATH}` carrying no session at all was answered "
        f"{answered.status_code} rather than {report_api_contract.role_refused_status}. Body "
        f"begins {answered.text[:400]!r}.\n\n"
        "A 200 here is the section list of somebody who never signed in; a 404 would mean the "
        "route is unbuilt, or that it refuses an anonymous caller by pretending it does not exist "
        "— and this route has no 404, because there is no parameter in this request to refuse."
    )

    surface = surface_of(answered)
    watched = instructor_sections.another_instructors.spellings()
    for section in instructor_sections.hers:
        watched |= section.spellings()
    named = sorted(value for value in watched if value in surface)
    assert not named, (
        f"The refusal handed to an anonymous request names {named}. Surface begins "
        f"{surface[:400]!r}."
    )
