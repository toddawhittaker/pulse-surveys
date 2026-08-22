# Entry 3. A test passed for a reason unrelated to what it asserted

**Caught: 51**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*30 instances recorded; the 3 below are the most recent, newest first. The
earlier 27 are in this file's git history and in the pull requests they cite.*

*The trim the last reader asked for has been done, from git rather than from the
page order, and the warning was worth writing down: the two E0-36 paragraphs
were **not** in chronological order, so cutting from the bottom would have kept
the older of the two. Dating a paragraph is `git log -S"its first phrase"` on
this file.*

*(Writing E0-40's tests (Batch I, 2026-08-22, found while building that ticket —
it has not merged), and this one is the entry working rather than the entry
catching: the prescriptions were applied deliberately, before anything was green.
The ticket's subject is gates that probe for a path nothing writes, so the tests
are searches over workflow and `Makefile` text — the exact instrument this entry
warns reads as coverage. Each search carries a canary: **a pattern must be shown
to match something before its non-match means anything**, and two of them exist
only to say so. The counts are asserted non-zero rather than merely equal, so a
search that has gone blind cannot agree with an expectation of nothing. And the
equality that matters — what a collector reports against what a scan of the tree
finds — carries a planted-divergence control, a tree deliberately made to disagree,
which is what turns "the two agree" from a sentence into a measurement. That
control is the part worth copying: an equality assertion between two derivations
of the same fact is worthless until somebody proves it can fail.)*

*(Writing E0-28's tests, and it is the shape where **the walk cannot fail the
assertion it is walking for.** Item 5 asks that a paged container carry `next`
only where a next page exists, and the obvious test walks a multi-page roster and
requires `next` absent on the last page and present on the others. Both are true
of any walk by construction — `link_walk` stops when a page advertises no `next`,
so the assertion is a restatement of the loop condition and would pass against a
container that advertised one page too many. What can see that defect is a
container that fits on a single page, and only if "single page" is defined as
*the first page holds every member the container has* rather than as "the walk
returned one page": under the very mutation it is written against, the walk
returns two. The same round moved item 4's fail-open test off `limit=1` — with
one filtered result and a page size of one, the filtered and unfiltered pages are
the same page and a lost filter is invisible — and made it follow the relations
the platform advertises with no limit at all, over a container the test first
proves carries more than one student.)*

*(The dev-only test console, and it is the shape where **the page under test can
be empty and the assertion still passes.** The console fetches the mock provider's
roster and lists the web-login people as sign-in links; the obvious integration
test renders `/dev` and asserts the dean's subject appears in the body. Against a
roster that came back empty — a fetch the seam refused, a provider seeded with
nobody — the page says nothing and "the subject is absent" is trivially true, so
the test would go green over a console that lists no one. It now asserts the
provider's own published roster really holds the two named subjects before
looking for them on the page. The same round has two HTML parsers, one reading
which `<option>` carries `selected` for the mock IdP's `login_hint` pre-select
and one reading which `<a>` carries `target="_blank"`, and each is the pattern
this entry warns of: each ships a control test run against markup it must flag and
markup it must let past, because a parser blind to the attribute makes "the right
option is selected" and "nothing is selected" both pass. And the login-form
pre-select carries its near miss — an unknown or absent `login_hint` must select
**nothing** — so the feature cannot pass by always selecting the first option.)*

**What happened.** A test asserting that a startup error carries no credential
passed against a demonstrably leaking implementation, because ten variables
happened to be set and pydantic's repr elision landed between the two passwords.
Separately, a set-equality test would have passed comparing two empty sets, if
a workflow's shape changed so nothing was collected.

A third, in E0-03, inside the test written to enforce entry 1 below. It asserted
that `ci.yml` no longer carries E0-02's note that "`worker` and `beat` join the
argument list in E0-03", by searching the file text for that phrase. The comment
wraps at 80 columns, so between `join the` and `argument list` the file holds a
newline, six spaces and a `#`. The pattern was written with a plain space. It
matched nothing, and the test went green against the exact comment it existed to
catch — reported as failing, because it had been read rather than run.

