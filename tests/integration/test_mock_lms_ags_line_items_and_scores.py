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

**The readback is two surfaces, and that is the point of it.** A conformant AGS
`Result` carries `userId`, `resultScore` and `resultMaximum` and nothing else —
no timestamp, no progress — so criterion 4's fields cannot be read back through
the protocol at all. E0-15 therefore serves the Results endpoint for E3 to build
against *and* a mock-only inspection route at `GET /mock/posted-scores`, outside
the AGS namespace, carrying the posted body verbatim in arrival order (ADR
0047). Both halves are asserted below, including that Results does **not** carry
the three fields: a mock that widened `Result` to make criterion 4 easy would
teach E3 to read a field no platform sends, and would pass every test that only
looked at the mock route.

**Verbatim is asserted as equality, not field by field.** The three ways a
recorder half-does this — normalising the timestamp, filling a default
`gradingProgress`, dropping a field it has no model for — are one assertion
apart, and naming them individually would leave the fourth one nobody thought
of. This is also why the timestamp is compared as a *string* here while
`tests/integration/test_mock_lms_seed_data.py` compares enrollment dates as
instants: there, two spellings of one moment are the same fact; here, the
spelling is the fact.
"""

from typing import Any

import pytest

pytestmark = pytest.mark.lti

# `mock_platform` and `signed_launch` come from
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
#   - the timestamp is a specific past second *and* is written with a `+00:00`
#     offset rather than `Z`. Both matter now that the ticket says verbatim: the
#     second defeats a recorder stamping its own clock, and the spelling defeats
#     one that round-trips the value through a datetime and re-renders it, which
#     is the single most likely way a FastAPI implementation loses it;
#   - `activityProgress` and `gradingProgress` are *not* the pair an
#     implementation hardcodes. AGS's five activity values are Initialized,
#     Started, InProgress, Submitted and Completed, and a stub that writes
#     "Completed"/"FullyGraded" over whatever it was sent passes a round trip
#     posted with those two and fails this one;
#   - the score is not a round number, so a stub echoing the maximum, the
#     percentage, or zero is visible.
#
# **This suite's choice**, all of them, and each is one line to change.
POSTED_TIMESTAMP = "2026-03-02T14:05:09+00:00"
POSTED_SCORE = 61.5
POSTED_MAXIMUM = 100
POSTED_ACTIVITY_PROGRESS = "Submitted"
POSTED_GRADING_PROGRESS = "PendingManual"

# An optional AGS member, carried in the verbatim test and deliberately absent
# from the test beside it. AGS 2.0 makes `comment` optional, so it is the field
# an implementation modelling a score with a fixed set of attributes either drops
# on the way in or invents as `null` on the way out.
POSTED_COMMENT = "e0-15 round trip, not shown to anybody"

# The three fields a conformant AGS `Result` does not have. Criterion 5 is that
# the Results endpoint carries none of them; they are listed from the AGS 2.0
# `Result` definition, which has `id`, `userId`, `resultScore`, `resultMaximum`,
# `scoreOf` and `comment` and nothing else.
FIELDS_A_RESULT_DOES_NOT_CARRY = ("timestamp", "activityProgress", "gradingProgress")

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


def scores_in(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The `score` object out of each `/mock/posted-scores` entry, in arrival order.

    An entry with no `score` fails here rather than being read as `{}` and
    compared, because "the platform recorded an entry carrying nothing" is worth
    saying and an empty dict quietly answers "the score did not round-trip" as
    though it were a field mismatch.
    """
    for entry in entries:
        if not isinstance(entry.get("score"), dict):
            pytest.fail(
                f"A `/mock/posted-scores` entry carries no `score` object: {entry!r}. E0-15 "
                'spells each entry `{"lineItem": …, "score": {…the posted body, verbatim…}}`.'
            )
    return [entry["score"] for entry in entries]


def scores_for(entries: list[dict[str, Any]], user_id: str) -> list[dict[str, Any]]:
    """Every recorded score naming `user_id`, in arrival order."""
    return [score for score in scores_in(entries) if str(score.get("userId", "")) == user_id]


