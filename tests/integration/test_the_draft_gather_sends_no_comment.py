"""The draft and the check are fed stored summaries and ratings, never a comment — E7-04 done-when 1.

> A test plants a distinctive comment in the section-week and asserts it appears
> in neither task's rendered prompt, for a shown stream and a held one.

**Measured on the wire, not on a return value.** The application's own gateway
sends each task's request to a provider this suite runs (`tests/fixtures/
response_draft.py`), so "the prompt" here is everything the request carried —
system and user messages, any schema, anything a later refactor adds. A prompt
renderer that was clean while something else in the request carried a comment
would pass a test of the renderer and fail this one, which is the right way round.

**The canary is a stored summary's text.** The ticket feeds both tasks the
section-week's stored summaries, so a summary planted for this week must arrive.
If it does not, the search is looking at a request that is not the task's — or at
no request at all — and every absence below would be trivially true
(`docs/MISTAKES.md` entry 3).

**Every kind of comment is planted, not only the two the criterion names.** The
shown and held streams are the criterion; the excluded, flagged and kept comments
are free to plant in the same world and close the obvious near miss — a gather that
filtered comments by moderation state and sent the "safe" ones.

**Marked `invariant`.** A comment in a held stream reaching a model whose answer a
person may publish to every student is §4.1 item 3's surface, one layer out.

**Which failure a red is.** Before E7-04 lands: a FAILED naming the missing route
(`draft_route`), or the missing `CheckTheme` when a check answer is built.
"""

from typing import Any

import pytest
from fixtures.report_api import FULL_WEEK, FULL_WEEK_COMMENTS
from fixtures.response_draft import (
    GATHER_KEYWORDS,
    HELD_COMMENT,
    HELD_SUMMARY_TEXT,
    HELD_THEME,
    RESPONSE_GATHER_TYPE,
    RUN_OF,
    SHOWN_SUMMARY_TEXT,
    DraftDoor,
    response_gather,
    strings_in,
    what_each_task_sent,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# Every comment this world holds for course week 1: the canonical world's five
# and the five this suite plants. The exact strings the product stored.
EVERY_COMMENT = (*RUN_OF, *FULL_WEEK_COMMENTS)


def leaked(text: str) -> list[str]:
    """Each planted comment, or its distinctive run, found in `text`."""
    found = [comment for comment in EVERY_COMMENT if comment in text]
    found += [run for run in RUN_OF.values() if run in text]
    tails = [comment.split(": ", 1)[1] for comment in FULL_WEEK_COMMENTS]
    found += [tail for tail in tails if tail in text]
    return sorted(set(found))


def test_neither_tasks_request_carries_a_comment_from_a_shown_or_a_held_stream(
    draft_door: DraftDoor,
) -> None:
    """Both tasks, one world: every comment absent, the stored summary present.

    **The mutation this kills:** the gather reading `report_comment` (or any comment
    read) into the prompt — for either stream, or for one stream only, which is the
    near miss of sending the shown stream's comments "because the instructor can
    read them anyway": the prompt's output is published to students, and the
    ticket says never raw comments. **The near miss it must survive:** sending the
    stored summaries, which the ticket requires and the canary asserts.
    """
    door = draft_door
    door.build_the_week()
    door.assert_the_streams_are(instructor_held=False, course_held=True)

    sent = what_each_task_sent(door)

    for task, text in sent.items():
        assert SHOWN_SUMMARY_TEXT in text, (
            f"The {task}'s request does not carry the shown stream's stored summary "
            f"({SHOWN_SUMMARY_TEXT!r}). The ticket feeds both tasks the stored summaries, so this "
            "is the canary: without it the absences below are a search of the wrong request."
        )
        found = leaked(text)
        assert not found, (
            f"The {task}'s request to the model carries comment text: {found}. The ticket: 'The "
            "gather sends no comment. Both tasks are fed the section-week's stored summaries and "
            "their stored themes, and the rating distributions and response counts. Never raw "
            f"comments.' The held stream's comment is {HELD_COMMENT!r}; a held comment in a "
            "prompt whose answer is published to every student is SPEC §4.1 item 3 undone."
        )


def test_the_gather_names_the_week_and_holds_no_comment(draft_door: DraftDoor) -> None:
    """Decision 3's function, read directly: summaries in, comments out.

    `response_gather(session, *, section_id, week_id, for_on_behalf=False)` is the
    instructor's gather; 03 reuses it. Every string it returns, at any depth, is
    searched — its fields are the implementer's, so the walk does not name them.

    **The canary is both stored summaries**, the shown stream's and the held
    stream's `summary.v3`, and the held theme's label: if the walk cannot see them
    it cannot see a comment either. **The mutation this kills:** a gather that
    carries comment text in a field the prompt happens not to render today — a
    later prompt edit would render it, and only this test sees it first.
    """
    door = draft_door
    door.build_the_week()
    gather = response_gather()

    found = gather(
        door.world.session,
        section_id=door.rows.taught_section_id,
        week_id=door.rows.week_id(FULL_WEEK),
        for_on_behalf=False,
    )
    text = "\n".join(strings_in(_plain(found)))

    for canary in (SHOWN_SUMMARY_TEXT, HELD_SUMMARY_TEXT, HELD_THEME):
        assert canary in text, (
            f"The gather's result does not carry {canary!r}, a stored summary value of this "
            "section-week that the instructor's report serves. Either the walk below cannot see "
            "the result's values, or the gather omits the stored summaries the ticket feeds both "
            f"tasks. It returned {found!r:.600}."
        )
    assert not leaked(text), f"The gather's result carries comment text: {leaked(text)}."


def _plain(value: Any) -> Any:
    """A gather result as plain JSON-like data, whatever kind of object it is."""
    if hasattr(value, "model_dump"):
        return _plain(value.model_dump(mode="json"))
    if hasattr(value, "__dataclass_fields__"):
        return {name: _plain(getattr(value, name)) for name in value.__dataclass_fields__}
    if hasattr(value, "_asdict"):
        return _plain(value._asdict())
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_plain(item) for item in value]
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return {key: _plain(item) for key, item in vars(value).items() if not key.startswith("_")}
    return value


