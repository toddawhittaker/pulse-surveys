"""The per-stream gate, as a generated property over moderated worlds — E6-01, criterion 10.

`docs/tickets/e6/carried-from-e5.md`, "The per-stream gate has no generated
property": E5.1-01 made SPEC §4's threshold a count of distinct commenters in one
stream of one week, and the cutter's three legs per (section, term, stream), and
every test of it is a hand-built world. E6-01 adds two kinds of comment the
hand-built worlds never held — one with no verdict, and one with a threat or
self-harm verdict, possibly followed by a later `clear` — and both change who
counts. So the criterion asks for one property, over random worlds that include
both, asserting:

  1. **no answer is both visible under its week and in a batch;**
  2. **every shown stream has at least the threshold of unreleased commenters**
     — distinct students whose comment in that stream that week the view returns
     (it holds a verdict, and none of its verdicts was ever threat or self-harm)
     and which is in no batch;
  3. **every batch slice has the threshold of authors over two or more weeks** —
     a slice being one batch's members in one stream.

Beside them, two that are E6-01's own and cost nothing to check on the same
worlds: no unverdicted or Care-class comment is ever returned, released or
batched; and no comment of a section-week that still holds an unverdicted comment
is ever shown (work order decision 5).

**The generator provably draws the cases this docstring names**
(`docs/MISTAKES.md` entry 15). `NAMED_WORLDS` are drawn from explicitly, beside
the generated space, and
`test_the_named_worlds_carry_every_case_the_property_names` asserts each case is
present — and that the classifier reports nothing for a world carrying none of
them, so a classifier answering "yes" to everything is caught rather than read as
coverage.

**Nothing here recomputes the gate** (`docs/MISTAKES.md` entry 19). The
properties are relations over what the readers answered and what this test
planted: which students wrote which comments, which verdicts each holds. Whether
a stream *should* have been shown is never derived here; what is asserted is what
must be true of any stream that was.

**Each example is its own world on its own connection**, opened on the migrated
engine and rolled back at the end, because the cutter commits for itself and a
savepoint per example would not survive it.

**What this space does not reach**, stated rather than claimed: one section,
three closed weeks of cohort `F`, a pool of `POOL` students, and the threshold the
environment configures. Released comments are read once, after one cut.
"""

from typing import Any, NamedTuple

import pytest
from fixtures.clock import DEVELOPMENT
from fixtures.moderation import CLEAR, HARMFUL, SELF_HARM, THREAT, UNMODERATED
from fixtures.report_comments import CommentWorld, ReleaseRows
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.supervision import seed_row
from fixtures.survey_windows import Fall2026
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

pytestmark = [pytest.mark.integration, pytest.mark.invariant, pytest.mark.slow]

WEEKS = (7, 8, 9)
POOL = 8

# The moderation a response's comments are planted with, by name.
KINDS = {
    "clear": CLEAR,
    "harmful": HARMFUL,
    "threat": THREAT,
    "self-harm": SELF_HARM,
    "threat-then-clear": (THREAT, CLEAR),
    "self-harm-then-clear": (SELF_HARM, CLEAR),
    "unverdicted": UNMODERATED,
}
CARE_CLASS_KINDS = frozenset({"threat", "self-harm", "threat-then-clear", "self-harm-then-clear"})
UNVERDICTED_KIND = "unverdicted"

STREAM_SETS = {
    "instructor": (INSTRUCTOR_STREAM,),
    "course": (COURSE_STREAM,),
    "both": (INSTRUCTOR_STREAM, COURSE_STREAM),
}

DATABASE_BACKED = settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


class Response(NamedTuple):
    """One student's response in one week: who, which streams they commented in, how moderated."""

    student: int
    streams: str
    kind: str


World = dict[int, tuple[Response, ...]]


def world_of(weeks: dict[int, list[tuple[int, str, str]]]) -> World:
    return {week: tuple(Response(*entry) for entry in weeks.get(week, [])) for week in WEEKS}


# The worlds drawn from explicitly (`docs/MISTAKES.md` entry 15). Sized for the
# documented threshold of 5; the premise in the property says so. The first carries
# none of the cases and is the classifier's control.
EVERYONE_CLEAR = world_of({7: [(index, "instructor", "clear") for index in range(5)]})
AN_UNVERDICTED_COMMENT_IN_A_SHOWN_WEEK = world_of(
    {
        7: [
            *((index, "instructor", "clear") for index in range(6)),
            (6, "instructor", "unverdicted"),
        ]
    }
)
A_CARE_CLASS_COMMENT_IN_A_SHOWN_WEEK = world_of(
    {7: [*((index, "both", "clear") for index in range(5)), (5, "both", "threat")]}
)
A_LATER_CLEAR_ON_A_HELD_DISCLOSURE = world_of(
    {
        7: [(0, "instructor", "clear"), (1, "instructor", "clear"), (2, "instructor", "clear")],
        8: [(3, "instructor", "self-harm-then-clear"), (4, "instructor", "clear")],
        9: [(5, "instructor", "clear")],
    }
)
AN_UNVERDICTED_COMMENT_IN_A_RELEASABLE_HELD_SET = world_of(
    {
        7: [(0, "instructor", "clear"), (1, "instructor", "clear"), (2, "instructor", "clear")],
        8: [(3, "instructor", "clear"), (4, "instructor", "unverdicted")],
        9: [(5, "instructor", "clear"), (6, "course", "harmful")],
    }
)
NAMED_WORLDS = (
    EVERYONE_CLEAR,
    AN_UNVERDICTED_COMMENT_IN_A_SHOWN_WEEK,
    A_CARE_CLASS_COMMENT_IN_A_SHOWN_WEEK,
    A_LATER_CLEAR_ON_A_HELD_DISCLOSURE,
    AN_UNVERDICTED_COMMENT_IN_A_RELEASABLE_HELD_SET,
)

