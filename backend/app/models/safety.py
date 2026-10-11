"""SPEC §6.2's threat and self-harm path: the row a Care case opens with (E6-01).

A comment holding a threat or self-harm moderation verdict is withheld from every
instructor and leadership view (`report_comment` v004) and routed to Care. This
module holds the record of that routing, `threat_case`: one row per comment,
written by the routing definer `public.route_moderation_verdict` in the same call
that writes the verdict (`views_sql/moderation_routing_v001.sql`, ADR 0187). A
threat verdict therefore never exists without its case.

**The opening row only.** Who works a case, its states and its closing are E10's
Care queue to design; the columns for them arrive with that queue. Until it
exists nothing reads this table, and the owner ruled on 2026-10-09 that no
deployment reaches real students before it does (SPEC §12, ADR 0187).

**`pulse_app` holds no privilege on this table of any kind**, so the connection
every instructor screen runs on cannot even count the cases. The definer's owner,
`pulse_moderation_definer`, is the only role that inserts here.

Written in the `models/report.py` style: `RESTRICT` foreign keys, a server-side
instant, and `UuidPrimaryKey`. `Base` comes from `app.models.base`, never from
`app.db`, for the reason that module gives.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AwareDateTime, Base, UuidPrimaryKey


class ThreatCase(UuidPrimaryKey, Base):
    """One comment routed to Care, and the moderation verdict that routed it.

    **Unique per comment.** A second threat or self-harm verdict on a comment that
    already has a case leaves that case alone: the definer inserts with
    `ON CONFLICT (answer_id) DO NOTHING`, so a re-run of moderation neither fails
    nor opens a second case that would show one student twice in E10's queue.
    """

    __tablename__ = "threat_case"

    # The comment. `RESTRICT`, like every foreign key on the survey tables: a case
    # is not removed by removing something else.
    answer_id: Mapped[UUID] = mapped_column(
        ForeignKey("answer.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    # The `MODERATION` classification row that opened the case. Indexed for the
    # foreign key; the read E10 will make is by case, and this answers "which
    # verdict" without a search.
    classification_id: Mapped[UUID] = mapped_column(
        ForeignKey("classification.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # When the case was opened, by the server, in the definer's transaction.
    opened_at: Mapped[datetime] = mapped_column(
        AwareDateTime, nullable=False, server_default=text("now()")
    )
