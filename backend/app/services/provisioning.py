"""Launch-time provisioning: what a verified launch discovers, and what it refuses.

SPEC §2.1 gives courses and sections two arrival paths, "hourly roster sync +
launch-time ingestion", and §7.3 makes the first of those the only thing that can
bootstrap the second: the scheduled job "has no way of its own to learn that a
section exists. So the first staff launch of a section bootstraps every later sync
of it." This module is that path, and it is the first code in this project that
writes a relation SPEC §2.1 puts on the LMS's side.

**It runs after a launch has verified and before the person is sent anywhere.**
`app.api.lti.launch` calls it with the claims `verified_launch` returned, so
everything here is reading a token this tool has already checked the signature,
issuer, audience, deployment, nonce and clock of. Nothing here validates a launch;
this module decides what a valid launch *means* for the org.

**It is handed the configuration the door already holds**, rather than reading the
process for itself, and E1-11 is the ticket that changed that (its D13, closing
deferred E1-10 items 5 and 2). Two rules here depend on configuration: which
addresses this container may fetch, which is switched off in development, and which
day a launch happened on, which decides its term. Both were read from somewhere
`Settings` could not see — `os.environ`, and `datetime.now(UTC)` — and both were
wrong in the same way: a process whose `ENVIRONMENT` lives only in a `.env` file
judged a development stack by a deployment's rules, and a launch in the hours
either side of a term boundary landed in the neighbouring term. `Settings` is the
one place either question is answered now, and `app.api.lti.launch` passes the
instance it already has on `request.app.state.settings`. E2-04 moved the second of
the two one step further on: the day now comes from `app.services.clock`, which
reads the institution timezone out of that same `Settings` and, on a developer's
machine alone, adds the offset a `clock_override` row carries (ADR 0109).

**A refusal here never fails the launch.** Every way a context can be unreadable
ends in a `launch_defect` row and a return, and the person lands exactly as they
would have. That is not leniency: the record is the visibility (`docs/MISTAKES.md`
entry 26), and the alternative — a person who cannot get in because their course
number is out of band — turns a data-quality problem into an outage for them. What
does *not* end in a defect row is a bug in this module: those raise, and the launch
door answers 500, because a writer that swallowed its own failures would be
indistinguishable from one that had nothing to do.

**Three writes, each through the chokepoint** (ADR 0045, ADR 0090). `course`,
`section` and `user` are refused to every caller of `guard_write` that is not
`launch_provisioning`, and this module is that writer: it holds a `WriteSanction`
the catalog in `app.services.authz` grants, and calls the guard before each table's
write in this module. The E0-35 sweep
(`tests/unit/test_every_writer_of_an_lms_owned_relation_names_the_guard.py`) reads
this file syntactically, so the writes are spelled where it can see them and the
guard is named here rather than in a helper somewhere else.

**A refusal from the guard is caught here and never reaches the door.** Today the
catalog grants all three tables, so it cannot happen; the day this module and the
catalog disagree — a table added to a write site and not to the grant, or removed
from the grant and not from the writer — the refusal would otherwise escape the
launch request and lock everybody out of the product, which is the exact failure
direction the ticket's rule forbids and on the one path where the guard is
working. So a refusal is caught on the same atomic boundary a defect is, the write
is skipped with nothing partial left behind, and the person lands. It is **logged
at error level** and it writes **no `launch_defect` row**: a defect record is a
fact about a launch's context, and this is a fact about this project's own code —
the two belong on different surfaces, and the closed set of defect kinds says
nothing about a writer that lost its grant. The log line is the visibility, and it
is not optional (`docs/MISTAKES.md` entry 26).

**The calendar is not derived here.** ADR 0021 gives a section's length, start
date, end date and modality exactly one writer, `apply_section_code`, and this
module calls it and never assigns any of the four. A start position the term's map
has no row for, or dates that would leave the term, is that service's refusal
arriving here as a defect.

**What is deliberately not done.** No roster sync is dispatched from here and no
enrollment or teaching-instructor row is written — a launch proves one person's
presence, not a roster, and E1-11 owns the sync, its debounce and its writes. What
this module does for that ticket is *answer which section*: `provision_from_launch`
returns the id of the section a roster can now be fetched for, and the door hands
that to `app.services.roster_sync.request_section_sync`, which decides whether to
enqueue anything at all. No `person` row is created (E1-12, ADR 0024). Nothing
reads `launch_defect` back: the application role holds `INSERT` on it and no
`SELECT`, and E11 builds the surface that reads it.
"""

import logging
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID, uuid4

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.lti.launch import INSTRUCTOR_ROLE_URI, LTI_ROLES_CLAIM, stated_roles
from app.models.identity import User
from app.models.lti import (
    AGS_CONTAINER_ADDRESS_COLUMN,
    ROSTER_SERVICE_ADDRESS_COLUMN,
    LaunchDefect,
    LaunchDefectKind,
    LtiDeployment,
    LtiPlatform,
    RegistrationAddressError,
    refuse_invalid_fetched_address,
)
from app.models.org import Course, Prefix, Section
from app.models.term import Term
from app.services import clock
from app.services.authz import (
    LmsOwnedWriteRefused,
    WriteSanction,
    guard_write,
    holds_leadership,
    leadership_grant_covers,
    sanction_for,
)
from app.services.identity import identity_behind_a_launch_subject
from app.services.section_codes import SectionCodeError, apply_section_code

__all__ = ["UnregisteredLaunchError", "provision_from_launch"]

logger = logging.getLogger("app.services.provisioning")

# This module's name in `authz.SANCTIONED_WRITERS`. Resolved once at import, so a
# name the catalog does not hold fails when the process starts rather than on
# somebody's launch (ADR 0090).
SANCTION: Final[WriteSanction] = sanction_for("launch_provisioning")

