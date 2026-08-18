# Entry 3. A test passed for a reason unrelated to what it asserted

**Caught: 35**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*14 instances recorded; the 3 most recent are below. The earlier 11 are in this file's git history and in the pull requests they cite.*

*(On both sides of E0-17, and it did different work on each.
Writing the tests, it put a control in front of nearly every assertion: a mapped
course before "some course is unmapped", because a seed with no mappings at all
makes every course unmapped; both leads' course sets asserted non-empty before
disjointness, because an empty set is disjoint from anything; a row count
asserted non-zero before "the same rows afterwards", because two empty databases
have the same rows; and the edge count before acyclicity, because a graph with no
edges passes every cycle check ever written. Building against them, it stopped a
green run being believed: twenty-one tests passed in 3.6 seconds, which looked
too fast to have started a container, migrated a database and run two
subprocesses. Three mutations were applied and reverted rather than reasoned
about — the assistant dean moved to lead a course inside a department they
supervise, the one chair who reports straight to the dean re-pointed at the
assistant dean, and `upsert` made never to find an existing row — and one, two
and one tests failed, each of them the one that owns the property.
`docs/tickets/e0/.attempts/E0-17.md` has the table. **The green run was real; the
belief in it was not, until then.**)*

*(In E0-16's review round, and the subject is a *reproduction*
rather than a test. A review reported that a PKCE verifier wrapped in whitespace
redeemed successfully; the script written to reproduce it before fixing anything
answered `400`, in the direction that says "already refused". Both the reviewer
and the script were right and they were exercising different flows: the script
computed the challenge over the padded verifier, where the trimming cancels on
both sides, and the reviewer had bound the challenge over the clean value and
sent the padded one — which is the case where trimming widens what PKCE binds
from one string to every string that trims to it. Reported as "cannot reproduce",
that finding closes as invalid and the 200 stays in the tree. **When a repro
disagrees with a review, the repro is the suspect**: rebuild it from the
reviewer's exact pairing before drawing any conclusion, and say which pairing was
measured. The corrected script answers 200 before the fix and `invalid_grant`
after, on the same instance.)*

*(In E0-16's fix round, and it decided three things about five
tests written *after* the code they cover — which is the position this entry is
hardest to hold, because such a test passes on its first run and proves nothing.
First, the malformed value is 43 characters long, the minimum RFC 7636 allows,
because at any shorter length the provider's length check answers first and the
alphabet check is never reached: the test would pass, name the handling it never
touched, and the mutation run would have shown it too — the implementer's own
pass had already found these two guards masking each other. Second, and sharpest,
the module's shared `refusal` helper said "not 2xx", so a **500 counted as a
refusal** — meaning the replay, mismatch and missing-verifier tests, three
acceptance criteria, would each have passed against the exact crash the round was
about. It now requires a 4xx. Third, the malformed-challenge test walks the whole
flow rather than judging the authorization response, because the value enters at
one endpoint and the crash lands at another: a test that stopped where the value
was submitted would have watched the provider accept it and reported a pass, with
the defect intact one step further on.)*

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
string certainly present — so a search that has gone blind says so.

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
