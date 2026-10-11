"""A reason for an unflagged exclusion, checked as sent — ticket E6-03, criterion 2, the route's half.

> Excluding a comment with no harmful or privacy verdict without a reason is
> refused with a governed sentence. A blank reason, or one over the bound, is
> refused by the route and by the database. The reason is checked as sent, before
> any trimming (entry 29).

SPEC §5.2: "Excluding a comment the AI did *not* flag requires a stated reason …
This is the anti-cherry-picking mechanism." The work order's decision 4 settles the
rule: required, non-blank and at most **500** characters when excluding a comment
with **no harmful or privacy moderation verdict**; optional otherwise, and held to
the same bounds when given. Refusals are 422 with a sentence from
`app.copy.instructor_report`.

**"No harmful or privacy verdict" is a fact about the comment's verdicts, not its
state**, and two tests below are written against the near miss that reads it off
the state: a harmful comment that was kept is no longer `FLAGGED_COLLAPSED` and
still needs no reason; a privacy comment is flagged by a verdict that is not
`harmful`.

**Every refusal is asserted on the record as well as on the status** — no row is
written — and beside an accepted twin one character or one verdict away
(`docs/MISTAKES.md` entry 3). The database's own half is
`test_the_decision_columns_are_held_to_their_rules_by_the_database.py`.

**Which failure a red is, before E6-03 lands:** a FAILED naming M2's columns or the
decision route, from the first statement of each test (entry 44).
"""

from typing import Any

import pytest
from fixtures.instructor_decisions import (
    EXCLUDE,
    KEEP,
    OK,
    OMITTED,
    REASON_BOUND,
    REASON_COLUMN,
    STATE_COLUMN,
    STORED_EXCLUDED,
    UNPROCESSABLE,
    DecisionDoor,
    a_reason,
    governed_sentence_of,
    latest,
    require_decision_columns,
)
from fixtures.moderation import CLEAR, HARMFUL, PRIVACY
from fixtures.report_api import FULL_WEEK
from fixtures.report_views import INSTRUCTOR_STREAM

pytestmark = pytest.mark.integration


def a_comment(door: DecisionDoor, verdict: str, text: str) -> Any:
    return door.plant_a_comment(
        course_week=FULL_WEEK, stream=INSTRUCTOR_STREAM, text=text, verdict=verdict
    )


def refused_and_unwritten(door: DecisionDoor, comment: Any, reason: Any, what: str) -> str:
    """An exclusion carrying `reason` is answered 422 with a governed sentence and writes nothing."""
    before = door.rows(comment)
    answered = door.decide(comment, EXCLUDE, reason)
    assert answered.status_code == UNPROCESSABLE, (
        f"{what}: the exclusion was answered {answered.status_code}, not {UNPROCESSABLE}. Body "
        f"begins {answered.text[:400]!r}."
    )
    key = governed_sentence_of(answered, what)
    assert door.rows(comment) == before, f"{what}: the refused exclusion wrote a row anyway."
    return key


def accepted_and_stored(door: DecisionDoor, comment: Any, reason: Any, what: str) -> dict[str, Any]:
    """An exclusion carrying `reason` is answered 200 and leaves one `EXCLUDED` row; that row."""
    before = door.rows(comment)
    answered = door.decide(comment, EXCLUDE, reason)
    assert answered.status_code == OK, (
        f"{what}: the exclusion was answered {answered.status_code}. Body begins "
        f"{answered.text[:400]!r}."
    )
    after = door.rows(comment)
    assert (
        len(after) == len(before) + 1 and latest(after)[STATE_COLUMN] == STORED_EXCLUDED
    ), f"{what}: answered 200 and the record is {after!r}."
    return latest(after)


@pytest.mark.parametrize("missing", [None, OMITTED], ids=["reason-null", "reason-absent"])
def test_excluding_an_unflagged_comment_without_a_reason_is_refused_and_a_stated_one_is_accepted(
    missing: Any, decision_door: DecisionDoor
) -> None:
    """The rule and its pair, on one `clear` comment: no reason 422, a stated reason 200.

    Both spellings of "no reason" — `null`, and the member left out — because the
    body the work order settles is `reason: str | null` and a check written against
    one spelling lets the other through. The accepted half stores the reason it was
    given, which is what E6-05's exclusion log reads.

    **The mutations this kills:** no reason rule at all (the first exclusion is
    answered 200 — a fair criticism quietly dropped with no trail); a rule that
    reads only a present key; the refusal answered with FastAPI's own validation
    message rather than a governed sentence; and a reason accepted but not stored.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    comment = a_comment(door, CLEAR, "E6-03 a fair criticism nobody flagged")

    refused_and_unwritten(door, comment, missing, "An unflagged exclusion with no reason")

    stated = "It repeats a rumour about a named teaching assistant."
    row = accepted_and_stored(door, comment, stated, "The same exclusion with a stated reason")
    assert row[REASON_COLUMN] == stated, (
        f"The exclusion stored the reason {row[REASON_COLUMN]!r}, not the one it was given. The "
        "stated reason is the record SPEC §5.2's exclusion log shows."
    )


@pytest.mark.parametrize("verdict", [HARMFUL, PRIVACY])
def test_excluding_a_flagged_comment_needs_no_reason(
    verdict: str, decision_door: DecisionDoor
) -> None:
    """The other side of the rule: a comment the AI flagged is excluded with no reason given.

    A case per flagging verdict, because the rule is "no harmful **or privacy**
    verdict" and a check reading only `harmful` makes every privacy exclusion ask for
    a reason the AI already gave.

    **The mutations this kills:** a reason required for every exclusion (§5.2's
    escape valve for genuinely harmful comments narrowed to a form), and a reason
    rule that recognises one of the two flagging verdicts.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    comment = a_comment(door, verdict, f"E6-03 a comment the AI flagged {verdict}")
    row = accepted_and_stored(door, comment, None, f"An exclusion of a {verdict} comment")
    assert row[REASON_COLUMN] is None, f"No reason was given and {row[REASON_COLUMN]!r} was stored."


