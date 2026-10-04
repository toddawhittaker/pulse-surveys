"""E5.1-03 criterion 1, the instructor gate's half — its 401 says the registry's sentence.

> Every sentence the four entry pages serve, plus `NOT_AN_INSTRUCTOR`, is a
> `CopyEntry` under a governed prefix.

`require_instructor` refuses a session that is not an instructor's — a student
session, or none at all — with a 401 and a `Bearer` challenge. Until this
ticket its detail was a literal in `app.api.deps`, a carried entry: the report
surface's other two refusals had moved into the registry and this one had not,
so the SPEC §4.1 items 4 and 5 sweep never read it. Ruling R1 of the work order
moves it to `app/copy/instructor_report.py` as
`instructor_report.not_an_instructor`, under the prefix the inventory already
governs for the report surface, and the gate serves that entry's `.text`.

**Asserted where it is served, over HTTP.** The registry holding the sentence is
the inventory module's to see; whether the gate *serves* it is only visible in a
response. So each case drives the built application through
`tests/fixtures/report_api.py`'s door and compares the 401's `detail` with the
entry's text, read out of the registry at run time and never written here
(`docs/MISTAKES.md` entry 19).

**Each refusal has its control** (`docs/MISTAKES.md` entry 35). The student
session first reads the student route its role certainly reads, so its 401
here is the role gate rather than a broken session; the no-session case first
reads the same route *with* the instructor's credential and gets 200, so its
401 is the missing session rather than a route that refuses everybody.

**Not marked `invariant`.** What a role is refused is
`tests/integration/test_the_report_route_names_nothing_about_a_section_she_does_not_teach.py`'s,
and it is marked there. This module asserts which words the refusal is made
of.

**How a red reads.** Each test begins with `the_registry_sentence`, a plain call
that `pytest.fail`s if the registry stops publishing
`instructor_report.not_an_instructor` (`docs/MISTAKES.md` entry 44). Otherwise a
red is the gate serving some other text.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fixtures.student_read import STUDENT_READ_PATH

pytestmark = pytest.mark.integration

# R1's key for the instructor gate's refusal.
NOT_AN_INSTRUCTOR_KEY = "instructor_report.not_an_instructor"

# The member of a FastAPI error body that carries an `HTTPException`'s detail.
DETAIL_MEMBER = "detail"


def the_registry_sentence(registry_texts: Callable[[], dict[str, str]]) -> str:
    """`instructor_report.not_an_instructor`'s text, or a failure naming the entry owed."""
    text = registry_texts().get(NOT_AN_INSTRUCTOR_KEY, "")
    if not text.strip():
        pytest.fail(
            f"The copy registry publishes no non-empty `{NOT_AN_INSTRUCTOR_KEY}`. E5.1-03's ruling "
            "R1 moves the instructor gate's 401 sentence out of `app.api.deps` into "
            "`app/copy/instructor_report.py`, byte for byte, as a `CopyEntry` added to that "
            "module's `COPY`; `require_instructor` then serves its `.text`."
        )
    return text


def detail_of(answered: Any, what: str) -> Any:
    """The `detail` member of a refusal's JSON body, or a failure saying the body has none."""
    try:
        body = answered.json()
    except ValueError:
        pytest.fail(f"{what} answered a body that is not JSON: {answered.text[:300]!r}.")
    if not isinstance(body, dict) or DETAIL_MEMBER not in body:
        pytest.fail(f"{what} answered {body!r}, which carries no `{DETAIL_MEMBER}`.")
    return body[DETAIL_MEMBER]


def test_a_student_session_is_refused_with_the_registry_sentence(
    report_door_as: Any, report_api_contract: Any, registry_texts: Any
) -> None:
    """A student session at an instructor route: 401, and the detail is the registry's text.

    **The mutation it kills:** `require_instructor` left serving the literal in
    `deps.py` with a registry entry beside it that nothing serves — which passes
    the inventory and is the carried entry unchanged — once the two sentences
    differ in a word; and the gate answering with another refusal's entry, such
    as the student gate's. **Its near miss** is the student session reading its
    own route, which must answer 200 first.
    """
    sentence = the_registry_sentence(registry_texts)
    door = report_door_as("STUDENT")

    with door.carrying_no_cookie():
        allowed = door.tool.get(STUDENT_READ_PATH, headers=door.credential())
    assert allowed.status_code == 200, (
        f"This student session was answered {allowed.status_code} by `{STUDENT_READ_PATH}`, the "
        "route its role certainly reads. Until that is 200, a 401 from an instructor route says "
        f"the session is broken rather than that it is a student's. Body {allowed.text[:300]!r}."
    )

    with door.carrying_no_cookie():
        answered = door.published_weeks()
    assert answered.status_code == report_api_contract.role_refused_status, (
        f"A student session at the instructor published-week route was answered "
        f"{answered.status_code}, not {report_api_contract.role_refused_status}. Body begins "
        f"{answered.text[:300]!r}."
    )
    detail = detail_of(answered, "The instructor gate's refusal of a student session")
    assert detail == sentence, (
        f"The instructor gate refused a student session with {detail!r}; the registry's "
        f"`{NOT_AN_INSTRUCTOR_KEY}` says {sentence!r}. R1: the gate serves the entry's `.text`, so "
        "the sentence the inventory sweeps is the sentence the reader is shown."
    )


def test_a_request_with_no_session_is_refused_with_the_registry_sentence(
    report_door: Any, report_api_contract: Any, registry_texts: Any
) -> None:
    """No session at all at an instructor route: 401, and the same registry sentence.

    **The mutation it kills:** the no-session branch of the gate keeping a
    literal of its own after the wrong-role branch moved — the folded guard
    helper R7 introduces holds both, and a fold that left one sentence behind
    is the shape this catches. **Its near miss** is the same request carrying
    the instructor's credential, which must answer 200 first.
    """
    sentence = the_registry_sentence(registry_texts)
    shape = report_api_contract.published_weeks_route(report_door.application)
    url, query = report_api_contract.request_for(
        shape, section_id=report_door.rows.taught_section_id
    )

    with report_door.carrying_no_cookie():
        allowed = report_door.tool.get(url, params=query or None, headers=report_door.credential())
        answered = report_door.tool.get(url, params=query or None)

    assert allowed.status_code == 200, (
        f"The published-week route answered the teaching instructor {allowed.status_code}. Until "
        "that is 200, a 401 without a session says nothing about the missing session. Body "
        f"begins {allowed.text[:300]!r}."
    )
    assert answered.status_code == report_api_contract.role_refused_status, (
        f"A request with no session at all was answered {answered.status_code}, not "
        f"{report_api_contract.role_refused_status}. Body begins {answered.text[:300]!r}."
    )
    detail = detail_of(answered, "The instructor gate's refusal of a request with no session")
    assert detail == sentence, (
        f"The instructor gate refused a request with no session with {detail!r}; the registry's "
        f"`{NOT_AN_INSTRUCTOR_KEY}` says {sentence!r}."
    )
