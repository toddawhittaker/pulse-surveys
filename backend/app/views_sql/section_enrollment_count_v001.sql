-- How many people a section holds — ticket E0-10, SPEC §8.
--
-- The counting half of the pair. §4.1 invariant 4 is that "aggregate language
-- counts sections, never instructors", and every count a report shows starts
-- here rather than from a query somebody writes against public.enrollment: a
-- count is the shape most likely to be extended with "…and their names" by a
-- screen that needs a roster, and this is the read path that cannot be.
--
-- LEFT JOIN, so a section nobody has enrolled in reports zero rather than
-- disappearing. A section missing from a roll-up reads as a section that does
-- not exist, which is a worse answer than zero and a harder one to notice.
--
-- **No threshold is applied here, deliberately.** §4's small-N rule and §5.1's
-- benchmark minimum are about *responses* in a reporting week, not about
-- enrollment, they are configurable (§6.3), and E4 and E5 own them. A view that
-- suppressed a row below some number would be a second place the threshold
-- lives, and a stale one.

CREATE VIEW public.section_enrollment_count AS
SELECT
    taught.id            AS section_id,
    taught.course_id     AS course_id,
    taught.term_id       AS term_id,
    taught.lms_section_code AS lms_section_code,
    count(member.id)     AS enrolled_count
FROM public.section AS taught
LEFT JOIN public.enrollment AS member ON member.section_id = taught.id
GROUP BY taught.id, taught.course_id, taught.term_id, taught.lms_section_code;
