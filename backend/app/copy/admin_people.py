"""The admin's people editor: the definers' refusals, the gate's two sentences, the import's.

SPEC §6.3 puts the People & reporting editor and the Lead Faculty mapping table in
the admin console. The writes underneath them are `SECURITY DEFINER` functions
in `app/views_sql/people_graph_v001.sql` (ADR 0200), `people_graph_v002.sql`
(E9-06's import record) and `people_graph_v003.sql` (E9-14's lead rule), and each
refusal they can
make is raised as SQLSTATE `P0001` whose message is **exactly one key below**,
for example `admin_people.actor_not_an_admin`. The message names no person and
no id. A caller reads the key off the database error and looks it up in `COPY`;
`app.services.people` writes that translation.

**Two refusals carry a number.** `admin_people.assignment_has_reports` is raised
with the count of assignments that still report to the one being revoked, and
`admin_people.lead_still_leads_courses` (`people_graph_v003.sql`) with the count
of courses a Lead Faculty assignment's person still leads, each as digits in the
error's detail field. Each text holds the placeholder `{count}`, filled with
`entry.text.format(count=...)`, as `app.copy.gradebook` fills its own
placeholders.

**Each sentence describes only itself.** It is answered to an admin about a staff
record, and it names no person, no role holder and no node, because the same
sentence is shown whichever record was refused.

**The gate's two sentences live here too**, beside the refusals, because the
admin gate answers every admin route and not one screen. They need words of
their own because the leadership gate's sentences say "leadership". The status
codes and challenges are the leadership gate's (`NOT_LEADERSHIP_STATUS`,
`NOT_YOUR_ROLE_STATUS` and their challenges in `app.api.deps`). `NOT_ADMIN` and
`NOT_ADMIN_ROLE` are the constants the gate imports, each its entry's own text.

**The surface owes SPEC §4.1 item 5 no confidentiality line.** Everything on
the people pages is a staff record: names, categories, role assignments,
reporting lines, lead mappings and whether a web login is linked. No student and
no response is shown (E9 README decision 15).
"""

from collections.abc import Mapping

from app.copy import CopyEntry

__all__ = ["COPY", "NOT_ADMIN", "NOT_ADMIN_ROLE"]

# --- The admin gate ---------------------------------------------------------

# The 401 for a request with no session the gate can verify: none at all, a
# malformed token, an expired one, or one signed with another key. One sentence
# for all four, so a caller trying tokens cannot tell a real one from a forgery.
_NOT_AN_ADMIN_SESSION = CopyEntry(
    key="admin_people.not_an_admin_session",
    text="This request does not carry an Admin session.",
)

# The 403 for a real, verified session in another role (ADR 0196's shape). One
# sentence for every other role.
_NOT_YOUR_ROLE = CopyEntry(
    key="admin_people.not_your_role",
    text="This request carries a signed-in session whose role is not Admin.",
)

# --- The definers' named refusals -------------------------------------------

# Every write, when the acting person's key holds no live ADMIN assignment.
_ACTOR_NOT_AN_ADMIN = CopyEntry(
    key="admin_people.actor_not_an_admin",
    text="Only somebody holding the Admin role may make this change.",
)

_NO_SUCH_PERSON = CopyEntry(
    key="admin_people.no_such_person",
    text="There is no person record here.",
)

_NO_SUCH_ASSIGNMENT = CopyEntry(
    key="admin_people.no_such_assignment",
    text="There is no role assignment here.",
)

# Decision 11: teaching grants are the roster sync's, never the editor's.
_INSTRUCTOR_IS_LMS_OWNED = CopyEntry(
    key="admin_people.instructor_is_lms_owned",
    text=(
        "Teaching assignments come from the learning platform's roster, so they are not "
        "granted, revoked or given a reporting line here."
    ),
)

_SCOPE_IS_NOT_THE_ROLES_NODE = CopyEntry(
    key="admin_people.scope_is_not_the_roles_node",
    text="This role is granted at another level of the organization than the one chosen.",
)

# Ruling 7: revoke deletes, and the database refuses to delete a row others
# report to. `{count}` is filled from the refusal's detail field.
_ASSIGNMENT_HAS_REPORTS = CopyEntry(
    key="admin_people.assignment_has_reports",
    text=(
        "Assignments still reporting to this one: {count}. Point each of them to another "
        "assignment before revoking this one."
    ),
)

# ADR 0044's trigger, or the rule that a Care assignment reports to nobody.
_EDGE_DOES_NOT_CLIMB = CopyEntry(
    key="admin_people.edge_does_not_climb",
    text=(
        "An assignment reports only to a role above it in the chain, never to or from Care, and "
        "never in a loop. This reporting line breaks that rule."
    ),
)

_NO_SUCH_COURSE = CopyEntry(
    key="admin_people.no_such_course",
    text="There is no such course here.",
)

_COURSE_ALREADY_LED = CopyEntry(
    key="admin_people.course_already_led",
    text="This course already has a lead. Unmap the current lead first.",
)

