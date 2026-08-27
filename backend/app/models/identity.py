"""Who someone is, and what they may do: users, identity, the people graph, and role assignments.

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
(ADR 0022) — `user_identity.identity_name`, `user_identity.identity_email`,
`person.identity_name`. The prefix says what the column *holds*; it does not say
who may read it, which is E0-10's decision and a separate one.
`tests/integration/test_identity_column_marker.py` is the tripwire: it sweeps the
tables that hold a person and fails on one whose name reads as a name or an email
address and which carries no marker.

**Two ownership markers meet on `user_identity` and only one can be the prefix.**
A display name and an email address reach Pulse from the platform, so ADR 0014
would prefix them `lms_`; ADR 0022 records why the identity marker wins the name
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

**The supervision graph is here too, at the bottom** — `role_assignment` and
`lead_faculty_mapping` (E0-09), which SPEC §13 puts in this module. They are what
turns a person into a purview, so they sit on the other side of the same line
`user` and `user_identity` sit on: this module holds both who somebody is and
what they may do, and it is the one place where confusing the two would be
expensive. `RoleAssignment`'s docstring says which rules the database refuses
and why each is where it is.

**Not here, on purpose.** The identity-separated views and the three database
roles are E0-10; purview computation over the graph is E0-11 and E9; the Care
re-identification path and its audit log are E10. The LTI registration tables
`user` points at are `app.models.lti`.
"""

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AwareDateTime, Base, UuidPrimaryKey


class User(UuidPrimaryKey, Base):
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


