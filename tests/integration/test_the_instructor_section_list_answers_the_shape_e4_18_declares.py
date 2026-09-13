"""What the instructor section list answers, and how — ticket E4-18, criteria 3, 4 and 6.

E4-11's report page has to call E4-07's routes and every one of them takes a
section id; nothing the client holds supplies one. This route is the answer, so
what it *carries* is as load-bearing as who it answers: an entry names its
section by key, by the code a person reads, and by the governed label FIX-01 item
2 settles — the same label the report and the student survey serve.

The three criteria this module asserts:

  - **3.** "A person with no teaching grant, and a session naming no person, each
    get 200 and an empty list." Neither is a state a launch can produce — E1-13
    resolves a landing from the assignment model, so a person with no assignment
    never lands as an instructor at all — so both are minted, and the control that
    a minted session is one this application accepts is a test of its own here.
  - **4.** "The order is the declared one, proven against sections seeded in a
    different order": ascending by `course_label`, then `code`, then `section_id`.
  - **6.** `Cache-Control: no-store`.

**Criterion 1's own assertions are next door**, in
`test_the_instructor_section_list_names_nothing_about_a_section_she_does_not_teach.py`,
which is `invariant`-marked and runs in the isolated §4.1 pass with criterion 2's
two refusals. What is here is the ordinary shape of an answer this instructor is
entitled to, and none of it is a confidentiality assertion.

**The first test is the must-be-green control**, and it is the only one in either
module expected to pass on a tree where E4-18 is unbuilt: it reads E4-07's report
for the section the launch granted her, through the route that already ships. A
red there is this ticket's fixtures failing to plant what they claim — a world
where the grant never landed would answer an empty list to every test in both
modules, and an empty list satisfies every absence assertion there is
(`docs/MISTAKES.md` entries 30 and 35).

**Which failure a red is, before E4-18 lands.** Nothing here imports a deliverable
of this ticket; every test drives the built application over HTTP, and an unbuilt
route answers 404. Each red is therefore an assertion about a status, a list or a
header rather than an error in setup (`docs/MISTAKES.md` entries 44 and 47).
"""

from typing import Any

import pytest
from fixtures.instructor_sections import (
    CACHE_CONTROL_HEADER,
    CODE_FIELD,
    COURSE_LABEL_MEMBER,
    NO_STORE,
    SECTION_ID_FIELD,
    SECTIONS_PATH,
    InstructorSections,
    TaughtSection,
    entries_in,
    section_ids_in,
)
from fixtures.report_api import FULL_WEEK

pytestmark = pytest.mark.integration


def entry_for(section: TaughtSection, entries: list[Any]) -> dict[str, Any]:
    """The one entry naming `section`, or a failure saying which entries came back.

    Found by key rather than by position, so this reads the same whatever order
    the answer is in — the order is the test below's subject and is not smuggled
    into every other assertion here.
    """
    found = [
        entry
        for entry in entries
        if isinstance(entry, dict) and str(entry.get(SECTION_ID_FIELD)) == str(section.section_id)
    ]
    if len(found) != 1:
        pytest.fail(
            f"{len(found)} of the {len(entries)} entries name the section coded {section.code} "
            f"({section.section_id}). The answer carries {entries!r}.\n\n"
            "Nought is a section she holds the teaching-instructor grant over and the list does "
            "not carry; two is one section answered twice, which would make the page open the "
            "same report from two rows."
        )
    return found[0]


