-- Every org node with the chain of ancestors above it — ticket E0-11, SPEC §2.1.
--
-- "Institution -> College -> Department -> Prefix -> Course -> Section." A
-- chair's own grant is the department subtree, a dean's the college, the VP of
-- Academics' the institution (§2.1, "with the own grant restricted by role
-- grain"), so the chokepoint has to turn one node into every node beneath it.
-- E0-05 built the hierarchy as six separate tables, and pulse_app is granted
-- nothing on any of them, so this view is the whole of how that question is
-- answered on the connection production serves requests over.
--
-- **One row per node, not one row per section.** The obvious shape is a single
-- row per section carrying its five ancestors, and it is wrong in a way that is
-- invisible until it matters: a prefix with no courses, or a course with no
-- sections, has no section row, so it would drop out of a chair's grant
-- entirely. §2.1's display labels count prefixes and sections separately
-- ("department rows `N prefixes . N sections`"), and a prefix that exists and
-- is not in the purview is a row a screen cannot render and nobody can explain.
-- So every node contributes a row of its own, with the levels at and below it
-- left NULL.
--
-- Reading it: the descendants of a node are the rows where that node's column
-- holds its key, and the purview is the non-NULL ids at the levels *below* the
-- one the assignment is scoped to. The node's own row is always in that set,
-- which is what makes a childless node answer for itself.
--
-- **This view is downward-closed by construction and carries no upward
-- information a reader could mistake for a grant.** Selecting the ancestors on
-- a descendant's row is what makes the filter possible at all; nothing in the
-- resolver ever collects a level above the assignment's own, and
-- tests/integration/test_own_grant_follows_the_role_grain.py compares a purview
-- whole, so a college id appearing in a chair's grant fails there rather than
-- widening quietly.
--
-- **term is deliberately absent.** SPEC §2.1's containment hierarchy has six
-- levels and a term is not one of them: it is the calendar a section's code is
-- read against (§2.2), and purview does not vary by term.
--
-- No name, no email address and no person: this view reaches only the six
-- containment tables, which SPEC §2.1 puts on Pulse's side as org structure.
--
-- Every relation is schema-qualified (ADR 0027). Every NULL carries its cast
-- rather than leaning on the first branch to fix the column types, so that
-- reordering the branches cannot change what this view returns.

CREATE VIEW public.containment_path AS
SELECT
    held.id       AS institution_id,
    NULL::uuid    AS college_id,
    NULL::uuid    AS department_id,
    NULL::uuid    AS prefix_id,
    NULL::uuid    AS course_id,
    NULL::uuid    AS section_id
FROM public.institution AS held
UNION ALL
SELECT
    held.institution_id,
    held.id,
    NULL::uuid,
    NULL::uuid,
    NULL::uuid,
    NULL::uuid
FROM public.college AS held
UNION ALL
SELECT
    above_college.institution_id,
    held.college_id,
    held.id,
    NULL::uuid,
    NULL::uuid,
    NULL::uuid
FROM public.department AS held
JOIN public.college AS above_college ON above_college.id = held.college_id
UNION ALL
SELECT
    above_college.institution_id,
    above_department.college_id,
    held.department_id,
    held.id,
    NULL::uuid,
    NULL::uuid
FROM public.prefix AS held
JOIN public.department AS above_department ON above_department.id = held.department_id
JOIN public.college AS above_college ON above_college.id = above_department.college_id
UNION ALL
SELECT
    above_college.institution_id,
    above_department.college_id,
    above_prefix.department_id,
    held.prefix_id,
    held.id,
    NULL::uuid
FROM public.course AS held
JOIN public.prefix AS above_prefix ON above_prefix.id = held.prefix_id
JOIN public.department AS above_department ON above_department.id = above_prefix.department_id
JOIN public.college AS above_college ON above_college.id = above_department.college_id
UNION ALL
SELECT
    above_college.institution_id,
    above_department.college_id,
    above_prefix.department_id,
    above_course.prefix_id,
    held.course_id,
    held.id
FROM public.section AS held
JOIN public.course AS above_course ON above_course.id = held.course_id
JOIN public.prefix AS above_prefix ON above_prefix.id = above_course.prefix_id
JOIN public.department AS above_department ON above_department.id = above_prefix.department_id
JOIN public.college AS above_college ON above_college.id = above_department.college_id;
