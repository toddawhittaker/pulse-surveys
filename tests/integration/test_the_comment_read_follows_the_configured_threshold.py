"""Where the small-N boundary is, and whose number decides it — tickets E4-04 and E5.1-01.

SPEC §4 states the rule and its configurability in one breath: raw comments are
hidden below the n-threshold, and "Threshold value is configurable (default 5)."
Two separate claims, and E4-04's third known trap is that a suite run against an
environment carrying 5 cannot tell them apart — "the configured value" and "the
spec's default" are then the same number, and a service holding a literal 5
satisfies both. E0-41's mutation battery measured exactly that survivor one ticket
over, in `services/authz.py`.

**What the threshold counts changed in E5.1-01**, and this module is where §4.1
item 3 is asserted, so it changed here too. E4-04 compared the week's *responses*
with the threshold. The owner's ruling 1 makes the unit **distinct students who
commented in that stream that week**: a week of six responses in which one student
wrote about the instructor shows that one comment under a count of responses, and
the gradebook's per-week completion ledger (ADR 0125) names its author.

So this module drives the boundary four ways:

  - **one commenter below the threshold**, which must return nothing;
  - **exactly at the threshold**, which must return the week's comments — the
    other half of the same pair, and the half that says `<` was not written where
    `<=` was meant;
  - **the same pair in weeks whose response count is at or above the threshold
    while the stream's commenter count is not** — the only worlds in which a gate
    counting responses and a gate counting commenters answer differently, so the
    only pair that turns red when the count is swapped back to responses
    (E5.1-01, criterion 2);
  - **under an institution's own threshold that is deliberately not SPEC §4's
    default**, both sides again, so nothing here is satisfied by a hard-coded 5.

In the first two and the last, every response carries one comment in the stream
read, so the response count and the commenter count are the same number; those
tests pin where the boundary is and whose number it is, and the third pair pins
what is counted.

**Every planted week's counts are read back out of the database** before any
assertion about them, which is E4-04's first known trap answered: a "week of four"
that seeded three is a fixture bug that makes every suppression assertion in this
epic true for the wrong reason, silently.

**Which failure a red is, before E4-04 lands.** `comment_contract.visible()` is a
`pytest.fail` naming `app.services.report_comments` and the signature the work
order settles — a FAILED assertion, not a setup error
(`docs/MISTAKES.md` entry 44). Before E5.1-01 lands, the commenter pair's hidden
halves fail on an assertion: a read counting responses shows the thin stream.
"""

