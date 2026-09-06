"""What the summary prompt carries, and what may never reach it — E4-05.

Two criteria meet in this module.

**Acceptance criterion 2**, in full: "no identity crosses the boundary: a test
asserts the rendered prompt for a planted week contains no user id, no name-shaped
seed data, and no section code". That is SPEC §4's rule at the one boundary this
ticket opens — "identity is never displayed to instructors or any leadership role,
in any view" is about screens, and comment text leaving for a provider is a
different door with the same rule. The ticket's own security note says so: "comment
text leaves the database and goes to the AI provider — the same boundary the
validity task already crosses, with the same rules: no identity accompanies it".

**And the injection boundary**, which `backend/app/ai/prompts/README.md` rests on
the student's text being the last thing in the message. E4-05 puts the comments
placeholder at the end of `summary.v1.md` for that reason, and ADR 0053 keeps the
gateway's one re-ask from appending a message after it. A prompt that put an
instruction after the comments would let a comment ending in "ignore the above"
speak to the model with the last word.

**The identity assertion is made twice, in two shapes, and only one of them is
strong.** Searching a rendered prompt for a name that is not there passes for many
reasons — a renderer that returned an empty string passes it, a search that has
gone blind passes it — so the structural test comes first: the renderer takes the
stream and the comment texts, and there is no parameter through which a user id, a
section or a session could arrive at all. The search is the second, with a canary
that the comments themselves *did* arrive and a control that the same search finds
the needles when they are present.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from fixtures.summary_task import (
    COURSE_STREAM,
    INSTRUCTOR_STREAM,
    SUMMARY_COMMENTS_PLACEHOLDER,
    SUMMARY_PROMPT_VERSION,
    SUMMARY_STREAM_PLACEHOLDER,
    SummaryApi,
)

# The week this module plants. Invented comments, carrying a nonce each so that
# "the comment reached the prompt" is evidence rather than a coincidence: an
# ordinary English sentence could in principle appear in a prompt template, and
# then the canary would be satisfied by a render that dropped every comment.
PLANTED_COMMENTS = (
    "The Thursday proofs went by too quickly to write anything down [Rb9NsWqvZm].",
    "Office hours were genuinely helpful once I got there [Xt4LdKj3Px].",
    "Please post the derivations afterwards if the pace has to stay [E8mZt5UwGh].",
)

# What a week of comments is *about*, and none of it may travel with them. **This
# suite's choice of values**, shaped like the real things: a `sub` claim is the
# LMS user id SPEC §4 keys responses to, a person's name is what `scripts/seed.py`
# writes into `person`, and a section code is §2.2's join of prefix, number and
# start letter. Nothing here is passed to the renderer — that is the point — so
# a match is a renderer that reached for identity through some other route.
PLANTED_USER_ID = "3f1c6a52-9b4e-4a77-8d21-0c5e7b9a4f18"
PLANTED_SECOND_USER_ID = "u-7741-Qv7Zm"
PLANTED_PERSON_NAME = "Amelia Rivera"
PLANTED_SECTION_CODE = "ITEC 4020 A01"
PLANTED_IDENTITY = (
    PLANTED_USER_ID,
    PLANTED_SECOND_USER_ID,
    PLANTED_PERSON_NAME,
    PLANTED_SECTION_CODE,
)

# The parameters E4-05's work order gives the renderer, and the whole of what it
# may be handed: `render_summary_prompt(version, *, stream, comments)`.
RENDERER_PARAMETERS = ("version", "stream", "comments")

# Names a parameter would carry if identity could reach the prompt at all.
IDENTITY_PARAMETERS = (
    "session",
    "db",
    "database",
    "section",
    "section_id",
    "section_code",
    "user",
    "user_id",
    "student",
    "student_id",
    "sub",
    "person",
    "person_id",
    "enrollment",
    "response",
    "responses",
)

# A version that certainly exists and certainly does not carry the summary
# prompt's placeholders: the validity prompt the application says it renders. It
# is resolved from `app.ai.tasks` rather than written down, because ADR 0032 keeps
# every committed prompt on disk forever and a literal would go on naming a file
# nothing sends (`tests/unit/test_mock_ai_rules.py` made this repair already).
VALIDITY_PROMPT_VERSION_CONSTANT = "VALIDITY_PROMPT_VERSION"

# The error a missing placeholder raises, which E0-12's `render_prompt` already
# defines. Named rather than discovered: a test that accepted any exception would
# be satisfied by the `KeyError` of a lookup that never found the file.
PROMPT_ERROR = "PromptError"


def rendered_week(api: SummaryApi, stream_token: str = INSTRUCTOR_STREAM) -> str:
    """The planted week, rendered through the application's own renderer."""
    render = api.render()
    return render(
        api.constant(SUMMARY_PROMPT_VERSION),
        stream=api.stream(stream_token),
        comments=PLANTED_COMMENTS,
    )


