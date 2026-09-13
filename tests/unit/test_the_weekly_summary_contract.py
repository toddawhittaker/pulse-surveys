"""The weekly-summary contract: what the model produces, and what the caller adds — E4-05.

E4-05's scope splits the contract in two, and the split is the ticket's main
design decision: "the typed contract in `contracts.py`: the summary text, the
themes it found, and room for the held-note (type only) that E6's moderation will
make real. **The stated response count is injected by the caller from data, never
trusted from the model** — the contract carries what the model must produce, and
the ADR draws that line explicitly."

That sentence is the whole subject of this module. SPEC §5.1 requires a summary to
"state the response count they draw from", and a count a model reports is a count
nobody checked: an instructor reading "drawn from 12 responses" under a week of
five would have no way to tell, and the number is arithmetic the caller already
has. So `WeeklySummaryOutput` carries what a model can be asked for and
`WeeklySummaryRecord` composes the count around it.

**The two classes are named rather than discovered**, unlike E0-13's validity
contract, which no ticket had ever spelled. E4-05's work order settles both, so a
test that went looking would be able to agree with an implementation that built
something else and called it something similar (`docs/MISTAKES.md` entry 19 — an
expectation held in a copy of the thing it checks).

**What is deliberately not asserted here.** Whether a summary is any *good* is a
distribution rather than an assertion: SPEC §9.3 answers it with an eval set, and
`tests/evals/summary/` is where E4-05 puts one. Nothing in this module reaches a
provider or renders a prompt.
"""

from __future__ import annotations

from typing import Any

import pytest
from fixtures.summary_task import (
    COMMENT_STREAM,
    COMMENT_THEME,
    COURSE_STREAM,
    INSTRUCTOR_STREAM,
    WEEKLY_SUMMARY_OUTPUT,
    WEEKLY_SUMMARY_RECORD,
    SummaryApi,
    normalised,
)
from pydantic import ValidationError

# Every way a count of the week's responses might be spelled on a contract.
# **This suite's choice**, and it is a list rather than one name because the
# criterion is that the model produces *no* such field, and a check against a
# single spelling is defeated by a rename. `comment_count` is the field E4-05
# removes from the model-produced contract; the others are what it would come
# back as.
RESPONSE_COUNT_SPELLINGS = (
    "responsecount",
    "commentcount",
    "responses",
    "comments",
    "count",
    "ncomments",
    "nresponses",
    "respondents",
)

# The audit pair ADR 0031 puts on every task output and forbids a model to report.
PROMPT_VERSION_FIELD = "prompt_version"
MODEL_ID_FIELD = "model_id"

# Values this module builds answers out of. Nothing here is asserted for its own
# sake; they exist so a contract can be constructed and read back.
A_SUMMARY = "Four comments are about the pace of the Thursday class."
A_THEME_LABEL = "Thursday class moved too quickly"
A_PROMPT_VERSION = "summary.v1"
A_MODEL_ID = "e4-05-contract-test-model"


def output_for(api: SummaryApi, **overrides: Any) -> Any:
    """One `WeeklySummaryOutput`, with the audit pair filled in.

    ADR 0031 makes `prompt_version` and `model_id` required on every task output
    and has the gateway supply both, so a test that omitted them would fail inside
    its own fixture on a rule that is not its subject (`docs/MISTAKES.md` entry
    13).
    """
    model = api.contract(WEEKLY_SUMMARY_OUTPUT)
    values: dict[str, Any] = {
        "stream": api.stream(INSTRUCTOR_STREAM),
        "summary": A_SUMMARY,
        "themes": (),
        PROMPT_VERSION_FIELD: A_PROMPT_VERSION,
        MODEL_ID_FIELD: A_MODEL_ID,
    }
    values.update(overrides)
    return model(**values)


def test_the_model_produced_contract_states_no_response_count(summary_api: SummaryApi) -> None:
    """The line the ticket draws: the model says what it found, never how many there were.

    SPEC §5.1 has a summary "state the response count they draw from", and E4-05
    settles where that number comes from — the caller, from data. A field for it
    on the model-produced contract is the defect this criterion is about, because
    a validated object carrying a plausible wrong number is indistinguishable from
    one carrying the right one, and the instructor is the only person who could
    notice.

    **The mutation this kills:** `comment_count` left on `WeeklySummaryOutput`,
    which is the shape this ticket changes and the one an implementation arrives
    at by editing the class in place. **The near miss that must stay green:**
    `CommentTheme.comment_count`, which is a count *of a theme* and is the model's
    to produce — so this looks only at the summary contract's own fields.
    """
    output_model = summary_api.contract(WEEKLY_SUMMARY_OUTPUT)

    counted = sorted(
        name for name in output_model.model_fields if normalised(name) in RESPONSE_COUNT_SPELLINGS
    )
    assert not counted, (
        f"`{WEEKLY_SUMMARY_OUTPUT}` carries {counted}, which asks the model for a count of the "
        f"week's responses. It holds {sorted(output_model.model_fields)}. E4-05: 'the stated "
        "response count is injected by the caller from data, never trusted from the model'."
    )

    theme_model = summary_api.contract(COMMENT_THEME)
    assert any(normalised(name) == "commentcount" for name in theme_model.model_fields), (
        f"`{COMMENT_THEME}` carries no comment count ({sorted(theme_model.model_fields)}). The "
        "ticket settles that themes carry per-theme counts now so E7's draft check does not "
        "need a second model call over the same text — this is the near miss the assertion "
        "above must not have taken with it."
    )


