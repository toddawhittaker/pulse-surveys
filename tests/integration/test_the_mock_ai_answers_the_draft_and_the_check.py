"""The in-repo mock provider answers both new tasks — E7-04 done-when 7.

> `mock-ai` answers both tasks, so 05's page and 09's drive run without a provider.

Work-order decision 5: "deterministic answers keyed by markers in the prompt, as
`mock-ai/app/rules.py` does for summaries."

**Driven the way 05 and 09 will meet it**: the tool's own gateway pointed at the
mock's application on a loopback socket (`tests/fixtures/mock_ai.py`'s bridge),
through the instructor's routes, in a week that has a held stream with a stored
summary — the ordinary shape of a quiet week. So an answer counts only if it gets
past both structural refusals as well as the gateway's shape validation: a mock
check naming a theme the week does not hold, or a mock draft stating a count beside
the held stream, is a 502 here and a broken page in 05.

**What this does not reach, and why.** The ticket also asks the mock for an answer
that reuses a planted comment's words and one naming a theme not stored, "so the
refusals can be driven end to end". The marker that selects each is not settled by
the ticket or the work order, and E2-07's rule is that a test reads the mock's
markers off `GET /mock/rules` rather than inventing them; so those two paths are
named here and left to the marker vocabulary the implementation publishes.

**Which failure a red is.** Before E7-04: a FAILED naming the missing route.
"""

from typing import Any

import pytest
from fixtures.instructor_decisions import DecisionDoor
from fixtures.mock_ai import MOCK_AI_PROVIDER_BASE_URL_VARIABLE, Endpoint
from fixtures.report_api import INSTRUCTOR_ROLE
from fixtures.response_draft import (
    A_PLAIN_DRAFT,
    COUNT_FIELD,
    HELD_THEME,
    LABEL_FIELD,
    SHOWN_THEME_A,
    SHOWN_THEME_A_COUNT,
    SHOWN_THEME_B,
    SHOWN_THEME_B_COUNT,
    DraftDoor,
    ScriptedProvider,
    text_of,
    unaddressed_of,
)

pytestmark = pytest.mark.integration

# What a stored theme of this week may be served as, label to count.
STORED = {
    SHOWN_THEME_A: SHOWN_THEME_A_COUNT,
    SHOWN_THEME_B: SHOWN_THEME_B_COUNT,
    HELD_THEME: None,
}


@pytest.fixture
def mock_draft_door(
    report_door_as: Any, configured_env: dict[str, str], mock_ai_endpoint: Endpoint
) -> DraftDoor:
    """The instructor's door with the tool's provider pointed at the mock, not at a script.

    The `DraftDoor`'s scripted provider is a placeholder that is never started and
    never pointed at: nothing here scripts an answer, and every completion request
    is counted on the mock's own bridge.
    """
    door = report_door_as(
        INSTRUCTOR_ROLE, **{MOCK_AI_PROVIDER_BASE_URL_VARIABLE: mock_ai_endpoint.base_url}
    )
    return DraftDoor(DecisionDoor(door, configured_env), ScriptedProvider(), configured_env)


def test_the_mock_answers_a_draft_the_route_serves_and_answers_it_the_same_way_twice(
    mock_draft_door: DraftDoor, mock_ai_endpoint: Endpoint
) -> None:
    """A draft from the mock: 200, a non-empty text, the same text on a second ask.

    **The mutation this kills:** no draft rule in the mock (its default answer is
    the validity payload, which the draft contract refuses — a 502 here); a rule
    whose draft states a number of students, refused beside the held stream; and a
    non-deterministic answer, which 09's drive cannot assert against.
    """
    door = mock_draft_door
    door.build_the_week()
    door.assert_the_streams_are(instructor_held=False, course_held=True)

    before = len(mock_ai_endpoint.completions)
    first = text_of(door.draft())
    assert len(mock_ai_endpoint.completions) > before, "The draft never reached the mock."
    assert first.strip(), "The mock's draft is empty."
    assert (
        text_of(door.draft()) == first
    ), "The mock answered two identical draft requests differently. Decision 5: deterministic."


def test_the_mock_answers_a_check_the_route_accepts(
    mock_draft_door: DraftDoor, mock_ai_endpoint: Endpoint
) -> None:
    """A check from the mock: 200, naming only stored themes as stored.

    **The mutation this kills:** no check rule in the mock, or one that names a
    theme of its own invention — the route refuses it with a 502 and 05's page has
    nothing to show. The empty list is a legal answer and passes.
    """
    door = mock_draft_door
    door.build_the_week()

    before = len(mock_ai_endpoint.completions)
    served = unaddressed_of(door.check(A_PLAIN_DRAFT))
    assert len(mock_ai_endpoint.completions) > before, "The check never reached the mock."
    for theme in served:
        label = theme.get(LABEL_FIELD)
        assert label in STORED and theme.get(COUNT_FIELD) == STORED[label], (
            f"The check served {theme!r} from the mock, which is not one of this week's stored "
            f"themes as stored ({STORED!r})."
        )