class UserIdentity(UuidPrimaryKey, Base):
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

    **Both columns are nullable, and E1-11 is why the name is.** NRPS exposes an
    email address only where the platform is configured to release it (SPEC §7.3,
    "email addresses where exposed"), so a roster sync must be able to record a
    name without one — which is what `identity_email` being nullable was always
    for. The mirror turned out to be the live case: ADR 0050 measured that this
    project's mock roster exposes "an address and no name", so E1-11's sync has an
    address to store for a user it has no name for at all. A NOT NULL name would
    leave it two bad options — invent one, or store no address — and inventing
    identity from a roster is the thing this table exists not to do.

    **A row with neither is therefore writable, and nothing here refuses it.** That
    is a state no writer in this project produces: `record_roster_email`
    (`roster_email_v001.sql`) creates a row only where the platform exposed an
    address, and clears an address without creating one. A `CHECK` requiring one of
    the two is deliberately not added — it would refuse the ordinary intermediate
    state of a two-step edit in §6.3's People editor, which nobody has built yet, in
    exchange for a rule no writer needs. ADR 0095 records the choice.
    """

    __tablename__ = "user_identity"
    __table_args__ = (UniqueConstraint("user_id"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    identity_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    identity_email: Mapped[str | None] = mapped_column(Text, nullable=True)


class Person(UuidPrimaryKey, Base):
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

    # RESTRICT: a `user` row that a person is linked to cannot be deleted out
    # from under the people graph. Unlinking is a deliberate edit, not a side
    # effect of removing an LMS user.
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=True
    )
    identity_name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)


class Enrollment(UuidPrimaryKey, Base):
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
    overlap", which Postgres expresses as the exclusion constraint below. ADR 0023
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

    **Neither date carries an `lms_` prefix, and E1-11 settled that they never
    will.** E0-08 left this open — "these two columns are most likely Pulse's
    record of when a student was first and last seen in the roster … E1's roster
    sync is what settles it" — and the sync's answer is that the prediction was
    right and that the platform's own dates are a *second* pair rather than the
    same one. `started_on` and `ended_on` stay Pulse's record of first and last
    sighting, unprefixed; the platform's window arrives beside them in
    `lms_window_start` and `lms_window_end`.

    **The two pairs are separate because SPEC §3.4 reads them differently.** "Late
    adds: denominator starts at the student's first enrolled week (from NRPS
    enrollment data). Where the platform supplies no enrollment dates — most supply
    none — a student counts as enrolled from the section's start date." Those are
    two rules, and E3 can only choose between them if "the platform supplied none"
    is a state the row can be in — which is why the new pair is nullable and why
    nothing may synthesize a value into it. A single pair carrying whichever
    happened to be known would make a windowless member indistinguishable from a
    dated one for the rest of the term.

    **Which is also why there is no status column.** NRPS reports `Active`,
    `Inactive` and `Deleted`, and it is tempting to store the last one seen; the
    open and closed windows *are* the recorded transition, and a status column
    beside them is a second answer to "was this student enrolled in week N" with no
    rule for choosing between the two. ADR 0095 records that and the rest of E1-11's
    window semantics.
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
    # The platform's own enrollment window, verbatim, where it supplies one (ADR
    # 0048's namespaced NRPS extension; E1-11). `lms_`-prefixed under E0-05's rule
    # because these are the platform's values and Pulse never edits them — it
    # follows them, the way it follows `course.lms_title`.
    #
    # **Nullable, and NULL means the platform supplied none.** That is the whole
    # value of the pair: see the class docstring, and never write a value here that
    # the extension did not carry. `AwareDateTime` refuses a naive datetime at the
    # bind boundary (ADR 0019), which is what makes "an RFC 3339 timestamp with its
    # offset, end to end" a property of the column rather than of the sync.
    #
    # A `timestamptz` beside two `date`s, because these are the two kinds of fact
    # they are: a platform dates an enrollment to an instant, and Pulse's own
    # record of a sighting is the day a sync ran.
    lms_window_start: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    lms_window_end: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)


class AssignmentRole(StrEnum):
    """The roles SPEC §2.1's table grants, as a Postgres enum type.

    Eight of the nine rows in that table. **`STUDENT` is deliberately absent**: a
    student is attached to "own responses" rather than to a node in the org
    hierarchy, and nothing in the spec or in any ticket gives a student a
    `role_assignment` row. Adding one would need a scope grain for it, and the
    honest answer to "which node is a student scoped to" is none of them — so the
    row is left unwritable rather than given an invented answer.

    **`CARE` is in this enumeration and reachable from nowhere else.** SPEC §6.2
    makes Care the only role that can re-identify a student, and E0-09 keeps the
    grant strictly here: no LTI claim, no OIDC claim and no LMS role may produce
    it, because the administrator of the platform controls what a claim says and
    a claim-to-Care mapping would hand them identity access.
    `tests/unit/test_care_is_not_reachable_from_a_claim.py` sweeps the syntax tree
    of every module under `app/` for a module that both reads a claim and names
    this role. That is why the name belongs to a shared enumeration in the model
    layer: a door that needs to exclude Care can exclude *this* member, and the
    exclusion is then a fact about the role rather than a literal in the door.

    Each member's value is its name, as `CourseLevel`'s and `Modality`'s are:
    one spelling in Python and in the database, rather than two to keep in step.
    """

    INSTRUCTOR = "INSTRUCTOR"
    LEAD_FACULTY = "LEAD_FACULTY"
    CHAIR = "CHAIR"
    ASSISTANT_DEAN = "ASSISTANT_DEAN"
    DEAN = "DEAN"
    VP_ACADEMICS = "VP_ACADEMICS"
    CARE = "CARE"
    ADMIN = "ADMIN"


# SPEC §2.1's "Scope attachment" column, as the one expression that holds it, and
# the reason `role_assignment` carries five nullable scope references (ADR 0025).
#
# §8 wrote a single `scope_node_id` when this was built, and it no longer does:
# the spec was corrected on 2026-08-18 to describe the five columns, because
# containment is six tables and a single column would be an untyped identifier
# with no referential integrity. So this is now what the spec says rather than a
# departure from it.
#
# Two clauses, and both are load-bearing.
#
# **`num_nonnulls(...) = 1`** says an assignment is scoped to exactly one node.
# Without it a row could name a department *and* a college, and the second one
# would be a grant nobody could see in any query written against the first.
#
# **The `CASE` says which one**, per role, out of SPEC §2.1's table: instructor
# to a section, lead faculty to a course, chair to a department, assistant dean
# and dean to a college ("the same node as the dean — authority comes from the
# supervision graph, not the scope"), VP of Academics, Care and Admin to the
# institution.
#
# **`ELSE false` is what makes this fail closed.** `role` is `NOT NULL` and the
# enum has exactly the eight labels the `CASE` names, so the `ELSE` is
# unreachable today. It is here for the day somebody adds a ninth: an unmatched
# `CASE` returns `NULL`, a `CHECK` that evaluates to `NULL` *passes*, and the new
# role would silently be scopeable to anything at all. With the `ELSE`, a role
# nobody has given a grain to cannot be written down until somebody does.
#
# There is deliberately no `prefix_id`. No role in SPEC §2.1's table is scoped to
# a prefix, so the column would exist only to be refused by this constraint —
# and a scope that cannot be spelled at all is a stronger rule than one that is
# spelled and rejected.
SCOPE_GRAIN_RULE = """
num_nonnulls(institution_id, college_id, department_id, course_id, section_id) = 1
AND CASE role
        WHEN 'INSTRUCTOR' THEN section_id IS NOT NULL
        WHEN 'LEAD_FACULTY' THEN course_id IS NOT NULL
        WHEN 'CHAIR' THEN department_id IS NOT NULL
        WHEN 'ASSISTANT_DEAN' THEN college_id IS NOT NULL
        WHEN 'DEAN' THEN college_id IS NOT NULL
        WHEN 'VP_ACADEMICS' THEN institution_id IS NOT NULL
        WHEN 'CARE' THEN institution_id IS NOT NULL
        WHEN 'ADMIN' THEN institution_id IS NOT NULL
        ELSE false
    END
