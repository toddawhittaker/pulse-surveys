"""Every write of E7-03 runs its CSRF gate at dispatch — E7-03, done-when 12 (MISTAKES entry 47).

> **The gates run at dispatch.** Each write with no CSRF token, or from another
> origin, is refused over HTTP against the built application, beside the same
> write with the token (MISTAKES entry 47).

`tests/integration/test_the_lead_decision_gate_runs_at_dispatch.py`'s shape,
extended to the seven writes this ticket adds. **The session rides the cookie**,
because ADR 0089's double-submit check exempts a Bearer header. "From another
origin" is a genuine token minted for a different session — what a page elsewhere
can come by.

**Each refusal is paired with the accepted request**, made the same way with this
session's own token, so a route refusing every cookie-borne write is red. Each
refusal is held to its effect as well as its status: no response row, no policy
row, no request reaching the provider.

The writes: the instructor's publish and edit (decision 1, the teacher's session);
the policy switch (decision 2, lead A's); the on-behalf draft, check, publish and
edit (decision 5, lead A's, past +96h on `F1WW`).

**Which failure a red is, before E7-03 lands.** `find_route` fails naming the
route.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fixtures.lead_review import MINTED
from fixtures.response_loop_doors import (
    CLEAR_PAST,
    INSTRUCTOR_API_MODULE,
    INSTRUCTOR_RESPONSE_ENDING,
    MODE_FIELD,
    ON_BEHALF_AFTER,
    ON_BEHALF_CHECK,
    ON_BEHALF_DRAFT,
    ON_BEHALF_EDIT,
    ON_BEHALF_PUBLISH,
    LoopWorld,
    OnBehalfDoor,
    fill,
    response_body,
)
from fixtures.submit import CSRF_REFUSED_STATUS
from fixtures.the_hold import REQUIRED

pytestmark = pytest.mark.integration

CASES = ("no-token", "another-sessions-token")


class Write:
    """One write: how to set its world up, and the request (method, url, token, body)."""

    def __init__(
        self,
        name: str,
        prepare: Callable[[LoopWorld], None],
        request: Callable[[LoopWorld], tuple[str, str, str, Any]],
    ) -> None:
        self.name = name
        self.prepare = prepare
        self.request = request

    def __repr__(self) -> str:
        return self.name


def _instructor(method: str, text: str) -> Callable[[LoopWorld], tuple[str, str, str, Any]]:
    def request(world: LoopWorld) -> tuple[str, str, str, Any]:
        template = world.route(
            module=INSTRUCTOR_API_MODULE, method=method, ending=INSTRUCTOR_RESPONSE_ENDING
        )
        url = fill(template, section_id=world.hold.taught, course_week=1)
        return method, url, world.teacher_token, response_body(text)

    return request


def _on_behalf(door: OnBehalfDoor) -> Callable[[LoopWorld], tuple[str, str, str, Any]]:
    def request(world: LoopWorld) -> tuple[str, str, str, Any]:
        world.script_for(door)
        url = world.on_behalf_url(door, section_id=world.hold.taught, course_week=1)
        return door.method, url, world.lead.token, world.body_for(door, "E7-03 by cookie")

    return request


def _policy(world: LoopWorld) -> tuple[str, str, str, Any]:
    return "PUT", world.policy_url(), world.lead.token, {MODE_FIELD: REQUIRED}


def _early(world: LoopWorld) -> None:
    world.stand(CLEAR_PAST)


def _early_published(world: LoopWorld) -> None:
    world.stand(CLEAR_PAST)
    published = world.instructor("POST", text="E7-03 published by Bearer, before the edit")
    assert published.status_code == 201, f"The setup publish answered {published.status_code}."


def _late(world: LoopWorld) -> None:
    world.own_course_required()
    world.stand(ON_BEHALF_AFTER + CLEAR_PAST)


def _late_published_on_behalf(world: LoopWorld) -> None:
    _late(world)
    published = world.on_behalf(ON_BEHALF_PUBLISH, world.lead, section_id=world.hold.taught)
    assert (
        200 <= published.status_code < 300
    ), f"The setup publish answered {published.status_code}."


WRITES = (
    Write("instructor-publish", _early, _instructor("POST", "E7-03 published by cookie")),
    Write("instructor-edit", _early_published, _instructor("PUT", "E7-03 edited by cookie")),
    Write("policy-switch", _early, _policy),
    Write("on-behalf-draft", _late, _on_behalf(ON_BEHALF_DRAFT)),
    Write("on-behalf-check", _late, _on_behalf(ON_BEHALF_CHECK)),
    Write("on-behalf-publish", _late, _on_behalf(ON_BEHALF_PUBLISH)),
    Write("on-behalf-edit", _late_published_on_behalf, _on_behalf(ON_BEHALF_EDIT)),
)


def effects(world: LoopWorld) -> tuple[int, int, int]:
    return world.response_count(), world.policy_count(), world.model_calls()


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("write", WRITES, ids=lambda write: write.name)
def test_a_cookie_borne_write_without_this_sessions_token_is_refused_and_with_it_accepted(
    response_loop: LoopWorld, write: Write, case: str
) -> None:
    """Refused (403, no effect) without this session's token; accepted (2xx) with it.

    **The mutations this kill:** the write declared behind `require_instructor` or
    `require_leadership` rather than its CSRF-verifying twin (both refusals
    accepted); the gate attached where it does not run at dispatch (entry 47's
    shape); a check comparing the cookie with the header (the other session's
    token, sent as both, passes it). **The near miss:** the same write with this
    session's own token, accepted — so a gate refusing every cookie is red.
    """
    world = response_loop
    write.prepare(world)
    method, url, token, body = write.request(world)
    csrf: Any = None
    if case == "another-sessions-token":
        csrf = world.review.another_sessions_csrf_token(token)
    before = effects(world)

    refused = world.as_a_browser(method, url, token=token, json=body, csrf_token=csrf)

    assert refused.status_code == CSRF_REFUSED_STATUS, (
        f"The cookie-borne {write.name} with {case} answered {refused.status_code}, not "
        f"{CSRF_REFUSED_STATUS}. Body {refused.text[:300]!r}."
    )
    assert effects(world) == before, (
        f"The refused {write.name} ({case}) changed (responses, policies, model calls) from "
        f"{before} to {effects(world)}."
    )

    method, url, token, body = write.request(world)
    accepted = world.as_a_browser(method, url, token=token, json=body, csrf_token=MINTED)
    assert 200 <= accepted.status_code < 300, (
        f"The same {write.name} with this session's own CSRF token answered "
        f"{accepted.status_code}, so the refusal above may be a route refusing every cookie. "
        f"Body {accepted.text[:300]!r}."
    )