def one_score_for(entries: list[dict[str, Any]], user_id: str) -> dict[str, Any]:
    """The single recorded score naming `user_id`, or a failure saying what came back."""
    matching = scores_for(entries, user_id)
    assert len(matching) == 1, (
        f"The platform recorded {len(matching)} scores for user {user_id!r}, not one. It "
        f"recorded {list(entries)!r}. E0-15 criterion 4: a posted score is "
        "retrievable by a test — which needs the record to say whose it is, since E3 posts one "
        "score per student per section."
    )
    return matching[0]


def disagreements(recorded: dict[str, Any], posted: dict[str, Any]) -> list[str]:
    """How `recorded` differs from `posted`, in the words the failure needs.

    Verbatim is asserted as equality; this exists only so the message names the
    three ways it fails — a field changed, a field lost, a field invented —
    rather than printing two dictionaries and leaving the reader to diff them.
    """
    return (
        [
            f"`{name}` came back {recorded[name]!r} for a posted {posted[name]!r}"
            for name in sorted(set(posted) & set(recorded))
            if recorded[name] != posted[name]
        ]
        + [
            f"`{name}` was posted as {posted[name]!r} and is absent"
            for name in sorted(set(posted) - set(recorded))
        ]
        + [
            f"`{name}` came back as {recorded[name]!r} and was never posted"
            for name in sorted(set(recorded) - set(posted))
        ]
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


def test_a_posted_score_is_read_back_verbatim_at_the_mock_route(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """Criterion 4, and the definition of done's round trip.

    "Verbatim means verbatim" is the ticket's own phrase, so the assertion is
    equality against the body that went out rather than a walk of the fields
    that happened to be thought of. Four recorders fail it and all four pass a
    field-by-field check written from the same body:

      - one that re-renders the timestamp. `2026-03-02T14:05:09+00:00` through a
        `datetime` and back is `...+00:00` on some paths and `...Z` on others,
        and the value posted here is spelled with the offset so the round trip
        through a model is visible rather than lucky;
      - one that stamps its own clock over the timestamp. The value is a
        specific past second, which no clock coincides with;
      - one that hardcodes `activityProgress` to "Completed" and
        `gradingProgress` to "FullyGraded" — the pair an implementation writes
        when it reads these as ceremony. The body posted here carries neither;
      - one that drops `comment`, which AGS makes optional and which is
        therefore the member a fixed attribute set loses without noticing.

    E3 recomputes and re-posts after each week closes (§3.4), so the timestamp is
    what says *which* week's recomputation a score is: a platform that rewrites
    it makes every repost indistinguishable from the last, and the tool has no
    way to prove what it sent.
    """
    created = mock_platform.create_line_item(signed_launch)
    user_id = seeded_subjects(mock_platform)[0]
    posted = score_payload(user_id, comment=POSTED_COMMENT)
    response = mock_platform.post_score(created, posted)
    assert 200 <= response.status_code < 300, (
        f"Posting the score answered {response.status_code}, so there is nothing to read back. "
        f"Body begins {response.text[:200]!r}."
    )

    entries = mock_platform.posted_scores_for(created)
    assert len(entries) == 1, (
        f"One score was posted to `{created.get('id')}` and `/mock/posted-scores` reports "
        f"{len(entries)} entries for it: {entries!r}."
    )
    recorded = scores_in(entries)[0]
    assert recorded == posted, (
        "The recorded score is not the body that was posted: "
        + "; ".join(disagreements(recorded, posted))
        + f". Recorded {recorded!r} against posted {posted!r}. E0-15: the entry carries 'the "
        "posted body, verbatim' — a recorder that normalises a field or fills in a default is a "
        "recorder a test cannot use to prove what the tool sent."
    )


def test_the_recorded_score_carries_no_field_the_tool_did_not_post(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """The other direction of verbatim, and the near miss the test above cannot see.

    The mutation is a score modelled with a fixed set of attributes and dumped
    back out: `comment` arrives as `null`, `scoreMaximum` as a default 100, and
    every field the tool *did* send round-trips perfectly. The test above posts
    a `comment` and so cannot tell an invented one from a kept one; this one
    posts the AGS-required members alone and asserts nothing was added.

    It matters beyond tidiness because E3's retry handling will compare what it
    sent against what the platform holds. A default the platform invented reads,
    from the tool's side, as a field the tool got wrong.
    """
    created = mock_platform.create_line_item(signed_launch)
    user_id = seeded_subjects(mock_platform)[0]
    posted = score_payload(user_id)
    mock_platform.post_score(created, posted)

    recorded = one_score_for(mock_platform.posted_scores_for(created), user_id)
    invented = sorted(set(recorded) - set(posted))
    assert not invented, (
        f"The recorded score carries {invented}, which the tool never posted — the whole record "
        f"is {recorded!r} against a posted {posted!r}. E0-15 records 'the posted body, verbatim', "
        "and a default the platform filled in is indistinguishable, from the tool's side, from a "
        "value the tool sent."
    )


def test_each_recorded_score_names_the_line_item_it_was_posted_to(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """The `lineItem` half of the entry, which one line item cannot exercise.

    Two mutations, and neither is visible while a test posts to a single line
    item. A recorder that stamps every entry with the most recently created line
    item, and one that records the entries in the right order with the line item
    of the *last* post, both answer correctly for one. SPEC §3.4 gives every
    section its own line item, so a readback that cannot say which section a
    score belongs to is one E3 cannot use to check its own passback.

    The identifier is compared whole rather than by suffix: E0-15 says the entry
    carries the absolute line item URL, and a relative path is a value that
    stops being unique the moment two contexts number their line items from one.
    """
    first = mock_platform.create_line_item(signed_launch)
    second = mock_platform.create_line_item(signed_launch)
    user_id = seeded_subjects(mock_platform)[0]

    mock_platform.post_score(first, score_payload(user_id))
    mock_platform.post_score(second, score_payload(user_id, scoreGiven=SECOND_POSTED_SCORE))

    for line_item, expected_score in ((first, POSTED_SCORE), (second, SECOND_POSTED_SCORE)):
        entries = mock_platform.posted_scores_for(line_item)
        assert len(entries) == 1, (
            f"`/mock/posted-scores` reports {len(entries)} entries naming line item "
            f"`{line_item.get('id')}` after one score was posted to it. Every entry it reports is "
            f"{mock_platform.posted_scores()!r}."
        )
        recorded = scores_in(entries)[0]
        assert recorded.get("scoreGiven") == expected_score, (
            f"The entry naming line item `{line_item.get('id')}` carries a score of "
            f"{recorded.get('scoreGiven')!r} rather than {expected_score!r}, so the entries and "
            "the line items they name have come apart."
        )


def test_two_students_scores_are_recorded_separately_and_in_arrival_order(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """One score per student, kept in the order they arrived.

    Two mutations in one test because they are two readings of one store. A
    recorder holding the last score it was sent passes every assertion in the
    round trip above, since only one score is ever in flight there; what it
    breaks is what a line item is for, because SPEC §3.4 posts one score per
    student per section and a single slot grades only whoever posted last while
    the tool sees success for everybody. And a recorder keyed by user rather
    than appended to answers both scores in whatever order a dictionary hands
    them over, which E0-15's "in the order the scores arrived" rules out — a
    readback that cannot say what arrived first cannot show a repost sequence.

    The two scores carry different values as well as different users, so a
    platform answering two entries built from one stored score is caught by the
    value rather than by the count.
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

    recorded = scores_in(mock_platform.posted_scores_for(created))
    assert [score.get("userId") for score in recorded] == [first_user, second_user], (
        f"After posting for {first_user!r} and then {second_user!r}, `/mock/posted-scores` reports "
        f"{[score.get('userId') for score in recorded]}. E0-15 records the scores 'in the order "
        "the scores arrived', and one entry where two were posted is a line item holding one "
        "score rather than one score per student."
    )
    assert [score.get("scoreGiven") for score in recorded] == [POSTED_SCORE, SECOND_POSTED_SCORE], (
        f"The two entries carry {[score.get('scoreGiven') for score in recorded]} for scores "
        f"posted as {[POSTED_SCORE, SECOND_POSTED_SCORE]}. Two entries built from one stored "
        "score carry the same value twice."
    )


def test_a_reposted_score_is_kept_beside_the_one_it_replaces(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """A record of what the tool sent, not of what the grade currently is.

    SPEC §3.4 recomputes and re-posts a participation score after every week
    closes, so the same student's score arrives at the same line item many times
    over a term. E0-15 records "the order the scores arrived", which a store
    keyed by `(lineItem, userId)` cannot express: it holds the latest and the
    earlier posts are gone. That store passes every other test in this module,
    and it is the one that leaves E3 unable to show that a repost happened at
    all — which is exactly what its retry handling will need to prove.

    The two posts carry increasing timestamps, because AGS permits a platform to
    refuse a score older than the one it holds and a test should not depend on
    the mock's choice about that.
    """
    created = mock_platform.create_line_item(signed_launch)
    user_id = seeded_subjects(mock_platform)[0]

    mock_platform.post_score(created, score_payload(user_id))
    mock_platform.post_score(
        created,
        score_payload(user_id, scoreGiven=SECOND_POSTED_SCORE, timestamp=SECOND_POSTED_TIMESTAMP),
    )

    recorded = scores_for(mock_platform.posted_scores_for(created), user_id)
    assert [score.get("scoreGiven") for score in recorded] == [POSTED_SCORE, SECOND_POSTED_SCORE], (
        f"Two scores were posted for {user_id!r} to one line item and `/mock/posted-scores` "
        f"reports {[score.get('scoreGiven') for score in recorded]}. E0-15 records scores 'in the "
        "order the scores arrived', which reads as a log of what was received rather than a "
        "latest-per-student store — if that reading is wrong, it is the ticket that has to say "
        "so, because a store that keeps only the latest cannot show E3 that a repost happened."
    )


def test_the_results_endpoint_answers_without_the_fields_a_result_has_no_room_for(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """The conformant half of the readback, and why the mock route exists at all.

    The mutation is a `Result` widened with `timestamp`, `activityProgress` and
    `gradingProgress` so that criterion 4 could be met through the protocol. It
    is an attractive mistake — one endpoint instead of two, and every readback
    test passes — and what it does is teach E3 to read fields no real platform
    sends, which surfaces against the first live LMS as a passback that cannot
    verify itself.

    The absence is asserted over a result that is *there*: `docs/MISTAKES.md`
    entry 3, because "the record carries none of these three fields" is true of
    an endpoint that answers an empty array, of one that lost the score, and of
    one that never received it. So the result for this user is required first,
    with the score it was posted, and only then is it asked what it does not
    carry.
    """
    created = mock_platform.create_line_item(signed_launch)
    user_id = seeded_subjects(mock_platform)[0]
    mock_platform.post_score(created, score_payload(user_id))

    results = [
        result
        for result in mock_platform.results(created)
        if str(result.get("userId", "")) == user_id
    ]
    assert len(results) == 1, (
        f"The AGS Result service reports {len(results)} results for {user_id!r} after one score "
        f"was posted. It reports {mock_platform.results(created)!r}. E0-15: 'The conformant AGS "
        "Results endpoint answers for the same line item.'"
    )
    result = results[0]
    assert isinstance(result.get("resultScore"), int | float), (
        f"The result for {user_id!r} carries no numeric `resultScore` — the whole result is "
        f"{result!r}. Without this the assertion below would be true of a result that had lost "
        "the score entirely, which is `docs/MISTAKES.md` entry 3 exactly."
    )
    assert result.get("resultScore") == POSTED_SCORE, (
        f"The result for {user_id!r} carries `resultScore` {result.get('resultScore')!r} for a "
        f"score posted as {POSTED_SCORE} out of {POSTED_MAXIMUM}, against a line item whose "
        f"maximum is also {POSTED_MAXIMUM}. AGS lets a platform rescale a score to the line "
        "item's maximum and there is nothing to rescale here, so the two should agree; if the "
        "mock is deliberately rescaling, that is a sentence the ticket owes rather than a "
        "number this test should widen."
    )
    widened = sorted(name for name in FIELDS_A_RESULT_DOES_NOT_CARRY if name in result)
    assert not widened, (
        f"The AGS Result for {user_id!r} carries {widened} — the whole result is {result!r}. A "
        "`Result` has `id`, `userId`, `resultScore`, `resultMaximum`, `scoreOf` and `comment` and "
        "nothing else, and E0-15 makes that absence a criterion: the readback of the posted body "
        "is `GET /mock/posted-scores`, outside the AGS namespace, precisely so that nothing "
        "teaches E3 to expect these three from a platform."
    )
