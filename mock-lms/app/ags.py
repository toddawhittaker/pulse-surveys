"""Assignment and Grade Services 2.0: line items, scores, and two ways to read back.

SPEC §3.4 is what will drive this: one line item per section called "Pulse
Participation", scored as valid weeks completed over weeks elapsed and re-posted
after every week closes. So a line item is created by the tool rather than seeded
here, and a score is *appended* rather than stored per student — the second
posting of one student's score is a new entry beside the first, because the
sequence is the only evidence E3 has that a repost happened.

**Two readbacks, and the split is the ticket's** (ADR 0047). A conformant AGS
`Result` carries `userId`, `resultScore`, `resultMaximum` and `scoreOf` and
nothing else: no timestamp, no `activityProgress`, no `gradingProgress`. So the
fields a tool needs to prove what it sent cannot come back through the protocol,
and widening `Result` to carry them would teach E3 to read fields no real
platform sends. This module therefore serves the conformant Result container
*and* records every posted body verbatim for `GET /mock/posted-scores`, outside
the AGS namespace.

**Verbatim means verbatim.** The posted body is stored as it was decoded and
served as it was stored — no model, no defaults, no re-rendered timestamp. A
recorder that round-trips a score through a typed model gives back a body that
looks right and is not the one the tool sent, and a test built on it cannot tell
the two apart.

**All of it is per-application state, in memory** (ADR 0049). One process, one
gradebook; a restart is a new platform with no line items and no scores.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from itertools import count
from typing import Any
from urllib.parse import quote

from app.config import PlatformSettings

# The media types AGS 2.0 fixes. Served rather than `application/json` for the
# reason `app.nrps` gives: a tool that content-negotiates gets what it asked for.
LINE_ITEM_MEDIA_TYPE = "application/vnd.ims.lis.v2.lineitem+json"
LINE_ITEM_CONTAINER_MEDIA_TYPE = "application/vnd.ims.lis.v2.lineitemcontainer+json"
RESULT_CONTAINER_MEDIA_TYPE = "application/vnd.ims.lis.v2.resultcontainer+json"
RESULT_MEDIA_TYPE = "application/vnd.ims.lis.v2.result+json"
SCORE_MEDIA_TYPE = "application/vnd.ims.lis.v1.score+json"

# How many line items a page carries when a tool asks for no `limit`. Paged
# always rather than only on request, for the reason `app.nrps` pages a roster
# of twelve: SPEC §7.3 names AGS score semantics as a place platforms deviate,
# and a container that answers everything in one response until somebody asks it
# not to is a container whose paging nobody exercises.
LINE_ITEM_PAGE_SIZE = 5

# The largest `limit` a tool may ask for. A bound rather than a policy: a
# platform caps what a client requests, and a mock that did not would let E3
# ship a sync that asks for everything and works only here.
MAX_LINE_ITEM_LIMIT = 100

# The scopes AGS 2.0 names for the two things §3.4 does, plus the two read-only
# scopes a platform advertises beside them. A tool asks its token endpoint for
# exactly these strings, so a scope of this platform's own devising would be one
# no tool ever requests.
LINE_ITEM_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem"
LINE_ITEM_READONLY_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly"
RESULT_READONLY_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly"
SCORE_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/score"

ADVERTISED_SCOPES = (
    LINE_ITEM_SCOPE,
    LINE_ITEM_READONLY_SCOPE,
    RESULT_READONLY_SCOPE,
    SCORE_SCOPE,
)

# What AGS 2.0 requires of a line item and of a score. Checked rather than
# assumed, and refused loudly: a platform that stored a line item with no
# maximum would answer every later score post with a division nobody can see,
# and a mock that shrugged at a malformed body is a mock that lets E3 ship one.
#
# `scoreMaximum` is deliberately not in the score's list: AGS permits a score
# carrying neither value nor maximum — a "no grade yet" post carrying only
# progress — so the rule is that a maximum is required *when a value is present*,
# which `score_value` below states and this tuple cannot.
REQUIRED_LINE_ITEM_MEMBERS = ("label", "scoreMaximum")
REQUIRED_SCORE_MEMBERS = ("userId", "timestamp", "activityProgress", "gradingProgress")

# AGS 2.0's two fixed vocabularies, whole. A platform that accepts a value
# outside them is the reference behaviour E1 and E3 are built against, so it
# teaches the tool a word — `Finished`, `Graded` — that Canvas answers 422 to and
# D2L accepts into a column that never shows a grade. Exact strings: a platform
# that title-cased what it was given would accept a spelling no conformant tool
# sends and report it as fine.
ACTIVITY_PROGRESS_VALUES = ("Initialized", "Started", "InProgress", "Submitted", "Completed")
GRADING_PROGRESS_VALUES = ("FullyGraded", "Pending", "PendingManual", "Failed", "NotReady")

# How RFC 3339 spells a UTC offset: `Z`, or `+HH:MM` with the colon. Checked
# beside `datetime.fromisoformat` rather than instead of it, because the two
# disagree: `fromisoformat` accepts a compact `+0000`, which RFC 3339 does not.
# ADR 0048 already holds an enrollment window's `start` to the spelling with the
# colon, and one service in this repository accepting what the other refuses
# would be a rule that holds in half the places it applies
# (`docs/MISTAKES.md` entry 13).
RFC_3339_OFFSET = re.compile(r"([Zz]|[+-]\d{2}:\d{2})$")


class GradeServiceError(ValueError):
    """A line item or a score cannot be accepted, and why.

    Carries the status the route answers with, because for one of these rules
    AGS 2.0 fixes the code and the rest it leaves to the platform. 422 is the
    default — the body was understood and is not admissible — and the one
    exception is `StaleScoreError` below.
    """

    status_code = 422


class StaleScoreError(GradeServiceError):
    """A score older than the one already held for that user on that line item.

    **409, and the code is part of the protocol rather than a transport detail**,
    which is why it lives here beside the rule instead of in the route. AGS 2.0
    fixes this one status, and E3 branches on it: a 409 means the platform holds
    a newer score and there is no point retrying, while a 4xx of any other kind
    means the request was malformed and retrying it unchanged will fail again.
    """

    status_code = 409


@dataclass(frozen=True)
class LineItem:
    """One line item, and the document the platform serves for it.

    `document` is what the tool posted with the platform's own `id` written over
    it — the platform owns the identifier and nothing else, so a `scoreMaximum`
    the tool asked for is the one that comes back. §3.4 posts a percentage *of
    the line item's maximum*, and a platform that substituted its own would
    rescale every participation grade in the institution.
    """

    identifier: str
    context_id: str
    document: dict[str, Any]

    @property
    def maximum(self) -> Any:
        return self.document.get("scoreMaximum")


@dataclass(frozen=True)
class PostedScore:
    """One score exactly as it arrived, and the line item it arrived for."""

    line_item: str
    score: dict[str, Any]


@dataclass(frozen=True)
class LineItemFilters:
    """The three filters AGS 2.0 defines on the line-item container.

    Named against the query parameters a tool sends — `resource_link_id`,
    `resource_id`, `tag` — and matched against the line item members those
    parameters select on, which AGS spells in camel case. The two spellings are
    the specification's, not this platform's, and keeping the pair in one place
    is what stops a route reading one and a store matching the other.

    An absent filter matches everything; a filter that matches nothing yields
    nothing. There is no defaulting: a line item created with no `resourceLinkId`
    is not silently attributed to the launch's placement, because a platform that
    did that would answer a filter for placement A with a line item that belongs
    to nobody.
    """

    resource_link_id: str | None = None
    resource_id: str | None = None
    tag: str | None = None

    def matches(self, line_item: "LineItem") -> bool:
        wanted = (
            ("resourceLinkId", self.resource_link_id),
            ("resourceId", self.resource_id),
            ("tag", self.tag),
        )
        return all(
            value is None or line_item.document.get(member) == value for member, value in wanted
        )


def required_members(payload: dict[str, Any], members: tuple[str, ...], subject: str) -> None:
    """Refuse a body missing anything AGS makes mandatory, naming what is missing."""
    absent = [member for member in members if payload.get(member) in (None, "")]
    if absent:
        raise GradeServiceError(
            f"The {subject} carries no {absent}. AGS 2.0 requires {list(members)}; it carries "
            f"{sorted(payload)}."
        )


def one_of(payload: dict[str, Any], member: str, vocabulary: tuple[str, ...]) -> None:
    """Refuse a value outside one of AGS's two fixed vocabularies."""
    value = payload.get(member)
    if value not in vocabulary:
        raise GradeServiceError(
            f"The score carries `{member}` {value!r}, which is not one of AGS 2.0's "
            f"{list(vocabulary)}. The values are exact strings; a platform that accepted a near "
            "miss would teach a tool to send a word no conformant platform takes."
        )