"""

# SPEC §2.1's "Entry point" column, as two stored generated columns (ADR 0026).
#
# "Every *reporting* role — instructor, lead faculty, chair, assistant dean,
# dean, VP of Academics — can enter through an LTI launch, including leadership.
# Every role except instructor and student can *also* enter by web login; Care
# and Admin are web login only (their work has no launch context), and students
# enter by launch only."
#
# **Derived from the role and not stored per row**, which is the whole decision:
# the rule §2.1 states is a rule about roles, so a value computed from the role
# cannot disagree with it. A writable column could — a Care assignment with
# `permits_launch` set is a row that contradicts its own role, and nothing would
# notice until a launch honoured it. A generated column has no write path at all,
# for a seed script, an admin console or a superuser session alike.
#
# **Each door is enumerated positively**, rather than `permits_web_login` being
# written as `role <> 'INSTRUCTOR'`. The negative spelling is shorter and it
# fails open: a ninth role added to `AssignmentRole` would acquire web login by
# default, from a line nobody revisited. Enumerated, a new role gets no door
# until someone writes it into one of these lists, which is the failure that
# reports itself the first time somebody tries to log in.
#
# **Spelled the way Postgres deparses it** — `= ANY (ARRAY[...])` with the enum
# cast on each literal — for the reason `app/models/org.py` gives at length about
# `COURSE_LEVEL_DERIVATION`: Alembic cannot alter a generated column, so its
# whole response to a changed expression is one normalised string comparison and
# a warning, and a comparison that never matches warns on every run. Editing
# either expression means writing a migration and pasting the server's own
# rendering back here; `pg_get_expr` on `pg_attrdef` prints it.
LAUNCH_DOOR_DERIVATION = """
role = ANY (ARRAY[
    'INSTRUCTOR'::assignment_role,
    'LEAD_FACULTY'::assignment_role,
    'CHAIR'::assignment_role,
    'ASSISTANT_DEAN'::assignment_role,
    'DEAN'::assignment_role,
    'VP_ACADEMICS'::assignment_role
])
"""

WEB_LOGIN_DOOR_DERIVATION = """
role = ANY (ARRAY[
    'LEAD_FACULTY'::assignment_role,
    'CHAIR'::assignment_role,
    'ASSISTANT_DEAN'::assignment_role,
    'DEAN'::assignment_role,
    'VP_ACADEMICS'::assignment_role,
    'CARE'::assignment_role,
    'ADMIN'::assignment_role
])
"""


class RoleAssignment(UuidPrimaryKey, Base):
    """One grant: this person, in this role, over this node (SPEC §2.1, §8).

    **People are not roles.** A person acting in any role but Student holds one
    or more assignments and every view is resolved from an assignment or a
    union of them, never from a person "type". Purview is computed over the
    `reports_to` edges between the rows of this table, so each row here is a
    grant of access to somebody's data, and every rule below is in the database
    rather than in `app/services/` for that reason: a seed script, a roster
    sync or a future admin console cannot write a row that breaks one.

    **`reports_to` references another assignment, never a person and never an org
    node** (SPEC §2.1, in bold). The distinction is invisible until somebody holds
    two hats: a chair who also leads a course has two assignments answering to two
    different supervisors, and an edge between *people* has one slot for the two
    of them. The failure is silent — the purview it computes is simply wrong, and
    it looks like an answer.

    **What the database refuses, and by which instrument.**

      - *A scope node of the wrong kind for the role* — the `CHECK` built from
        `SCOPE_GRAIN_RULE` above. A lead faculty scoped to a prefix holds every
        sibling lead's course, which is SPEC §4.1 invariant 2 broken in the schema
        before any query is written.
      - *A Care assignment with a `reports_to` edge* — the second `CHECK` below.
        §2.1 puts Care outside the supervision graph: it supervises nothing and
        escalates to nobody, and an edge upward would put the one role that can
        re-identify a student inside a chair's transitive purview.
      - *An assignment reporting to a Care assignment, and a reporting cycle at
        any depth* — one `AFTER INSERT OR UPDATE` trigger, created by the
        migration, because both are facts about a *pair* of rows and a `CHECK`
        may not look at a second row. ADR 0027 records why that is a trigger and
        what it costs. `alembic check` cannot see a trigger in either direction;
        the behavioural tests in
        `tests/integration/test_role_assignment_graph.py` and the generated
        properties in `tests/integration/test_supervision_graph_properties.py`
        are what hold it.

    **What the database deliberately permits.** A person may hold both a `CARE`
    assignment and a reporting assignment. E0-09 is explicit that this must not
    be constrained: a Care staffer who also teaches a section is unlikely and
    legitimate, non-composability is about capabilities rather than about people,
    and §6.2 handles the overlap detectively by flagging such a reveal in the
    identity-access audit log rather than by blocking it. Person-level cycles are
    permitted for the same kind of reason — SPEC §2.1 calls a chair's lead-faculty
    assignment reporting to their own chair assignment "legal and expected", so
    the cycle guard walks assignment ids and never `person_id`.

    **There is no uniqueness rule on this table.** Two chairs of one department,
    or one person holding the same role twice over one node, are shapes no ticket
    rules out, and a constraint here would be this module guessing at a policy
    question the People editor (§6.3) owns.

    **`lead_faculty_mapping` is the authority on who leads a course, not this
    table.** A `LEAD_FACULTY` row here says where an assignment sits in the
    supervision graph — who it reports to, and what its own grant is restricted
    to — while §2.1 puts "one lead per course" on the mapping and computes a
    lead's grant from it. The two can disagree today and nothing refuses it:
    measured, two `LEAD_FACULTY` assignments on one course are accepted, and so is
    a `LEAD_FACULTY` assignment on a course whose mapping names somebody else. The
    scope grain rule above is *necessary* for §4.1 invariant 2 and it is not
    sufficient — it stops a lead being scoped above a course, and it does not make
    the course theirs. So a purview resolver reads the mapping to decide which
    courses a lead holds, and reads this table only for the edges; E0-11 is where
    that is written down, and E9 is where an editor keeping the two in step gets
    built.
    """

    __tablename__ = "role_assignment"
    __table_args__ = (
        CheckConstraint(SCOPE_GRAIN_RULE, name="scope_node_matches_the_role"),
        # The half of E0-09 criterion 8 that one row can answer for. The other
        # half — nothing may report *to* a Care assignment — needs the parent
        # row's role and is in the trigger.
        CheckConstraint(
            "role <> 'CARE' OR reports_to IS NULL",
            name="care_reports_to_nobody",
        ),
    )

    # The Pulse-owned people graph, not `user`: SPEC §2.1 keeps the two sides
    # apart and computes purview from this one, because "the LMS has no
    # equivalent". A dean who has never launched the tool still supervises
    # chairs, which is the case ADR 0024 makes `person.user_id` nullable for.
    #
    # Indexed, because this is the first question every authorization decision
    # asks — "which assignments does this actor hold" — and nothing else covers
    # it. RESTRICT: removing a person while they hold a grant is a deliberate
    # edit, not a side effect.
    person_id: Mapped[UUID] = mapped_column(
        ForeignKey("person.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    role: Mapped[AssignmentRole] = mapped_column(
        Enum(AssignmentRole, name="assignment_role"), nullable=False
    )
    # The five scope references, one per containment level a role can be scoped
    # to (ADR 0025). Exactly one is populated on any row, and which one is fixed
    # by the role: see `SCOPE_GRAIN_RULE`. All five are RESTRICT, matching
    # `app/models/org.py` — deleting a department that somebody chairs would
    # otherwise silently drop the grant rather than refuse the deletion.
    #
    # None of the five is indexed. The reads this table serves start from a
    # person or walk an edge, not from a node: "who chairs this department" is a
    # display label on a roll-up (§2.1) rather than a hot path, and five indexes
    # on five mostly-null columns would be paid for on every write. E9 adds one
    # with a measurement if the People editor turns out to need it.
    institution_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("institution.id", ondelete="RESTRICT"), nullable=True
    )
    college_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("college.id", ondelete="RESTRICT"), nullable=True
    )
    department_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("department.id", ondelete="RESTRICT"), nullable=True
    )
    course_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("course.id", ondelete="RESTRICT"), nullable=True
    )
    section_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("section.id", ondelete="RESTRICT"), nullable=True
    )
    # The supervision edge. Self-referential, nullable — a root assignment
    # reports to nobody — and indexed, because the purview union descends it
    # ("all assignments transitively reporting to it") and the trigger asks the
    # same question in the other direction before letting a row become Care.
    #
    # RESTRICT: an assignment that somebody reports to cannot be deleted out from
    # under them. Re-pointing the reporting line first is the deliberate edit
    # §6.3's People editor performs, and a cascade here would delete a subtree of
    # grants for a reason nobody could see afterwards.
    reports_to: Mapped[UUID | None] = mapped_column(
        ForeignKey("role_assignment.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    # SPEC §2.1's two entry doors, derived from the role rather than stored per
    # row (ADR 0026). See `LAUNCH_DOOR_DERIVATION` above for why they are
    # generated and why each is enumerated positively.
    permits_launch: Mapped[bool] = mapped_column(
        Boolean, Computed(LAUNCH_DOOR_DERIVATION, persisted=True), nullable=False
    )
    permits_web_login: Mapped[bool] = mapped_column(
        Boolean, Computed(WEB_LOGIN_DOOR_DERIVATION, persisted=True), nullable=False
    )


class LeadFacultyMapping(UuidPrimaryKey, Base):
    """Which courses a person leads (SPEC §2.1, §8).

    Pulse-owned, maintained in the admin console with CSV import/export, and the
    thing a Lead Faculty's own grant is computed from: "a Lead Faculty's grant is
    only the courses they lead (never sibling leads' courses, at any point in the
    union)".

    **One lead per course, and any number of courses per lead.** The uniqueness
    rule is on `course_id` alone. Both halves matter and they pull in opposite
    directions: a second mapping for one course hands a second person the first
    one's purview, which is SPEC §4.1 invariant 2; and a rule written over the
    person, or over the pair, would refuse the ordinary case §2.1 states twice —
    "people and courses are not 1:1", and "a lead's practical span may cross
    prefixes and departments".

    **A course with no mapping is a row that does not exist.** §2.1: such a course
    "falls to its department chair". That resolution is a query concern and is
    deliberately not stored — a row saying "the chair leads this" would be a
    second, staler answer to who the chair is, and it would have to be rewritten
    every time a chair changed.

    **This table carries no assignment reference.** A person's `LEAD_FACULTY`
    assignment and their mappings are separate facts, and joining them into one
    row would make the commonest case — one lead assignment, four led courses —
    four assignments in the supervision graph, each with its own edge to
    maintain.
    """

    __tablename__ = "lead_faculty_mapping"
    __table_args__ = (UniqueConstraint("course_id"),)

    # Indexed: "which courses does this lead lead" is how a lead's own grant is
    # built, and it is asked on every request they make. Nothing else covers it —
    # the unique constraint below leads with `course_id`.
    person_id: Mapped[UUID] = mapped_column(
        ForeignKey("person.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Not indexed on its own: it is the whole of `uq_lead_faculty_mapping_course_id`,
    # which serves a lookup by course. Same reasoning as `course.prefix_id` in
    # `app/models/org.py`.
    course_id: Mapped[UUID] = mapped_column(
        ForeignKey("course.id", ondelete="RESTRICT"), nullable=False
    )
