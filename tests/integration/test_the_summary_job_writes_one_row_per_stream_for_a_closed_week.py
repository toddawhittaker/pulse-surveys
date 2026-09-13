"""What the Monday walk stores for a section-week whose window has closed — ticket E4-06.

The ticket's scope, and the whole of this module's subject:

> The walk: sections with closed weeks lacking summary rows → per stream, gather
> the week's comments (under-threshold included, moderation-held excluded), call
> the task, store text, response count, themes if the contract carries them,
> prompt version, model id.

plus criterion 3 ("a small-N week gets its summary … with a two-response fixture
week"), criterion 4 ("the stored row's response count equals the count of
responses whose comments fed the call — injected from data") and criterion 7
("zero closed weeks is a clean no-op run").

**Every test drives the task, and nothing here imports the walk.** Where the walk
lives is the implementer's — the task, or a service module — and every criterion
above is about what it *does*. The task is also the only surface the ticket
settles a name for, so a suite that reached past it would be pinning a home the
ticket deliberately leaves open.

**The task opens its own session, and that is load-bearing twice over.** It
connects through `app.db`, whose engine is the application role's
(`tests/fixtures/database.py`), so every row written here is written through the
connection production uses and a missing grant fails these tests rather than
being driven around (`docs/MISTAKES.md` entry 46). And it means the world has to
be *committed* before the run and re-read after it, which
`tests/fixtures/summary_job.py` does.

**Whether a summary is any good is asked nowhere here.** SPEC §9.3 answers that
with an eval set and `tests/evals/summary/` holds it. The gateway double supplies
the model's answer so the job's behaviour *around* it can be measured
(`docs/MISTAKES.md` entry 30).

**Which failure a red here is.** Before E4-06 lands every test in this module is
expected red on `pytest.fail` naming `app.jobs.tasks` as a module with no
`generate_weekly_summaries` — a plain call in a test body, never a fixture
(`docs/MISTAKES.md` entry 44). A red naming `weekly_summary` instead means E4-02
is not in this branch; a red naming `summarize_stream` means E4-05 is not.
"""

from typing import Any

import pytest
from fixtures.summary_job import (
    A_CLOSED_TERM_WEEK,
    A_MODEL_ID,
    A_SUMMARY_TEXT,
    A_THEME_COUNT,
    A_THEME_LABEL,
    COURSE_STREAM,
    INSTRUCTOR_STREAM,
    StreamAwareGateway,
    SummaryWorld,
    UnreachableGateway,
    comment_text,
)

pytestmark = pytest.mark.integration

# The term week the world's other week is compared against: the next one, whose
# window has not closed when the clock stands just after this one's did. A pair,
# not a decoration — "the closed week is summarized" and "the open one is not"
# are one rule with one boundary, and either half alone is satisfied by a walk
# that visits everything or by one that visits nothing.
AN_OPEN_TERM_WEEK = A_CLOSED_TERM_WEEK + 1

# This suite's own values. The numbers are the subject of criterion 4 and are
# chosen so no two of them coincide: nine responses, three of which carry an
# instructor comment and one a course comment. §3.2 makes both comments optional
# above the rating threshold, so that is the ordinary week rather than a
# contrivance — and `len(comments)` cannot accidentally equal the truth.
RESPONSES_THAT_WEEK = 9
INSTRUCTOR_COMMENTS_THAT_WEEK = 3
COURSE_COMMENTS_THAT_WEEK = 1

# A two-response week, for criterion 3. Its being below the n-threshold is
# asserted from configuration in the test rather than assumed here, which is the
# ticket's named trap: "an 'even in small-N weeks' test that passes because the
# week was above threshold".
RESPONSES_IN_A_SMALL_WEEK = 2

# Tokens that appear nowhere else in this repository, so a match in a prompt is
# evidence rather than a coincidence (`docs/MISTAKES.md` entry 3).
A_NONCE = "Vt6XcRb1Nm"
ANOTHER_NONCE = "Hd3ZpKw8Qs"

# Two themes with counts that differ from each other and from every other number
# in this module, so that finding them in the stored column cannot be an accident
# of some other value serialising the same way.
TWO_THEMES = (("the Thursday proofs went too fast", 2), ("office hours helped", 3))