# The claims a context arrives in, spelled as LTI 1.3 and the Names and Role
# Provisioning Service specification spell them. Not this project's to choose, and
# spelled here rather than imported from `app.lti.launch`, which is where the
# claims that module *validates* live. The roles vocabulary this module reads *is*
# imported from there (E1-13), because that one is a vocabulary two modules share
# rather than a claim one module happens to look at.
LTI_CLAIM_PREFIX = "https://purl.imsglobal.org/spec/lti/claim/"
CONTEXT_CLAIM = f"{LTI_CLAIM_PREFIX}context"
DEPLOYMENT_ID_CLAIM = f"{LTI_CLAIM_PREFIX}deployment_id"
NRPS_CLAIM = "https://purl.imsglobal.org/spec/lti-nrps/claim/namesroleservice"
AGS_CLAIM = "https://purl.imsglobal.org/spec/lti-ags/claim/endpoint"

# Where the roster service address sits inside that claim. The member name is the
# NRPS specification's.
MEMBERSHIPS_URL_MEMBER = "context_memberships_url"

# Where the AGS line-item container sits inside the endpoint claim. The member name
# is the Assignment and Grade Services 2.0 specification's, and the claim's other
# members — the scopes a token may be requested for, and a line item id when the
# platform launched into one — are not this module's business. E3-04 is what asks
# for a token; this module only stores the address.
LINE_ITEMS_MEMBER = "lineitems"

# The three members of a context claim this module reads. `id` is the only one LTI
# 1.3 requires; `label` and `title` are both optional, and the whole of what this
# module does with a context depends on which of them arrived.
CONTEXT_ID_MEMBER = "id"
CONTEXT_LABEL_MEMBER = "label"
CONTEXT_TITLE_MEMBER = "title"

# A context label is `PREFIX-NUMBER-CODE` — "BIOL-215-R3WW". Three parts on
# hyphens, exactly: two parts name no section and four name nothing this schema
# holds, and either is a label this tool cannot read rather than one to guess at.
LABEL_SEPARATOR = "-"
LABEL_PARTS = 3

# SPEC §8's course-number bands, as the width rule and the two ranges. **This is a
# second spelling of `app.models.org.COURSE_LEVEL_DERIVATION`**, which is the
# stored generated column that derives `level` from the same bands, and the two
# have to move together — §8 is the authority for both.
#
# It is here rather than left to the column on purpose. `course.level` is NOT NULL
# and derives NULL outside the bands, so the database already refuses an
# out-of-band number — but it refuses it as `null value in column "level"` in the
# middle of a request, which is a 500 and not a refusal: the launch fails, the
# person does not land, and nothing is recorded. §8 asks for the row to be
# rejected at write time, and ADR 0015 calls an unexpected number "a defect to
# see, not a row to accept". Seeing it means checking here first.
#
# **Width is part of the rule.** A three-digit number is valid only in `000`-`799`
# and a four-digit one only in `8000`-`9999`, so `0099` is refused while `099` is
# accepted: they are different strings that a numeric comparison would read as one
# course, which is how one course acquires two spellings and two rows.
THREE_DIGIT_NUMBER = re.compile(r"^[0-9]{3}$")
FOUR_DIGIT_NUMBER = re.compile(r"^[0-9]{4}$")
THREE_DIGIT_CEILING = 799
FOUR_DIGIT_FLOOR = 8000
FOUR_DIGIT_CEILING = 9999


class UnregisteredLaunchError(LookupError):
    """The launch's issuer and audience resolve to no `lti_platform` row.

    Not a defect record and not a refusal: `verified_launch` resolves a launch
    against exactly this registration before this module is reached, so a launch
    that gets here with no platform row means the registration was deleted between
    the two reads, or that this module was called from somewhere that skipped the
    door. Both are conditions to see rather than to write down as a fact about a
    course.
    """


@dataclass(frozen=True)
class ContextLabel:
    """One context label's three parts: `BIOL-215-R3WW` → BIOL, 215, R3WW."""

    prefix: str
    number: str
    code: str


@dataclass(frozen=True)
class ContextBinding:
    """Which context, on which registration, a section was discovered from.

    The identity a course copy cannot reproduce, and the pair `section` is unique
    on. Carried as a value rather than as two arguments because the two are only
    ever meaningful together: a context id without its deployment is unique
    nowhere, and a deployment without a context id is every section of that
    registration at once.
    """

    deployment_id: UUID
    context_id: str


def provision_from_launch(
    session: Session, claims: Mapping[str, Any], settings: Settings
) -> UUID | None:
    """Write what this launch discovered, or record why it could not be read.

    The order is the rule and not an implementation detail. The `user` row is
    written for **every** validated launch — a student's, a teaching assistant's,
    a mentor's — because the person is authenticated whatever their role and
    whatever their context turns out to be, and SPEC §4 keys every response they
    will ever give to that row. Only then is the context looked at, and only for a
    launch §7.3 authorizes: an instructor's, by the claim, or a leadership
    person's, by their own assignment.

    **The two limbs are asked separately, and only one of them is scoped**
    (E2-02, ADR 0108). The LTI roles claim is context-scoped — an Instructor URN
    states what this person is *in the course they launched from* — so the claim
    limb carries its own answer to "staff of which context" and ingests with
    `purview_of=None`. The leadership limb reads a `role_assignment` row that
    says nothing about this launch's context, so it hands `_ingest_the_context`
    the person it resolved and that function refuses to bind a context their
    assignments do not reach. The E1 boundary review's M9 is what that closes:
    before it, "a leadership assignment anywhere" was an unscoped
    roster-ingestion trigger.

    **The ordering carries the leadership limb** (E1-12). That limb resolves the
    launching subject to a `user` row, and the row it resolves is the one the line
    above has just written — a leadership person's very first launch works
    because the write precedes the read inside one transaction, rather than
    provisioning nothing until their second visit.

    **What it answers is the section a roster can now be fetched for**, or `None`.
    SPEC §7.3 pulls NRPS "on schedule and on launch (debounced)", and the launch
    half needs a section id — so this hands one back rather than making the door
    resolve a context claim to a row for itself, which would put domain logic in a
    router §13 keeps thin. It is `None` for every launch that did not both discover
    a section and store an address for it: a student's launch, a staff launch whose
    context could not be read, a staff launch by a leadership person whose own
    assignments do not reach that context, and a staff launch whose platform
    advertised no roster address or an address this container may not fetch. Each
    of those is a section with no roster to pull rather than a sync to skip.

    Nothing here commits: the caller owns the transaction, exactly as
    `app.lti.replay_guard.claim_nonce` leaves its claim to ride inside the
    launch's own session. `app.api.lti.launch` commits once this returns.
    """
    platform = _registered_platform(session, claims)
    _record_the_launching_subject(session, platform, claims)
    if _is_a_staff_launch(claims):
        return _ingest_the_context(session, claims, settings, purview_of=None)
    leader = _leadership_person_behind(session, platform, claims)
    if leader is not None:
        return _ingest_the_context(session, claims, settings, purview_of=leader)
    return None


