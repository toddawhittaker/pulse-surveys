-- One role assignment, its scope node and its supervision edge — ticket E0-11.
--
-- SPEC §2.1 computes purview from this table: "Purview(assignment) = own grant
-- union the purviews of all assignments transitively reporting to it". The
-- authorization chokepoint in backend/app/services/authz.py is the only thing
-- that reads it, and it runs on the pulse_app connection, which E0-10 left
-- holding SELECT on two views and on nothing else. So the resolver could not
-- answer a single question this ticket asks until this view existed.
--
-- **Why a view rather than a grant on the table.** SPEC §8 puts instructor and
-- leadership read paths behind views "enforced in the database, not just the
-- application", and a grant on public.role_assignment would also hand pulse_app
-- the two generated entry-door columns and every future column added to it. A
-- view fixes the column list at the moment somebody has to think about it: a
-- later ticket adding, say, a validity window to an assignment has to write a
-- _v002 of this file before any read path can see it.
--
-- **Nothing here names a person.** person_id is the key SPEC §2.1's people graph
-- hangs off and carries no identity; the name lives on public.person, which this
-- view does not touch and pulse_app is granted nothing on.
-- tests/unit/test_no_service_reads_an_identity_table_directly.py is the sweep
-- that keeps the resolver reading this view rather than that table.
--
-- **reports_to is carried although E0-11 reads nothing but the scope columns.**
-- SPEC §2.1's union walks this edge and E9 is the ticket that walks it (ADR
-- 0003); under ADR 0041 a column added later costs a _v002 file and a revision,
-- so the edge is here now rather than in the first migration E9 has to write.
--
-- Every relation is schema-qualified (ADR 0027).

CREATE VIEW public.assignment_scope AS
SELECT
    held.id             AS assignment_id,
    held.person_id      AS person_id,
    held.role           AS role,
    held.reports_to     AS reports_to,
    held.institution_id AS institution_id,
    held.college_id     AS college_id,
    held.department_id  AS department_id,
    held.course_id      AS course_id,
    held.section_id     AS section_id
FROM public.role_assignment AS held;
