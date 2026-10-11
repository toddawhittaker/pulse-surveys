"""On behalf opens only past +96h — E7-03, done-when 7.

> **On behalf only past 96 hours.** An on-behalf read, draft, check or publish
> before + 96h is refused and writes no row.

Work order decision 5: every refusal is the one 404; decision 6: every refusal is
decided before any model call. So each refused request is held to three things:
the 404, no `instructor_response` row, and **no request reaching the provider**.

**Each refusal is paired with the same request two minutes later**, past the edge,
answered 2xx — so a door that refuses everything is red on the pair. The route
reads the moving development clock (ADR 0109), so it stands `HTTP_MARGIN` either
side of +96h rather than on the second; the second itself is the predicate's, in
`test_the_owed_and_on_behalf_clocks_start_at_report_open.py`.

The section is `F1WW`, which lead A leads and does not teach; its course is
required from a day before the week opened, and nobody has answered.

**Which failure a red is, before E7-03 lands.** `find_route` fails naming the
on-behalf route.
"""

import pytest
from fixtures.response_loop_doors import (
    HTTP_MARGIN,
    NOT_FOUND,
    ON_BEHALF_AFTER,
    ON_BEHALF_FOUR,
    OWED_AFTER,
    LoopWorld,
    OnBehalfDoor,
)
from fixtures.the_hold import sentences_served

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("door", ON_BEHALF_FOUR, ids=lambda door: door.name)
def test_before_ninety_six_hours_each_door_is_refused_and_past_it_served(
    response_loop: LoopWorld, door: OnBehalfDoor
) -> None:
    """One minute before +96h: 404, one sentence, no row, no model call. One minute after: 2xx.

    **The mutations this kill:** a door that checks "owed" (+48h) rather than
    "on-behalf open" (+96h); a draft or check that calls the model and refuses
    afterwards (decision 6); a publish that writes and then refuses. **The near
    miss:** the same request past +96h.
    """
    world = response_loop
    world.own_course_required()
    world.stand(ON_BEHALF_AFTER - HTTP_MARGIN)
    rows, calls = world.response_count(), world.model_calls()

    refused = world.on_behalf(door, world.lead, section_id=world.hold.taught)

    assert refused.status_code == NOT_FOUND, (
        f"The on-behalf {door.name} a minute before +96h answered {refused.status_code}. Body "
        f"{refused.text[:300]!r}. Done-when 7."
    )
    assert len(sentences_served(refused)) == 1, f"The 404 served {refused.text[:300]!r}."
    assert world.response_count() == rows, f"The refused {door.name} wrote a response row."
    assert world.model_calls() == calls, (
        f"The refused {door.name} reached the provider. Decision 6: every refusal is decided "
        "before any model call."
    )

    world.stand(ON_BEHALF_AFTER + HTTP_MARGIN)
    served = world.on_behalf(door, world.lead, section_id=world.hold.taught)
    assert 200 <= served.status_code < 300, (
        f"The same {door.name} a minute past +96h answered {served.status_code}, so the refusal "
        f"above may be a door refusing everything. Body {served.text[:300]!r}."
    )


def test_at_forty_eight_hours_owed_is_not_on_behalf(response_loop: LoopWorld) -> None:
    """At +48h and a minute the week is owed; the on-behalf read is still the 404.

    **The mutation this kills:** on-behalf opened by the owed clock.
    """
    world = response_loop
    world.own_course_required()
    world.stand(OWED_AFTER + HTTP_MARGIN)

    refused = world.on_behalf(ON_BEHALF_FOUR[0], world.lead, section_id=world.hold.taught)

    assert (
        refused.status_code == NOT_FOUND
    ), f"The on-behalf read at +48h answered {refused.status_code}; on behalf opens at +96h."