def test_the_record_carries_the_response_count_the_caller_injected(summary_api: SummaryApi) -> None:
    """The other half of the split: a record composes the count around the output.

    E4-06 stores this record, and SPEC §5.1's "state the response count they draw
    from" is met by the caller's arithmetic rather than by the model's claim.

    **The mutation this kills:** a record that recomputes or re-derives the count
    from the themes it was given — which would be the model's number again, one
    indirection further away — and a record that drops it, leaving §5.1's sentence
    with nothing behind it.
    """
    record_model = summary_api.contract(WEEKLY_SUMMARY_RECORD)
    output = output_for(summary_api)

    record = record_model(summary=output, response_count=7)

    assert record.response_count == 7, (
        f"the record was built with a response count of 7 and reports "
        f"{record.response_count}. The caller injects this number from data."
    )
    assert record.summary is output or record.summary == output, (
        f"the record carries {record.summary!r} rather than the output it was composed from. "
        "E4-06 stores the model's answer and the caller's count together."
    )


@pytest.mark.parametrize("count", (0, 1, 250))
def test_the_record_accepts_any_count_of_responses_a_week_can_have(
    summary_api: SummaryApi, count: int
) -> None:
    """Zero is a real answer, and the empty week is why.

    A week with no responses has a summary — E4-05's fourth criterion — and its
    count is zero. A contract that required a positive count would make the empty
    shape unconstructible, and the task would have to lie or fail.

    **The mutation this kills:** `ge=1` on the response count, which reads as
    tidy and makes the one case §5.1 singles out impossible. **Its pair is the
    test below**, where a negative count must be refused, so this cannot be
    satisfied by a contract that validates nothing.
    """
    record_model = summary_api.contract(WEEKLY_SUMMARY_RECORD)

    record = record_model(summary=output_for(summary_api), response_count=count)

    assert record.response_count == count


def test_the_record_refuses_a_negative_response_count(summary_api: SummaryApi) -> None:
    """A count of responses below zero is not a week, it is a defect upstream.

    **The mutation this kills:** the bound removed altogether. Its pair is the
    test above: together they say the accepted range starts at zero, and neither
    is worth anything alone — a contract that accepts everything passes the first,
    and one that accepts nothing passes this one.
    """
    record_model = summary_api.contract(WEEKLY_SUMMARY_RECORD)

    with pytest.raises(ValidationError) as raised:
        record_model(summary=output_for(summary_api), response_count=-1)

    assert "response_count" in str(raised.value), (
        f"the record refused a negative count and the refusal does not name the field: "
        f"{raised.value}. A validation error that names the wrong field sends the reader to "
        "the wrong place."
    )


def test_the_summary_text_may_not_be_empty(summary_api: SummaryApi) -> None:
    """A summary is prose, and an empty string is a summary that says nothing.

    §5.1 makes the summary the only comment signal an instructor gets in a small-N
    week, so an answer that validated with an empty string would put a blank panel
    on the report and record it as a successful generation. The empty *week* has
    its own stated text, which is not the same thing as no text.

    **The mutation this kills:** `summary: str` with no minimum, which accepts
    `""` from a provider that answered with an empty object shape. **Its pair is
    the one-character case below it**, so this cannot be satisfied by a contract
    that refuses every summary.
    """
    with pytest.raises(ValidationError) as raised:
        output_for(summary_api, summary="")

    assert "summary" in str(
        raised.value
    ), f"an empty summary was refused without the error naming the field: {raised.value}"

    kept = output_for(summary_api, summary="No.")
    assert kept.summary == "No.", (
        "a short but non-empty summary was not kept. The rule is that there is text, not that "
        "there is a particular amount of it."
    )


