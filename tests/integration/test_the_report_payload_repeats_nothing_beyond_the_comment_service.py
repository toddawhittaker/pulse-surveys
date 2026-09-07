"""What the assembly layer may add to a comment — ticket E4-07, criteria 4 and 6.

> The payload's comment and summary members are exactly what E4-04 and the
> summary table return — a test proves the service adds no field, no count, and
> no ordering information beyond them (no widening at the assembly layer, §4.1
> item 6's spirit).

E4-04 is where SPEC §4's suppression is decided, and it hands back
`ReportComment(text, status, stream)` and nothing else: SPEC §4 says "timestamps
are never shown with comments", ADR 0153 drops a released comment's week because
the gradebook's per-week ledger would otherwise name its author, and ADR 0152
places the released list in this payload. Every one of those guarantees is a
property of a *value* one module produces — and E4-07 is the first thing that
takes those values and builds something else out of them. An assembly layer that
adds an index, a count per week, or a submission instant it happened to have in
hand undoes all of it without touching the module that was reviewed line by line.

**So this module asserts the forbidden state rather than looking for a name**
(`docs/MISTAKES.md` entry 2). A test that searched for a field called `week` would
pass against `course_week`, `period`, `when`, or a `submitted_at` added by a later
ticket's convention. What is asserted is the field list as a subset of the
service's own, and then, at any depth inside a comment, that no value is an
instant and no value is any identifier this world planted.

**The comparison is against the service, not against a written-down list.** The
texts the payload carries are compared with what `visible_comments` and
`released_comments` answer on this suite's own session, so a payload that widened
what it shows is red even where the widening is a comment E4-04 would also have
returned under different arguments.

**Marked `invariant` at the module level**, which puts it in the isolated §4.1
pass and satisfies
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`.

**Which failure a red is, before E4-07 lands.** `report_api_contract` and
`comment_contract` both look their deliverables up inside the test body and fail
naming them, so the first red is a FAILED naming the router, the schema or the
comment service (`docs/MISTAKES.md` entry 44).
"""

from datetime import datetime
from typing import Any
from uuid import UUID

