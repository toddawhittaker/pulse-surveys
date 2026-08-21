"""The append-only record of who reached what, and when (SPEC §4, §6.2, §8).

SPEC §8 names one table for this — `audit_log` — and says it "includes all
re-identifications, exclusions and kept-decisions, policy changes,
response-on-behalf actions, imports (with their dry-run diffs), and admin config
edits". E0-10 needs exactly one of those: §4's "every identity access is
automatically audit-logged with actor, timestamp, and case".

**Only one action can be written today, and the enum says so.** `audit_action`
has a single member, `IDENTITY_REVEAL`, because that is the only thing in this
repository that writes a row here. Each later ticket that logs something adds its
own member in the same change as the code that writes it, so the type is a list
of things that actually happen rather than a forecast — the same reasoning
`AssignmentRole` gives for leaving `STUDENT` out.

**Nothing in the application writes this table, and that is the design.** The row
is written inside `public.record_identity_reveal`, a `SECURITY DEFINER` function
that returns the row's id and no identity at all. Neither runtime role holds
`INSERT` here, so there is no second way to write a row.

**A row has to be committed before any name is handed over, and that is what
makes it a record rather than a courtesy.**
[ADR 0001](../../../docs/adr/0001-identity-separation-by-database-role.md)
originally put the write and the read in one transaction, which E0-10's review
measured as less than it claimed: Postgres streams the result rows before the
caller decides what to do with its transaction, so a caller that rolled back kept
the name and discarded the row.
[ADR 0071](../../../docs/adr/0071-the-reveal-answers-only-a-committed-record.md)
replaced that with two calls — `public.record_identity_reveal` writes the row and
`public.reveal_student_identity` answers only where the row's writing transaction
has committed. So the ordering is enforced by the database rather than by a
convention a code path can skip, and a caller that discards its transaction ends
up with neither the row nor the name.

**What that changes about what a row means.** A committed row is a reveal that
was *authorised*, not necessarily one whose name was read, because the caller may
commit the record and never spend it. The log errs in **both** directions, and
the second is the one §4 forbids: nothing limits a committed record to a single
spend, so one row can stand behind any number of reads of the name it points at.
§6.2's periodic review outside the Care office counts rows as accesses and will
therefore count low. ADR 0071 states both directions; the re-spend half is
carried to E10.

**What is deliberately absent.** §6.2's conflict-of-interest flag has no column
yet. E0-10's scope leaves the choice between "leave the column or leave room for
it" and this is the second: the flag is E10's to *compute*, the general case
needs E9's purview union, and a boolean that is NULL on every row until then is
three states where the schema should carry two. `ALTER TABLE audit_log ADD COLUMN
conflict_of_interest boolean NOT NULL` is what E10 writes, alongside the code
that fills it — an addition, not a redesign. The rest of §6.2's queue — the case
model, the disposition note, the two actions — arrives with it.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AwareDateTime, Base


class AuditAction(StrEnum):
    """What an `audit_log` row records having happened.

    One member, and it is the whole of E0-10's audit surface: a Care staff
    member was authorised to obtain a student's name and email address through
    the reveal function. "Authorised" rather than "obtained" since ADR 0071 — the
    row is committed before the name is read, so it records the access having
    been opened. The member's value is its name, as every other enum in this
    model layer does it — one spelling in Python and in the database.
    """

    IDENTITY_REVEAL = "IDENTITY_REVEAL"


class AuditLog(Base):
    """One thing that happened, the actor who did it, and when (SPEC §8).

    Append-only by rule rather than by instrument today: nothing holds `UPDATE`
    or `DELETE` on it, because the two runtime roles hold no privilege on it at
    all and the only writer is a `SECURITY DEFINER` function that inserts. E10
    owns the review surface (§6.2 makes the log "reviewable by Admin, without
    comment content") and can add the instrument with the reader.
    """

    __tablename__ = "audit_log"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Server-side, not application-side: the one writer is SQL inside the
    # database, and a timestamp a caller could choose is not evidence of when
    # the access happened. `AwareDateTime` refuses a naive value (ADR 0019).
    occurred_at: Mapped[datetime] = mapped_column(
        AwareDateTime, nullable=False, server_default=text("now()")
    )
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action"), nullable=False
    )
    # RESTRICT, like every other reference to `person`: deleting somebody out of
    # the people graph must not silently delete the record of what they reached.
    # §6.2 has this log "reviewed periodically outside the Care office", which a
    # cascade would quietly empty.
    actor_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("person.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # The student whose identity was revealed. NOT NULL because the only action
    # this table can hold names one; a later action that names no subject is a
    # migration that relaxes this, in the ticket that adds the action.
    subject_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # §4 asks for "actor, timestamp, and case". The case is nullable and carries
    # no foreign key because `threat_case` does not exist until E10 — E0-10
    # ships the reveal as a proof of mechanism, before there is any case model
    # to reveal *from*. E10 adds the reference when it adds the table.
    case_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
