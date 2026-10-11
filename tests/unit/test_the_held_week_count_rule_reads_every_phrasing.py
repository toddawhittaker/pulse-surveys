"""The held-week count rule, read over every phrasing and every twin — E7-04 fix-round G1.

The work order's G1 settles the rule in place of a phrase list: in a week with a
held stream, a draft states no number of anything except one naming a course
structure. "One function in `services/reporting.py` holds the rule", and the
coordinator names it `states_a_count_of_people(text) -> bool`. G2 has the eval
grader call the same function, so this module is the only place its reading of
each phrasing is pinned.

**The phrasings are written in `tests/fixtures/response_draft.py`, not derived from
the rule** (`docs/MISTAKES.md` entry 19): the six the fix-round review found, the
original residue-A pair, and one per token class G1 lists. The twins are the
structure-word exceptions, an ordinal, and a draft with no number.

**The function decides whether a draft states a count; whether a stream is held is
the route's question**, and `tests/integration/test_a_draft_stating_a_count_beside_a_held_stream_is_refused.py`
drives that half (including the shown week, where "two of you" is accepted).

**Which failure a red is.** Before the fix round: a FAILED naming the missing
function (`count_rule`).
"""

import pytest
from fixtures.response_draft import (
    ALLOWED_CLAUSES,
    COUNTING_CLAUSES,
    a_draft_saying,
    count_rule,
)


@pytest.fixture(autouse=True)
def _a_stated_environment(configured_env: dict[str, str]) -> None:
    """`app.services.reporting` is imported; the environment is stated (entry 40)."""


@pytest.mark.parametrize("case", tuple(COUNTING_CLAUSES))
def test_a_draft_carrying_a_count_token_states_a_count(case: str) -> None:
    """Every refused phrasing: the rule answers True.

    **The mutations this kills, one per parameter:** a phrase list in place of the
    token rule (the review's six are each a phrasing a list missed); a number-word
    list stopping short of ninety-nine, of hyphenated compounds or of "hundred";
    each quantity word G1 names left out; a rule scoped to counts of people; and a
    structure word that licenses every later number in the sentence.
    """
    draft = a_draft_saying(COUNTING_CLAUSES[case])
    assert count_rule()(draft) is True, (
        f"`states_a_count_of_people` answers False for {draft!r}. G1: in a week with a held "
        "stream the draft states no number of anything except one naming a course structure."
    )


@pytest.mark.parametrize("case", tuple(ALLOWED_CLAUSES))
def test_a_draft_naming_a_course_structure_or_no_number_states_no_count(case: str) -> None:
    """Every twin: the rule answers False.

    **The mutations this kills:** no structure-word exception; a case-sensitive one
    ("Week 4"); one that does not reach a hyphenated compound ("chapter twenty-one");
    ordinals read as counts; and a rule that answers True for any text at all.
    """
    draft = a_draft_saying(ALLOWED_CLAUSES[case])
    assert count_rule()(draft) is False, (
        f"`states_a_count_of_people` answers True for {draft!r}, which names a course "
        "structure, uses an ordinal, or states no number. G1 allows those."
    )


def test_the_frame_every_phrasing_sits_in_states_no_count() -> None:
    """The control for both tables: the frame alone answers False.

    **Without it**, a rule that read the frame as a count ("each class"?) would make
    every refused case true for the wrong reason and every twin false for the same
    one, and the tables would pass and fail together for nothing they name.
    """
    assert count_rule()(a_draft_saying("You wrote to me")) is False, (
        "The frame the phrasings sit in already states a count by this rule, so the two "
        "tables above measure the frame rather than the phrasings."
    )
