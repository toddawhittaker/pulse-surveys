"""The one chokepoint every entry point passes through to read anything (SPEC §13).

SPEC §13 puts it here: "`api/` routers stay thin and all real behavior lives in
`services/`", with this module the single place an actor is turned into a scope
and a scope is turned into a read. HTTP requests, Celery jobs and the
future MCP server (SPEC §7.5) all come through here or they do not read data.

**SPEC §2.1 defines purview as a union, and this module computes it.**
"Purview(assignment) = own grant union the purviews of all assignments
transitively reporting to it, with the own grant restricted by role grain." (The
spec writes that union as the set-theory symbol; it is spelled out here and
everywhere below, because a lone glyph in a docstring is one an editor, a
terminal or a diff can render as something else.) The **own grant** is
`own_grant`: a lead's led courses, a chair's department subtree, a dean's
college, the VP of Academics' institution, an instructor's section, and nothing
for an assistant dean, whose authority comes from the graph. The **transitive
union** is `transitive_purview`: a breadth-first walk down `reports_to`, by
assignment id, one statement per level of the graph.

**The lead clamp.** A `LEAD_FACULTY` assignment's purview is its own grant only,
whatever reports to it, so the walk never passes through a lead. An instructor on
a sibling lead's course who reports to a lead therefore adds nothing to that lead,
nor to anyone above the lead through it. That is what §2.1's "never sibling
leads' courses, at any point in the union" asks for.

**A leadership scope is the union over leadership assignments only.**
`resolve_scope` unions the purviews of the person's `LEAD_FACULTY`, `CHAIR`,
`ASSISTANT_DEAN`, `DEAN` and `VP_ACADEMICS` assignments, one `LeadershipGrant`
each. An instructor hat is reached through an instructor session and never merged
in, and `CARE` and `ADMIN` contribute nothing. The scope is asked for in one place,
`app.api.deps.leadership_scope`, from the verified session's own person and
nothing else. [ADR 0199](../../../docs/adr/0199-the-purview-walk-the-lead-clamp-and-its-chokepoint.md)
records the walk, the clamp, the leadership-only union and the chokepoint.

**Deferred seams fail closed.** [ADR
0003](../../../docs/adr/0003-deferred-authz-seams-fail-closed.md) is why
`raw_comments_permitted`, whose suppression rules are **E4**'s, raises rather
than answering: every value that could stand in for a missing authorization
decision is a value a caller can act on, and an empty answer is the worst of them
because it is also a legitimate state. If you are here because something crashed
on that raise, the seam is working; the fix is upstream, not a value returned from
here.

**Care is a capability beside the purview and never an element of one.** SPEC §2:
"Care is deliberately not composable with reporting roles — its sole power is the
threat queue, kept isolated so safety re-identification never rides alongside
routine oversight access." `Purview` is six sets of org-node ids and has nowhere
to put a capability, so no union can ever pick one up; `ActorScope.holds_care` is
where the answer lives for this module's own callers, and `holds_care` below
computes it here — but "here" is deliberately not the only place the live-CARE
predicate is checked. This module reads it from `public.assignment_scope` over
the `pulse_app` pool; `app.services.safety` reads it again from
`public.role_assignment` over the separate `pulse_care` pool (ADR 0042),
because the two pools hold different grants and neither can borrow the
other's. `app.services.safety`'s own comment above its
`_HOLDS_A_LIVE_CARE_ASSIGNMENT` is the one place all four copies — this
module's included — are named and kept in step (`docs/MISTAKES.md` entry 13).
An actor holds Care because they hold a live `CARE` role assignment, never
because of anything an LTI or OIDC claim says, since the platform administrator
controls what a claim says.

**No read here can reach identity, and every read that could goes through a
view.** SPEC §8: "instructor/leadership read paths go through views that
structurally cannot join to `user` identity columns — enforced in the database,
not just the application." The connection this module is handed is `pulse_app`,
which holds `SELECT` on the read views and on `public.person` and `public.user`
not at all, so a query *written here* that named either would be refused by the
server rather than by review.
`tests/unit/test_no_service_reads_an_identity_table_directly.py` is the
application-side half of that, and it reaches the two tables no grant stops:
`person` holds a name outright (§2.1) and `user` holds the LMS key.

**One read here names a base table, and it is `public.enrollment`.** E1-13's
student predicate (`_enrolled_today`) asks whether a user has a live enrollment
window, over the `SELECT` E1-11 granted `pulse_app` in
`roster_sync_grants_v001.sql`. This module's sentence used to say `pulse_app`
held "`SELECT` on five views and on no base table at all"; E1-11's grants on
`enrollment` and `nrps_call` had already made that false, and this read is what
made the correction due (`docs/MISTAKES.md` entry 1). The guarantee the sentence
was standing in for is unchanged and is stated above: `enrollment` carries a
`user_id`, a `section_id` and two dates, no name and no LMS key, and the
predicate answers a boolean.

**The grant does not protect the views themselves, and this ticket added three.**
Measured on the pinned Postgres: every read view in `public` is owned by
`pulse_admin` with `security_invoker` off, so each executes with its owner's
privileges. No count is written here — the set grows with every ticket that ships
a read view, and a number in a comment is a record with a scheduled expiry
(`docs/MISTAKES.md` entry 1); E4-03's three report views were the widening that
made the count this sentence used to carry false. A `_v002` of
`assignment_scope`, `lead_faculty_course` or `containment_path` that joined
`public.person` would hand `pulse_app` a name, and no grant would be consulted on
the way. What stands between that and a deployment is ADR 0041's rule — a view
ships as a new immutable versioned file that a migration executes, so the join is
in a diff somebody reads — together with the structural sweep in
`tests/integration/test_identity_column_marker.py`. Neither of those is the server
refusing it. Adding a view here widens the surface that rule protects, which is a
cost E0-11 paid three times over.

**Nothing here obtains its own connection.** ADR 0042 binds the `pulse_care` pool
to `app.services.safety` and to nothing else, so this module reads whatever
session it is handed and never chooses a pool. A caller that could choose one
could choose the one that reaches identity.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum, StrEnum, auto
from typing import Final, NamedTuple
from uuid import UUID

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

from app.config import Settings
from app.models.identity import LEADERSHIP_ROLES, AssignmentRole
from app.services import clock
from app.views_sql.queries import (
    SectionEnrollmentCount,
    SectionRosterRow,
    section_enrollment_counts,
    section_roster,
)

__all__ = [
    "LANDING_FOR_ROLE",
    "LANDING_PRECEDENCE",
    "LMS_OWNED_TABLES",
    "SANCTIONED_WRITERS",
    "ActorScope",
    "AuthzError",
    "CareIsNotComposableError",
    "Door",
    "LandingRole",
    "LeadershipGrant",
    "LmsOwnedWriteRefused",
    "NoReportingPurviewError",
    "OutOfPurviewError",
    "Purview",
    "ScopedReader",
    "UnknownAssignmentError",
    "UnknownSanctionedWriterError",
    "WriteSanction",
    "chosen_landing",
    "guard_write",
    "holds_care",
    "holds_leadership",
    "chaired_courses_with_a_lead",
    "lead_review_courses",
    "leadership_grant_covers",
    "own_grant",
    "raw_comments_permitted",
    "resolve_landing",
    "resolve_scope",
    "sanction_for",
    "scoped_reader",
    "taught_or_once_taught_section_ids",
    "taught_section_ids",
    "teaching_instructor_assigned",
    "teaching_instructor_grants",
    "teaching_instructors_of",
    "transitive_purview",
]


# ---------------------------------------------------------------------------
# Refusals. One family, so an entry point can turn any of them into one answer.
# ---------------------------------------------------------------------------


class AuthzError(Exception):
    """The base of every refusal this chokepoint raises.

    One family on purpose. SPEC §13 makes this module the single chokepoint for
    HTTP, for Celery and for the future MCP server (§7.5), and each of those has to turn a
    refusal into something a caller sees. A refusal outside this family escapes
    the `except AuthzError` somebody wrote and reaches a user as a 500 with a
    stack trace — or, in a Celery task, as a retry loop over a decision that will
    never change.
    """


class CareIsNotComposableError(AuthzError):
    """A Care assignment was asked for a reporting purview, and it has none.

    SPEC §2 and §6.2: Care's access is the threat queue and re-identification,
    "**no reporting access**". §2.1 puts it outside the supervision graph
    entirely, so there is no own grant to return and nothing to union.

    **Raised rather than answered with an empty purview**, which is the tempting
    reading and the wrong one: "Care supervises nothing" and "this lead has no
    reports" would then be the same value, a caller would union it, get its own
    grant back, and the rule §2 states would be enforced by nothing. The Care
    row's scope is the institution — that is where the queue lives, not a span of
    oversight — so the value that would leak here is the largest one in the
    product.
    """


class NoReportingPurviewError(AuthzError):
    """This role holds no reporting purview, so no own grant can be computed for it.

    `ADMIN` today: SPEC §2's table gives it the observability console, LTI
    registration, org and people management and configuration, and no reporting
    access, and §2.1's supervision chain does not contain it. A ninth role added
    to `AssignmentRole` lands here too until somebody writes down what it holds,
    which is the same fail-closed choice as `SCOPE_GRAIN_RULE`'s `ELSE false` and
    as the rank rule refusing an edge on an unranked role.
    """


class OutOfPurviewError(AuthzError):
    """A read was asked for a node the actor's purview does not hold.

    **Raised rather than filtered.** An empty result set is what a reader that
    silently drops out-of-scope rows returns, and a caller cannot tell it from a
    section nobody is enrolled in. §4.1 invariant 2 is about a lead never getting
    a sibling lead's course, and the difference between "you may not see this" and
    "there is nothing here" is the difference between a bug report and a screen
    that quietly renders one row fewer than it should.
    """


# `N818` asks for an `Error` suffix and it is suppressed rather than followed:
# this name is part of the interface E0-11 settled before any of it was written,
# and every caller, test and record in the ticket spells it this way. Renaming it
# to satisfy a naming rule would be a change to the contract in order to quiet a
# linter. The base class carries the suffix, which is the name an entry point
# catches.
class LmsOwnedWriteRefused(AuthzError):  # noqa: N818
    """A write was attempted against data the LMS owns and Pulse only mirrors.

    SPEC §2.1's ownership list is "courses, sections, section codes, enrollments,
    teaching instructors"; §8 restates it as a constraint: "LMS-owned data is
    never hand-edited in Pulse." The failure this prevents is quiet — an edit here
    is not rejected by the LMS and does not error, it is overwritten at the next
    hourly roster sync, so the symptom is a value that changes back by itself and
    reads as a sync bug.
    """


class UnknownSanctionedWriterError(LookupError):
    """`sanction_for` was asked for a writer `SANCTIONED_WRITERS` does not name.

    **Deliberately outside `AuthzError`.** Every member of that family is a
    refusal an entry point turns into an answer for a caller, and this is not
    one: the argument is a writer's name written in the source, so an unknown
    name is a bug in the calling module rather than a decision about a request.
    Inside the family it would be caught by somebody's `except AuthzError` and
    reported as "you may not do that", which is a wrong answer to a question
    nobody asked.
    """


class UnknownAssignmentError(AuthzError):
    """No assignment with that key exists, so no grant could be computed.

    Fails loudly rather than answering with an empty purview, which is ADR 0003's
    argument applied to a key that has been deleted or mistyped: an empty purview
    is a real state and a caller has no way to tell the two apart.
    """


# ---------------------------------------------------------------------------
# What a scope is made of.
# ---------------------------------------------------------------------------

# SPEC §2.1's containment hierarchy, outermost first. The order is the whole of
# what "restricted by role grain" means below: an own grant holds the node an
# assignment is scoped to and every node beneath it, and nothing above it.
CONTAINMENT_LEVELS: Final[tuple[str, ...]] = (
    "institution",
    "college",
    "department",
    "prefix",
    "course",
    "section",
)


@dataclass(frozen=True, slots=True)
class Purview:
    """The org nodes one assignment reaches, one set per containment level.

    SPEC §2.1's hierarchy is "Institution → College → Department → Prefix →
    Course → Section", and a purview is a set of nodes at each of those levels.

    **There is nowhere in this value to put a capability, and that is the
    design.** §2 makes Care non-composable with reporting roles, and §2.1 defines
    purview as a union — so the way a capability leaks is a union carrying it. Six
    sets of ids cannot: `union` below joins ids to ids, and there is nothing else
    in the value for it to join. A seventh field would not have to be called
    `care` to break that; `can_reveal`, `is_admin` or an entry-door flag would do
    it, and each arrives for a good local reason because this is already the value
    every read path is handed.

    Frozen, so a router, a task or an MCP server cannot widen the scope it was
    given and then read with it. §4.1 item 6 — "no view may ever widen a student's
    visibility relative to these rules" — is a rule about views, and this is the
    value they are all handed.
    """

    institution_ids: frozenset[UUID]
    college_ids: frozenset[UUID]
    department_ids: frozenset[UUID]
    prefix_ids: frozenset[UUID]
    course_ids: frozenset[UUID]
    section_ids: frozenset[UUID]

    @classmethod
    def empty(cls) -> "Purview":
        """A purview holding nothing — the identity element `union` starts from."""
        return cls(
            institution_ids=frozenset(),
            college_ids=frozenset(),
            department_ids=frozenset(),
            prefix_ids=frozenset(),
            course_ids=frozenset(),
            section_ids=frozenset(),
        )

    @classmethod
    def of(cls, nodes: Mapping[str, frozenset[UUID]]) -> "Purview":
        """A purview holding `nodes` at the levels it names and nothing elsewhere.

        Keyed by the level names in `CONTAINMENT_LEVELS` rather than by field
        name, so a caller that has just filtered `public.containment_path` by
        level does not have to spell `_ids` on every key.
        """
        return cls(
            institution_ids=nodes.get("institution", frozenset()),
            college_ids=nodes.get("college", frozenset()),
            department_ids=nodes.get("department", frozenset()),
            prefix_ids=nodes.get("prefix", frozenset()),
            course_ids=nodes.get("course", frozenset()),
            section_ids=nodes.get("section", frozenset()),
        )

    def union(self, other: "Purview") -> "Purview":
        """The union of SPEC §2.1's definition, level by level.

        Answers a new `Purview` and changes neither operand: a purview is handed
        to every read path in a request, so an in-place union would widen scopes
        the caller never asked about, in an order nothing records.

        A level dropped here is invisible in E0 — a purview with `section_ids` and
        no `course_ids` still renders, still scopes a query and still looks like an
        answer — which is why every level is written out rather than looped over a
        name list that could go stale.
        """
        return Purview(
            institution_ids=self.institution_ids | other.institution_ids,
            college_ids=self.college_ids | other.college_ids,
            department_ids=self.department_ids | other.department_ids,
            prefix_ids=self.prefix_ids | other.prefix_ids,
            course_ids=self.course_ids | other.course_ids,
            section_ids=self.section_ids | other.section_ids,
        )


class LeadershipGrant(NamedTuple):
    """One leadership assignment and the purview it reaches, as `resolve_scope` found it.

    A named triple, so a caller may unpack it as `(assignment_id, role, purview)`
    or read it by name. `purview` is that one assignment's `transitive_purview`,
    so the roots of a leader's tree and which assignment reaches a node are
    answered without walking the graph a second time.
    """

    assignment_id: UUID
    role: AssignmentRole
    purview: Purview


@dataclass(frozen=True, slots=True)
class ActorScope:
    """Everything a request needs to know about who is asking.

    Five fields and each is a separate requirement: the person the scope was
    resolved for; the leadership purview, which is the union of SPEC §2.1's
    purviews over the person's leadership assignments only; `grants`, one
    `LeadershipGrant` per such assignment, whose purviews union to `purview`;
    Care as a capability of its own so that no union operation can pick it up;
    and §4's n-threshold, which E4's suppression rules read from here rather than
    fetching for themselves — a caller that has to look the threshold up
    separately is a caller that can forget to.
    """

    person_id: UUID
    purview: Purview
    holds_care: bool
    n_threshold: int
    grants: tuple[LeadershipGrant, ...]


# ---------------------------------------------------------------------------
# The statements. Every one of them names a view, never a base table.
# ---------------------------------------------------------------------------

# One assignment, by key. The five scope columns are ADR 0025's "one nullable
# foreign key per level", exactly one of which is populated on any row.
_ASSIGNMENT = text(
    "SELECT assignment_id, person_id, role,"
    " institution_id, college_id, department_id, course_id, section_id"
    " FROM public.assignment_scope"
    " WHERE assignment_id = :assignment_id"
)

# Every assignment that reports straight to one of a set of assignments: one level
# of SPEC §2.1's supervision graph, read for a whole level at once. The edge is
# `reports_to`, which joins assignment to assignment and never person to person
# (§2.1: "`reportsTo` edges connect role assignments, not people or org nodes").
_REPORTS_TO_ANY_OF = text(
    "SELECT assignment_id, person_id, role,"
    " institution_id, college_id, department_id, course_id, section_id"
    " FROM public.assignment_scope"
    " WHERE reports_to = ANY(:assignment_ids)"
    " ORDER BY assignment_id"
)

# Every assignment one person holds. SPEC §2.1: "a person acting in any role but
# Student holds one or more role assignments… every view is resolved from an
# assignment (or a union of them), never from a person type."
_ASSIGNMENTS_OF_PERSON = text(
    "SELECT assignment_id, person_id, role,"
    " institution_id, college_id, department_id, course_id, section_id"
    " FROM public.assignment_scope"
    " WHERE person_id = :person_id"
    " ORDER BY assignment_id"
)

# Whether this person holds a live `CARE` assignment at all, read here from
# `public.assignment_scope`. E0-09's `role_assignment` carries no validity
# dates, so "live" reads as "exists" today: a revoked assignment is a deleted
# row. If end-dating is ever added, this predicate gains it along with its
# three siblings — `app.services.safety`'s own copy, and the two inside
# `public.record_identity_reveal` and `public.reveal_student_identity` — all
# four statements of one rule, named together in `app.services.safety`, above
# its `_HOLDS_A_LIVE_CARE_ASSIGNMENT` (`docs/MISTAKES.md` entry 13).
_HOLDS_A_LIVE_CARE_ASSIGNMENT = text(
    "SELECT EXISTS ("
    " SELECT 1 FROM public.assignment_scope AS acting"
    " WHERE acting.person_id = :person_id"
    " AND acting.role = CAST(:care AS public.assignment_role)"
    ")"
)

# Whether this person holds a live assignment in SPEC §2's reporting chain
# (E1-12). The same shape as the predicate above and here for the same reason it
# is: `public.assignment_scope` is read through this module and nowhere else, and
# `tests/unit/test_the_org_views_are_read_only_through_the_grant.py` is what holds
# that. §7.3 authorizes a roster sync on "an instructor **or any leadership
# role**", and the leadership half is a `role_assignment` row rather than anything
# a launch says — `app.services.provisioning` asks it through `holds_leadership`
# below.
#
# The set is bound and cast, so a role name this schema does not have is a
# database error rather than a silent no-match. It carries "live" in the same
# sense the Care predicate does, and gains end-dating with it.
_HOLDS_A_LEADERSHIP_ASSIGNMENT = text(
    "SELECT EXISTS ("
    " SELECT 1 FROM public.assignment_scope AS held"
    " WHERE held.person_id = :person_id"
    " AND held.role = ANY(CAST(:roles AS public.assignment_role[]))"
    ")"
)

# Whether one person already holds the teaching-instructor grant over one section.
# **A grant question rather than a purview question**, and it is here rather than
# in the caller because `public.assignment_scope` is this module's view to read:
# E0-41 fails any module under `backend/app/` outside this one that runs SQL
# naming it, on the ground that a second reader is a second place the scoping rule
# can be got wrong. The caller is `app.services.roster_sync`, which holds no
# privilege on `role_assignment` at all (it adds and ends the grant through two
# definers, ADR 0096 and ADR 0183) — so this is also the only way it can ask.
_HOLDS_THE_TEACHING_INSTRUCTOR_GRANT = text(
    "SELECT EXISTS ("
    " SELECT 1 FROM public.assignment_scope AS granted"
    " WHERE granted.person_id = :person_id"
    " AND granted.role = CAST(:role AS public.assignment_role)"
    " AND granted.section_id = :section_id"
    ")"
)

# Every section one person holds the teaching-instructor grant over — the set
# question beside the single-section one above, and the same three conditions
# written the same way, so the two cannot answer differently about one section.
# `DISTINCT` because SPEC §2.1 puts no uniqueness rule on `role_assignment` and
# two identical grants are a shape nothing refuses (E0-09); a section named twice
# would be a section listed twice.
#
# The null test is the grain: a row scoped to a course or to a college carries a
# null `section_id`, and without it such a row would put a null in the answer for
# every leadership hat the same person holds.
_TEACHING_INSTRUCTOR_SECTIONS = text(
    "SELECT DISTINCT granted.section_id"
    " FROM public.assignment_scope AS granted"
    " WHERE granted.person_id = :person_id"
    " AND granted.role = CAST(:role AS public.assignment_role)"
    " AND granted.section_id IS NOT NULL"
)

# The sections a roster walk ended this person's teaching grant on (ADR 0183's
# record). `pulse_app` reads these two columns of it and nothing else (E6-09).
_ONCE_TAUGHT_SECTIONS = text(
    "SELECT DISTINCT ended.section_id"
    " FROM public.ended_teaching_grant AS ended"
    " WHERE ended.person_id = :person_id"
)

# Everybody holding the teaching-instructor grant over one section — the people
# column of `_HOLDS_THE_TEACHING_INSTRUCTOR_GRANT`'s three conditions, with the
# person left open. E5-14's round-4 sealing asks it: each of them can read this
# section's report, and each knows the sections they teach.
_TEACHING_INSTRUCTORS_OF_A_SECTION = text(
    "SELECT DISTINCT granted.person_id"
    " FROM public.assignment_scope AS granted"
    " WHERE granted.role = CAST(:role AS public.assignment_role)"
    " AND granted.section_id = :section_id"
)

# Every teaching-instructor grant over one section, by assignment — E5.1-02. The
# same two conditions as `_TEACHING_INSTRUCTORS_OF_A_SECTION` above, answering the
# assignment id beside the person, because the roster sync ends a grant by its id
# (`public.end_teaching_instructor`). No `DISTINCT`: two identical grants are two
# rows, and each is ended on its own.
_TEACHING_INSTRUCTOR_GRANTS_OF_A_SECTION = text(
    "SELECT granted.assignment_id, granted.person_id"
    " FROM public.assignment_scope AS granted"
    " WHERE granted.role = CAST(:role AS public.assignment_role)"
    " AND granted.section_id = :section_id"
)

# Everybody holding an assignment whose scope names one section — the staff of that
# section, whatever role the assignment carries. E3-08's boundary round (EE-M1)
# reads it to answer "is this member of the roster somebody who teaches here", and
# `section_scoped_assignees` below is the only caller.
#
# **`section_id` is the assignment's own column, not a purview.**
# `public.assignment_scope` is a projection of `role_assignment` and expands no
# containment, so a dean's row names their college and answers nothing here — which
# is what keeps a dean enrolled in a course as a learner a learner. SPEC §2.1
# scopes exactly one role to a section, so today this is the teaching instructor
# and it is written as the *grain* rather than as that role, because a role added
# at section grain by a later ticket is staff of that section on the day it is
# added and nobody should have to remember to add it here.
_SECTION_SCOPED_ASSIGNEES = text(
    "SELECT DISTINCT granted.person_id"
    " FROM public.assignment_scope AS granted"
    " WHERE granted.section_id = :section_id"
)

# Which courses a person leads, out of the Lead Faculty mapping and not out of
# the assignment row. SPEC §2.1 puts "one lead per course" on the mapping; E0-09
# measured that `role_assignment` accepts two `LEAD_FACULTY` rows on one course
# and a `LEAD_FACULTY` row on a course whose mapping names somebody else, so the
# assignment's own `course_id` is not an answer to "which courses do they lead".
#
# Bound as a set of people so that a supervision walk reads every lead it reached
# in one statement. The answer is the union of what each of them leads, which is
# exactly the term a walk unions in; nothing asks it about two people and then
# treats the answer as one person's.
_LED_COURSES = text(
    "SELECT course_id FROM public.lead_faculty_course WHERE person_id = ANY(:person_ids)"
)

# Which of a set of courses anybody leads — the other question the same mapping
# answers. A chair reviews only the courses of their department that nobody
# leads (`lead_review_courses`, SPEC §2.1: "a course with no mapping falls to its
# department chair").
_COURSES_WITH_A_LEAD = text(
    "SELECT DISTINCT course_id FROM public.lead_faculty_course WHERE course_id = ANY(:course_ids)"
)

# Every node beneath a set of nodes of one level, at every level. Bound as a set
# so that a supervision walk reads every chair's department (or every dean's
# college) it reached in one statement rather than one per assignment. Built from
# one template over
# `CONTAINMENT_LEVELS` so the projection is written once; nothing a caller
# supplies is interpolated — the level names are literals in this module and the
# node key is always bound. `prefix` is in the mapping for completeness and is
# reached by no role: SPEC §2.1's scope table gives no role a prefix-shaped
# scope, and ADR 0025 records why a lead is refused one.
_DESCENDANTS_TEMPLATE = (
    "SELECT institution_id, college_id, department_id, prefix_id, course_id, section_id"
    " FROM public.containment_path"
    " WHERE {level}_id = ANY(:node_ids)"
)

_DESCENDANTS: Final[Mapping[str, TextClause]] = {
    level: text(_DESCENDANTS_TEMPLATE.format(level=level)) for level in CONTAINMENT_LEVELS
}

# The sections of a set of courses, for the one grant that is not a containment
# subtree: a lead holds named courses rather than a node, so their sections come
# from the courses rather than from anything above them.
_SECTIONS_OF_COURSES = text(
    "SELECT section_id FROM public.containment_path"
    " WHERE course_id = ANY(:course_ids) AND section_id IS NOT NULL"
)


# ---------------------------------------------------------------------------
# Role grain: which containment level each role's own grant is rooted at.
# ---------------------------------------------------------------------------

# SPEC §2.1's scope-attachment table, as the level an own grant starts from.
# `LEAD_FACULTY` is in it because a lead's grant *is* course-grained, and it is
# the one role whose courses do not come from the assignment row — see
# `_own_grant_of`.
#
# **A role absent from this mapping holds no reporting purview**, which is the
# fail-closed direction and the reason this is a mapping rather than a `CASE` with
# a default. `CARE` is absent because §2 makes it non-composable; `ADMIN` is
# absent because §2's table gives it a console rather than a span of other
# people's data; and a role added to `AssignmentRole` by a later ticket is absent
# until somebody decides what it holds.
_OWN_GRANT_ROOT: Final[Mapping[AssignmentRole, str]] = {
    AssignmentRole.INSTRUCTOR: "section",
    AssignmentRole.LEAD_FACULTY: "course",
    AssignmentRole.CHAIR: "department",
    AssignmentRole.DEAN: "college",
    AssignmentRole.VP_ACADEMICS: "institution",
}

# **`ASSISTANT_DEAN` is scoped to a college and its own grant is empty**, which is
# the one role grain that cannot be read off the scope column — and the one SPEC
# §2.1 singles out to say so: "The assistant dean is the worked example for why
# purview comes from the graph: own led courses union every supervised chair's
# department — **a set no single containment node holds**." §2's table says it from
# the other side, in the scope-attachment column itself: "College (same node as the
# dean — **authority comes from the supervision graph, not the scope**)." §2.1's
# own-grant sentence names a lead, a chair and a dean, and does not name this role.
#
# So both terms of that union arrive from somewhere other than this assignment. The
# led courses come from the person's own `LEAD_FACULTY` assignment, resolved as its
# own row, because §2 keeps people and roles apart and a purview is computed per
# assignment. The supervised chairs' departments come from `transitive_purview`'s
# walk down the supervision graph.
#
# **An empty answer here means "the graph supplies it", and for `CARE` an empty
# answer would have meant "there is nothing to supply"** — which is why Care raises
# instead of returning this. The two are opposite claims and must not share a
# spelling; ADR 0046 records the distinction.
#
# An earlier version of this module rooted the grant at the
# college, which made `ASSISTANT_DEAN` and `DEAN` identical, handed an assistant
# dean every department in the college including those whose chairs report straight
# to the dean, and contradicted the spec sentence quoted above. It was found by
# E0-11's security review and is asserted against by three tests in
# `tests/integration/test_own_grant_follows_the_role_grain.py`.
_GRANT_ARRIVES_THROUGH_THE_GRAPH: Final[frozenset[AssignmentRole]] = frozenset(
    {AssignmentRole.ASSISTANT_DEAN}
)


# ---------------------------------------------------------------------------
# Resolving a scope.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Assignment:
    """One row of `public.assignment_scope`, with names and types on it.

    Private, and it is the only place a `RowMapping` from that view is taken
    apart. A row's values arrive untyped, so every read of one is a place a
    `department_id` could be used where a `college_id` was meant; converting once,
    here, means the rest of this module is checked.

    The five scope references are ADR 0025's "one nullable foreign key per level",
    and exactly one of them is populated on any row — a database `CHECK` says so,
    which is why `_scope_node` below is a lookup by level rather than a coalesce.
    """

    assignment_id: UUID
    person_id: UUID
    role: AssignmentRole
    institution_id: UUID | None
    college_id: UUID | None
    department_id: UUID | None
    course_id: UUID | None
    section_id: UUID | None

    @classmethod
    def of(cls, row: RowMapping) -> "_Assignment":
        """One row of `public.assignment_scope`, converted."""
        return cls(
            assignment_id=row["assignment_id"],
            person_id=row["person_id"],
            role=AssignmentRole(row["role"]),
            institution_id=row["institution_id"],
            college_id=row["college_id"],
            department_id=row["department_id"],
            course_id=row["course_id"],
            section_id=row["section_id"],
        )


def _scope_node(assignment: _Assignment, level: str) -> UUID | None:
    """The node this assignment is scoped to, read at one containment level.

    A lookup per level and deliberately not a coalesce over the five columns. ADR
    0025 gives `role_assignment` five nullable references with a `CHECK` that
    exactly one is populated; a coalesce would answer with whichever one it met
    first, so a chair whose row somehow carried a college would be handed the
    college — and every sibling department in it.
    """
    return {
        "institution": assignment.institution_id,
        "college": assignment.college_id,
        "department": assignment.department_id,
        "course": assignment.course_id,
        "section": assignment.section_id,
    }[level]


def _nodes_beneath(
    session: Session, level: str, node_ids: Collection[UUID]
) -> Mapping[str, frozenset[UUID]]:
    """Every node strictly below any of `node_ids`, by level, out of `public.containment_path`.

    The view holds one row per org node with its ancestors filled in, so the rows
    whose `<level>_id` is one of these nodes are those nodes and everything under
    them. Every node in `node_ids` is at `level`; the answer is the union of their
    subtrees, and no caller reads it as one node's.
    Only the levels *below* `level` are collected: an own grant is the scope node
    and its subtree, and a level above it is somebody else's grant. A chair who
    also held `college_ids` would hold every sibling department in that college,
    which is a widening nobody it happens to can detect.
    """
    below = CONTAINMENT_LEVELS[CONTAINMENT_LEVELS.index(level) + 1 :]
    if not below or not node_ids:
        # A section has nothing beneath it, and no nodes have no subtree.
        return {name: frozenset() for name in below}
    found: dict[str, set[UUID]] = {name: set() for name in below}
    rows = session.execute(_DESCENDANTS[level], {"node_ids": list(node_ids)}).mappings()
    for row in rows:
        for name in below:
            key: UUID | None = row[f"{name}_id"]
            if key is not None:
                found[name].add(key)
    return {name: frozenset(keys) for name, keys in found.items()}


def _lead_faculty_grant(session: Session, person_ids: Collection[UUID]) -> Purview:
    """The courses these leads lead, and their sections. SPEC §2.1's role grain for a lead.

    A set of people because a supervision walk unions every lead it reaches; a
    caller asking about one lead passes one person.

    "A Lead Faculty's grant is only the courses they lead (never sibling leads'
    courses, at any point in the union)." The courses come from
    `public.lead_faculty_course` and never from the assignment's own `course_id`:
    E0-09 measured that a `LEAD_FACULTY` assignment can name a course the mapping
    gives to somebody else, and that row is one an administrator can write by hand
    today.

    **No `prefix_ids`, and that is not an oversight.** ADR 0025 refuses a lead a
    prefix-shaped scope precisely because it "would grant the lead every course
    under that prefix, sibling leads' courses included, which is §4.1 invariant
    2", and a purview that listed the prefix invites exactly the reading the scope
    column was denied. §2.1's "tree roots are the prefixes of their led courses"
    is a statement about where a navigation tree starts, computed from the
    courses, not about what the lead holds.

    A lead with no mapping rows holds nothing, which is a real state rather than a
    deferral: §2.1 says a course with no mapping "falls to its department chair".
    """
    if not person_ids:
        return Purview.empty()
    courses = frozenset(session.execute(_LED_COURSES, {"person_ids": list(person_ids)}).scalars())
    if not courses:
        return Purview.empty()
    sections = frozenset(
        session.execute(_SECTIONS_OF_COURSES, {"course_ids": list(courses)}).scalars()
    )
    return Purview.of({"course": courses, "section": sections})


def _own_grant_of(session: Session, assignment: _Assignment) -> Purview:
    """One assignment's own grant, with the role grain already applied.

    Split out from `own_grant` because callers that have the row in hand already
    would otherwise re-read it by key, a second answer to a question just asked.
    It is `_own_grants_of` over one row, so the role grain is written once.
    """
    return _own_grants_of(session, (assignment,))


def _own_grants_of(session: Session, assignments: Collection[_Assignment]) -> Purview:
    """The union of these assignments' own grants, with the role grain applied to each.

    The one place SPEC §2.1's role grain is written. It reads in a number of
    statements fixed by which grains are present — one per containment level that
    some assignment is rooted at, and two for every lead together — and never one
    per assignment, which is what lets `transitive_purview` read a whole level of
    the supervision graph at once.

    Every assignment is checked before anything is read, so a `CARE` or `ADMIN`
    row anywhere in `assignments` refuses the whole question rather than a part of
    it.
    """
    rooted: dict[str, set[UUID]] = {level: set() for level in CONTAINMENT_LEVELS}
    leads: set[UUID] = set()
    for assignment in assignments:
        if assignment.role is AssignmentRole.CARE:
            raise CareIsNotComposableError(
                f"assignment {assignment.assignment_id} is a CARE assignment and has no reporting "
                "purview. SPEC 2: Care is deliberately not composable with reporting roles — its "
                "sole power is the threat queue, kept isolated so safety re-identification never "
                "rides alongside routine oversight access. Ask holds_care() instead."
            )

        if assignment.role in _GRANT_ARRIVES_THROUGH_THE_GRAPH:
            continue

        level = _OWN_GRANT_ROOT.get(assignment.role)
        if level is None:
            raise NoReportingPurviewError(
                f"assignment {assignment.assignment_id} holds the {assignment.role.value} role, "
                "which SPEC 2.1's supervision chain does not contain and SPEC 2's table gives no "
                "reporting access. A role with no grain written down holds nothing here until "
                "somebody writes one, which is the same fail-closed choice as the scope grain "
                "rule's ELSE false."
            )

        if assignment.role is AssignmentRole.LEAD_FACULTY:
            leads.add(assignment.person_id)
            continue

        node_id = _scope_node(assignment, level)
        if node_id is None:
            raise UnknownAssignmentError(
                f"assignment {assignment.assignment_id} holds the {assignment.role.value} role and "
                f"carries no {level} scope reference. SPEC 2.1's scope table and the schema's "
                "scope grain rule both say it must, so this row was written past the constraint "
                "that refuses it."
            )
        rooted[level].add(node_id)

    granted = _lead_faculty_grant(session, leads)
    for level, node_ids in rooted.items():
        if node_ids:
            subtree = Purview.of(
                {level: frozenset(node_ids), **_nodes_beneath(session, level, node_ids)}
            )
            granted = granted.union(subtree)
    return granted


def own_grant(session: Session, *, assignment_id: UUID) -> Purview:
    """The own grant of one assignment: its scope node restricted by role grain.

    SPEC §2.1: "with the own grant restricted by role grain: a Lead Faculty's
    grant is only the courses they lead (never sibling leads' courses, at any
    point in the union); a chair's is the department subtree; a dean's the
    college."

    This is one term of §2.1's definition. The union over everything
    transitively reporting to the assignment is `transitive_purview`.
    """
    row = session.execute(_ASSIGNMENT, {"assignment_id": assignment_id}).mappings().first()
    if row is None:
        raise UnknownAssignmentError(
            f"no assignment {assignment_id} exists, so it grants nothing. An empty purview is a "
            "real state — a lead with no mapped courses has one — so a missing row is reported "
            "rather than answered."
        )
    return _own_grant_of(session, _Assignment.of(row))


def _assignments_of(session: Session, person_id: UUID) -> list[_Assignment]:
    """Every assignment one person holds, converted, in assignment-key order."""
    return [
        _Assignment.of(row)
        for row in session.execute(_ASSIGNMENTS_OF_PERSON, {"person_id": person_id}).mappings()
    ]


def _chaired_courses_and_those_with_a_lead(
    session: Session, assignments: Sequence[_Assignment]
) -> tuple[frozenset[UUID], frozenset[UUID]]:
    """The courses in the departments these `CHAIR` rows hold, and which of them have a lead.

    The one statement of the chair's walk to a department's courses with a lead.
    `lead_review_courses` keeps the first set less the second (the chair reviews
    an unled course), and `chaired_courses_with_a_lead` answers the second (the
    chair reads a led course's policy and cannot set it). Every other role is
    ignored, and a chair row with no department is a row the scope grain rule
    refuses, so it contributes nothing rather than raising.
    """
    departments = {
        held.department_id
        for held in assignments
        if held.role is AssignmentRole.CHAIR and held.department_id is not None
    }
    chaired = _nodes_beneath(session, "department", departments)["course"]
    if not chaired:
        return frozenset(), frozenset()
    led = frozenset(session.execute(_COURSES_WITH_A_LEAD, {"course_ids": list(chaired)}).scalars())
    return chaired, led


def lead_review_courses(session: Session, *, person_id: UUID) -> Mapping[UUID, AssignmentRole]:
    """The courses this person's own leadership grants put under moderation review, and the role.

    SPEC §5.2 routes a harmful comment to "the course's Lead Faculty review
    queue", and §2.1 sends a course with no mapping to its department chair. So
    the answer is, for each course, the one role whose grant covers it here
    (E6-05, decision 3):

      - `LEAD_FACULTY` for every course this person leads, from the mapping and
        never from the assignment's own course (`_lead_faculty_grant`), and only
        when they hold a `LEAD_FACULTY` assignment at all;
      - `CHAIR` for every course in a department they chair **that has no lead**.
        A chair's own grant is the whole department subtree (`_own_grant_of`),
        and this is narrower on purpose: a mapped course's comments are its
        lead's to review, and a chair given them too would be a second reviewer
        the spec does not name.

    The two sets cannot overlap: a course is led or it is not. A person who both
    leads a course and chairs its department is answered `LEAD_FACULTY` for it.

    **Own grants of these two roles only, never the walk.** An instructor
    assignment is ignored, so a lead who also teaches a sibling section never
    reaches that sibling course through it (SPEC §4.1 item 2). An assistant
    dean's own grant is empty, and a dean or vice president is not a reviewer
    §5.2 names, so each answers an empty mapping, which the caller refuses.
    """
    assignments = _assignments_of(session, person_id)
    covered: dict[UUID, AssignmentRole] = {}
    if any(held.role is AssignmentRole.LEAD_FACULTY for held in assignments):
        for course_id in _lead_faculty_grant(session, {person_id}).course_ids:
            covered[course_id] = AssignmentRole.LEAD_FACULTY
    chaired, led_by_somebody = _chaired_courses_and_those_with_a_lead(session, assignments)
    for course_id in chaired - led_by_somebody:
        covered[course_id] = AssignmentRole.CHAIR
    return covered


def chaired_courses_with_a_lead(session: Session, *, person_id: UUID) -> frozenset[UUID]:
    """The courses of a department this person chairs that have a lead: theirs to read, not set.

    E7's ruling 5: a chair sets the response policy for the department's
    courses that have no lead (`lead_review_courses` answers those as `CHAIR`),
    and for a course that has a lead "the chair reads the policy and cannot
    change it". This is that second set, and it grants nothing but the read of
    the setting. Disjoint from `lead_review_courses`' `CHAIR` courses by
    construction, and it may overlap its `LEAD_FACULTY` courses for a person who
    leads a course of the department they chair; the caller treats a course it
    can set as settable.

    The department walk is `_chaired_courses_and_those_with_a_lead`, the same
    statement `lead_review_courses` uses, so the two cannot disagree about which
    departments a person chairs or which of their courses have a lead.
    """
    _, led_by_somebody = _chaired_courses_and_those_with_a_lead(
        session, _assignments_of(session, person_id)
    )
    return led_by_somebody


# The most assignments one supervision chain can hold. The rank rule on
# `role_assignment` lets an edge run only from a role to one strictly above it in
# INSTRUCTOR, LEAD_FACULTY, CHAIR, ASSISTANT_DEAN, DEAN, VP_ACADEMICS (ADR 0044),
# so no chain is longer than that list, and SPEC §2.1 says the graph is "at most
# six assignments deep".
_DEEPEST_CHAIN: Final[int] = 6


def _clamped_subtree(session: Session, root: _Assignment) -> list[_Assignment]:
    """`root` and every assignment its purview takes an own grant from, walked level by level.

    Breadth-first down `reports_to`, one statement per level for the whole level.
    **A `LEAD_FACULTY` assignment is reached and never walked through** — the
    lead clamp: a lead's purview is its own grant only, so nothing that reports
    to a lead reaches the lead or anyone above it through the lead. SPEC §2.1: a
    Lead Faculty's grant is "only the courses they lead (never sibling leads'
    courses, at any point in the union)", and an instructor assignment on a
    sibling lead's course may legally report to a lead.

    It walks assignment ids. A walk by person would merge a two-hat person's
    instructor edge into their lead hat.

    A chain deeper than the rank rule allows is refused rather than walked: it
    means the rule that bounds the graph is gone, and a walk that kept going
    would be a walk with no bound.
    """
    reached = [root]
    frontier = [root]
    levels_walked = 0
    while parents := [
        held.assignment_id for held in frontier if held.role is not AssignmentRole.LEAD_FACULTY
    ]:
        if levels_walked == _DEEPEST_CHAIN:
            raise RuntimeError(
                f"assignment {root.assignment_id} heads a supervision chain longer than "
                f"{_DEEPEST_CHAIN} assignments. The supervision rank rule (ADR 0044) makes that "
                "impossible, so the rule is not holding, and the walk stops rather than run "
                "without a bound."
            )
        frontier = [
            _Assignment.of(row)
            for row in session.execute(_REPORTS_TO_ANY_OF, {"assignment_ids": parents}).mappings()
        ]
        reached.extend(frontier)
        levels_walked += 1
    return reached


def _transitive_purview_of(session: Session, root: _Assignment) -> Purview:
    """`transitive_purview` for a row already in hand. See there."""
    return _own_grants_of(session, _clamped_subtree(session, root))


def transitive_purview(session: Session, *, assignment_id: UUID) -> Purview:
    """SPEC §2.1's full purview of one assignment, with the lead clamp.

    "Purview(assignment) = own grant union the purviews of all assignments
    transitively reporting to it." So it is the assignment's own grant
    (`own_grant`) together with the purview of every assignment that reports to
    it, recursively — and, because a union of unions is one union, that is the
    union of the own grants of every assignment in its reporting subtree.

    **The lead clamp.** A `LEAD_FACULTY` assignment's purview is its own grant
    only, whatever reports to it. So the subtree stops at every lead: the lead's
    own grant is in it and nothing beneath the lead is. An instructor on a
    sibling lead's course who reports to lead A adds nothing to A, nor to A's
    chair through A. The chair still reaches that section if it lies in the
    chair's own department, through the department grant.

    **The cost** is one statement per level of the graph, plus a fixed number
    for the own grants of everything reached (`_own_grants_of`), so it grows with
    depth and not with how many assignments a level holds.

    Refuses a `CARE` or `ADMIN` assignment as `own_grant` does, and an unknown
    key with `UnknownAssignmentError`: an empty purview is a real state, so a
    missing row is reported rather than answered.
    """
    row = session.execute(_ASSIGNMENT, {"assignment_id": assignment_id}).mappings().first()
    if row is None:
        raise UnknownAssignmentError(
            f"no assignment {assignment_id} exists, so it grants nothing. An empty purview is a "
            "real state — a lead with no mapped courses has one — so a missing row is reported "
            "rather than answered."
        )
    return _transitive_purview_of(session, _Assignment.of(row))


def _leadership_grants(session: Session, person_id: UUID) -> tuple[LeadershipGrant, ...]:
    """One `LeadershipGrant` per leadership assignment this person holds, in key order.

    Leadership assignments only: `LEAD_FACULTY`, `CHAIR`, `ASSISTANT_DEAN`,
    `DEAN` and `VP_ACADEMICS` (`LEADERSHIP_ROLES`). An `INSTRUCTOR` assignment is
    reached through an instructor session and never merged into a leadership
    scope, and `CARE` and `ADMIN` hold no reporting purview at all. Each
    assignment is walked on its own, by its id.
    """
    return tuple(
        LeadershipGrant(held.assignment_id, held.role, _transitive_purview_of(session, held))
        for held in _assignments_of(session, person_id)
        if held.role in LEADERSHIP_ROLES
    )


def _union_of(grants: Sequence[LeadershipGrant]) -> Purview:
    """The union of the purviews these grants carry."""
    union = Purview.empty()
    for grant in grants:
        union = union.union(grant.purview)
    return union


def holds_care(session: Session, *, person_id: UUID) -> bool:
    """Does this person hold a live `CARE` assignment? The only supported way to ask.

    SPEC §6.2 makes Care the one role that can re-identify a student, and E0-11 is
    explicit about where the answer comes from: an actor holds Care because they
    hold a live `CARE` role assignment, "never because of anything in an LTI or
    OIDC claim". The platform administrator controls what a claim says, so a
    claim-to-Care mapping would hand them identity access;
    `tests/unit/test_care_is_not_reachable_from_a_claim.py` sweeps for a module
    that both reads a claim and names the role.

    Both directions cost something and they are not symmetric. A false *no* closes
    §6.2's queue for a student who has disclosed self-harm. A false *yes* hands a
    chair a route to a name, with the audit log recording the access as legitimate
    because by then it is.
    """
    answer = session.execute(
        _HOLDS_A_LIVE_CARE_ASSIGNMENT,
        {"person_id": person_id, "care": AssignmentRole.CARE.value},
    ).scalar_one()
    return bool(answer)


def holds_leadership(session: Session, *, person_id: UUID) -> bool:
    """Does this person hold a live assignment in SPEC §2's reporting chain? (E1-12)

    SPEC §7.3 authorizes a roster sync on a launch "by an instructor **or any
    leadership role**", and §2.1 makes a role a `role_assignment` row rather than
    anything a launch says — the administrator of a platform writes what its
    launches claim, and a limb read out of the roles claim would let them hand
    themselves a section's whole roster of names and email addresses.
    `app.services.provisioning` asks this once a launch's subject has resolved to
    a person, and only when the claim-based half has already said no.

    **It says the limb applies, not that it reaches this context.** Whether the
    person's assignments cover the launch's own course is `leadership_grant_covers`
    below, which E2-02 added and which the same caller asks straight after this
    one — the E1 boundary review's M9 was that nobody asked it at all.

    **Here rather than at the caller**, and that placement is the rule rather than
    a preference: `public.assignment_scope` is unfiltered — nothing in the
    database narrows it — so every read of it goes through this module, where
    §2.1's scope rules are written. `tests/unit/test_the_org_views_are_read_only_
    through_the_grant.py` is the invariant that holds it, and it names this file
    as where a new predicate belongs.

    **It is a predicate about a role and not a purview**, which is why it sits
    beside `holds_care` rather than inside `resolve_scope`. It answers whether a
    launch may trigger a write of the tool's own; it scopes no read and returns no
    node. `LEADERSHIP_ROLES` is the enumerated set, and `CARE`, `ADMIN` and
    `INSTRUCTOR` are outside it deliberately — the first two hold no rank in the
    supervision chain (§2.1), and an instructor is §7.3's other limb, authorized
    by the launch's own LIS role against a different source.

    Both directions cost something and they are not symmetric. A false *no* is a
    dean's section discovered late, which is what E1-10 shipped on purpose. A
    false *yes* points a scheduled sync at a roster §7.3 does not authorize, and
    that roster is names and email addresses.
    """
    answer = session.execute(
        _HOLDS_A_LEADERSHIP_ASSIGNMENT,
        {"person_id": person_id, "roles": [role.value for role in LEADERSHIP_ROLES]},
    ).scalar_one()
    return bool(answer)


def leadership_grant_covers(
    session: Session,
    *,
    person_id: UUID,
    prefix_id: UUID,
    course_id: UUID | None,
    section_id: UUID | None,
) -> bool:
    """Do this person's leadership assignments reach the context a launch came from? (E2-02)

    `holds_leadership` above answers whether §7.3's second limb applies at all;
    this answers whether it applies *here*. The E1 boundary review's M9 is the
    gap between the two: the limb "admits any holder of a live leadership
    assignment as a staff-launch trigger with no reference to the launch's
    context", so a Lead Faculty enrolled as a Learner in a sibling lead's course
    could launch from it and bind that section — which §2.1 refuses in as many
    words, "a Lead Faculty's grant is only the courses they lead (never sibling
    leads' courses, at any point in the union)".

    **The answer is the person's full leadership purview** — the union of
    `transitive_purview` over their leadership assignments only (ADR 0199), so an
    assistant dean's launch into a supervised chair's department binds — and it is
    checked at three grains: the section this launch is
    bound to, the course its label names, or the prefix above that course. A
    `None` at either of the first two is a row that does not exist yet and never
    matches; the prefix always does exist, because a launch whose prefix the org
    does not hold is `unknown_prefix` before this is asked.

    **Prefix-or-below is what keeps the first launch working**, and it is this
    ticket's design answer (ADR 0108). A dean's legitimate first launch into a
    brand-new course is a launch whose course is in nobody's course set, by
    construction — Pulse has never heard of it — so a condition written over the
    course or the section alone would refuse the one launch §7.3 relies on to
    discover a section at all. A dean's own grant lists every prefix under their
    college (`_nodes_beneath`), so the prefix is both the thing that makes that
    launch legitimate and the thing a wrong-college launch fails on.

    **The claim limb is deliberately not gated by this.** The LTI roles claim is
    context-scoped: it states what the launching person is *in the course they
    launched from*, so an Instructor claim already carries the fact this
    predicate exists to establish, and `app.services.provisioning` asks nothing
    here for that limb. Gating both limbs is the natural over-application and it
    would stop every real instructor Pulse holds no assignment for from
    discovering their own section — which is most of them.

    **The lead clamp holds here too.** A lead's purview is its own grant only, so
    a lead's launch into a sibling lead's course is refused however the graph
    beneath the lead is drawn.

    **Both directions cost something and they are not symmetric**, in the same
    direction §7.3's own cost argument runs. A false *no* is a section discovered
    late: this launch binds nothing, the section stays unknown, and the real
    instructor's next launch discovers it through the claim limb. A false *yes*
    stores a roster address permanently and points the scheduled sync — which
    calls with the tool's own credentials — at a class the launcher's records do
    not reach, and takes the `(course, term, section_code)` name with it under
    ADR 0091's first-writer-wins.

    **Here rather than at the caller**, for the reason every predicate in this
    section gives: `public.assignment_scope` is unfiltered, so every read of it
    lives in this module (`tests/unit/test_the_org_views_are_read_only_through_
    the_grant.py`). It runs no SQL of its own — it reads the leadership grants
    `resolve_scope` reads.
    """
    granted = _union_of(_leadership_grants(session, person_id))
    return (
        (section_id is not None and section_id in granted.section_ids)
        or (course_id is not None and course_id in granted.course_ids)
        or prefix_id in granted.prefix_ids
    )


def teaching_instructor_assigned(session: Session, *, person_id: UUID, section_id: UUID) -> bool:
    """Does this person already hold the `INSTRUCTOR` grant over this section?

    Asked by E1-11's roster sync before it writes one, so that an hourly run does
    not add a second identical grant every hour. SPEC §2.1 puts no uniqueness rule
    on `role_assignment` — two chairs of one department is a shape no ticket rules
    out — so nothing in the database refuses the duplicate, and the writer has to
    ask.

    **It lives here because the view does.** E0-41's rule is that
    `public.assignment_scope` is read through this module and nowhere else, and
    `tests/unit/test_the_org_views_are_read_only_through_the_grant.py` enforces it.
    The sync holds no privilege on `role_assignment` at all — it adds and ends the
    grant through two definers (ADR 0096, ADR 0183) — so this view is not merely
    the tidy way for it to ask, it is the only way.

    **Not an authorization decision**, and the difference matters for how it fails.
    `guard_write` is what decides whether the sync may write the row at all; this
    only says whether the row is already there. A false *yes* leaves a real
    instructor without the section's report, and a false *no* writes a duplicate
    grant to somebody who already had it — neither widens anybody's purview, which
    is why this is a plain predicate and not a `ScopedReader` method.
    """
    answer = session.execute(
        _HOLDS_THE_TEACHING_INSTRUCTOR_GRANT,
        {
            "person_id": person_id,
            "role": LMS_OWNED_ASSIGNMENT_ROLE.value,
            "section_id": section_id,
        },
    ).scalar_one()
    return bool(answer)


def taught_or_once_taught_section_ids(session: Session, *, person_id: UUID) -> set[UUID]:
    """Which sections does this person teach now, or did they teach before the roster ended it?

    `taught_section_ids` (the live grants) united with every section whose
    teaching grant a roster walk ended, from `ended_teaching_grant` (ADR 0183).
    ADR 0190's rule keeps a leader's own taught sections out of their review
    queue, their leader door and their exclusion log, because the instructor
    door refused them that held text; a grant the roster ended last week does not
    make them a stranger to the section, so it stays out too (E6-09, done-when 5).

    **An authorization decision, and it only narrows.** A false *yes* hides a
    section from one leader's review, which another reviewer of the course still
    sees; a false *no* would show a former instructor the held text of their own
    section. The reverse case, a leader who starts teaching a section after
    reviewing it, is ADR 0190's accepted residual.
    """
    return taught_section_ids(session, person_id=person_id) | set(
        session.execute(_ONCE_TAUGHT_SECTIONS, {"person_id": person_id}).scalars()
    )


def taught_section_ids(session: Session, *, person_id: UUID) -> set[UUID]:
    """Which sections does this person hold the `INSTRUCTOR` grant over? (E4-18)

    The set form of the question `teaching_instructor_assigned` above asks about
    one section. E4-18's list route is the caller: every report route takes a
    section id and nothing a client holds supplies one, so this is what an
    instructor's page discovers her own sections from.

    **It lives here because the view does.** E0-41's rule is that
    `public.assignment_scope` is read through this module and nowhere else, and
    `tests/unit/test_the_org_views_are_read_only_through_the_grant.py` enforces it.
    A join written in the reporting service would be a second answer to "whose
    sections are these", and the first thing that diverges is a widening nobody can
    see.

    **This one *is* an authorization decision**, which is where it parts company
    with both its neighbours. They answer questions a caller acts on and neither
    opens anything; this answers what a reader is shown. A false *yes* names a
    section she has no relationship with, on the page she reads every Monday, and a
    false *no* hides a section she teaches and leaves her unable to open its report
    at all. It is a plain predicate rather than a `ScopedReader` method for the
    reason §2.1 gives: a teaching grant is the assignment's own `section_id` and
    expands through no containment, so there is no purview to compute.

    **Ids only, deliberately.** What a section is *called* — its code, and FIX-01
    item 2's governed label — is composed in `app.services.reporting`, over rows
    this module has no business reading. That keeps the scope decision one query
    with three conditions, which is the thing a reviewer has to be able to read in
    one sitting.

    **Every section she holds the grant over, past terms included.** `role_assignment`
    carries no validity dates (E0-09), so "live" reads as "exists" here exactly as
    it does in `_HOLDS_A_LIVE_CARE_ASSIGNMENT` above, and this set is the same set
    the report routes already serve one section at a time. Narrowing it here and not
    there would let a reader page to a section the report then refuses.
    """
    return set(
        session.execute(
            _TEACHING_INSTRUCTOR_SECTIONS,
            {"person_id": person_id, "role": LMS_OWNED_ASSIGNMENT_ROLE.value},
        ).scalars()
    )


def teaching_instructors_of(session: Session, *, section_id: UUID) -> set[UUID]:
    """Who holds the `INSTRUCTOR` grant over this section? (E5-14)

    The people form of `teaching_instructor_assigned`: the same three conditions,
    with the person left open. `app.services.benchmarks` asks it to seal a
    section's comparison figures once for each person who can read that
    section's report, against the sections that person teaches
    (`taught_section_ids`) — each of them knows their own sections' answers and
    can subtract them, and no one of them knows a co-instructor's.

    **It lives here because the view does** — E0-41's rule that
    `public.assignment_scope` is read through this module and nowhere else.

    **Not an authorization decision.** It opens nothing: the report route still
    decides who may read. A section nobody teaches answers the empty set, and its
    figures are then sealed on their own population alone — which nobody can
    read, because every report route requires the teaching grant.
    """
    return set(
        session.execute(
            _TEACHING_INSTRUCTORS_OF_A_SECTION,
            {"role": LMS_OWNED_ASSIGNMENT_ROLE.value, "section_id": section_id},
        ).scalars()
    )


def teaching_instructor_grants(session: Session, *, section_id: UUID) -> dict[UUID, UUID]:
    """Every `INSTRUCTOR` grant over this section, as `{assignment id: person id}`. (E5.1-02)

    Asked by the roster sync after a complete walk, to find the grants the roster
    no longer supports: each grant whose person the walk did not list as a
    teaching member is ended through `public.end_teaching_instructor`, which takes
    the assignment's id. `teaching_instructors_of` above answers the people alone
    and cannot say which row to end.

    **It lives here because the view does** — E0-41's rule that
    `public.assignment_scope` is read through this module and nowhere else. The
    sync holds no `SELECT` on `role_assignment`, so this is the only way it can
    ask.

    **Not an authorization decision.** It opens nothing. What it feeds is a
    narrowing: a grant missing from this answer is a grant the sync leaves in
    place, and the definer refuses any row that is not a section-scoped
    `INSTRUCTOR` whatever this answers.
    """
    return {
        row.assignment_id: row.person_id
        for row in session.execute(
            _TEACHING_INSTRUCTOR_GRANTS_OF_A_SECTION,
            {"role": LMS_OWNED_ASSIGNMENT_ROLE.value, "section_id": section_id},
        )
    }


def section_scoped_assignees(session: Session, *, section_id: UUID) -> set[UUID]:
    """The people holding an assignment scoped to this section — its staff (EE-M1).

    Asked by SPEC §3.4's participation sweep before it delivers a score. A roster
    container carries everybody the platform lists, instructors included. Until
    E5.1-02 the sync wrote an `enrollment` row for each of them; it now writes none
    for a member listed as Instructor and closes an open one, but a row first seen
    and closed on the same day still covers that day (ADR 0183). Without this the sweep would post a participation
    percentage into the gradebook column of the person doing the grading, computed
    from the weeks they did not fill in their own survey. §3.4 makes the score a
    student's: "completed items ÷ total items across the student's elapsed weeks".

    **It answers people, not members.** The caller holds `user` ids and this
    answers `person` ids, because those are two different keys for two different
    things (ADR 0024) and the hop between them is a definer call the caller makes —
    `app.services.identity.person_for_user`. Answering members would put that hop
    inside this module and give it a second thing to be about.

    **It lives here because the view does.** E0-41's rule is that
    `public.assignment_scope` is read through this module and nowhere else, and
    `tests/unit/test_the_org_views_are_read_only_through_the_grant.py` enforces it.
    `teaching_instructor_assigned` above is the neighbouring question — one person,
    one section, one role — and this is the set, for a caller that has to sort a
    roster into two kinds of people.

    **Not an authorization decision**, exactly as its neighbour is not: it opens
    nothing and refuses nothing, and what a caller does with the answer is the
    caller's rule. A false *yes* withholds a grade from a student; a false *no*
    posts one to a member of staff. Neither widens anybody's purview.
    """
    return set(session.execute(_SECTION_SCOPED_ASSIGNEES, {"section_id": section_id}).scalars())


def resolve_scope(
    session: Session,
    *,
    person_id: UUID,
    n_threshold: int | None = None,
    settings: Settings | None = None,
) -> ActorScope:
    """One person's leadership scope, as one value every leadership read is handed.

    The purview is the union of `transitive_purview` over the person's
    **leadership** assignments only — `LEAD_FACULTY`, `CHAIR`, `ASSISTANT_DEAN`,
    `DEAN` and `VP_ACADEMICS` — and `grants` carries one `LeadershipGrant` per
    such assignment (ADR 0199). SPEC §2.1 resolves a view "from an assignment (or
    a union of them), never from a person type", and a person with two leadership
    hats — a chair who also leads courses — gets both, each walked by its own
    assignment id. A person holding no leadership assignment gets an empty scope.

    **Its one caller is `app.api.deps.leadership_scope`**, which passes the
    verified session's own person. This answers about any person it is given, so
    a second caller would be a second place a request could name whose scope is
    read.

    **An instructor hat is never merged in.** It is reached through an instructor
    session, so a chair who teaches a section in another department does not
    find that section in their leadership tree.

    **Assignments with no reporting purview are skipped rather than raising**, and
    the difference from `own_grant` is deliberate. Asking `own_grant` for a `CARE`
    assignment is a caller mistake and is refused; asking what a *person* may see
    is an ordinary question for somebody who holds a Care hat and a leadership
    hat, and §2.1 calls that combination legal — "it is capabilities that do not
    compose, not people". So the Care row contributes nothing to the purview and
    `holds_care` answers separately. `ADMIN` is skipped for the same reason and a
    different one: §2's table gives it no reporting access.

    The Care assignment is scoped to the institution (§2's table), so a resolver
    that unioned it in would hand an adjunct every college in the university —
    the largest widening available in this product, arriving with no error, no log
    line and nothing on screen to distinguish it from a VP's own view.

    `n_threshold` defaults to the institution's configured value (§4, "Threshold
    value is configurable (default 5)"). The parameter exists for the callers E4
    will write — a recomputation over a past week, a job answering for another
    institution — and an override that were quietly ignored would be worse than no
    parameter at all, since the caller believes it applied.

    `settings` is the configuration that default is read from. A caller that
    already holds one — every route does, on `request.app.state.settings` — should
    pass it, because building a fresh `Settings` re-reads and re-validates the
    whole environment on every call. When it is omitted the read happens here, at
    call time, exactly as it always did: this is deliberately not cached, because
    a process that read its configuration once at import time would fail on
    whichever variable the machine running the suite happens not to have set yet.
    """
    grants = _leadership_grants(session, person_id)

    if n_threshold is None:
        configured = Settings() if settings is None else settings
        threshold = configured.n_threshold_default
    else:
        threshold = n_threshold
    return ActorScope(
        person_id=person_id,
        purview=_union_of(grants),
        holds_care=holds_care(session, person_id=person_id),
        n_threshold=threshold,
        grants=grants,
    )


# ---------------------------------------------------------------------------
# Reading, scoped.
# ---------------------------------------------------------------------------


class ScopedReader:
    """The E0-10 read views, with the purview checked before each one is reached.

    E0-11's scope asks for "a `ScopedSession`-style helper or query dependency
    that makes the E0-10 views the default read path and makes bypassing it
    visibly deliberate". This is it: the helpers in `app.views_sql.queries` take
    the keys they are given and filter by nobody, which is right for them — a
    second half-answer to "who is asking" living down there is how the two come
    apart — so the scope check lives here, once per view.

    Bypassing it means calling `app.views_sql.queries` directly, which is one
    import — and E0-41 mechanised that. The sweep in
    `tests/unit/test_the_org_views_are_read_only_through_the_grant.py` fails any
    module under `backend/app/` outside this one that makes that import; its SQL
    half likewise fails any module that runs SQL naming a relation in the
    policed inventory, outside the exempt locations that sweep file records —
    this file among them, each with its reason beside it. The inventory is
    parsed at test time from the catalog under `backend/app/views_sql/`, so the
    set moves with the catalog and no count written here can go stale. Until
    then it was a property a reviewer had to notice in a diff, and a property
    nothing executes is a comment (`docs/MISTAKES.md` entry 9).
    """

    def __init__(self, session: Session, scope: ActorScope) -> None:
        self._session = session
        self._scope = scope

    def section_roster(self, *, section_id: UUID) -> Sequence[SectionRosterRow]:
        """Everybody enrolled in one section, if the section is inside the purview.

        §4.1 invariant 2 asked at the read path: a lead asking for a section in
        another lead's course is refused rather than answered with an empty list.
        """
        if section_id not in self._scope.purview.section_ids:
            raise OutOfPurviewError(
                f"section {section_id} is not in the purview resolved for person "
                f"{self._scope.person_id}, so its roster was not read. SPEC 4.1 invariant 2: a "
                "Lead Faculty assignment never grants sibling leads' courses, at any point in the "
                "purview union computation."
            )
        return section_roster(self._session, section_id=section_id)

    def section_enrollment_counts(self, *, course_id: UUID) -> Sequence[SectionEnrollmentCount]:
        """One count per section of one course, if the course is inside the purview.

        Course grain is where a lead's purview is defined (§2.1, "only the courses
        they lead"), and an aggregate is not a softer disclosure than a roster:
        §4.1 item 4 keeps aggregate language away from individuals because a count
        over a small section, read beside a roll-up somebody else can see, is a
        fact about people.
        """
        if course_id not in self._scope.purview.course_ids:
            raise OutOfPurviewError(
                f"course {course_id} is not in the purview resolved for person "
                f"{self._scope.person_id}, so its enrollment counts were not read. SPEC 2.1 gives "
                "a Lead Faculty 'only the courses they lead', and 2.1 gives leads the hierarchy "
                "view precisely so that a peer's courses have nowhere to appear."
            )
        return section_enrollment_counts(self._session, course_id=course_id)


def scoped_reader(session: Session, scope: ActorScope) -> ScopedReader:
    """A reader bound to one resolved scope. See `ScopedReader`."""
    return ScopedReader(session, scope)


# ---------------------------------------------------------------------------
# Writes the application may not make.
# ---------------------------------------------------------------------------

# SPEC §2.1's ownership list, as the tables it lands on. Four of its five items —
# courses, sections, section codes, enrollments — live on `course`, `section` and
# `enrollment`, so refusing the table answers most of the list without reading a
# column name and catches an LMS-owned column that nobody prefixed.
#
# **`user` is here because `user.lms_user_id` is the `sub` claim verbatim** (ADR
# 0014): the platform supplies it and Pulse never edits it. §4 keys every response
# to that value, and the launch path that creates the row is a sanctioned writer
# in the same way E1's roster sync must be for the other three.
#
# **`user_identity` is deliberately absent.** It is LMS-sourced and it is
# identity-marked (ADR 0022), and what protects it is E0-10's grant model —
# `pulse_app` holds no privilege of any kind on it — not this chokepoint. Adding
# it here would put a second, weaker statement of that guarantee in the
# application layer, where deleting it changes nothing and reading it suggests the
# protection lives in Python.
#
# **What this grain does not catch**, said here so nobody has to infer it: a
# Pulse-owned *writable* column landing on `course`, `section` or `enrollment`
# later is refused along with everything else on that table. `course.level` is
# already a non-LMS column there and is saved only by being a stored generated
# column that nothing can write (ADR 0015). ADR 0014's open half — that an
# unmarked LMS-owned column is invisible to a name-based check — stays open, and
# E0-21 carries the residue. Nothing here should be cited as closing it.
LMS_OWNED_TABLES: Final[frozenset[str]] = frozenset({"course", "section", "enrollment", "user"})

# The one row on a table the application otherwise writes freely. SPEC §2.1's
# fifth owned item is the teaching instructor, its chain is
# `INSTRUCTOR(section) → LEAD_FACULTY(course) → …` over **role assignments**, and
# §8 puts those on `role_assignment`. That row is not a stale attribute: §2.1
# computes purview from exactly these rows, so an application write path able to
# create one is a path that can grant somebody oversight of a section, with the
# moderation view and the report that hang off it.
#
# Every other role on that table is Pulse's to write — §2.1 builds the people
# graph "top-down in the admin console" — so the refusal reads the role rather
# than the table. A chokepoint that refused `role_assignment` outright would
# satisfy every denial test and leave §6.3's People editor unable to write
# anything.
LMS_OWNED_ASSIGNMENT_ROLE: Final[AssignmentRole] = AssignmentRole.INSTRUCTOR

ROLE_ASSIGNMENT_TABLE: Final[str] = "role_assignment"


@dataclass(frozen=True)
class WriteSanction:
    """One writer's permission to pass this chokepoint for a named set of tables.

    A value rather than a handle onto the catalog, and frozen rather than merely
    conventional: a caller holding a mutable sanction could add a table to the
    very object `sanction_for` handed it, and if that object shared the catalog's
    own `frozenset` the widening would reach every later caller in the process
    with nothing recording it.

    **Holding one is not the permission.** `guard_write` reads
    `SANCTIONED_WRITERS` and never `sanction.tables`, so a hand-built sanction
    naming an uncatalogued writer — or naming more tables than the catalog grants
    its writer — is refused exactly as no sanction at all would be. That is the
    difference between this and a bypass flag, and ADR 0090 is the record.
    """

    writer: str
    tables: frozenset[str]


# Every writer sanctioned to pass this chokepoint, and the tables each may write.
# **The authority, not the argument** (ADR 0090): `guard_write` consults this
# mapping, so a caller cannot authorize itself by constructing the sanction it
# wants.
#
# **Three entries, and adding a fourth is the conversation.** `launch_provisioning`
# is `app.services.provisioning`, E1-10's launch-time ingestion: SPEC §2.1 gives
# courses and sections two arrival paths, "hourly roster sync + launch-time
# ingestion", and §7.3 makes the first staff launch of a section the only thing
# that discovers it at all. `user` is here because ADR 0045 already named "the
# launch path that creates a `user` row" as a sanctioned writer when it put `user`
# in the guarded set.
#
# **`enrollment` is deliberately absent from the launch writer**, and so is the
# `INSTRUCTOR` `role_assignment` row: a launch proves one person's presence, not a
# roster.
#
# `roster_sync` is `app.services.roster_sync`, E1-11's hourly NRPS pull — §2.1's
# other arrival path. It takes three: `user`, because a member this deployment has
# never seen needs a row before anything can be enrolled; `enrollment`, which is
# what §3.4's participation windows are computed from; and `role_assignment`, for
# the teaching instructor's row, which is the first entry in this catalog that is a
# row-grain rule rather than a table (see `guard_write` below).
#
# **`course` and `section` are deliberately not in the sync's entry**, and the
# absence is the load-bearing part: SPEC §7.3 gives a section exactly one way to be
# discovered — the staff launch that stores its roster address — so a sync able to
# write `section` would be inventing a section from a roster it could only fetch
# because that section already existed.
#
# `grade_passback` is `app.services.grading`, E3-05's line-item creation, and it
# takes `section` alone. SPEC §3.4 gives every section one AGS line item "created
# by the tool on first launch", and the id of the one this tool creates lives on
# `section.ags_line_item_url` (ADR 0128) — so the passback path is a writer of a
# table `LMS_OWNED_TABLES` names, and it passes this chokepoint the way the other
# two do rather than being excused from it. ADR 0136 is the record.
#
# **The rest of `section` is not in the entry, and the database says so a second
# way.** This catalog cannot express a column, so it grants the table and the
# grant `pulse_app` actually holds is column-scoped: `UPDATE (ags_line_item_url)`
# and nothing else (`backend/app/views_sql/grade_passback_grants_v002.sql`). The
# section code, the binding columns and ADR 0021's derived calendar columns are a
# launch's discovery, and neither layer is the other's backstop.
#
# **The inventory is pinned in a test, not here** (`docs/MISTAKES.md` entry 35).
# `tests/unit/test_a_sanctioned_writer_satisfies_the_chokepoint.py` compares this
# mapping against a hand-written copy as an equality, so a writer or a table added
# here is a visible diff in a test file this module cannot shrink.
SANCTIONED_WRITERS: Final[Mapping[str, frozenset[str]]] = {
    "launch_provisioning": frozenset({"course", "section", "user"}),
    "roster_sync": frozenset({"user", "enrollment", "role_assignment"}),
    "grade_passback": frozenset({"section"}),
}


def sanction_for(writer: str) -> WriteSanction:
    """The catalogued sanction for `writer`, or a failure naming it.

    Raises `UnknownSanctionedWriterError` for a name the catalog does not hold,
    rather than answering with an empty sanction: a lookup that handed out
    something for every name would make `SANCTIONED_WRITERS` a comment, and an
    empty sanction would fail at the first `guard_write` call with a message
    about a table instead of about the name that was wrong.
    """
    tables = SANCTIONED_WRITERS.get(writer)
    if tables is None:
        raise UnknownSanctionedWriterError(
            f"{writer!r} is not a sanctioned writer. `SANCTIONED_WRITERS` in app/services/authz.py "
            f"names {sorted(SANCTIONED_WRITERS)}, and a writer is added to it in the pull request "
            "that needs it, with the sentence it rests on (ADR 0090)."
        )
    return WriteSanction(writer=writer, tables=tables)


def _catalog_grants(sanction: WriteSanction | None, table: str) -> bool:
    """Whether the catalog grants `sanction`'s writer this table.

    The catalog is read here and the sanction is read only for the name it was
    issued under. A sanction whose `tables` a caller widened, or whose `writer`
    a caller invented, grants nothing.
    """
    if sanction is None:
        return False
    return table in SANCTIONED_WRITERS.get(sanction.writer, frozenset())


def guard_write(
    *,
    table: str,
    assignment_role: AssignmentRole | None = None,
    sanction: WriteSanction | None = None,
) -> None:
    """Refuse a write to data the LMS owns. SPEC §8: "never hand-edited in Pulse."

    Called by every application write path before it writes. It answers nothing
    and raises `LmsOwnedWriteRefused` when the write is one Pulse may not make;
    see `LMS_OWNED_TABLES` above for the grain, why it is table-grained plus one
    row, and what it does not catch.

    `assignment_role` is read only for `role_assignment` and is `None` everywhere
    else, because no other table in this schema carries a row whose ownership
    depends on a column value.

    **With no `sanction` the answer is unconditional refusal on the guarded set**,
    which is the behaviour every caller in this project that is not a catalogued
    writer gets and the property ADR 0090 was designed around. With one, the
    *catalog* decides: `sanction_for` is how a writer obtains it, and a sanction
    the catalog does not back refuses exactly as none would.

    **The teaching-instructor row below reads the catalog the same way**, and E1-11
    is why. That branch was an unconditional refusal while no catalogued writer was
    granted `role_assignment`; SPEC §2.1 makes the teaching instructor LMS-owned and
    the roster is where Pulse learns who teaches a section, so the sync has to be
    able to pass it — and the alternative to passing the guard is a writer that does
    not call it, which is exactly the bypass ADR 0045 names. It mirrors the branch
    above exactly: the catalog is the authority, `sanction.tables` is never read,
    and any role but `INSTRUCTOR` on this table is Pulse's own to write.
    """
    if table in LMS_OWNED_TABLES and not _catalog_grants(sanction, table):
        sanctioned = "" if sanction is None else f" `{sanction.writer}` is not sanctioned for it."
        raise LmsOwnedWriteRefused(
            f"public.{table} holds LMS-owned data and Pulse never hand-edits it (SPEC 2.1, 8). An "
            "edit here is not rejected by the LMS and does not error: it is overwritten at the "
            "next hourly roster sync, so the symptom is a value that changes back by itself."
            f"{sanctioned}"
        )

    if (
        table == ROLE_ASSIGNMENT_TABLE
        and assignment_role is LMS_OWNED_ASSIGNMENT_ROLE
        and not _catalog_grants(sanction, ROLE_ASSIGNMENT_TABLE)
    ):
        sanctioned = "" if sanction is None else f" `{sanction.writer}` is not sanctioned for it."
        raise LmsOwnedWriteRefused(
            f"a {LMS_OWNED_ASSIGNMENT_ROLE.value} row on public.{ROLE_ASSIGNMENT_TABLE} is SPEC "
            "2.1's teaching-instructor link, which the LMS owns. It is not a stale attribute but "
            "a purview grant — 2.1 computes purview from exactly these rows — so writing one "
            "grants somebody oversight of a section. Every other role on this table is Pulse's "
            f"own, built top-down in the admin console.{sanctioned}"
        )


def raw_comments_permitted(*, response_count: int, n_threshold: int) -> bool:
    """§4's small-N suppression. **Not implemented: E4 lands it, and this raises.**

    E0-11 ships "the parameter and the call site, with the threshold read from
    `Settings`"; the rule that consumes them is E4's, and ADR 0003 generalises the
    fail-closed seam to any deferred authorization decision.

    **The rule is not the comparison this signature suggests**, which is why a
    partial implementation would be worse than none. SPEC §4: comments from
    under-threshold weeks "are not discarded — they feed the summary, and they
    surface as raw text once the section's cumulative comment volume for the term
    crosses the threshold, **batched so that timing cannot identify an author**".
    A seam that answered `False` below the threshold and `True` above it would be
    right about the easy half and silent about the batching, which is the half
    that decides whether a comment from a two-response week can be identified by
    when it appeared.
    """
    raise NotImplementedError(
        f"raw comment suppression is E4's work: {response_count} responses against a threshold of "
        f"{n_threshold} cannot be decided here. E0-11 ships the parameter and the call site. SPEC "
        "4's rule is a batching rule rather than the comparison this signature suggests — "
        "under-threshold comments feed the summary and surface later, batched so that timing "
        "cannot identify an author — and 4.1 item 3 makes what it gates an invariant."
    )


# ---------------------------------------------------------------------------
# What a session may act as: the door, the landing, and the rows that decide it.
#
# One section rather than pieces distributed among the sections above, and the
# two statements below sit here rather than with the others: a reader asking
# "which screen does this person open on" gets the whole rule — the enums, the
# map, the ordering, the SQL and the two functions — without leaving it (E1-13,
# ADR 0098).
# ---------------------------------------------------------------------------


class Door(Enum):
    """Which entry door somebody arrived at, and so which assignments may admit them.

    SPEC §2.1's table is authoritative and states the rule as a property of the
    role: every reporting role can enter through an LTI launch, leadership
    included; every role except instructor and student can *also* enter by web
    login; Care and Admin are web login only, "their work has no launch context";
    and students enter by launch only. ADR 0026 puts that on `role_assignment` as
    two stored generated columns, so entering a door is a filter over rows rather
    than a branch in Python — and this enum is what names which filter.

    A two-member enum rather than a boolean or a column name, so a router cannot
    ask for a column that does not exist and cannot pass the wrong one by getting
    an argument the wrong way round. `app/api/lti.py` passes `LAUNCH` and
    `app/api/auth.py` passes `WEB`, and those two lines are the whole of what
    either router knows about which door it is.

    **The member names are a contract with `app.services.session`**, which writes
    a session's door by name and reads it back as `Door[...]`. Renaming a member
    invalidates every session already sitting in somebody's browser.
    """

    LAUNCH = auto()
    WEB = auto()


class LandingRole(StrEnum):
    """The five views a door can land somebody on, by the testid each carries.

    The value *is* the `data-testid` the SPA's landing route puts on the page, so
    the contract a Playwright spec addresses and the contract the frontend
    implements are the same string rather than two strings that have to agree.
    `mock-idp/app/pages.py` names its own controls the same way and for the same
    reason.

    The **name**, lowercased, is the route segment — `fragment_redirect` builds
    `/app/<name>#session=` out of it and `frontend/src/router.tsx` mounts the same
    segments (ADR 0086). So both halves of this enum are a contract with the
    frontend: the name addresses the route and the value addresses the page. The
    name is also what `app.services.session` writes into a session and reads back
    as `LandingRole[...]`, so it may not be renamed without invalidating every
    session in flight.

    **Five views and eight assignment roles**, which is what `LANDING_FOR_ROLE`
    below is for: §2.1's five leadership roles differ in *purview*, which
    `transitive_purview` computes over the supervision graph, and not in which
    screen they arrive at.
    """

    STUDENT = "pulse-landing-student"
    INSTRUCTOR = "pulse-landing-instructor"
    LEADERSHIP = "pulse-landing-leadership"
    CARE = "pulse-landing-care"
    ADMIN = "pulse-landing-admin"


# Which view each assignment role opens on. All eight members of `AssignmentRole`
# are spelled out, and the five in `LEADERSHIP_ROLES` share one view because SPEC
# §2 gives leadership one entry point: what separates a chair from a dean is the
# purview `transitive_purview` computes, not the screen they arrive at.
#
# **`STUDENT` is deliberately unreachable from here.** ADR 0028: "A student holds
# no `role_assignment` row, and one cannot be written: the enum has no label for
# it." A student's access is resolved from `enrollment`, which is the whole reason
# `resolve_landing` below asks two questions rather than one.
#
# **A role this mapping does not name contributes no landing**, which is the
# fail-closed direction and the same shape as `_OWN_GRANT_ROOT` above and ADR
# 0026's positive door lists: a ninth role added to the enum by a later migration
# gets no view until somebody decides which one, and the failure reports itself
# the first time that person tries to enter rather than landing them on whichever
# screen a default happened to name.
LANDING_FOR_ROLE: Final[Mapping[AssignmentRole, LandingRole]] = {
    AssignmentRole.INSTRUCTOR: LandingRole.INSTRUCTOR,
    AssignmentRole.LEAD_FACULTY: LandingRole.LEADERSHIP,
    AssignmentRole.CHAIR: LandingRole.LEADERSHIP,
    AssignmentRole.ASSISTANT_DEAN: LandingRole.LEADERSHIP,
    AssignmentRole.DEAN: LandingRole.LEADERSHIP,
    AssignmentRole.VP_ACADEMICS: LandingRole.LEADERSHIP,
    AssignmentRole.CARE: LandingRole.CARE,
    AssignmentRole.ADMIN: LandingRole.ADMIN,
}

# Which view a person holding more than one hat opens on, highest first (ADR
# 0098). One total ordering at both doors: SPEC §2 says a launch shows the
# person's full purview rather than the launch context, so the higher-standing
# hat's screen is the useful one, and leadership over Care over admin is what
# E0-18 wrote down and nothing held — `docs/tickets/e1/carried-from-e0.md`'s
# second entry measured that reversing it left 424 tests green.
#
# **`STUDENT` is not in it, and that absence is the second half of the rule.**
# Enrollment is a fallback consulted only when no assignment lands, so an
# assignment always beats an enrollment. Inside this ordering a student landing
# would be something an assignment could lose to, and the teaching assistant
# enrolled in the course she grades would open on her own results page instead of
# her section's.
#
# E9's role switcher is §2's real answer for people with several hats and
# supersedes this ordering when it lands. Until then this is the minimal recorded
# rule, and it is pinned over every ordered pair in the unit suite and again over
# rows and real doors in the integration suite.
LANDING_PRECEDENCE: Final[tuple[LandingRole, ...]] = (
    LandingRole.LEADERSHIP,
    LandingRole.INSTRUCTOR,
    LandingRole.CARE,
    LandingRole.ADMIN,
)

# Which generated column each door is a filter over (ADR 0026). A mapping keyed by
# `Door` and written in this module, never a name a caller supplies: the template
# below is interpolated with these two values and with nothing else, so the only
# thing a caller contributes to the statement is a bound `person_id`
# (`docs/MISTAKES.md` entry 17).
_DOOR_PERMISSION_COLUMN: Final[Mapping[Door, str]] = {
    Door.LAUNCH: "permits_launch",
    Door.WEB: "permits_web_login",
}

# The roles on one person's live assignments, filtered by the door they entered
# at. Built from one template over the mapping above so the projection is written
# once, exactly as `_DESCENDANTS` is. `assignment_scope_v002.sql` is what publishes
# the two columns, and E0-41's rule — this view is read from this module and
# nowhere else — is why the filter is here rather than at the door.
#
# "Live" reads as "the row exists", as it does for the three predicates above:
# `role_assignment` carries no validity dates, so a revoked assignment is a
# deleted row. The one dated boundary in this module is the enrollment window
# below.
_ASSIGNED_ROLES_TEMPLATE = (
    "SELECT held.role AS role"
    " FROM public.assignment_scope AS held"
    " WHERE held.person_id = :person_id"
    " AND held.{column}"
)

_ASSIGNED_ROLES_AT: Final[Mapping[Door, TextClause]] = {
    door: text(_ASSIGNED_ROLES_TEMPLATE.format(column=column))
    for door, column in _DOOR_PERMISSION_COLUMN.items()
}

# Whether this user is enrolled in anything on a given day — the whole of a
# student's access (ADR 0028), and the one read in this module that names a base
# table rather than a view. See the module docstring on why that is safe here and
# on the sentence it corrects.
#
# **The window is inclusive at both ends.** ADR 0020's `'[]'` convention makes an
# end date the last *included* day, so somebody whose enrollment ends today is
# still enrolled today and somebody whose enrollment ended yesterday is not. A
# NULL `ended_on` is the open window a roster sync leaves on a member it is still
# seeing (ADR 0023), and the `IS NULL` arm is what stops three-valued logic
# answering "unknown" for every current student.
#
# `EXISTS` rather than a count: the question is whether there is any live
# enrollment at all, and a count over somebody in nine sections reads nine rows to
# answer a boolean.
_A_LIVE_ENROLLMENT = text(
    "SELECT EXISTS ("
    " SELECT 1 FROM public.enrollment AS enrolled"
    " WHERE enrolled.user_id = :user_id"
    " AND enrolled.started_on <= :today"
    " AND (enrolled.ended_on IS NULL OR enrolled.ended_on >= :today)"
    ")"
)


def chosen_landing(
    roles: Collection[AssignmentRole],
    *,
    enrolled_today: bool,
    door: Door,
) -> LandingRole | None:
    """Which view this set of roles opens on, or `None` if none of them does.

    **Pure: no session, no configuration, no IO.** `resolve_landing` below does
    the reads and this makes the decision, and the split is what lets the ordering
    be proved over inputs rather than over rows.

    `roles` is the set of roles on the person's live assignments **already
    filtered by the door's permission column**. The filtering is ADR 0026's
    column's job and this function takes its answer as given: writing the door
    rule a second time here would be one rule with two authorities, and the one an
    operator can read off the row is the one that stops being consulted
    (`docs/MISTAKES.md` entry 13).

    A role `LANDING_FOR_ROLE` does not name is **skipped** — not defaulted, which
    would land somebody on whichever screen came last in somebody's `if`, and not
    raised, which would turn an unfinished migration into a 500 on a real
    person's launch. Skipping is also why an unknown role beside a real one leaves
    the real one standing.

    `enrolled_today` is consulted only when no assignment lands, and only at the
    launch door: §2.1's table gives the student row one entry point, so somebody
    whose only claim on a view is an enrollment has none at the web login, and the
    honest answer there is the calm page rather than their results.
    """
    landings = {LANDING_FOR_ROLE[role] for role in roles if role in LANDING_FOR_ROLE}
    for landing in LANDING_PRECEDENCE:
        if landing in landings:
            return landing
    if door is Door.LAUNCH and enrolled_today:
        return LandingRole.STUDENT
    return None


def _enrolled_today(session: Session, *, user_id: UUID, settings: Settings) -> bool:
    """Is this user enrolled in anything on the institution's current day?

    **The institution's day, never UTC's and never `CURRENT_DATE`** — Todd's
    ruling on E1-11, applied to a second read. SPEC §8 makes the institution
    timezone a deployment-level setting, and a boundary evaluated in UTC puts
    everybody who launches in the evening a calendar day out.

    **The day comes from `app.services.clock`, and the second copy of it is gone**
    (E2-04, ADR 0109). This read and `app.services.provisioning`'s term lookup
    (`_term_containing_the_launch_day`) each computed the institution's day for
    itself, and the two were named at both ends because a shared helper would have
    moved a function across a module boundary. E2-04 is the ticket that made the
    move worth taking: the same question is asked by a third site, the roster sync,
    and by E2-06's window logic, and it now has one answer — the effective day,
    which on a developer's machine carries the `clock_override` offset so a week
    that is not this one can be walked through by hand.

    **Nothing about the *authorization* rule moved with it.** The window is still
    `started_on <= today AND (ended_on IS NULL OR ended_on >= today)`, and it is
    still judged in the institution's zone; what changed is only where the day
    comes from. The override applies in development alone, so no deployment's
    enrollment check can be moved by a row.
    """
    today = clock.today(session, settings=settings)
    answer = session.execute(_A_LIVE_ENROLLMENT, {"user_id": user_id, "today": today}).scalar_one()
    return bool(answer)


def resolve_landing(
    session: Session,
    *,
    door: Door,
    person_id: UUID | None,
    user_id: UUID | None,
    settings: Settings,
) -> LandingRole | None:
    """Which view this session's own identity opens on at this door, or `None`.

    E1-13, and authorization's first question: what may this session act as. The
    answer comes from the app-owned assignment model and from `enrollment`, and
    never from what a token said — the person who administers an LMS writes what
    its launches state, which is E0-09 criterion 10's whole argument.

    Two reads, in this order, and the order is the recorded decision (ADR 0098):

    1. the person's live assignments, filtered by `door`'s permission column, run
       through `chosen_landing`'s precedence;
    2. only if that lands nothing, and only at the launch door, whether the user
       holds an enrollment window containing today — ADR 0028's student.

    Assignments before enrollment is what makes staff who are also enrolled act as
    staff.

    **Only the session's own identity is ever resolved here.** Both ids come from
    `app.services.identity`, which resolved them out of the door's verified token,
    and no router passes another person's. The leadership scope holds the same
    rule structurally: `app.api.deps.leadership_scope` is the only caller of
    `resolve_scope` and takes the person from the verified session (ADR 0199).

    **Each absent id skips its own read.** A launch by a student resolves no
    `person`, a web login resolves no `user` at all, and both absent is a session
    with nothing to look up — which is the calm no-access page rather than an
    error.

    **This does IO**, so both `async def` handlers reach it through
    `run_in_threadpool` (ADR 0013): the session is synchronous and reading it on
    the event loop would block every other request on the process.
    """
    roles: list[AssignmentRole] = []
    if person_id is not None:
        roles = [
            AssignmentRole(role)
            for role in session.execute(
                _ASSIGNED_ROLES_AT[door], {"person_id": person_id}
            ).scalars()
        ]

    landed = chosen_landing(roles, enrolled_today=False, door=door)
    if landed is not None:
        return landed
    if door is not Door.LAUNCH or user_id is None:
        return None
    return chosen_landing(
        roles,
        enrolled_today=_enrolled_today(session, user_id=user_id, settings=settings),
        door=door,
    )
