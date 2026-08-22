"""The one chokepoint every entry point passes through to read anything (SPEC §13).

SPEC §13 puts it here: "`api/` routers stay thin and all real behavior lives in
`services/`", with this module the single place an actor is turned into a scope
and a scope is turned into a read. HTTP requests, Celery jobs and E9's MCP server
all come through here or they do not read data.

**SPEC §2.1 defines purview as a union, and this module builds only half of it.**
"Purview(assignment) = own grant union the purviews of all assignments
transitively reporting to it, with the own grant restricted by role grain." (The
spec writes that union as the set-theory symbol; it is spelled out here and
everywhere below, because a lone glyph in a docstring is one an editor, a
terminal or a diff can render as something else.) The **own grant**
is here and complete: a lead's led courses, a chair's department subtree, a
dean's college, the VP of Academics' institution, an instructor's section. The
**transitive union over the supervision graph is deliberately absent**, and
`transitive_purview` below raises `NotImplementedError` naming **E9**, which is
the epic SPEC §14.3 gives the DAG walk and its Hypothesis properties to.

**Why it raises rather than answering.** [ADR
0003](../../../docs/adr/0003-deferred-authz-seams-fail-closed.md) settles this
and is worth reading before changing it. Every value that could stand in for the
missing union is a value a caller can act on and none of them is right. An empty
`Purview` is the tempting one and the worst: an empty purview is a *legitimate*
state — a lead faculty member with no reports has one — so nothing about it looks
wrong, callers work, tests pass, and a dean silently sees nothing. The repair
somebody then reaches for is to diagnose "the dean sees no data" as a scoping
problem and widen access somewhere else, which is how a confidentiality invariant
gets broken by a well-meant fix. Returning the own grant alone reads as a missing
roster sync; returning the institution is the one direction §4.1 forbids
absolutely. So the seam refuses, before it opens a session, and its message names
the epic that lands it. The same rule is applied to `raw_comments_permitted`,
whose suppression rules are **E4**'s: ADR 0003 generalises to *any* deferred
authorization seam.

If you are here because something crashed on one of those raises, the seam is
working. The fix is upstream — do not traverse it — not a value returned from
here.

**Care is a capability beside the purview and never an element of one.** SPEC §2:
"Care is deliberately not composable with reporting roles — its sole power is the
threat queue, kept isolated so safety re-identification never rides alongside
routine oversight access." `Purview` is six sets of org-node ids and has nowhere
to put a capability, so no union can ever pick one up; `ActorScope.holds_care` is
where the answer lives, and `holds_care` below is the one place that computes it.
E0-10's Care service asks this module rather than reading a claim: an actor holds
Care because they hold a live `CARE` role assignment, never because of anything
an LTI or OIDC claim says, since the platform administrator controls what a claim
says.

**Every read here goes through a view, and none of them can reach identity.**
SPEC §8: "instructor/leadership read paths go through views that structurally
cannot join to `user` identity columns — enforced in the database, not just the
application." The connection this module is handed is `pulse_app`, which holds
`SELECT` on five views and on no base table at all, so a query *written here* that
named `public.person` would be refused by the server rather than by review.
`tests/unit/test_no_service_reads_an_identity_table_directly.py` is the
application-side half of that, and it reaches the two tables no grant stops:
`person` holds a name outright (§2.1) and `user` holds the LMS key.

**The grant does not protect the views themselves, and this ticket added three.**
Measured on the pinned Postgres: all five views are owned by `pulse_admin` with
`security_invoker` off, so each executes with its owner's privileges. A `_v002` of
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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

from app.config import Settings
from app.models.identity import AssignmentRole
from app.views_sql.queries import (
    SectionEnrollmentCount,
    SectionRosterRow,
    section_enrollment_counts,
    section_roster,
)

__all__ = [
    "LMS_OWNED_TABLES",
    "ActorScope",
    "AuthzError",
    "CareIsNotComposableError",
    "LmsOwnedWriteRefused",
    "NoReportingPurviewError",
    "OutOfPurviewError",
    "Purview",
    "ScopedReader",
    "UnknownAssignmentError",
    "guard_write",
    "holds_care",
    "own_grant",
    "raw_comments_permitted",
    "resolve_scope",
    "scoped_reader",
    "transitive_purview",
]


# ---------------------------------------------------------------------------
# Refusals. One family, so an entry point can turn any of them into one answer.
# ---------------------------------------------------------------------------


class AuthzError(Exception):
    """The base of every refusal this chokepoint raises.

    One family on purpose. SPEC §13 makes this module the single chokepoint for
    HTTP, for Celery and for E9's MCP server, and each of those has to turn a
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


