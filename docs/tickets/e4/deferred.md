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

## A comment's moderation state is resolved in two places once this wave lands

**What is not enforced.** ADR 0145 makes `moderation_state` append-only with the
latest row governing and the initial state the *absence* of a row, and names the
consequence: "a reader of a comment's moderation state has to write a window
function, or its equivalent … That is E4-04's and E6's to write once, in
`app.services`, not per call site." E4-04 wrote it once, as
`_reported_status_of` in `backend/app/services/report_comments.py`, and both of
that module's reads go through it. E4-06's summary job gathers the same week's
comments and resolves the same state for its own purposes, in a parallel branch
built off the same head — so after this wave merges the resolution exists twice,
in two modules neither of which imports the other. Two copies of "the latest row,
or published" disagree the first time somebody changes one: an `ORDER BY` dropped
on one side, or a default that is not published, is a defect visible in one
surface and not the other, and §5.2's whole lifecycle is about which decision is
current.

**Why it was left.** Neither branch could import the other while both were being
built. E4-04's copy is the one ADR 0145 asked for and it is shaped to be called
from elsewhere — a helper over an answer key, returning a SQL expression rather
than a row — but pointing E4-06 at it would have made that ticket unbuildable
until this one landed, and pointing this one at E4-06 would have put SPEC §4's
suppression behind a module about prompts. The duplication is the price of two
parallel builds and is recorded rather than absorbed.

**Owner:** E4-07, which is the first ticket downstream of both and reads what
each produces.

**Done when:** one helper in `app.services` resolves a comment's moderation state
— the latest row by its decision instant, or the initial state where there is
none — and both the comment read path and the summary job's gather call it, with
no second copy of the ordering or of the default anywhere under `backend/app/`.

## SPEC §6.2's threat and self-harm class is suppressed in neither the comment read path nor the summary gather

**What is not enforced.** SPEC §5.2 ends "threat/self-harm classifications bypass
this flow entirely (§6.2) and are never shown to the instructor", and §6.2 routes
those comments to the Care queue instead. Two modules in this epic read a comment's
moderation state, and neither implements that exclusion. This is one gap seen from
two places, and E4-04 and E4-06 recorded it separately while their branches were
being built in parallel; the entries are merged here, at the merge that made one
tree of them.

*The read path and the release cut* (`backend/app/services/report_comments.py`): a
comment carrying such a verdict is returned by `visible_comments` like any other
above the threshold, is counted by `cut_due_release_batches` toward every leg of
the release gate, and can be written into a release batch and surfaced with its
week stripped — where it cannot be un-released (ADR 0146). The moderation record
this module reads is §5.2's lifecycle (`published`, `flagged_collapsed`,
`excluded`, `kept`), which is a different question from a safety classification and
carries no token for one.

*The summary gather* (`app.services.reporting`): the gather drops a comment whose
latest `moderation_state` row is `FLAGGED_COLLAPSED` or `EXCLUDED` and reads the
absence of a row as published — ADR 0145's rule, and correct for every state that
exists. Bypassing the flow means bypassing the record: nobody moderates such a
comment, so it never acquires a row, and an absent row is exactly what this gather
reads as feed. So the one class §6.2 keeps furthest from an instructor is the class
that would reach a provider and be paraphrased into instructor-visible prose, and
nothing regenerates a summary (the E4 breakdown's decision 2), so it would stay
there for the term.

**Why it was left.** It cannot fire today and a filter for it cannot be written
today, which are two halves of one fact. `ClassificationTask` has exactly one
member, `COMMENT_VALIDITY`, nothing in the system writes a harm verdict of any
kind, and the vocabulary a predicate would select on does not exist. A closed set
written now would be a guess at an enum E6 has not designed — the same reason the
held-note type at the head of this file is still a string, and the same mistake in
the same shape: a set built before the thing it closes over reads as a guarantee
and is not one. What is mechanical instead is the *precondition*. While the
vocabulary has one member the gap is unreachable; the moment it gains a second it
is reachable, and that is a fact a test can hold.

**The shared alarm, so this entry is not a note nobody reads.**
`ClassificationTask` gaining a member is the tripwire for both halves, and it is a
committed test rather than a hope:
`tests/integration/test_the_summary_job_feeds_no_moderation_held_comment_to_the_model.py::test_no_harm_classification_task_exists_yet_for_this_filter_to_have_missed`
asserts `ClassificationTask`'s members as an equality against a set written out in
that module rather than read off the enum, so a second task reds it. It is green
today and required to be. Its failure message states the repair and refuses the
cheap resolution by name: widening the expected set makes the test green and
changes nothing about what crosses to a provider. **The red arrives before the
classifier writes its first verdict rather than after**, which is why the alarm is
on the vocabulary rather than on a verdict row. Whoever adds that member is adding
the first writer of a verdict these paths must not show, and both the read path and
the summary job's gather become live defects on that commit rather than on the
commit that renders them.

**Owner:** E6, in the ticket that adds the second classification task and writes
the moderation states and the safety routing §6.2 describes — before that ticket
merges, not in a follow-up.

**Done when:** a comment whose current classification is a threat or self-harm
verdict is absent from what the read path returns, from what its cutter releases,
and from what the summary gather hands a provider — enforced **below** the read
path rather than in each caller, so a later surface cannot reach the rows by
writing its own query. Proven by a test that plants such a verdict on a comment in
a week at the threshold and asserts the forbidden state at the service's return
value, at the batch's membership, and at the gather's model-facing input. That test
can only be written once a verdict of that kind can exist, which is why the
writer's ticket owns it.

## The report's three copy modules sit outside the collector, so nothing sweeps their strings

**What is not enforced.** SPEC §4.1 items 4 and 5 — the aggregate-language rule
and the confidentiality-copy rule — are enforced by the invariant-marked
inventory test over the strings `tests/fixtures/copy_inventory.py` collects, and
that collector walks `frontend/src/copy/`. The report's three copy modules are not
in it: `instructorReportTrendCopy.ts`, `instructorReportStatCopy.ts` and
`instructorReportCommentCopy.ts` all ship in `frontend/src/components/` beside the
components that read them. Every word an instructor reads on the trend, stat and
comment surfaces is therefore held to items 4 and 5 by review and by a header
paragraph in each file, which is weaker than the way the survey surface's strings
are held.

**Why it was left.** The inventory test reds on any key prefix its governance map
does not list, and it is `invariant`-marked, so moving a file under
`frontend/src/copy/` without growing that map reds a §4.1 gate. Growing the map is
heavy-lane work over the whole report surface and belongs to one ticket rather than
to three. E4-08, E4-09 and E4-10 are light tickets scheduled before it, and a light
diff may not reach a heavy surface — so each of them put its copy module beside its
components, said so in the file's own header, and left the move to the ticket that
owns the map. This entry is that decision recorded where the epic can see it rather
than only in the files that work around it, which is `docs/MISTAKES.md` entry 48.

**Owner:** E4-12, which grows the inventory over the report surface.

**Done when:** all three files are collected by
`tests/fixtures/copy_inventory.py`'s own walk, their key prefixes are in the
governance map, and the items-4-and-5 vocabulary gate has been seen running over
their strings — E4-12's acceptance criterion 7 states it, and closing it closes
this entry.
