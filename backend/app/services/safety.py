"""The Care queue, and the only connection in this application that can reach identity.

SPEC §6.2 gives this queue to the Care role "and only the Care role: comment
content and identity access are visible to no other role, including Admin and the
VPAA". §13 names this module for it. E0-10 builds the door and E10 builds the
queue behind it — the case model, the two actions, the disposition note — so what
is here is the connection, the check, and the one call.

**The pool is bound to this module, not to the person asking.** §2.1 permits one
person to hold a Care assignment *and* a reporting assignment — a Care staffer
who also teaches — so "pick the pool from the actor's role" has no answer for
them, and the answer it invents is the expensive one. The rule is that the code
path decides: their instructor requests run on `pulse_app`, which holds no
privilege on `public.user_identity` and cannot execute the reveal, however many
hats they hold. Nothing outside this module obtains a Care session, and
`tests/unit/test_care_session_is_bound_to_the_care_service.py` sweeps every module
under `app/` for one that does.

**The actor is checked twice, in two places, and that is the design.**
`reveal_identity` verifies the actor holds a live `CARE` assignment before it
calls anything, and `public.reveal_student_identity` verifies the same thing for
itself. Neither alone:

* the check here catches a **routing** mistake — a request that reached the Care
  service with an actor who is not Care staff is refused before a `SECURITY
  DEFINER` function is entered at all, so no audit row is written for an access
  that was never going to happen, and the caller gets an error naming the reason;
* the check in the function catches **everything that did not come through
  here** — a psql session on the Care credential, a future module that acquires a
  session some other way, a bug in this file. That is the half that has to hold
  when this one is bypassed, and it is asserted against the database with no
  service in the picture.

**The engine is built on first use, and the configuration is validated at
import.** `Settings` requires `CARE_DATABASE_URL`, so a deployment missing it
fails when `app.db` is imported — at start-up, in every process, loudly. What is
deferred is only the socket: `worker` and `beat` never serve this queue, and a
pool they never check out is a pool they should not open. ADR 0006 left the
lifetime question open per entry point and ADR 0042 answers it for this one.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cache
from uuid import UUID

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models.identity import AssignmentRole

__all__ = ["NotCareStaffError", "RevealedIdentity", "reveal_identity"]

# Whether this person holds an assignment in the Care role at all. E0-09's
# `role_assignment` carries no validity dates, so "live" reads as "exists" today:
# a revoked assignment is a deleted row. When E9 or E10 adds end-dating this
# predicate gains it, and so does the copy inside
# `public.reveal_student_identity` — they are two statements of one rule and they
# move together (`docs/MISTAKES.md` entry 13).
_HOLDS_A_LIVE_CARE_ASSIGNMENT = text(
    "SELECT EXISTS ("
    " SELECT 1 FROM public.role_assignment AS acting"
    " WHERE acting.person_id = :actor_person_id"
    " AND acting.role = CAST(:care AS public.assignment_role)"
    ")"
)

# The reveal. `SELECT * FROM` a set-returning function rather than
# `SELECT reveal(...)`, so the two output columns arrive as columns rather than
# as one composite value to take apart here.
_REVEAL = text(
    "SELECT identity_name, identity_email"
    " FROM public.reveal_student_identity("
    " :actor_person_id, :subject_user_id, :case_id)"
)


class NotCareStaffError(Exception):
    """The acting person holds no live `CARE` assignment, so nothing was revealed.

    Raised rather than returning nothing, and the difference matters at the
    surface: an empty result is indistinguishable from a student who does not
    exist, and §6.2's queue has to tell a Care staffer which of those happened.
    Carries the actor's key and never the subject's identity — an exception
    message is the most-copied string in an incident.
    """


@dataclass(frozen=True, slots=True)
class RevealedIdentity:
    """Who a student is, as §6.2's reveal action returns them.

    `identity_email` is optional because NRPS exposes an address only where the
    platform is configured to release one, so `user_identity.identity_email` is
    nullable and a reveal can legitimately return a name and no address.
    """

    identity_name: str
    identity_email: str | None


@cache
def _care_engine() -> Engine:
    """The `pulse_care` engine, built once, on first use.

    Private, and the leading underscore is doing work: this is the only object in
    the application that can execute the reveal, and nothing outside this module
    may hold it. `@cache` rather than a module-level assignment so that importing
    this module opens no socket — see the note on lifetime in the module
    docstring.
    """
    settings = Settings()
    return create_engine(
        # The explicit act ADR 0008's `SecretStr` choice exists to make
        # searchable. It goes no further than this call: the URL lives inside the
        # engine, whose own `repr` masks the password.
        settings.care_database_url.get_secret_value(),
        # Same reasoning as `app.db`: a pooled connection can be dead before it
        # is handed out, and this pool is checked out rarely enough that an idle
        # socket dropped by the network is the ordinary case rather than the rare
        # one.
        pool_pre_ping=True,
    )


@cache
def _care_sessions() -> sessionmaker[Session]:
    """The factory, not a session. One unit of work per reveal."""
    return sessionmaker(bind=_care_engine())


@contextmanager
def _care_session() -> Iterator[Session]:
    """One Care session, closed when the block ends.

    Not exported, and not a FastAPI dependency. A dependency is something a
    router can ask for, and a router that can ask for this is a router that
    chooses its own pool — which E0-10 forbids in as many words: "A caller can
    never choose its own pool, and no general-purpose helper hands out a
    `pulse_care` session."
    """
    with _care_sessions()() as session:
        yield session


def reveal_identity(
    *,
    actor_person_id: UUID,
    subject_user_id: UUID,
    case_id: UUID | None = None,
) -> RevealedIdentity | None:
    """Reveal one student's identity to one Care staff member, and record that it happened.

    Answers `None` where the student has no identity row — an LMS user Pulse has
    seen but whose name never arrived over NRPS — which is a different answer from
    a refusal and is why `NotCareStaffError` is raised rather than returned.

    The audit row is written inside the function, in the transaction this commits,
    so the read and the record cannot come apart (ADR 0001). A failure anywhere
    after the reveal discards both.

    `case_id` is optional and defaults to nothing because there is no case model
    until E10; §4 asks for "actor, timestamp, and case" and the column is there
    waiting for it.
    """
    with _care_session() as session:
        holds_care = session.execute(
            _HOLDS_A_LIVE_CARE_ASSIGNMENT,
            {"actor_person_id": actor_person_id, "care": AssignmentRole.CARE.value},
        ).scalar_one()
        if not holds_care:
            raise NotCareStaffError(
                f"{actor_person_id} holds no live CARE assignment, so no identity was "
                "revealed. Re-identification is possible only through the Care queue and "
                "only by the Care role (SPEC 4, 6.2)."
            )

        revealed = session.execute(
            _REVEAL,
            {
                "actor_person_id": actor_person_id,
                "subject_user_id": subject_user_id,
                "case_id": case_id,
            },
        ).one_or_none()
        session.commit()

    if revealed is None:
        return None
    return RevealedIdentity(
        identity_name=revealed.identity_name, identity_email=revealed.identity_email
    )
