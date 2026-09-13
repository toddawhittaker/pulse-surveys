"""What a released comment may say about itself — ticket E4-04, criteria 4 and 5.

Criterion 5 makes the week-attribution decision testable whichever way the ADR
rules it, and E4-04's work order rules it: **released batches present without
week grouping.** So the first branch of the criterion is the one asserted here —
"if releases drop week attribution, no released comment's payload or grouping
names its week".

This is not a rendering detail, and the ticket says why:

> a released under-threshold comment is grouped under a week, the ledger says who
> completed that week's comment items, and the intersection can be small.

That ledger is ADR 0125's: SPEC §3.4 posts a per-week participation ledger into
the gradebook, "Week 1: 4 of 5 items", and ADR 0125 accepts that an instructor
reads it. The acceptance rests on the ledger being a *completion* signal that the
gradebook already carries. It does not survive a released comment arriving under
a week heading: an instructor with the gradebook open then has a set of students
who completed that week's comment item and a comment known to come from it, and
in a four-response week the intersection can be one person. Dropping the week is
what keeps ADR 0125's acceptance true, and this module is what stops the week
coming back.

Criterion 4's other half is here too — "a released comment carries no timestamp"
— because it is the same assertion about the same value: `ReportComment`'s whole
field list, as an equality.

**Asserted as the forbidden state and as an inventory, never as a search for a
name** (`docs/MISTAKES.md` entry 2, and ADR 0146's reasoning about the membership
row's columns one layer down). A test that looked for a field called `week` would
pass against `course_week`, `period`, `when` or a `submitted_at` added by a later
ticket's convention.

**Marked `invariant` at the module level**, which puts it in the isolated §4.1
pass and satisfies
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`.

**Which failure a red is, before E4-04 lands.** Every test reaches the service
through `comment_contract`, whose lookups are `pytest.fail` calls naming the
deliverable — a FAILED assertion, not a setup error
(`docs/MISTAKES.md` entry 44).
"""

import dataclasses
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fixtures.report_comments import CommentWorld, ReleaseRows

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# Two held weeks, so "the release is not grouped by week" has two groups it could
# have been grouped into. One week could be flattened by accident and look right.
FIRST_HELD_WEEK = 7
SECOND_HELD_WEEK = 8
THIRD_HELD_WEEK = 9
HELD_WEEKS = (FIRST_HELD_WEEK, SECOND_HELD_WEEK, THIRD_HELD_WEEK)

# One comment per response, one or two responses per week, so every held week is
# under any plausible threshold and the comments are distinguishable by week.
A_COMMENT_FROM = {
    FIRST_HELD_WEEK: "the first week of the module moved much faster than the syllabus promised",
    SECOND_HELD_WEEK: "the second seminar had no reading attached and nobody knew what to prepare",
    THIRD_HELD_WEEK: "by the third week the group work had settled and the feedback was useful",
}


def plant_a_released_term(world: CommentWorld, contract: Any) -> dict[str, Any]:
    """Held comments across three closed under-threshold weeks, crossed and cut.

    Answers the planted comments by week and the batch rows, so a caller can ask
    what a release said about a comment whose week it knows.
    """
    threshold = contract.threshold()
    assert (
        threshold >= 2
    ), f"The configured n-threshold is {threshold}, and no week can be planted below it."

    world.build()
    per_week: dict[int, list[Any]] = {}
    planted = 0
    week_index = 0
    while planted < threshold:
        week = HELD_WEEKS[week_index % len(HELD_WEEKS)]
        world.close_week(week)
        texts = [f"{A_COMMENT_FROM[week]} (response {len(per_week.get(week, [])) + 1})"]
        per_week.setdefault(week, []).extend(
            world.week_of_comments(term_week=week, texts=texts, stream=contract.instructor_stream)
        )
        planted += 1
        week_index += 1

    for week, comments in per_week.items():
        count = world.responses_in(term_week=week)
        assert 0 < count < threshold, (
            f"Term week {week} holds {count} responses and the configured threshold is "
            f"{threshold}; a week that is not under it was never held, and it planted "
            f"{len(comments)} comments."
        )
    assert len(per_week) >= 2, (
        f"Only {len(per_week)} week(s) hold comments, and this module's whole subject is that a "
        "release is not grouped by week — which one week cannot show."
    )

    volume = world.comment_answers_in_term()
    assert volume >= threshold, (
        f"The section holds {volume} comment answers and the threshold is {threshold}, so nothing "
        "has crossed and there is no release to read."
    )

    cut = contract.cut()(world.session)
    assert cut == 1, (
        f"`{contract.cut_name}` cut {cut} batches over a section that crossed once. Until a batch "
        "exists, every assertion in this module is about an empty tuple."
    )
    return {"by_week": per_week, "threshold": threshold}