def test_the_seeded_instructor_reads_the_existing_report_for_the_section_she_teaches(
    instructor_sections: InstructorSections,
) -> None:
    """The control this ticket's whole world rests on — green before E4-18 is built.

    Every other test in both of this ticket's modules is a statement about a
    teaching grant: that her sections come back, that another instructor's does
    not, that a person holding none is answered an empty list. All of them are
    equally satisfied by a world where no grant was ever written — the list would
    be empty and the absences would hold for a reason that has nothing to do with
    scope (`docs/MISTAKES.md` entry 30).

    So this reads E4-07's report for her first section through the route that
    already ships. A 200 there is the shipped authorization chokepoint saying she
    holds the teaching-instructor grant over that section, measured rather than
    assumed — and the chokepoint E4-18's list is required to agree with.

    **What it does not cover, said plainly** (`docs/MISTAKES.md` entry 14): her
    *second* grant and the other instructor's are written by this ticket's own
    fixture and E4 ships no route that reads either one on its own, so they are
    checked as rows — `tests/fixtures/instructor_sections.py` counts the
    assignments each person holds before any test runs, and both are written by
    the same call whose result this test measures.

    **The mutation this kills:** a fixture that plants no grant at all, or plants
    one for a person no request resolves to.
    """
    answered = instructor_sections.door.report(course_week=FULL_WEEK)
    assert answered.status_code == 200, (
        f"E4-07's report for the section this session's launch granted her answered "
        f"{answered.status_code}. That route is shipped and its scope is the same "
        "teaching-instructor grant E4-18 lists, so a refusal here means this world's grant is not "
        f"in place and no test of this ticket is measuring what it says. Body begins "
        f"{answered.text[:400]!r}."
    )


def test_a_minted_instructor_session_for_her_own_person_reads_her_own_two_sections(
    instructor_sections: InstructorSections,
) -> None:
    """The control the two empty-list cases rest on: a minted session is a session.

    Criterion 3's two cases cannot be launched into existence, so they are minted
    — and each expects a 200. A minted token this application declined for a
    reason of its own would answer both with a refusal, and the pair would read
    exactly like a route that refuses a person who teaches nothing rather than
    answering them an empty list (`docs/MISTAKES.md` entry 35).

    This session is minted by the same helper, carrying the same three claims her
    launched session carries. A 200 with her two sections says the minting is
    sound; a refusal here says the two tests below are about the minting rather
    than about the route.

    **The mutation this kills:** a session helper that signs with the wrong
    secret, states the wrong door or names the wrong role — each of which would
    make the two cases below fail against a correct implementation.
    """
    answered = instructor_sections.taught_sections(
        token=instructor_sections.a_session_minted_for_her()
    )
    ids = section_ids_in(entries_in(answered))
    expected = [str(section.section_id) for section in instructor_sections.hers]
    assert sorted(ids) == sorted(expected), (
        f"A session minted for her own person was answered {sorted(ids)} rather than "
        f"{sorted(expected)}. Body begins {answered.text[:400]!r}."
    )


def test_a_person_holding_no_teaching_grant_is_answered_an_empty_list(
    instructor_sections: InstructorSections,
) -> None:
    """Criterion 3's first half: an empty teaching set is an ordinary state, not a refusal.

    The ticket is explicit that this is a 200 with an empty list rather than a
    refusal of any kind: "An empty teaching set is an ordinary state (the student
    analog: an empty list is between terms), and there is no parameter in this
    request to refuse". The person named here holds no assignment at all, and is
    named both ways a request could resolve one — the `person_id` claim and a
    linked `user` row — so the case does not rest on which the implementer reads.

    **The mutation this kills:** a handler that treats an empty teaching set as a
    404 or a 403, which is the shape an implementation reaches for when it copies
    the refusal pair of the two existing routes; the ticket's known traps say that
    reasoning does not transfer, because there is no id in this request to
    enumerate with. Its near miss is a 200 whose body is an error object rather
    than an empty list, which is why the `sections` member is read rather than the
    status alone.
    """
    answered = instructor_sections.taught_sections(
        token=instructor_sections.a_session_naming_a_person_with_no_teaching_grant()
    )
    entries = entries_in(answered)
    assert entries == [], (
        f"An instructor session for a person holding no teaching grant was answered {entries!r}. "
        "That person holds no `role_assignment` row of any kind, so there is no section this list "
        f"could name. Body begins {answered.text[:400]!r}."
    )


