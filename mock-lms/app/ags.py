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

from dataclasses import dataclass, field
from itertools import count
from typing import Any
from urllib.parse import quote

from app.config import PlatformSettings

# The media types AGS 2.0 fixes. Served rather than `application/json` for the
# reason `app.nrps` gives: a tool that content-negotiates gets what it asked for.
LINE_ITEM_MEDIA_TYPE = "application/vnd.ims.lis.v2.lineitem+json"
LINE_ITEM_CONTAINER_MEDIA_TYPE = "application/vnd.ims.lis.v2.lineitemcontainer+json"
RESULT_CONTAINER_MEDIA_TYPE = "application/vnd.ims.lis.v2.resultcontainer+json"
SCORE_MEDIA_TYPE = "application/vnd.ims.lis.v1.score+json"

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
REQUIRED_LINE_ITEM_MEMBERS = ("label", "scoreMaximum")
REQUIRED_SCORE_MEMBERS = ("userId", "timestamp", "activityProgress", "gradingProgress")


class GradeServiceError(ValueError):
    """A line item or a score cannot be accepted, and why. The route makes it a 422."""


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


def required_members(payload: dict[str, Any], members: tuple[str, ...], subject: str) -> None:
    """Refuse a body missing anything AGS makes mandatory, naming what is missing."""
    absent = [member for member in members if payload.get(member) in (None, "")]
    if absent:
        raise GradeServiceError(
            f"The {subject} carries no {absent}. AGS 2.0 requires {list(members)}; it carries "
            f"{sorted(payload)}."
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

    def line_items(self, context_id: str) -> list[LineItem]:
        """Every line item in one section's gradebook, in creation order."""
        return [item for item in self._line_items.values() if item.context_id == context_id]

    def line_item(self, context_id: str, line_item_id: str) -> LineItem | None:
        """One line item, or `None` — the route decides the error.

        Addressed through its context as well as its own identifier, so a line
        item cannot be reached from a section it does not belong to.
        """
        found = self._line_items.get(self.settings.line_item_url(context_id, line_item_id))
        return found if found is not None and found.context_id == context_id else None

    # -- scores --------------------------------------------------------------

    def record_score(self, line_item: LineItem, payload: dict[str, Any]) -> None:
        """Append one score, exactly as it arrived.

        Nothing is normalised, defaulted or dropped. The body is the decoded
        request and is stored by reference to that decode alone, so a field the
        tool sent and a field this platform invented cannot be confused — which
        is the only property that makes this readback usable as evidence.
        """
        required_members(payload, REQUIRED_SCORE_MEMBERS, "score")
        given = payload.get("scoreGiven")
        if given is not None and not isinstance(given, int | float):
            raise GradeServiceError(
                f"The score carries `scoreGiven` {given!r}, which is not a number. AGS 2.0 makes "
                "it optional and numeric; a score sent without one clears the result."
            )
        self._scores.append(PostedScore(line_item=line_item.identifier, score=payload))

    def posted_scores(self) -> list[PostedScore]:
        """Every score this platform has been sent, in the order it received them."""
        return list(self._scores)

    def results(self, line_item: LineItem) -> list[dict[str, Any]]:
        """The conformant AGS Result container for one line item.

        A `Result` is the *current* grade, so it is folded out of the score log
        rather than stored beside it: the latest score for each user wins, and a
        score sent with no `scoreGiven` clears that user's result, which is what
        AGS 2.0 says an absent `scoreGiven` means.

        Nothing is rescaled. `resultScore` is the posted `scoreGiven` and
        `resultMaximum` is the line item's own maximum — AGS permits a platform
        to rescale between the two, and a mock that did would make every E3
        assertion about a posted number a question about arithmetic nobody wrote
        down.
        """
        latest: dict[str, dict[str, Any]] = {}
        for posted in self._scores:
            if posted.line_item != line_item.identifier:
                continue
            user = posted.score.get("userId")
            if not isinstance(user, str):
                continue
            if posted.score.get("scoreGiven") is None:
                latest.pop(user, None)
            else:
                latest[user] = posted.score
        return [result_document(line_item, user, score) for user, score in latest.items()]


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
