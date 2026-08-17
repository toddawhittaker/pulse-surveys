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

**What the service refuses is as much of the contract as what it accepts**, and
a review found the refusals missing: `{"activityProgress": "Finished"}`,
`{"timestamp": "yesterday"}` and a score older than the one already held were
all accepted, the last of them overwriting a newer grade. The mock is the
reference platform E1 and E3 are built against rather than a quirk profile, so
a score it takes is a score the tool learns to send — and finds out about
against a real LMS. One of those rules goes past AGS 2.0's own text and is
marked where it is asserted: a `scoreMaximum` differing from the line item's is
**refused** rather than rescaled, because E0-15 rules that Results does not
rescale, and accepting the mismatch would produce a wrong grade in silence. It
is a deliberate narrowing rather than conformance — the specification permits
the mismatch and expects the platform to scale — and what follows for E3 is that
it posts against the line item's own maximum and never relies on a platform to
scale for it.

A second rule fills a gap the specification leaves rather than narrowing it. AGS
refuses a timestamp *before* the one held and says nothing about an equal one;
E0-15 rules that equal is **accepted**, because a passback that times out on the
network re-sends an identical body and a platform that answered 409 to that
would tell E3 its retry failed while the score sat in the log. This suite
asserted the opposite for a day, and the test that turned around says so in its
own docstring.

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
from uuid import uuid4

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

# AGS 2.0's two fixed vocabularies, whole. **The specification's, not this
# suite's**, and transcribed rather than sampled on purpose: a validator is as
# easy to write too narrow as too wide, and the test that every one of these is
# accepted is what tells a rejected `Finished` apart from a rejected everything.
ACTIVITY_PROGRESS_VALUES = ("Initialized", "Started", "InProgress", "Submitted", "Completed")
GRADING_PROGRESS_VALUES = ("FullyGraded", "Pending", "PendingManual", "Failed", "NotReady")

# The launch claim naming the placement a line item can be tied to, spelled as
# LTI 1.3 spells it. A line item may carry a `resourceLinkId`, and the container
# may be filtered by it.
RESOURCE_LINK_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/resource_link"

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


def stamped(step: int, second: int = 9) -> str:
    """A distinct RFC 3339 timestamp, strictly later for a larger `step`.

    Several tests post more than once for one student on one line item, and AGS
    2.0 makes a score's timestamp monotonic per student per line item — so a
    sequence of posts needs a sequence of stamps, and reusing one constant would
    turn a test about something else into a test about the conflict rule.

    `second` exists for the one test that needs a stamp a *second* earlier
    rather than a minute, and it is derived from the same expression rather than
    written out beside it: a constant holding "one second before `stamped(5)`"
    is two copies of one arithmetic, and the day the base moves only one of them
    follows.
    """
    assert 0 <= step <= 54, f"`stamped({step})` would not stay inside one hour."
    assert 0 <= second <= 59, f"`stamped(second={second})` is not a second."
    return f"2026-03-02T14:{5 + step:02d}:{second:02d}+00:00"


def refused(platform: Any, line_item: dict[str, Any], payload: dict[str, Any], why: str) -> Any:
    """Post `payload`, require it refused, and require nothing recorded.

    Two halves, and the second is the near miss in every refusal test below: an
    implementation that appends the score and *then* validates answers 4xx and
    keeps it, which E0-15's log makes visible and a status-only assertion does
    not. The ticket also rules that the store is a log, so a refused post must
    leave that log exactly as it was.

    The refusal is asserted as any 4xx rather than as a particular code, because
    AGS fixes one — 409 for a stale timestamp, asserted by the test that is about
    it — and leaves the rest to the platform. FastAPI answers 422 for a body its
    model rejects and 400 for a rule a handler enforces, and choosing between
    those two would be this suite deciding where the implementer puts a check.
    """
    before = platform.posted_scores_for(line_item)
    response = platform.post_score(line_item, payload)
    assert 400 <= response.status_code < 500, (
        f"The platform answered {response.status_code} for {why}: {payload!r}. Body begins "
        f"{response.text[:200]!r}. AGS 2.0 does not admit this score, and a mock that accepts it "
        "is the reference behaviour E1 and E3 are built against — so the tool learns to send "
        "something no real platform takes."
    )
    after = platform.posted_scores_for(line_item)
    assert len(after) == len(before), (
        f"The platform answered {response.status_code} for {why} and recorded it anyway: "
        f"{len(before)} scores before the post and {len(after)} after. A refusal that stores the "
        "score is worse than an acceptance, because the tool retries what it believes failed."
    )
    return response


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