# ---------------------------------------------------------------------------
# Who launched, and from where.
# ---------------------------------------------------------------------------


def _registered_platform(session: Session, claims: Mapping[str, Any]) -> LtiPlatform:
    """The `lti_platform` row this launch was issued by and for.

    Looked up by the pair rather than by the issuer alone, because that is what
    identifies a registration: one LMS can register this tool twice — a pilot
    beside production — and `sub` is unique per issuer, so the same person on two
    registrations of one platform is one `user` row and on two platforms is two.
    """
    issuer = claims.get("iss")
    audience = claims.get("aud")
    client_id = audience[0] if isinstance(audience, list) else audience
    platform = session.scalars(
        select(LtiPlatform).where(LtiPlatform.issuer == issuer, LtiPlatform.client_id == client_id)
    ).one_or_none()
    if platform is None:
        raise UnregisteredLaunchError(
            "This launch resolves to no registered platform, which the door it came through has "
            "already checked. Either the registration was removed between that check and this "
            "one, or provisioning was reached without one."
        )
    return platform


def _registered_deployment(session: Session, claims: Mapping[str, Any]) -> LtiDeployment:
    """The `lti_deployment` row this launch came from.

    Half of a section's identity, and the half that makes the other half mean
    anything: a context id is the platform's own opaque string, unique inside one
    registration and meaningless across registrations.

    Resolved rather than trusted: `verified_launch` has already refused a launch
    naming a deployment nobody registered, so a launch reaching this point with no
    row is the same class of condition as one with no platform — a registration
    removed between the two reads, or provisioning reached without the door.
    """
    platform = _registered_platform(session, claims)
    deployment_id = claims.get(DEPLOYMENT_ID_CLAIM)
    deployment = session.scalars(
        select(LtiDeployment).where(
            LtiDeployment.lti_platform_id == platform.id,
            LtiDeployment.deployment_id == deployment_id,
        )
    ).one_or_none()
    if deployment is None:
        raise UnregisteredLaunchError(
            "This launch names a deployment no registration holds, which the door it came through "
            "has already checked. A section is bound to the registration it was discovered "
            "through, so there is nothing to bind one to."
        )
    return deployment


def _record_the_launching_subject(
    session: Session, platform: LtiPlatform, claims: Mapping[str, Any]
) -> None:
    """Insert the launching subject's `user` row if it is absent, and never update it.

    ADR 0045 puts `user` in the guarded set because "`user.lms_user_id` is the
    `sub` claim verbatim (ADR 0014: the platform supplies the value and Pulse never
    edits it) and §4 keys every response to it", and names "the launch path that
    creates a `user` row" as the sanctioned writer. This is that path.

    **Written for every verified launch**, whatever the role and whatever the
    context turns out to be. The person is authenticated: a teaching assistant this
    door has no view for is no less somebody E1-12 has to be able to link, and a
    launch whose course could not be read is a defect in the *context*.

    **Insert and let the unique constraint decide, rather than looking first.** The
    row is insert-if-absent and never rewritten — nothing on it can be corrected,
    and the application role holds no `UPDATE` on the table in any form — so
    `UNIQUE (lti_platform_id, lms_user_id)` already answers the only question there
    is, atomically and without a read. That is the same reasoning
    `app.lti.replay_guard.claim_nonce` gives for spending a nonce with no `SELECT`,
    and it is what keeps this module out of the way of E0-11's rule that a service
    does not query an identity table
    (`tests/unit/test_no_service_reads_an_identity_table_directly.py`): `user`
    leads to identity, and the launch writer has no business reading it.

    **A guard refusal here leaves nothing to undo**, because the chokepoint is
    asked before the row is built — so this one needs no savepoint of its own, and
    it is caught rather than allowed to escape for the reason the module docstring
    gives. The context is still ingested afterwards: the two are independent, and a
    grant this module has lost on `user` says nothing about its grant on `course`.
    """
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise UnregisteredLaunchError(
            "This launch carries no `sub`, which the door it came through has already required. "
            "There is no subject for a `user` row to be."
        )

    try:
        guard_write(table="user", sanction=SANCTION)
    except LmsOwnedWriteRefused as refusal:
        _log_a_refused_write("user", refusal)
        return
    with _tolerating_a_row_that_is_already_there(session, "the launching subject's user row"):
        session.add(User(lti_platform_id=platform.id, lms_user_id=subject))
        session.flush()