def test_the_gather_has_the_signature_decision_3_settles(configured_env: dict[str, str]) -> None:
    """`response_gather(session, *, section_id, week_id, for_on_behalf: bool) -> ResponseGather`.

    03 calls it with `for_on_behalf=True`, so the signature is an interface between
    two tickets and is pinned here rather than discovered. **The mutation this
    kills:** `for_on_behalf` made optional with a default — the on-behalf caller's
    filter is then one forgotten keyword away from the instructor's — or the
    return left unannotated, which leaves 03 nothing to type against.
    """
    import inspect
    import typing

    gather = response_gather()
    signature = inspect.signature(gather)
    parameters = signature.parameters
    for name in GATHER_KEYWORDS:
        assert name in parameters, f"`response_gather{signature}` takes no `{name}`."
        assert (
            parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        ), f"`{name}` is {parameters[name].kind.name}; decision 3 makes it keyword-only."
    assert parameters["for_on_behalf"].default is inspect.Parameter.empty, (
        "`for_on_behalf` has a default. Decision 3 spells it `for_on_behalf: bool` with none, so "
        "each caller states which reader it gathers for."
    )
    positional = [p for p in parameters.values() if p.kind is not inspect.Parameter.KEYWORD_ONLY]
    assert len(positional) == 1, f"`response_gather{signature}`: decision 3 takes one `session`."
    returned = typing.get_type_hints(gather).get("return")
    assert getattr(returned, "__name__", None) == RESPONSE_GATHER_TYPE, (
        f"`response_gather` is annotated to return {returned!r}; decision 3 says "
        f"`{RESPONSE_GATHER_TYPE}`."
    )