def occurrences(text: str, needle: str) -> int:
    """How many times `needle` appears in `text`."""
    return text.count(needle)


def identity_in(text: str) -> list[str]:
    """Every planted identity value `text` carries, as the one detector both ways.

    One function rather than an inline comprehension, so that the control below
    exercises the same code the assertion does. A detector proven on a haystack it
    is not used against is not a control.
    """
    return sorted(needle for needle in PLANTED_IDENTITY if needle in text)


def test_the_renderer_cannot_be_handed_identity_at_all(summary_api: SummaryApi) -> None:
    """Acceptance criterion 2, in the shape that cannot pass vacuously.

    SPEC §4 keys responses to the LMS user id and lets identity out through one
    audited path only. The way to keep it out of a prompt is not to remember to
    leave it out: it is for the renderer to have nowhere to put it. E4-05 settles
    the signature as `render_summary_prompt(version, *, stream, comments)`, which
    takes a list of strings and the stream they belong to — a caller holding a
    session, a section and a student cannot pass any of them.

    **This is an ordinary member of the unit suite and carries no `invariant`
    marker.** That marker is the inventory of SPEC §4.1's enumerated items, and
    §4.1 does not name the model-provider boundary — §7.4 and this ticket's second
    criterion do. Marking it would make the epic-exit count of §4.1's set assert
    something false. Whether the boundary deserves §4.1 standing is a question for
    the spec, raised separately.

    **The mutation this kills:** a renderer widened to take the section, the
    responses, or a session "so it can look up the week itself" — after which
    nothing structural stops a future edit interpolating a name, and the search
    below becomes the only guard. **The near miss that must stay green:** an
    optional parameter the ticket does settle, and any keyword-only spelling of
    the three it names.
    """
    render = summary_api.render()
    signature = inspect.signature(render)
    parameters = [
        parameter.name
        for parameter in signature.parameters.values()
        if parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
    ]

    assert parameters, (
        f"`render_summary_prompt{signature}` takes no parameters at all, so it cannot be "
        "rendering a week's comments and the assertion below would be vacuous."
    )
    reaching = sorted(name for name in parameters if name in IDENTITY_PARAMETERS)
    assert not reaching, (
        f"`render_summary_prompt{signature}` accepts {reaching}. E4-05: the input is 'the "
        "week's comments for one stream ... with no identity, no section code, no user id in "
        "the prompt', and the renderer having nowhere to put identity is what makes that "
        "structural rather than a matter of what each caller remembers."
    )

    # The version's parameter is left free to be called anything — it is the one
    # value passed positionally, so no call site spells it — while the two
    # keyword-only ones are the settled interface every caller writes out.
    by_keyword = sorted(
        parameter.name
        for parameter in signature.parameters.values()
        if parameter.kind is parameter.KEYWORD_ONLY
    )
    assert by_keyword == sorted(RENDERER_PARAMETERS[1:]), (
        f"`render_summary_prompt{signature}` takes {by_keyword} by keyword and E4-05's work "
        f"order settles {sorted(RENDERER_PARAMETERS[1:])}. A parameter outside that is an "
        "interface question for the ticket rather than something this test accepts quietly."
    )
    assert len(parameters) == len(RENDERER_PARAMETERS), (
        f"`render_summary_prompt{signature}` takes {len(parameters)} parameters; the settled "
        f"shape is {list(RENDERER_PARAMETERS)} — the prompt version, the stream, and the "
        "comment texts."
    )