def _is_a_staff_launch(claims: Mapping[str, Any]) -> bool:
    """Whether this launch's roles authorize discovering a course and storing its roster address.

    SPEC §7.3 makes the launching person's role the authorization for the trigger,
    never the request: "The tool calls the roster service with its own credentials,
    so the launching person's role authorizes the *trigger*." So this is an
    authorization boundary and its set is closed and named.

    **Compared whole against the context-instructor URI, never by looking for the
    word.** The two URIs are
    `…/vocab/lis/v2/membership#Instructor` and
    `…/vocab/lis/v2/membership/Instructor#TeachingAssistant`, and neither is a
    substring of the other — so what a whole-value comparison defends against is
    not one URI matching the other but the rule somebody writes instead:
    `any("Instructor" in role for role in roles)`, which the TeachingAssistant
    sub-role satisfies because it spells the parent role in its own path. That is
    the natural implementation and it is correct on every launch tried by hand.
    What it costs is §7.3's boundary: over-inclusion hands a teaching assistant the
    full roster — names and email addresses — that §7.3 does not authorize.
    Under-inclusion costs nothing that lasts, because a real instructor's next
    launch discovers the section.

    **This is one of §7.3's two limbs and it is the claim-based one.** The other —
    "any leadership role" — is a live `role_assignment` in Pulse's own graph rather
    than anything the launch says, and it is `_leadership_person_behind` below.
    E1-10 shipped this limb alone and left that one dormant, because reaching an
    assignment needs the `sub` → `user` → `person` link E1-12 built; E1-12
    activated it (ADR 0090, ADR 0091, ADR 0097). The two are deliberately
    separate functions because they are checked against different sources and one
    of them can be wrong without the other.

    **This limb alone is exempt from E2-02's purview gate**, and the exemption is
    what makes it usable: the roles claim is scoped to the context it arrived
    with, so an Instructor URN is this person's staffness *of this very context*
    and there is no further question to ask. ADR 0108 records the choice; the
    other limb's grant is checked against the launch's own context.
    """
    return INSTRUCTOR_ROLE_URI in stated_roles(claims.get(LTI_ROLES_CLAIM))


def _leadership_person_behind(
    session: Session, platform: LtiPlatform, claims: Mapping[str, Any]
) -> UUID | None:
    """The person behind this launch if Pulse's own records give them a leadership role.

    Answers the `person` this limb authorized, or `None` when the limb does not
    apply. **The identifier is the answer rather than a yes** (E2-02): the
    leadership limb's grant has to be checked against the launch's own context
    before anything is bound, and the caller cannot check a boolean. Before that
    ticket this was `_launching_subject_holds_leadership` and answered `bool`,
    which is the shape the E1 boundary review's M9 describes — a limb that admits
    a leadership holder "with no reference to the launch's context".

    §7.3's second limb, and the one that reads the database rather than the token:
    "A launch by an instructor **or any leadership role** triggers a roster sync."
    §2.1 makes a role a `role_assignment` row and never a claim, and E0-09's tenth
    criterion is the reason — the administrator of a platform writes what its
    launches say, so a limb read out of the roles claim would let them hand
    themselves a section's whole roster of names and email addresses.

    **So the question is asked of the assignment and answered from `sub`.** The
    subject resolves to a `user` row at this registration and then to a `person`
    (ADR 0094's point resolvers, through `app.services.identity`), and the roles
    that person holds are asked of `app.services.authz.holds_leadership`.

    **The role question goes through the chokepoint and is not asked here**, which
    is a rule rather than a preference and it is the one thing this function got
    wrong first. `public.assignment_scope` is unfiltered — nothing in the database
    narrows it — so the only narrowing anywhere is inside `app.services.authz`,
    where §2.1's scope rules are written, and
    `tests/unit/test_the_org_views_are_read_only_through_the_grant.py` is the §4.1
    invariant that holds every read of that view to that module. A `SELECT` written
    here applied whichever of §2.1's rules its author remembered; the invariant
    caught it and its message names where the predicate belongs.

    **Three ways to answer no, and each is an ordinary state.** A launch with no
    `sub` never reaches here from the door; a subject with no `person` is a student
    or somebody nobody has put in the people graph (ADR 0028); and a person holding
    only assignments outside `LEADERSHIP_ROLES` — a Care officer, an administrator
    — holds a live grant that authorizes nothing about a roster. §2.1 puts Care
    outside the supervision graph altogether, which is why that set is enumerated
    positively rather than written as "any assignment at all".

    **Asked only when the claim limb has already said no**, because the caller
    returns on that limb first: an ordinary instructor launch costs no query, and
    the two hops plus the chokepoint's read are paid on the launches the cheap
    test does not answer.
    """
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        return None
    identity = identity_behind_a_launch_subject(session, platform_id=platform.id, subject=subject)
    if identity.person_id is None:
        return None
    if not holds_leadership(session, person_id=identity.person_id):
        return None
    return identity.person_id


# ---------------------------------------------------------------------------
# What the context says, and the ways it cannot be ingested. `LaunchDefectKind`
# in `app.models.lti` is the closed set, and the order they are checked in here
# is the precedence: a launch that is two of them is recorded as the first.
# ---------------------------------------------------------------------------


