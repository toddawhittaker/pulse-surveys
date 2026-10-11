"""The instructor week report carries no held count of any kind — E6-03, after the owner's ruling 6.

Ruling 2 had E6-03 build a "participation note" on the week report ("N responses
held for review"). Ruling 6 drops it, for a privacy reason: a per-week held count
shown beside a released comment's harmful flag lets a reader pin the released
comment's text to its week (ADR 0153's channel), and a count of held comments in
a small week also lowers the effective small-N threshold. SPEC §5.2 goes back to
"no count" below the threshold, with no participation trace at all.

So the forbidden state is asserted at three layers, because the note could come
back at any of them:

  - **The schema.** The week report's own model (the one declaring `streams`)
    declares no `participation_note`.
  - **The service.** `app.services.report_comments` exposes no
    `participation_count`.
  - **The served payload, by difference rather than by name.** A held harmful
    comment that is then kept changes nothing at all in what the instructor reads
    for that week. A count that moved with the keep — under any member name — is
    the note back. This is the half that does not depend on spelling
    (`docs/MISTAKES.md` entry 2).

Two behaviours of criterion 7 survive the ruling and are kept here, because
nothing else asserts them: below the threshold no string in the payload names a
moderation category, and above it a flagged comment's card shows its chip. The
second is also the canary for the first's scan (`docs/MISTAKES.md` entry 3).

Every week is read twice in a row and both reads are asserted (`docs/MISTAKES.md`
entry 51). Marked `invariant`: a confidentiality denial under SPEC §4.1.

**Which failure a red is, before the code change:** an assertion — the model
declares `participation_note`, the service exposes `participation_count`, the
served body carries `participation_note`, and the kept comment changes the body
from `{"held": 1}` to `null`. Never an import error (`docs/MISTAKES.md` entry 44).
"""

from importlib import import_module
from typing import Any

import pytest
from fixtures.instructor_decisions import (
    AS_LEAD_FACULTY,
    FLAGGED,
    STATE_COLUMN,
    STORED_KEPT,
    DecisionDoor,
    latest,
    require_decision_columns,
)
from fixtures.moderation import HARMFUL, PRIVACY, SELF_HARM, THREAT
from fixtures.report_api import FIRST_HELD_WEEK, FLAG_FIELD, FULL_WEEK, strings_in
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

DROPPED_MEMBER = "participation_note"
DROPPED_SERVICE_NAME = "participation_count"
SERVICE_MODULE = "app.services.report_comments"
# The categories a payload may never name below the threshold — ADR 0030's stored
# tokens (`tests/fixtures/moderation.py`), compared case-blind.
CATEGORY_WORDS = (HARMFUL, PRIVACY, THREAT, SELF_HARM, "self-harm")


def twice(door: DecisionDoor, course_week: int) -> list[Any]:
    """Two consecutive reads of one week's report (entry 51)."""
    return [door.payload(course_week), door.payload(course_week)]


def keys_in(node: Any) -> list[str]:
    """Every mapping key at any depth of a JSON body."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.append(str(key))
            found.extend(keys_in(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(keys_in(value))
    return found


def differences(before: Any, after: Any, path: str = "$") -> list[str]:
    """The paths at which two JSON bodies differ, for a failure message that names them."""
    if isinstance(before, dict) and isinstance(after, dict):
        found: list[str] = []
        for key in sorted(set(before) | set(after), key=str):
            if key not in before or key not in after:
                found.append(f"{path}.{key}: {before.get(key)!r} -> {after.get(key)!r}")
            else:
                found.extend(differences(before[key], after[key], f"{path}.{key}"))
        return found
    if before != after:
        return [f"{path}: {before!r} -> {after!r}"]
    return []


def categories_in(body: Any) -> list[str]:
    """Every string in a payload that names a moderation category, case-blind."""
    return [
        value
        for value in strings_in(body)
        if any(word == value.strip().lower() for word in CATEGORY_WORDS)
    ]


def a_held_harmful_comment(door: DecisionDoor, threshold: int, text: str) -> Any:
    """One harmful comment, the only one in course week 3's course stream, which is held."""
    answer_id = door.plant_a_comment(
        course_week=FIRST_HELD_WEEK, stream=COURSE_STREAM, text=text, verdict=HARMFUL
    )
    commenters = door.door.rows.commenters_in(FIRST_HELD_WEEK, COURSE_STREAM)
    assert 0 < commenters < threshold, (
        f"Course week {FIRST_HELD_WEEK}'s course stream holds {commenters} commenters and the "
        f"threshold is {threshold}; this test is about a held stream, so it has to be under it and "
        "not empty."
    )
    return answer_id