def test_no_identity_appears_in_the_rendered_prompt_for_a_planted_week(
    summary_api: SummaryApi,
) -> None:
    """The same criterion measured on the text, with a canary and a control.

    **The canary comes first.** A renderer that answered the empty string, or that
    dropped every comment, would pass an assertion about what is *absent* — which
    is `docs/MISTAKES.md` entry 3 in its purest form. So the comments are asserted
    present, by nonce, before anything is asserted missing.

    **And the search is run in both directions.** Each needle is looked for in a
    string that certainly contains it, because a search that had gone blind — a
    case fold gone wrong, a match against the empty string — would report the
    prompt clean whatever it held.

    **The mutation this kills:** a renderer that grew a "context" header naming
    the section, or a debugging line carrying a response id. Neither would be
    caught by the structural test above if the value arrived through the module
    rather than through a parameter.
    """
    rendered = rendered_week(summary_api)

    assert rendered.strip(), "the renderer answered an empty prompt."
    for comment in PLANTED_COMMENTS:
        assert comment in rendered, (
            f"the planted comment {comment!r} is not in the rendered prompt, so this test would "
            "report 'no identity' about a prompt that carries no comments either."
        )

    carried = identity_in(rendered)
    assert not carried, (
        f"the rendered prompt carries {carried}. SPEC §4 keys responses to the LMS user id and "
        "lets identity out through the Care queue alone; E4-05 sends comment text to a "
        "provider and nothing else about who wrote it."
    )

    contaminated = rendered.replace(
        PLANTED_COMMENTS[0], f"{PLANTED_COMMENTS[0]} — {PLANTED_PERSON_NAME}, {PLANTED_USER_ID}"
    )
    assert identity_in(contaminated) == sorted((PLANTED_PERSON_NAME, PLANTED_USER_ID)), (
        "the control for the detector above: the same prompt with a name and a user id written "
        "into it was reported clean, so the clean result on the real render means nothing."
    )


def test_the_comments_are_the_last_thing_in_the_rendered_prompt(summary_api: SummaryApi) -> None:
    """The injection boundary, asserted at the one place a prompt can lose it.

    `backend/app/ai/prompts/README.md` rests the whole defence on the student's
    text running to the end of the message, and ADR 0053 keeps the gateway's
    bounded re-ask from appending anything after it. A summary prompt renders
    several comments rather than one, so the rule becomes: the last comment ends
    the prompt.

    **The mutation this kills:** a closing instruction after the placeholder —
    "now answer with JSON" — which is the natural way to end a prompt and hands
    the last word to whatever a student typed. **The near miss that must stay
    green:** trailing whitespace, which is layout rather than instruction.
    """
    rendered = rendered_week(summary_api)
    tail = rendered.rstrip()

    assert tail.endswith(PLANTED_COMMENTS[-1]), (
        "the rendered prompt does not end with the last comment; it ends "
        f"{tail[-160:]!r}. `backend/app/ai/prompts/README.md`: the student's text runs to the "
        "end of the message and nothing follows it, so a comment cannot be answered by an "
        "instruction it was written to defeat."
    )


def test_every_comment_is_rendered_once_verbatim_and_in_order(summary_api: SummaryApi) -> None:
    """A summary of the week is a summary of all of it, in the order it was given.

    §4's small-N rule sends under-threshold comments to the summary — "comments
    from under-threshold weeks are not discarded — they feed the summary" — so a
    renderer that dropped one, or that deduplicated, would quietly remove a
    student's week from the only signal their instructor gets.

    **The mutation this kills:** a renderer that joins the comments into one blob
    and truncates, one that renders only the first, and one that renders the same
    comment twice under two numbers (which would inflate every theme count a model
    produces). **The near miss that must stay green:** whatever numbering or
    separator the prompt uses — nothing here asserts the label, only that the
    comments are whole, once each, and in the order the caller gave them.
    """
    rendered = rendered_week(summary_api)

    for comment in PLANTED_COMMENTS:
        assert occurrences(rendered, comment) == 1, (
            f"the comment {comment!r} appears {occurrences(rendered, comment)} times in the "
            "rendered prompt. Once: a comment rendered twice is one a model counts twice, and "
            "a comment rendered never is a student the summary does not speak for."
        )

    positions = [rendered.index(comment) for comment in PLANTED_COMMENTS]
    assert positions == sorted(positions), (
        f"the comments are rendered in the order {positions}, which is not the order they were "
        "given in. §4 randomises comment *display* order on a report; the prompt is not a "
        "display, and a renderer that reorders makes two runs over one week two prompts."
    )

    separated = all(
        "\n\n" in rendered[positions[index] : positions[index + 1]]
        for index in range(len(positions) - 1)
    )
    assert separated, (
        "two consecutive comments are rendered with no blank line between them. E4-05 renders "
        "them as separate numbered blocks; run together, a comment ending mid-sentence reads "
        "as the beginning of the next one."
    )