def test_a_kept_harmful_comment_excluded_later_needs_no_reason(
    decision_door: DecisionDoor,
) -> None:
    """The reason rule reads the comment's verdicts, not its current state.

    A harmful comment is kept — so it is no longer `FLAGGED_COLLAPSED` — and later
    excluded with no reason. Accepted: the AI flagged it, whatever the latest row
    says.

    **The mutation this kills:** "unflagged" read as "not currently
    `FLAGGED_COLLAPSED`", which demands a reason here and is satisfied by every
    other test in this module.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    comment = a_comment(door, HARMFUL, "E6-03 a harmful comment kept, then excluded after all")
    kept = door.decide(comment, KEEP)
    assert kept.status_code == OK, "The keep this test starts from was refused."
    accepted_and_stored(door, comment, None, "Excluding a kept harmful comment with no reason")


@pytest.mark.parametrize("blank", ["", " ", "\t\n  "], ids=["empty", "one-space", "whitespace"])
@pytest.mark.parametrize("verdict", [CLEAR, HARMFUL], ids=["unflagged", "flagged"])
def test_a_blank_reason_is_refused_whether_or_not_one_is_required(
    blank: str, verdict: str, decision_door: DecisionDoor
) -> None:
    """Decision 4: a blank reason is refused — for an unflagged exclusion, and for a flagged one.

    A reason is optional on a flagged exclusion "but stored if given, same bounds",
    so a blank one is refused there too rather than stored as a reason that says
    nothing. **The pair**: the same comment excluded with a one-character reason is
    accepted.

    **The mutations this kills:** a non-empty check (`""` refused, `" "` stored as a
    stated reason — the log then shows a blank where §5.2 promised a reason);
    blankness tested only when the reason is required; and a blank reason trimmed to
    nothing and stored as `NULL`, which on an unflagged comment is the missing reason
    accepted.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    comment = a_comment(door, verdict, f"E6-03 a {verdict} comment offered a blank reason")

    refused_and_unwritten(door, comment, blank, f"A {verdict} exclusion with reason {blank!r}")
    accepted_and_stored(door, comment, "x", f"A {verdict} exclusion with a one-character reason")


def test_the_reason_is_bounded_at_500_characters_as_sent(decision_door: DecisionDoor) -> None:
    """Decision 4's bound, both sides of it, and the near miss entry 29 is about.

    On one unflagged comment, in order:

      - 501 characters → refused, nothing written;
      - 500 characters with one space either side — 502 as sent, 500 once trimmed —
        → refused, nothing written. **This is the case the rule "checked as sent,
        before any trimming" exists for** (`docs/MISTAKES.md` entry 29): a value
        repaired before the check that should have refused it;
      - exactly 500 → accepted, and stored as sent.

    **The mutations this kills:** no bound (501 is stored, and the database's own
    `CHECK` becomes the first refusal — a 500 rather than a governed 422); a bound
    of 501 or `>` written for `>=` (the first case); the reason stripped before it is
    measured (the second case); and a bound of 499 (the third).
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    comment = a_comment(door, CLEAR, "E6-03 a comment whose exclusion reason is long")

    refused_and_unwritten(
        door, comment, a_reason(REASON_BOUND + 1), f"A reason of {REASON_BOUND + 1} characters"
    )
    padded = a_reason(REASON_BOUND, pad=" ")
    assert len(padded) == REASON_BOUND + 2 and len(padded.strip()) == REASON_BOUND
    refused_and_unwritten(
        door,
        comment,
        padded,
        f"A reason of {REASON_BOUND} characters sent with a space either side ({len(padded)} sent)",
    )

    exact = a_reason(REASON_BOUND)
    assert len(exact) == REASON_BOUND
    row = accepted_and_stored(
        door, comment, exact, f"A reason of exactly {REASON_BOUND} characters"
    )
    assert row[REASON_COLUMN] == exact, "The 500-character reason was not stored as it was sent."
