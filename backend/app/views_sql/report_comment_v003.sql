-- The comments an instructor's report is built from, de-identified and undated —
-- v003, ticket E5.1-12, SPEC §4, §4.1 item 3, ADR 0041, ADR 0182, and
-- docs/disputes/E5.1-12-01.md.
--
-- Supersedes report_comment_v002.sql, which superseded v001. The five columns,
-- the joins and the first two filters are v001's and v002's, and everything
-- v001 records about them still holds and is not restated. What moved is the
-- last filter, the test for blank text, for the second time.
--
-- **The history of that filter.** v001 wrote `btrim(comment_text) <> ''`, and
-- PostgreSQL's one-argument btrim trims only the space character, so a comment
-- of tabs and line breaks counted its author toward SPEC §4's threshold. v002
-- kept a comment only if it held a character outside `[:space:]` or eight extra
-- escapes. That class follows the collation: it matched Python's `strip` under
-- the project's en_US.utf8 and missed fifteen Unicode spaces under
-- `COLLATE "C"`. The submission path drops a comment `strip` empties before it
-- is stored, but this view is the read side's own guard and does not rely on
-- that.
--
-- This body keeps a comment only if it holds a character that Python's
-- `str.strip()`, the submission path's test, would not remove. The class lists
-- every character `strip` removes, by code point, and nothing else: U+0009 to
-- U+000D (tab, line feed, vertical tab, form feed, carriage return), U+001C to
-- U+001F, U+0020 (space), U+0085, U+00A0 (no-break space), U+1680, U+2000 to
-- U+200A, U+2028, U+2029, U+202F, U+205F and U+3000. It names no `[:space:]`
-- class, because what that class covers depends on the collation: under
-- en_US.utf8 it misses eight of these characters and under `COLLATE "C"` it
-- misses twenty-three. A list of code points means the same thing under every
-- collation. The escapes are PostgreSQL regex escapes inside a standard string
-- literal (standard_conforming_strings is on), so the string parser passes the
-- backslashes through and the regex engine reads them.

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
  AND written.comment_text ~ '[^\u0009-\u000d\u001c-\u001f\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]';
