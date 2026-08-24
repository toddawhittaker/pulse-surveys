-- Which courses a person leads — ticket E0-11, SPEC §2.1.
--
-- "A Lead Faculty's grant is only the courses they lead (never sibling leads'
-- courses, at any point in the union)", and §2.1 puts the answer to *which*
-- courses on the Pulse-owned Lead Faculty mapping rather than on the assignment
-- row. `RoleAssignment`'s docstring settles the same question from the other
-- end: "a purview resolver reads the mapping to decide which courses a lead
-- holds, and reads this table only for the edges."
--
-- That is not a preference. E0-09 measured that public.role_assignment accepts
-- two LEAD_FACULTY rows on one course, and accepts a LEAD_FACULTY row on a
-- course whose mapping names somebody else; public.lead_faculty_mapping carries
-- UNIQUE (course_id), so it has exactly one answer per course. Reading the
-- assignment's own course_id would hand a lead a course the mapping gives to a
-- sibling, which is SPEC §4.1 invariant 2.
--
-- Two columns, because two is what the question needs. A view over the whole
-- mapping table would carry its primary key, which no read path has a use for.
--
-- Every relation is schema-qualified (ADR 0027).

CREATE VIEW public.lead_faculty_course AS
SELECT
    mapped.person_id AS person_id,
    mapped.course_id AS course_id
FROM public.lead_faculty_mapping AS mapped;