def a_week_of(
    world: SummaryWorld,
    *,
    cohort: str,
    term_week: int,
    responses: int,
    instructor_comments: int,
    course_comments: int,
    nonce: str = A_NONCE,
) -> dict[str, list[str]]:
    """`responses` students answer one section-week; some of them also write comments.

    Every student answers both ratings; the first `instructor_comments` of them
    write an instructor comment and the first `course_comments` a course comment,
    so the three numbers are independent and the caller states each. Nothing here
    computes an expectation — the texts are handed back so a test can say which
    of them fed the call.
    """
    written: dict[str, list[str]] = {INSTRUCTOR_STREAM: [], COURSE_STREAM: []}
    for index in range(responses):
        instructor = None
        course = None
        if index < instructor_comments:
            instructor = comment_text(INSTRUCTOR_STREAM, f"{nonce}-i{index}")
            written[INSTRUCTOR_STREAM].append(instructor)
        if index < course_comments:
            course = comment_text(COURSE_STREAM, f"{nonce}-c{index}")
            written[COURSE_STREAM].append(course)
        world.respond(
            f"{nonce}-subject-{cohort}-w{term_week}-{index}",
            cohort=cohort,
            term_week=term_week,
            instructor_comment=instructor,
            course_comment=course,
        )
    return written


def an_ordinary_week(world: SummaryWorld, contract: Any) -> dict[str, list[str]]:
    """The world most tests here run over: one section, one closed week, nine responses."""
    world.build(contract.a_cohort)
    planted = a_week_of(
        world,
        cohort=contract.a_cohort,
        term_week=A_CLOSED_TERM_WEEK,
        responses=RESPONSES_THAT_WEEK,
        instructor_comments=INSTRUCTOR_COMMENTS_THAT_WEEK,
        course_comments=COURSE_COMMENTS_THAT_WEEK,
    )
    world.clock_after(A_CLOSED_TERM_WEEK)
    world.commit()
    return planted


def streams_of(rows: list[dict[str, Any]], contract: Any) -> list[str]:
    return sorted(str(row[contract.stream_column]) for row in rows)


