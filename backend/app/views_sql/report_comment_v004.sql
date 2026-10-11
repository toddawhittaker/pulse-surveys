-- The comments an instructor's report is built from, de-identified, undated and
-- moderated — v004, ticket E6-01, SPEC §4, §4.1 item 3, §5.2, §6.2, ADR 0041,
-- ADR 0187.
--
-- Supersedes report_comment_v003.sql. The five columns, the joins and v003's
-- three filters are unchanged, and everything v001 to v003 record about them
-- still holds and is not restated; v003's header is where the blank-text class
-- is argued. v004 adds two conditions, both about the comment's moderation
-- verdicts, which are `public.classification` rows with `task = 'MODERATION'`.
-- The routing definer `public.route_moderation_verdict` is their only writer
-- (moderation_routing_v001.sql).
--
-- **A comment appears only once it holds a moderation verdict.** Until E6-01 a
-- comment nobody had moderated counted as published, and nothing moderated
-- anything, so every comment reached every reader unreviewed. Now a comment with
-- no verdict is absent from every reader built on this view: the week read, the
-- release cut, every release batch and the summary gather.
--
-- **A comment never appears once any of its verdicts, ever, is threat or
-- self-harm.** SPEC §6.2 suppresses those from every instructor and leadership
-- view. The condition is over every verdict the comment has ever held, never the
-- latest: a later `clear` on the same comment does not bring it back, because a
-- re-run that disagrees is not evidence the first reading was wrong, and §6.2
-- routes the comment to Care either way.
--
-- **What is not here.** Whether a whole section-week is moderated is decided in
-- `app.services.report_comments.section_week_moderated`, not in this view: a
-- reader shows nothing of a section-week until every comment this view would
-- otherwise show holds a verdict, so no read shows part of a week (ADR 0187).
-- The view decides which comments exist for a reader; that helper decides when a
-- week's set is final.

CREATE OR REPLACE VIEW public.report_comment AS
SELECT
    submitted.section_id AS section_id,
    submitted.week_id    AS week_id,
    asked.stream         AS stream,
    written.id           AS answer_id,
    written.comment_text AS comment_text
FROM public.answer AS written
JOIN public.question AS asked ON asked.id = written.question_id
JOIN public.response AS submitted ON submitted.id = written.response_id
WHERE asked.kind = 'comment'
  AND written.comment_text IS NOT NULL
  AND written.comment_text ~ '[^\u0009-\u000d\u001c-\u001f \u0085   -     　]'
  AND EXISTS (
      SELECT 1
        FROM public.classification AS moderated
       WHERE moderated.answer_id = written.id
         AND moderated.task = 'MODERATION'
  )
  AND NOT EXISTS (
      SELECT 1
        FROM public.classification AS routed_to_care
       WHERE routed_to_care.answer_id = written.id
         AND routed_to_care.task = 'MODERATION'
         AND routed_to_care.verdict IN ('threat', 'self_harm')
  );