import pytest
from fixtures.report_api import (
    FIRST_HELD_WEEK,
    FULL_WEEK,
    RESPONSES_IN_WEEK,
    SILENT_WEEK,
    TERM_WEEK_OF_COURSE_WEEK,
    ReportDoor,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# The latest published week of this world, and one that is not. ADR 0152: "Released
# comments appear in the latest published week's report under a from-earlier-weeks
# heading, with no week attribution anywhere." Every one of this section's six
# windows has closed at the clock the door starts on, so the latest published week
# is its last course week.
LATEST_PUBLISHED_WEEK = SILENT_WEEK
AN_EARLIER_PUBLISHED_WEEK = FULL_WEEK


def cut_the_release(door: ReportDoor, comment_contract: Any) -> int:
    """Run E4-04's cutter over this world, and answer how many batches it cut.

    The batch is cut by the product's own writer and never planted
    (`docs/MISTAKES.md` entry 30): ADR 0152 makes
    `cut_due_release_batches` the one writer of `release_batch` and
    `release_batch_member`, and it commits for itself. This world is built to open
    all three legs of that gate — five distinct respondents behind held comments
    spanning two under-threshold closed weeks, with a cumulative comment volume
    above the threshold — so a cutter that cuts nothing is a red about the world
    or about the gate, and this helper says which.
    """
    door.refresh()
    cut = comment_contract.cut()(door.world.session)
    door.world.session.commit()
    return int(cut)


def comment_objects(body: Any, contract: Any, answered: Any) -> list[dict[str, Any]]:
    """Every comment object in one payload: both streams' lists and the released list.

    All of them together, because §4 is one rule about one kind of thing and a
    test that walked one member would be silent about whichever member the next
    convenience field landed on.
    """
    found: list[dict[str, Any]] = []
    for stream in (contract.instructor_stream, contract.course_stream):
        found.extend(
            contract.stream_member(body, stream, contract.comments_field, answered=answered)
        )
    found.extend(contract.member(body, contract.released_member, answered=answered))
    return found


def reads_as_an_instant(value: str) -> bool:
    """Whether a string in the payload reads as a date or a time.

    Spelling-independent, because E4-07 settles no serialization for an instant
    and `2026-11-08T23:59:59Z` and `2026-11-08T23:59:59+00:00` are one moment
    written two ways. A comment's own text cannot parse as either, so a positive
    here is a field that carries time.
    """
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def identifiers_of(*values: Any) -> set[str]:
    """Every identifier in the spellings a JSON body could carry it in.

    Hyphenated and hyphen-stripped: `str(...)` is the default rendering of a uuid
    and `uuid.hex` is the near miss that walks through a search for the first —
    the pair `tests/integration/test_the_dev_console_names_nobody.py` had to add
    after a mutation battery walked past it.
    """
    found: set[str] = set()
    for value in values:
        written = str(value)
        found.add(written)
        if isinstance(value, UUID):
            found.add(value.hex)
    return found


def test_the_payloads_comments_are_the_comment_services_own(
    report_door: ReportDoor, report_api_contract: Any, comment_contract: Any
) -> None:
    """Criterion 4's first half: the same comments, no more and no fewer.

    `visible_comments` is where SPEC §4's n-threshold is applied, and E4-07 reads
    it rather than re-deriving it. A payload holding a comment that service does
    not return is a suppression rule with a second implementation
    (`docs/MISTAKES.md` entry 13 in production code); one holding fewer is a
    report that quietly drops feedback.

    **The mutation this kills:** the assembly layer selecting comments from
    `report_comment` directly — the view is right there, the join is one line, and
    the threshold is not in it. **The canary:** the service returns a non-empty
    tuple for this week, asserted first, or the comparison is between two empty
    lists (`docs/MISTAKES.md` entry 3).
    """
    report_door.refresh()
    from_service = comment_contract.visible()(
        report_door.world.session,
        section_id=report_door.rows.taught_section_id,
        week_id=report_door.rows.week_id(FULL_WEEK),
        stream=report_api_contract.instructor_stream,
    )
    assert len(from_service) == RESPONSES_IN_WEEK[FULL_WEEK], (
        f"`{comment_contract.visible_name}` answered {len(from_service)} comments for the full "
        f"week, which holds {RESPONSES_IN_WEEK[FULL_WEEK]} responses each carrying one instructor "
        "comment. Until that is the planted number, every comparison below is between two lists "
        "neither of which is the subject."
    )

    body, answered = report_door.payload(course_week=FULL_WEEK)
    in_payload = report_api_contract.stream_member(
        body,
        report_api_contract.instructor_stream,
        report_api_contract.comments_field,
        answered=answered,
    )

    assert sorted(entry["text"] for entry in in_payload) == sorted(
        comment.text for comment in from_service
    ), (
        f"The payload carries {len(in_payload)} comments and "
        f"`{comment_contract.visible_name}` answers {len(from_service)} for the same section, week "
        "and stream, and their texts differ."
    )


def test_no_comment_object_carries_a_field_the_comment_service_does_not(
    report_door: ReportDoor, report_api_contract: Any, comment_contract: Any
) -> None:
    """Criterion 4's second half: no field, no count, no ordering information.

    `ReportComment`'s whole field list is `(text, status, stream)` and E4-04
    asserts that as an equality one layer down. Here it is a ceiling: a comment
    object in this payload may carry those and nothing else, so an `index`, a
    `position`, a `submitted_at` or a per-week `count` is red in the diff that
    adds it rather than in the epic that renders it.

    **The mutation this kills:** an ordering field added for the frontend's
    convenience. SPEC §4 randomizes comment display order precisely so that
    position says nothing, and a payload that numbers the comments hands the order
    back — over two reads a week apart, the numbering re-derives which comment is
    new (`docs/MISTAKES.md` entry 51).
    """
    body, answered = report_door.payload(course_week=FULL_WEEK)
    objects = comment_objects(body, report_api_contract, answered)
    assert objects, (
        "This payload carries no comment objects at all, so the ceiling below is a statement about "
        "nothing. The full week is at the n-threshold and its comments are visible."
    )

    widened = sorted(
        {
            name
            for entry in objects
            for name in entry
            if name not in report_api_contract.comment_fields_permitted
        }
    )
    assert not widened, (
        f"Comment objects in this payload carry {widened}, and "
        f"`{comment_contract.comment_class_name}` carries "
        f"{sorted(report_api_contract.comment_fields_permitted)}. Criterion 4: the service adds no "
        "field, no count and no ordering information beyond what E4-04 returns."
    )


def test_no_comment_in_the_payload_carries_a_timestamp_a_week_or_an_author(
    report_door: ReportDoor, report_api_contract: Any, comment_contract: Any
) -> None:
    """SPEC §4.1 item 6, at every depth of a comment rather than at its first level.

    SPEC §4: "Comment display order is randomized; timestamps are never shown with
    comments", and the cumulative release is "batched so that timing cannot
    identify an author". ADR 0153 removes the week for the sharper reason: the
    gradebook's per-week participation ledger says who completed that week's
    comment item, so a comment known to come from a four-response week intersects
    with that ledger down to one person.

    The scan is over **values**, in both currencies a leak travels in — an
    identifier and an instant — and at any depth, because the field-list ceiling
    one test up sees only the top level of each object.

    **The mutation this kills:** a nested `response` or `week` object hung off a
    comment. **The canary:** the identifiers searched for are ones this world
    certainly planted and the payload certainly could have carried, asserted
    non-empty first, so a scan that had gone blind says so
    (`docs/MISTAKES.md` entry 3).
    """
    report_door.refresh()
    forbidden = identifiers_of(
        *report_door.rows.enrolled_user_ids(),
        *report_door.rows.stored_response_ids(),
        *(report_door.rows.week_id(week) for week in TERM_WEEK_OF_COURSE_WEEK),
    )
    assert len(forbidden) >= 2, (
        f"This world offers {len(forbidden)} identifiers to search a comment for, and it seeded "
        "students, responses and weeks. A scan with nothing to find reports every payload clean."
    )

    body, answered = report_door.payload(course_week=FULL_WEEK)
    objects = comment_objects(body, report_api_contract, answered)
    assert objects, "This payload carries no comment objects, so this scan judged nothing."

    for entry in objects:
        for value in report_api_contract.strings_in(entry):
            assert value not in forbidden, (
                f"A comment in this payload carries {value!r}, which is a `user`, `response` or "
                f"`week` key this world planted. The comment object was {entry!r}."
            )
            assert not reads_as_an_instant(value), (
                f"A comment in this payload carries {value!r}, which reads as an instant. SPEC §4: "
                f"timestamps are never shown with comments. The comment object was {entry!r}."
            )


def test_a_below_threshold_week_carries_no_raw_comment_at_the_payload_boundary(
    report_door: ReportDoor, report_api_contract: Any, comment_contract: Any
) -> None:
    """The suppression E4-04 decided, still decided one layer up.

    SPEC §4: below the n-threshold "instructors see rating distributions and the
    AI summary, but **no raw comments**", and §4.1 item 3 makes it an invariant.
    E4-04 holds it in `visible_comments`; this is the assertion that the report
    which renders that week did not reach around it.

    **The mutation this kills:** a payload that reads `report_comment` for its own
    week and `visible_comments` only for the released list. **The premise:** the
    week is genuinely under the configured threshold *and* genuinely holds
    comments, both read back from the database — a below-threshold week with
    nothing in it proves nothing (E4-04's own second known trap).
    """
    threshold = comment_contract.threshold()
    responses = report_door.rows.responses_in(FIRST_HELD_WEEK)
    assert 0 < responses < threshold, (
        f"Course week {FIRST_HELD_WEEK} holds {responses} responses and the configured threshold is "
        f"{threshold}; this test is only about suppression if the week is under it and not empty."
    )

    report_door.refresh()
    held = comment_contract.visible()(
        report_door.world.session,
        section_id=report_door.rows.taught_section_id,
        week_id=report_door.rows.week_id(FIRST_HELD_WEEK),
        stream=report_api_contract.instructor_stream,
    )
    assert held == (), (
        f"`{comment_contract.visible_name}` answered {held!r} for an under-threshold week, so the "
        "layer this test is about is not the one suppressing."
    )

    body, answered = report_door.payload(course_week=FIRST_HELD_WEEK)
    shown = report_api_contract.stream_member(
        body,
        report_api_contract.instructor_stream,
        report_api_contract.comments_field,
        answered=answered,
    )
    assert shown == [], (
        f"The report for course week {FIRST_HELD_WEEK} carries {shown!r}. That week holds "
        f"{responses} responses against a threshold of {threshold}, and its comments are held."
    )


def test_the_threshold_the_payload_prints_is_the_threshold_the_gate_applied(
    report_door: ReportDoor,
    report_api_contract: Any,
    comment_contract: Any,
    monkeypatch: Any,
) -> None:
    """One settings source behind the label and the gate — the security round's LOW.

    The report prints a threshold in its `small_n` member and E4-04's read path
    applies one, and the two were reaching it by different routes: the label from
    the application's startup `Settings`, the gate from a fresh `Settings()` built
    per call. They agree on every ordinary deployment and come apart the moment
    the two are built at different times — which is a screen telling an instructor
    "comments appear once five students have answered" while the query that hid
    them was applying some other number. A promise about confidentiality that is
    printed from one source and enforced from another is two promises.

    **What this drives, and why the environment is changed mid-process.** The
    application's settings exist by the time the door has launched. Changing the
    variable afterwards is the one manipulation that separates a value read at
    startup from a value read per call, and it is exactly the manipulation
    `docs/MISTAKES.md` entry 52 describes from the other end — a process-global
    built at import is bound by whoever built it first, and everything built later
    disagrees with it. Here the disagreement is the subject rather than the
    hazard.

    **It asserts agreement, not a number.** Whichever source the implementation
    settles on, the label and the behaviour move together: this test computes what
    the printed threshold implies for a week of known size and requires the
    comments to match it. A test that pinned 5, or pinned the changed value, would
    be choosing which of the two sources wins — and that is a decision the ruling
    leaves to the implementer, who only has to make it once.

    **The mutation this kills:** the label and the gate reading two `Settings`
    objects. **The near miss it is written against:** a week whose response count
    is outside both candidate thresholds, where the two sources agree by accident
    — so the week is chosen with the count strictly between them, asserted before
    anything is read.
    """
    week = FIRST_HELD_WEEK
    responses = report_door.rows.responses_in(week)

    body, answered = report_door.payload(course_week=week)
    at_startup = report_api_contract.member(
        body, report_api_contract.small_n_member, "threshold", answered=answered
    )
    assert isinstance(at_startup, int), (
        f"`{report_api_contract.small_n_member}.threshold` came back as {at_startup!r}. The sketch "
        "spells it the configured response count below which raw comments stay hidden, and this "
        "test reasons about the week's size against it."
    )

    # A value on the other side of this week's response count from the one the
    # application started with, so the two sources cannot agree by accident.
    changed_to = responses - 1 if at_startup > responses else responses + 1
    assert min(at_startup, changed_to) <= responses < max(at_startup, changed_to), (
        f"Course week {week} holds {responses} responses, the application started with a threshold "
        f"of {at_startup}, and this test would change it to {changed_to} — which does not straddle "
        "the week's size, so both sources would suppress (or both show) and their disagreement "
        "would be invisible."
    )
    monkeypatch.setenv(comment_contract.threshold_variable, str(changed_to))

    body, answered = report_door.payload(course_week=week)
    printed = report_api_contract.member(
        body, report_api_contract.small_n_member, "threshold", answered=answered
    )
    shown = report_api_contract.stream_member(
        body,
        report_api_contract.instructor_stream,
        report_api_contract.comments_field,
        answered=answered,
    )

    assert bool(shown) == (responses >= printed), "\n".join(
        [
            f"The report prints a threshold of {printed} for a week holding {responses} responses, "
            f"and {'shows' if shown else 'hides'} that week's comments.",
            "",
            f"A threshold of {printed} means comments appear from {printed} responses, so this week "
            f"should be {'shown' if responses >= printed else 'hidden'} and it is not.",
            "",
            f"The application started with {at_startup} and `{comment_contract.threshold_variable}` "
            f"was changed to {changed_to} afterwards. The label and the gate are reading two "
            "different `Settings` objects — one built at startup, one built per call — and this "
            "week's size sits between the two values, which is the only place the difference is "
            "visible. Which of the two wins is the implementer's to settle; that they are the same "
            "value is not.",
        ]
    )


def test_the_released_list_carries_the_release_in_the_latest_published_week(
    report_door: ReportDoor, report_api_contract: Any, comment_contract: Any
) -> None:
    """ADR 0152's placement, the half where the list is populated.

    > The release is carried by one report, and E4-07 places it. Released comments
    > appear in the latest published week's report under a from-earlier-weeks
    > heading, with no week attribution anywhere.

    **The mutation this kills:** a released list assembled from `report_comment`
    for the weeks that were held, rather than from `released_comments` — which
    would show held comments that no batch has released, in a section that never
    crossed. **The canary:** the cutter is required to have cut a batch and the
    service is required to answer a non-empty tuple, both before the payload is
    read, because an empty list satisfies the paired test below for free.
    """
    assert cut_the_release(report_door, comment_contract) == 1, (
        "The cutter cut no batch over a world built to open all three legs of ADR 0152's gate: five "
        "distinct respondents behind held comments spanning two under-threshold closed weeks. "
        "Until a batch exists there is no release for this payload to place."
    )
    report_door.refresh()
    released = comment_contract.released()(
        report_door.world.session,
        section_id=report_door.rows.taught_section_id,
        term_id=report_door.rows.term_id,
        stream=report_api_contract.instructor_stream,
    )
    assert released, (
        f"`{comment_contract.released_name}` answered nothing after a batch was cut, so the "
        "assertion below would be about an empty list either way."
    )

    body, answered = report_door.payload(course_week=LATEST_PUBLISHED_WEEK)
    carried = report_api_contract.member(
        body, report_api_contract.released_member, answered=answered
    )
    assert sorted(entry["text"] for entry in carried) == sorted(
        comment.text for comment in released
    ), (
        f"The latest published week's report carries {len(carried)} released comments and "
        f"`{comment_contract.released_name}` answers {len(released)} for the same section, term and "
        "stream, and their texts differ."
    )


def test_the_released_list_is_empty_in_every_week_but_the_latest_published_one(
    report_door: ReportDoor, report_api_contract: Any, comment_contract: Any
) -> None:
    """ADR 0152's placement, the half that keeps it in one report.

    The list is "present in every report payload as a list; populated only when
    the requested course week is the latest published week, else empty" — so the
    member is on the wire everywhere and full in exactly one place. Carrying it in
    every week would show the same batch six times, and a reader paging back
    through the term would meet it once per page with a different week's data
    beside it each time, which is the week attribution ADR 0153 removed arriving
    through the navigation instead of through a field.

    **The mutation this kills:** the released list assembled unconditionally,
    which the paired test above is green against. **The premise:** a batch exists
    — asserted here too, because "empty everywhere" is what an unbuilt release
    looks like as well.
    """
    assert cut_the_release(report_door, comment_contract) == 1, (
        "The cutter cut no batch, so an empty released list in an earlier week says nothing about "
        "placement."
    )

    body, answered = report_door.payload(course_week=AN_EARLIER_PUBLISHED_WEEK)
    carried = report_api_contract.member(
        body, report_api_contract.released_member, answered=answered
    )
    assert carried == [], (
        f"The report for course week {AN_EARLIER_PUBLISHED_WEEK} carries {len(carried)} released "
        f"comments; the latest published week is {LATEST_PUBLISHED_WEEK} and ADR 0152 places the "
        "release there and nowhere else."
    )
    assert report_api_contract.released_member in body, (
        f"The payload for an earlier week carries no `{report_api_contract.released_member}` member "
        f"at all; it carries {sorted(body)}. The member is present in every report and empty in all "
        "but one, so a frontend that renders the heading has one shape to render."
    )


def test_an_absent_summary_row_is_the_schemas_explicit_absent_state(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """Criterion 6: an absent summary is absent, and never an empty string pretending.

    E4-06 writes one `weekly_summary` row per section, course week and stream, and
    nothing in this world has run it — which is the ordinary state of a report
    read before Monday's job, and the state E4-11 has to render honestly rather
    than as an empty panel.

    **The mutation this kills:** `summary = row.text if row else ""`, which puts a
    blank AI summary above a comment group and reads, to an instructor, as a model
    that had nothing to say about her week.
    """
    body, answered = report_door.payload(course_week=FULL_WEEK)
    summary = report_api_contract.stream_member(
        body,
        report_api_contract.instructor_stream,
        report_api_contract.summary_field,
        answered=answered,
    )

    if summary is None:
        return
    assert isinstance(summary, dict), (
        f"The summary member is {summary!r} for a week no summary was generated for. The explicit "
        "absent state is null, or an object whose own text is null; a bare string is neither."
    )
    text = summary.get("text")
    assert text is None, (
        f"The summary member carries text {text!r} for a week E4-06 has not run over. Criterion 6: "
        "an absent summary row renders as the schema's explicit absent state, never an empty string "
        "pretending to be a summary."
    )
