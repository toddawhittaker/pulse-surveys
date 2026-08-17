"""The mock platform's grade services, driven the way passback drives them — E0-15.

E0-15 builds the *platform* side of Assignment and Grade Services 2.0: line-item
creation and listing, and score posting that records what it received. SPEC §3.4
is what will use it — one line item per section called "Pulse Participation",
scored as valid weeks completed over weeks elapsed — so the line item created
below carries §3.4's label and maximum rather than an invented one.

**How a test finds the service.** Out of the AGS endpoint claim in the launch,
which carries the line-items URL and the scopes a token may be requested for.
That is how a real tool finds it, so nothing here knows a path. The score URL is
the one construction this file makes rather than reads, and it is the
specification's: AGS 2.0 defines the Score service as the line item's own URL
with `/scores` appended, which is what lets E0-15's criterion 3 speak of an
identifier "that score posting accepts" without naming a second URL.

**What is deliberately not here.** Tool-side line-item management, the
participation formula and retry handling are E3's, and E0-15's out-of-scope list
says so. Nothing below asserts what Pulse computes or when it posts. There is no
token-flow test either, for the reason `test_mock_lms_nrps_roster.py` gives.

**One thing worth knowing before reading criterion 4.** A conformant AGS
**Result** carries `userId`, `resultScore` and `resultMaximum`, and carries
neither a timestamp nor an activity progress. So "a posted score is retrievable
by a test, including its timestamp and activity progress fields" cannot be met
by the Result service alone — it is what makes the inspection surface in E0-15's
scope ("an endpoint or fixture hook that lets a test inspect posted scores") a
deliverable rather than a convenience. `recorded_scores` in `tests/conftest.py`
tries the three places that hook could plausibly live and names all three when
none answers, because E0-15 names none of them.
"""

from typing import Any

import pytest

pytestmark = pytest.mark.lti

# `mock_platform`, `signed_launch` and `instant_of` come from
# `tests/conftest.py` and are reached through fixtures rather than imported, for
# the reason `test_mock_lms_launch.py` gives: a module that imports its sibling
# `conftest` by name depends on where pytest put `tests/` on `sys.path`, and an
# import error is a broken suite rather than a red.

# The scopes AGS 2.0 names for the two things SPEC §3.4 does. Specification
# constants: a tool asks its token endpoint for exactly these strings, so a
# platform advertising a scope of its own devising grants a token for a scope no
# tool will request.
AGS_LINE_ITEM_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem"
AGS_SCORE_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/score"

# The score this suite posts. Every value is chosen to be one no implementation
# would arrive at by accident, which is the whole point of the round trip:
#
#   - the timestamp is a specific past second, so a recorder that stamped its own
#     clock cannot coincide with it;
#   - `activityProgress` and `gradingProgress` are *not* the pair an
#     implementation hardcodes. AGS's five activity values are Initialized,
#     Started, InProgress, Submitted and Completed, and a stub that writes
#     "Completed"/"FullyGraded" over whatever it was sent passes a round trip
#     posted with those two and fails this one;
#   - the score is not a round number, so a stub echoing the maximum, the
#     percentage, or zero is visible.
#
# **This suite's choice**, all four, and each is one line to change.
POSTED_TIMESTAMP = "2026-03-02T14:05:09+00:00"
POSTED_SCORE = 61.5
POSTED_MAXIMUM = 100
POSTED_ACTIVITY_PROGRESS = "Submitted"
POSTED_GRADING_PROGRESS = "PendingManual"

# The second score, for a second student, in the test that asks whether the
# platform keeps them apart. A different value as well as a different user, so a
# recorder holding one score per line item is caught by the value even where two
# users' records both come back.
SECOND_POSTED_SCORE = 12.5
SECOND_POSTED_TIMESTAMP = "2026-03-09T09:41:17+00:00"


def score_payload(user_id: str, **overrides: Any) -> dict[str, Any]:
    """One AGS score, spelled as AGS 2.0 spells it."""
    payload: dict[str, Any] = {
        "userId": user_id,
        "timestamp": POSTED_TIMESTAMP,
        "scoreGiven": POSTED_SCORE,
        "scoreMaximum": POSTED_MAXIMUM,
        "activityProgress": POSTED_ACTIVITY_PROGRESS,
        "gradingProgress": POSTED_GRADING_PROGRESS,
    }
    payload.update(overrides)
    return payload