def test_a_session_naming_no_person_is_answered_an_empty_list(
    instructor_sections: InstructorSections,
) -> None:
    """Criterion 3's second half: a session that resolves to nobody is answered nothing.

    ADR 0028 makes "no person" a defined session-carried state rather than an
    error, and E4-18 answers it the same way it answers a person who teaches
    nothing: 200, empty list. The session minted here names a `user` row no
    `person` points at and carries a null person claim, so neither way of
    resolving a person finds one.

    **The mutation this kills:** a handler that assumes a person and raises — an
    unhandled `None` reaching the scope query is a 500, which is this route
    failing on a state the ticket says is ordinary. Its near miss is the same
    handler refusing with a 401, which would be indistinguishable from the role
    gate firing; the test above, whose session names a person and is answered
    two sections, is what tells the two apart.
    """
    answered = instructor_sections.taught_sections(
        token=instructor_sections.a_session_naming_no_person()
    )
    entries = entries_in(answered)
    assert entries == [], (
        f"An instructor session naming no person was answered {entries!r} rather than an empty "
        f"list. Body begins {answered.text[:400]!r}."
    )


def test_the_entries_are_ordered_by_course_label_and_not_by_section_code(
    instructor_sections: InstructorSections,
) -> None:
    """Criterion 4: the declared order, over sections seeded in a different one.

    The order the ticket declares is ascending by `course_label`, then `code`,
    then `section_id`, "so the page renders stably and nothing about submission or
    creation order leaks into it". Her two sections are built so that the three
    candidate orders are three different answers:

      - **creation order** is the launch's section first, hers-under-the-second-
        course second;
      - **code order** is the same, because `F1WW` sorts before `H1WW`;
      - **label order** is the reverse, because the second section hangs off a
        course numbered `099` under the same prefix and the seeding walker numbers
        every course it invents in 100-799.

    So the expected answer is the reverse of the order the rows were written in,
    and it is written out here rather than computed by sorting — an expectation
    produced by the same arithmetic as the code under test agrees with an
    implementation that got it wrong (`docs/MISTAKES.md` entry 19).

    **The mutations this kill:** no ordering at all (which usually answers in
    creation or key order), and an ordering on `code` alone — the near miss that
    every section of one course cannot tell apart, since a label carries its own
    section code in the middle.

    **What it does not reach** (`docs/MISTAKES.md` entry 14): the second and third
    keys of the order. Two sections with equal labels would have to be two
    sections of one course with one code, which E0-06's uniqueness rule refuses,
    so `code` and `section_id` as tie-breakers are unreachable from a world this
    schema permits and nothing here asserts them.

    The premises are asserted before the order is, because both rest on values the
    seeding walker invented and a world where they no longer hold would make this
    test pass while measuring nothing.
    """
    launched, second_course = instructor_sections.hers
    assert second_course.course_label < launched.course_label, (
        "This test needs her second section's label to sort first, and the two labels are\n"
        f"  {second_course.course_label!r}\n  {launched.course_label!r}\n"
        "Both sections sit under one prefix, so the course number decides: `099` against the "
        "number the seeding walker invented. If the walker's range has moved, "
        "`HER_SECOND_COURSE_NUMBER` in tests/fixtures/instructor_sections.py is the one line that "
        "changes."
    )
    assert launched.code < second_course.code, (
        f"This test needs the code order to disagree with the label order, and the codes are "
        f"{launched.code!r} and {second_course.code!r}. With the two agreeing, an implementation "
        "ordering by `code` alone answers exactly what the declared order answers and nothing "
        "here would notice."
    )

    answered = instructor_sections.taught_sections()
    ids = section_ids_in(entries_in(answered))
    assert ids == [str(second_course.section_id), str(launched.section_id)], (
        f"The list answered {ids} for the sections coded "
        f"{[launched.code, second_course.code]} (in the order they were written). The declared "
        f"order puts {second_course.code} first, because its course label sorts first — the "
        "reverse of both the creation order and the code order. Body begins "
        f"{answered.text[:400]!r}."
    )