def test_a_theme_claims_at_least_one_comment(summary_api: SummaryApi) -> None:
    """A theme is something several comments said; a theme of nothing is invented.

    The counts are what E7's draft check reads — "names themes the draft hasn't
    addressed, with comment counts" (§5.3) — so a theme reporting zero comments
    would put "0 comments" in front of an instructor as if it meant something.

    **The mutation this kills:** the lower bound dropped from the theme's count.
    **Its pair is the second half of this test**, where exactly one is accepted:
    a single comment can be a theme, and a bound of two would silently drop the
    small-N week's only signal.
    """
    theme_model = summary_api.contract(COMMENT_THEME)

    with pytest.raises(ValidationError):
        theme_model(label=A_THEME_LABEL, comment_count=0)

    theme = theme_model(label=A_THEME_LABEL, comment_count=1)
    assert theme.comment_count == 1


def test_the_held_note_is_absent_by_default_and_carries_a_type_when_it_is_present(
    summary_api: SummaryApi,
) -> None:
    """E6's room, and it is empty in E4 — which is the half that has to be asserted now.

    SPEC §5.1: above small-N a summary "may note 'one comment is held for review'
    with type only". E6 writes the moderation states that populate it; E4 leaves
    the field absent. A default of anything other than absent would put a held
    note on every summary this epic generates, with no moderation behind it.

    **The mutation this kills:** a default of `""` or of a placeholder string,
    either of which renders as a note in E4-10's panel. **The near miss that must
    stay green:** the field accepting a type when E6 supplies one, which is what
    the room is for.
    """
    record_model = summary_api.contract(WEEKLY_SUMMARY_RECORD)

    without = record_model(summary=output_for(summary_api), response_count=5)
    assert without.held_note_type is None, (
        f"a record built without a held note reports {without.held_note_type!r}. E6 has not "
        "been built; a note here is one the report would show with nothing behind it."
    )

    with_note = record_model(
        summary=output_for(summary_api), response_count=5, held_note_type="privacy"
    )
    assert with_note.held_note_type == "privacy", (
        "the record did not keep the held-note type it was given, so E6 has no room to write "
        "into after all."
    )


def test_the_prompt_version_and_model_id_reach_a_caller_through_the_record(
    summary_api: SummaryApi,
) -> None:
    """Acceptance criterion 6, at the contract level: E4-06 stores them without re-deriving.

    SPEC §7.4 rests the single-shot boundary on exactly this pair — "a specific
    prompt version and model ID produced a specific classification for a specific
    comment" — and E4-02's columns are where they land. A record that dropped them
    would leave E4-06 reading a constant out of `app.ai.tasks` and calling it what
    produced the summary, which is a record of what the code says rather than of
    what happened.

    **The mutation this kills:** a record composed of the summary text alone,
    which is the natural shape if the record is thought of as "the row".
    """
    record_model = summary_api.contract(WEEKLY_SUMMARY_RECORD)

    record = record_model(summary=output_for(summary_api), response_count=3)

    assert getattr(record.summary, PROMPT_VERSION_FIELD, None) == A_PROMPT_VERSION, (
        "the prompt version the answer was produced under is not readable from the record. "
        "E4-06 stores it, and re-deriving it from a constant would record the configuration "
        "rather than the run."
    )
    assert (
        getattr(record.summary, MODEL_ID_FIELD, None) == A_MODEL_ID
    ), "the model that answered is not readable from the record."


def test_the_contract_knows_exactly_the_two_streams_the_report_groups_comments_under(
    summary_api: SummaryApi,
) -> None:
    """§5.1's two groups, transcribed rather than derived.

    "De-identified comments **grouped under 'About the instructor' / 'About the
    course'**, each group led by its own AI summary." Two streams, everywhere in
    the product, and E4-05 makes the task one call per stream so a course
    complaint cannot be summarized into the instructor stream.

    **The mutation this kills:** a third stream, or the two folded into one —
    either of which makes the per-stream call meaningless while every other test
    in this ticket goes on passing, because they ask for one stream and get one
    back. The names are this file's transcription of the specification's own
    words, deliberately not read off the enum (`docs/MISTAKES.md` entry 19): an
    enum read into its own assertion agrees with itself.
    """
    streams = summary_api.contract(COMMENT_STREAM)

    assert summary_api.stream(INSTRUCTOR_STREAM) != summary_api.stream(COURSE_STREAM), (
        "the two streams resolve to the same member, so nothing separates a comment about the "
        "instructor from a comment about the course."
    )
    assert len(list(streams)) == 2, (
        f"`{COMMENT_STREAM}` offers {[member.name for member in streams]}. SPEC §5.1 groups "
        "every comment under 'About the instructor' / 'About the course' and the product has "
        "no third group; a stream nothing renders is a summary nobody reads."
    )