def moment(value: Any) -> datetime:
    """`value` as an RFC 3339 instant, or a refusal saying why it is not one.

    **An offset is required**, not merely a parseable date. Two reasons, and the
    second is this module's own: ADR 0048 already refuses a naive stamp on an
    enrollment window because E0-06 made the calendar timezone-aware throughout,
    and the score ordering rule below *compares* timestamps — two stamps in
    unknown zones cannot be ordered at all, so an ordering rule resting on them
    is arithmetic on a guess.

    A bare `2026-03-02` parses perfectly, lands at midnight in no zone, and is
    exactly what an implementer writes when the day is what matters. That is the
    value this refusal exists for; `"yesterday"` fails on its own.
    """
    if not isinstance(value, str):
        raise GradeServiceError(
            f"The score carries a `timestamp` of {value!r}, which is not a string. AGS 2.0 makes "
            "it an RFC 3339 timestamp."
        )
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as failure:
        raise GradeServiceError(
            f"The score carries a `timestamp` of {value!r}, which is not an RFC 3339 timestamp: "
            f"{failure}. A platform that stored it would have a log it cannot sort."
        ) from failure
    if parsed.tzinfo is None:
        raise GradeServiceError(
            f"The score's `timestamp` {value!r} carries no UTC offset. A stamp without a zone "
            "cannot be ordered against another, and this service refuses a score older than the "
            "one it holds — so an unzoned stamp is a comparison against a guess."
        )
    if not RFC_3339_OFFSET.search(value.strip()):
        raise GradeServiceError(
            f"The score's `timestamp` {value!r} spells its offset in a form RFC 3339 does not. "
            "The offset is `Z` or `+HH:MM` with the colon; `datetime.fromisoformat` also accepts "
            "a compact `+0000`, and this platform does not — an enrollment window is held to the "
            "same spelling (ADR 0048), and one service in this repository accepting what the "
            "other refuses is how a tool learns a rule that holds in half the places it applies."
        )
    return parsed


