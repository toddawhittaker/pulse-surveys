-- One role assignment, its scope node, its supervision edge and the two doors it
-- opens — ticket E1-13, ADR 0026, SPEC §2.1.
--
-- The second version of assignment_scope_v001.sql, which withheld the two
-- generated entry-door columns and said in as many words that a later ticket
-- would want them: "a later ticket adding, say, a validity window to an
-- assignment has to write a _v002 of this file before any read path can see it."
-- E1-13 is that ticket, and what it needs is the doors rather than a window.
--
-- **Why the resolution needs them in SQL rather than in Python.** E1-13 resolves
-- which view a person lands on from their live assignments, filtered by the door
-- they entered at. ADR 0026 puts that rule on public.role_assignment as two
-- stored generated columns derived from the role, precisely so that "a Care
-- assignment cannot open a launch" is a property of the row that no write path
-- can contradict — "there is no write path to either column for anyone:
-- application role, seed script, superuser session or future admin console
-- alike". A resolver that re-derived the rule in Python would be a second
-- authority for one rule, and the one an operator can read off the row is the one
-- that stops being consulted (`docs/MISTAKES.md` entry 13). So the columns are
-- published here and the filter is a WHERE clause.
--
-- **Everything else is v001 character for character.** The two columns are added
-- and nothing is removed or renamed: every caller of the v001 view goes on
-- reading exactly what it read. Under ADR 0041 this file is immutable from the
-- moment its revision executes, and v001 stays exactly as `9a71c4be0d3f` applied
-- it — a version is written rather than edited.
--
-- **Nothing here names a person**, unchanged from v001. person_id is the key SPEC
-- §2.1's people graph hangs off and carries no identity; the name lives on
-- public.person, which this view does not touch and pulse_app is granted nothing
-- on. The two columns added are booleans derived from an enum, so this version
-- widens the column list without widening what it can reach.
--
-- Every relation is schema-qualified (ADR 0027).

CREATE VIEW public.assignment_scope AS
SELECT
    held.id                AS assignment_id,
    held.person_id         AS person_id,
    held.role              AS role,
    held.reports_to        AS reports_to,
    held.institution_id    AS institution_id,
    held.college_id        AS college_id,
    held.department_id     AS department_id,
    held.course_id         AS course_id,
    held.section_id        AS section_id,
    held.permits_launch    AS permits_launch,
    held.permits_web_login AS permits_web_login
FROM public.role_assignment AS held;
