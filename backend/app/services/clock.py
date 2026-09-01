"""What time it is, for everything this product schedules — E2-04.

SPEC §3.1 makes every moment in Pulse a moment in the institution's timezone: a
survey window opens Friday 18:00 and closes Sunday 23:59:59 there, a section's
term is decided by the day a launch arrives, and an enrollment is live on a day
rather than at an instant. Those readings used to be direct
`datetime.now(...)` calls scattered across three services. They come through
here now, and E2-06's window logic is written against this module from the start.

**Two functions, because the codebase asks two questions.** `now` is the current
instant in UTC and `today` is the current date in `settings.institution_timezone`.
`today` is derived from `now` rather than reading the clock a second time, so an
override moves both or neither.

**The override is an offset, not a freeze.** In development, and only there, a
`clock_override` row carries an instant a developer typed (`pretend_now`) and the
real instant they typed it at (`anchored_at`). The effective now is
`real + (pretend_now - anchored_at)`, so the clock keeps running from wherever it
was moved to: a stack pushed to Friday 18:00 reaches Sunday 23:59:59 on its own,
and a window opened by hand still closes. A freeze — storing an instant and
answering it — would make the whole feature useless for the thing it exists for.

**Outside development the row is dead weight, and the gate is here.** Nothing in
the schema marks a `clock_override` row as development-only, so a deployment that
acquired one — a restored dump, a copied database — must go on reading the real
clock. `is_development(settings)` is checked before the table is read at all, so
on a deployment this module issues no statement and answers `datetime.now(UTC)`.

**Which clocks do *not* come through here** is a decision, not an omission, and
`docs/adr/0109-the-dev-clock-is-a-database-offset-not-a-freeze.md` carries the
whole list: launch validation (nonce and state expiry, token `exp`, clock skew),
session expiry, audit timestamps, `func.now()` column defaults, the NRPS debounce
window and call log, and Celery beat's own firing schedule. Those are protocol and
observability instants; a movable clock on any of them would open the replay
window E1 closed, or would refuse every honest launch the moment a developer moved
the clock. The rule for a reviewer is short: **a new direct `datetime.now` in
scheduling or visibility code is the thing to ask about.**

**A module of its own under `services/`, and §13's list names none that fits.**
Time is cross-cutting — provisioning, the roster sync and `authz` all read it
today, and E2-06's scheduling will — so it belongs to no one of them, and putting
it inside any would make the other two import a peer service for a question that
has nothing to do with that peer's subject.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, is_development
from app.models.clock import ClockOverride


def now(session: Session, *, settings: Settings) -> datetime:
    """The effective current instant, timezone-aware and in UTC.

    Real time, unless this is a developer's machine carrying an override row, in
    which case the difference between the pretended instant and the instant it was
    anchored at is added to real time.

    The environment is checked before the query, so a deployment never reads the
    table: the gate is cheaper, and a deployment holding a stray row issues no
    statement about it at all.
    """
    real = datetime.now(UTC)
    if not is_development(settings):
        return real
    override = session.scalars(select(ClockOverride)).first()
    if override is None:
        return real
    return real + (override.pretend_now - override.anchored_at)


def today(session: Session, *, settings: Settings) -> date:
    """The effective date, in the institution's own timezone.

    **The institution's day, never UTC's and never the server's.** SPEC §3.1 puts
    every window at a wall-clock time in that zone and §8 makes the zone a
    deployment-level setting, so which day a launch, a roster sync or an
    enrollment window belongs to is a fact about the institution's calendar. A
    reading in UTC puts everybody who launches in the evening a calendar day out.
    """
    return (
        now(session, settings=settings).astimezone(ZoneInfo(settings.institution_timezone)).date()
    )