def test_a_report_comment_carries_exactly_text_status_and_stream(comment_contract: Any) -> None:
    """Criteria 4 and 5, made structural: the payload's whole field list, as an equality.

    `ReportComment` is what both reads answer with, so its fields are the whole of
    what a caller can be told about one comment. SPEC §4 says "timestamps are
    never shown with comments" and batches the release "so that timing cannot
    identify an author"; E4-04's work order drops week attribution on release. A
    field called `week`, `submitted_at`, `released_at` or `response_id` would make
    both statements false at once, and would do it in a diff that reads as a
    convenience.

    **An equality over the whole set, not a search for a name** — the same rule
    `tests/integration/test_report_schema.py` applies to
    `release_batch_member`'s columns, and for the reason ADR 0146 gives: a test
    looking for `released_at` passes against `surfaced_on`, `first_shown` or a
    `created_at` a later ticket's convention adds.

    **Frozen is asserted too**, because a mutable payload is a payload a caller
    can be handed and then decorate — and the decoration a caller reaches for
    first is the week it looked the comment up under.

    **The mutation it kills:** `week_id: UUID` added to the dataclass "so the
    payload layer can group", which is criterion 5's whole subject; and the class
    declared without `frozen=True`.
    """
    comment_class = comment_contract.comment_class()

    assert dataclasses.is_dataclass(comment_class), (
        f"`{comment_contract.comment_class_name}` is {comment_class!r}, which is not a dataclass. "
        "The work order settles it as a frozen dataclass so that what a caller may be told about "
        "one comment is a list somebody has to edit deliberately."
    )
    fields = tuple(field.name for field in dataclasses.fields(comment_class))
    assert fields == comment_contract.comment_fields, (
        f"`{comment_contract.comment_class_name}` carries {list(fields)} and E4-04 settles it as "
        f"{list(comment_contract.comment_fields)} and nothing else.\n\n"
        "SPEC §4: 'Comment display order is randomized; timestamps are never shown with comments', "
        "and held comments surface 'batched so that timing cannot identify an author'. E4-04's "
        "work order drops week attribution on release, and the ticket says why it is not a "
        "rendering detail: a released comment grouped under a week, read beside SPEC §3.4's "
        "per-week participation ledger in the gradebook (ADR 0125), narrows the author to the "
        "students who completed that week's comment item — a set that can be one person.\n\n"
        "A field added here is that channel or a timestamp, and either belongs in the pull request "
        "that argues for it."
    )
    assert comment_class.__dataclass_params__.frozen, (
        f"`{comment_contract.comment_class_name}` is a mutable dataclass. A caller that receives "
        "one can then set an attribute on it, and the attribute a caller reaches for first is the "
        "week it looked the comment up under — which is exactly what the release drops."
    )


