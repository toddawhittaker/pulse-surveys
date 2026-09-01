"""The development clock override: one row, a pretended instant and its anchor.

E2-04. SPEC §3.1 puts every survey window at a wall-clock time in the institution
timezone, and E2 has to be drivable by hand — what a student sees on a Friday
evening has to be visible without waiting for one. `app.services.clock` is the one
place the scheduling and visibility code asks what time it is, and this table is
what a developer moves that answer with.

**A row, not a process setting, and that is the whole reason this is a table.**
The tool and the Celery worker are two processes; an override held in an
environment variable, a module global or a cached offset would move one of them
and leave the other on real time, and the disagreement would only surface when
E2-06 schedules a window in one and reads it in the other. A row is the one place
both already look.

**Two instants, because the override is an offset and never a freeze.**
`pretend_now` is the instant a developer typed and `anchored_at` is the real
instant they typed it at; the service adds the difference to real time on every
read, so time keeps flowing from the point it was set. A single "pretend now"
column would stop the clock where somebody typed it: a window opened that way
never closes, and nothing that depends on elapsed time could be driven by hand at
all.

**A development scaffold, and the environment gate is not here.** Nothing in this
table says which environment it applies in, and no constraint could: the row is
dead weight outside development because `app.services.clock` refuses to read it
there (`app.config.is_development`), which is where the ticket's criterion 3 puts
the gate. A deployment that acquired one of these rows — a restored dump, a copied
database — goes on reading the real clock.

**A module of its own, and §13 names no aggregate for it.** The section list is
the product's domain — the containment hierarchy, the calendar, identity, LTI,
audit, AI — and a development-only time control is none of those. `term.py` is the
nearest neighbour and is the wrong home: it holds the institution's *configured*
calendar, which an administrator sets and the product reads, while this row is a
scaffold a developer sets and no deployment has.
"""

from datetime import datetime

from sqlalchemy import Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AwareDateTime, Base, UuidPrimaryKey


class ClockOverride(UuidPrimaryKey, Base):
    """The pretended instant this stack is running at, and when it was set.

    **At most one row, enforced by a unique index over a constant.** `(true)` is
    the same value in every row, so a second insert collides with the first and
    the error names the index — the shape `institution` uses for the same job
    (`app.models.org.Institution`, ADR 0072, which records the `singleton boolean`
    column measured and rejected). The `/dev` control deletes before it inserts,
    so a developer setting the clock twice replaces the row rather than meeting
    that error; the index is what makes "the single row" a property of the
    database instead of a habit of the one writer.

    The index is named explicitly for the reason `Institution` gives: the `ix`
    template on `Base.metadata` interpolates a column name and a textual
    expression has none to give it, so the model and the migration each spell the
    name and the two have to match.

    **Both columns are `AwareDateTime`** (ADR 0019). An offset is a difference
    between two instants, and a naive value is a different instant on every
    connection — so a pretend now stored without a zone would move the whole
    product by however many hours the reader's session happened to be configured
    for.
    """

    __tablename__ = "clock_override"
    __table_args__ = (Index("uq_clock_override_one_row", text("(true)"), unique=True),)

    pretend_now: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    anchored_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
