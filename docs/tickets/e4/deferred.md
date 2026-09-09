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

**Closed by E4-07, and it opened the entry below.**
`app.services.report_comments.reported_status_of` is public, the summary gather in
`app.services.reporting` calls it, and no second statement of the ordering or of
the default is left under `backend/app/` —
`tests/unit/test_the_moderation_state_ordering_has_one_home_under_backend_app.py`
counts the modules that name the relation in executable code and holds the tree to
one. E4-06's tests are green unmodified.

Consolidating it is what made the ordering itself reviewable, and E4-07's security
round then found that neither of the two orderings was right. That is the next
entry, and it is a real gap rather than a note about this one.

## `moderation_state` has no ordering a same-instant tie can be broken by

**What is not enforced.** ADR 0145 makes the record append-only with "the latest
row governing", and `reported_status_of` implements that as `ORDER BY decided_at
DESC LIMIT 1`. `decided_at` is a `now()` server default, which in PostgreSQL is
the **transaction** timestamp: every row written in one transaction carries the
same instant to the microsecond. Two decisions about one comment in one
transaction therefore tie, and `LIMIT 1` picks between them arbitrarily — so "the
latest decision" can resolve to the earlier one, and a comment a moderator
excluded can come back `published`. It is the same defect from either side: E4-06's
copy broke the tie on `moderation_state.id`, which is `gen_random_uuid()` and
therefore a coin flip rather than an order; E4-04's copy, which is now the one
home, breaks it not at all.

Nothing in E4 can reach the state, and that is why it is deferred rather than
fixed here: E6 writes the first `moderation_state` row this system will ever hold,
so today the subquery has nothing to order and every comment resolves to the
initial state by absence. The consequence is a future one, and it is a
confidentiality consequence — a held comment shown — rather than a cosmetic one.

**Why it was left.** The fix is a schema change: an explicit monotonic column, a
migration, a backfill rule for a table with no rows, and a writer that sets it.
E4-07 is a read ticket that was told to expect no migration, and inventing the
column here would settle the shape of E6's own write path from a ticket that
writes nothing. What E4-07 could do it did: put the ordering in one place, so
there is one function to change rather than two.

**Owner:** E6, in the ticket that writes the first moderation decision — before it,
not after. A writer landing on this ordering is a writer whose first same-transaction
pair is already wrong.

**Done when:** `moderation_state` carries an explicit monotonic sequence column
that a same-transaction pair cannot tie on, `reported_status_of` orders by it, and
a test plants two decisions about one comment inside a single transaction and
requires the second to be the one reported — driven both ways round, since a tie
broken arbitrarily passes half of such a test by luck.

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

**Closed by E4-12.** All four report copy modules — the three above and
`instructorReportPageCopy.ts`, which E4-11 shipped after this entry was
written — moved into `frontend/src/copy/`, their five prefixes govern one
`report` surface, the collector's own list names every file, and the
vocabulary gate was seen failing against a planted "underperforming" in
report copy. The header paragraphs that recorded the workaround moved out
with the files. The stat module's two number formatters, which name their own
keys and so cannot sit below a copy literal the parser accepts, live in
`frontend/src/components/instructorReportFigures.ts` — the one departure from
"a move, not a rewrite", recorded in the ticket's attempt log.

## The report API's two refusal sentences sit outside the copy registry

**What is not enforced.** SPEC §4.1 items 4 and 5 are checked over the inventory
`app.copy.copy_modules()` publishes, and `app.api.instructor` serves two strings
that inventory cannot see: the shared 404 a section outside the session's teaching
set and a section that does not exist both get, and the 404 for a course week the
section has no window for. Both are module constants in the router. They name
nobody and nothing — a refusal answered to anybody who can make a request may
describe only itself — and that is held by review and by the module's own header
rather than by a sweep.

**Why it was left.** The inventory governs a key by its surface prefix and reds on
a prefix no surface claims, and it is `invariant`-marked. So a copy module for the
report surface cannot land before the report is a governed surface, and making it
one is work over the whole surface rather than over two strings — the same reason
the entry above leaves three frontend copy modules beside their components, and the
same position the gradebook's two instructor-visible strings are already in
(`docs/tickets/e4/carried-from-e3.md`). Writing the sentences into the router and
recording it here is the alternative to inventing a surface for the inventory to
police.

**Owner:** E4-12, with the rest of the report surface's copy and the governance map
it grows.

**Done when:** both sentences are entries in an `app.copy` module under a prefix the
inventory's governance map claims for the report surface, `app.api.instructor` looks
them up by key rather than holding them, and the items-4-and-5 vocabulary gate has
been seen running over them.

**Closed by E4-12.** `backend/app/copy/instructor_report.py` publishes
`instructor_report.section_unavailable` and `instructor_report.week_unavailable`
under a prefix the governance map claims for the report surface; the router's
two constants are reads of those entries, held to them by a live-object
equality test (equal text proves no drift, and that the constants are reads is
visible in the diff); and the vocabulary gate was seen failing against a
planted "underperforming" in the week refusal. The refusal pair's one-body
no-oracle property is unchanged and was re-checked by the ticket's security
review.

## The course label is composed in two modules

**What is not enforced.** FIX-01 item 2's governed course label — "MATH 140 E1FF —
College Algebra, Fall 2026", the owner's ruling of 2026-09-03 — is composed in
`app.services.survey_read._course_label` for the student's own page and again in
`app.services.reporting._course_label` for the instructor's report. The two strings
agree today because one was copied from the other. Nothing holds them together, so
an amendment applied to one names the same course differently on the two surfaces,
and neither surface can see the other's version.

**Why it was left.** E4-07 was scoped not to touch
`backend/app/services/survey_read.py`, and promoting a private function to a shared
one crosses a module boundary — which this repository's build rules have a ticket
propose rather than do. E4-07's pull request carries the proposal. The alternative
inside the ticket's scope was to import the private name across modules, which is a
worse shape for the same guarantee.

**Owner:** whichever ticket next changes the label's form, or accepts E4-07's
proposal. (E4-17 was the first candidate when this was written; it merged
without touching either copy, so the candidacy lapsed — noted by the E4
boundary's docs review. `app/services/enrollment_windows.py`, ADR 0161, is
now the worked example of exactly this promotion done under review.)

**Done when:** one function composes the label, both the student read path and the
report read call it, and no second copy of the format is left under `backend/app/`.

## E4-07's two keyed routes state `Cache-Control: no-store` and nothing asserts it

**What is not enforced.** `app.api.instructor`'s report route and published-week
list both set `Cache-Control: no-store`, and their module docstring says why —
a stored copy of a report holds raw student comments and outlives the reason it
was shown. No test reads the header off either route: E4-18's battery went
looking for the existing routes' header tests to use as stay-green controls and
found that the only instructor route with one is E4-18's own section list
(`tests/integration/test_the_student_survey_paths_pin_cache_control_no_store.py`
pins the student paths, nothing pins these two). A later edit could drop either
header and the suite would stay green.

**Why it was left.** Found during E4-18's verification, and E4-18's diff does
not touch either route — adding their tests here would put an unrelated
assertion into a ticket whose scope is the section list. The gap is E4-07
coverage, not E4-18 behavior.

**Owner:** E4-15, the exit ticket that drives these routes against the running
stack.

**Done when:** a test asserts the exact `no-store` value on both keyed
instructor routes, the way the student-path pin and E4-18's own header test
assert theirs.

**Closed by E4-15.**
`tests/integration/test_the_instructor_report_paths_pin_cache_control_no_store.py`
pins both routes to the exact value with a status-200 premise guard first and
the non-equivalents named; both header lines were each deleted in turn and
each reddened exactly its own test, twice over (the build battery and an
independent re-run). Deliberately not invariant-marked, with the reason in
its docstring; the boundary's invariant-coverage review recorded a partial
disagreement with that classification and accepted it as argued.


## The landing views' sentences sit outside the inventory and outside the sweep

**What is not enforced.** The four landing views render their sentences from
`frontend/src/lib/landings.ts`, which is outside `frontend/src/copy/` (so the
inventory does not collect it) and outside `frontend/src/components/` and
`frontend/src/routes/` (so E4-12's string sweep does not read it). SPEC §4.1
items 4 and 5 are asserted over neither. Today's strings are pinned
byte-for-byte by `tests/e2e/landing-views.spec.ts` as a drift proof, so they
cannot change silently — but a string added there ships ungoverned.

**Why it was left.** The carried done-when E4-12 built to names the component
and route trees, and the landing sentences are neither report copy nor new;
widening the sweep over `lib/` mid-ticket would have been scope the ticket's
own boundary refuses. ADR 0159 discloses the limit.

**Owner:** whichever epic next touches the landing views — E9, which renders
the leadership shell, is the first candidate.

**Done when:** the landing strings are collected under governed prefixes (a
copy module per surface, rows in the governance map, the line-or-no-line
decision made for each landing), or a recorded decision widens the sweep's
scope over `frontend/src/lib/` instead.