# E9-14: a course is mapped only to somebody holding a Lead Faculty assignment,
# so the course reaches a review queue (people_graph_v003.sql).
_LEAD_NEEDS_THE_LEAD_ROLE = CopyEntry(
    key="admin_people.lead_needs_the_lead_role",
    text=(
        "A course can be mapped only to somebody who holds the Lead Faculty role. Grant the "
        "role first."
    ),
)

# E9-14: the other side of the same rule. `{count}` is filled from the refusal's
# detail field.
_LEAD_STILL_LEADS_COURSES = CopyEntry(
    key="admin_people.lead_still_leads_courses",
    text=(
        "Courses still mapped to this lead: {count}. Unmap each of them before revoking the "
        "Lead Faculty role."
    ),
)

_COURSE_NOT_LED = CopyEntry(
    key="admin_people.course_not_led",
    text="This course has no lead to unmap.",
)

_SUBJECT_LINKED_TO_ANOTHER = CopyEntry(
    key="admin_people.subject_linked_to_another",
    text="This web login is already linked to another person.",
)

_PERSON_ALREADY_LINKED = CopyEntry(
    key="admin_people.person_already_linked",
    text="This person already has a web login linked. Unlink it first.",
)

_PERSON_NOT_LINKED = CopyEntry(
    key="admin_people.person_not_linked",
    text="This person has no web login to unlink.",
)

# `admin_record_import` (people_graph_v002.sql), asked to record an import of a
# kind other than a people file or a mapping file. The service passes only the
# two, so this reaches nobody unless the service is wrong.
_IMPORT_KIND_UNKNOWN = CopyEntry(
    key="admin_people.import_kind_unknown",
    text="This import is neither a people file nor a lead mapping file, so nothing was changed.",
)

# --- The editor's own sentences (the import and its dry run) ----------------

# Each lead mapping a dry run would remove: SPEC §2.1's "unmapped, falls to
# chair". `{course}` is the course's label.
_UNMAPPED_FALLS_TO_CHAIR = CopyEntry(
    key="admin_people.unmapped_falls_to_chair",
    text="{course} is left without a lead and falls to its chair.",
)

# A refused line of an import file. `{line}` counts the header as line 1, and
# `{reason}` is one of the sentences below or a definer's refusal above.
_IMPORT_LINE_REFUSED = CopyEntry(
    key="admin_people.import_line_refused",
    text="Line {line} of the file cannot be imported, so nothing was changed. {reason}",
)

_IMPORT_HEADER_WRONG = CopyEntry(
    key="admin_people.import_header_wrong",
    text=(
        "The first line of the file is not the header this table exports. Start from an "
        "exported file."
    ),
)

_IMPORT_LINE_MALFORMED = CopyEntry(
    key="admin_people.import_line_malformed",
    text=(
        "It does not have the header's columns, or a value in it is not written the way the "
        "export writes it."
    ),
)

_IMPORT_KEY_REPEATED = CopyEntry(
    key="admin_people.import_key_repeated",
    text="It names the same record as an earlier line.",
)

# The apply's digest no longer matches: the tables moved after the dry run.
_IMPORT_STALE = CopyEntry(
    key="admin_people.import_stale",
    text=(
        "The tables changed after this file's dry run, so nothing was applied. Run the dry "
        "run again and review the new changes."
    ),
)

# What the gate serves. Each is its entry's own text, so a reworded sentence is
# one edit above.
NOT_ADMIN = _NOT_AN_ADMIN_SESSION.text
NOT_ADMIN_ROLE = _NOT_YOUR_ROLE.text

# What the inventory reads, and what a caller looks a definer's key up in.
COPY: Mapping[str, CopyEntry] = {
    entry.key: entry
    for entry in (
        _NOT_AN_ADMIN_SESSION,
        _NOT_YOUR_ROLE,
        _ACTOR_NOT_AN_ADMIN,
        _NO_SUCH_PERSON,
        _NO_SUCH_ASSIGNMENT,
        _INSTRUCTOR_IS_LMS_OWNED,
        _SCOPE_IS_NOT_THE_ROLES_NODE,
        _ASSIGNMENT_HAS_REPORTS,
        _EDGE_DOES_NOT_CLIMB,
        _NO_SUCH_COURSE,
        _COURSE_ALREADY_LED,
        _LEAD_NEEDS_THE_LEAD_ROLE,
        _LEAD_STILL_LEADS_COURSES,
        _COURSE_NOT_LED,
        _SUBJECT_LINKED_TO_ANOTHER,
        _PERSON_ALREADY_LINKED,
        _PERSON_NOT_LINKED,
        _IMPORT_KIND_UNKNOWN,
        _UNMAPPED_FALLS_TO_CHAIR,
        _IMPORT_LINE_REFUSED,
        _IMPORT_HEADER_WRONG,
        _IMPORT_LINE_MALFORMED,
        _IMPORT_KEY_REPEATED,
        _IMPORT_STALE,
    )
}
