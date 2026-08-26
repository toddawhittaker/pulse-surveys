"""Single-use launch nonces, enforced in Postgres — ticket E1-08.

A launch nonce is spent exactly once. Replaying a whole signed `id_token` a
second time is the replay attack SPEC §9.1 names: the signature, issuer,
audience and clock are all still valid on the second delivery, so nothing the
signature-and-claims path checks can tell it from the first. The only thing that
can is a record of which nonces this tool has already honoured, and that record
is `lti_launch_nonce`.

**`INSERT ... ON CONFLICT (nonce) DO NOTHING`, and the row count is the verdict.**
The unique index on `nonce` makes the second insert a no-op rather than an error,
and a no-op inserts zero rows — so `claim_nonce` needs no `SELECT` at all: it
inserts, and if nothing was inserted the nonce was already spent. That is atomic
against two launches racing the same nonce, because the database, not this
process, decides which insert wins.

**Claimed only after every other check has passed** (`app.lti.launch`). A nonce
spent by a launch that was then refused for a bad signature would refuse the
legitimate retry, so the claim is the last thing a launch does before it is
admitted, and it rides inside the launch's own `Session` — it commits with the
session it belongs to or rolls back with it.

Its only caller is `app.lti.launch`; `purge_expired_nonces` is called by a daily
Celery beat task (`app.tasks`), which is what replaces Redis's native TTL now
that the ledger lives in Postgres (ADR 0089).
"""

from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.lti import LtiLaunchNonce

__all__ = ["NonceReplayedError", "claim_nonce", "purge_expired_nonces"]


class NonceReplayedError(Exception):
    """The nonce this launch carries has already been spent by an earlier launch.

    Raised by `claim_nonce` on the `ON CONFLICT` no-op. Carries no claim value
    and no part of any token — like every launch refusal, it reaches a log line
    and a page, and a nonce is part of a credential (SPEC §10). The launch door
    translates it into a claim-free refusal and logs only this class's name.
    """


def claim_nonce(session: Session, *, nonce: str, expires_at: datetime) -> None:
    """Spend `nonce` once, or raise `NonceReplayedError` if it was already spent.

    Inserts the nonce and lets the unique index decide: a first claim inserts one
    row, a replay inserts none. No `SELECT` is issued and none is needed — the
    conflict *is* the answer — which is why `pulse_app` holds `INSERT` on this
    table and not `SELECT`.

    The write is left uncommitted: it belongs to the caller's `Session` and
    commits with the rest of the launch, so a launch that fails after the claim
    for an unrelated reason leaves the nonce unspent and the legitimate retry
    open.
    """
    statement = (
        insert(LtiLaunchNonce)
        .values(nonce=nonce, expires_at=expires_at)
        .on_conflict_do_nothing(index_elements=["nonce"])
        .returning(LtiLaunchNonce.id)
    )
    # A first claim returns the new row's id; a replay conflicts, inserts
    # nothing, and returns no row. `rowcount` is unreliable once `RETURNING` is
    # present, so the presence of a returned row is the verdict.
    if session.execute(statement).first() is None:
        raise NonceReplayedError(
            "This launch has already been delivered once. A launch nonce is single-use, and "
            "presenting the same signed launch a second time is refused."
        )


def purge_expired_nonces(session: Session, *, now: datetime) -> int:
    """Delete every claimed nonce whose lifetime has passed, and return the count.

    The daily replacement for a native TTL. A spent nonce is only worth keeping
    for as long as the launch that spent it could still be replayed — its own
    `expires_at` — after which the row is dead weight. Deletes on the
    `expires_at` index rather than scanning, and the caller commits.
    """
    result = session.execute(delete(LtiLaunchNonce).where(LtiLaunchNonce.expires_at < now))
    return result.rowcount or 0