@dataclass(frozen=True, slots=True)
class ActorScope:
    """Everything a request needs to know about who is asking.

    Four fields and each is a separate requirement: the person the scope was
    resolved for, the purview SPEC §2.1 defines, Care as a capability of its own
    so that no union operation can pick it up, and §4's n-threshold, which E4's
    suppression rules read from here rather than fetching for themselves — a
    caller that has to look the threshold up separately is a caller that can
    forget to.
    """

    person_id: UUID
    purview: Purview
    holds_care: bool
    n_threshold: int


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

# Every assignment one person holds. SPEC §2.1: "a person holds one or more role
# assignments… every view is resolved from an assignment (or a union of them),
# never from a person type."
_ASSIGNMENTS_OF_PERSON = text(
    "SELECT assignment_id, person_id, role,"
    " institution_id, college_id, department_id, course_id, section_id"
    " FROM public.assignment_scope"
    " WHERE person_id = :person_id"
    " ORDER BY assignment_id"
)

# Whether this person holds a live `CARE` assignment at all. E0-09's
# `role_assignment` carries no validity dates, so "live" reads as "exists" today:
# a revoked assignment is a deleted row. When E9 or E10 adds end-dating, this
# predicate gains it — and so do its two siblings, the one inside
# `app.services.safety` and the one inside `public.reveal_student_identity`, which
# are three statements of one rule (`docs/MISTAKES.md` entry 13).
_HOLDS_A_LIVE_CARE_ASSIGNMENT = text(
    "SELECT EXISTS ("
    " SELECT 1 FROM public.assignment_scope AS acting"
    " WHERE acting.person_id = :person_id"
    " AND acting.role = CAST(:care AS public.assignment_role)"
    ")"
)

# Which courses a person leads, out of the Lead Faculty mapping and not out of
# the assignment row. SPEC §2.1 puts "one lead per course" on the mapping; E0-09
# measured that `role_assignment` accepts two `LEAD_FACULTY` rows on one course
# and a `LEAD_FACULTY` row on a course whose mapping names somebody else, so the
# assignment's own `course_id` is not an answer to "which courses do they lead".
_LED_COURSES = text("SELECT course_id FROM public.lead_faculty_course WHERE person_id = :person_id")

