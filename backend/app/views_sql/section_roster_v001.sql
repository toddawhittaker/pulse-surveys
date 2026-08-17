-- Who is enrolled in a section, by key — ticket E0-10, SPEC §8.
--
-- SPEC §4: "Responses are stored keyed to the LMS user ID (`sub` from the
-- launch). Identity is never displayed to instructors or any leadership role, in
-- any view, including CSV exports." This view is the read path that statement
-- describes: it carries the key and the enrollment window and nothing that names
-- anybody.
--
-- **The guarantee is not that this view omits a name.** It is that the
-- connection reading it holds no privilege on public.user_identity at all, so a
-- query joining this view back to that table is refused by the server rather
-- than by whoever reviews it. Omission is what a careless edit undoes; the grant
-- is what survives one. identity_grants_v001.sql is the other half, and
-- tests/integration/test_identity_grants.py asserts the refusal.
--
-- Every relation is schema-qualified (ADR 0027). A view is bound at CREATE VIEW
-- time, so an unqualified name here is not the hijack it is inside a function —
-- but this file is the model the next view is copied from, and a later function
-- that reads this view inherits its text into its own plan.

CREATE VIEW public.section_roster AS
SELECT
    member.id            AS enrollment_id,
    member.user_id       AS user_id,
    member.section_id    AS section_id,
    member.started_on    AS started_on,
    member.ended_on      AS ended_on,
    taught.course_id     AS course_id,
    taught.term_id       AS term_id,
    taught.lms_section_code AS lms_section_code,
    taught.length_weeks  AS length_weeks,
    taught.start_date    AS section_start_date,
    taught.end_date      AS section_end_date
FROM public.enrollment AS member
JOIN public.section AS taught ON taught.id = member.section_id;