def _ingest_the_context(
    session: Session,
    claims: Mapping[str, Any],
    settings: Settings,
    *,
    purview_of: UUID | None,
) -> UUID | None:
    """Upsert the course and section this launch's context names, or record a defect.

    Answers the section this launch's roster can be fetched for, and `None` where
    there is none to fetch — see `provision_from_launch` for what the answer is
    spent on and for every way it comes back `None`.

    **`purview_of` is which limb authorized this launch** (E2-02, ADR 0108).
    `None` is the claim limb, whose Instructor URN is already an assertion about
    *this* context, so nothing further is asked. A person id is the leadership
    limb, and it is the person whose own assignments have to reach the context
    below before anything is bound — the E1 boundary review's M9. It is a
    keyword-only parameter with no default on purpose: a caller that forgot it
    would silently get the unscoped behaviour this ticket exists to remove.

    Every look-up happens before any write, so that every defect but one is
    decided while nothing has been written at all. The exception —
    `section_code_underivable` — is ADR 0021's refusal and can only be known by
    asking `apply_section_code`, which is why the two writes sit inside one
    savepoint: a defect anywhere leaves course *and* section unwritten, and a
    course row for a section that could never be completed is a row a later
    correct launch would find and not recognise.

    **A guard refusal rides the same savepoint**, for the same reason and with a
    different outcome. `guard_write` is asked before each of the two writes, so a
    catalog that no longer grants `section` refuses after the course is written —
    and that is exactly the partial row this boundary exists to prevent. It is
    rolled back and logged, and unlike the defect kinds it writes no record: it is
    a fact about this project's own code rather than about the launch's context.

    **The binding is resolved before the parsed identity, and the two have to
    agree** (round 3, ADR 0091). A section belongs to the context it was
    discovered from — `(lti_deployment_id, lms_context_id)` — and what its label
    parses to is what it is *called*. A course copy reproduces the name and cannot
    reproduce the identity, so the two lookups disagreeing is a collision:
    somebody else's section wears this launch's name, or this launch's context has
    been renamed onto a name nothing holds. Either way nothing is written, the
    course title included, which is why the check sits above the savepoint rather
    than inside it.
    """
    label = _parsed_label(claims)
    context_id = _context(claims).get(CONTEXT_ID_MEMBER)
    if label is None or not isinstance(context_id, str) or not context_id:
        # A context claim carrying no `id` is unreadable in the same way one
        # carrying no label is: LTI 1.3 requires the member, and without it there
        # is no identity to bind a section to and nothing to resolve one by.
        _record_defect(session, claims, LaunchDefectKind.UNPARSEABLE_CONTEXT_LABEL)
        return None
    if not _inside_the_bands(label.number):
        _record_defect(session, claims, LaunchDefectKind.OUT_OF_BAND_COURSE_NUMBER)
        return None

    prefix = session.scalars(select(Prefix).where(Prefix.code == label.prefix)).one_or_none()
    if prefix is None:
        _record_defect(session, claims, LaunchDefectKind.UNKNOWN_PREFIX)
        return None

    term = _term_containing_the_launch_day(session, settings)
    if term is None:
        _record_defect(session, claims, LaunchDefectKind.NO_TERM_FOR_LAUNCH_DATE)
        return None

    binding = ContextBinding(
        deployment_id=_registered_deployment(session, claims).id, context_id=context_id
    )
    discovered = _course_row(session, prefix.id, label.number)
    bound = _section_bound_to(session, binding)
    named = (
        None if discovered is None else _section_row(session, discovered.id, term.id, label.code)
    )
    if not _the_same_section(bound, named):
        _record_defect(session, claims, LaunchDefectKind.CONTEXT_COLLISION)
        return None

    # The purview gate, and it sits exactly here (E2-02, ADR 0108). After the
    # collision check, because a context bound to somebody else's section is an
    # identity-integrity defect whatever the launcher is; before the address is
    # judged, because a launch that may not bind this context should not have its
    # roster address considered at all. It needs `prefix`, `discovered` and
    # `bound`, which is the earliest point all three are resolved.
    #
    # **It refuses the binding and not the launch.** Returning `None` is what
    # every defect above already does, and the door lands the person exactly as
    # it would have — E1-10's rule that a provisioning refusal never fails the
    # launch is unchanged. Nothing about the person reaches the record: SPEC §10
    # keeps personal information out, and the four-field row `_record_defect`
    # writes is the same one every other kind gets.
    if purview_of is not None and not leadership_grant_covers(
        session,
        person_id=purview_of,
        prefix_id=prefix.id,
        course_id=None if discovered is None else discovered.id,
        section_id=None if bound is None else bound.id,
    ):
        _record_defect(session, claims, LaunchDefectKind.CONTEXT_OUTSIDE_PURVIEW)
        return None

    address = _an_address_this_tool_may_call(
        session,
        claims,
        settings,
        _roster_address(claims),
        column=ROSTER_SERVICE_ADDRESS_COLUMN,
        refused=LaunchDefectKind.ROSTER_ADDRESS_REFUSED,
        service="roster service",
    )
    # E3-02's gradebook address, judged on exactly the same terms and here for the
    # same reason: this is the one path SPEC §3.4's line-item container arrives on.
    # A launch that advertises none leaves the column NULL with no record, because
    # a platform granting no gradebook scope is a configuration and not a fault;
    # one that advertises an address these rules refuse leaves the column NULL and
    # records `ags_address_refused`, which is a fault somebody can act on.
    gradebook_address = _an_address_this_tool_may_call(
        session,
        claims,
        settings,
        _gradebook_address(claims),
        column=AGS_CONTAINER_ADDRESS_COLUMN,
        refused=LaunchDefectKind.AGS_ADDRESS_REFUSED,
        service="AGS line-item container",
    )

    both_or_neither = session.begin_nested()
    try:
        course = _upsert_course(session, prefix.id, label, _platform_title(claims))
        if course is not None:
            _upsert_section(
                session,
                course,
                term,
                label,
                binding=binding,
                address=address,
                gradebook_address=gradebook_address,
                section=bound,
            )
    except SectionCodeError as refusal:
        both_or_neither.rollback()
        logger.warning("%s: %s", LaunchDefectKind.SECTION_CODE_UNDERIVABLE.value, refusal)
        _record_defect(session, claims, LaunchDefectKind.SECTION_CODE_UNDERIVABLE)
        return None
    except LmsOwnedWriteRefused:
        # Already logged, by the write site that knows which table it asked about.
        # What is left to do is the undoing, and this is the only frame that holds
        # the savepoint to undo it with.
        both_or_neither.rollback()
        return None
    both_or_neither.commit()

    if address is None:
        # A section with no stored address is SPEC §7.3's never-synced state and
        # there is nothing to trigger: "it has no way of its own to learn that a
        # section exists" cuts both ways, and a sync enqueued with no URL to call
        # would write a failed call record that makes never-synced look like a
        # platform refusing the tool.
        return None
    # Re-read rather than threaded back out of the savepoint above, because the
    # section this launch resolves to is `_section_bound_to`'s answer whether the
    # row was written a moment ago or three terms back, and one lookup on a staff
    # launch is cheaper than a second way of being told which row it is.
    stored = _section_bound_to(session, binding)
    return None if stored is None else stored.id