def seeded_subjects(platform: Any) -> list[str]:
    """Every distinct user the platform will sign a launch for, in a stable order."""
    subjects = {
        str(launch.claims["sub"])
        for offer in platform.require_offers()
        for launch in [platform.mint(offer)]
        if isinstance(launch.claims.get("sub"), str)
    }
    assert subjects, (
        "No launch the platform offers carries a `sub`, so there is no user to post a score for. "
        "E0-14 seeds the users; SPEC §4 keys every response to this value."
    )
    return sorted(subjects)


def recorded_for(records: list[dict[str, Any]], user_id: str) -> dict[str, Any]:
    """The one recorded score naming `user_id`, or a failure listing what came back."""
    matching = [
        record
        for record in records
        if str(record.get("userId", record.get("user_id", ""))) == user_id
    ]
    assert matching, (
        f"Nothing the platform recorded names user {user_id!r}. It recorded {records!r}. E0-15 "
        "criterion 4: a posted score is retrievable by a test — which needs the record to say "
        "whose it is, since E3 posts one score per student per section."
    )
    return matching[0]


def value_of(record: dict[str, Any]) -> Any:
    """The score inside a recorded score, under either spelling AGS uses.

    `scoreGiven` on a Score and `resultScore` on a Result are the same number
    seen from the two sides of AGS, and which one an inspection surface answers
    with is not something E0-15 decides.

    A record carrying neither fails here rather than being read as `None` and
    compared: a `TypeError` inside an assertion is a broken test rather than a
    red, and "the platform recorded no score value" deserves to be said.
    """
    for member in ("scoreGiven", "resultScore", "score"):
        value = record.get(member)
        if isinstance(value, int | float | str):
            return value
    pytest.fail(
        f"The recorded score {record!r} carries no score value under `scoreGiven`, `resultScore` "
        "or `score`. E0-15's scope: 'score posting that records what it received so a test can "
        "assert on it.'"
    )


# ---------------------------------------------------------------------------
# Finding the service at all. The precondition for every criterion below.
# ---------------------------------------------------------------------------


def test_a_launch_advertises_the_assignment_and_grade_service_with_its_scopes(
    signed_launch: Any,
    mock_platform: Any,
) -> None:
    """The claim a tool discovers line items and scores through.

    Catches an AGS implementation served at a path someone chose with nothing in
    the token pointing at it: E3's passback would then be written against a URL
    this repository invented, and the first real platform — which issues a
    line-items URL per context — would have no route in.

    The scopes are asserted separately and are not decoration. A tool requests
    an access token for the scopes the platform granted; a claim carrying a URL
    and an empty `scope` array describes a service the tool may call for
    nothing, and it is a shape that looks complete in a decoded token.
    """
    url = mock_platform.line_items_url(signed_launch)
    assert url.startswith(("http://", "https://")), (
        f"The AGS endpoint claim advertises `{url}`, which is not an absolute URL. A tool "
        "resolves this value with no knowledge of where the token came from."
    )
    scopes = mock_platform.ags_scopes(signed_launch)
    missing = [scope for scope in (AGS_LINE_ITEM_SCOPE, AGS_SCORE_SCOPE) if scope not in scopes]
    assert not missing, (
        f"The AGS endpoint claim advertises scopes {scopes!r} and does not carry {missing}. SPEC "
        "§3.4 has the tool create one line item per section and post a score to it, so those are "
        "the two scopes E3 will ask a token for; a service advertised without them is one a "
        "conformant tool may not call."
    )


# ---------------------------------------------------------------------------
# Criterion 3 — creation returns an identifier that score posting accepts.
# ---------------------------------------------------------------------------


