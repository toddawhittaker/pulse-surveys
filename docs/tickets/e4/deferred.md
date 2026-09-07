# E4 — deferred

What an E4 ticket chose not to fix while it was in the file, with an owner and
the condition that closes it. A PR that defers something adds it here in the same
PR; E4-15 runs the cleanup pass over this file at the epic exit.

A deferral is a decision, not a note. Each entry says what is not enforced, why
it was left, who owns it, and what "done" means — a gap recorded only as a
comment in the file that works around it is `docs/MISTAKES.md` entry 48.

## The summary's held-note type is a free string, so §5.2's exclusion is not enforced

**What is not enforced.** `WeeklySummaryRecord.held_note_type` is `str | None`.
SPEC §5.1 lets a summary above small-N note "one comment is held for review" with
type only, and §5.2 routes threat and self-harm out of every instructor and
leadership view to the Care queue (§6.2) — so those two verdicts may never be the
type in a summary an instructor reads. Nothing in the type stops one being
written there. The field's own docstring says so, and this entry is the record
that says it out loud where the epic can see it.

**Why it was left.** E4 has no moderation. E6 writes the states this type would
enumerate, and a closed set guessed at now would be built before the thing it
closes over exists — a set that is wrong is worse than a string, because it reads
as a guarantee. In E4 the field is `None` on every record the epic produces, and
a test asserts that default, so nothing renders a held note during this epic.

**Owner:** E6, in the ticket that writes the moderation states a summary can cite.

**Done when:** the held-note type is a closed set that cannot express threat or
self-harm, enforced where the note is written rather than where it is rendered —
so a caller cannot construct the excluded value at all, and §6.2's suppression
does not depend on every reader remembering it.

## A comment can forge block boundaries and inflate a theme's count within the week's total

**What is not enforced.** The summary prompt renders a week's comments as
numbered blocks separated by blank lines, and the only boundary between two
comments is that convention. A comment that itself contains a blank line and a
line reading like a block label reads, to the model, as two comments. The task
refuses any theme claiming more comments than the week held (ADR 0148's fifth
decision), so an inflated count is bounded by the true total; within that total,
a forged boundary can still raise the count a theme is credited with. Nothing
structural prevents it.

**Why it was left.** The validity prompt already carries the same soft
prompt-injection posture — a comment is data, instructed to count for nothing
when it tries to instruct — and the bound above limits the consequence to a
prevalence figure inside the week's own size, never a confidentiality or
authorization boundary. Closing it needs an unforgeable per-comment delimiter,
which is a change to the rendering scheme every prompt version shares rather
than one task's fix, and E4-05's independent security review accepted the
residual on that reasoning.

**Owner:** whichever ticket next changes the multi-comment rendering scheme or
adds a second task that renders several comments (E7's draft and draft check are
the first candidates).

**Done when:** a comment cannot make the rendered prompt read as more comments
than were handed to the renderer — proven by a test that plants a comment
containing a blank line and a block-label lookalike and asserts the model-facing
boundary count equals the true count.

## The summary gather excludes moderation-held comments and not §6.2's threat and self-harm class

**What is not enforced.** `app.services.reporting`'s gather drops a comment whose
latest `moderation_state` row is `FLAGGED_COLLAPSED` or `EXCLUDED`, and reads the
absence of a row as published — ADR 0145's rule, and correct for every state that
exists. SPEC §5.2's last bullet routes a different class of comment around that
record entirely: "Threat/self-harm classifications bypass this flow entirely
(§6.2) and are never shown to the instructor." Bypassing the flow means bypassing
the record — nobody moderates such a comment, so it never acquires a row — and an
absent row is exactly what this gather reads as feed. So the one class §6.2 keeps
furthest from an instructor is the class that would reach a provider and be
paraphrased into instructor-visible prose, and nothing regenerates a summary (the
E4 breakdown's decision 2), so it would stay there for the term.

**Why it was left.** It cannot fire today and a filter for it cannot be written
today, which are two halves of one fact. `ClassificationTask` has exactly one
member, `COMMENT_VALIDITY`, and nothing in the system writes a harm verdict of any
kind; the vocabulary a predicate would select on does not exist. A closed set
written now would be a guess at an enum E6 has not designed — the same reason the
held-note type at the head of this file is still a string, and the same mistake in
the same shape: a set built before the thing it closes over reads as a guarantee
and is not one. What is mechanical instead is the *precondition*. While the
vocabulary has one member the gap is unreachable; the moment it gains a second it
is reachable, and that is a fact a test can hold.

**The alarm, so this entry is not a note nobody reads.**
`tests/integration/test_the_summary_job_feeds_no_moderation_held_comment_to_the_model.py::test_no_harm_classification_task_exists_yet_for_this_filter_to_have_missed`
asserts `ClassificationTask`'s members as an equality against a set written out in
that module rather than read off the enum, so a second task reds it. It is green
today and required to be. Its failure message states the repair and refuses the
cheap resolution by name: widening the expected set makes the test green and
changes nothing about what crosses to a provider. **The red arrives before the
classifier writes its first verdict rather than after**, which is why the alarm is
on the vocabulary rather than on a verdict row.

**Owner:** E6, in the ticket that adds the second classification task — before it
merges, not in a follow-up.

**Done when:** the summary gather excludes comments whose current classification
is in the threat or self-harm set, asserted with a planted verdict of that class,
before any writer of one exists.