def _parsed_label(claims: Mapping[str, Any]) -> ContextLabel | None:
    """This launch's context label in three parts, or `None` if there is no reading it.

    A context claim carrying `id` alone is LTI 1.3-conformant and a real platform
    may send one, and there is nothing in it to resolve a prefix or a course number
    from — so it is refused and recorded rather than provisioned from a guess.
    Todd's ruling, 2026-08-26.
    """
    label = _context(claims).get(CONTEXT_LABEL_MEMBER)
    if not isinstance(label, str):
        return None
    parts = label.split(LABEL_SEPARATOR)
    if len(parts) != LABEL_PARTS or not all(parts):
        return None
    prefix, number, code = parts
    return ContextLabel(prefix=prefix, number=number, code=code)


def _inside_the_bands(number: str) -> bool:
    """Whether SPEC §8 holds a band for this course number. See the constants above."""
    if THREE_DIGIT_NUMBER.match(number):
        return int(number) <= THREE_DIGIT_CEILING
    if FOUR_DIGIT_NUMBER.match(number):
        return FOUR_DIGIT_FLOOR <= int(number) <= FOUR_DIGIT_CEILING
    return False


def _term_containing_the_launch_day(session: Session, settings: Settings) -> Term | None:
    """The term whose dates contain the day of this launch, or `None`.

    Todd's ruling, 2026-08-26: "a new section belongs to the one term whose dates
    contain the day of the launch". Not the only term and not the most recent one —
    an empty `term` table and a table holding next year's term are different
    situations with the same answer here, and taking whatever term exists would put
    every section of the year into it.

    **The day is the institution's**, which is E1-11 closing deferred E1-10 item 2.
    This read UTC's day while the writer was handed no configuration, and ADR 0091
    recorded the limit: "a launch in the hours either side of a term boundary can be
    read into the neighbouring calendar day and land in the neighbouring term." SPEC
    §3.1 makes every moment in this product a moment in the institution timezone and
    §8 makes that a deployment-level setting, so a section's term is a fact about the
    institution's calendar rather than about the server's clock.

    **And the day comes from `app.services.clock`** (E2-04, ADR 0109), which is the
    one place this codebase asks what day it is for scheduling purposes. It reads
    the institution's zone, so the paragraph above is unchanged; what it adds is
    that a developer who has moved the clock provisions into the term they moved to.
    `app.services.authz._enrolled_today` asks the same question through the same
    service, so the two are one reading now rather than two copies to keep in step.

    The most recently started containing term wins if an administrator has
    configured two that overlap, which is a tie this schema permits and nothing else
    decides.
    """
    today = clock.today(session, settings=settings)
    return session.scalars(
        select(Term)
        .where(Term.start_date <= today, Term.end_date >= today)
        .order_by(Term.start_date.desc())
    ).first()


def _context(claims: Mapping[str, Any]) -> Mapping[str, Any]:
    """The launch's context claim, or an empty mapping if it carries none."""
    context = claims.get(CONTEXT_CLAIM)
    return context if isinstance(context, Mapping) else {}


def _platform_title(claims: Mapping[str, Any]) -> str | None:
    """The title the platform states for this context, if it states one."""
    title = _context(claims).get(CONTEXT_TITLE_MEMBER)
    return title if isinstance(title, str) and title else None


def _the_same_section(bound: Section | None, named: Section | None) -> bool:
    """Whether the section this context is bound to is the one its label names.

    Both absent is agreement — this is a context nobody has launched, naming a
    section nobody has written — and so is both present and the same row. Anything
    else is the collision: a section some other context is bound to wearing this
    launch's name, or this context bound to a section whose name has moved.
    """
    if bound is None or named is None:
        return bound is None and named is None
    return bound.id == named.id


def _section_bound_to(session: Session, binding: ContextBinding) -> Section | None:
    """The section discovered from one context on one registration, if there is one."""
    return session.scalars(
        select(Section).where(
            Section.lti_deployment_id == binding.deployment_id,
            Section.lms_context_id == binding.context_id,
        )
    ).one_or_none()


def _an_address_this_tool_may_call(
    session: Session,
    claims: Mapping[str, Any],
    settings: Settings,
    address: str | None,
    *,
    column: str,
    refused: LaunchDefectKind,
    service: str,
) -> str | None:
    """One address off a launch if this container may fetch it, and `None` if not.

    Round 3's MEDIUM. E1-11 calls the roster address with the tool's own client
    credentials, on a schedule, with nobody present, so it is judged by the same
    rules `jwks_url` and `auth_token_url` pass — through the one function that
    holds them (`docs/MISTAKES.md` entry 13), not a second copy beside it. There
    are five of those rules since ADR 0101, and the fifth resolves the host and
    judges every address it answers with.

    **It takes the address rather than reading one**, because a launch now carries
    two of them and every word below is true of both. E3-02's AGS line-item
    container is fetched by E3-04 on the same terms, so it reaches the same rules
    under a column of its own and records a kind of its own; `column` is what the
    rules key on and `refused` is what the record says. Two copies of this function
    would be entry 13 exactly — a hazard handled in one of the two places facing
    it — and the copy that went stale would be the one nobody was looking at.

    **This caller names no exempt host and passes no resolver**, which is a
    decision rather than an omission (ADR 0101). In development the blanket
    admission is unchanged, so a launch on the demo stack costs no name lookup; in
    a deployment the host is resolved with the machine's own resolver, one lookup
    on a staff launch that discovers a section.

    **A refused address is not a refused section.** The address stays NULL, the
    refusal is recorded, and the section is provisioned: SPEC §7.3 makes a section
    with no roster a *state* — "the admin console shows it as never-synced …
    rather than as empty" — and refusing the launch would take a real course out of
    the product over a URL.

    The refusal's own message says "registration", because that is the column set
    the rules were written for and the message is not this module's to reword; the
    log line beside it says which address was actually refused.
    """
    if address is None:
        return None
    try:
        refuse_invalid_fetched_address(settings.environment, column=column, address=address)
    except RegistrationAddressError as refusal:
        logger.warning(
            "%s: the %s address this launch advertised is one this container will not fetch. %s",
            refused.value,
            service,
            refusal,
        )
        _record_defect(session, claims, refused)
        return None
    return address