A fourth, caught before it landed, and recorded because of where it came from
rather than what it cost. A reviewer's sketch for the E0-06 test holding ADR 0018
ended "assert that afterwards the term still reads N weeks with week N still
present". The refused `UPDATE` runs inside `begin_nested()`, so by the time
anything could query, the savepoint has rolled back and the term reads N whatever
the database did — the assertion cannot fail. It is the same assertion
`tests/integration/test_org_containment_schema.py` deleted for the same reason
during E0-05, proposed again by a careful reader one ticket later. The shape is
attractive because it reads like thoroughness.

A fifth, in E0-08, and it is a shape none of the four above has. The test for
"an enrollment rejects an end date before its start date" wrote a backwards
window and asserted the database refused it. It could not fail. The *other*
criterion in the same ticket is enforced by an exclusion constraint over
`daterange(started_on, ended_on, '[]')`, and Postgres will not construct a range
whose end precedes its start — the error comes from evaluating the expression,
before any constraint is consulted. So the refusal arrived whether or not
anything stated criterion 4's rule, and deleting the check constraint left all
fifteen tests in the module green. Every control that test needed was present and
correct: controls stop a refusal being unrelated to the *row*, and this refusal
was unrelated to the *constraint*. The implementer found it in its own work and
declared it.

A sixth, in E0-10, and it is the first one found by running a mutation the test
itself named. `test_every_read_view_is_created_from_a_sql_file_under_views_sql`
says what it is built against: "move the `CREATE VIEW` into `op.execute("...")`
in a revision file and the sweep below has nothing to read while staying green."
That mutation was performed — `section_roster_v001.sql` deleted, its SQL inlined
into the revision — and all seven tests in the module stayed green. The test
searches the combined text of `views_sql/` for the view's *name*, and
`identity_grants_v001.sql` names both views because it grants on them. So the
sweep is satisfied by a mention and the assertion it advertises is about a
definition.

**Root cause.** Asserting an absence. Absence is satisfied by the thing being
broken in an unrelated way, by a fixture returning nothing, by a parser matching
nothing. In the third case, by the difference between what a sentence looks like
in a file and what it is as a string. In the fifth, by a second mechanism in the
same schema that refuses the same row for its own reasons — "the database said
no" does not say which part of it said so. In the sixth, by a search that matches
the *name* of the thing rather than the thing, in a directory where the name
appears for three unrelated reasons.

**Consequence. ** A green suite is read as coverage. The first case would have
been counted as proof the leak was fixed when it proved nothing about it. The
fifth would have let a later ticket delete a constraint as redundant, with the
rule it states surviving only as a side effect of how overlap happens to be
enforced today. The sixth leaves a layout decision — where a view's SQL lives —
recorded in an ADR and enforced by nothing, which is the state the ADR now says
it is in rather than the state it claimed.

**Rule.** Verify by mutation, not by reading: break the thing and watch the test
fail. Where a test can be satisfied by emptiness, assert non-emptiness first, and
say in the message why that guard is not ceremony. A pattern searched against a
file is a case of this and looks like none: run it against the text you claim it
catches *and* against the text you claim it allows, and give it a canary — a
string certainly present — so a search that has gone blind says so. **Build that
canary sample by copying whole lines, the line the sentence starts on included.**
A sentence retyped from where you think it begins is the thing the sample exists
to disprove, and a comment wrap is exactly what puts the boundary somewhere you
did not expect.

**A mutation a test names in its own docstring is a claim, not a record.** Run
it. The sixth case is a test that named the exact edit it exists to catch,
carefully, in the file — and the edit did not catch it. A named mutation is the
cheapest one to try and the one least likely to have been tried.

**Where two rules can refuse the same row, a behavioural test cannot tell you
which one did.** Mutation is what exposes it — delete the constraint and see
whether anything goes red — and the fix is to assert the rule is *stated*, out of
what the catalog reports, as well as that the row is refused. Both, not either:
the catalog test cannot see whether the rule works and the behavioural test
cannot see whether it exists.

---
