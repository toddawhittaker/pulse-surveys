# 0168 — A week's served question wording comes from the rows its responses answered

## Context

E5-02 puts each stream's rating-question wording on the instructor's Monday
report, so the two histograms are titled with the question students answered
rather than with the name of the stream.

SPEC §3.2 makes that wording versioned — "Question text is stored in a versioned
`question_set` table even though v1 ships one fixed set" — and then stops. It
does not say which set is *in force* for a given week, and the schema is
deliberately silent in the same place: `app/models/survey.py` gives `question_set`
no `is_active` column and no dating, and says why in as many words — "no ticket
has yet specified how a second one would be selected — per institution, per
level, per term — so there is no `is_active` column and no ordering rule."

A report is the first read that has to answer the question anyway. It shows a
week that is already over, and week navigation pages back across every published
week of a section (SPEC §5.1), so "which wording" is asked once per week of the
term rather than once.

The submission path already answers a narrower version of it:
`app.services.submissions.current_questions` takes the set at the highest
version, because a student answering right now is answering the newest
instrument. That rule is right for a form and wrong for a report — applied to a
closed week it would re-title every historical week the moment a second set
ships.

## Decision

**The wording a week serves is read off the question rows that week's own
responses answered.** The read joins `answer` to `response` for the reported
section-week and on to `question`, filtered to the rating kind and to the stream
the member sits under — the same join shape `_comments_reaching_the_model` uses
for that week's comments. `answer.question_id` is durable, so the questions a
week's responses point at stay the questions that week was asked, whatever is
published afterwards.

Two consequences of that rule are decided here rather than left to be discovered:

- **A week nobody answered falls back to the newest set's matching question.**
  There are no answered rows to read, and the week still has two empty
  histograms to title. The newest set is the same highest-version rule a
  submission is judged against, which keeps one answer to "the set in force" in
  the codebase rather than two.
- **A week whose responses answered two versions serves the newest answered
  version's wording.** Both queries are read the same way, by version
  descending. A mixed week is possible only if a set is re-versioned mid-window;
  serving the newest of the versions actually answered keeps the title a
  question somebody in that week was asked.

The served column is `question.prompt` — the sentence a student reads — verified
against the form rather than assumed: `frontend/src/components/LikertInput.tsx`
renders `<legend>{question.prompt}</legend>`. `question.name` is §3.2's bold
heading ("Instructor rating"), which no student sees, and it stands in only where
a question carries no prompt at all, since that column is nullable.

## Alternatives rejected

**A dated in-force table — `question_set_assignment(term, level, effective_from)`
or similar.** This is what the feature §3.2 anticipates will eventually need, and
it is real machinery: a table, a migration, a selection rule, and a second
question ("what if two rows cover one week?") to settle before any of it can be
read. Nobody needs it until a second set ships, and the ticket that adds one is
the ticket that knows how sets are chosen — per institution, per level, per term.
Building it now would be guessing at that answer and freezing the guess into a
schema.

**The newest set, for every week — the submission rule applied unchanged.** One
query, no join, and wrong in the way that matters: the day a second set ships,
every week already reported is re-titled with a question its respondents were
never asked. A chart labelled with the wrong question is worse than one labelled
with the stream, because it looks right.

**The set whose questions the week's *window* was opened with.** Nothing records
that. A window row carries instants and a week, not an instrument, so this would
need the same new machinery the first alternative needs, reached by a longer
route.

**Formatting the wording into the payload as a finished title.** Rejected for the
same reason the close instant travels as an instant: the presentation — the
mockup's typographic quotes — is the renderer's, and a server that wrote the
quotes would put a piece of the design in the one place a designer cannot change
it.

## Consequences

- A report of an October week keeps October's wording for the rest of the term,
  which is what §3.2's versioning is worth having.
- The read costs two small statements per report: the answered rows for this
  section-week, and the rating questions of the newest set for the fallback.
  Neither is per-stream and neither grows with the term.
- Nothing is stored and no migration is needed, so the day a real in-force rule
  is specified, this is one function to replace rather than a table to unwind.
- A deployment with no rating question for a stream in any set raises rather than
  serving a blank title. That is a broken instrument, not a quiet week, and
  `app.services.submissions.current_questions` already refuses the same way.