def test_creating_a_line_item_returns_an_identifier_of_its_own(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """Criterion 3, the first half.

    Catches the stub that answers 201 with an empty body, or with the request
    echoed back unchanged. Both look like success at the transport layer and
    leave E3 with nothing to address a score to — the failure then surfaces at
    the score post, one layer away from its cause.

    `scoreMaximum` is asserted because §3.4 posts a percentage *of the line
    item's maximum*: a platform that stores its own maximum rather than the one
    it was given silently rescales every participation grade in the institution.
    """
    created = mock_platform.create_line_item(signed_launch)
    assert isinstance(created.get("id"), str) and created["id"], (
        f"Creating a line item answered {created!r}, which carries no `id`. AGS 2.0 makes the "
        "`id` the line item's own URL, and E0-15 criterion 3 is that score posting accepts it."
    )
    assert created.get("scoreMaximum") == 100, (
        f"The created line item reports `scoreMaximum` {created.get('scoreMaximum')!r} for a "
        "creation that asked for 100. SPEC §3.4 posts the participation score as a percentage of "
        "the line item's maximum, so a maximum the platform chose for itself rescales it."
    )


def test_two_created_line_items_carry_different_identifiers(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """The near miss on the test above: an identifier that is a constant.

    A stub returning a fixed `id` passes creation, passes score posting, and
    passes a single round trip. What it breaks is one line item per *section*
    (SPEC §3.4): every section's participation column becomes the same column,
    and the scores E3 posts for one section overwrite another's. Nothing else in
    this module can see it, because every other test creates one line item.
    """
    first = mock_platform.create_line_item(signed_launch)
    second = mock_platform.create_line_item(signed_launch)
    assert first.get("id") != second.get("id"), (
        f"Two line items created one after the other carry the same `id` ({first.get('id')!r}). "
        "SPEC §3.4 has one line item per section, so a constant identifier makes every section's "
        "participation column the same column."
    )


def test_a_created_line_item_appears_in_the_line_item_listing(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """E0-15's scope: "line-item creation **and listing**".

    Catches a creation endpoint that mints a well-formed identifier and stores
    nothing, and a listing that answers seeded fixtures regardless of what was
    created. The listing is read *before* the creation as well as after, which
    is what makes the second read evidence: a listing that answered the same
    array every time would otherwise satisfy "the id is in the list" whenever
    the id happened to be seeded, and would satisfy nothing at all if it were
    empty.
    """
    before = {str(item.get("id")) for item in mock_platform.line_items(signed_launch)}
    created = mock_platform.create_line_item(signed_launch)
    identifier = str(created.get("id"))
    assert identifier not in before, (
        f"The line item listing already carried `{identifier}` before it was created, so this "
        "test cannot tell a stored line item from a seeded one. Either creation reused a seeded "
        "identifier or the listing is a fixture."
    )
    after = {str(item.get("id")) for item in mock_platform.line_items(signed_launch)}
    assert identifier in after, (
        f"The line item created at `{identifier}` is absent from the listing, which carries "
        f"{sorted(after)}. E0-15's scope asks for creation and listing; a creation that returns "
        "an identifier and stores nothing is a passback that reports success and posts nowhere."
    )


def test_a_score_posted_against_the_created_identifier_is_accepted(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """Criterion 3, the second half: the identifier creation returned is the one scores use.

    Catches the mismatch the criterion is written against — creation answering a
    numeric identifier or a bare name while the score endpoint is keyed by URL,
    or the reverse. Both halves work in isolation and E3 cannot join them.
    """
    created = mock_platform.create_line_item(signed_launch)
    user_id = seeded_subjects(mock_platform)[0]
    response = mock_platform.post_score(created, score_payload(user_id))
    assert 200 <= response.status_code < 300, (
        f"Posting a score to the line item created at `{created.get('id')}` answered "
        f"{response.status_code}. E0-15 criterion 3: 'AGS line-item creation returns an "
        f"identifier that score posting accepts.' Body begins {response.text[:200]!r}."
    )


# ---------------------------------------------------------------------------
# Criterion 4 and the definition of done — the post-and-read round trip.
# ---------------------------------------------------------------------------


def test_a_posted_score_is_read_back_with_the_timestamp_and_progress_it_carried(
    mock_platform: Any,
    signed_launch: Any,
    instant_of: Any,
) -> None:
    """Criterion 4, field by field, and the definition of done's round trip.

    Catches a recorder that stores the number and drops everything around it —
    the near miss E0-15's scope is written against, "score posting that records
    **what it received**". Three shapes of it, each of which passes a round trip
    that only compares the score:

      - a timestamp stamped from the platform's own clock rather than taken from
        the request. Asserted as an instant rather than as a string, so a
        platform that normalises `+00:00` to `Z` is not failed for it, and
        against a specific past second, so a clock cannot coincide with it;
      - an `activityProgress` hardcoded to "Completed" and a `gradingProgress`
        hardcoded to "FullyGraded", which is the pair an implementation writes
        when it treats these as ceremony. The score posted here carries neither;
      - a score echoed from the maximum or from the request's own body without
        being stored, which the listing-shaped assertion above cannot see.

    E3 recomputes and re-posts after each week closes (§3.4), so the timestamp is
    the field that says *which week's* recomputation a score is, and a platform
    that overwrites it makes every repost indistinguishable from the last.
    """
    created = mock_platform.create_line_item(signed_launch)
    user_id = seeded_subjects(mock_platform)[0]
    posted = score_payload(user_id)
    response = mock_platform.post_score(created, posted)
    assert 200 <= response.status_code < 300, (
        f"Posting the score answered {response.status_code}, so there is nothing to read back. "
        f"Body begins {response.text[:200]!r}."
    )

    record = recorded_for(mock_platform.recorded_scores(created), user_id)

    assert float(value_of(record)) == pytest.approx(POSTED_SCORE), (
        f"The platform recorded {value_of(record)!r} for a score posted as {POSTED_SCORE}. "
        f"The whole record is {record!r}."
    )
    assert instant_of(record.get("timestamp")) == instant_of(POSTED_TIMESTAMP), (
        f"The platform recorded timestamp {record.get('timestamp')!r} for a score posted with "
        f"{POSTED_TIMESTAMP!r}. The whole record is {record!r}. E0-15 criterion 4 asks for the "
        "timestamp the score carried; a recorder that stamps its own clock, or an inspection "
        "surface that answers AGS Results — which carry no timestamp at all — cannot give E3 the "
        "field that distinguishes one week's repost from the next."
    )
    assert record.get("activityProgress") == POSTED_ACTIVITY_PROGRESS, (
        f"The platform recorded `activityProgress` {record.get('activityProgress')!r} for a score "
        f"posted with {POSTED_ACTIVITY_PROGRESS!r}. The whole record is {record!r}. A value "
        "hardcoded to 'Completed' is right for every score E3 will ever post and wrong about "
        "every one of them."
    )
    assert record.get("gradingProgress") == POSTED_GRADING_PROGRESS, (
        f"The platform recorded `gradingProgress` {record.get('gradingProgress')!r} for a score "
        f"posted with {POSTED_GRADING_PROGRESS!r}. The whole record is {record!r}."
    )


def test_two_students_scores_are_recorded_separately_on_one_line_item(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """The near miss on the round trip: one score slot per line item.

    A recorder that keeps the last score it was sent passes every assertion
    above — the fields all round-trip, because there is only ever one score in
    flight. What it breaks is the thing a line item is for: SPEC §3.4 posts one
    score per student per section, so a single slot means the last student
    posted is the only student graded, and the tool sees success for all of them.

    The two scores carry different values as well as different users, so a
    platform that returns two records built from one stored score is caught by
    the value rather than by the count.
    """
    subjects = seeded_subjects(mock_platform)
    assert len(subjects) > 1, (
        f"The platform offers launches for only {subjects}, so there is one student to post for "
        "and this test cannot tell one slot from two. E0-14 criterion 7 seeds at least two users."
    )
    first_user, second_user = subjects[0], subjects[1]
    created = mock_platform.create_line_item(signed_launch)

    mock_platform.post_score(created, score_payload(first_user))
    mock_platform.post_score(
        created,
        score_payload(
            second_user, scoreGiven=SECOND_POSTED_SCORE, timestamp=SECOND_POSTED_TIMESTAMP
        ),
    )

    records = mock_platform.recorded_scores(created)
    assert float(value_of(recorded_for(records, first_user))) == pytest.approx(POSTED_SCORE), (
        f"After posting {POSTED_SCORE} for {first_user!r} and {SECOND_POSTED_SCORE} for "
        f"{second_user!r}, the platform reports {records!r}. The first student's score has moved, "
        "so the line item holds one score rather than one score per student."
    )
    assert float(value_of(recorded_for(records, second_user))) == pytest.approx(
        SECOND_POSTED_SCORE
    ), (
        f"After posting {POSTED_SCORE} for {first_user!r} and {SECOND_POSTED_SCORE} for "
        f"{second_user!r}, the platform reports {records!r} for the second student."
    )
