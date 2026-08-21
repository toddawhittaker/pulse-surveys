# Entry 3. A test passed for a reason unrelated to what it asserted

**Caught: 44**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*23 instances recorded; the 3 below are the most recent, newest first. The
earlier 20 are in this file's git history and in the pull requests they cite.*

*The trim the last reader asked for has been done, from git rather than from the
page order, and the warning was worth writing down: the two E0-36 paragraphs
were **not** in chronological order, so cutting from the bottom would have kept
the older of the two. Dating a paragraph is `git log -S"its first phrase"` on
this file.*

*(Writing E0-30's error-redirect battery, and it is the shape where **the
obvious assertion is satisfied by three different wrong providers at once**.
"The refusal is a 3xx to the registered URI carrying `error`" passes against a
provider that hands back an authorization code beside the error, against one
that answers a single constant code for every refusal, and against one that
re-encodes the `state` a client will compare byte for byte. So the helper every
redirect case goes through refuses a `code` in the returned query, requires
`error` to be one of RFC 6749 §4.1.2.1's codes **and** each test to say which,
and requires `error_description` to carry something. The page assertions were
worse, and worse in exactly the way this entry is named for: "this refusal did
not redirect" was a true statement about the provider as it stood, which
redirected nothing at all — all eight page cases passed on the day the ticket
opened and would have gone on passing over an implementation that never changed.
The ordering near miss, which is the one that guards against an open redirector,
now asserts both halves in one run: the same unknown scope with the registered
redirect URI must redirect, and with an unregistered one must not, so the
negative half is only read once the positive half has been seen.)*

*(Writing E0-26 item 1's tests, and it is the "assertion that cannot fail" shape
in the place it is hardest to see — inside a control. The refusal test for a
non-Care actor took the committed `audit_log` total before and after the refused
`record_identity_reveal` call and asserted it had not moved, on the reasoning that
a function checking the actor *after* inserting the row would be caught. It cannot
be. A `RAISE` aborts the caller's transaction, so a row written before the check is
discarded by the caller's own `ROLLBACK` whatever the implementation did, and the
two orderings produce exactly the same count. Only a record written over a second
connection would make the ordering observable, and this ticket rejects that
mechanism. The assertion was removed, and what stands in its place is one that can
fail — the permitted call's returned id must name a committed row read from the
second connection, which kills a recording call that answers a uuid it invented.
The docstring now says the ordering is worth doing and is not observable from
here, so the next reader does not add the check back.*

***A second application in the same ticket, counted once**, and it arrived through
a fixture guard firing. `user_identity.identity_email` is nullable, the seeding
helper fills only what the schema requires, and **nothing in `tests/` had ever
seeded that column** — so every identity row the suite had ever made carried a null
address. Two assertions written against it were therefore satisfied by nothing: the
honest path's `returned["identity_email"] == revealable.identity_email` was
`None == None`, and the leak half of the subject-substitution test asked whether the
*other* student's address appeared in what came back, which is true of any result
at all when that address is `None`. The obvious repair — seed an address for the
one subject whose guard fired — would have left both. Both students are now seeded
with an address explicitly, and the optional-address case that the null was
accidentally standing in for became a subject of its own with a test that names it.
Three cases that had been one are now three: a name with an address, a name with
none, and no identity row at all.)*

*(Writing E0-38's tests, and it is the variant where **the safe reading and the
asserting reading are the same exit code**. The classification E0-38 adds must
fail toward running everything, so the pipeline has to read any non-zero exit —
a crash, a bad argument, a missing file — as "not inert, run the full pipeline".
The obvious `classify()` helper copies that: exit 0 is inert, anything else is
not inert. Six of the seven behaviour cases in the module assert **not inert**,
and no classifier existed yet, so `sys.executable` on a script that is not there
exits 2 and all six would have passed on the day the ticket opened — a red-green
ticket whose tests were green before anybody started, and which would have stayed
green over a classifier that crashed on every input. `classify()` now fails
loudly on a missing file and on any exit outside the two the contract names, so a
not-inert verdict can only come from a classifier that ran and decided. The same
reading put two controls and a canary on the sweep that derives the parsed
documents from the suite: it must find the document in a module shaped like
`test_ai_contracts.py`, find nothing in a module that only cites documents in
prose, and still find `docs/SPEC.md` in the real tree — because a reader that has
gone blind reports that the suite parses no documents at all, which satisfies
"every document a test reads is outside the inert set" perfectly.

**A second application in the same ticket, counted once.** The test that holds
the `python3`-not-`python` fix runs the workflow step on a planted PATH holding
`git` and `python3` and no `python`. The whole battery is satisfied by a PATH on
which `python` is still resolvable — under it the mutation runs perfectly and
every case passes — and whether it is resolvable depends on the machine the suite
happens to be on, not on anything the test controls. So the absence is proved by
running `command -v python` under the planted PATH and requiring it to fail,
before any case is believed. An environment a test builds is as capable of being
wrong as one it finds.)*

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