def test_the_week_report_model_declares_no_participation_note(report_api_contract: Any) -> None:
    """Ruling 6 at the schema: the week report's own model has no note member.

    **The mutation this kills:** `participation_note` left on (or put back on) the
    report model. **The near miss:** the member kept but made always-null — still a
    declared slot the wire types and the frontend render, and this still reds.
    """
    schema = report_api_contract.schema()
    reports = [
        value
        for name, value in vars(schema).items()
        if not name.startswith("_")
        and isinstance(value, type)
        and report_api_contract.streams_member in (getattr(value, "model_fields", None) or {})
    ]
    assert len(reports) == 1, (
        f"`{report_api_contract.schema_module_name}` declares {len(reports)} models carrying "
        f"`{report_api_contract.streams_member}`; this test reads the week report's own model."
    )
    declared = set(reports[0].model_fields)
    assert DROPPED_MEMBER not in declared, (
        f"`{reports[0].__name__}` still declares `{DROPPED_MEMBER}` ({sorted(declared)}). Ruling 6 "
        "dropped the participation note: SPEC §5.2 shows no count below the threshold."
    )


def test_the_comment_service_exposes_no_participation_count() -> None:
    """Ruling 6 at the service: nothing in `report_comments` computes the held count.

    **The mutation this kills:** the payload member removed but the counting
    function left in place, ready for the next caller. **The near miss:** the
    function renamed — not caught here, and caught by the served-payload
    difference test below, which does not depend on any name.
    """
    module = import_module(SERVICE_MODULE)
    assert not hasattr(module, DROPPED_SERVICE_NAME), (
        f"`{SERVICE_MODULE}` still exposes `{DROPPED_SERVICE_NAME}`. Ruling 6 dropped the "
        "participation note, and with it the per-week held count."
    )


def test_a_week_with_a_held_harmful_comment_serves_no_participation_member(
    decision_door: DecisionDoor, comment_contract: Any
) -> None:
    """Ruling 6 over HTTP, in the world where the old note was non-null.

    One harmful comment held in course week 3's course stream — the exact world in
    which the dropped note read `{"held": 1}`. Read twice: no `participation_note`
    member, and no key at any depth whose name mentions participation.

    **The mutation this kills:** the note served again under its old name, or
    nested one level down. **The near miss:** a renamed count (`held`,
    `held_count`), which the difference test below catches.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    a_held_harmful_comment(door, comment_contract.threshold(), "E6-03 r6 a held harmful comment")

    for read, body in enumerate(twice(door, FIRST_HELD_WEEK), start=1):
        keys = keys_in(body)
        assert keys, "The canary: the key walk found no keys in the payload at all."
        named = sorted({key for key in keys if "participation" in key.lower()})
        assert not named, (
            f"Read {read} of course week {FIRST_HELD_WEEK} carries {named}. Ruling 6 dropped the "
            "participation note; the week report carries no held count of any kind."
        )


def test_keeping_a_held_harmful_comment_changes_nothing_the_instructor_reads(
    decision_door: DecisionDoor, comment_contract: Any
) -> None:
    """Ruling 6 by difference: no count moves when a held comment's decision changes.

    One harmful comment held in course week 3's course stream. The week is read
    twice; the comment is then kept (by the Lead Faculty, the below-threshold
    reviewer ruling 1 names); the week is read twice again. All four bodies are
    equal. Below the threshold the comment is never shown, so the only thing a
    keep could change in this week is a count of held comments — whatever it is
    called.

    **The mutation this kills:** any held count served on the week report — the
    old `participation_note` going from `{"held": 1}` to `null`, or the same count
    under a new name. **The near miss:** a count that ignores decisions (it would
    not move with the keep); the name checks above catch it under the old name,
    and this test does not claim to.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    comment = a_held_harmful_comment(
        door, comment_contract.threshold(), "E6-03 r6 a held harmful comment, then kept"
    )

    before = twice(door, FIRST_HELD_WEEK)
    lead = door.a_person()
    door.plant_a_decision(comment, STORED_KEPT, decided_by=lead, decided_as=AS_LEAD_FACULTY)
    assert (
        latest(door.rows(comment))[STATE_COLUMN] == STORED_KEPT
    ), "The keep was not recorded, so an unchanged payload below would be about nothing."
    after = twice(door, FIRST_HELD_WEEK)

    reads = [*before, *after]
    for index, body in enumerate(reads[1:], start=2):
        changed = differences(reads[0], body)
        assert not changed, (
            f"Read {index} of course week {FIRST_HELD_WEEK} differs from read 1 "
            f"({'after' if index > 2 else 'before'} the keep) at: {changed}. Below the threshold "
            "a kept comment is not shown, so a change here is a held count — which ruling 6 "
            "dropped."
        )


