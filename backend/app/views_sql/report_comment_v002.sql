-- The comments an instructor's report is built from, de-identified and undated —
-- v002, ticket E5.1-12, SPEC §4, §4.1 item 3, ADR 0041, ADR 0182, and the ruling
-- appended to docs/disputes/E5.1-12-01.md.
--
-- Supersedes report_comment_v001.sql. v001 is unchanged in every respect but one,
-- and everything it records — the five columns and the four that are absent, why
-- answer_id is present, why the view suppresses nothing itself, why it is keyed
-- by the week row, and the three filters — still holds and is not restated.
--
-- **What changed: what counts as blank text.** v001's last filter was
-- `btrim(comment_text) <> ''`. PostgreSQL's one-argument btrim trims only the
-- space character, so a comment of spaces, tabs and line breaks passed it. Its
-- author was then counted by `_commenters_by_stream_week`, the one count SPEC
-- §4's threshold is compared with, and four real commenters plus one blank one
-- reached a threshold of five and were shown. The submission path drops such a
-- comment before it is stored, but this view is the read side's own guard and
-- does not rely on that.
--
-- This body keeps a comment only if it holds a character that is not in the
-- `[:space:]` class. Under the database's en_US.utf8 character type that class
-- covers space, tab, line feed, vertical tab, form feed and carriage return, as
-- Python's `str.strip()` does, and also most Unicode spaces. Python's `strip`
-- removes eight characters this class does not: U+001C to U+001F, U+0085,
-- U+00A0 (no-break space), U+2007 and U+202F. A comment made only of those still
-- passes here; the submission path's `strip` is what stops one today.

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
  AND written.comment_text ~ '[^[:space:]]';