def score_value(payload: dict[str, Any], line_item: "LineItem") -> None:
    """Refuse a score whose value and maximum do not make a fraction of the line item's.

    Three rules, and the third goes past AGS 2.0 on purpose.

    **A value needs a maximum.** A score is a fraction, and half of one is not a
    smaller fact — it is no fact at all. A platform accepting `scoreGiven` alone
    has to invent the denominator, and whichever it invents turns a tool's bug
    into a grade nobody can trace. AGS permits a score with *neither*, which is
    why this is conditional rather than a required member.

    **A maximum is positive.** Zero makes every participation percentage in E3 a
    division by zero and a negative one inverts the grade — the same rule
    `create_line_item` already applies one layer up.

    **A maximum must equal the line item's**, which AGS does not require: the
    specification lets a platform take a differing maximum and scale, and Canvas
    does. E0-15 rules that Results does not rescale, and those two together would
    let `61.5` out of `50` read back as `61.5` out of `100` — a different grade
    from the one posted, correct-looking from both ends. Refusing is the loud
    half of that ruling. See
    `docs/adr/0051-a-disagreeing-score-maximum-is-refused-rather-than-rescaled.md`.
    """
    given, maximum = payload.get("scoreGiven"), payload.get("scoreMaximum")
    if given is not None and maximum is None:
        raise GradeServiceError(
            f"The score carries `scoreGiven` {given!r} and no `scoreMaximum`. AGS 2.0 makes them "
            "a pair, because a score is a fraction and a platform that invents the denominator "
            "produces a grade nobody can trace."
        )
    if given is not None and not isinstance(given, int | float):
        raise GradeServiceError(
            f"The score carries `scoreGiven` {given!r}, which is not a number. AGS 2.0 makes it "
            "optional and numeric; a score sent without one clears the result."
        )
    if maximum is None:
        return
    if not isinstance(maximum, int | float) or maximum <= 0:
        raise GradeServiceError(
            f"The score carries `scoreMaximum` {maximum!r}. A maximum is a positive number: zero "
            "makes every percentage a division by zero and a negative one inverts the grade."
        )
    if maximum != line_item.maximum:
        raise GradeServiceError(
            f"The score is out of {maximum!r} and the line item is out of {line_item.maximum!r}. "
            "This platform refuses the mismatch rather than rescaling — AGS 2.0 permits it and "
            "expects the platform to scale, and E0-15 rules that Results does not, so accepting "
            "it would read back as a different grade from the one posted. Post against the line "
            "item's own maximum."
        )


