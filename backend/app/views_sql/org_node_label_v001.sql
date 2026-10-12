-- The display name of every org node above a section — ticket E9-07, SPEC §2.1, ADR 0205.
--
-- The roll-up tree labels its rows "Mathematics" and "College of Arts and
-- Sciences" (§2.1's labels), and `pulse_app` holds no SELECT on `institution`,
-- `college` or `department`: containment_path_v001.sql's rule is that the
-- application is granted nothing on those tables. A column grant on `name`
-- would break that rule for one reader; this view keeps it and answers every
-- level's name in one read.
--
-- **One row per node at five levels, no section.** `level` is the containment
-- level, `node_id` the node's key, `name` what a screen prints for it, and
-- `parent_id` the key of the node it sits in (NULL for the institution). A
-- section is not a row: its code is on `section`, which `pulse_app` already
-- reads, and a section row here would be a second place to learn it.
--
-- **What each level's name is.** An institution, college and department print
-- their `name`. A prefix prints its `code` ("MATH"). A course prints its
-- course-form label, "MATH 140 — College Algebra": the prefix code, the LMS
-- number, an em dash and the LMS title. That is the form
-- `app.services.section_codes.course_label` builds when it is given no section
-- code, which is what a comparison set and the roll-up tree name a course by;
-- the two spellings must move together.
--
-- **No person, no identity, no email, no figure.** The chair or dean a label
-- names arrives through the staff-name door (ADR 0201), and every count is
-- computed over the reader's purview in `services/rollups.py`. A name or a
-- count on this row would be one read past both.
--
-- **Nothing here filters by who is asking.** Which nodes a reader may label is
-- decided in `services/authz.py`, which reads this view only for the nodes
-- above sections already inside the reader's purview.
--
-- Every relation is schema-qualified (ADR 0027), and every NULL carries its
-- cast so reordering the branches cannot change the column types. The level
-- names are dollar-quoted because each is also a table's name, and a table's
-- name inside single quotes is the `'name'::regclass` lookup that
-- tests/integration/test_identity_separated_views.py refuses unqualified.

CREATE VIEW public.org_node_label AS
SELECT
    $$institution$$::text AS level,
    held.id             AS node_id,
    held.name::text     AS name,
    NULL::uuid          AS parent_id
FROM public.institution AS held
UNION ALL
SELECT
    $$college$$::text,
    held.id,
    held.name::text,
    held.institution_id
FROM public.college AS held
UNION ALL
SELECT
    $$department$$::text,
    held.id,
    held.name::text,
    held.college_id
FROM public.department AS held
UNION ALL
SELECT
    $$prefix$$::text,
    held.id,
    held.code::text,
    held.department_id
FROM public.prefix AS held
UNION ALL
SELECT
    $$course$$::text,
    held.id,
    (above.code || ' ' || held.lms_number || ' — ' || held.lms_title)::text,
    held.prefix_id
FROM public.course AS held
JOIN public.prefix AS above ON above.id = held.prefix_id;

GRANT SELECT ON public.org_node_label TO pulse_app;