def test_both_placeholders_are_substituted_and_the_stream_is_named_before_the_comments(
    summary_api: SummaryApi,
) -> None:
    """The prompt the provider receives has no template left in it.

    An unsubstituted placeholder is the failure that looks like success: the
    request is well-formed, the provider answers something, and the answer is
    about a template. E0-13's roundtrip module asserts the same property for the
    validity prompt after finding that "an empty prompt or an unsubstituted
    placeholder also passed".

    **The stream is asserted to come first**, because a summary is per-stream and
    a model told which stream it is reading *after* it has read the comments has
    been told nothing useful — and because a stream token rendered after the last
    comment would break the injection boundary the test above asserts.

    **The mutation this kills:** either placeholder left in the file with the
    substitution done for the other; a stream placeholder substituted with the
    enum's Python `repr`, which reads as a class name rather than as a stream.
    """
    rendered = rendered_week(summary_api, COURSE_STREAM)

    for constant in (SUMMARY_COMMENTS_PLACEHOLDER, SUMMARY_STREAM_PLACEHOLDER):
        placeholder = summary_api.constant(constant)
        assert placeholder not in rendered, (
            f"the rendered prompt still carries {placeholder!r}. A prompt sent with its "
            "placeholder intact is a request the provider answers about a template."
        )

    stream_at = rendered.lower().find(COURSE_STREAM)
    assert stream_at >= 0, (
        f"the rendered prompt never names the {COURSE_STREAM!r} stream. The task is one call "
        "per stream and the prompt is what says which one this call is about."
    )
    assert stream_at < rendered.index(PLANTED_COMMENTS[0]), (
        "the stream is named after the first comment. It belongs in the instructions, which "
        "run before the student text, not inside it."
    )


def test_a_prompt_without_the_placeholders_is_refused_rather_than_rendered(
    summary_api: SummaryApi,
) -> None:
    """The other direction of the placeholder rule, driven by a real file.

    E0-12's `render_prompt` refuses a prompt whose placeholder is missing, and the
    summary renderer inherits that rule: a template that has lost its
    substitution point renders to instructions with no comments in them, and a
    provider answers about a week it was never shown.

    The version used here is the *validity* prompt, resolved from the application
    rather than written down — a real committed file, certainly present, and
    certainly without the summary placeholders. A synthetic file could not show
    that the refusal happens on the path a version lookup takes.

    **The mutation this kills:** a renderer that substitutes what it finds and
    returns the rest unchanged, which produces a well-formed request for a summary
    of nothing. **Its pair is every test above**, where the real version renders.
    """
    render = summary_api.render()
    tasks = summary_api.tasks()
    prompt_error = summary_api.named(
        tasks,
        PROMPT_ERROR,
        "E0-12's renderer refuses a prompt with no placeholder and E4-05's renderer inherits "
        "the rule; the error class is where that refusal is named.",
    )
    other_version = summary_api.named(
        tasks,
        VALIDITY_PROMPT_VERSION_CONSTANT,
        "E0-13 shipped it and `tests/evals/live.py` sends it; this test needs one committed "
        "prompt that certainly does not carry the summary placeholders.",
    )

    with pytest.raises(prompt_error) as raised:
        render(
            other_version,
            stream=summary_api.stream(INSTRUCTOR_STREAM),
            comments=PLANTED_COMMENTS,
        )

    message = str(raised.value)
    assert other_version in message or "placeholder" in message.lower(), (
        f"the refusal says {message!r}, which names neither the version it could not render "
        "nor the placeholder it looked for. Whoever meets this in a log needs one of the two."
    )
    for comment in PLANTED_COMMENTS:
        assert comment not in message, (
            "the refusal quotes a student's comment back into its message. E3's decision 10 "
            "keeps student content out of worker logs and E4-06 relies on it."
        )


def test_the_renderer_answers_a_string_and_nothing_else(summary_api: SummaryApi) -> None:
    """A control on every assertion above, run before their silence is believed.

    All of them search a value this returns. A renderer answering a template
    object, a list of messages, or a tuple would make `in` mean something else
    entirely — membership in a sequence rather than a substring — and several of
    the assertions above would pass or fail for reasons that have nothing to do
    with what they say.

    **A red here means these tests are broken, or the renderer's contract has
    moved, and reading this one first says which.**
    """
    rendered: Any = rendered_week(summary_api)

    assert isinstance(rendered, str), (
        f"the renderer answered {type(rendered).__name__}. E0-12's `render_prompt` answers the "
        "prompt text, and the gateway sends what it is given."
    )