def _roster_address(claims: Mapping[str, Any]) -> str | None:
    """The roster service address this launch advertises, if it advertises one.

    SPEC §7.3: "The roster service address arrives as a claim on that launch and is
    **stored**, which is what gives the scheduled job the discovery it otherwise
    lacks." Read out of the claim rather than built from the issuer and a guessed
    path: an address this tool assembled is one no platform published.
    """
    service = claims.get(NRPS_CLAIM)
    address = service.get(MEMBERSHIPS_URL_MEMBER) if isinstance(service, Mapping) else None
    return address if isinstance(address, str) and address else None


def _gradebook_address(claims: Mapping[str, Any]) -> str | None:
    """The AGS line-item container this launch advertises, if it advertises one.

    SPEC §3.4 gives every section one line item called "Pulse Participation", and a
    line item is created *in a container* — the `lineitems` member of the AGS
    endpoint claim is the only thing that says where that container is. Read out of
    the claim rather than built from the issuer and a guessed path, for the reason
    `_roster_address` above gives: an address this tool assembled is one no platform
    published, and a guessed one points a scored post at whatever the guess hit.

    **`None` covers both shapes of absence.** A platform that grants this tool no
    gradebook scope sends no endpoint claim at all; one that sends the claim for its
    scopes alone sends no `lineitems` member. Neither is a fault and neither is
    distinguishable from the other in anything this tool goes on to do, so both
    answer the same way and neither records anything.
    """
    endpoint = claims.get(AGS_CLAIM)
    address = endpoint.get(LINE_ITEMS_MEMBER) if isinstance(endpoint, Mapping) else None
    return address if isinstance(address, str) and address else None


# ---------------------------------------------------------------------------
# The two writes.
# ---------------------------------------------------------------------------


def _upsert_course(
    session: Session, prefix_id: UUID, label: ContextLabel, platform_title: str | None
) -> Course | None:
    """Find or create the course this label names, and correct its title if it needs it.

    Keyed on `(prefix_id, lms_number)`, which is the course's identity in SPEC §8
    and the unique constraint the schema already holds. `None` is answered when a
    concurrent launch of the same never-before-seen course is mid-flight; see
    `_tolerating_a_row_that_is_already_there`.

    **The title has an owner and a marker** (ADR 0091). §2.1 makes the title the
    LMS's, so a platform-supplied title is stored as sent and a changed one
    replaces what is stored — the institution renamed the course, and a tool
    showing the old name is showing something retired. When a context carries no
    title, `course.lms_title` is NOT NULL and something has to be written, so
    "PREFIX NUMBER" is written and `title_is_fallback` records that Pulse made it
    up. That marker is what makes the two corrections asymmetric: a real title
    replaces a fallback, and a fallback never replaces a real title.

    A refusal is logged here, where the table it is about is known, and travels to
    the savepoint in `_ingest_the_context`, which is the only frame holding
    anything to undo.
    """
    try:
        guard_write(table="course", sanction=SANCTION)
    except LmsOwnedWriteRefused as refusal:
        _log_a_refused_write("course", refusal)
        raise
    course = _course_row(session, prefix_id, label.number)
    if course is None:
        with _tolerating_a_row_that_is_already_there(session, "the course this launch names"):
            session.add(
                Course(
                    prefix_id=prefix_id,
                    lms_number=label.number,
                    lms_title=platform_title or _fallback_title(label),
                    title_is_fallback=platform_title is None,
                )
            )
            session.flush()
        return _course_row(session, prefix_id, label.number)

    if platform_title is not None and platform_title != course.lms_title:
        course.lms_title = platform_title
    if platform_title is not None and course.title_is_fallback:
        course.title_is_fallback = False
    session.flush()
    return course


def _course_row(session: Session, prefix_id: UUID, number: str) -> Course | None:
    """The course one prefix holds under one number, if it holds one."""
    return session.scalars(
        select(Course).where(Course.prefix_id == prefix_id, Course.lms_number == number)
    ).one_or_none()


def _fallback_title(label: ContextLabel) -> str:
    """The title stored when the platform states none: "BIOL 215".

    Todd's ruling, 2026-08-26 — the label's prefix and number, spelled the way SPEC
    §2.1 spells a course throughout. It is a placeholder that reads as a course
    name rather than as an error, and `title_is_fallback` is what says it is one.
    """
    return f"{label.prefix} {label.number}"


def _upsert_section(
    session: Session,
    course: Course,
    term: Term,
    label: ContextLabel,
    *,
    binding: ContextBinding,
    address: str | None,
    gradebook_address: str | None,
    section: Section | None,
) -> None:
    """Update the section this context is bound to, or create it with the binding stamped.

    `section` is what `_ingest_the_context` resolved by the binding, and it has
    already been checked against what the label names — so by the time this runs,
    "found" means *this context's own section* rather than a row that happens to
    share a name. That check is deliberately not repeated here: two places
    deciding one identity is two places to disagree.

    The insert still carries `(course_id, term_id, lms_section_code)` as before,
    because that is what a section is *called* and it is still unique; what
    changed in round 3 is that it is no longer what a section is looked up by.

    **The calendar comes from `apply_section_code` and from nothing here** (ADR
    0021). Its refusals travel out of this function as `SectionCodeError` and reach
    the caller, which writes the defect and leaves both rows unwritten.

    **The binding is stamped once, at insert, and never revised.** The application
    role holds no `UPDATE` on either column, so a writer that tried would be
    refused by Postgres as well as by this rule — a connection able to repoint
    `lms_context_id` reaches round 3's finding through the database instead of
    through this module.

    **The two service addresses are stored on a staff launch and never cleared.** A
    staff launch carrying no NRPS or AGS claim, or one whose address this container
    will not fetch, leaves whatever is there: a platform that stops advertising a
    service has not moved the roster or the gradebook, and a section with no address
    at all is §7.3's never-synced state rather than an error. E3-02's gradebook
    address is the roster address's exact mirror in every line of this — same
    trigger, same writer, same "changed means the platform moved it" rule.

    **`ags_line_item_url` is written nowhere here**, and it is not an omission: the
    column holds the id of a line item a launch has not created, `app.lti.ags`
    creates it, and `app.services.grading.ensure_line_item` is its only writer —
    on a worker, after the launch, under its own sanction (ADR 0136).

    **That separation is this module's own from E3-05 on**, and it is worth saying
    plainly because it used to be the database's: the application role now holds a
    column-scoped `UPDATE` on `ags_line_item_url`, and `launch_provisioning`'s
    catalog entry already names `section`, so a writer added here would pass both
    controls. What keeps the id out of a launch is that a launch has not made the
    call that produces one.

    A guard refusal is logged here and travels, exactly as `_upsert_course`'s does
    — and it is the case that makes the shared savepoint load-bearing, because by
    this point the course has been written and the two go together or not at all.
    """
    try:
        guard_write(table="section", sanction=SANCTION)
    except LmsOwnedWriteRefused as refusal:
        _log_a_refused_write("section", refusal)
        raise
    if section is None:
        with _tolerating_a_row_that_is_already_there(session, "the section this launch names"):
            session.add(
                apply_section_code(
                    session,
                    Section(
                        course_id=course.id,
                        term_id=term.id,
                        lms_section_code=label.code,
                        lms_context_memberships_url=address,
                        lms_ags_line_items_url=gradebook_address,
                        lti_deployment_id=binding.deployment_id,
                        lms_context_id=binding.context_id,
                    ),
                )
            )
            session.flush()
        return

    corrected = False
    if address is not None and section.lms_context_memberships_url != address:
        section.lms_context_memberships_url = address
        corrected = True
    if gradebook_address is not None and section.lms_ags_line_items_url != gradebook_address:
        section.lms_ags_line_items_url = gradebook_address
        corrected = True
    if corrected:
        session.flush()