def test_a_closed_section_week_ends_with_exactly_one_summary_for_each_stream(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """The unit of work: two rows, one per stream, for the section-week that closed.

    SPEC §5.1 groups every comment under "About the instructor" / "About the
    course", "each group led by its own AI summary", and E4-02 gives the table one
    row per section, course week and stream. So a walk that visited a closed week
    and wrote one row has left half the report with no summary at all, and a walk
    that wrote three has written a row about a stream nothing renders.

    **The count and the streams are both asserted**, because neither says what the
    other does: two rows both about the instructor stream is exactly as wrong as
    one row, and E4-02's uniqueness rule would not refuse it across two weeks.

    **The mutation this kills:** a walk written per section-week rather than per
    stream, which is the natural shape if the summary is thought of as "the week's
    summary" — SPEC §5.1's report has two, and ADR 0148 makes them two calls
    precisely so a course complaint cannot be summarized into the instructor's.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    an_ordinary_week(summary_world, summary_job_contract)
    gateway = StreamAwareGateway(summary_contracts)

    summary_job_contract.run(gateway=gateway)

    stored = summary_world.summaries(
        section_id=summary_world.section_id(summary_job_contract.a_cohort)
    )
    assert streams_of(stored, summary_job_contract) == sorted(
        summary_job_contract.stored_streams
    ), (
        f"the closed section-week ended with {len(stored)} summary row(s) covering "
        f"{streams_of(stored, summary_job_contract)}. SPEC §5.1 leads each of the two comment "
        f"groups with its own summary, so a closed week ends with exactly "
        f"{list(summary_job_contract.stored_streams)} and nothing else."
    )
    for row in stored:
        assert row[summary_job_contract.week_column] == summary_world.week_id(A_CLOSED_TERM_WEEK), (
            f"a summary was written against week {row[summary_job_contract.week_column]} and the "
            f"closed week is {summary_world.week_id(A_CLOSED_TERM_WEEK)}. The row is keyed by the "
            "`week` row rather than by a course-week number, and this section's course week 1 is "
            "term week 7 — so a walk that stored an ordinal would key every section's summaries "
            "onto the same handful of rows."
        )


def test_only_the_week_whose_window_has_closed_is_summarized(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """The boundary the walk selects on, with a week on each side of it.

    SPEC §3.1 closes a window on Sunday at 23:59:59 and puts the report on Monday
    morning; the ticket's scope reaches "sections with closed weeks". A walk that
    summarized an *open* week would publish an AI summary of a survey students are
    still answering, and generation is once-and-done (breakdown decision 2) — so
    the partial week's summary is the one that week ever gets.

    **This is the pair, and each half is worthless alone.** A walk that visits
    nothing passes the second assertion; a walk that visits everything passes the
    first. Two answered weeks in one section, with the clock standing between
    their two closes, is the smallest world that distinguishes them.

    **The mutation this kills:** the close comparison written `>=` against the
    wrong instant, or dropped altogether so the walk selects on "has a
    `survey_window` row" — which is every week of the term from the day the
    windows are derived.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    summary_world.build(summary_job_contract.a_cohort)
    a_week_of(
        summary_world,
        cohort=summary_job_contract.a_cohort,
        term_week=A_CLOSED_TERM_WEEK,
        responses=RESPONSES_THAT_WEEK,
        instructor_comments=INSTRUCTOR_COMMENTS_THAT_WEEK,
        course_comments=COURSE_COMMENTS_THAT_WEEK,
    )
    a_week_of(
        summary_world,
        cohort=summary_job_contract.a_cohort,
        term_week=AN_OPEN_TERM_WEEK,
        responses=RESPONSES_THAT_WEEK,
        instructor_comments=INSTRUCTOR_COMMENTS_THAT_WEEK,
        course_comments=COURSE_COMMENTS_THAT_WEEK,
        nonce=ANOTHER_NONCE,
    )
    standing_at = summary_world.clock_after(A_CLOSED_TERM_WEEK)
    assert standing_at < summary_world.closes_at(AN_OPEN_TERM_WEEK), (
        f"the clock was stood at {standing_at} and term week {AN_OPEN_TERM_WEEK}'s window closes "
        f"at {summary_world.closes_at(AN_OPEN_TERM_WEEK)}, which is not later. Then both weeks are "
        "closed and this test asserts nothing about the boundary."
    )
    summary_world.commit()

    summary_job_contract.run(gateway=StreamAwareGateway(summary_contracts))

    stored = summary_world.summaries()
    closed_week = summary_world.week_id(A_CLOSED_TERM_WEEK)
    open_week = summary_world.week_id(AN_OPEN_TERM_WEEK)
    assert sorted(str(row[summary_job_contract.week_column]) for row in stored) == sorted(
        [str(closed_week)] * 2
    ), (
        f"the walk wrote {len(stored)} rows across weeks "
        f"{sorted({str(row[summary_job_contract.week_column]) for row in stored})}. The closed "
        f"week is {closed_week} and {open_week} is still open — students are still answering it, "
        "and a summary generated now is the only one that week will ever have."
    )


def test_the_stored_response_count_is_the_weeks_responses_and_not_its_comments(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """Criterion 4, and the number that is plausible when it is wrong.

    SPEC §5.1 has each summary "state the response count they draw from", and
    ADR 0148 settles where that number comes from: the caller, from data, never
    the model. §3.2 makes both comments optional above the rating threshold, so a
    week of nine responses carrying three comments is ordinary — and an instructor
    reading "drawn from 3 responses" under a week of nine is the only person who
    could notice, and cannot.

    **The construction is asserted, not assumed.** The three numbers are required
    to be distinct before the rows are read, because if the week happened to carry
    nine comments this test would pass against a walk that stored `len(comments)`
    (`docs/MISTAKES.md` entry 3).

    **Both streams are asserted and the course stream is the interesting one.** It
    carries one comment against nine responses, so a walk deriving the count from
    the comments it gathered per stream writes a 1 there — a walk that got the
    instructor stream right by coincidence still gets this one wrong.

    **The mutation this kills:** `response_count=len(comments)` at the call site,
    and a count taken from the model's themes one indirection further away.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    planted = an_ordinary_week(summary_world, summary_job_contract)

    counts = (
        RESPONSES_THAT_WEEK,
        len(planted[INSTRUCTOR_STREAM]),
        len(planted[COURSE_STREAM]),
    )
    assert len(set(counts)) == len(counts), (
        f"the week was built with {RESPONSES_THAT_WEEK} responses, "
        f"{len(planted[INSTRUCTOR_STREAM])} instructor comments and "
        f"{len(planted[COURSE_STREAM])} course comments, and two of those are equal. A walk "
        "storing `len(comments)` would then write the right number for the wrong reason and this "
        "test would say nothing."
    )

    summary_job_contract.run(gateway=StreamAwareGateway(summary_contracts))

    by_stream = summary_world.summaries_by_stream(
        section_id=summary_world.section_id(summary_job_contract.a_cohort)
    )
    for stream in summary_job_contract.stored_streams:
        assert stream in by_stream, (
            f"there is no {stream} summary to read a response count off; the walk wrote "
            f"{sorted(by_stream)}."
        )
        assert by_stream[stream][summary_job_contract.response_count_column] == (
            RESPONSES_THAT_WEEK
        ), (
            f"the {stream} summary states "
            f"{by_stream[stream][summary_job_contract.response_count_column]} responses and the "
            f"week had {RESPONSES_THAT_WEEK}. It carried {len(planted[INSTRUCTOR_STREAM])} "
            f"instructor comments and {len(planted[COURSE_STREAM])} course ones, so a count of "
            "either is the count of comments rather than of responses — SPEC §5.1's sentence is "
            "about responses and ADR 0148 puts the number in the caller's hand for exactly this "
            "reason."
        )


def test_each_stored_row_names_the_prompt_and_the_model_that_produced_it(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """ADR 0148's consequence: the provenance is a record of the run, not of the configuration.

    "E4-06 stores a `WeeklySummaryRecord` and reads the prompt version and model id
    off `record.summary`, without re-deriving either from a constant." SPEC §7.4
    requires every model output to store both, and §6.1's drift panel and §9.3's
    eval scoping are what spend them: a summary attributed to a model that did not
    write it is worse than one attributed to nothing.

    **The model id is a value this test chose**, arriving back through the record
    the double produced. A row naming it names the call that happened; a row
    naming whatever `app.ai.tasks` publishes names the configuration, and the two
    are indistinguishable unless the test supplies a model id no constant could
    be.

    **The summary text is asserted beside it** so that a row carrying the right
    provenance and somebody else's prose is a red here rather than a surprise on
    the report.

    **Its pair is the empty-stream test below**, where both values must be
    *different* ones. Together they say the row copies what the record carried; a
    walk that hard-coded either passes exactly one of the two.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    an_ordinary_week(summary_world, summary_job_contract)

    summary_job_contract.run(gateway=StreamAwareGateway(summary_contracts))

    by_stream = summary_world.summaries_by_stream(
        section_id=summary_world.section_id(summary_job_contract.a_cohort)
    )
    stored = by_stream.get(summary_job_contract.stored_instructor)
    assert stored is not None, (
        f"there is no instructor-stream summary; the walk wrote {sorted(by_stream)}. This test is "
        "about what a row produced by a model call carries."
    )
    assert stored[summary_job_contract.model_id_column] == A_MODEL_ID, (
        f"the row names {stored[summary_job_contract.model_id_column]!r} as the model that "
        f"answered, and the gateway this run was given reported {A_MODEL_ID!r}. A row naming "
        "anything else names a call that did not happen — most likely a constant read out of "
        "`app.ai.tasks` rather than the audit pair off `record.summary` (ADR 0148)."
    )
    assert stored[summary_job_contract.prompt_version_column] == summary_contracts.constant(
        summary_job_contract.summary_prompt_version_name
    ), (
        f"the row was produced under {stored[summary_job_contract.prompt_version_column]!r}. "
        "ADR 0032 makes a committed prompt immutable, so a version that does not name the file the "
        "call rendered leaves every later re-judgement of this summary pointed at a different text."
    )
    assert stored[summary_job_contract.text_column] == A_SUMMARY_TEXT, (
        f"the row carries {stored[summary_job_contract.text_column]!r} and the model answered "
        f"{A_SUMMARY_TEXT!r}. What an instructor reads has to be what came back."
    )


def test_a_stream_with_no_comments_still_gets_a_row_and_it_names_no_model(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """The empty group, which SPEC §5.1 gives a notice rather than a hidden heading.

    "Empty groups show a one-line notice, not a hidden heading." E4-11 renders
    that notice off a row; an absent row is an absent panel, and the reader cannot
    tell "nobody commented about the course" from "the job has not run".

    ADR 0148 point 3 settles what such a row costs: **nothing**. An empty stream
    reaches no model at all and `summarize_stream` answers the stated empty
    sentence under `EMPTY_WEEK_PROMPT_VERSION` and the gateway's `NOT_A_MODEL`. So
    the row exists, and its provenance says a model did not write it.

    **This is the half of the provenance pair that a constant cannot pass.** The
    test above requires a row to name the model that answered; this one requires
    the row *beside it, in the same run*, to name `NOT_A_MODEL` and the empty
    week's version. A walk that wrote `SUMMARY_PROMPT_VERSION` and the configured
    model id onto every row passes the first and fails here, and that is the whole
    reason the two are written as a pair (ADR 0148's consequence: "without
    re-deriving either from a constant").

    **No provider call is asserted for the empty stream, and the count of calls
    is.** Exactly one call for a week with one commented stream — the instructor's
    — because a request per empty stream per section per Monday is a bill nobody
    chose and the answer most likely to be invented.

    **The mutation this kills:** an empty stream skipped entirely ("nothing to
    summarize"), and an empty stream called anyway "for uniformity".
    """
    summary_job_contract.require_table(summary_world.world.tables)
    summary_world.build(summary_job_contract.a_cohort)
    a_week_of(
        summary_world,
        cohort=summary_job_contract.a_cohort,
        term_week=A_CLOSED_TERM_WEEK,
        responses=RESPONSES_THAT_WEEK,
        instructor_comments=INSTRUCTOR_COMMENTS_THAT_WEEK,
        course_comments=0,
    )
    summary_world.clock_after(A_CLOSED_TERM_WEEK)
    summary_world.commit()
    gateway = StreamAwareGateway(summary_contracts)

    summary_job_contract.run(gateway=gateway)

    assert len(gateway.calls) == 1, (
        f"the walk made {len(gateway.calls)} model calls for a week whose course stream carried no "
        "comments. ADR 0148 point 3: an empty stream reaches no model at all — asking anyway is "
        "the request most likely to come back with something invented, once per empty stream per "
        "section per Monday."
    )

    by_stream = summary_world.summaries_by_stream(
        section_id=summary_world.section_id(summary_job_contract.a_cohort)
    )
    empty = by_stream.get(summary_job_contract.stored_course)
    assert empty is not None, (
        f"the course stream carried no comments and got no summary row; the walk wrote "
        f"{sorted(by_stream)}. §5.1 gives an empty group a one-line notice, and E4-11 renders it "
        "off this row — an absent row is a reader who cannot tell an empty week from an unrun job."
    )
    assert empty[summary_job_contract.model_id_column] == summary_contracts.named(
        summary_contracts.gateway(),
        summary_job_contract.not_a_model_name,
        "ADR 0054 puts the marker in `app/ai/gateway.py` as `NOT_A_MODEL`, because the gateway is "
        "what knows no model answered.",
    ), (
        f"the empty stream's row names {empty[summary_job_contract.model_id_column]!r} as the "
        "model that answered. No model answered. A row naming this run's real model id is a row "
        "whose provenance was re-derived from configuration rather than read off the record — "
        "which is exactly what ADR 0148's consequence forbids, and the instructor-stream row in "
        "the same run would look correct while it happened."
    )
    assert empty[summary_job_contract.prompt_version_column] == summary_contracts.constant(
        summary_job_contract.empty_week_prompt_version_name
    ), (
        f"the empty stream's row was produced under "
        f"{empty[summary_job_contract.prompt_version_column]!r}. ADR 0054's rule: a record made "
        "without a model call names the reason in its audit pair rather than naming a prompt that "
        "was never rendered — and a reader asking which summaries no model produced selects on it."
    )
    assert empty[summary_job_contract.text_column] == summary_contracts.constant(
        summary_job_contract.empty_week_summary_name
    ), (
        f"the empty stream's row carries {empty[summary_job_contract.text_column]!r} and "
        "`app.ai.tasks` publishes the sentence an empty week states. The task states it once so "
        "each surface does not invent its own."
    )
    assert empty[summary_job_contract.response_count_column] == RESPONSES_THAT_WEEK, (
        f"the empty stream's row states "
        f"{empty[summary_job_contract.response_count_column]} responses and the week had "
        f"{RESPONSES_THAT_WEEK}. A stream with no comments is not a week with no responses: nine "
        "students answered and none of them wrote about the course."
    )


def test_the_themes_the_model_returned_reach_the_stored_row(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """The themes column, which E4-10 renders and §5.3's draft check will read.

    E4-05 settles that themes carry per-theme comment counts "now so E7's draft
    check does not need a second model call over the same text", and §5.3 names
    the surface: the check "quietly names any theme not yet addressed (with its
    comment count)". A walk that stored the summary prose and dropped the themes
    leaves that feature with nothing to read and E4-10's panel with nothing to
    show, and no other test in this repository would notice.

    **The counts are asserted as well as the labels**, and they are two different
    numbers on purpose. A walk that stored the labels alone — a list of strings,
    which is the shape a `[t.label for t in themes]` produces — keeps both labels
    and loses both counts, and would pass a test that only looked for the prose.

    **The column's storage shape is not pinned.** E4-02 chose it and this ticket
    does not change it, so what is asserted is that the labels and the counts are
    in there, whatever the encoding.

    **The mutation this kills:** `themes` left NULL because the contract carries
    them and the row does not, and a walk that stored `len(themes)` instead.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    an_ordinary_week(summary_world, summary_job_contract)
    gateway = StreamAwareGateway(
        summary_contracts,
        themes={
            INSTRUCTOR_STREAM: TWO_THEMES,
            COURSE_STREAM: ((A_THEME_LABEL, A_THEME_COUNT),),
        },
    )
    assert max(count for _label, count in TWO_THEMES) <= INSTRUCTOR_COMMENTS_THAT_WEEK, (
        f"this test scripts themes claiming up to {max(c for _l, c in TWO_THEMES)} comments over an "
        f"instructor stream of {INSTRUCTOR_COMMENTS_THAT_WEEK}. E4-05's task refuses a theme "
        "claiming more comments than the week held (ADR 0148 point 5), so the run would fail for a "
        "reason that is not this ticket's."
    )

    summary_job_contract.run(gateway=gateway)

    by_stream = summary_world.summaries_by_stream(
        section_id=summary_world.section_id(summary_job_contract.a_cohort)
    )
    stored = by_stream.get(summary_job_contract.stored_instructor)
    assert stored is not None, f"the walk wrote {sorted(by_stream)} and no instructor summary."
    held = summary_job_contract.themes_text(stored[summary_job_contract.themes_column])
    absent = [
        piece for label, count in TWO_THEMES for piece in (label, str(count)) if piece not in held
    ]
    assert not absent, (
        f"the stored themes carry none of {absent}; the column holds {held!r}. The model returned "
        f"{TWO_THEMES} and E4-02 gives the row a column for them, so a theme that did not survive "
        "the write is a theme E4-10 cannot render and E7's draft check cannot read — and the "
        "counts are the half that a list of labels silently loses."
    )


def test_a_two_response_week_gets_its_summaries(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
    summary_job_environment: Any,
) -> None:
    """Criterion 3: SPEC §5.1's "generated even in small-N weeks", as the asserted state.

    "AI summaries … are generated **even in small-N weeks** — there, the summary
    is the only comment signal." §4 hides the raw comments from the instructor
    below the threshold and does not discard them: "they feed the summary". So a
    walk that skipped a thin week would leave that instructor not with a thinner
    report but with an empty one, in exactly the weeks §4 designed the summary to
    carry.

    **The week is proven below the threshold rather than assumed to be**, which is
    the ticket's own named trap: "an 'even in small-N weeks' test that passes
    because the week was above threshold". The threshold is configuration —
    `N_THRESHOLD_DEFAULT`, SPEC §4's "configurable (default 5)" — so it is read
    off the `Settings` this run is made under and compared, rather than written
    here as a 5 that a deployment could move.

    **The mutation this kills:** a minimum response count or a minimum comment
    count in the walk, which reads as a sensible economy — why spend a model call
    on two comments — and removes the signal §4's small-N rule promises.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    threshold = getattr(summary_job_environment, "n_threshold_default", None)
    assert isinstance(threshold, int), (
        f"`Settings.n_threshold_default` is {threshold!r}. `.env.example` documents "
        "`N_THRESHOLD_DEFAULT` as the responses in a reporting week below which raw comments stay "
        "hidden, and without it this test cannot say its week is small-N rather than merely small."
    )
    assert threshold > RESPONSES_IN_A_SMALL_WEEK, (
        f"this week is built with {RESPONSES_IN_A_SMALL_WEEK} responses and the configured "
        f"n-threshold is {threshold}, so the week is not below it and this test would pass against "
        "a walk that summarizes only weeks above the threshold — which is the ticket's named trap."
    )

    summary_world.build(summary_job_contract.a_cohort)
    a_week_of(
        summary_world,
        cohort=summary_job_contract.a_cohort,
        term_week=A_CLOSED_TERM_WEEK,
        responses=RESPONSES_IN_A_SMALL_WEEK,
        instructor_comments=RESPONSES_IN_A_SMALL_WEEK,
        course_comments=RESPONSES_IN_A_SMALL_WEEK,
    )
    summary_world.clock_after(A_CLOSED_TERM_WEEK)
    summary_world.commit()

    summary_job_contract.run(gateway=StreamAwareGateway(summary_contracts))

    stored = summary_world.summaries(
        section_id=summary_world.section_id(summary_job_contract.a_cohort)
    )
    assert streams_of(stored, summary_job_contract) == sorted(
        summary_job_contract.stored_streams
    ), (
        f"a week of {RESPONSES_IN_A_SMALL_WEEK} responses — below the configured threshold of "
        f"{threshold} — ended with {len(stored)} summary row(s) covering "
        f"{streams_of(stored, summary_job_contract)}. §5.1 generates the summaries even in "
        "small-N weeks, and §4 hides the raw comments there, so these two rows are the whole of "
        "what that instructor is given about what their students said."
    )
    for row in stored:
        assert row[summary_job_contract.response_count_column] == RESPONSES_IN_A_SMALL_WEEK, (
            f"a small-N summary states {row[summary_job_contract.response_count_column]} responses "
            f"and the week had {RESPONSES_IN_A_SMALL_WEEK}. §5.1 has the summary state the count it "
            "drew from, and in a small-N week that number is also the reader's only clue how thin "
            "the week was."
        )


def test_a_run_with_no_closed_week_writes_nothing_and_reaches_no_provider(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """Criterion 7: "zero closed weeks (a term's first Friday) is a clean no-op run".

    The first Monday of a term is a real Monday and the beat entry fires on it. A
    walk that raised, or that wrote a summary of a week nobody has answered yet,
    would do so every term for every institution — and the failure would arrive as
    a Celery traceback in a stream nobody is watching on the quietest morning of
    the year.

    **The gateway fails on any attribute access at all**, so "no model call" is
    asserted without naming the method one would travel through: a run that finds
    nothing to do must not spend a provider request, and a double that answered
    politely would hide it.

    **The second half is what stops this being vacuous, and it is the pair.** With
    the clock moved past the same window's close and nothing else changed, the
    same world must produce its rows. Without that, this test is satisfied by a
    walk that never writes anything at all — which is precisely the tree it will
    first be run against (`docs/MISTAKES.md` entry 3).

    **The mutation this kills:** an unguarded `max()`, a division, or a `[0]` over
    an empty set of closed weeks, and a walk whose "closed" predicate is really
    "has a window row".
    """
    summary_job_contract.require_table(summary_world.world.tables)
    summary_world.build(summary_job_contract.a_cohort)
    a_week_of(
        summary_world,
        cohort=summary_job_contract.a_cohort,
        term_week=A_CLOSED_TERM_WEEK,
        responses=RESPONSES_THAT_WEEK,
        instructor_comments=INSTRUCTOR_COMMENTS_THAT_WEEK,
        course_comments=COURSE_COMMENTS_THAT_WEEK,
    )
    standing_at = summary_world.clock_before(A_CLOSED_TERM_WEEK)
    assert standing_at < summary_world.closes_at(A_CLOSED_TERM_WEEK), (
        f"the clock was stood at {standing_at}, which is not before this week's close at "
        f"{summary_world.closes_at(A_CLOSED_TERM_WEEK)}. Then there is a closed week after all."
    )
    summary_world.commit()

    summary_job_contract.run(gateway=UnreachableGateway())

    assert summary_world.summaries() == [], (
        f"a run over a term with no closed week wrote {summary_world.summaries()}. There is "
        "nothing to summarize on a term's first Monday, and a row written now is the only summary "
        "that week will ever have (breakdown decision 2 — there is no regeneration)."
    )

    summary_world.clock_after(A_CLOSED_TERM_WEEK)
    summary_job_contract.run(gateway=StreamAwareGateway(summary_contracts))

    assert streams_of(summary_world.summaries(), summary_job_contract) == sorted(
        summary_job_contract.stored_streams
    ), (
        "the canary for the no-op above: with the clock moved past the same window's close and "
        "nothing else changed, this world produced "
        f"{streams_of(summary_world.summaries(), summary_job_contract)} rather than the two rows a "
        "closed week ends with. So the empty table above was a walk that writes nothing at all "
        "rather than a walk that correctly found nothing to do."
    )
