"""The held-week count rule reads fractions and the added quantity words — E7-03, work order decision 8.

Carried from the privacy-authz re-check of #309 (a LOW accepted there and fixed
here): in `states_a_count_of_people`, a hyphenated word counts when ANY part of it
is a count token ("two-thirds"), and the quantity words gain `third thirds quarter
quarters single dozens hundreds tens`. The work order names five phrasings for the
held-week unit test; they are written here, beside that module's tables rather
than inside them, so this branch does not edit E7-04's
`tests/fixtures/response_draft.py` while it is only on the epic branch. The
coordinator may fold them into `COUNTING_CLAUSES` when the branches meet.

Each phrasing sits in `a_draft_saying`'s frame, which
`tests/unit/test_the_held_week_count_rule_reads_every_phrasing.py` already pins
as stating no count.

**Which failure a red is, before E7-03 lands.** An assertion: `count_rule()`
exists (E7-04) and answers False for these five.
"""

import pytest
from fixtures.response_draft import a_draft_saying, count_rule

FRACTION_AND_QUANTITY_CLAUSES: dict[str, str] = {
    "two-thirds": "Two-thirds of you asked for slower derivations",
    "a-third": "A third of you asked for slower derivations",
    "a-quarter": "A quarter of the class asked for slower derivations",
    "dozens": "Dozens of you asked for slower derivations",
    "a-single-student": "A single student asked for slower derivations",
}


@pytest.fixture(autouse=True)
def _a_stated_environment(configured_env: dict[str, str]) -> None:
    """`app.services.reporting` is imported; the environment is stated (entry 40)."""


@pytest.mark.parametrize("case", tuple(FRACTION_AND_QUANTITY_CLAUSES))
def test_a_fraction_or_an_added_quantity_word_states_a_count(case: str) -> None:
    """Every phrasing decision 8 names: the rule answers True.

    **The mutations this kill, one per parameter:** a hyphenated word counted only
    when its *first* part is a count token, or only when every part is
    ("two-thirds"); `third`, `quarter`, `dozens` and `single` left out of the
    quantity words.
    """
    draft = a_draft_saying(FRACTION_AND_QUANTITY_CLAUSES[case])
    assert count_rule()(draft) is True, (
        f"`states_a_count_of_people` answers False for {draft!r}. E7-03 work order decision 8: a "
        "hyphenated word counts when any part is a count token, and the quantity words gain "
        "third, thirds, quarter, quarters, single, dozens, hundreds and tens."
    )