def test_the_answer_carries_cache_control_no_store(
    instructor_sections: InstructorSections,
) -> None:
    """Criterion 6: `Cache-Control: no-store`, like every answer this module serves.

    The list names the sections one instructor teaches, so a browser or an
    intermediate cache holding a copy after she signs out on a shared machine goes
    on saying what she teaches.

    **The mutation this kills:** the header left off the new route while the two
    existing routes keep theirs — nothing else in this suite would notice, because
    E2-15's pair asserts it of the student routes only.

    **The near miss it must survive:** a header present and spelled some other way
    — `no-cache`, `private`, `max-age=0` — each of which still lets a cache retain
    the body under some conditions. Compared as an exact value, the way E2-15's
    own pair compares it.
    """
    answered = instructor_sections.taught_sections()
    assert answered.status_code == 200, (
        f"`GET {SECTIONS_PATH}` answered {answered.status_code} for the instructor whose sections "
        f"it lists, so this test's header assertion would be about a refusal. Body begins "
        f"{answered.text[:400]!r}."
    )
    header = answered.headers.get(CACHE_CONTROL_HEADER)
    assert header == NO_STORE, (
        f"`GET {SECTIONS_PATH}` answered with `{CACHE_CONTROL_HEADER}: {header!r}` rather than "
        f"`{NO_STORE}`."
    )


def test_each_entry_carries_the_section_id_the_code_and_the_governed_course_label(
    instructor_sections: InstructorSections,
) -> None:
    """Criterion 1's shape half: id, code and the governed label, on every entry.

    The id is what E4-07's routes are asked with and is compared as the uuid
    string; the code is what the page shows a reader; and the label is FIX-01 item
    2's governed form, `<prefix code> <lms_number> <section code> — <lms_title>,
    <term name>` — "the same form the report's `section.course_label` and the
    student survey serve". Each expected value is composed from the seeded rows by
    `tests/fixtures/student_read.py`'s own reader, which is the one place that
    form is spelled in this suite, rather than by a second copy in this ticket.

    **The mutations these kill:** an entry carrying the section's key under some
    other spelling — `uuid.hex` is the near miss, and it is why the id is compared
    against `str(...)` rather than searched for; a code taken from anywhere but
    the section's own `lms_section_code`; and a label built from a shorter form —
    the course title alone, or the code alone — which is the shape a second
    composer written for this route would take.

    **Both her sections are read, not one.** They differ in the course above them,
    so a label composed from the world's first course for every entry — or from
    the *term's* only course, since the walker builds one per chain — passes
    against one section and fails against the other.
    """
    entries = entries_in(instructor_sections.taught_sections())
    assert len(entries) == len(instructor_sections.hers), (
        f"The list carries {len(entries)} entries for an instructor holding "
        f"{len(instructor_sections.hers)} teaching grants: {entries!r}."
    )

    for section in instructor_sections.hers:
        entry = entry_for(section, entries)
        assert entry.get(SECTION_ID_FIELD) == str(section.section_id), (
            f"The entry for the section coded {section.code} carries "
            f"{entry.get(SECTION_ID_FIELD)!r} as its `{SECTION_ID_FIELD}`, and the section's key "
            f"is {str(section.section_id)!r}. E4-07's routes are asked with this value, so a "
            "spelling they do not accept — a hyphen-stripped uuid among them — is a page that "
            "cannot open a report at all."
        )
        assert entry.get(CODE_FIELD) == section.code, (
            f"The entry for {section.section_id} carries `{CODE_FIELD}` "
            f"{entry.get(CODE_FIELD)!r}; the section's stored `lms_section_code` is "
            f"{section.code!r}."
        )
        assert entry.get(COURSE_LABEL_MEMBER) == section.course_label, (
            f"The entry for the section coded {section.code} carries\n"
            f"  {entry.get(COURSE_LABEL_MEMBER)!r}\n"
            f"and FIX-01 item 2's governed label for that section is\n"
            f"  {section.course_label!r}\n\n"
            "The ticket makes this member the same form the report's `section.course_label` and "
            "the student survey serve, so a label built any other way for this route is a second "
            "answer to what a section is called."
        )