def test_a_held_harmful_comment_leaves_no_category_anywhere_in_the_week(
    decision_door: DecisionDoor, comment_contract: Any
) -> None:
    """SPEC §5.2, kept from criterion 7: below the threshold, no chip and no flag-type hint.

    One harmful comment held in course week 3's course stream. Read twice: the
    stream's comment list is empty and no string anywhere in the payload names a
    moderation category. The canary is the last test in this module, where the
    same scan finds the class on a shown chip.

    **The mutations this kill:** a `flag` left on a hidden card, or a summary
    held-note type, naming the class below the threshold.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    a_held_harmful_comment(door, comment_contract.threshold(), "E6-03 r6 harmful, held, unnamed")

    for read, body in enumerate(twice(door, FIRST_HELD_WEEK), start=1):
        assert strings_in(body), "The canary: the scan found no strings in the payload at all."
        named = categories_in(body)
        assert not named, (
            f"Read {read} of a week whose harmful comment is held names a category: {named}. "
            "Below the threshold there is no chip and no flag-type hint (SPEC §5.2)."
        )
        shown = body["streams"]["course"]["comments"]
        assert shown == [], f"Read {read}: the held course stream shows {shown!r}."


@pytest.mark.parametrize("verdict", [HARMFUL, PRIVACY])
def test_above_the_threshold_the_flagged_comment_shows_its_chip(
    verdict: str, decision_door: DecisionDoor, comment_contract: Any
) -> None:
    """SPEC §5.2, kept from criterion 7: a shown flagged comment carries its class.

    A flagged comment in course week 1's instructor stream, which is at the
    threshold with it. Read twice: the card is `flagged_collapsed` with `flag`
    equal to its verdict's class. This is also the canary for the category scan
    above: here the class is on the page, and the scan finds it.

    **The mutations this kill:** a chip missing its class (`flag` null on a flagged
    card), and the class from the wrong verdict.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    threshold = comment_contract.threshold()
    comment = door.plant_a_comment(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text=f"E6-03 r6 a {verdict} comment in a shown stream",
        verdict=verdict,
    )
    commenters = door.door.rows.commenters_in(FULL_WEEK, INSTRUCTOR_STREAM)
    assert commenters >= threshold, (
        f"Course week 1's instructor stream holds {commenters} commenters against a threshold of "
        f"{threshold}; this test is about a shown stream."
    )

    for read, body in enumerate(twice(door, FULL_WEEK), start=1):
        card = door.card(body, comment)
        assert card is not None, f"Read {read}: the flagged comment is not on the shown stream."
        assert (card.get("status"), card.get(FLAG_FIELD)) == (FLAGGED, verdict), (
            f"Read {read}: the flagged comment's card is {card!r}. Above the threshold it is "
            f"`{FLAGGED}` with its chip — `flag` {verdict!r} (SPEC §5.2, work order decision 6)."
        )
        assert verdict in categories_in(
            body
        ), "The canary for the category scan: the shown chip's class is not found by it."
