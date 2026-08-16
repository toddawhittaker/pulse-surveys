"""Who someone is: the LMS user key, the identity split off from it, the people graph, enrollment.

SPEC §4, §2.1 and §8. This is the module the confidentiality guarantees exist to
protect, so what is *not* here matters as much as what is.

**`user` holds a key and a platform reference and nothing else.** No name, no
email address. Identity lives one table over, in `user_identity`, because
[ADR 0001](../../../docs/adr/0001-identity-separation-by-database-role.md) makes
the protection a **table-level** grant: `pulse_app` serves every student,
instructor, leadership and admin request with no grant of any kind on
`user_identity`. A column-level grant would be the obvious alternative and it
disappears silently the next time a table is recreated, which is a routine
migration voiding the guarantee with nothing going red. E0-10 builds the views
and the grants; this ticket builds the split they need.

**Identity-bearing columns carry an `identity_` name prefix**
(ADR 0020) — `user_identity.identity_name`, `user_identity.identity_email`,
`person.identity_name`. The prefix says what the column *holds*; it does not say
who may read it, which is E0-10's decision and a separate one.
`tests/integration/test_identity_column_marker.py` is the tripwire: it sweeps the
tables that hold a person and fails on one whose name reads as a name or an email
address and which carries no marker.

**Two ownership markers meet on `user_identity` and only one can be the prefix.**
A display name and an email address reach Pulse from the platform, so ADR 0014
would prefix them `lms_`; ADR 0020 records why the identity marker wins the name
instead. Nothing else in this module is LMS-owned in ADR 0014's sense except
`user.lms_user_id`, which is the `sub` claim verbatim.

**What the database refuses, and why it is the database that refuses it.** SPEC
§8 puts these rules in the schema rather than in `app/services/`, so a seed
script, a Celery task or a roster sync cannot write a row that breaks them:

  - a user is unique per LMS user ID **per platform**, because `sub` is only
    unique per issuer (SPEC §7.3) — the same person on a test LMS and a
    production LMS is two users, and a uniqueness rule over the ID alone would
    make the second one unwritable;
  - a user has at most one identity row;
  - a person corresponds to at most one user, and may correspond to none;
  - an enrollment window runs forwards, and two windows for one user in one
    section may not overlap. See `Enrollment` for that one, which is the only
    rule here that needs an instrument other than a unique or check constraint.

**Not here, on purpose.** `role_assignment`, `lead_faculty_mapping` and the
supervision graph are E0-09; the identity-separated views and the three database
roles are E0-10; the Care re-identification path and its audit log are E10. The
LTI registration tables `user` points at are `app.models.lti`.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    """One LMS user on one platform — the key SPEC §4 keys every response to.

    "Responses are stored keyed to the **LMS user ID** (`sub` from the launch)."
    That is all this row is: the key, and which platform issued it. A name or an
    email address here would sit inside the grant every instructor and leadership
    read path already holds, which is the whole failure ADR 0001 is written
    against, so `tests/integration/test_identity_schema.py` asserts their absence
    against Postgres rather than against this class.

    **`lms_user_id` is text.** A `sub` is an opaque string the platform chooses;
    Canvas issues digits, Moodle a UUID-shaped value, and nothing in LTI 1.3
    promises either. It carries the `lms_` prefix because it is the platform's
    value verbatim and Pulse may never edit it (ADR 0014).

    **Unique per platform, not globally.** `sub` is unique within an issuer and
    says nothing across issuers (SPEC §7.3).
    """

    __tablename__ = "user"
    __table_args__ = (UniqueConstraint("lti_platform_id", "lms_user_id"),)

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    # No index of its own: it leads `uq_user_lti_platform_id_lms_user_id`, which
    # already serves a lookup by platform. Same reasoning as `course.prefix_id`
    # in `app/models/org.py`, and the same caveat — leading position is what
    # makes it true, so reordering the constraint means putting an index back.
    #
    # RESTRICT rather than CASCADE: de-registering a platform must not silently
    # delete every user on it, and with them every response keyed to those users.
    lti_platform_id: Mapped[UUID] = mapped_column(
        ForeignKey("lti_platform.id", ondelete="RESTRICT"), nullable=False
    )
    lms_user_id: Mapped[str] = mapped_column(Text, nullable=False)


class UserIdentity(Base):
    """The name and email address of one LMS user, in a table of their own.

    One row per user, enforced by `UNIQUE (user_id)` rather than implied by the
    foreign key: nothing in a foreign key says one, and a second row would double
    every joined result in E0-10's read paths, or — worse — make which name comes
    back depend on the query plan.

    **`ON DELETE CASCADE`, which is the one place in this schema that cascades.**
    Everything else deletes with `RESTRICT`, because losing a containment node
    silently would lose everything under it. Here the direction of the risk is
    reversed: what must never happen is a name outliving the user it belongs to.
    SPEC §4's retention rules delete personally identifiable data on a schedule,
    and a `RESTRICT` here would make every such deletion a two-step that a future
    code path can perform half of.

    **`identity_email` is nullable.** NRPS exposes an email address only where
    the platform is configured to release it (SPEC §7.3, "email addresses where
    exposed"), so a roster sync must be able to record a name without one. A name
    is required: an identity row with neither is a row with no reason to exist.
    """

    __tablename__ = "user_identity"
    __table_args__ = (UniqueConstraint("user_id"),)

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    identity_name: Mapped[str] = mapped_column(Text, nullable=False)
    identity_email: Mapped[str | None] = mapped_column(Text, nullable=True)


class Person(Base):
    """A Pulse-owned person record: the node the supervision graph hangs off.

    SPEC §2.1 puts "person records (name, category) plus reports-to edges" on
    Pulse's side of the ownership line — the LMS has no equivalent, and purview is
    computed from this graph rather than from containment. E0-09 adds
    `role_assignment` and the `reports_to` edges; this row is what those point at.

    **The link to a `user` is nullable, unique, and explicit.** Nullable because a
    dean who has never launched the tool still supervises chairs, and the graph is
    built top-down in the admin console before anyone launches anything. Unique
    because two people claiming one LMS user is a contradiction rather than a
    state to resolve at read time. Explicit because the alternative is matching a
    person to a user by name in application code, which is exactly the ambiguity
    an identity split exists to remove.

    **The link is on this table rather than on `user`**, so that `user` stays what
    E0-08's scope says it is — the key and the platform reference. The cost is
    stated rather than hidden: one person who launches from two registered
    platforms has two `user` rows and this column can hold only one of them. That
    is a migration (a join table, or moving the link to `user`) if a deployment
    ever registers two platforms carrying the same people, and until then it is
    the shape that makes the wrong row unwritable.

    **`category` is free text and not an enum.** SPEC §2.1 names the field and
    never enumerates its values, and inventing a closed set here would put a
    guess in a database type that later has to be migrated out of it. Every other
    closed set in this schema — `course.level` — comes from a table in the spec.
    """

    __tablename__ = "person"
    __table_args__ = (UniqueConstraint("user_id"),)

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    # RESTRICT: a `user` row that a person is linked to cannot be deleted out
    # from under the people graph. Unlinking is a deliberate edit, not a side
    # effect of removing an LMS user.
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=True
    )
    identity_name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)


class Enrollment(Base):
    """One window during which a user was enrolled in a section.

    E3's participation formula is enrollment-windowed — it asks whether a student
    was enrolled in week N — so this is a window and not a flag, and a student who
    drops in week 3 and re-adds in week 8 has two rows that do not touch.

    **Overlapping windows for one user and section are refused** (E0-08 criterion
    5, which leaves the choice open and asks for it to be made and tested). Two
    overlapping rows give "was this student enrolled in week N" two answers with
    no rule for choosing between them, and the student is then counted twice in
    the denominator of a number that goes on an instructor's report. Permitting
    overlap would need that tie-break written down first, and no ticket has one.

    `UNIQUE (user_id, section_id)` is the constraint that suggests itself and it
    is the wrong one: it refuses the drop-and-re-add above, which the LMS sends
    and E0-15 seeds deliberately. What is needed is "no two windows for this pair
    overlap", which Postgres expresses as the exclusion constraint below. ADR 0021
    records the alternatives and what this one costs.

    **`alembic check` does not vouch for that constraint.** Autogenerate rendered
    it into the migration because it is on this `Table` and the table was new;
    afterwards it is compared in neither direction, since Alembic's Postgres
    implementation drops the backing GiST index from the reflected set
    (`correct_for_autogen_constraints`) and nothing compares `pg_constraint` rows
    of type `x`. Change the rule here without writing a migration and the check
    stays green. `tests/integration/test_identity_schema.py` asserts the
    behaviour against a real server, which is the only thing that can.

    **The check constraint below can be deleted with the whole suite green, and
    it stays anyway.** Measured by deleting it: a backwards window is refused
    either way, because `daterange(started_on, ended_on, '[]')` raises "range
    lower bound must be less than or equal to range upper bound" on its own. The
    check is kept because it states criterion 4's rule in the schema rather than
    leaving it implied by an implementation of a different rule, and because its
    error names the columns. Deleting it would make the ordering rule disappear
    the day somebody changes how overlap is enforced.

    **`ended_on` is nullable and means still enrolled.** The range is then
    unbounded above, so a second open-ended window for the same pair overlaps the
    first and is refused, which is the correct answer. The alternative — writing
    the section's end date in advance — stores a prediction as a fact and has to
    be corrected on every drop.

    **Neither date carries an `lms_` prefix, and that is a judgment.** Enrollments
    are LMS-owned in SPEC §2.1, but NRPS 2.0 reports a membership *status* rather
    than enrollment dates, so these two columns are most likely Pulse's record of
    when a student was first and last seen in the roster — derived by Pulse from
    LMS data, which is the `course.level` case ADR 0014 leaves unprefixed. E1's
    roster sync is what settles it; if a platform turns out to supply the dates,
    renaming them is a migration and a visible schema event, which is what ADR
    0014 says an ownership change should be.
    """

    __tablename__ = "enrollment"
    __table_args__ = (
        CheckConstraint(
            "ended_on IS NULL OR ended_on >= started_on",
            name="ends_on_or_after_it_starts",
        ),
        # Equality on `uuid` inside a GiST constraint needs the `btree_gist`
        # extension, which the migration creates. `'[]'` — both ends inclusive —
        # because a window is a set of days a student was enrolled on, and the
        # day they dropped is one of them; it is also what makes a window that
        # starts and ends on the same day a non-empty range rather than an empty
        # one that overlaps nothing.
        ExcludeConstraint(
            ("user_id", "="),
            ("section_id", "="),
            (text("daterange(started_on, ended_on, '[]')"), "&&"),
            name="ex_enrollment_windows_do_not_overlap",
            using="gist",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Not indexed on its own: it leads the GiST index backing the exclusion
    # constraint above, so a lookup of one user's enrollments is served without a
    # second index. That index is also what every insert here already pays for.
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    # Indexed, unlike `user_id`, because nothing else covers it and this is the
    # read E3 performs constantly: every participation figure on every report is
    # "who was enrolled in this section during week N". Postgres 17 has no skip
    # scan, so the exclusion constraint's index — which leads with `user_id` —
    # serves no lookup by section.
    section_id: Mapped[UUID] = mapped_column(
        ForeignKey("section.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    started_on: Mapped[date] = mapped_column(Date, nullable=False)
    ended_on: Mapped[date | None] = mapped_column(Date, nullable=True)