# ---------------------------------------------------------------------------
# What the Score service refuses. AGS 2.0's own rules, none of them the mock's
# to relax: it is the reference platform E1 and E3 are built against, so a score
# it accepts is a score the tool learns to send.
# ---------------------------------------------------------------------------


def test_a_score_that_carries_a_value_and_no_maximum_is_refused(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """AGS 2.0 makes `scoreGiven` and `scoreMaximum` a pair.

    A score is a fraction, and half of one is not a smaller fact — it is no fact
    at all. A platform accepting `scoreGiven` alone has to invent the
    denominator, and whichever it invents (the line item's maximum, 100, 1.0)
    turns a tool's bug into a grade nobody can trace.

    The mutation this survives is the natural one: a request model that makes
    `scoreMaximum` optional because AGS also permits a score with *neither*
    field — a "no grade yet" post carrying only progress. That is a real shape
    and it is why the rule cannot be "scoreMaximum is required"; it is
    "required when `scoreGiven` is present", and only a test that posts one
    without the other tells the two apart.
    """
    created = mock_platform.create_line_item(signed_launch)
    payload = score_payload(seeded_subjects(mock_platform)[0])
    payload.pop("scoreMaximum")
    refused(mock_platform, created, payload, "a score carrying `scoreGiven` and no `scoreMaximum`")


def test_a_score_with_a_non_positive_maximum_is_refused(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """Zero and negative are refused, as they already are on a line item.

    `create_line_item` refuses a line item whose maximum is not positive; the
    Score service is the same rule one layer down and is easy to leave out,
    because a score arrives with its maximum already "checked" by whoever sent
    it. A maximum of zero makes every participation percentage a division by
    zero in E3, and a negative one inverts the grade.

    Each value gets its own line item, so a value that is wrongly accepted
    cannot leave a score behind that changes what the next value is compared
    against.
    """
    user_id = seeded_subjects(mock_platform)[0]
    for maximum in (0, -100):
        created = mock_platform.create_line_item(signed_launch)
        refused(
            mock_platform,
            created,
            score_payload(user_id, scoreMaximum=maximum),
            f"a score whose `scoreMaximum` is {maximum}",
        )


def test_a_score_whose_maximum_disagrees_with_the_line_items_is_refused(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """A mismatch is refused rather than silently taken and dropped.

    E0-15 rules that the Results endpoint does not rescale, and refusing the
    mismatch is what keeps that ruling honest: accepting `scoreGiven` 61.5 out of
    50 against a line item out of 100 leaves a `Result` that reads 61.5 out of
    100, which is a different grade from the one the tool posted and looks
    correct from both ends.

    **This is a deliberate narrowing of AGS 2.0 and the ticket owns it.** The
    specification lets a platform accept a differing maximum and scale, and
    Canvas does; the mock is the reference behaviour rather than a quirk
    profile, so the narrowing has to be somewhere and refusing is the loud
    choice. What follows for E3 is worth knowing: it must post against the line
    item's own maximum rather than assume a platform will rescale for it.
    """
    created = mock_platform.create_line_item(signed_launch)
    refused(
        mock_platform,
        created,
        score_payload(seeded_subjects(mock_platform)[0], scoreMaximum=POSTED_MAXIMUM // 2),
        f"a score out of {POSTED_MAXIMUM // 2} against a line item out of {POSTED_MAXIMUM}",
    )


def test_every_value_in_the_ags_progress_vocabularies_is_accepted(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """The control on the two refusal tests below, and it is not ceremony.

    A validator that refuses `Finished` and `Graded` passes those tests; so does
    a validator that refuses everything, and so does one built from the three
    values somebody happened to think of. `docs/MISTAKES.md` entry 3: run the
    matcher against what it is claimed to allow as well as what it is claimed to
    catch. AGS's vocabularies are small and fixed, so "all of them" is the whole
    of what it must allow.

    E3 will send `Submitted`/`PendingManual` and, once a week has closed,
    `Completed`/`FullyGraded`; a mock that admits only the pair its own tests use
    fails the first time the tool changes state.
    """
    user_id = seeded_subjects(mock_platform)[0]
    for activity in ACTIVITY_PROGRESS_VALUES:
        created = mock_platform.create_line_item(signed_launch)
        response = mock_platform.post_score(
            created, score_payload(user_id, activityProgress=activity)
        )
        assert 200 <= response.status_code < 300, (
            f"The platform answered {response.status_code} for `activityProgress` {activity!r}, "
            f"which is one of AGS 2.0's five: {list(ACTIVITY_PROGRESS_VALUES)}. Body begins "
            f"{response.text[:200]!r}."
        )
    for grading in GRADING_PROGRESS_VALUES:
        created = mock_platform.create_line_item(signed_launch)
        response = mock_platform.post_score(
            created, score_payload(user_id, gradingProgress=grading)
        )
        assert 200 <= response.status_code < 300, (
            f"The platform answered {response.status_code} for `gradingProgress` {grading!r}, "
            f"which is one of AGS 2.0's five: {list(GRADING_PROGRESS_VALUES)}. Body begins "
            f"{response.text[:200]!r}."
        )


def test_an_activity_progress_outside_the_ags_vocabulary_is_refused(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """`Finished` is not a value AGS has, however reasonable it reads.

    The mutation is the absence of any check at all: `{"activityProgress":
    "Finished"}` is accepted with 200, recorded verbatim, and read back by a test
    that compares what it posted — so the round trip agrees with itself about a
    word no platform sends. E1 or E3 written against it produces a passback that
    a real LMS refuses in production, which is the worst place to find out.

    The lower-case case is included deliberately: AGS's values are exact
    strings, so a platform that title-cases what it is given is accepting a
    spelling that no conformant tool sends and teaching the tool it is fine.
    """
    user_id = seeded_subjects(mock_platform)[0]
    for wrong in ("Finished", "Complete", "submitted"):
        created = mock_platform.create_line_item(signed_launch)
        refused(
            mock_platform,
            created,
            score_payload(user_id, activityProgress=wrong),
            f"an `activityProgress` of {wrong!r}, outside {list(ACTIVITY_PROGRESS_VALUES)}",
        )


def test_a_grading_progress_outside_the_ags_vocabulary_is_refused(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """`Graded` is the natural wrong guess, and it is not one of the five.

    Its own test rather than a second case inside the one above, because the two
    fields are validated separately and an implementation that checks one and
    forgets the other is the likeliest half-right shape there is — and a runner
    line naming the field is the difference between reading that and opening the
    file.
    """
    user_id = seeded_subjects(mock_platform)[0]
    for wrong in ("Graded", "Done", "fullygraded"):
        created = mock_platform.create_line_item(signed_launch)
        refused(
            mock_platform,
            created,
            score_payload(user_id, gradingProgress=wrong),
            f"a `gradingProgress` of {wrong!r}, outside {list(GRADING_PROGRESS_VALUES)}",
        )


def test_a_timestamp_that_is_not_rfc_3339_is_refused(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """`"yesterday"` is currently accepted, and the ordering rule rests on this one.

    Three shapes, and the last two are the near misses. `"yesterday"` is the
    obvious mutation — no validation at all. A bare `2026-03-02` is a date rather
    than a timestamp and is what an implementer writes when the day is what
    matters. `2026-03-02T14:05:09` carries no offset, which is the same defect
    ADR 0048 refuses on an enrollment `start` and matters more here: the score
    ordering rule below compares timestamps, and two stamps in unknown zones
    cannot be ordered at all.

    A refusal is the only safe answer. A platform that stores an unparseable
    timestamp has a log it cannot sort, and one that silently substitutes its own
    clock has thrown away the field E3 uses to tell one week's repost from the
    next.
    """
    user_id = seeded_subjects(mock_platform)[0]
    for wrong in ("yesterday", "2026-03-02", "2026-03-02T14:05:09", "03/02/2026"):
        created = mock_platform.create_line_item(signed_launch)
        refused(
            mock_platform,
            created,
            score_payload(user_id, timestamp=wrong),
            f"a `timestamp` of {wrong!r}, which is not an RFC 3339 timestamp with an offset",
        )


def test_a_score_older_than_the_last_one_for_that_user_is_refused_with_409(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """AGS's one fixed status code, and the state it protects.

    Posting `2020-01-01` after `2026-03-02` currently moves the result to the
    older value — a passback arriving out of order, which is exactly what a retry
    is, overwrites a newer grade with a stale one. AGS 2.0 fixes the answer at
    **409 Conflict**, and that specific code is asserted rather than "a 4xx"
    because it is the one E3's retry handling will branch on: a 409 means "your
    score is stale, stop retrying", and a 400 means "your score is malformed,
    fix it".

    Three things are asserted after the refusal, and the second and third are
    where a half-right implementation lives. An implementation that answers 409
    from a guard placed after the write leaves the result moved and the log
    grown, and the status alone cannot see it — E0-15 rules the store is a log,
    so a refused post must leave both exactly as they were.

    **The second stale score is one second earlier rather than years**, and it is
    here because the rule's boundary moved: equal is now accepted, so a guard is
    right about a five-minute gap and wrong inside a minute if it compares
    truncated stamps, or dates, or strings that sort by their date part. A
    six-year gap is refused by every one of those.
    """
    created = mock_platform.create_line_item(signed_launch)
    user_id = seeded_subjects(mock_platform)[0]
    accepted = mock_platform.post_score(
        created, score_payload(user_id, timestamp=stamped(5), scoreGiven=POSTED_SCORE)
    )
    assert 200 <= accepted.status_code < 300, (
        f"The first score answered {accepted.status_code}, so there is no established timestamp "
        f"for a later post to be older than. Body begins {accepted.text[:200]!r}."
    )

    response = refused(
        mock_platform,
        created,
        score_payload(user_id, timestamp=stamped(0), scoreGiven=SECOND_POSTED_SCORE),
        "a score older than the one already recorded for that user on that line item",
    )
    assert response.status_code == 409, (
        f"The platform answered {response.status_code} for a stale score rather than 409. AGS 2.0 "
        "fixes this one code, and E3 branches on it: 409 means the score it holds is newer, which "
        "is a reason to stop retrying, while a 400 means the request was malformed."
    )

    inside_the_minute = refused(
        mock_platform,
        created,
        score_payload(user_id, timestamp=stamped(5, second=8), scoreGiven=SECOND_POSTED_SCORE),
        "a score one second older than the one already recorded for that user",
    )
    assert inside_the_minute.status_code == 409, (
        f"The platform answered {inside_the_minute.status_code} for a score one second older than "
        "the one it holds. Since a score at the *same* instant is accepted, a comparison that "
        "truncates to the minute — or compares dates, or compares the strings by their date part "
        "— is right about the five-minute gap above and wrong here, which is the whole width of "
        "the boundary this rule now has."
    )
    logged = scores_for(mock_platform.posted_scores_for(created), user_id)
    assert [score.get("scoreGiven") for score in logged] == [POSTED_SCORE], (
        f"The refused score reached the log, which now reads {logged!r}. E0-15 records what the "
        "platform *received*, and a refused post was not received — a log carrying it makes every "
        "reader of that log believe a grade was posted that the platform rejected."
    )
    result = [
        entry for entry in mock_platform.results(created) if str(entry.get("userId", "")) == user_id
    ]
    assert result and result[0].get("resultScore") == POSTED_SCORE, (
        f"After a stale score was refused, the result for {user_id!r} reads {result!r} rather "
        f"than the {POSTED_SCORE} that was accepted. A refusal that moves the grade anyway is the "
        "defect the 409 exists to prevent, wearing the status code that says it did not happen."
    )


def test_a_score_repeating_the_last_timestamp_is_accepted_as_a_retry(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """The boundary of the ordering rule: strictly earlier is stale, equal is a retry.

    **This test asserted the opposite until 2026-08-17, and the reason it turned
    around is worth more than the assertion.** AGS 2.0 says a platform refuses a
    timestamp *before* the one it holds; it says nothing about an equal one, and
    "not later" looked like the safe reading. The case that decides it is E3's
    own retry path: a passback that times out on the network re-sends an
    identical body, timestamp included, and a platform answering 409 to that has
    told the tool its retry failed when the score is sitting in the log. So the
    rule is strictly earlier refused, equal accepted, and this test is the one
    that moved.

    The mutation it now kills is therefore the guard written `<=`, which was the
    rule this file asserted a day earlier — a reminder that a test is a record of
    a decision and not only of a behaviour.

    **Why the repeat carries a different score.** The motivating case is an
    identical body, and an identical body is unobservable: the log would hold
    two entries that agree and the result would read the same number whether the
    repeat was applied or silently dropped, which is `docs/MISTAKES.md` entry 3
    exactly. So the repeat carries a different value, and "the repeat won" is
    then distinguishable from "nothing happened". What that does not reach,
    stated rather than implied: the literal identical-retry case is not asserted
    here, and a platform that special-cased a byte-identical body would pass
    this while doing something else with the case E3 actually sends.
    """
    created = mock_platform.create_line_item(signed_launch)
    user_id = seeded_subjects(mock_platform)[0]
    first = mock_platform.post_score(
        created, score_payload(user_id, timestamp=stamped(5), scoreGiven=POSTED_SCORE)
    )
    assert 200 <= first.status_code < 300, (
        f"The first score answered {first.status_code}, so there is no recorded timestamp for a "
        f"second post to repeat. Body begins {first.text[:200]!r}."
    )

    repeat = mock_platform.post_score(
        created, score_payload(user_id, timestamp=stamped(5), scoreGiven=SECOND_POSTED_SCORE)
    )
    assert 200 <= repeat.status_code < 300, (
        f"The platform answered {repeat.status_code} for a score repeating the timestamp it "
        "already holds. AGS 2.0 refuses a timestamp *before* the one recorded and says nothing "
        "about an equal one, and E3's retry path decides it: a passback that times out on the "
        "network re-sends the same body, so a 409 here tells the tool its retry failed while the "
        f"score is in the log. Body begins {repeat.text[:200]!r}."
    )

    logged = [
        score.get("scoreGiven")
        for score in scores_for(mock_platform.posted_scores_for(created), user_id)
    ]
    assert logged == [POSTED_SCORE, SECOND_POSTED_SCORE], (
        f"The log for {user_id!r} reads {logged} after two scores were posted at one timestamp. "
        "E0-15 records what the platform received, in arrival order, so a repeat lands beside the "
        "score it repeats rather than replacing it — a store that overwrites has lost the "
        "evidence that a retry happened, which is the one thing E3's retry handling needs it for."
    )

    result = [
        entry for entry in mock_platform.results(created) if str(entry.get("userId", "")) == user_id
    ]
    assert result and result[0].get("resultScore") == SECOND_POSTED_SCORE, (
        f"After a score at the same timestamp carried {SECOND_POSTED_SCORE}, the result for "
        f"{user_id!r} reads {result!r}. An accepted score is the one the grade reflects; a "
        "platform that logs the repeat and leaves the result on the earlier value has accepted a "
        "post and applied nothing, which the 2xx it answered says it did not do."
    )


# ---------------------------------------------------------------------------
# The line-item container: what a tool may ask it for.
# ---------------------------------------------------------------------------


def test_the_line_item_container_filters_by_resource_id(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """AGS's `resource_id` filter, asked of the platform rather than applied here.

    The mutation is the one every query parameter suffers: accepted and ignored.
    The container answers 200 with every line item it has, a tool filtering the
    response client-side sees the right answer, and the day a context holds a
    hundred line items the tool is reading all of them to find one. Only asking
    the platform and comparing what comes back can tell the two apart.

    Both directions are asserted. Presence alone is satisfied by a container
    that ignores the filter, which is exactly the defect — so the line item that
    must *not* match is created first and required absent.
    """
    resource = f"e0-15-resource-{uuid4().hex[:12]}"
    other = mock_platform.create_line_item(signed_launch)
    mine = mock_platform.create_line_item(signed_launch, resourceId=resource)

    listed = {
        str(item.get("id"))
        for item in mock_platform.line_items(signed_launch, resource_id=resource)
    }
    assert str(mine.get("id")) in listed, (
        f"Filtering the line-item container by `resource_id={resource}` did not return the line "
        f"item created with it. It returned {sorted(listed)}."
    )
    assert str(other.get("id")) not in listed, (
        f"Filtering by `resource_id={resource}` also returned a line item created without it "
        f"({other.get('id')}). The filter is being accepted and ignored, which reads as correct "
        "from a tool that filters the response itself and stops reading as correct the moment a "
        "context holds more line items than fit on a page."
    )


def test_the_line_item_container_filters_by_tag(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """AGS's `tag` filter. Its own test because it is its own parameter.

    Same mutation as `resource_id` and a separate implementation of it: a
    container that reads one filter and drops the other is the shape this catches
    that the test above cannot, and the runner line names which parameter went
    missing.
    """
    tag = f"e0-15-tag-{uuid4().hex[:12]}"
    other = mock_platform.create_line_item(signed_launch)
    mine = mock_platform.create_line_item(signed_launch, tag=tag)

    listed = {str(item.get("id")) for item in mock_platform.line_items(signed_launch, tag=tag)}
    assert str(mine.get("id")) in listed, (
        f"Filtering the line-item container by `tag={tag}` did not return the line item created "
        f"with it. It returned {sorted(listed)}."
    )
    assert str(other.get("id")) not in listed, (
        f"Filtering by `tag={tag}` also returned a line item created without it "
        f"({other.get('id')}). The filter is accepted and ignored."
    )


def test_the_line_item_container_filters_by_resource_link_id(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """AGS's `resource_link_id` filter, against the placement the launch names.

    Written differently from the two filters above, and deliberately. A line item
    created without a `resourceLinkId` may reasonably be *defaulted* to the
    launch's placement by the platform, so "the other one must be absent" would
    fail a mock that is behaving well. What cannot be defaulted is a placement
    that does not exist — so the filter is shown returning the line item that
    carries the launch's own resource link, and returning nothing for a
    placement nobody has. The second half is what a filter being ignored fails.
    """
    placement = signed_launch.claims.get(RESOURCE_LINK_CLAIM)
    link_id = placement.get("id") if isinstance(placement, dict) else None
    if not isinstance(link_id, str) or not link_id:
        pytest.fail(
            f"The launch carries no resource link `id` (its claim is {placement!r}), so there is "
            "no placement to tie a line item to. E0-14's own suite asserts that claim."
        )

    mine = mock_platform.create_line_item(signed_launch, resourceLinkId=link_id)
    listed = {
        str(item.get("id"))
        for item in mock_platform.line_items(signed_launch, resource_link_id=link_id)
    }
    assert str(mine.get("id")) in listed, (
        f"Filtering the line-item container by `resource_link_id={link_id}` did not return the "
        f"line item created against that placement. It returned {sorted(listed)}."
    )

    absent = f"e0-15-absent-link-{uuid4().hex[:12]}"
    assert mock_platform.line_items(signed_launch, resource_link_id=absent) == [], (
        f"Filtering by `resource_link_id={absent}`, which no line item carries, returned "
        f"{mock_platform.line_items(signed_launch, resource_link_id=absent)!r}. A filter that "
        "matches nothing returns nothing; one that falls through to everything hands a tool "
        "another placement's line items."
    )


def test_a_line_item_filter_that_matches_nothing_returns_nothing(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """The empty answer, which is the one a filter is most often wrong about.

    The mutation: an unmatched filter falling through to the unfiltered
    container. It is the natural shape of `if tag: items = [...]` written with
    the assignment inside a branch that never runs, and it fails *open* — the
    tool asks for one line item and is handed every line item in the context.
    Every other filter test here is satisfied by it, because they all assert
    that something is present.

    Asserted with a line item in existence, so that "nothing came back" is a
    fact about the filter rather than about an empty container.
    """
    mock_platform.create_line_item(signed_launch)
    assert mock_platform.line_items(signed_launch), (
        "The line-item container is empty even after a line item was created, so the emptiness "
        "asserted below would say nothing about the filter."
    )
    absent = f"e0-15-absent-tag-{uuid4().hex[:12]}"
    matched = mock_platform.line_items(signed_launch, tag=absent)
    assert matched == [], (
        f"Filtering the line-item container by `tag={absent}`, which no line item carries, "
        f"returned {matched!r}. A filter that matches nothing returns nothing."
    )


def test_the_line_item_container_pages_by_link_header_when_a_limit_is_given(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """`limit` is honoured and the rest is advertised, exactly as NRPS does it.

    Two mutations. A container that accepts `limit` and ignores it answers
    everything on one page with no `Link` header, which a tool reading the first
    page calls the whole set — and it is indistinguishable from a small context
    until one is not. A container that honours `limit` but advertises no next
    page truncates silently, which is worse: the tool sees a short list and no
    reason to ask for more.

    The cursor's own spelling is not asserted. E0-15 names `page`, but what a
    client does is follow the `Link` header wherever it points, so the walk sends
    back exactly what the platform advertised — and a platform that emits a
    cursor it then ignores is caught by the walk arriving at the same page twice,
    which `link_walk` fails on by name.
    """
    first = mock_platform.create_line_item(signed_launch)
    second = mock_platform.create_line_item(signed_launch)

    pages = mock_platform.line_item_pages(signed_launch, limit=1)
    assert len(pages) > 1, (
        f"Asking the line-item container for `limit=1` returned everything on one page of "
        f"{len(pages[0]) if pages else 0} items, with no next relation advertised. Either the "
        "limit was ignored or the rest of the container was never advertised; a tool reading the "
        "first page calls that the whole set."
    )
    assert all(len(page) == 1 for page in pages[:-1]), (
        f"With `limit=1`, the pages came back holding {[len(page) for page in pages]} items. A "
        "limit that is honoured on the first page and forgotten afterwards is a limit a tool "
        "cannot page on."
    )
    assembled = [str(item.get("id")) for page in pages for item in page]
    assert len(assembled) == len(set(assembled)), (
        f"Walking the line-item container by `Link` returned {assembled}, which repeats an "
        "identifier — the same paging overlap the roster tests exist for, one service over."
    )
    for created in (first, second):
        assert str(created.get("id")) in assembled, (
            f"The line item created at `{created.get('id')}` is missing from the assembled "
            f"container {assembled}. Paging that loses a line item loses a section's grades."
        )


# ---------------------------------------------------------------------------
# Results: the container a tool reads, and the URL a single result lives at.
# ---------------------------------------------------------------------------


def test_the_results_container_filters_by_user_id(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """One student's result, asked for by the platform rather than sifted here.

    The mutation is the filter accepted and ignored, and here it is not merely
    inefficient: E3 asking a platform for one student's result and receiving the
    whole class is a tool holding grades it did not ask for. That is the shape
    §4's confidentiality model exists to keep out of the tool, and while the
    mock's own data is fictional, the behaviour E1 and E3 are written against is
    not.

    Both directions again: the other student's result must be absent, not merely
    the asked-for one present.
    """
    subjects = seeded_subjects(mock_platform)
    assert len(subjects) > 1, (
        f"The platform offers launches for only {subjects}, so a filter by user cannot be told "
        "from no filter at all. E0-14 criterion 7 seeds at least two users."
    )
    created = mock_platform.create_line_item(signed_launch)
    mock_platform.post_score(created, score_payload(subjects[0]))
    mock_platform.post_score(created, score_payload(subjects[1], scoreGiven=SECOND_POSTED_SCORE))

    filtered = mock_platform.results(created, user_id=subjects[0])
    named = {str(result.get("userId", "")) for result in filtered}
    assert subjects[0] in named, (
        f"Asking the results container for `user_id={subjects[0]}` returned {filtered!r}, which "
        "does not carry that student's result."
    )
    assert subjects[1] not in named, (
        f"Asking for `user_id={subjects[0]}` also returned {subjects[1]}'s result: {filtered!r}. "
        "The filter is accepted and ignored, so a tool asking for one student is handed the class."
    )


def test_the_score_response_hands_back_a_result_url_that_answers(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """`resultUrl` is the platform's answer to "where did that go?".

    AGS returns it on the Score response so a tool can read back the result it
    just caused without listing a container and searching. The mutation is a
    `resultUrl` composed and returned while no route serves it — which is exactly
    the defect the review found on `<lineitem>/results/<userId>`, and it is
    invisible to every test that reads the container instead.

    A tool that follows what a platform hands it is doing the right thing; a
    platform that hands back a 404 has told it a lie that only shows up in
    whichever job follows the link.
    """
    created = mock_platform.create_line_item(signed_launch)
    user_id = seeded_subjects(mock_platform)[0]
    response = mock_platform.post_score(created, score_payload(user_id))
    try:
        body = response.json()
    except ValueError:
        body = None
    assert isinstance(body, dict) and body.get("resultUrl"), (
        f"The Score service answered {response.status_code} with body {response.text[:200]!r}, "
        "which carries no `resultUrl`. AGS returns it so a tool can read back the result it just "
        "caused, and E0-15 makes it the same URL a `Result` identifies itself by."
    )
    read = mock_platform.service_get(str(body["resultUrl"]))
    assert read.status_code == 200, (
        f"The `resultUrl` the platform handed back — `{body['resultUrl']}` — answered "
        f"{read.status_code}. A URL a platform returns and does not serve is a link a tool "
        "follows once, in the job that needed it."
    )
    assert (
        str(read.json().get("userId", "")) == user_id
    ), f"`{body['resultUrl']}` answered {read.json()!r}, which is not {user_id!r}'s result."


def test_every_result_identifies_itself_with_a_url_that_answers(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """A `Result`'s `id` is a URL, and a URL that 404s is not one.

    The finding this closes: `<lineitem>/results/<userId>` is composed into every
    result's `id` and no route serves it. Nothing else notices, because every
    other test reads the container and the container is served — the identifier
    is a string that looks exactly right and is checked by nobody.

    Asserted over every result rather than the first, since a route serving one
    shape of identifier and not another is the failure that survives a
    single-sample test; the container is required non-empty first, because a
    loop over nothing passes.
    """
    created = mock_platform.create_line_item(signed_launch)
    user_id = seeded_subjects(mock_platform)[0]
    mock_platform.post_score(created, score_payload(user_id))

    results = mock_platform.results(created)
    assert results, (
        "The results container is empty after a score was accepted, so the loop below would "
        "assert nothing about any identifier."
    )
    for result in results:
        identifier = result.get("id")
        assert isinstance(identifier, str) and identifier, (
            f"The result {result!r} carries no `id`. AGS makes a result's `id` the URL it lives "
            "at, and E0-15 makes that URL one a tool can follow."
        )
        read = mock_platform.service_get(identifier)
        assert read.status_code == 200, (
            f"A result identifies itself as `{identifier}` and that URL answered "
            f"{read.status_code}. The identifier is composed and never served — which reads as "
            "correct in the container and fails in whatever job follows it."
        )
