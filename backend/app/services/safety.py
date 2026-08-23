"""The Care queue, and the only connection in this application that can reach identity.

SPEC §6.2 gives this queue to the Care role "and only the Care role: comment
content and identity access are visible to no other role, including Admin and the
VPAA". §13 names this module for it. E0-10 builds the door and E10 builds the
queue behind it — the case model, the two actions, the disposition note — so what
is here is the connection, the check, and the one entry point.

**The pool is bound to this module, not to the person asking.** §2.1 permits one
person to hold a Care assignment *and* a reporting assignment — a Care staffer
who also teaches — so "pick the pool from the actor's role" has no answer for
them, and the answer it invents is the expensive one. The rule is that the code
path decides: their instructor requests run on `pulse_app`, which holds no
privilege on `public.user_identity` and cannot execute the reveal, however many
hats they hold. Nothing outside this module obtains a Care session, and
`tests/unit/test_care_session_is_bound_to_the_care_service.py` sweeps every module
under `app/` for one that does.

**The door is two calls, and `reveal_identity` is still one.** E0-26 item 1
split `public.reveal_student_identity` in two: `public.record_identity_reveal`
writes the `audit_log` row and hands back its id, and the reveal takes that id
and answers only where the record's writing transaction has **committed**. So a
caller that rolls back keeps no name — the rollback destroys the record, and
without a committed record the second call raises. What this module does with
that is record, commit, and then reveal in a second transaction. §6.2 asks for
"a plain, one-click procedural action", which is about what Care staff do rather
than about how many statements the service sends, so `reveal_identity` keeps its
signature and its single call.

**The actor is checked three times, in three places, and that is the design.**
`reveal_identity` verifies the actor holds a live `CARE` assignment before it
calls anything; `public.record_identity_reveal` verifies the actor it is handed;
and `public.reveal_student_identity` verifies the actor named by the record it is
spending. None alone:

* the check here catches a **routing** mistake — a request that reached the Care
  service with an actor who is not Care staff is refused before a `SECURITY
  DEFINER` function is entered at all, so no audit row is written for an access
  that was never going to happen, and the caller gets an error naming the reason;
* the check in `record_identity_reveal` catches **everything that did not come
  through here** — a psql session on the Care credential, a future module that
  acquires a session some other way, a bug in this file. That is the half that
  has to hold when this one is bypassed, and it is asserted against the database
  with no service in the picture;
* the check in the reveal catches a **stale** record. Without it a committed
  record would be a bearer token: written while its actor held `CARE`, spent
  after the assignment was revoked.

**The configuration decides which process can reveal at all.**
`CARE_DATABASE_URL` is optional in `Settings`, and its absence is the ordinary
state rather than a misconfiguration: `docker-compose.yml` gives it to `api` and
blanks it on `worker` and `beat`, so the one credential that can execute the
reveal reaches only the process that serves this queue. `worker` is also the
process that ships comment text to a third-party model provider, which is why it
is the last container that should hold a route to a name.

So a process without the variable does not fail at import — it fails at the
call, in `_care_engine`, naming the variable and saying that only the API process
is configured to serve the Care queue. That is a deliberate move of the failure
from start-up to first use, and ADR 0042's amendment records why the trade
changed. The engine itself is still built on first use behind `functools.cache`,
so importing this module opens no socket; ADR 0006 left the lifetime question
open per entry point and ADR 0042 answers it for this one.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cache
from uuid import UUID

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import engine_options
from app.models.identity import AssignmentRole

__all__ = [
    "CareQueueNotConfiguredError",
    "NotCareStaffError",
    "RevealedIdentity",
    "reveal_identity",
]

# Whether this person holds an assignment in the Care role at all. E0-09's
# `role_assignment` carries no validity dates, so "live" reads as "exists" today:
# a revoked assignment is a deleted row. This predicate is checked four times,
# and this is the one place that names all four: this module's own
# `_HOLDS_A_LIVE_CARE_ASSIGNMENT` below; `app.services.authz.holds_care` /
# `_HOLDS_A_LIVE_CARE_ASSIGNMENT`, which reads the same fact from
# `public.assignment_scope` on the `pulse_app` pool for `authz`'s own callers;
# and the SQL copies inside `public.record_identity_reveal` and
# `public.reveal_student_identity`. When E9 or E10 adds end-dating, all four
# gain it together — four statements of one rule, and they move together
# (`docs/MISTAKES.md` entry 13).
_HOLDS_A_LIVE_CARE_ASSIGNMENT = text(
    "SELECT EXISTS ("
    " SELECT 1 FROM public.role_assignment AS acting"
    " WHERE acting.person_id = :actor_person_id"
    " AND acting.role = CAST(:care AS public.assignment_role)"
    ")"
)

# The first half of the door: the record, which the caller must commit before the
# second half will answer. It returns the `audit_log` row's id and nothing else —
# no identity, on any path — so a scalar rather than a row.
_RECORD_THE_REVEAL = text(
    "SELECT public.record_identity_reveal(:actor_person_id, :subject_user_id, :case_id)"
)

# The second half. `SELECT * FROM` a set-returning function rather than
# `SELECT reveal(...)`, so the two output columns arrive as columns rather than
# as one composite value to take apart here. It takes the record's id and nothing
# else, so the subject is read from the committed record and this module cannot
# substitute one.
_REVEAL = text(
    "SELECT identity_name, identity_email FROM public.reveal_student_identity(:reveal_id)"
)


class CareQueueNotConfiguredError(Exception):
    """This process holds no Care credential, so it cannot reveal anything.

    Not a defect on its own: `worker` and `beat` are configured this way on
    purpose, and reaching this means a reveal was attempted somewhere that was
    never meant to serve the Care queue. Raised rather than allowed to become a
    `None` inside `create_engine`, which answers `ArgumentError: Expected string
    or URL object, got None` — measured on the pinned SQLAlchemy, and it names
    neither the variable nor the reason.
    """


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

    Refuses before it builds anything when the setting is absent or blank. That
    is the state `worker` and `beat` are deliberately in, so the message says
    which variable is missing and which process is meant to hold it, rather than
    letting a `None` reach `create_engine` and come back as an argument error
    about a URL.
    """
    settings = Settings()
    care_database_url = settings.care_database_url
    if care_database_url is None:
        raise CareQueueNotConfiguredError(
            "CARE_DATABASE_URL is not set in this process, so no Care connection can be "
            "opened and nothing was revealed. Only the API process is configured to serve "
            "the Care queue: docker-compose.yml gives it this credential and blanks it on "
            "`worker` and `beat`, because it is the one credential in the cluster that can "
            "execute public.reveal_student_identity (SPEC 6.2, ADR 0042). If a reveal is "
            "genuinely reaching this process, the routing is wrong — do not set the "
            "variable here to make the error go away."
        )
    return create_engine(
        # The explicit act ADR 0008's `SecretStr` choice exists to make
        # searchable. It goes no further than this call: the URL lives inside the
        # engine, whose own `repr` masks the password.
        care_database_url.get_secret_value(),
        # The same options `app.db` builds its engine with, from the same
        # function, so that one place decides what either connection may write to
        # a log. `engine_options` already carries `pool_pre_ping=True`; the
        # sharper reason it is routed through here is `hide_parameters=True`
        # outside development. The security review of Batch H found this engine
        # built with `pool_pre_ping` alone, so with `sqlalchemy.engine` configured
        # at INFO by name it logged every bound parameter — and the parameters on
        # this connection are a reveal's arguments and the rows are the identity
        # itself (SPEC §4.1, §6.2, §10).
        **engine_options(settings),
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

    **Three statements and two transactions, and the order is the guarantee.**
    The record is written and *committed* first, and only then is identity read,
    in a second transaction against the committed record. So there is no state in
    which this returns a name that is not already recorded: a failure anywhere
    after the commit — the reveal raising, the connection dropping, this process
    being killed — leaves the record standing and hands back nothing.

    That is the safe direction and it is not free: a record committed here for
    a reveal that then fails is a row saying an access was authorised when no
    name was read, and §6.2's periodic review outside the Care office reads it as
    an access. The log errs the other way too, which is the direction §4 forbids:
    nothing limits a committed record to a single spend, so one row can stand
    behind several reads of the same subject's name. ADR 0071 argues both, and
    the re-spend half is E10's.

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

        reveal_id = session.execute(
            _RECORD_THE_REVEAL,
            {
                "actor_person_id": actor_person_id,
                "subject_user_id": subject_user_id,
                "case_id": case_id,
            },
        ).scalar_one()
        # The commit the whole ticket is about. Until it returns, the record is
        # this transaction's to discard and `public.reveal_student_identity` will
        # refuse to answer against it.
        session.commit()

        revealed = session.execute(_REVEAL, {"reveal_id": reveal_id}).one_or_none()
        session.commit()

    if revealed is None:
        return None
    return RevealedIdentity(
        identity_name=revealed.identity_name, identity_email=revealed.identity_email
    )