@dataclass
class GradeBook:
    """Every line item and every score one running platform has been given.

    A list of scores rather than a mapping keyed by student, and that is the
    ticket's decision rather than a shortcut: §3.4 re-posts a section's score
    after every week closes and E3 adds retries on top, so a re-post is a second
    entry beside the first. A store holding the latest per student cannot show
    that a repost happened at all, which is the one thing E3's retry handling
    will need to prove.
    """

    settings: PlatformSettings
    _line_items: dict[str, LineItem] = field(default_factory=dict)
    _scores: list[PostedScore] = field(default_factory=list)
    _next_ordinal: "count[int]" = field(default_factory=lambda: count(1))

    # -- line items ----------------------------------------------------------

    def create_line_item(self, context_id: str, payload: dict[str, Any]) -> LineItem:
        """Store one line item and give it a URL of its own.

        The identifier is minted here and never taken from the request, however
        the tool spelled one: AGS makes the `id` the platform's, and a platform
        that accepted a tool's would let one section's passback address another
        section's column.
        """
        required_members(payload, REQUIRED_LINE_ITEM_MEMBERS, "line item")
        if not isinstance(payload["scoreMaximum"], int | float) or payload["scoreMaximum"] <= 0:
            raise GradeServiceError(
                f"The line item asks for `scoreMaximum` {payload['scoreMaximum']!r}. A maximum is "
                "a positive number; §3.4 posts a participation score as a percentage of it."
            )
        ordinal = next(self._next_ordinal)
        identifier = self.settings.line_item_url(context_id, str(ordinal))
        document = {key: value for key, value in payload.items() if key != "id"}
        document["id"] = identifier
        line_item = LineItem(identifier=identifier, context_id=context_id, document=document)
        self._line_items[identifier] = line_item
        return line_item

    def line_items(
        self, context_id: str, filters: "LineItemFilters | None" = None
    ) -> list[LineItem]:
        """One section's line items, in creation order, matching every filter given.

        AGS 2.0 defines three filters on this container and a tool uses them to
        do find-or-create: SPEC §3.4 has E3 create one "Pulse Participation" line
        item per section on first launch, which means asking whether it already
        exists. A platform that accepted a filter and ignored it answers that
        question with every line item in the context, so the idempotency check
        can never be exercised honestly — and against a platform that pages, a
        line item on page two reads as absent and E3 creates a second gradebook
        column per section per sync.

        A filter that matches nothing returns nothing. That sounds too obvious to
        write down and it is the half that fails open: `if tag: items = [...]`
        with the assignment inside a branch that never runs hands a tool every
        line item in the context, and every "the one I asked for is present"
        assertion passes against it.
        """
        found = [item for item in self._line_items.values() if item.context_id == context_id]
        return [item for item in found if filters is None or filters.matches(item)]

    def line_item(self, context_id: str, line_item_id: str) -> LineItem | None:
        """One line item, or `None` — the route decides the error.

        Addressed through its context as well as its own identifier, so a line
        item cannot be reached from a section it does not belong to.
        """
        found = self._line_items.get(self.settings.line_item_url(context_id, line_item_id))
        return found if found is not None and found.context_id == context_id else None

    # -- scores --------------------------------------------------------------

    def record_score(self, line_item: LineItem, payload: dict[str, Any]) -> None:
        """Check one score against AGS's rules and append it exactly as it arrived.

        **Every check runs before anything is stored.** A refusal that appends
        first and validates afterwards answers 4xx and keeps the score, which is
        worse than accepting it: the tool retries what it believes failed, and
        the log — which E0-15 makes the record of what the platform *received* —
        claims a grade was posted that the platform rejected.

        Nothing is normalised, defaulted or dropped on the way in. The body is
        the decoded request and is stored as it decoded, so a field the tool sent
        and a field this platform invented cannot be confused, which is the only
        property that makes this readback usable as evidence.
        """
        required_members(payload, REQUIRED_SCORE_MEMBERS, "score")
        one_of(payload, "activityProgress", ACTIVITY_PROGRESS_VALUES)
        one_of(payload, "gradingProgress", GRADING_PROGRESS_VALUES)
        stamped = moment(payload["timestamp"])
        score_value(payload, line_item)
        self.refuse_a_stale_score(line_item, str(payload["userId"]), stamped)
        self._scores.append(PostedScore(line_item=line_item.identifier, score=payload))

    def refuse_a_stale_score(self, line_item: LineItem, user_id: str, stamped: datetime) -> None:
        """Refuse a score older than the last one held for that user on that line item.

        **Strictly earlier is refused; equal is accepted**, and the boundary is a
        decision rather than a reading of the specification. AGS 2.0 says a
        platform refuses a timestamp *before* the one it holds and says nothing
        about an equal one. The case that settles it is E3's own retry path: a
        passback that times out on the network re-sends an identical body,
        timestamp included, and a platform answering 409 to that has told the
        tool its retry failed while the score is sitting in the log.

        The comparison is between instants, not between strings or dates. Since
        equal is accepted, a guard that truncated to the minute — or compared the
        date halves — would be right about a stale score from last year and wrong
        about one a second early, which is the whole width of this boundary.
        """
        held = self.last_timestamp(line_item, user_id)
        if held is not None and stamped < held:
            raise StaleScoreError(
                f"The score for {user_id!r} is stamped {stamped.isoformat()} and this platform "
                f"already holds one stamped {held.isoformat()} for that user on this line item. "
                "AGS 2.0 refuses a score older than the one recorded: a passback arriving out of "
                "order would otherwise overwrite a newer grade with a stale one."
            )

    def last_timestamp(self, line_item: LineItem, user_id: str) -> datetime | None:
        """The newest timestamp this platform holds for one user on one line item.

        Read off the log rather than kept in a second mapping beside it, because
        a cache of a fact the log already carries is a fact that can disagree
        with it — and the log is the thing E0-15 makes authoritative. Every entry
        in it was checked by `moment` on the way in, so none of these parses can
        fail.
        """
        stamps = [
            moment(posted.score["timestamp"])
            for posted in self._scores
            if posted.line_item == line_item.identifier
            and str(posted.score.get("userId", "")) == user_id
        ]
        return max(stamps) if stamps else None

    def posted_scores(self) -> list[PostedScore]:
        """Every score this platform has been sent, in the order it received them."""
        return list(self._scores)

    def results(self, line_item: LineItem, user_id: str | None = None) -> list[dict[str, Any]]:
        """The conformant AGS Result container for one line item, optionally for one user.

        A `Result` is the *current* grade, so it is folded out of the score log
        rather than stored beside it: the newest score for each user wins, and a
        score sent with no `scoreGiven` clears that user's result, which is what
        AGS 2.0 says an absent `scoreGiven` means.

        **Newest by timestamp, with arrival order breaking a tie**, and not by
        arrival order alone. The 409 above already makes the log monotonic per
        user per line item, so the two orders agree today and this looks like a
        distinction without a difference — which is the point. The rule "the
        newest score is the grade" and the rule "no score older than the one held
        may be stored" are two guards facing one hazard, and a later ticket that
        relaxed the second would silently regress every grade if the fold leaned
        on it (`docs/MISTAKES.md` entry 13). The tie-break is what keeps a repeat
        at an equal timestamp winning, which is the retry case the 409 admits.

        Nothing is rescaled. `resultScore` is the posted `scoreGiven` and
        `resultMaximum` is the line item's own maximum — and a score whose
        maximum disagreed with the line item's never reached the log, which is
        what makes those two comparable rather than a coincidence (ADR 0051).

        `user_id` filters the container the way AGS 2.0's own query parameter
        does. Filtering here rather than in the route is deliberate: a tool
        asking a platform for one student's result and receiving the class is
        holding grades it did not ask for.
        """
        newest: dict[str, tuple[datetime, int, dict[str, Any]]] = {}
        for arrival, posted in enumerate(self._scores):
            if posted.line_item != line_item.identifier:
                continue
            user = posted.score.get("userId")
            if not isinstance(user, str) or (user_id is not None and user != user_id):
                continue
            ranked = (moment(posted.score["timestamp"]), arrival)
            held = newest.get(user)
            if held is None or ranked >= held[:2]:
                newest[user] = (*ranked, posted.score)
        return [
            result_document(line_item, user, score)
            for user, (_, _, score) in newest.items()
            if score.get("scoreGiven") is not None
        ]

    def result(self, line_item: LineItem, user_id: str) -> dict[str, Any] | None:
        """One user's result on one line item, or `None` — the route decides the error.

        The same fold as the container, asked for one user, so the URL a `Result`
        identifies itself by and the container it appears in cannot answer two
        different grades.
        """
        found = self.results(line_item, user_id=user_id)
        return found[0] if found else None