def test_no_released_comment_carries_a_value_that_could_name_its_week(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """Criterion 5's first branch: no released comment's payload names its week.

    The comments in this world come from three different weeks and are released
    together. What comes back must say nothing that distinguishes them by week —
    not a week id, not a week number, not a date or an instant of any kind, and
    not a text that some implementation has helpfully prefixed with "Week 3:".

    **The forbidden state, enumerated over the values rather than over the field
    names.** The field list is pinned by the test above; this one asks what is
    actually *in* those fields, because a `stream` carrying `"INSTRUCTOR week 3"`
    or a `status` carrying a date passes a field-name inventory perfectly.

    **The pair is that the release is not empty**: the same read must return every
    held comment. A path that answered `()` would satisfy every absence here and
    would also mean SPEC §4's "they surface as raw text" never happens.

    **The mutation it kills:** a `week_id` smuggled into the payload under
    another name or inside another field, and a released comment whose text has
    been decorated with the week it came from.
    """
    contract = comment_contract
    world = comment_world
    planted = plant_a_released_term(world, contract)

    read = contract.released()
    released = read(
        world.session,
        section_id=world.section_id(),
        term_id=world.term_id(),
        stream=contract.instructor_stream,
    )

    every_planted = [comment for comments in planted["by_week"].values() for comment in comments]
    assert len(released) == len(every_planted), (
        f"The release read answered {len(released)} comments and the section held "
        f"{len(every_planted)}; the batch holds {len(release_rows.members())} memberships. SPEC §4: "
        "under-threshold comments 'surface as raw text once the section's cumulative comment volume "
        "for the term crosses the threshold'. Until they do, every absence asserted below is "
        "satisfied by a read that answers nothing."
    )

    week_ids = {world.week_id(week) for week in planted["by_week"]}
    week_numbers = set(planted["by_week"])
    forbidden: list[str] = []
    for comment in released:
        for field in dataclasses.fields(comment):
            value = getattr(comment, field.name)
            if value in week_ids:
                forbidden.append(f"{field.name}={value!r} is a `week` row's key")
            elif isinstance(value, datetime | date | time | timedelta):
                forbidden.append(f"{field.name}={value!r} is an instant or a duration")
            elif isinstance(value, int | Decimal) and not isinstance(value, bool):
                if value in week_numbers:
                    forbidden.append(f"{field.name}={value!r} is a term-week number")
            elif isinstance(value, str):
                for number in sorted(week_numbers):
                    if f"week {number}" in value.lower():
                        forbidden.append(f"{field.name}={value!r} names term week {number}")

    assert not forbidden, (
        "A released comment says which week it came from:\n  " + "\n  ".join(forbidden) + "\n\n"
        "E4-04's work order drops week attribution on release, and the ticket states the sharpest "
        "version of why: a released under-threshold comment grouped under a week, read beside the "
        "per-week participation ledger SPEC §3.4 posts into the gradebook (ADR 0125), narrows the "
        "author to the students who completed that week's comment item — and in a week of four "
        "responses that intersection can be one person. ADR 0125 accepts the ledger's disclosure "
        "precisely because it is a completion signal the gradebook already carries; it does not "
        "accept this."
    )


def test_the_release_arrives_as_one_flat_tuple_rather_than_grouped_by_week(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """Criterion 5's second half: no *grouping* names the week either.

    The payload is one half of "no released comment's payload or grouping names
    its week"; the shape of the return is the other. A mapping keyed by week, a
    tuple of per-week tuples, or a list of `(week, comments)` pairs carries the
    attribution in the container rather than in the comment, and every assertion
    about the payload above would still pass.

    **The pair is that the flat tuple holds every held comment**, from more than
    one week — so "flat" is not being satisfied by a release that happens to hold
    one week's worth.

    **The mutation it kills:** `dict[week_id, tuple[ReportComment, ...]]` as the
    return type, which is the shape somebody reaches for the moment a report
    surface wants to head each group with something.
    """
    contract = comment_contract
    world = comment_world
    planted = plant_a_released_term(world, contract)

    released = contract.released()(
        world.session,
        section_id=world.section_id(),
        term_id=world.term_id(),
        stream=contract.instructor_stream,
    )

    assert isinstance(released, tuple), (
        f"`{contract.released_name}` answered a {type(released).__name__}: {released!r}. The work "
        "order settles the return as a flat `tuple[ReportComment, ...]` — a mapping or a nesting "
        "carries the week attribution in the container, which criterion 5 forbids as plainly as it "
        "forbids a field."
    )

    comment_class = contract.comment_class()
    wrong = [item for item in released if not isinstance(item, comment_class)]
    assert not wrong, (
        f"The release holds {wrong!r}, which are not `{contract.comment_class_name}` instances. A "
        "tuple of per-week tuples is a flat tuple to `isinstance`, and this is what tells them "
        "apart."
    )

    every_planted = [comment for comments in planted["by_week"].values() for comment in comments]
    assert len(released) == len(every_planted), (
        f"The release holds {len(released)} comments and {len(every_planted)} were held across "
        f"{len(planted['by_week'])} weeks. A flat tuple holding one week's worth would satisfy the "
        "shape assertions above while grouping by week somewhere else."
    )
