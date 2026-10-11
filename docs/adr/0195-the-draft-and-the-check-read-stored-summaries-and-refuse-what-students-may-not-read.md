# 0195 — The draft and the check read stored summaries, and refuse what students may not read

**Status:** Accepted
**Date:** 2026-10-11
**Ticket:** [E7-04](../tickets/e7/E7-04-ai-draft-and-check.md)

## Context

SPEC §5.3 gives the instructor two advisory AI modes: a draft of their response
to the class, and a check naming the themes a draft has not addressed, "with its
comment count", and without one for a stream held below the threshold. §7.4
makes each one call in, one validated object out. What a published response may
carry is §4.1 item 3's question: students read it under the instructor's name.
The spec does not say what the two tasks are fed, what is checked after the
model answers, or what a refusal says.

## Decision

**The gather is stored summaries and figures, never a comment.**
`reporting.response_gather` returns the week's response count and, per stream,
the stored summary, its stored themes and the rating distribution.
`ResponseGather` has no field a comment could go in. Summaries and themes come
from one filtered read (`_served_summary_rows`, the read the report makes), so
an ordinary-mode `summary.v1` row of a stream now held gives neither
([0188](0188-moderation-runs-at-window-close-swept-hourly-with-an-attempt-cap.md)).
Held is the report's own per-stream answer (`_held_streams`: suppressed, or the
week not yet moderated).

**Below the threshold a theme carries no count** (the E7 breakdown's decision
12). A held stream's theme is gathered with `None`, and `GatheredStream`
refuses to be built otherwise. The check's output uses a new `CheckTheme`
(`comment_count: int | None`); `CommentTheme` and the weekly summary keep their
required count. A theme's count is a count of comments and never feeds the
threshold (`docs/MISTAKES.md` entry 50).

**Two structural refusals after the model answers**, each one 502 with one
sentence from `app.copy`, whatever triggered it and whatever the model did:

- The check may name only gathered themes, each as an exact (label, count) pair:
  a shown stream's with its stored count, a held stream's with none.
- The draft may not reuse a run (`_reused_run`, twenty characters) of a comment
  students will not see: excluded, still flagged, or in a held stream, read
  through `report_comment` v004 for this comparison only.
- In a week with a held stream the draft states no number of anything except a
  named course structure, because a summary's prose can carry the count the
  themes do not. *Amended in E7-04's fix round.* `states_a_count_of_people`
  refuses any count token: a digit run; a cardinal word from zero to
  ninety-nine, hyphenated compounds included, or "hundred"; or both, half,
  couple, several, few, dozen, pair, handful, majority or minority. A token is
  allowed only when the word immediately before it is a course-structure word
  (week, chapter, lab, unit, module, section, page, question, assignment, quiz,
  exam, day, hour, minute, part, step, problem, version, and their plurals
  where listed), so "week 3" passes and "weeks 3 and 4" is refused at "4".
  Ordinals are not count tokens. The eval grader calls the same function, and
  `response_draft.v2` asks the model for exactly this rule.

**The instructor's gather keeps a summary written before an exclusion.** The
instructor already reads that summary on the report, and is the author of
whatever is published; the run refusal blocks quoting the excluded comment.
The on-behalf gather, which E7-03 builds behind `for_on_behalf=True`, leaves
such a summary out (the E7 breakdown's ruling 9). E7-03 built it (ADR 0194).

**The forged summary block boundaries entry does not trigger here.** No comment
is rendered into either prompt. The summaries and labels that are rendered are
model text, so the week goes in as one ASCII-escaped JSON document: no value
can stand on a line of its own and pose as a marker line. The check's draft is
the last thing in its prompt.

**No floor.** The eval cases in `tests/evals/response_draft/` and
`tests/evals/draft_check/` are typed and graded offline, with no `floors.py`,
as `tests/evals/moderation/` ships. A floor needs a live run against the
owner's endpoint (SPEC §9.3).

## Alternatives rejected

- **Making `CommentTheme.comment_count` optional.** It would let a summary store
  a theme with no count, a loosening nobody asked for (residue B).
- **Feeding the shown stream's published comments**, which the instructor can
  read anyway. The draft is published to students, and the ticket rules out raw
  comments; the summaries are what the report already condensed.
- **A refusal per cause.** Naming the matched comment, its state or the broken
  rule describes comments the instructor is not shown.
- **A phrase list for counts of people** (the first version: a number beside
  "students", "comments", "of you" and a few more). Review found phrasings it
  missed at once: "two of your classmates", "2 learners said", "the 7 who
  responded", "Both students", "Half the class". The ways of saying how many
  never close, so the rule forbids the number itself. The cost is that "three
  worked examples" is refused too in a held week.
- **Rewriting a refused answer** (stripping a count, dropping a theme). The
  answer is refused whole, as `summarize_stream` refuses an overclaim.

## Consequences

- A draft that quotes a hidden comment, or carries a number in a held week,
  costs a model call and a retry by the instructor. The token rule cannot catch
  a count spelled with a word outside its list ("a trio of you"); it does not
  try to read meaning, and the prompt asks for no numbers at all.
- Every model failure, an outage included, reads as the same 502.
- `RESPONSE_TEXT_MAX` (4000) bounds the check's draft in `app.schemas.report`
  until E7-01's bound merges and replaces it.

**Amended by E7-03 (ADR 0194's ticket).** The count rule also counts a
hyphenated word when any part of it is a cardinal ("two-thirds"), adds
"single", "dozens", "hundreds" and "tens" to the quantity words, and counts
"third", "thirds", "quarter" and "quarters" only when the next word is "of"
("a third of you"), so the ordinal in "the third week" stays allowed.
