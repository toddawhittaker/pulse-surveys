"""The set preview answers two counts and nothing else — E5-06.

Criterion 5: "The preview returns counts, never section names or figures — a
reader below the minimums learns a count of sections, which §5.1 treats as safe
at set-definition time." Work-order decision 5 fixes the two numbers:
`member_count` is the set's membership rows and `section_count` is
`len(resolve_named_set(session, set_id=...))` — E5-04 is merged, so the section
count is in scope and its contingency does not apply.

**A count is the whole payload, and that is the confidentiality claim.** The
minimums SPEC §5.1 puts on comparison figures exist because a mean over two
sections is a number about those two sections. A count of sections is not such a
number — it says how wide a cohort is and nothing about what anybody in it said —
so this route may answer it to a leader who could not be shown a single figure
over the same set. What it may not do is carry a name, a code or a statistic,
because those are the two things the minimum is protecting and a preview is
reached before any suppression helper runs.

**Two halves, and the positive control comes first.** "The body carries no
course title" is satisfied by an empty body, by a 500 rendered as JSON, and by a
route that answers `{}` — so the counts are asserted to be *right* for a planted
world before anything is asserted to be absent (`docs/MISTAKES.md` entry 3).

**The world makes the two counts different numbers on purpose.** Two member
courses; three sections of them at the set's declared length; one section of a
member course at another length and one section of a course the set does not
name, neither of which may be counted. So `member_count` is 2 and
`section_count` is 3, and neither is the number of sections planted (5) nor the
number of courses (4): a preview answering one number in the other's place, or
counting every section in the term, is red rather than plausible.

**Marked `invariant` at the module level**, which puts it in the isolated §4.1
pass and satisfies
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`.
The marker is here because what this route answers is a fact about a comparison
set, and §4.1 item 7 is the rule that no figure computed from one reaches a
reader below the minimums: a preview that grew a name, a code or a statistic
would be that widening, decided by a route rather than by the suppression
chokepoint E4 built. The counts themselves are the deliberate exception §5.1
allows at set-definition time, which is why the positive control sits in the
pass beside the denial rather than outside it.

**Which failure a red here is, before E5-06 lands.** The path is the work
order's own, so an application without the router answers 404 and every test
fails on its status naming the router — a FAILED, not an error
(`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest
from fixtures.named_sets import NamedSetDoor

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# What this world's planted rows make each count, written out here rather than
# derived from the rows (`docs/MISTAKES.md` entry 19): a fixture that counted the
# sections the same way the service does would agree with a service that counted
# the wrong ones.
#
#   - two member courses → two membership rows;
#   - `E2WW` and `H2WW` under the first member course and `E3WW` under the
#     second are six-week sections, which is the length both sets declare → three;
#   - `X2WW` is eight weeks under a member course and `H3WW` is six weeks under a
#     course no set names → neither is counted.
EXPECTED_MEMBER_COUNT = 2
EXPECTED_SECTION_COUNT = 3


def test_the_preview_answers_the_counts_the_planted_world_makes(
    named_sets: NamedSetDoor, named_set_contract: Any
) -> None:
    """Criterion 5's positive control: both counts, over a world whose near misses are planted.

    **The mutations this kills:** a `section_count` that counts the set's member
    *courses* rather than their sections (2 where 3 belongs); one that counts
    every section of every member course, ignoring the declared length (4); one
    that counts every section in the term (5); and a `member_count` that counts
    resolved sections instead of membership rows. The two numbers are different
    and neither matches any of those wrong answers, which is what makes each of
    them a distinct red.

    **It is also what makes the denial test below mean anything**: a body that
    carries the right two counts is a body the route really produced.

    **Expected red before E5-06 lands:** a FAILED naming the router.
    """
    world = named_sets.world
    answered = named_sets.preview(world.hers.set_id)
    body = named_set_contract.body_of(answered, "The set preview", named_set_contract.list_ok)

    assert body.get(named_set_contract.member_count_field) == EXPECTED_MEMBER_COUNT, (
        f"The preview answered {body.get(named_set_contract.member_count_field)!r} member(s); this "
        f"set was planted with {EXPECTED_MEMBER_COUNT} member courses. Body: {body!r}."
    )
    assert body.get(named_set_contract.section_count_field) == EXPECTED_SECTION_COUNT, (
        f"The preview answered {body.get(named_set_contract.section_count_field)!r} section(s); "
        f"the member courses hold {EXPECTED_SECTION_COUNT} sections at the "
        f"{named_set_contract.declared_length}-week length this set declares, beside one "
        f"{named_set_contract.another_length}-week section of a member course and one six-week "
        f"section of a course no set names, neither of which resolves. Body: {body!r}."
    )


def test_the_preview_carries_the_two_counts_and_no_other_member(
    named_sets: NamedSetDoor, named_set_contract: Any
) -> None:
    """Criterion 5's denial half, over the whole payload at every depth.

    The two counts are the whole contract: `{"member_count": int,
    "section_count": int}`. A third member is where a figure arrives — a mean
    added "for the UI", a list of section codes added to make the count
    explicable — and either is a comparison figure reaching a reader without
    passing the suppression chokepoint E4 built (SPEC §4.1 item 7).

    **The mutations this kills:** a preview that returns the resolved section
    *ids* beside the count, which is a list of the cohort's sections; a preview
    that returns the set itself (name, level, member list) because reusing
    `SetDetail` was convenient; and a `float` count, which is a figure wearing a
    count's name.

    **Expected red before E5-06 lands:** a FAILED naming the router.
    """
    world = named_sets.world
    answered = named_sets.preview(world.hers.set_id)
    body = named_set_contract.body_of(answered, "The set preview", named_set_contract.list_ok)

    assert sorted(body) == sorted(named_set_contract.preview_fields), (
        f"The preview carries {sorted(body)}; decision 5 gives it exactly "
        f"{sorted(named_set_contract.preview_fields)}. Anything else on this payload is something "
        "a leader learns about a cohort before any minimum has been consulted."
    )
    for field in named_set_contract.preview_fields:
        value = body[field]
        assert isinstance(value, int) and not isinstance(value, bool), (
            f"`{field}` came back as {value!r} ({type(value).__name__}). A count is a whole number "
            "of things; a float here is a statistic, and a statistic over a comparison set is what "
            "SPEC §4.1 item 7 suppresses."
        )


def test_the_preview_names_no_course_no_section_and_no_set(
    named_sets: NamedSetDoor, named_set_contract: Any
) -> None:
    """Nothing in the answer names anything the set is made of — headers included.

    The member-by-member test above says the payload's *shape* is two counts;
    this says the same thing in the currency a leak actually arrives in. An
    identifier can ride a header — a `Location`, an `ETag` built out of the row
    it describes — and a scan blind to them reports a clean answer
    (`tests/fixtures/instructor_sections.py::surface_of` says the same).

    **The sweep is over strings this world planted**, so a hit names which one
    leaked rather than reporting that "something" did. Its pair is the count
    test above: the counts prove the body was produced by the route, so an empty
    scan here is a scan over a real payload.

    **The mutations this kills:** a preview that echoes the set's name so the UI
    can title the panel, and one that lists the codes of the sections it
    counted — both of which read as helpful and both of which hand a reader the
    cohort itself.

    **Expected red before E5-06 lands:** a FAILED naming the router.
    """
    world = named_sets.world
    answered = named_sets.preview(world.hers.set_id)
    named_set_contract.body_of(answered, "The set preview", named_set_contract.list_ok)

    headers = " ".join(f"{name}: {value}" for name, value in answered.headers.items())
    surface = f"{headers} {answered.text}"
    leaked = {
        what: value for what, value in world.planted_names().items() if value and value in surface
    }

    assert not leaked, (
        f"The preview's answer carries {leaked}. Criterion 5 gives this route two counts and "
        "nothing else: a name or a code here is the cohort itself, handed to a reader who is not "
        "entitled to a single figure computed over it."
    )
