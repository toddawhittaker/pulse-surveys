"""The sessions that ended before their tokens expired — E9-04, ADR 0202.

A session is a signed token that verifies until its `exp` (ADR 0089,
`app.services.session`). Until E9-04 nothing could end one sooner. The role
switch and logout both have to, so this table holds the `jti` of every session
that was ended early, until the token would have expired anyway. After that the
signature check refuses the token on its own and the row is dead weight, which
`app.services.session.revoke_session` deletes as it writes.

**A module of its own, beside nothing else.** The table belongs to the session
both doors issue, so it is neither `lti` (the launch door's records) nor
`identity` (who a person is and what they hold). It holds no person: a `jti` is
a random value `issue_session` mints, and nothing joins it to anybody. So
`PERSON_TABLES` does not change and no identity-separated view is owed.
"""

from datetime import datetime

from sqlalchemy import Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AwareDateTime, Base


class RevokedSession(Base):
    """One session ended before its token expired, held until that expiry.

    **The `jti` is the primary key**, because it is the whole of what a read
    asks ("is this session revoked?") and because a second revocation of the
    same session is an insert that does nothing on conflict: a second logout
    with the same token answers the same as the first.

    **`expires_at` is the token's own `exp`**, not the moment of revocation and
    not a fixed horizon. A row is needed exactly as long as the token would
    otherwise verify, and no longer.

    **`pulse_app` holds SELECT, INSERT and DELETE** (`revoked_session_grants_v001.sql`):
    SELECT for the check every gated request makes, INSERT for the switch and
    logout, DELETE for the purge. UPDATE is withheld: a revocation is never
    edited, and an `expires_at` moved earlier would bring an ended session back.
    """

    __tablename__ = "revoked_session"

    jti: Mapped[str] = mapped_column(Text, primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(
        AwareDateTime, nullable=False, server_default=text("now()")
    )
