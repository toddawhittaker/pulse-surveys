"""Who a verified subject is: where a door turns a token into a row id — E1-12.

SPEC §13 puts domain logic in `services/`, and this is the smallest piece of it
there is: a verified subject comes in, and the primary key of the row this system
stores for that person goes out. It is E1-12's first criterion — "the same stored
identity, one row, by its primary key" — and it is what E1-13 reads assignments
and enrollment through.

**A module of its own, and §13 names none.** Every module in §13's `services/`
list is a screen's worth of domain logic and none of them is this. `authz.py` is
the authorization chokepoint: it answers what a purview covers, and since E1-13
which view a session's own identity opens on; `session.py` signs and verifies the
token a door hands over and touches no database; `provisioning.py` writes what a
launch discovered. Three of those need this answer and none of them owns the
question — putting it in one would have the other doors importing that one's
module for something it does not do. So: a module, because nothing fits, which is
what §13 asks the pull request to say.

**Nothing here reads an identity table, and a sweep holds that**
(`tests/unit/test_no_service_reads_an_identity_table_directly.py`). It could not
anyway: E1-10's round-3 review revoked `SELECT (lms_user_id)` on `user` from
`pulse_app`, because a connection able to read that column can enumerate every
subject that ever launched and join a response back to the person who gave it,
and `pulse_app` holds no privilege on `person` at all. So every lookup below goes
through a `SECURITY DEFINER` function that answers one point question (ADR 0094):
this subject, this row. The connection resolves a subject it already holds from a
token it has verified, and can never enumerate the subjects it does not.

**Three of the four answer a uuid and one answers a subject**, and the asymmetry
is a decision rather than an oversight. `subject_for_user` runs the mechanism
backwards for SPEC §3.4's grade passback, which posts a score keyed by the LTI
`sub` and can key it by nothing else, so it hands a value back where the others
hand an id. **That one gives the enumeration back**: a scalar function is callable
per row inside a `SELECT` and this connection can already list `user.id`, so the
door is as wide as the column was for anyone composing a query. What is kept is
auditability — one inventoried, greppable function with a stated argument (ADR
0139) — and the line at a *name*: `user_identity` and `person.identity_name` stay
unreachable from this connection by every mechanism this scheme has.

**Two doors, two lookups, and deliberately not one clever query.** A launch
reaches a person in two hops — the platform's `sub` to a `user` row, then ADR
0024's `person.user_id` link — and a web login reaches one in a single hop through
the `web_login_subject` linkage. They are separate because the evidence is
separate: a lookup taking a "which door" argument is one edit away from answering
the launch question with the web door's evidence, and SPEC §8 is written against
exactly that economy.

**`None` is a defined answer on every path and never an error.** A student's
launch resolves to a `user` row and no `person` — ADR 0028 gives a student a user
row and no assignment — and the session carries "no person" rather than the door
failing. A web login by a subject nobody has provisioned resolves to no person at
all, and that is the calm no-account page: the identity provider asserts that
somebody authenticated, never that Pulse has a record of them (SPEC §2 puts every
role in Pulse's own records).

**A merge is never inferred from a mutable claim**, which is the constraint the
ticket bounds this decision with. Nothing here reads an email address, a name, or
any claim but the two that identify the token itself. ADR 0097 records the
decision; ADR 0024 rejected the same shape for the person-to-user link, because
"the failure is a purview computed for the wrong person — invisible, because it
produces a plausible answer".
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.lti import LtiPlatform

__all__ = [
    "ResolvedIdentity",
    "identity_behind_a_launch",
    "identity_behind_a_launch_subject",
    "person_behind_a_web_login",
    "subject_for_user",
]

# ADR 0094's point resolvers, called and never joined to. Each takes what the
# caller already holds and answers with one value or NULL, and the inventory of
# what `pulse_app` may execute at all is
# `tests/integration/test_identity_grants.py`'s. `scalar_one` is safe on every
# one of them: a scalar function returns exactly one row, and the value in it may
# be NULL.
#
# The first three answer a uuid and read the subject only to match on it. The
# fourth runs the other way and answers the subject itself (ADR 0139) — the one
# direction that hands a value back rather than an id, and the one whose consequence
# is written out in `identity_resolution_v002.sql` and in that record.
_PLATFORM_USER = text("SELECT public.resolve_platform_user(:lti_platform_id, :lms_user_id)")
_PERSON_FOR_USER = text("SELECT public.resolve_person_for_user(:user_id)")
_WEB_PERSON = text("SELECT public.resolve_web_person(:idp_issuer, :idp_subject)")
_SUBJECT_FOR_USER = text("SELECT public.resolve_subject_for_user(:user_id)")

# The two claims a launch is identified by, and the two an `id_token` is. Both
# doors spell them the same way and neither spelling is this project's: `sub` and
# `iss` are OIDC Core 1.0's, and LTI 1.3 inherits them.
SUBJECT_CLAIM = "sub"
ISSUER_CLAIM = "iss"


@dataclass(frozen=True)
class ResolvedIdentity:
    """What a launch's subject resolves to: a `user` row, and a `person` or none.

    Both halves together rather than two calls, because a door needs both and the
    second is looked up from the first — returning only the person would throw
    away the row SPEC §4 keys every response to, and returning only the user would
    leave every caller making the second hop for itself.

    `person_id` is `None` for a student and for anybody an administrator has not
    put in the people graph yet, which is a state and not a failure. `user_id` is
    `None` only when this launch resolves to no stored subject at all — a
    registration that has gone, or a launch that reached this module without the
    door that writes the row.
    """

    person_id: UUID | None
    user_id: UUID | None


def identity_behind_a_launch(session: Session, claims: Mapping[str, Any]) -> ResolvedIdentity:
    """The stored identity a verified launch's subject reaches, resolved from its claims.

    For a caller holding the launch and nothing else — `app.api.deps` at the
    landing. A caller that already holds the registration row should use
    `identity_behind_a_launch_subject` and skip the lookup below.

    The registration is resolved by the `(issuer, audience)` pair rather than by
    the issuer alone, for the reason `app.services.provisioning` gives: one LMS can
    register this tool twice, and a `sub` is unique per issuer, so the same person
    on two registrations of one platform is two `user` rows.
    """
    subject = claims.get(SUBJECT_CLAIM)
    if not isinstance(subject, str) or not subject:
        return ResolvedIdentity(person_id=None, user_id=None)

    audience = claims.get("aud")
    client_id = audience[0] if isinstance(audience, list) else audience
    platform_id = session.scalars(
        select(LtiPlatform.id).where(
            LtiPlatform.issuer == claims.get(ISSUER_CLAIM), LtiPlatform.client_id == client_id
        )
    ).one_or_none()
    if platform_id is None:
        return ResolvedIdentity(person_id=None, user_id=None)
    return identity_behind_a_launch_subject(session, platform_id=platform_id, subject=subject)


def identity_behind_a_launch_subject(
    session: Session, *, platform_id: UUID, subject: str
) -> ResolvedIdentity:
    """The two hops, for a caller that already knows which registration issued the subject.

    `sub` to a `user` row at that registration, then ADR 0024's `person.user_id`
    link read in the direction a door needs it. The second hop is skipped when the
    first answers nothing: there is no person to look for behind a subject this
    system has never stored.
    """
    user_id = session.execute(
        _PLATFORM_USER, {"lti_platform_id": platform_id, "lms_user_id": subject}
    ).scalar_one()
    if user_id is None:
        return ResolvedIdentity(person_id=None, user_id=None)
    person_id = session.execute(_PERSON_FOR_USER, {"user_id": user_id}).scalar_one()
    return ResolvedIdentity(person_id=person_id, user_id=user_id)


def person_behind_a_web_login(session: Session, claims: Mapping[str, Any]) -> UUID | None:
    """The person a verified `id_token`'s `(issuer, sub)` pair is linked to, or `None`.

    One hop and no fallback. `None` means this system has no record of the person
    the provider signed in, which is the state D5 answers with a calm page — never
    a reason to look for them by some other claim. An address or a name is a value
    the provider's administrator controls and a person can change, and a merge
    inferred from one hands somebody else's purview to whoever holds it next.

    Both halves of the pair are required to be present and non-empty. A token
    missing either is one no conformant provider issued, and matching on a blank
    would make every such token resolve to whichever row was written with a blank.
    """
    issuer = claims.get(ISSUER_CLAIM)
    subject = claims.get(SUBJECT_CLAIM)
    if not isinstance(issuer, str) or not issuer:
        return None
    if not isinstance(subject, str) or not subject:
        return None
    resolved: UUID | None = session.execute(
        _WEB_PERSON, {"idp_issuer": issuer, "idp_subject": subject}
    ).scalar_one()
    return resolved


def subject_for_user(session: Session, user_id: UUID) -> str | None:
    """The platform's own subject for one stored `user` row, or `None` for no such row.

    ADR 0094's mechanism run backwards, and the only caller is SPEC §3.4's grade
    passback (ADR 0139): an AGS Score names its student by the LTI `sub` and by
    nothing else, so a sweep holding a `user` row id has to be able to reach the
    subject that row was created for.

    **What this does and does not contain, stated honestly** (E3-06's security
    round, MEDIUM 1). `pulse_app` holds no `SELECT` on `user.lms_user_id` — E1-10's
    round-3 review revoked it, because a connection able to read it can enumerate
    every subject that ever launched and join a response back to the person who
    gave it — so this goes through a `SECURITY DEFINER` function instead. **That is
    not enumeration resistance.** A scalar function is callable per row inside a
    `SELECT`, so a caller composing its own queries can reach through this door for
    a whole table's worth of subjects as readily as it could have read the column;
    `pulse_app` holds `SELECT (id)` on `user`, which is the enumeration this leaves
    open by construction.

    What the door does buy is two things worth having and worth naming as what they
    are. It is **auditable**: one inventoried function with a signature, an owner, a
    stated argument (ADR 0139) and a name a reviewer can grep, rather than a column
    any join can pick up unremarked. And it holds a hard line at the value: what
    comes back is the pseudonymous identifier the issuing platform assigned, and a
    *name* is refused by every mechanism this scheme has — `user_identity` is
    unreachable from this connection entirely and `person.identity_name` is not
    among the columns this function's owner may read.

    **`None` is a defined answer.** A row can go missing between the moment a
    caller reads an enrollment and the moment it asks for the subject, and the
    sweep steps over that student rather than failing the section it was in the
    middle of. It is never somebody else's subject: the body matches on the
    primary key.
    """
    resolved: str | None = session.execute(_SUBJECT_FOR_USER, {"user_id": user_id}).scalar_one()
    return resolved