AN_UNVERDICTED_COMMENT = "an unverdicted comment"
A_CARE_CLASS_COMMENT = "a Care-class comment"
A_LATER_CLEAR = "a Care-class verdict followed by a later clear"
A_SHOWN_SIZED_WEEK_WITH_A_CASE = "a week of at least the threshold's size holding one of the cases"
THE_CASES = (
    AN_UNVERDICTED_COMMENT,
    A_CARE_CLASS_COMMENT,
    A_LATER_CLEAR,
    A_SHOWN_SIZED_WEEK_WITH_A_CASE,
)
NAMED_THRESHOLD = 5


def features_of(world: World, threshold: int = NAMED_THRESHOLD) -> set[str]:
    """Which of the named cases one world carries."""
    found: set[str] = set()
    for responses in world.values():
        kinds = {response.kind for response in responses}
        if UNVERDICTED_KIND in kinds:
            found.add(AN_UNVERDICTED_COMMENT)
        if kinds & CARE_CLASS_KINDS:
            found.add(A_CARE_CLASS_COMMENT)
        if kinds & {"threat-then-clear", "self-harm-then-clear"}:
            found.add(A_LATER_CLEAR)
        if len(responses) >= threshold and (UNVERDICTED_KIND in kinds or kinds & CARE_CLASS_KINDS):
            found.add(A_SHOWN_SIZED_WEEK_WITH_A_CASE)
    return found


def generated_worlds() -> st.SearchStrategy[World]:
    """The named worlds and a generated space, as one strategy."""
    response = st.tuples(
        st.integers(min_value=0, max_value=POOL - 1),
        st.sampled_from(sorted(STREAM_SETS)),
        st.sampled_from(sorted(KINDS)),
    )
    week = st.lists(response, unique_by=lambda entry: entry[0], max_size=POOL)
    generated = st.builds(
        lambda seven, eight, nine: world_of({7: seven, 8: eight, 9: nine}), week, week, week
    )
    return st.one_of(st.sampled_from(NAMED_WORLDS), generated)


def test_the_named_worlds_carry_every_case_the_property_names() -> None:
    """The control on the generator (`docs/MISTAKES.md` entry 15): the cases are in the space.

    Each case the property's docstring names is carried by at least one named
    world, so it is drawn by construction rather than by luck; and the classifier
    reports nothing for `EVERYONE_CLEAR`, so a classifier that answered every case
    for every world would be caught here rather than read as coverage.

    **Green on any tree**; it reads no database. A red here means the property's
    space has lost a case, not that the product has a defect.
    """
    assert features_of(EVERYONE_CLEAR) == set(), (
        f"The classifier reports {features_of(EVERYONE_CLEAR)} for a world of `clear` comments, "
        "so it cannot tell a world carrying the cases from one that does not."
    )
    carried = set().union(*(features_of(world) for world in NAMED_WORLDS))
    missing = [case for case in THE_CASES if case not in carried]
    assert not missing, f"No named world carries {missing}, so the property may never draw them."


class Planted(NamedTuple):
    week: int
    student: int
    stream: str
    kind: str
    text: str
    answer: Any


def eligible(kind: str) -> bool:
    """Whether the view returns a comment planted as `kind`: verdicted, and never Care-class."""
    return kind != UNVERDICTED_KIND and kind not in CARE_CLASS_KINDS