# Every node beneath one node, at every level. Built from one template over
# `CONTAINMENT_LEVELS` so the projection is written once; nothing a caller
# supplies is interpolated — the level names are literals in this module and the
# node key is always bound. `prefix` is in the mapping for completeness and is
# reached by no role: SPEC §2.1's scope table gives no role a prefix-shaped
# scope, and ADR 0025 records why a lead is refused one.
_DESCENDANTS_TEMPLATE = (
    "SELECT institution_id, college_id, department_id, prefix_id, course_id, section_id"
    " FROM public.containment_path"
    " WHERE {level}_id = :node_id"
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
# assignment. The supervised chairs' departments come from the transitive walk,
# which is E9's and which `transitive_purview` refuses to fake.
#
# **An empty answer here means "the graph supplies it", and for `CARE` an empty
# answer would have meant "there is nothing to supply"** — which is why Care raises
# instead of returning this. The two are opposite claims and must not share a
# spelling; ADR 0046 records the distinction.
#
# Until E9 lands, an assistant dean therefore sees nothing, exactly as ADR 0003
# says of every consumer of the deferred union: "Leadership landing views are empty
# by design in E0." An earlier version of this module rooted the grant at the
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


def _nodes_beneath(session: Session, level: str, node_id: UUID) -> Mapping[str, frozenset[UUID]]:
    """Every node strictly below `node_id`, by level, out of `public.containment_path`.

    The view holds one row per org node with its ancestors filled in, so the rows
    whose `<level>_id` is this node are the node itself and everything under it.
    Only the levels *below* `level` are collected: an own grant is the scope node
    and its subtree, and a level above it is somebody else's grant. A chair who
    also held `college_ids` would hold every sibling department in that college,
    which is a widening nobody it happens to can detect.
    """
    below = CONTAINMENT_LEVELS[CONTAINMENT_LEVELS.index(level) + 1 :]
    found: dict[str, set[UUID]] = {name: set() for name in below}
    rows = session.execute(_DESCENDANTS[level], {"node_id": node_id}).mappings()
    for row in rows:
        for name in below:
            key: UUID | None = row[f"{name}_id"]
            if key is not None:
                found[name].add(key)
    return {name: frozenset(keys) for name, keys in found.items()}


def _lead_faculty_grant(session: Session, person_id: UUID) -> Purview:
    """The courses one lead leads, and their sections. SPEC §2.1's role grain for a lead.

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
    courses = frozenset(session.execute(_LED_COURSES, {"person_id": person_id}).scalars())
    if not courses:
        return Purview.empty()
    sections = frozenset(
        session.execute(_SECTIONS_OF_COURSES, {"course_ids": list(courses)}).scalars()
    )
    return Purview.of({"course": courses, "section": sections})


def _own_grant_of(session: Session, assignment: _Assignment) -> Purview:
    """One assignment's own grant, with the role grain already applied.

    Split out from `own_grant` because `resolve_scope` has the rows in hand
    already and re-reading each one by key would be a second answer to a question
    just asked.
    """
    if assignment.role is AssignmentRole.CARE:
        raise CareIsNotComposableError(
            f"assignment {assignment.assignment_id} is a CARE assignment and has no reporting "
            "purview. SPEC 2: Care is deliberately not composable with reporting roles — its sole "
            "power is the threat queue, kept isolated so safety re-identification never rides "
            "alongside routine oversight access. Ask holds_care() instead."
        )

    if assignment.role in _GRANT_ARRIVES_THROUGH_THE_GRAPH:
        return Purview.empty()

    level = _OWN_GRANT_ROOT.get(assignment.role)
    if level is None:
        raise NoReportingPurviewError(
            f"assignment {assignment.assignment_id} holds the {assignment.role.value} role, which "
            "SPEC 2.1's supervision chain does not contain and SPEC 2's table gives no reporting "
            "access. A role with no grain written down holds nothing here until somebody writes "
            "one, which is the same fail-closed choice as the scope grain rule's ELSE false."
        )

    if assignment.role is AssignmentRole.LEAD_FACULTY:
        return _lead_faculty_grant(session, assignment.person_id)

    node_id = _scope_node(assignment, level)
    if node_id is None:
        raise UnknownAssignmentError(
            f"assignment {assignment.assignment_id} holds the {assignment.role.value} role and "
            f"carries no {level} scope reference. SPEC 2.1's scope table and the schema's scope "
            "grain rule both say it must, so this row was written past the constraint that refuses "
            "it."
        )
    return Purview.of({level: frozenset({node_id}), **_nodes_beneath(session, level, node_id)})


def own_grant(session: Session, *, assignment_id: UUID) -> Purview:
    """The own grant of one assignment: its scope node restricted by role grain.

    SPEC §2.1: "with the own grant restricted by role grain: a Lead Faculty's
    grant is only the courses they lead (never sibling leads' courses, at any
    point in the union); a chair's is the department subtree; a dean's the
    college."

    This is the half of §2.1's definition E0-11 builds. The other half — the union
    over everything transitively reporting to the assignment — is
    `transitive_purview`, which raises; see this module's docstring.
    """
    row = session.execute(_ASSIGNMENT, {"assignment_id": assignment_id}).mappings().first()
    if row is None:
        raise UnknownAssignmentError(
            f"no assignment {assignment_id} exists, so it grants nothing. An empty purview is a "
            "real state — a lead with no mapped courses has one — so a missing row is reported "
            "rather than answered."
        )
    return _own_grant_of(session, _Assignment.of(row))


def transitive_purview(session: Session | None, *, assignment_id: UUID) -> Purview:
    """SPEC §2.1's full purview. **Not implemented: E9 lands it, and this raises.**

    "Purview(assignment) = own grant union the purviews of all assignments
    transitively reporting to it." The own grant is `own_grant` above; the walk over the
    supervision graph is E9's, together with the Hypothesis properties over
    generated graphs that SPEC §14.3 puts in the same epic and that are what would
    make a union trustworthy.

    **It raises before it reads anything**, which is why `session` may be `None`.
    A seam that connects first, walks half a graph and only then declines is a
    seam that can be reached by half. ADR 0003 has the full argument and every
    value it rejects; the module docstring says why an empty `Purview` is the
    worst of them.

    E0-18's leadership landing views are empty by design in E0 and must not
    traverse this. If a smoke test reaches it, the test asserts more than E0
    delivers — fix the test, do not soften the seam.
    """
    raise NotImplementedError(
        f"the transitive purview union over the supervision graph is E9's work, and assignment "
        f"{assignment_id} cannot be resolved through it in E0. SPEC 2.1 defines purview as 'own "
        "grant union the purviews of all assignments transitively reporting to it'; E0-11 ships "
        "the own grant (own_grant) and leaves the union a named seam that raises rather than "
        "returning a value a caller could act on. ADR 0003 rejects every stand-in, an empty "
        "Purview above all: an empty purview is a legitimate state, so a caller would work, the "
        "tests would pass, and a dean would silently see nothing."
    )


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


def resolve_scope(
    session: Session, *, person_id: UUID, n_threshold: int | None = None
) -> ActorScope:
    """Everything one person may reach, as one value every read path is handed.

    The purview is the union of the own grants of the person's **reporting**
    assignments. SPEC §2.1 resolves a view "from an assignment (or a union of
    them), never from a person type", and a person with two reporting hats — a
    chair who also leads courses — gets both, which is what `Purview.union` is
    for.

    **Assignments with no reporting purview are skipped rather than raising**, and
    the difference from `own_grant` is deliberate. Asking `own_grant` for a `CARE`
    assignment is a caller mistake and is refused; asking what a *person* may see
    is an ordinary question for somebody who holds a Care hat and a teaching hat,
    and §2.1 calls that combination legal — "it is capabilities that do not
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
    """
    rows = session.execute(_ASSIGNMENTS_OF_PERSON, {"person_id": person_id}).mappings().all()

    purview = Purview.empty()
    for row in rows:
        assignment = _Assignment.of(row)
        if (
            assignment.role not in _OWN_GRANT_ROOT
            and assignment.role not in _GRANT_ARRIVES_THROUGH_THE_GRAPH
        ):
            continue
        # An assistant dean's row is unioned rather than skipped, though it
        # contributes nothing today. Skipping would give the same answer and would
        # go on giving it if `_own_grant_of` ever learned to answer for the role,
        # which is a second place for the grain to live.
        purview = purview.union(_own_grant_of(session, assignment))

    threshold = Settings().n_threshold_default if n_threshold is None else n_threshold
    return ActorScope(
        person_id=person_id,
        purview=purview,
        holds_care=holds_care(session, person_id=person_id),
        n_threshold=threshold,
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
    module under `backend/app/` outside this one that makes that import, or that
    runs SQL naming one of the three org views. Until then it was a property a
    reviewer had to notice in a diff, and a property nothing executes is a
    comment (`docs/MISTAKES.md` entry 9).
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


def guard_write(*, table: str, assignment_role: AssignmentRole | None = None) -> None:
    """Refuse a write to data the LMS owns. SPEC §8: "never hand-edited in Pulse."

    Called by every application write path before it writes. It answers nothing
    and raises `LmsOwnedWriteRefused` when the write is one Pulse may not make;
    see `LMS_OWNED_TABLES` above for the grain, why it is table-grained plus one
    row, and what it does not catch.

    `assignment_role` is read only for `role_assignment` and is `None` everywhere
    else, because no other table in this schema carries a row whose ownership
    depends on a column value.
    """
    if table in LMS_OWNED_TABLES:
        raise LmsOwnedWriteRefused(
            f"public.{table} holds LMS-owned data and Pulse never hand-edits it (SPEC 2.1, 8). An "
            "edit here is not rejected by the LMS and does not error: it is overwritten at the "
            "next hourly roster sync, so the symptom is a value that changes back by itself."
        )

    if table == ROLE_ASSIGNMENT_TABLE and assignment_role is LMS_OWNED_ASSIGNMENT_ROLE:
        raise LmsOwnedWriteRefused(
            f"a {LMS_OWNED_ASSIGNMENT_ROLE.value} row on public.{ROLE_ASSIGNMENT_TABLE} is SPEC "
            "2.1's teaching-instructor link, which the LMS owns. It is not a stale attribute but "
            "a purview grant — 2.1 computes purview from exactly these rows — so writing one "
            "grants somebody oversight of a section. Every other role on this table is Pulse's "
            "own, built top-down in the admin console."
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
