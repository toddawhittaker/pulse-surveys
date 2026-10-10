"""A decided comment's card names no decider and carries no date — ticket E6-03, criterion 5.

> `CommentView` carries the answer id, the flag class and "decided by you", and no
> date, time, week, author or decider.

The ceiling in
`tests/integration/test_the_report_payload_repeats_nothing_beyond_the_comment_service.py`
reads the card's member names and its values for a world nobody has decided
anything in. This is the same scan **after a decision**, because a decision is
what brings a decider and an instant into existence: the `moderation_state` row
names a `person` and carries `decided_at`, and a card assembled from that row is
one convenient field away from carrying either. ADRs 0153 and 0162 name the
channel a date on a card opens — set beside the gradebook's per-week ledger, the
day a comment was decided narrows who wrote it — and ruling 4 keeps staff names
out of every view until E9.

**The scan is over values, at any depth, in both currencies a leak travels in** —
the decider's `person` key (hyphenated and bare hex) and anything that reads as an
instant — over every card in the payload, the decided one included.

**The canary** (`docs/MISTAKES.md` entry 3): the decided card is found by its
handle and is required to say `decided_by_you: true` before anything is scanned,
so a scan over a payload the decision never reached says so.

Marked `invariant` at the module level: a confidentiality denial
(`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`).
"""

from datetime import datetime
from uuid import UUID

import pytest
from fixtures.instructor_decisions import (
    EXCLUDE,
    OK,
    DecisionDoor,
    require_decision_columns,
)
from fixtures.moderation import HARMFUL
from fixtures.report_api import DECIDED_BY_YOU_FIELD, FULL_WEEK, strings_in
from fixtures.report_views import INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]


def reads_as_an_instant(value: str) -> bool:
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def test_a_card_decided_by_the_reader_carries_neither_the_decider_nor_an_instant(
    decision_door: DecisionDoor,
) -> None:
    """After the reader excludes a flagged comment, no card in the week names them or a moment.

    **The mutations this kills:** a `decided_by` or `decider` member carrying the
    `person` key ("decided by you" computed on the client instead); a
    `decided_at`, or an "excluded on …" string, on the card; and either nested one
    level down, under a `decision` object, where a top-level member check would not
    look.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    text = "E6-03 a flagged comment whose card is scanned after it is decided"
    comment = door.plant_a_comment(
        course_week=FULL_WEEK, stream=INSTRUCTOR_STREAM, text=text, verdict=HARMFUL
    )
    answered = door.decide(comment, EXCLUDE)
    assert answered.status_code == OK, f"The exclusion was answered {answered.status_code}."

    decider = door.person_id
    forbidden = {str(decider)} | ({decider.hex} if isinstance(decider, UUID) else set())
    assert all(forbidden), "The door's instructor has no `person` key to search for."

    body = door.payload(FULL_WEEK)
    decided = door.card(body, comment)
    assert decided is not None and decided.get(DECIDED_BY_YOU_FIELD) is True, (
        f"The decided comment's card is {decided!r}; it should be on the report and say the "
        "reader decided it. Until it does, the scan below is over a payload the decision did not "
        "reach."
    )
    assert text in strings_in(decided), "The canary: the card's own text is not found by the scan."

    for card in door.cards(body):
        for value in strings_in(card):
            assert value not in forbidden, (
                f"A card carries {value!r}, the `person` key of the instructor who decided. "
                f"Ruling 4 and work order decision 6: no decider on a card. The card: {card!r}."
            )
            assert not reads_as_an_instant(value), (
                f"A card carries {value!r}, which reads as an instant. No date or time on a card "
                f"(criterion 5; ADRs 0153 and 0162). The card was {card!r}."
            )