def _section_row(session: Session, course_id: UUID, term_id: UUID, code: str) -> Section | None:
    """The section one course holds under one code in one term, if it holds one."""
    return session.scalars(
        select(Section).where(
            Section.course_id == course_id,
            Section.term_id == term_id,
            Section.lms_section_code == code,
        )
    ).one_or_none()


# ---------------------------------------------------------------------------
# The record. One writer, one statement, five fields — and the one refusal that
# gets no record at all.
# ---------------------------------------------------------------------------


def _log_a_refused_write(table: str, refusal: LmsOwnedWriteRefused) -> None:
    """Report that the chokepoint refused this module a write it is sanctioned for.

    **Error level, and no `launch_defect` row.** Every defect kind is a fact
    about a launch's *context* — a label nobody can parse, a prefix the org does
    not hold — and this is a fact about this project's own code: the catalog in
    `app.services.authz` and the write sites in this module disagree about what
    `launch_provisioning` may write. Recording it as a defect would put a
    deployment's bug on the surface E11 builds for data quality, under a kind the
    closed enum does not have and should not grow. So the log line is the whole of
    the visibility, and it is not optional — a refusal this module swallowed in
    silence would leave provisioning quietly doing nothing
    (`docs/MISTAKES.md` entry 26).

    **It names the writer and the table and nothing else.** SPEC §10 keeps personal
    information out of what gets written down, and there is none here to keep out:
    the refusal's own message is built from the table name and static prose, and
    nothing about the launching person reaches this line.
    """
    logger.error(
        "The chokepoint refused the sanctioned writer %r its write to %r: %s",
        SANCTION.writer,
        table,
        refusal,
    )


def _record_defect(session: Session, claims: Mapping[str, Any], kind: LaunchDefectKind) -> None:
    """Write down that this launch's context could not be ingested, and what refused it.

    **The one place a defect is written**, so that the field set is decided once
    and every refusal above is one line. SPEC §10 keeps personal information out of
    what gets written down, and the omissions are the design: no `sub`, which E1-01
    keeps out of every view and which every response in the product is keyed to; no
    name, no email address, no claims payload, which carries both. What is here is
    a fact about a course — which platform, which deployment, which context, and
    which rule fired.

    **A bare `INSERT`, with the key generated here.** The application role holds
    `INSERT` on this table and no `SELECT`, and Postgres checks the columns an
    `INSERT ... RETURNING` returns against the reader's privileges — so letting
    SQLAlchemy fetch the server-generated key would be refused, on a launch that
    was otherwise fine. `app.lti.replay_guard.claim_nonce` supplies its key for the
    identical reason.

    The log line carries the kind and nothing more, which is strictly less than the
    row it is about.
    """
    logger.warning("%s", kind.value)
    session.execute(
        insert(LaunchDefect.__table__).values(  # type: ignore[arg-type]
            id=uuid4(),
            kind=kind,
            issuer=claims.get("iss"),
            deployment_id=claims.get(DEPLOYMENT_ID_CLAIM),
            context_id=_context(claims).get(CONTEXT_ID_MEMBER),
        )
    )


@contextmanager
def _tolerating_a_row_that_is_already_there(session: Session, what: str) -> Iterator[None]:
    """Let a duplicate-key failure inside this block mean "the row this launch wanted exists".

    Two situations, one rule. The launching subject's `user` row is inserted
    without looking first, so every launch after somebody's first collides with the
    row their first launch wrote — the ordinary case, and the constraint is what
    makes the insert idempotent. And two staff launches of the same
    never-before-seen section arriving together both read no row and both insert
    one, so the second collides with the first. Neither is a defect in a launch or
    a fact about a course: the row this launch wanted is there, which is the
    outcome. Without this the second person's launch would answer 500, which is the
    one thing provisioning may never cause.

    A savepoint rather than the whole transaction, because a failed statement
    aborts a Postgres transaction outright: without one, the launch's own commit
    would fail too and a returning person's launch would take the nonce claim with
    it.

    Only a constraint violation is tolerated. Anything else travels, because a
    writer that swallowed its own failures would be indistinguishable from one
    that had nothing to do.
    """
    savepoint = session.begin_nested()
    try:
        yield
    except IntegrityError:
        savepoint.rollback()
        logger.info("%s was already there.", what)
    else:
        savepoint.commit()