@DATABASE_BACKED
@given(world=generated_worlds())
def test_the_per_stream_gate_holds_over_worlds_with_unverdicted_and_care_class_comments(
    world: World,
    migrated_engine: Any,
    metadata_tables: dict[str, Any],
    comment_contract: Any,
) -> None:
    """Criterion 10: the three gate properties, plus E6-01's two, over one generated world.

    One section, three closed weeks, students drawn from a pool so that one person
    can comment in several weeks (`docs/MISTAKES.md` entry 50: the threshold counts
    people). Each response comments in one stream or both, planted with one
    moderation kind. The cutter runs once; then every week's two streams are read,
    the released list for both streams, and the batch membership.

    **The mutations this kills:** a shown stream counted with its unverdicted or
    Care-class commenters (property 2 — a stream of `threshold - 1` eligible
    commenters plus one Care-class one is shown); a batch whose authors include a
    Care-class comment's (property 3, and E6-01's first extra); a released comment
    still shown under its week (property 1); the comment read's per-comment filter
    in place of the section-week rule (E6-01's second extra).
    """
    from sqlalchemy.orm import Session

    connection = migrated_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        info={"environment": DEVELOPMENT},
    )
    try:

        def seed(name: str, chain: dict[str, Any] | None = None, /, **overrides: Any) -> Any:
            return seed_row(session, metadata_tables, name, chain, **overrides)

        place = CommentWorld(Fall2026(seed, session, metadata_tables))
        threshold = comment_contract.threshold()
        assert threshold <= POOL - 2, (
            f"The configured n-threshold is {threshold} and the student pool is {POOL}; the space "
            "cannot hold a shown stream beside a case."
        )
        place.build()
        students = [place.respondent() for _ in range(POOL)]
        planted: list[Planted] = []
        for week in WEEKS:
            place.close_week(week)
            for response in world[week]:
                streams = STREAM_SETS[response.streams]
                texts = {
                    stream: f"e6-01 property w{week} s{response.student} {stream} {response.kind}"
                    for stream in streams
                }
                _, written = place.submit(
                    term_week=week,
                    comments=texts,
                    moderation={stream: KINDS[response.kind] for stream in streams},
                    student=students[response.student],
                )
                for stream in streams:
                    planted.append(
                        Planted(
                            week,
                            response.student,
                            stream,
                            response.kind,
                            texts[stream],
                            place.answer_key(written[stream]),
                        )
                    )

        comment_contract.cut()(session)

        by_text = {entry.text: entry for entry in planted}
        by_answer = {entry.answer: entry for entry in planted}
        members = ReleaseRows(session, metadata_tables).members()
        batched = {row["answer_id"] for row in members}

        shown: dict[tuple[int, str], set[str]] = {}
        for week in WEEKS:
            for stream in (INSTRUCTOR_STREAM, COURSE_STREAM):
                answered = comment_contract.visible()(
                    session,
                    section_id=place.section_id(),
                    week_id=place.week_id(week),
                    stream=stream,
                )
                shown[(week, stream)] = {str(comment.text) for comment in answered}
        released_texts = set()
        for stream in (INSTRUCTOR_STREAM, COURSE_STREAM):
            released_texts |= {
                str(comment.text)
                for comment in comment_contract.released()(
                    session,
                    section_id=place.section_id(),
                    term_id=place.term_id(),
                    stream=stream,
                )
            }

        # E6-01's first extra: nothing unverdicted or Care-class reaches any reader.
        reached = sorted(
            entry.text
            for entry in planted
            if not eligible(entry.kind)
            and (
                entry.answer in batched
                or entry.text in released_texts
                or entry.text in shown[(entry.week, entry.stream)]
            )
        )
        assert not reached, f"Unverdicted or Care-class comments reached a reader: {reached}."

        # Property 1: no answer both visible under its week and in a batch.
        both = sorted(
            text
            for (week, stream), texts in shown.items()
            for text in texts
            if text in by_text and by_text[text].answer in batched
        )
        assert not both, f"Comments both shown under their week and in a batch: {both}."

        for (week, stream), texts in shown.items():
            if not texts:
                continue
            # E6-01's second extra: a shown section-week holds no unverdicted comment.
            waiting = [
                entry.text
                for entry in planted
                if entry.week == week and entry.kind == UNVERDICTED_KIND
            ]
            assert not waiting, (
                f"Term week {week}'s {stream} stream was shown while the week still held comments "
                f"with no verdict: {waiting}. A section-week is shown only once every comment in it "
                "holds one (work order decision 5)."
            )
            # Property 2: a shown stream has the threshold of unreleased commenters.
            unreleased = {
                entry.student
                for entry in planted
                if entry.week == week
                and entry.stream == stream
                and eligible(entry.kind)
                and entry.answer not in batched
            }
            assert len(unreleased) >= threshold, (
                f"Term week {week}'s {stream} stream was shown with {len(unreleased)} distinct "
                f"unreleased commenters whose comments the view returns; the threshold is "
                f"{threshold}. The comments shown were {sorted(texts)}."
            )

        # Property 3: every batch slice has the threshold of authors over two or more weeks.
        slices: dict[tuple[Any, str], list[Planted]] = {}
        for row in members:
            entry = by_answer.get(row["answer_id"])
            assert entry is not None, f"A batch holds a comment this world did not plant: {row}."
            slices.setdefault((row["batch_id"], entry.stream), []).append(entry)
        for (batch, stream), entries in slices.items():
            authors = {entry.student for entry in entries}
            weeks = {entry.week for entry in entries}
            assert len(authors) >= threshold and len(weeks) >= 2, (
                f"Batch {batch}'s {stream} slice holds {len(authors)} distinct authors over "
                f"{sorted(weeks)}; every slice needs the threshold of {threshold} over two or more "
                "weeks (ADR 0152, ADR 0153)."
            )
    finally:
        session.close()
        transaction.rollback()
        connection.close()
