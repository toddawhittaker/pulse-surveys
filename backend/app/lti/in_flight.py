"""The server-side memory of a launch handshake in flight — ticket E1-08.

A launch is two requests with nothing shared between them but the browser:
`/lti/login` mints a `state` and a `nonce` and redirects, and `/lti/launch`
receives the platform's signed answer with that `state`. This module is where
the `state` -> `nonce` mapping lives in between — `LtiLaunchState` — and it is
server-side rather than a cookie because the launch runs inside the LMS's
cross-site iframe, where a third-party cookie is blocked whatever its attributes
say (ADR 0089, SPEC §7.3: "no third-party cookie is ever required").

Three operations and a purge:

* `remember_launch` records the mapping at login (its caller commits).
* `look_up_launch` reads the expected `nonce` back at launch, without consuming —
  a successful launch leaves its `state` in place so a *replay of the whole valid
  launch* reaches the nonce ledger (`app.lti.replay_guard`) and is refused there,
  which is where single-use of a spent launch belongs.
* `consume_launch` deletes the row, called on a refusal so that a correct `state`
  replayed after a refusal finds nothing — the burn-after-use the ADR-0078 cookie
  had, as a server-side property.
* `purge_expired_launch_states` reclaims the expired tail on the daily beat.

`pulse_app` holds `SELECT`, `INSERT` and `DELETE` here and no `UPDATE`: a
handshake row is written once and read once, never rewritten.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.models.lti import LtiLaunchState

__all__ = [
    "consume_launch",
    "look_up_launch",
    "purge_expired_launch_states",
    "remember_launch",
]


def remember_launch(session: Session, *, state: str, nonce: str, expires_at: datetime) -> None:
    """Record that this tool started a launch with `state`, expecting `nonce` back.

    The `id` is supplied here rather than left to the column default so the insert
    emits no `RETURNING` (the caller commits the write with the rest of the login).
    """
    session.execute(
        insert(LtiLaunchState.__table__).values(  # type: ignore[arg-type]
            id=uuid4(), state=state, nonce=nonce, expires_at=expires_at
        )
    )


def look_up_launch(session: Session, *, state: str, now: datetime) -> str | None:
    """The `nonce` this tool is expecting for `state`, or `None` if there is none.

    A `None` covers every way a `state` fails to name a launch this tool started
    and has not yet let expire: never issued, tampered, already consumed by a
    refusal, or past its lifetime. Read-only — the row is consumed on a refusal by
    `consume_launch`, not here, so a successful launch leaves it in place.
    """
    row = session.execute(
        select(LtiLaunchState.nonce).where(
            LtiLaunchState.state == state,
            LtiLaunchState.expires_at > now,
        )
    ).first()
    return None if row is None else row[0]


def consume_launch(session: Session, *, state: str) -> None:
    """Delete the in-flight row for `state`, so it cannot be presented again.

    Called on a launch refusal: a `state` is good once, and one left behind is one
    an attacker can retry a different token against. A `state` that names no row
    (a tampered or already-consumed one) deletes nothing, which is the correct
    no-op. The caller commits.
    """
    session.execute(delete(LtiLaunchState).where(LtiLaunchState.state == state))


def purge_expired_launch_states(session: Session, *, now: datetime) -> int:
    """Delete every in-flight launch whose handshake lifetime has passed.

    A launch that never came back leaves a row; the daily purge reclaims it. The
    caller commits.
    """
    result = session.execute(delete(LtiLaunchState).where(LtiLaunchState.expires_at < now))
    return result.rowcount or 0  # type: ignore[attr-defined]
