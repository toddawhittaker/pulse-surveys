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
