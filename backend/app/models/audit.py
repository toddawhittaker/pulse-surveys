"""The append-only record of who reached what, and when (SPEC §4, §6.2, §8).

SPEC §8 names one table for this — `audit_log` — and says it "includes all
re-identifications, exclusions and kept-decisions, policy changes,
response-on-behalf actions, imports (with their dry-run diffs), and admin config
edits". E0-10 needs exactly one of those: §4's "every identity access is
automatically audit-logged with actor, timestamp, and case".

**Seven actions can be written, and the enum lists exactly those.** E0-10 added
`IDENTITY_REVEAL`. E9-02 added five for the admin's people-graph writes
(`ROLE_GRANTED`, `ROLE_REVOKED`, `REPORTS_TO_SET`, `LEAD_MAPPING_CHANGED` and
`WEB_LOGIN_LINKAGE_CHANGED`), because the E9 owner ruling makes every grant and
revocation made in the People editor audited: that row, not a code refusal, is
what keeps a Care or Admin grant visible to the outside review (SPEC §6.2,
[ADR 0200](../../../docs/adr/0200-the-admins-people-graph-definers.md)). E9-06
added `IMPORT_APPLIED`, one row per applied CSV import (ADR 0204). Each
later ticket that logs something adds its own member in the same change as the
code that writes it, so the type is a list of things that actually happen rather
than a forecast — the same reasoning `AssignmentRole` gives for leaving `STUDENT`
out.

**Nothing in the application writes this table, and that is the design.** Every
row is written inside a `SECURITY DEFINER` function: a reveal by
`public.record_identity_reveal`, which returns the row's id and no identity at
all; an admin write by the people-graph definer that made the write, in the
same transaction and with no exception handler around the insert, so a write
whose row cannot be written is not committed; and an applied import by
`public.admin_record_import`, inside the apply's transaction. Neither runtime
role holds `INSERT` here, so there is no second way to write a row.

**Two shapes of row, each held by a check.** A reveal names a student
(`subject_user_id`) and no person written about; an admin write names the person
written about (`subject_person_id`) and, for an assignment or a mapping, the
role and the scope node, and names no student. `subject_user_id` was `NOT NULL`
while the reveal was the only action; it is nullable now, and two two-way checks
hold each shape: a row names a student exactly when it is a reveal, and names a
person exactly when it is neither a reveal nor an applied import. E9-06's
`IMPORT_APPLIED` row is the third shape: it names no student and no person, and
it alone carries `detail`, the import's kind and dry-run diff. Since E9-14 two
more checks hold the admin write's own shape: an assignment or mapping row
carries a role and a scope node and no other row carries both, and a linkage row
carries no scope node, so a later writer cannot record a grant without its role.

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
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AwareDateTime, Base, UuidPrimaryKey
from app.models.identity import AssignmentRole


class AuditAction(StrEnum):
    """What an `audit_log` row records having happened.

    `IDENTITY_REVEAL` is E0-10's: a Care staff member was authorised to obtain a
    student's name and email address through the reveal function. "Authorised"
    rather than "obtained" since ADR 0071 — the row is committed before the name
    is read, so it records the access having been opened.

    The other five are E9-02's, one per kind of people-graph write an admin
    makes (ADR 0200). One member covers each pair: `REPORTS_TO_SET` a set and a
    clear, `LEAD_MAPPING_CHANGED` a map and an unmap, and
    `WEB_LOGIN_LINKAGE_CHANGED` a link and an unlink. Creating or editing a
    person record is not audited.

    `IMPORT_APPLIED` is E9-06's: an admin applied a people or mapping CSV
    import, and the row carries the kind and the dry-run diff in `detail`
    (SPEC §8, "imports (with their dry-run diffs)"; ADR 0204). It names no
    subject person, because one import is about many.

    Each member's value is its name, as every other enum in this model layer
    does it — one spelling in Python and in the database.
    """

    IDENTITY_REVEAL = "IDENTITY_REVEAL"
    ROLE_GRANTED = "ROLE_GRANTED"
    ROLE_REVOKED = "ROLE_REVOKED"
    REPORTS_TO_SET = "REPORTS_TO_SET"
    LEAD_MAPPING_CHANGED = "LEAD_MAPPING_CHANGED"
    WEB_LOGIN_LINKAGE_CHANGED = "WEB_LOGIN_LINKAGE_CHANGED"
    IMPORT_APPLIED = "IMPORT_APPLIED"


class AuditLog(UuidPrimaryKey, Base):
    """One thing that happened, the actor who did it, and when (SPEC §8).

    Append-only by rule rather than by instrument today: nothing holds `UPDATE`
    or `DELETE` on it, because the two runtime roles hold no privilege on it at
    all and the only writers are `SECURITY DEFINER` functions that insert (the
    reveal's record, the people-graph definers and the import record). E10
    owns the review surface (§6.2 makes the log "reviewable by Admin, without
    comment content") and can add the instrument with the reader.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        # Relaxing `subject_user_id` for the admin's writes must not let a reveal
        # lose its student (E9-02's known trap), and an admin write names no
        # student. Two-way, so each row has exactly one shape.
        CheckConstraint(
            "(action = 'IDENTITY_REVEAL') = (subject_user_id IS NOT NULL)",
            name="a_reveal_names_its_student",
        ),
        # Every single admin write names the person it was about; a reveal and
        # an applied import (about many people at once) name none.
        CheckConstraint(
            "(action IN ('IDENTITY_REVEAL', 'IMPORT_APPLIED')) = (subject_person_id IS NULL)",
            name="an_admin_write_names_its_person",
        ),
        # An applied import carries its kind and its dry-run diff, and no other
        # row carries anything here.
        CheckConstraint(
            "(action = 'IMPORT_APPLIED') = (detail IS NOT NULL)",
            name="only_an_import_carries_a_detail",
        ),
        # Only an edge write names a parent.
        CheckConstraint(
            "action = 'REPORTS_TO_SET' OR parent_assignment_id IS NULL",
            name="only_an_edge_write_names_a_parent",
        ),
        # An assignment or mapping write names the role and the scope node it
        # wrote (ADR 0200), so a Care grant cannot be recorded without saying
        # so; and no other row carries both, so none reads as a grant (E9-14).
        CheckConstraint(
            "(action IN ('ROLE_GRANTED', 'ROLE_REVOKED', 'REPORTS_TO_SET', "
            "'LEAD_MAPPING_CHANGED')) = (role IS NOT NULL AND scope_node_id IS NOT NULL)",
            name="an_admin_write_names_its_role_and_scope",
        ),
        # A linkage row may carry the linked person's privilege as its role, and
        # never a scope node: a login is linked to a person, not to a node.
        CheckConstraint(
            "action <> 'WEB_LOGIN_LINKAGE_CHANGED' OR scope_node_id IS NULL",
            name="a_linkage_names_no_scope",
        ),
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
    # The student whose identity was revealed. Nullable since E9-02, whose admin
    # writes name no student; the `a_reveal_names_its_student` check above keeps
    # it required on a reveal.
    subject_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    # The person an admin's people-graph write was about: the grantee, the
    # revoked or re-pointed assignment's holder, the lead mapped or unmapped, or
    # the person linked or unlinked (ADR 0200). NULL on a reveal. RESTRICT, as
    # `actor_person_id` is and for the same reason. Not indexed: nothing reads by
    # it yet, and an index arrives with the first read that needs one.
    subject_person_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("person.id", ondelete="RESTRICT"), nullable=True
    )
    # For an assignment write, the assignment's role and its scope node; for a
    # mapping write, `LEAD_FACULTY` and the course. A Care grant is told apart by
    # this role, so E10's access log can show it. On a web-login linkage, the
    # privilege the linked person holds at the time: `CARE`, else `ADMIN`, else
    # NULL, so a login linked to a Care holder reads as reaching Care. NULL on a
    # reveal.
    role: Mapped[AssignmentRole | None] = mapped_column(
        Enum(AssignmentRole, name="assignment_role"), nullable=True
    )
    # No foreign key: which table the id belongs to is decided by `role`, by the
    # level rule `SCOPE_GRAIN_RULE` in `app.models.identity` sets out. The row is a
    # record of what was written, and it must outlive a node deleted later.
    scope_node_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    # On a `REPORTS_TO_SET` row, the new parent assignment, or NULL for a clear.
    # No foreign key: the parent may be revoked later, and the row records what
    # was written. The `only_an_edge_write_names_a_parent` check keeps it NULL on
    # every other action.
    parent_assignment_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    # §4 asks for "actor, timestamp, and case". The case is nullable and carries
    # no foreign key because `threat_case` does not exist until E10 — E0-10
    # ships the reveal as a proof of mechanism, before there is any case model
    # to reveal *from*. E10 adds the reference when it adds the table.
    case_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    # On an `IMPORT_APPLIED` row, `{"kind": "people" | "lead_mappings", "diff":
    # {...}}`: the diff the dry run answered, without its digest (ADR 0204). Staff
    # records only, because no import names a student. NULL on every other row,
    # by the `only_an_import_carries_a_detail` check. `none_as_null`, so a Python
    # `None` is SQL NULL rather than the JSON value `null`, which the check would
    # count as a detail.
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
