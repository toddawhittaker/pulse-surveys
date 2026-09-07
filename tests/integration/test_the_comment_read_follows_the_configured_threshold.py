"""Where the small-N boundary is, and whose number decides it — ticket E4-04.

SPEC §4 states the rule and its configurability in one breath: "Small-N handling
(n < 5 responses in a reporting week): instructors see rating distributions and
the AI summary, but **no raw comments** … Threshold value is configurable
(default 5)." Two separate claims, and E4-04's third known trap is that a suite
run against an environment carrying 5 cannot tell them apart — "the configured
value" and "the spec's default" are then the same number, and a service holding a
literal 5 satisfies both. E0-41's mutation battery measured exactly that survivor
one ticket over, in `services/authz.py`.

So this module drives the boundary three times:

  - **one response below the threshold**, which must return nothing;
  - **exactly at the threshold**, which must return the week's comments — the
    other half of the same pair, and the half that says `<` was not written where
    `<=` was meant;
  - **under an institution's own threshold that is deliberately not SPEC §4's
    default**, both sides again, so nothing here is satisfied by a hard-coded 5.

**Every planted week's response count is read back out of the database** before
any assertion about it, which is E4-04's first known trap answered: a "week of
four" that seeded three is a fixture bug that makes every suppression assertion
in this epic true for the wrong reason, silently.

**Which failure a red is, before E4-04 lands.** `comment_contract.visible()` is a
`pytest.fail` naming `app.services.report_comments` and the signature the work
order settles — a FAILED assertion, not a setup error
(`docs/MISTAKES.md` entry 44).
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

pytestmark = pytest.mark.integration

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