def result_url(line_item: LineItem, user_id: str) -> str:
    """Where one user's result on one line item is addressed.

    AGS answers a score post with the URL of the result it produced, and serves
    the same URL inside the result itself. One builder, so the two cannot
    disagree about how a user identifier is encoded into a path.
    """
    return f"{line_item.identifier}/results/{quote(user_id, safe='')}"


def result_document(line_item: LineItem, user_id: str, score: dict[str, Any]) -> dict[str, Any]:
    """One AGS `Result`, carrying what a `Result` carries and nothing else.

    The absence is a criterion of E0-15's rather than tidiness: `timestamp`,
    `activityProgress` and `gradingProgress` have no place in a `Result`, and a
    platform that added them would teach E3 to expect three fields no real one
    sends. `GET /mock/posted-scores` is where those are read back.
    """
    document: dict[str, Any] = {
        "id": result_url(line_item, user_id),
        "scoreOf": line_item.identifier,
        "userId": user_id,
        "resultScore": score["scoreGiven"],
        "resultMaximum": line_item.maximum,
    }
    comment = score.get("comment")
    if comment is not None:
        document["comment"] = comment
    return document


def ags_endpoint_claim(settings: PlatformSettings, context_id: str) -> dict[str, Any]:
    """The AGS endpoint claim: where the line items are, and what a token may ask for.

    Both halves matter. A claim carrying a URL and an empty `scope` array
    describes a service the tool may call for nothing, and it looks complete in a
    decoded token.
    """
    return {
        "scope": list(ADVERTISED_SCOPES),
        "lineitems": settings.line_items_url(context_id),
    }