from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest
from fixtures.report_comments import (
    COMMENT_SERVICE_MODULE,
    VISIBLE_FUNCTION,
    VISIBLE_IS_OWED,
    CommentWorld,
    configured_threshold,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

# **Marked `invariant`, which puts this module in CI's isolated §4.1 pass** where a
# skip or an empty collection is a failure (`scripts/ci/check_invariants.py`).
# §4.1 item 3 in its literal form: "below the n-threshold, raw comments are hidden
# from instructors and students alike". A read that compares against a literal
# rather than against the configured threshold obeys SPEC §4's default and stops
# obeying the institution the day they raise it — and the failure direction is
# disclosure, not refusal.
pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# Two term weeks inside cohort `F`'s run (term weeks 7 to 12).
BELOW_WEEK = 7
AT_WEEK = 8

# An institution's own threshold, chosen **not** to be SPEC §4's default and
# asserted to differ before it is used. Seven rather than three, so that the
# spec's default of five is strictly *inside* the gap: a week of five responses
# is at the boundary under the default and below it under this one, which is the
# single planted week that tells a lookup from a literal.
INSTITUTIONS_OWN_N_THRESHOLD = 7

A_COMMENT = "the two lab sessions covered the same material and neither reached the assessed part"


def a_week_of(count: int) -> list[str]:
    """`count` distinct comment texts."""
    return [f"{A_COMMENT} (response {index + 1})" for index in range(count)]


def read_week(read: Any, world: CommentWorld, term_week: int, stream: str) -> Any:
    """What the read path answers for one of this world's weeks."""
    return read(
        world.session,
        section_id=world.section_id(),
        week_id=world.week_id(term_week),
        stream=stream,
    )


def plant(world: CommentWorld, *, below: int, at: int, stream: str) -> None:
    """Two weeks of the sizes the caller named, with the counts asserted from the database."""
    world.build()
    world.close_week(BELOW_WEEK).close_week(AT_WEEK)
    world.week_of_comments(term_week=BELOW_WEEK, texts=a_week_of(below), stream=stream)
    world.week_of_comments(term_week=AT_WEEK, texts=a_week_of(at), stream=stream)

    planted = (world.responses_in(term_week=BELOW_WEEK), world.responses_in(term_week=AT_WEEK))
    assert planted == (below, at), (
        f"The two weeks hold {planted} responses and this test planted {(below, at)}. E4-04's first "
        "known trap is that a fixture bug breaks this diff silently: a week that is not the size "
        "the test believes makes every assertion below true for a reason nobody chose."
    )


def test_a_week_one_response_below_the_threshold_returns_no_comments(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """The lower half of the boundary pair, at the configured value.

    One response fewer than the threshold, every response carrying a comment. SPEC
    §4 hides raw comments below the threshold, and "below" is where the rule
    bites: a week at the boundary is not small-N and a week one under it is.

    **The pair is the test below**, and both are needed. This half alone is passed
    by a service that suppresses everything; that half alone is passed by one that
    suppresses nothing.

    **The mutation it kills:** `>` written where `>=` was meant in the threshold
    comparison, which shifts the boundary by one and shows a whole week of a
    small section's comments.
    """
    contract = comment_contract
    threshold = contract.threshold()
    assert threshold >= 2, (
        f"The configured n-threshold is {threshold}, and a week strictly below it cannot hold a "
        "response at all. Nothing under this configuration is plantable, so this is a failure of "
        "the environment these tests run under rather than of the service."
    )

    plant(
        comment_world,
        below=threshold - 1,
        at=threshold,
        stream=contract.instructor_stream,
    )
    read = contract.visible()

    at_the_boundary = read_week(read, comment_world, AT_WEEK, contract.instructor_stream)
    assert at_the_boundary, (
        f"The week holding exactly {threshold} responses returned nothing, so the emptiness "
        "asserted below is what this path answers for every week and says nothing about the "
        "threshold. `test_a_week_exactly_at_the_threshold_returns_its_comments` in this module "
        "diagnoses that half."
    )

    below = read_week(read, comment_world, BELOW_WEEK, contract.instructor_stream)
    assert tuple(below) == (), (
        f"A week of {threshold - 1} responses — one below the configured threshold of {threshold} —"
        f" returned {[comment.text for comment in below]}. SPEC §4 gives an instructor "
        "distributions and the summary at that size and no raw comments, and §4.1 item 3 makes it "
        "an invariant rather than a convention."
    )


def test_a_week_exactly_at_the_threshold_returns_its_comments(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """The upper half: the boundary is inclusive, so `n = threshold` is not small-N.

    SPEC §4 defines small-N as "n < 5 responses in a reporting week", so the
    threshold value itself is the first size at which comments are shown. A
    service that hid the boundary week as well would satisfy every suppression
    test in this epic and would withhold a week of comments from every instructor
    whose section sat exactly on the line — a defect nothing else in the suite
    would report, because every other assertion here is about absence.

    **The mutation it kills:** `<=` written where `<` was meant, which moves the
    boundary the other way and is invisible to every below-threshold test.
    """
    contract = comment_contract
    threshold = contract.threshold()
    assert (
        threshold >= 2
    ), f"The configured n-threshold is {threshold}, and nothing is plantable below it."

    plant(comment_world, below=threshold - 1, at=threshold, stream=contract.instructor_stream)
    read = contract.visible()

    at_the_boundary = read_week(read, comment_world, AT_WEEK, contract.instructor_stream)
    assert len(at_the_boundary) == threshold, (
        f"A week of exactly {threshold} responses, each carrying one comment, returned "
        f"{len(at_the_boundary)} comments: {[comment.text for comment in at_the_boundary]}.\n\n"
        f"SPEC §4's small-N rule is 'n < {threshold} responses in a reporting week', so this week "
        "is not small-N and its comments are the instructor's to read. A boundary written one "
        "response too high withholds a week of feedback from exactly the sections the product "
        "exists to reach."
    )


def plant_by_stream(
    world: CommentWorld, *, term_week: int, instructor_only: int, course_only: int
) -> tuple[int, int, int]:
    """One closed week of two disjoint groups, and its three counts read back from the database.

    Answers `(responses, instructor commenters, course commenters)` so the test
    that planted the week asserts all three in its own body.
    """
    world.close_week(term_week)
    world.week_by_stream(
        term_week=term_week,
        instructor_only=instructor_only,
        course_only=course_only,
        label=A_COMMENT,
    )
    return (
        world.responses_in(term_week=term_week),
        world.commenters_in(term_week=term_week, stream=INSTRUCTOR_STREAM),
        world.commenters_in(term_week=term_week, stream=COURSE_STREAM),
    )


def test_a_stream_one_commenter_short_is_hidden_in_a_week_whose_responses_reach_the_threshold(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """The hidden half of the commenter pair — E5.1-01's criterion 2, and the one that counts.

    One week, two disjoint groups of respondents: `threshold - 1` students comment
    about the instructor and nothing else; `threshold` others comment about the
    course and nothing else. The week holds `2 x threshold - 1` responses — past
    the threshold — and the instructor stream holds one commenter fewer than it.
    The instructor stream must return nothing, beside the course stream of the
    same week returning its comments.

    **This is the world that tells the two counts apart**, which is why it is
    shaped this way rather than with every respondent commenting in both streams:
    there, responses and each stream's commenters are one number and a gate
    counting either passes. Here they differ, in the direction that discloses.

    **The mutation it kills:** the commenter count swapped back to the week's
    response count — `2 x threshold - 1` reaches the threshold and the thin stream
    is shown. **Near misses it also kills:** distinct commenters counted across the
    whole week rather than in the stream (`2 x threshold - 1` people commented
    somewhere); comment answers counted across the week (the same number, one
    answer each); and the stream filter dropped from the count, so the instructor
    stream borrows the course stream's commenters.

    **A near miss this world cannot reach, named rather than claimed**
    (`docs/MISTAKES.md` entry 14): comment answers counted *within* the stream
    rather than people. One student writes at most one comment per stream per week
    — one response per student per section-week (E2-05), one answer per question
    per response — so inside one stream-week the two counts are always equal, and
    no fixture world through the schema can pull them apart.

    **The pair is the test below**, which puts exactly the threshold of commenters
    behind a stream in the same shape of world and requires them shown.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 2, f"The configured n-threshold is {threshold}; nothing is below it."
    world.build()

    counts = plant_by_stream(
        world, term_week=BELOW_WEEK, instructor_only=threshold - 1, course_only=threshold
    )
    assert counts == (2 * threshold - 1, threshold - 1, threshold), (
        f"The week holds (responses, instructor commenters, course commenters) = {counts} and this "
        f"test planted {(2 * threshold - 1, threshold - 1, threshold)}. The responses must reach "
        "the threshold while the instructor stream's commenters do not, or a gate counting "
        "responses answers this week the same way as one counting commenters."
    )

    read = contract.visible()
    course = read_week(read, comment_world, BELOW_WEEK, contract.course_stream)
    assert len(course) == threshold, (
        f"The course stream of the same week answered {len(course)} comments, and {threshold} "
        "distinct students commented in it. Until it answers, the emptiness asserted below is what "
        "this read gives every stream (`docs/MISTAKES.md` entry 3)."
    )

    instructor = read_week(read, comment_world, BELOW_WEEK, contract.instructor_stream)
    assert tuple(instructor) == (), (
        f"The instructor stream answered {[comment.text for comment in instructor]}. "
        f"{threshold - 1} distinct students commented in it this week — one below the configured "
        f"threshold of {threshold} — while the week holds {2 * threshold - 1} responses.\n\n"
        "SPEC §4.1 item 3 hides raw comments below the n-threshold, and the owner's ruling 1 makes "
        "the threshold a count of distinct commenters in that stream. A read that shows this "
        "stream is counting the week's responses, or the week's commenters across both streams, "
        "and each of those is a count of something other than the people the threshold protects "
        "(`docs/MISTAKES.md` entry 50)."
    )


def test_a_stream_of_exactly_threshold_commenters_is_shown_beside_a_stream_one_short(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """The shown half of the commenter pair: exactly the threshold of commenters is not small-N.

    The mirror of the test above, in one week: `threshold` students comment about
    the instructor only; `threshold - 1` others comment about the course only. The
    instructor stream is shown in full; the course stream, one commenter short in
    a week of `2 x threshold - 1` responses, returns nothing.

    **Two halves in one world**, so neither is satisfied by a read that answers the
    same thing for every stream. The shown half is asserted first.

    **The mutation it kills:** `<=` written where `<` was meant in the commenter
    comparison, which hides a stream sitting exactly on the threshold — invisible
    to every hidden-stream test in this module. Its course half kills the count
    swapped back to responses a second time, in the other stream, so a gate that
    counted commenters for one stream and responses for the other is red in one of
    the two tests.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 2, f"The configured n-threshold is {threshold}; nothing is below it."
    world.build()

    counts = plant_by_stream(
        world, term_week=AT_WEEK, instructor_only=threshold, course_only=threshold - 1
    )
    assert counts == (2 * threshold - 1, threshold, threshold - 1), (
        f"The week holds (responses, instructor commenters, course commenters) = {counts} and this "
        f"test planted {(2 * threshold - 1, threshold, threshold - 1)}."
    )

    read = contract.visible()
    instructor = read_week(read, comment_world, AT_WEEK, contract.instructor_stream)
    assert len(instructor) == threshold, (
        f"The instructor stream answered {len(instructor)} comments: "
        f"{[comment.text for comment in instructor]}. Exactly {threshold} distinct students "
        "commented in it this week, which is the configured threshold, so it is not small-N and its "
        "comments are the instructor's to read. A boundary written one commenter too high withholds "
        "a week of feedback from exactly the streams that sit on the line."
    )

    course = read_week(read, comment_world, AT_WEEK, contract.course_stream)
    assert tuple(course) == (), (
        f"The course stream answered {[comment.text for comment in course]}. {threshold - 1} "
        f"distinct students commented in it — one below the threshold of {threshold} — in a week "
        f"of {2 * threshold - 1} responses. A read showing it is counting responses, or counting "
        "people across both streams, rather than the people who commented in this one."
    )


def test_the_boundary_moves_with_an_institutions_own_threshold(
    comment_world: CommentWorld,
    comment_contract: Any,
    documented_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    import_app_module: Callable[[str], ModuleType | None],
) -> None:
    """SPEC §4's "threshold value is configurable", driven on both sides of a value that is not 5.

    Two facts, and a single assertion could report either as the other, so both
    are asserted separately: `.env.example` documents SPEC §4's default, and the
    service reads whatever the institution configured. The week planted here holds
    **exactly SPEC §4's default number of responses** and the configured threshold
    is higher, so a service holding a literal 5 shows that week and a service that
    reads configuration hides it — which is the one planted week that tells them
    apart.

    **Why the module is re-imported.** A module that builds something out of
    `Settings` may read the environment once, at import time;
    `import_app_module` exists for exactly that. Re-importing after the override
    makes this test true of a service that reads `Settings` per call *and* of one
    that holds a `Settings` from import, so it asserts the criterion rather than
    an implementation of it — the same reasoning
    `tests/integration/test_a_resolved_scope_holds_care_beside_the_purview.py`
    records for the same configuration value.

    **The world is seeded before the re-import**, for the same reason that module
    seeds before it: `import_app_module` empties `app.*` out of `sys.modules`, and
    rows written through a mapped class afterwards would be written through a
    second registry.

    **The mutation it kills:** `threshold = 5`, or any other literal, in place of
    the `Settings` lookup — which is green against every other test in this epic,
    because the suite's own environment carries 5.
    **The near miss that must stay green:** a service that reads the value once at
    import, which is legitimate and is what the re-import accommodates.
    """
    contract = comment_contract
    documented = documented_env.get(contract.threshold_variable)
    assert documented is not None, (
        f"`.env.example` documents no `{contract.threshold_variable}`, so there is no "
        "institution-facing default at all and SPEC §4's 'threshold value is configurable' is a "
        "sentence about nothing."
    )
    assert int(documented) == contract.spec_default_threshold, (
        f"`.env.example` documents `{contract.threshold_variable}` as {documented!r} and SPEC §4's "
        f"default is {contract.spec_default_threshold}. That is a configuration defect rather than "
        "a service one, and it is asserted separately so the two are not reported as each other."
    )
    assert contract.spec_default_threshold < INSTITUTIONS_OWN_N_THRESHOLD, (
        f"This test runs under a threshold of {INSTITUTIONS_OWN_N_THRESHOLD}, which is not above "
        f"SPEC §4's default of {contract.spec_default_threshold}, so the planted week is not "
        "between the two numbers and a service holding the default would answer it the same way. "
        "Change `INSTITUTIONS_OWN_N_THRESHOLD` at the top of this file."
    )

    # A week of exactly the spec's default: shown under the default, hidden under
    # this institution's higher one. And a week at the institution's own
    # threshold, which is the presence half.
    plant(
        comment_world,
        below=contract.spec_default_threshold,
        at=INSTITUTIONS_OWN_N_THRESHOLD,
        stream=contract.instructor_stream,
    )

    monkeypatch.setenv(contract.threshold_variable, str(INSTITUTIONS_OWN_N_THRESHOLD))
    configured = configured_threshold()
    assert configured == INSTITUTIONS_OWN_N_THRESHOLD, (
        f"`Settings.n_threshold_default` reads {configured} after `{contract.threshold_variable}` "
        f"was set to {INSTITUTIONS_OWN_N_THRESHOLD}, so the override never reached configuration "
        "and everything below would be compared against a number nobody changed. That is a failure "
        "of this test's setup rather than of the service."
    )

    module = import_app_module(COMMENT_SERVICE_MODULE)
    assert module is not None, f"There is no `{COMMENT_SERVICE_MODULE}` module. {VISIBLE_IS_OWED}"
    read = getattr(module, VISIBLE_FUNCTION, None)
    assert callable(read), (
        f"`{COMMENT_SERVICE_MODULE}` exposes no callable `{VISIBLE_FUNCTION}`; it exposes "
        f"{sorted(name for name in vars(module) if not name.startswith('_'))}.\n\n"
        f"{VISIBLE_IS_OWED}"
    )

    stream = contract.instructor_stream
    at_the_institutions_boundary = read_week(read, comment_world, AT_WEEK, stream)
    assert len(at_the_institutions_boundary) == INSTITUTIONS_OWN_N_THRESHOLD, (
        f"Under a configured threshold of {INSTITUTIONS_OWN_N_THRESHOLD}, a week of "
        f"{INSTITUTIONS_OWN_N_THRESHOLD} responses returned "
        f"{len(at_the_institutions_boundary)} comments. Until this half answers, the suppression "
        "below is what this path does to every week."
    )

    at_the_spec_default = read_week(read, comment_world, BELOW_WEEK, stream)
    assert tuple(at_the_spec_default) == (), (
        f"A week of {contract.spec_default_threshold} responses returned "
        f"{[comment.text for comment in at_the_spec_default]} under an institution whose "
        f"configured threshold is {INSTITUTIONS_OWN_N_THRESHOLD}.\n\n"
        f"{contract.spec_default_threshold} is SPEC §4's *default* and this institution's "
        "configuration deliberately is not it — 'Threshold value is configurable (default 5)'. A "
        "week shown here is a service comparing against a literal rather than against "
        "`Settings.n_threshold_default`, which is a rule that stops being the institution's the day "
        "they change it."
    )
