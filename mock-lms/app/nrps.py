"""Names and Role Provisioning Service 2.0: one section's roster, in pages.

**Paged, deliberately, on a seed small enough not to need it.** SPEC §7.3 names
NRPS paging as one of the two places platforms deviate from each other, so a mock
that answered every roster in one response would hide the whole bug class until
E1 met it against a real LMS. The page size below is therefore a small constant
rather than something a caller can turn off.

**The `Link` header is the contract.** RFC 8288 is how a platform says where the
next page is, and it is what a conformant client reads — `pylti1p3` among them.
A next URL carried in the response body instead reads perfectly to a human and
leaves a tool syncing page one and calling it the class, so nothing about paging
is expressed in the document.

**Enrollment windows ride on a vendor extension**, under a namespace that cannot
be mistaken for the standard's. NRPS 2.0 defines no date field on a member at
all, while SPEC §3.4 and §9.2 both have the sync read enrollment windows from
NRPS — so every platform that supplies one supplies it as an extension, and this
mock does the same rather than teaching E1 that the dates are core. See
`docs/adr/0048-enrollment-windows-ride-on-a-namespaced-nrps-extension.md`.

**One seeded member carries no such extension at all**, and the key is absent
rather than empty (E0-28 item 1, 2026-08-21). ADR 0048's rule holds for every
member that carries the extension; the exception exists so that E1 meets the
platform supplying no enrollment dates in a test rather than in a deployment.
"""

from dataclasses import dataclass
from typing import Any

from app.config import PlatformSettings
from app.paging import link_header, page_count, page_url, window
from app.seed import MockContext, MockEnrollment, SeededPlatform

# The media type NRPS 2.0 gives a membership container. Served rather than
# `application/json`, because a tool that content-negotiates gets what it asked
# for and a tool that does not is unaffected.
MEMBERSHIP_CONTAINER_MEDIA_TYPE = "application/vnd.ims.lti-nrps.v2.membershipcontainer+json"

# Where an enrollment window rides, and the namespace is the message. `.invalid`
# can never resolve, so nobody can mistake this for a published specification,
# and the path says which specification it is *extending*.
ENROLLMENT_EXTENSION = "https://mock-lms.invalid/spec/nrps/enrollment"

# How many members a page carries. **A constant, not a setting.** Its only job is
# that the seeded rosters divide, and a knob for it would exist to be turned to
# "all of them", which is the arrangement paging exists to stop anyone shipping.
# Five is chosen against the seed in `app.seed`: twelve members is two full pages
# and a short one, seven is one and a short one, and five is exactly one page and
# no next relation at all.
PAGE_SIZE = 5


def nrps_claim(settings: PlatformSettings, context_id: str) -> dict[str, Any]:
    """The NRPS claim: where this launch's roster is served.

    `service_versions` is what a tool reads to decide it is talking to NRPS 2.0
    rather than to the LTI 1.1 memberships extension, and a claim without it is
    one a conformant tool may decline to call.
    """
    return {
        "context_memberships_url": settings.memberships_url(context_id),
        "service_versions": ["2.0"],
    }


@dataclass(frozen=True)
class MembershipPage:
    """One page of one section's roster, with the header that pages it."""

    document: dict[str, Any]
    link_header: str | None


def member_document(platform: SeededPlatform, enrollment: MockEnrollment) -> dict[str, Any]:
    """One NRPS member, spelled as NRPS 2.0 spells it.

    `user_id` and not `userId`: the container is read by `pylti1p3`, which asks
    for the specification's spelling and reads a member with any other as a
    member with no user. `status` is one of NRPS's own three values, which is
    what SPEC §3.4's "Drops: scores stop updating" fires on.

    No name of any kind, and `email` is the only personal field — see
    `app.seed` and ADR 0050.

    **The extension key is omitted entirely for an enrollment with no window**
    (E0-28 item 1), rather than emitted with a `null` `start`. The three shapes
    are three different statements to a tool: an absent key says this platform
    supplies no enrollment dates, which is what every mainstream platform says,
    while a key present and empty says it supplies them and has none for this
    student. E1's `PlatformProfile` adapter (§7.3) branches on which of those it
    is looking at, so a seed serving the tidy one would send it down the wrong
    branch. Exactly one seeded enrollment is written that way; see `app.seed`.
    """
    user = platform.user(enrollment.user_id)
    document: dict[str, Any] = {
        "status": enrollment.status,
        "user_id": enrollment.user_id,
        "roles": list(enrollment.roles),
    }
    if enrollment.opened_at is not None:
        document[ENROLLMENT_EXTENSION] = {
            "start": enrollment.opened_at,
            # Present and `null` rather than omitted. A tool reading an absent
            # key cannot tell "still enrolled" from "this platform does not
            # supply an end", and those need different handling in E1.
            "end": enrollment.closed_at,
        }
    if user is not None:
        document["email"] = user.email
    return document


def membership_page(
    platform: SeededPlatform,
    settings: PlatformSettings,
    context: MockContext,
    page: int,
) -> MembershipPage:
    """One page of one section's roster, with the header that says where the next is.

    Raises `PageOutOfRangeError` for a page this roster does not have, so that a
    client following a header into nowhere gets a `404` naming the problem
    rather than an empty container that reads as a section nobody is in.

    The slicing and the header come from `app.paging`, which the AGS line-item
    container uses too — the ticket rules that it pages "exactly as `nrps.py`
    does", and two copies of that rule would be two things to keep in step.
    """
    base = settings.memberships_url(context.context_id)
    members = platform.enrollments_in(context.context_id)
    pages = page_count(len(members), PAGE_SIZE)
    return MembershipPage(
        document={
            "id": page_url(base, page),
            "context": {
                "id": context.context_id,
                "label": context.label,
                "title": context.title,
            },
            "members": [
                member_document(platform, enrollment)
                for enrollment in window(members, page, PAGE_SIZE)
            ],
        },
        link_header=link_header(base, page, pages),
    )
