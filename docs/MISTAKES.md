# Mistakes

Things that have actually gone wrong in this repository, and the rule that
prevents each one happening again. Every entry is a real incident with a real
consequence — nothing here is hypothetical, and nothing is here because it
sounded like good advice.

**Read this before you start work.** It is short on purpose, and it is ordered
so the first entries are the ones that keep happening.

## How to use it

**Consulting it.** Read the headings. If one describes something you are about
to do, read that entry and act on its rule.

**Bumping the counter.** When an entry stops you making the mistake, increment
its `Caught:` number in the same change as the work it saved. That number is the
only signal for what belongs at the top, so an entry nobody bumps sinks and an
entry that keeps saving people rises. Do not bump for reading an entry — bump
for an entry changing what you did.

**Adding an entry.** When something goes wrong, append: what happened, the root
cause, the consequence, and the rule. Cite the real artifact — the commit, the
file and line, the pull request. A rule with no incident behind it is advice,
and advice belongs in `CLAUDE.md`.

**Re-ordering.** Sort by `Caught:` descending when you notice it is wrong. Ties
break toward the more expensive consequence. **An entry keeps its number when it
moves**, so the headings below are not in numerical order and are not meant to
be. The number is the entry's name: code comments, commit messages and test
docstrings cite "entry 7", and renumbering would silently repoint every one of
them at a different incident.

---

## 3. A test passed for a reason unrelated to what it asserted

**Caught: 31**

*(The thirty-first, on both sides of E0-17, and it did different work on each.
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

*(The thirtieth, in E0-15's review round, and three tests at once — each asserting a
strictly weaker property than its own name. Two of the three were found by reviewers
reading the finished suite rather than by anyone writing it, which is the part worth
keeping: the tests had already been read, twice, by the people who wrote them. The
sharpest is the late add: `a_seeded_section_holds_a_member_who_enrolled_after_their_classmates`
asserted that a section held more than one distinct enrollment `start`, which is
satisfied by an enrollment a month **early**, and a reviewer proved it by setting the
seed's late add backwards and watching every test stay green. A test named for a
direction was passing on the inverse of it. The other two are the same shape in
quieter clothes: `end is not None` cannot tell an absent key from a null one, so a
window emitted with no `end` at all passed; and "no member is dropped", checked
against the two users the launch page offers, passed a page slice that lost one
member per boundary, because both those users sit at the head of every roster. **The
general rule, which none of the three had:** when a criterion is about an ordering or
a shape, assert the ordering or the shape — "the values differ" is a property of the
case and of its mirror image, and the mirror image is what ships.)*

*(The twenty-ninth, writing E0-15's tests for the mock platform's roster and grade
services, and it decided six of them. "No member is duplicated" is a count against a
count, which is `n == n` over a roster that fits on one page — so the test finds the
rosters that came back on more than one page first and fails if there are none, and
its sibling asserts the first page is *shorter* than the assembled membership. "A
posted score is retrievable" is asserted with an `activityProgress` of `Submitted`
and a `gradingProgress` of `PendingManual`, because a stub that hardcodes the
obvious pair passes a round trip posted as `Completed`/`FullyGraded`; and with a
fixed past second for the timestamp, because a recorder stamping its own clock
cannot coincide with one. The seed's dropped member is asserted beside a member who
is still `Active`, since a roster reporting everybody `Inactive` satisfies "somebody
is not Active" with no drop in it. And both matchers this suite invented — §2.2's
section code and §8's course-number bands — are run against what they are claimed to
catch and what they are claimed to allow, in their own tests, before any silence
from them counts.)*

*(The twenty-eighth, writing the tests for E0-11's two review dispositions, and it
decided the shape of both. An `ASSISTANT_DEAN` assignment's own grant is asserted
**empty**, which is this entry's own shape, so each of the three tests for it
carries a control resolved on the same session against the same rows — a `DEAN` on
the same college, and a supervised chair — because an `own_grant` broken to answer
an empty purview for every role would otherwise pass all three and read as the
defect fixed. And the test that the migration refuses a stored non-climbing edge
asserts the failure names one of the two **row keys** rather than the role pair: a
`DatabaseError` renders the statement that raised it and the migration's own SQL
spells `LEAD_FACULTY` in its rank map, so a role-name match would be satisfied by
an anonymous failure that merely echoed the statement.)*

*(The twenty-seventh, in E0-11's arbitration round, and it caught the same shape
twice in one afternoon. First, three tests in `test_identity_grants.py` reached
their subject with `alembic downgrade -1` — a step chosen relative to head, so on
a branch carrying a new revision they undid E0-11's work while asserting facts
about E0-10's. They were red, which is the lucky version. Second, and worse
because it was green: `test_an_assignment_that_reports_to_itself_is_refused`,
`test_a_two_assignment_cycle_is_refused` and `test_a_three_assignment_cycle_is_refused`
all passed against the new rank rule rather than against the cycle guard they are
named for, and the two-assignment test's message assertion passed only because
`CYCLE_ERROR_FRAGMENTS` held `"supervis"` while the rank rule's message reads "a
supervision edge runs from a role to one that outranks it". Three tests named for
a guard, none of them reaching it, and a fragment list meant to identify one guard
satisfied by another's wording. The repair plants a non-climbing edge under the
superuser bypass so the cycle walk has a subject that exists, and splits the
fragments into a cycle set and a rank set so a test can say which answered.)*

*(The twenty-sixth, in E0-11, and it decided the shape of a measurement rather
than of a test. The claim was that the new revision's `downgrade()` restores
E0-09's trigger function body, and "the body matches after the downgrade" is
satisfied by a database nobody changed and by two bodies that were always
identical — so the script asserts the two differ **at head** before it downgrades
anything, and reads the expected body out of revision `014ccb3d0fe5`'s own text on
disk rather than out of `pg_proc`. It is also why the rank check was placed
*after* E0-09's Care-children rule in the same function: with it first, the test
that turns a chair with children into a `CARE` assignment would still pass, and
would pass because of a rank comparison rather than because of the rule it is
named for.)*

*(The twenty-fifth, and it caught a line inside this entry's own reader. Writing
E0-11's tests for the deferred purview union, the first draft put
`assert refused.value is not None` after a `pytest.raises(NotImplementedError)`
block — the exact assertion the twenty-second below records deleting from an
E0-10 service test, reintroduced one ticket later by a session that had just read
it. `pytest.raises` has already made that true. It is now a `try/except/
pytest.fail` that reports the value that came back instead, which is the thing
worth seeing: ADR 0003's whole subject is that an empty `Purview` is what a
broken seam returns. The same entry is why the two-lead disjointness test asserts
both purviews non-empty before asserting they do not overlap — two empty sets are
disjoint — why the n-threshold override is asserted to differ from the configured
default before it is used, and why every scoped read that must be refused is
preceded by one that must succeed on the same reader.)*

*(The twenty-fourth, and it caught an assertion in a brief rather than in a file.
The tests for E0-10's downgrade were specified down to the statement, and one of
them — `has_database_privilege('pulse_app', current_database(), 'CONNECT')` is
still true after the downgrade — cannot fail: Postgres grants `CONNECT` to
`PUBLIC` on every new database, so that call answers true for every role in the
cluster, with the grant revoked, with the role holding nothing at all, and on a
database nobody has migrated. The test asserts the entry in `datacl` instead,
which is the thing a `REVOKE` in `downgrade()` would actually remove. This entry
is also why each of the three downgrade tests reads its baseline at head before
undoing anything — every assertion after the downgrade is that a set is empty,
and an empty set is what a database with no grants in it produces — and why
`only_the_identity_revision_was_undone` exists: `-1` is relative to head, so the
day a revision lands on top of this one, every one of those emptiness assertions
is satisfied by a downgrade of something else.)*

*(The twenty-third: the tests for E0-10's Care-credential fix. "`worker` and
`beat` must not hold `CARE_DATABASE_URL`" is satisfied by a stack that blanks it
everywhere, which also has no Care queue at all — so this entry is why the
Compose rule asserts `api` holds a value before it asserts anybody else does
not, why the absolute rule checks each variable's one permitted owner still
carries it, why the interpolation rule keeps the walker canary its superuser
sibling has, and why the engine that refuses an absent credential is also
asserted to build one when the credential is there. Five guards, all of the same
shape, none of them ceremony: each names a way the rule beside it passes against
a system with the feature deleted.)*

*(The twenty-second: repairing the sixth incident below. The replacement sweep
requires a `CREATE` of the view rather than a mention of it, and this entry is
why it ships with six must-allow samples — `GRANT`, `REVOKE`, `DROP`,
`COMMENT ON`, a name in a comment, and a different view whose name begins the
same way — each of which the old version accepted as evidence that a view was
defined. It is also why the E0-10 service test ends at `pytest.raises` rather
than at `assert refused.value is not None`, which cannot fail.)*

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

## 1. A record went on asserting something the change had made false

**Caught: 29**

*(The twenty-ninth, twice in E0-17 and both times about a sentence counting
something. Writing the tests, it corrected a claim in `tests/conftest.py`'s own
header that had gone stale — the file said E0-11 added its fixtures "at the very
bottom", which stopped being true the moment E0-17 added two below them.
Implementing, the sweep outward from "`scripts/seed.py` now reads `.env`" reached
`.env.example`'s opening paragraph, which told every reader the file "has three
readers, not one" and named them. It had four from the moment the seed landed, and
nothing would have failed: no test counts readers, and the sentence is the one a
person consults when deciding whether a new variable can be documented there.
ADR 0008's amendment line and its index row carry the same count and were changed
in the same commit. **A number in a prose sentence is a record with a scheduled
expiry, and the expiry is whenever somebody adds the fourth of anything.**)*

*(The twenty-eighth, in E0-15's implementation, one round after the twenty-seventh
below found the same file's header. The sweep outward from "the mock now holds an
email address" reached four records nobody was editing: `mock-lms/app/main.py`'s
own first line counting "six endpoints" and its §10 paragraph saying "this
platform holds none" of the personally identifiable information it forbids in
logs — the second being the expensive kind, since it is the sentence a reader
would trust when deciding whether a new log line is safe; `app/seed.py`'s "One
context has a title and one has none", which the ruling of 2026-08-17 had already
falsified; the `if context.title is not None` branch in `id_token_claims`, a
record in code for a case the seed can no longer produce; and `README.md`'s
paragraph telling a developer that one seeded section deliberately has no title.
This entry's rule about counts is also why the corrected first line names the two
halves of the surface instead of counting them — "six endpoints" had been wrong
since the moment a seventh route was declared, and a corrected number would be
wrong again at the eighth.)*

*(The twenty-seventh, in E0-15's tests. `tests/conftest.py`'s header describes what
each ticket added to the file and why, and adding the Advantage-service helpers to
`MockPlatform` made its E0-14 paragraph — "it discovers the mock platform rather than
naming its parts" — a description of a class that had grown a second subject. The
sweep is small and the rule is the same one: the header is the record a reader meets
before the code, and it goes stale by something being added to the file rather than
by anything in it being edited.)*

*(The twenty-sixth, and it is this entry's rule about counts caught by the change
that made one stale. `tests/integration/test_own_grant_follows_the_role_grain.py`
said in its docstring that the module asserts "five role grains", which the
assistant-dean tests make wrong; the number is deleted rather than corrected,
since one that has to be re-measured on every edit will be wrong again. Sweeping
outward from it found `tests/conftest.py`'s header saying "E0-11 adds two, at the
very bottom", wrong twice over once a third fixture lands beside
`supervision_graph` rather than at the bottom.)*

*(The twenty-fifth, one commit after the twenty-fourth below, in the artifact this
entry's own rule calls the highest risk. The commit that corrected ADR 0044 and
this file after the E0-11-01 ruling did not reach **the ADR index**, whose row for
0044 went on saying "the equal-rank half is in dispute" after the dispute had been
ruled on. The body of a record and its row in an index are two claims edited by
different reflexes, and only the body is ever re-read on purpose — so a sweep that
stops at the file it just corrected is not a sweep.)*

*(The twenty-fourth, and it set the radius of a one-line repair. Pinning three
tests to E0-10's revision changed one call and falsified everything around it:
six assertion messages that said "After `alembic downgrade -1` …", a section
comment claiming `downgrade -1` is the inverse of `upgrade head`, a fixture named
`views_at_head` that no longer looked at head, and two module docstrings. It also
caught a count — ADR 0044 recorded E0-11's edge module as "43 assertions" and
recorded the three E0-09 tests as "red on this branch", both true when written and
both false an hour later. The count was deleted rather than corrected: a number
that has to be re-measured on every edit is a record that will be wrong again.)*

*(The twenty-third: E0-11 added two rules to E0-09's supervision trigger, and this
entry is why the sweep went outward from the function rather than stopping at it.
ADR 0027's decision says the trigger enforces "the three cross-row rules", which
had become an undercount; its consequences said the Hypothesis properties "generate
cycles of every length up to eight", which the rank rule makes a space the schema no
longer admits; and the ADR index's row for ADR 0014 said the enforcing check was
"deferred to E0-11", which E0-11 declined to close. All three were records nobody
was editing. This entry's rule about counts is also why the corrected sentence in
ADR 0027 names the two new rules instead of counting the set — the count had already
gone stale once and would go stale again the next time a rule lands there.)*

*(The twenty-second: two records left over from the round that measured E0-10's
"the read and the audit write cannot come apart" false. A test's **name** is a
record — `test_a_rollback_discards_the_revealed_identity_and_its_audit_row_
together` was the removed claim, in the one place a reader meets it as a passing
green line — and this entry is why the rename did not stop at the name. The two
assertion messages inside it still quoted "a name cannot be obtained without
leaving a record", and the brief said only to leave the assertions alone; a
`grep` for the old name then found it recorded once more in
`docs/tickets/e0/.attempts/E0-10.md`'s mutation table, which is a record of what
was run and is reported rather than edited. The second: this entry's rule about
counts is why the corrected sentence in `test_application_role_privileges.py`
names the three doors instead of counting them, having just gone stale by being
a count of a set that grew to four.)*

*(The twenty-first: widening E0-10's downgrade revokes. ADR 0043's "the downgrade
revokes what the drop cannot" describes the definer's two grants and nothing
else, which is the record that made the gap look covered; it is proposed rather
than amended here, because the ADRs belong to another session this round. And
this entry's rule about counts in prose deleted one from the new comment before
it shipped — "grant eleven privileges" was wrong on the first count and would
have gone wrong again the day a grant moved, so the sentence names the two files
instead.)*

*(The twentieth, in the same correction one file over: withholding the Care
credential from `worker` and `beat` made ADR 0042's own consequence — "nothing
about the caller's own session can separate them" — false, and this entry is why
the sweep did not stop at the paragraph the brief named. It reached the ADR
index, `.env.example`, `README.md`'s "Seven variables have no default" and its
"a name cannot be obtained without leaving a record", and `config.py`'s "Both
URLs below", which had been a count of two over three fields since the Care URL
landed. Four of the six were records nobody had touched.)*

*(The nineteenth: correcting E0-10's "the read and the audit write cannot come
apart", which a reviewer measured false. This entry is why the sweep went outward
from the sentence rather than stopping at the three places the review named —
`grep` for the phrase found a fourth in `docs/tickets/e0/`, cleared the migration
docstring, and cleared the ADR index. It is also why the prose in the same diff
was re-read as if somebody else had written it, which found a second false claim
in `views_sql/queries.py` that no review had reported: `SectionRosterRow` said an
identity column in the view would be unreachable on this connection, when a view
is read with its owner's privileges and `pulse_app` would get it.)*

*(The eighteenth: E0-10's fixture change, `TEST_APP_USER` from `pulse_test_app`
to `pulse_app`. This entry is why the sweep went outward from the constant rather
than stopping at it — the epic README's "the fix is one line… until it lands, do
not read a green `application_engine` test as evidence about a grant" was written
about a state that had just stopped being true, and three test-module docstrings
described the marker convention this ticket had just widened.)*

**What happened.** Nine times, across three tickets. `.dockerignore`'s header
claimed it made secret leakage "impossible rather than unlikely" while `!backend`
re-included the whole subtree. The `db` health-check comment described
authentication that `pg_isready` never performs. A comment said the application
role held "nothing but CONNECT" when it kept Postgres's `PUBLIC` defaults. ADR
0007 claimed digest drift "is visible in a diff on both sides"; that was
retracted, and then the retraction itself went stale two commits later when the
guard landed. `.env.example` said both readers resolve `${...}` top-down, which
measurement disproved. The ADR index silently omitted three ADRs the same branch
shipped. Pull request #13's description spent a round describing a one-role
database stack that no longer existed.

A tenth, in E0-03, and it is the sharpest because of where it sat. The commit
that removed a false claim from `README.md` — that the worker ran the same code
as the API — put a new one in `docker-compose.override.yml` in the same diff: a
comment saying a stale worker makes `get()` hang, when the measurement in that
same commit's README said it raises `NotRegistered` for an added task and
silently returns the old answer for a changed one. It cited this file for it.

An eleventh and twelfth, in E0-12, in the same pull request, and both are the
variant where the record was **never** true rather than made false by a change.
ADR 0031 said a provider volunteering its own `model_id` "is refused rather than
trusted" because the contracts set `extra="forbid"`. `extra="forbid"` refuses
*undeclared* keys; `model_id` is a declared field, so a provider-supplied value
validates and round-trips, and which one survives depends on a merge order the
next ticket has not written yet. ADR 0030 said the hyphenated `self-harm` "stays
in the spec and in the prompt text" — but the enum's value is `self_harm` and
`"self-harm"` is refused, so a prompt author acting on that sentence would ship
a moderation prompt that fails on the one verdict §9.3 gates hardest. Neither
claim was ever run. Both were reasoned from what a setting is *for*, written down
in a record whose whole audience is the ticket that has to implement against it,
and found by an independent reviewer.

**Root cause.** Changing a mechanism and not asking what else in the repository
makes a claim about it. In the E0-12 pair, a second root cause with the same
consequence: reasoning about what a configuration option does instead of running
it. `extra="forbid"` and "forbid an extra value for a field" are one short step
apart in English and are different rules, and prose is where that step is
invisible — the code was correct in both cases and only the record was wrong. Three of these were *introduced by a fix for this same
class of defect* — the `.env.example` header rewritten to correct one false claim
acquired a different one, that `LOG_LEVEL` is settled by the spec, which the spec
never mentions; and the override comment above was written by a session that had
read this entry, bumped its counter, and used it to find four stale claims in
files it was not editing. The sweep is outward-facing. It asks what *other*
records say about the thing you changed, and a sentence you are writing right
now is not yet a record, so it is not in the set you sweep.

**Consequence.** A reader trusts the record over the code, because reading the
record is cheaper. That is what a record is for, so a false one is worse than
none. The stale pull request body was rated HIGH: it was the artifact the merge
decision rested on.

**Rule.** After changing a thing, ask what else in the repository asserts
something about that thing — comments, ADRs, tickets, indexes, READMEs, the pull
request body, test docstrings. Indexes are the highest risk: written once, never
re-read. "Re-read nearby prose" is not enough; it misses the record that was
never written and the one that drifted out from under you.

A thirteenth, in E0-15, and it is the sharpest instance of the count rule below
because it happened **inside the commit that bumped this entry's counter for
sweeping outward**. `README.md` and `mock-lms/app/seed.py` both said the seed
holds "twenty people and thirty-two enrollments". Twenty is right. Thirty-two was
never right: the three rosters hold twelve, seven and five, which is twenty-four,
and the number came from adding the same figure up in my head rather than out of
`seeded_platform()`. The table two lines below it in the README gave 12, 7 and 5
correctly, so the document contradicted itself on one screen and neither half was
re-read against the other. It reached three prose sites, a report to the
coordinator, and a commit message that cannot be corrected because history is not
rewritten here; the coordinator found it by counting the enrollments out of the
code. The repair deletes the number in all three places rather than correcting
it — the roster sizes are in the table, and a total is a number nobody will
recount the next time a section is added.

**And read the prose in your own diff as if someone else wrote it.** Every claim
you have just written is a claim nobody has checked, including the ones written
while correcting somebody else's. Where a sentence describes a behaviour, it has
to match what you measured — not what you expected to measure before you ran it.

This paragraph already existed when the E0-12 pair was written, and it is the
rule that would have caught both. It failed because "what you measured" reads as
being about experiments, and neither sentence felt like an experiment: one
described a library setting, the other a spelling. So, stated without the escape
hatch — **a claim about what a setting, a flag or a type refuses is a claim about
behaviour, and costs one line in a REPL to check.** If a record says something is
rejected, reject it before writing the sentence. This is entry 9 arriving through
prose rather than through a guard, and it is worth the two entries agreeing: the
expensive records are the ones a later ticket implements against, where the code
is right and only the sentence is wrong, so nothing goes red.

**A count in prose is a record with a scheduled expiry**, so prefer not writing
one. Three of these were counts — the ADR index that omitted three ADRs, "the
two tests below" in `tests/integration/test_term_calendar_schema.py`, left behind
by the commit that added a third and updated the identical count one docstring
over, and E0-15's thirty-two enrollments. The fix is to delete the number rather
than correct it: "the tests below" cannot go stale, and a sentence that needs the
number usually wants a different sentence.

**And a count is not only a stale-record risk — it is an unverified measurement.**
The E0-15 case was wrong on the day it was written, so no amount of re-reading it
later would have helped; what would have helped is the one thing nobody did,
which is to ask the program. A count of rows, files, tests or enrollments is a
number the code can produce in a line, and writing one from memory is entry 9
arriving through arithmetic: citing a total without executing the thing that
knows it. If a sentence must carry a number, get the number from the system and
say in the commit that you did.

---

## 2. Behaviour shipped with nothing asserting it

**Caught: 26**

*(The twenty-sixth, in E0-15's review round, and it is four survivors of one
mutation run rather than one defect. Nineteen mutations against the new AGS rules:
fifteen killed by the test named for what each broke, and **four survived, of which
exactly one is a gap**. That ratio is the reason to write this down — a survivor is a
result about the mutation until it has been read, and three of these four are a
second guard already refusing the same input. The score's positive-maximum check is
unreachable through the HTTP surface, because the disagreeing-maximum rule refuses
any maximum that is not the line item's and `create_line_item` already refuses a
non-positive line-item maximum. The naive-timestamp check is subsumed by the offset
check added beside it, and survives as the branch that produces the *true sentence*
for a bare date rather than as one that changes an answer. The results fold by
timestamp is subsumed by the 409, exactly as its own docstring predicted. All three
stay — each becomes load-bearing the moment its neighbour is relaxed, which
[ADR 0051](adr/0051-a-disagreeing-score-maximum-is-refused-rather-than-rescaled.md)
contemplates for one of them — and each now says in the code that a test cannot tell
it apart from the guard beside it. **The fourth is real:** widening the line-item
filter to `in (value, None)`, so that a filter hands back every line item *lacking*
the member, left all 28 tests then in this module green, because every line item the
suite creates carries a `tag` and a `resourceId`. It fails open, which is the
direction that hands a tool another placement's grades. **Now closed**, by the only
agent that could: `test_a_line_item_filter_does_not_return_an_item_that_lacks_the_member`
creates one line item carrying the value and one with the member absent — a body
`create_line_item` had to gain an `omitting=` keyword to send, since `tag=None` posts
a null and a null is not a missing key — and requires the first back and the second
not. It is the second guard on this branch that passes on first run against correct
code, and like the first it is evidence only because the mutation was re-applied
against it. What it still does not cover is the same widening on `resourceLinkId`,
which no test here can create a line item lacking; that went to the followup ticket
rather than being guessed at.)*

*(The twenty-fifth, in E0-15, and it is a gap found by trying to reintroduce a
defect rather than by any review. The mock platform's roster is served per
context, and the mutation that makes `membership_page` read **the first seeded
section's** members while the container goes on naming the context it was asked
for left all 61 tests then in the four mock modules green. Every launch user is
enrolled in every section, so `every_user_the_platform_will_launch_appears_in_
the_roster_of_its_context` is satisfied by the wrong roster; the paging
assertions are satisfied by any roster that divides; and
`the_membership_container_names_the_context_the_launch_came_from` compares the
container's declared context, which the mutation does not touch — its docstring
claimed it caught "a handler that ignores the context it was given", and it
catches the declaration rather than the membership. **Now closed**, which is the
half of this entry that usually does not happen on the same branch: the
implementer declared the gap and named the assertion it needed rather than
leaving it, the coordinator reproduced the mutation, and
`test_two_seeded_contexts_do_not_return_the_same_membership` is the test — two
seeded rosters, both non-empty, whose member sets differ, which kills it because
BIOL's twelve served for MATH's seven is a set the seed does not contain. The
misleading docstring was corrected in the same change, since a test that says it
catches something it does not is why nobody went looking. Two things are worth
keeping from it. The guard was declared by the only agent that could not write
it, which is what turned a convention into a test rather than into a line in a
pull request nobody re-reads. And the new test does not assert that a roster is
the *right* one — swapped rosters pass — because pinning the seed's own section
codes as expected values would make the test a second copy of the seed; the
docstring says so rather than implying more.)*

*(The twenty-fourth: E0-11's mirror rule. The rank rule refuses an edge that does
not climb, but a supervisor's *role* can be edited after its reporters are in
place — a `CHAIR` with a lead reporting to it, changed to `LEAD_FACULTY`, turns
every one of those stored edges into the inversion the rule exists to refuse,
without an edge being written. The implementer closed it in four lines and could
not test it, because the test wall put the assertion on the other side; ADR 0044
declared the gap in writing rather than letting it ship silent, and this entry is
why the declaration was not treated as sufficient. The test now exists with its
control — the same edit to a role that still outranks its reporters must succeed,
and the reporter must still report to it afterwards, which kills a mirror rule
implemented by clearing the children's edges.)*

*(The twenty-third, in E0-11, and it is the honest half of this entry rather than a
fix. Closing the mirror of the rank rule — an assignment may not change to a role
that something already reporting to it fails to be outranked by — was the right
call for entry 13's reasons, and **no test writes that `UPDATE`**. The implementer
is walled out of `tests/`, so it ships as a convention, and the response was to say
so in ADR 0044's consequences and in the pull request, and to name the test it
needs down to its control: a `CHAIR` with a `LEAD_FACULTY` reporting to it, updated
to `LEAD_FACULTY`, refused — with the same update on a chair nothing reports to,
which must succeed. A fix with nothing asserting it is a convention, and saying so
is not the same as fixing it.)*

*(The twenty-second: E0-11's chokepoint. Two guards in it would otherwise have
been conventions. `LMS_OWNED_TABLES` is a set of table *names*, so a misspelling
in it refuses a table that does not exist while leaving the real one writable and
reading as correct in review — hence the test that every name in it is a table on
`Base.metadata`. And an `ADMIN` assignment holds no rank in SPEC §2.1's chain, so
a rank rule that treats an unranked role as rank zero accepts every edge out of
one; nothing else in the suite writes such an edge, so the two parametrised
cases are what make the fail-closed direction a rule rather than an accident.)*

*(The twenty-first, found while closing the twentieth below and not by any
review of it. `tests/unit/test_config_settings.py` holds a settings object to
keeping its credentials out of seven serialisation surfaces and two
startup-error surfaces, and it drives all nine off `CREDENTIAL_BEARING_URLS` —
which named `DATABASE_URL` and `REDIS_URL`. `CARE_DATABASE_URL` carries a
password in exactly the same position and had been absent from that mapping
since it landed, so the masking on the one field that opens a route to a
student's name was asserted by nothing and could have been dropped with the
suite green. The widening comes with an interlock, because the mapping that
says what to configure and the mapping that says what to search for are two
copies of one fact and drifted apart once already.)*

*(The twentieth: E0-10's fix for the Care credential on `worker` and `beat`. The
blanking went in, and this entry is why the next step was to put it back rather
than to call it done — `CARE_DATABASE_URL` restored to the shared anchor renders
the real password into all three containers under `docker compose config`, and
all 195 unit tests stay green. The implementer is walled out of `tests/`, so the
gap is reported rather than closed, which is the honest half of this entry: a fix
with nothing asserting it is a convention, and saying so is not the same as
fixing it.)*

**What happened.** Four times. `__repr_args__` was added to keep credentials out
of `repr(settings)` — deleting it left the suite green. The `institution_timezone`
validator could be deleted whole with the suite green. "`DATABASE_URL` must never
point at the superuser" was prose, and repointing it passed all 50 tests and the
`docker` gate. The two Postgres image digests could be set to different values
with every gate green.

**Root cause.** Fixing the defect and stopping there. The fix is visible in the
diff, so it feels done; nothing makes the absence of a guard visible.

**Consequence.** The next person deletes it during an unrelated refactor and
every gate stays green. For the superuser case, the exact defect the pull request
existed to fix was reintroducible without any signal.

**Rule.** After fixing something, try to reintroduce it. If the suite stays
green, you have written a convention, not a guarantee. Prefer asserting the
*forbidden* state over the permitted one — it keeps working when a legitimate
second case arrives.

---

## 9. Citing a guard as a guarantee without executing it

**Caught: 17**

*(The seventeenth, in the test that migrates over a stored edge that does not
climb. The plant rests on E0-09's trigger accepting a row E0-11's refuses, so the
same `UPDATE` is attempted at the new revision *first* and required to be refused
before anything is downgraded. A plant that was legal at both revisions would
store the edge, pass every assertion after it, and look identical in the runner —
while proving nothing about a migration.)*

*(The sixteenth, inside the helper that plants a non-climbing edge for the cycle
tests. The plant needs the superuser bypass to store a row the rank rule refuses —
and a helper that goes straight to the bypass would keep working on a schema where
the rank rule had been deleted, planting nothing, with the cycle tests still green
and no longer testing what they claim. So it attempts the edge unbypassed first
and requires the refusal before bypassing anything: the guard it depends on is
executed, not assumed.)*

*(The fifteenth, in E0-11, twice, and one of the two changed the order the whole
ticket was built in. Before designing anything, the question "does a revision
landing on top of E0-10's break its downgrade tests?" was answered by writing a
throwaway revision whose entire content was `CREATE VIEW public.probe_view AS
SELECT 1` and running them: three go red on a guard that says so in its own
message. Reasoning about it would have reached the same answer and would have
reached it after the work rather than before, and the answer decided that the
ticket could not be finished green. The second: `authz_grants_v001.sql` claims
`pulse_app` is refused every base table these views read, so the claim was run —
`SET ROLE pulse_app` and a direct `SELECT` on all eleven, eleven "permission
denied" and three views permitted — before the sentence was written.)*

*(The fourteenth, one round after the thirteenth below and about the same guard.
The thirteenth ran both halves by hand; this is the test that keeps them run.
`test_the_downgrade_completes_when_a_role_it_revokes_from_is_absent` would have
been a single call to `alembic downgrade -1` with a role missing, and a downgrade
that completes proves nothing on its own — it completes on a cluster where the
role was never absent, which is what a rename that silently did not happen leaves
behind. So the bare `REVOKE ALL ON public.role_assignment FROM pulse_care` runs
first and has to fail with `undefined_object`, on the same database, seconds
earlier: the control is what turns "the downgrade worked" into "the guard is what
made it work".)*

*(The thirteenth, and the guard is the `IF EXISTS` around E0-10's downgrade
revokes. Its comment claims `REVOKE … FROM <role>` is an error rather than a
no-op when the role is absent, so both halves were run instead of cited: on a
throwaway cluster at head with all three roles dropped, the bare `REVOKE ALL ON
public.role_assignment FROM pulse_care` fails with `role "pulse_care" does not
exist`, and the guarded `alembic downgrade -1` completes and leaves the two
views, the function, `audit_log` and the enum type all gone rather than stopping
part-way.)*

*(The twelfth, and the guard is a YAML feature rather than a hook. The fix for
the Care credential turns on `<<:` merging a mapping *inside* an `environment:`
block, and on a service's own `environment:` replacing the anchor's wholesale
rather than adding to it. Both are claims about what Compose does, so both were
put through `docker compose config` before the comment explaining them was
written — which is also what showed that `DB_CARE_USER` and `DB_CARE_PASSWORD`
were still arriving in `worker` and `beat` through `env_file:` after the URL had
been blanked.)*

*(The eleventh, and the guard is one of this repository's own hooks. Asked to
make two changes inside `tests/`, the implementer had read
`.claude/hooks/deny-test-edits.sh` and could have reported "that is denied me"
from the source. It attempted the smallest of the two edits instead and was
blocked, which is what turned a claim about a hook into an observation — and it
also established that the `Edit` branch fires and not only the `Bash` one, which
reading the two `case` statements does not settle.)*

*(The tenth: E0-10's reveal function. A review found that nothing set its owner,
so a `SECURITY DEFINER` body was running as the migration superuser, and the
implementer's own file header cited four controls — static SQL, typed
parameters, a fixed `search_path`, qualified relations — as bounding it. This
entry is why the reach was measured instead of argued: a probe function created
the same way returned all 18 rows of `pg_authid` to a `pulse_care` caller that is
refused that table one statement later. The same probe, re-owned by the scoped
role the fix adds, is refused — and so is a body that reads one extra ordinary
table, which is the fail-closed property the change was made for.)*

**What happened.** Three times. A brief told the test author "a hook denies you
writes elsewhere" — no such hook existed; the hook matched `Read|Grep|Glob` and
denied *reads* of implementation source. Both hooks then turned out to fail open
when `jq` was absent, and one could be bypassed entirely with `cat` through
`Bash`, while their own comments called one "the wall."

The third is the sharpest, and it is a coordination mechanism rather than a hook.
A peer Claude session was asked to run `/clear` before a security review, so the
review would start with fresh eyes. `/clear` is a harness command: nothing a peer
sends can make it fire. The request also carried the line "I know you cannot
report back, because this message goes with it" — which **pre-explained the
silence the failure would produce**. Had the peer simply not replied, that would
have read as confirmation, and the review request would have gone into a context
still holding the previous review and the requester's framing of it. The peer
caught it and said so.

**Root cause.** Reading a mechanism's name and description instead of running it,
then reasoning about what its output would look like instead of observing the
output.

**Consequence.** Two rounds of work proceeded on a guarantee that was not
enforced. The third would have produced a review that looked independent and was
not — *worse than skipping the clear*, because the result would have been trusted
more.

**Rule.** Before citing a guard, execute it against the case you claim it stops
and the case you claim it allows. A guard that has never been run is a comment.
And never write a prediction that explains away the evidence of its own failure:
if you find yourself saying "there will be no confirmation, and that is expected",
you have removed the only signal that would have told you it did not work.

---

## 13. A hazard was written down and worked around in only one of the two places facing it

**Caught: 15**

*(The fifteenth, on both sides of E0-17, and both catches are about a second copy
that was nearly written. Writing the tests, the module needed to know how an
assignment's scope is spelled and which column carries the reporting edge —
questions `tests/conftest.py`'s `SupervisionGraph` already answers off
`Base.metadata` — so it requested that fixture **as a reader only**, over a
session belonging to a different database, rather than becoming the fourth copy of
the scope-shape logic. Implementing, the same entry caught the string
`"development"`: `app/db.py` compares against it before it lets the engine echo
SQL, and `scripts/seed.py` now compares against it before it will run at all. Two
places facing one convention. The copy is still there, because consolidating it
crosses a module boundary this ticket does not otherwise touch — but it is named
at the new site, in ADR 0063, and in the pull request, instead of being left for
somebody to find when the two disagree. **Naming a duplicate you decline to remove
is not the same as removing it, and it is much better than not noticing.**)*

*(The fourteenth, in E0-15's review round, and it is one repository disagreeing with
itself about what RFC 3339 means. ADR 0048 holds an enrollment window's `start` to an
offset spelled `+HH:MM` with the colon, and the seed suite refuses a compact `+0000`
by name. The review's HIGH then asked for a score `timestamp` to be parsed as RFC
3339, which `datetime.fromisoformat` does — except that it also accepts `+0000`, so
the score service would have taken exactly the spelling the roster service refuses.
No test covers it in either direction; the four the suite names are `"yesterday"`, a
bare date, a naive stamp and `03/02/2026`. It was found by running every new refusal
branch before writing the commit message rather than by reading the parser and
agreeing with it, which is entry 9's method arriving at this entry's defect. The
narrower lesson is about the tool rather than the rule: **a standard-library parser
named after a standard is not a check against that standard**, and the gap is exactly
where a second place facing the same hazard ends up disagreeing with the first.)*

*(The thirteenth, in E0-15's tests, and it decided where the helpers live. More than
one module asks what a `Link` header says, so the paging walk and the header parser
sit once in `tests/conftest.py` and reach the modules as fixtures — a copy in a test
module would be a copy that drifts from the walk it is meant to control, and a control
that has drifted from the thing it controls is worth less than none. The same entry
then had to be argued *against* one round later: reading a timestamp is asked in two
places and the two want different answers, because a score is recorded verbatim and an
enrollment window is not, so the roster tests compare instants and the AGS round trip
compares strings. One helper serves both and the fixture's docstring says why only one
caller uses it — the hazard this entry is about is two copies of a rule, not two
callers with different questions.)*

*(The twelfth, twice over the same hazard. E0-09's scope grain rule ties the
populated scope column to the role, so a test that edits a supervisor's role and
leaves its scope node alone is refused by the grain rule — a refusal that says
nothing about rank, and would have made the mirror-rule test pass for the wrong
reason. `change_role` therefore moves the scope with the role in one `UPDATE`.
The same rule is why the forest generator excludes the institution-scoped top
rank: two `VP_ACADEMICS` assignments in one transaction sit on the single
institution node, and a refusal there would read as a graph rule firing.)*

*(The eleventh, in E0-11, and the two places are four lines apart in one plpgsql
function. The new rule refuses a supervision edge that does not climb SPEC §2.1's
role rank, enforced on the row carrying the edge — and an edge is also made illegal
by changing the **parent's** role, which that check never runs for: an administrator
editing a chair into a lead faculty member in §6.3's People editor leaves whatever
reported to that chair reporting to a lead. E0-09's Care rule already closes exactly
that shape, in the same function, for the same reason — a row "may not become a CARE
assignment while other assignments report to it" — so closing it for one rule and
not the rule beside it would have been this entry with both halves visible on one
screen. It is narrow: it runs only on an `UPDATE` where the role changed, because no
row can have children at the instant it is inserted, which keeps ADR 0027's rule
that an ordinary insert takes no advisory lock.)*

*(The tenth, one layer up from the eighth below: the *rules* face the hazard in
more places than the Compose file does. Asked for a test that `worker` and
`beat` no longer hold `CARE_DATABASE_URL`, this entry is why the answer was not
one assertion over the base file. The two parts `.env` builds the URL from go in
the same rule, because a fix that blanked the URL alone reads as complete;
`docker-compose.override.yml` gets its own rule, because its shared anchor
reaches all three application services and re-supplying a variable there leaves
a base-file rule green; and the credential inside another key's value, one hop
through `.env`, gets a third — that spelling was two separate reviewer findings
against the superuser pair, and nothing about it is specific to which credential
is being carried.)*

*(The ninth: E0-10's `downgrade()` revoked the definer's grants on the two tables
that survive the revision and left `pulse_care`'s `SELECT` on `role_assignment`
one statement away, inside the block whose own comment states the hazard. This
entry is why the fix was not that one line: every grant the revision makes was
listed against the rule the block states, which turned up two more. `USAGE ON
SCHEMA public` for all three roles is this revision's alone and is now revoked;
`CONNECT ON DATABASE` is deliberately left, because `scripts/db-init` grants
`pulse_app` the same privilege before the migration runs and an ACL entry records
no history, so one `REVOKE` would take the other mechanism's grant with it.)*

*(The eighth: the brief for withholding the Care credential from `worker` and
`beat` named `CARE_DATABASE_URL`, and this entry is why the next question was
which other value opens the same door. `env_file: - .env` also hands those two
`DB_CARE_USER` and `DB_CARE_PASSWORD`, and `DATABASE_URL` supplies the host, the
port and the database name — so blanking the URL alone would have left the
credential in the container in three parts, and the fix would have read as
complete in review. All three are blanked now, on every application service.)*

*(The seventh: E0-10 widened `IDENTITY_NAME_FRAGMENTS`, and this entry is why the
author went looking for every copy rather than editing the one the dispute named.
There were three — `test_identity_column_marker.py`, `test_identity_schema.py`,
`test_role_assignment_graph.py` — and the comment on the first said there were
two, which is exactly how the third stays behind.)*

**What happened.** In E0-06's test module, `timestamp_columns` discovers timestamp
columns by reflecting from Postgres, and its docstring said why: "a column whose
type is a `TypeDecorator` — the natural place for the criterion 4 guard to live —
is not an instance of `DateTime` and would be missed." The row-seeding helper in
the same file dispatched `isinstance` against the **declared** column type and
got no such accommodation. When the implementation did what the docstring
predicted, both criterion-4 tests died inside the fixture on
`survey_window.closes_at`, before either reached an assertion. It took a dispute
round to settle ([`docs/disputes/E0-06-01.md`](disputes/E0-06-01.md)).

A second, in E0-09, three tickets later, and it cost another dispute round
([`docs/disputes/E0-09-01.md`](disputes/E0-09-01.md)). The E0-09 seeding helper
pins two column values so that a freely invented one cannot trip a rule from an
earlier ticket. The section code is drawn fresh per call, because E0-06 made
`(course, term, code)` unique; the course number one line above it was the
constant `"150"`, because SPEC §8 bands the number — and E0-05 also made
`(prefix, number)` unique. So the second course any test seeded under one prefix
was refused, and the three tests that need a sibling lead died inside the fixture
before any assertion ran. The two entries sit in the same dictionary, four lines
apart, and one of them already had the answer.

**Root cause.** Meeting a hazard at the call site where it first bit, instead of
asking which other call sites ask the same question. The write-up made it look
handled: the file named the hazard, in prose, one screen above the code that fell
to it. In the E0-09 case it was narrower still — the two values face *two* rules
each, a format rule and a uniqueness rule, and satisfying the format rule with a
constant is what violates the uniqueness one. Checking the entry against one rule
and stopping is the same shape as checking one call site and stopping.

**Consequence.** Two tests that could not pass against any implementation the
criterion admits, reported as a defect in the implementation. A round of the
loop, and — the expensive shape — an implementer under pressure to satisfy a
fixture rather than a criterion. Two of the four implementations tried in
response would have satisfied the helper *by removing the guard*, and one of them
is what the schema would have shipped.

**Rule.** When you work around a quirk of a type, a parser or an API, grep for
every place that asks the same question and route them through one helper, in the
same change. A docstring explaining the quirk is not a fix for the code that does
not call the fix. And when a test fails inside its own fixture, suspect the
fixture first — the message this one printed said exactly that, and was right.

**A fixture value has to satisfy every rule the column carries, not the one you
pinned it for.** Ask what makes the row *unique* as well as what makes it
well-formed, and prefer a generator over a literal wherever a second row of the
same kind is a shape any test might want. The `"150"` course number still sits in
the private copies of that dictionary in `test_identity_schema.py`,
`test_section_date_derivation.py` and `test_term_calendar_schema.py`; it is
latent there rather than active, because none of them seeds two courses under one
prefix yet.

---

## 16. A mutation harness reported kills it had not made

**Caught: 6**

*(The sixth, in E0-15, and this entry's last paragraph is the one that fired: "read
each mutation for whether it changes *meaning*". Seventeen mutations were run
against the mock platform with the controls below — baseline recorded first,
never `-x`, the replaced text asserted to match exactly once, the revert checked
by digest — and two came back SURVIVED. One was real (entry 2 above). The other
was not a result about the code at all: the mutation renamed the seeded section
`MATH-140-E1FF` to `MATH-140-R4WW` to remove the second start letter and the
`FF` modality, and a **third** section, `NURS-8100-Q2FF`, still supplied both. So
the diff was real, the file changed, the suite stayed green, and the mutation had
removed nothing. Renaming both of the other two sections killed it immediately,
by the two tests named for it. A harness that checks the text was replaced still
cannot check that the replacement removed the property — only reading the
mutation against the seed can, and the tell here was the same one this entry
already names: a result that disagrees with a test written specifically for that
property should be disbelieved before it is reported.)*

*(The fifth, and its subject is a mutation that lives in the database rather than
in a file. The cycle tests plant an inverted edge by reinstalling E0-09's trigger
function, writing the row, and restoring E0-11's — three statements, any of which
can silently not take effect, after which the test measures a database in a state
nobody intended. So the plant reads the edge back out before anything is believed,
asserts the session is off `replica` again, and restores the function in a
`finally` so a failing assertion does not leave E0-09's trigger installed for
whatever runs next.)*

*(The fourth, in E0-11, and it is this entry's last paragraph applied before
anything went wrong. The object under measurement is a trigger function body, which
lives in the database rather than in a file, and the thing being claimed is that
`downgrade()` puts E0-09's version back. So the baseline is read **from the revision
that installs it** — `014ccb3d0fe5`'s own dollar-quoted constant, parsed off disk —
and never from `pg_proc`, because a downgrade that reinstates whatever the database
happens to hold reinstates nothing and reports success. Control 0 is that E0-11's
`PREVIOUS_…` constant equals E0-09's shipped body byte for byte; control 1 is that
the two bodies differ at head. Without the second, "the bodies match after the
downgrade" is true of a revision that changed the function not at all.)*

*(The third: measuring what E0-10's `downgrade()` leaves behind. The thing being
changed lives in the database rather than in a file, so the baseline is the whole
ACL dump — `pg_class`, `pg_namespace`, `pg_database`, `pg_proc` — taken at head
before the migration was touched, and the fixed downgrade-and-upgrade round trip
is asserted against it by `diff` rather than by reading a `\dp` twice and
agreeing with it. The control that the old text really did leave the grant behind
is the pre-fix `DO` block taken out of `git show HEAD:`, checked to contain no
`pulse_care` before it was run, and then run: `pulse_care=r/pulse_admin` survives
it and the definer's two entries do not.)*

*(The second: the one mutation run against E0-10's Care-credential fix. This
entry is why it carried its own controls rather than a diff and a summary line —
the replacement asserted it matched exactly once before writing, the mutated
compose file was rendered through `docker compose config` to show the real
password reaching `worker` and `beat` before the suite was believed, and the
revert was checked by `sha256sum` against the value taken beforehand. Without the
render, "195 passed" under the mutation would have been indistinguishable from a
mutation that never took, and the conclusion drawn from it is the opposite one.)*

**What happened.** In E0-09, eight guards were mutated one at a time to check
that each was load-bearing — the cycle walk, the two Care rules, the role grain
rule, both entry doors. The harness ran the suite after each mutation and called
the mutation killed if the run came back non-zero. All eight reported killed.

Six of the eight reports were worthless and two were wrong.

Three tests in that module were **already failing**, for a reason unrelated to
the schema — a defect in the shared fixture, now `docs/disputes/E0-09-01.md`. The
harness ran with `-x`, so every run stopped at the first of those, and the
mutation under test was frequently never reached. Eight mutations, one identical
summary line: "1 failed, 10 passed".

Worse, two of the mutations mutated nothing. `AND CASE role ...` was "removed" by
replacing it with `AND true AND CASE role ...`, which leaves the `CASE` exactly
where it was. Those two would have reported SURVIVED against a correct harness
and been read as "this guard is untested", which is the opposite of the truth: on
a second run that deleted the whole `CASE`, fifteen tests went red, and loosening
any single arm turned its own test red.

A third mutation compared an enum column against a string that is not one of its
labels. Postgres raises on the comparison itself, so every row in the module
failed — a kill for a reason that had nothing to do with the guard.

**Root cause.** Measuring "did the run fail" instead of "did *this* fail", from a
baseline that was not green. A mutation harness is a test of the tests, and it
was written with none of the care the tests themselves get: no baseline, no
check that the mutation applied, no check that it applied *semantically*, and a
flag (`-x`) whose whole purpose is to stop before the interesting part.

**Consequence.** Caught before anything rested on it, because eight identical
summary lines is a suspicious shape. Had it not been, the pull request would have
claimed every guard verified by mutation, with three of the eight claims false
and two guards recorded as tested that no test touches. That is worse than not
mutating at all — the claim would have discouraged the next person from checking.

**Rule.** A mutation harness needs its own controls, and they are cheap. Record
the baseline failures first and report the failures a mutation **adds** to that
set, never the exit code. Never use `-x`. Assert the mutated text was found
before replacing it, and assert the revert restored the file byte for byte. And
read each mutation for whether it changes *meaning*: adding `AND true` in front
of a condition, or widening a value the code never reads, produces a diff and no
mutation. If several mutations report the same result, suspect the harness before
believing them.

**A mutation that lives in the database rather than in a file needs the same
care, and the file-shaped rule above does not cover it.** Later in E0-09 a second
harness replaced a trigger *function* per variant and read its baseline back out
of `pg_proc`. An earlier run had died before reinstalling the original, so the
baseline it read was already mutated and all three variants came back identical —
the same defect as above with no file involved. Read the baseline from the source
that installs the object, and assert it does **not** already contain the thing
you are about to add.

---

## 12. A stale build of the thing under test was reused, and the run looked clean

**Caught: 5**

*(The fifth, applied before anything went wrong rather than after. E0-15's
mutation harness edits `mock-lms/app/*.py` and reverts each edit inside seconds,
which is exactly the size-and-second window this entry's root cause describes —
and `tests/conftest.py` re-imports every `app.*` module per platform, so a stale
`.pyc` would be read seventeen times over. The harness therefore runs each variant
with `PYTHONDONTWRITEBYTECODE=1` and deletes every `__pycache__` under
`mock-lms/` first, which is this entry's rule and costs one line. Nothing was
observed going wrong, which is the point: with the caches left in place there
would have been nothing to observe.)*

**What happened.** In E0-05, checking that `alembic check` warns when a generated
column's expression drifts: edit `app/models/org.py` to change one band edge from
`499` to `498`, run the check, edit it back, run it again. The warning was there
both times. Ten minutes went into the model, the migration and the database
before `grep` showed the file on disk said `499` while the module Python imported
said `498`.

A second, in E0-12, one level up from bytecode. `backend/app/ai/prompts/` was
missing from the built wheel entirely — that defect is entry 18; this is what
happened while verifying its fix. The fix was a
`[tool.setuptools.package-data]` entry. Verifying it
meant removing the entry and rebuilding, which produced a wheel that still
contained the prompts: setuptools had reused the `build/` directory and the
egg-info left by the previous build, so the wheel described the *previous*
configuration. Deleting both first showed the real answer, an empty package.

**Root cause.** CPython validates a cached `__pycache__/*.pyc` against the source
file's size and mtime **truncated to the second**. Reverting a mutation of equal
length inside the same second leaves the cache valid, so the stale bytecode is
what runs. `499`→`498`→`499` is exactly that: same length, same second, and the
revert is invisible to the interpreter. The build tree is the same mechanism with
a longer memory and no invalidation rule worth the name: `build/` and
`*.egg-info` persist until something removes them, and no tool warns that it is
answering from them.

**Consequence.** The reverted run and the mutated run produce identical output,
which reads as "the mutation made no difference" — the conclusion that kills the
finding. In E0-05 it would have been "matching the server's own rendering does not
silence the warning, so do not bother", and the drift signal E0-20 now depends on
would have been dropped as not working. In E0-12 it would have been "the
`package-data` entry makes no difference", against a defect that empties the
prompt directory in every container the project ships.

**Rule.** When mutating and reverting between runs, destroy the caches in the
same command — `find <pkg> -name __pycache__ -type d -exec rm -rf {} +` or
`PYTHONDONTWRITEBYTECODE=1` for bytecode, `rm -rf build *.egg-info` before any
rebuild — and confirm the revert in the thing that ran rather than in the file:
print the value the module holds, list the archive. `grep` proves what is on
disk, which is not what ran. **In a test, prefer making the reuse impossible over
undoing it**: build in a copy that has never been built in, and there is no stale
artifact to remember to delete, no working tree to reach into, and nothing to get
wrong on the run where it matters. `tests/unit/test_prompt_directory_layout.py`
does this.

---

## 8. Prescribing a fix without probing it

**Caught: 4**

*(The fourth, and it is the second time this entry has caught a prescription
about the same tuple. A review of E0-10 found that the Care-session sweep in
`tests/unit/test_care_session_is_bound_to_the_care_service.py` cannot see
`Settings.care_database_url`, and prescribed widening `SESSION_FRAGMENTS`. Run
before being written down, over the 26 modules under `backend/app` and over the
reviewer's own future module, the widening does close that shape and does not
close a second one: `defined_here` subtracts **any** assigned name, so
`care_database_url = settings.care_database_url` — the exact idiom
`app/services/safety.py` itself uses — masks the attribute read and the sweep
reports nothing with the widened tuple in place. The prescription was necessary
and not sufficient, and reading it would not have shown that.)*

**What happened.** `hide_input_in_errors=True` was the obvious fix for a
credential appearing in a pydantic validation error. It cleans `str(exc)` and
leaves the credential in `errors()`.

A second, in E0-10's objection file, caught by this entry before it was filed.
The objection proposed a widened identity-column fragment set for the marker
sweep and wrote out the tuple: `"name", "email", "login", "picture", …`. Run
against the schema as it stands, `login` matches
`role_assignment.permits_web_login` — a boolean about which doors a role opens,
carrying no identity — so the proposed fix would have arrived as a new red test
in a module nobody had touched. `login_id` adds nothing on today's schema, which
was measured the same way. The prescription was one word wrong and read
perfectly.

**Root cause.** The fix was plausible and cheap, so it went into the brief
without being run. In the second case the tuple was written by thinking of
claims a roster sync carries, which is the right list to start from and is not
the same question as "what does this substring match in the schema I have".

**Consequence.** Would have shipped green against the one test that existed,
leaving the credential one `json.dumps` from any structured logger. The second
would have handed an arbitrator a fix that breaks a passing test, in the file
whose whole subject is a sweep that fires on the wrong things.

**Rule.** Before naming a mechanism in a brief, run it. If you are asking for a
property, say the property and let the implementer find the mechanism.

---

## 15. A property test's generator excluded the case its own docstring named

**Caught: 4**

*(The fourth, in E0-15's tests, and about a stated scope rather than a strategy —
this entry's last sentence is the one that applied: "a stated bound is a scope, and
an unstated one is a false claim of totality". Two tests carry a bound they cannot
remove, and stating both is what got one of them lifted. "No member is dropped" has
no total on the NRPS surface to check against, so it is checked against the users the
launch page will sign a launch for, which is a lower bound and says so. The mid-term
add was the second: with no enrollment-window field named anywhere, the test could
only look for a member value that parsed as a date and assert that the dates were not
all equal. Writing that bound down is what sent it to Todd as a question rather than
leaving it as a weak green test, and the ruling added the field — so the assertion is
now over a named `start`, within one section. **Both bounds have since moved, and
stating them is what moved them.** The enrollment field arrived from the first
ruling, and a reviewer then measured that "not all together" was satisfied by an
early add — so the assertion is now the shape of a late arrival: one member later
than every other, over a cohort of at least two. And the lower bound on "no member is
dropped" was measured too weak to keep alone; the claim now rests on the seed's own
numbering, with the lower bound kept beside it because the two fail for different
reasons. What is left is stated for the same reason as before: E0-15 asks that the
added member's `start` fall after its *section's* start date, and no section start
date is published on this surface at all — the section's calendar is derived
tool-side from its code and the term's start-letter map.)*

*(The third: the rank rule changed what both supervision generators can produce,
and the docstrings describing them were written against the old space. Cycles no
longer run to length eight but to six, because six ranks is the longest chain that
can exist; the forest no longer draws every role at every position but a strictly
lower role than its parent; and the top rank is excluded from the forest for the
grain reason in entry 13. Each of those is a narrowing that a reader would have
gone on believing was not there, so the "what these generators do not reach" lists
were rewritten against what the generators now actually draw rather than amended
at the edges.)*

**What happened.** E0-07's parsing suite carries a property for the definition of
done's "parsing is total: no exception type that escapes as a 500". Its docstring
listed the leaks it refuses and put `ValueError` out of `int()` first. It
generated `st.text(max_size=12)`.

The string that produces that `ValueError` is a start letter, more than four
thousand digits and a modality suffix: CPython caps integer-from-string
conversion at `sys.get_int_max_str_digits()`, 4300 by default, and
`parse_section_code("R" + "9" * 4301 + "WW")` raises `builtins.ValueError`
rather than the service's own error. Section codes come from the LMS roster feed,
so it is reachable input, and nothing shortens the value on the way in — a
`String(16)` column is not enforced in Python, and the derived columns are
`NOT NULL`, so the parse always runs before any row exists. The suite was green.
`/security-review` found it.

**Root cause.** The bound on the generator and the claim in the docstring were
written at different moments and never read against each other. Twelve characters
is a reasonable size for a section code, which is exactly why it looked like a
detail rather than a decision: it silently redefined "arbitrary text" as "text
short enough to be a section code", and the counterexample lives on the other
side of that line. A property test states its claim in the docstring and its
scope in the strategy, and only the second one runs.

It is entry 3's family — a test that passed for a reason unrelated to what it
asserted — but the mechanism is its own and worth naming separately: not an
absence that something else satisfied, and not a pattern that matched nothing. An
input space narrowed to where the assertion happens to hold.

**Consequence.** A guarantee about untrusted input, asserted by a test named for
it, over a space that could not contain the failure. Had it shipped, the first
malformed roster value of that shape would have been a 500 on the sync, with the
suite still reporting the case as covered. The repair was not simply a larger
`max_size` either: `st.text()` will not assemble that string by chance in three
hundred examples, so widening the bound would have put the counterexample inside
the declared space and left it just as unreachable — the same defect behind a
bigger number.

**Rule.** For every property, read the strategy against the docstring and ask
which named case the generator cannot produce. If the claim is about a boundary —
a limit in the standard library, a column width, a protocol maximum — generate
*around that boundary explicitly*, drawing from a band that straddles it, rather
than trusting a wide range to wander into it. Where a bound stays, say in the
docstring what it does not reach; a stated bound is a scope, and an unstated one
is a false claim of totality.

---

## 14. An enumeration was reported as an impossibility

**Caught: 3**

*(The third, in E0-11, and it decided how an objection was argued rather than
whether to file one. `docs/disputes/E0-11-01.md` claims that no rule can accept the
`CHAIR → CHAIR` edge E0-09's properties require and refuse the one E0-11's matrix
requires refused. The tempting way to support that is a list of implementations
tried, and this entry forbids it — so the objection says plainly "one
implementation, and then I stopped", and the argument is from the **construction of
the two rows**: both are built by the same `graph.node` helper, each with its own
new person and its own new department, so they are identical in every column any
rule could read. That is an argument from the mechanism, which is what this entry
asks for in place of a longer list, and it is checkable by a fresh arbitrator
without running anything.)*

**What happened.** In E0-06, the guard that refuses a naive datetime has to sit
on the column type, and the test module's fixture could not seed a decorated
type. Four implementations were tried and measured — a `TypeDecorator`, a
`DateTime` subclass, a hybrid of the two, and putting the guard in a service —
and the objection filed in `docs/disputes/E0-06-01.md` generalised from them:
"no implementation that satisfies criterion 4 can get past `invented_value`."

That is false. A type subclassing psycopg's `_PGTimeStamp` survives
`adapt_type`, so the `isinstance` check passes *and* the guard runs, and the
module passes 18 for 18 with no fixture change. The arbitrator found it by
reading `adapt_type` and running it — the same method the objection had used for
its own four options and abandoned at the moment it generalised.

**Root cause.** Treating a search that stopped as a search that finished. Each
of the four options was measured honestly; the sentence joining them was not
measured at all, because there was nothing to run — which is exactly why it went
in unchecked while the four claims around it were verified.

**Consequence.** A false universal in a durable record. The dispute file is read
by a fresh arbitrator with no context, and had it been believed, the ruling would
have rested on it. The correct position was available and narrower — the only
implementation the fixture admitted was built on a private, driver-specific class
— and it won the dispute on its own. The overclaim added nothing and cost the
record a correction.

**Rule.** Do not write "no X can" from a list of the X you tried. Say what you
tried and what it did, and let the boundary of the search be visible: "four
shapes, all measured, all fail" is honest and is usually enough to decide. If a
universal is genuinely load-bearing, it needs an argument from the mechanism —
here, from what `adapt_type` does — not a longer list.

---

## 17. An unqualified table name let the caller choose which table a guard read

**Caught: 1**

**What happened.** E0-09's supervision-edge trigger names `role_assignment`
unqualified in all three of its guard queries and in `'role_assignment'::regclass`,
which keys its advisory lock. Postgres searches the temporary schema **first** for
relation names, and does so whether or not `pg_temp` is in `search_path` — being
unlisted is what puts it first, not what skips it. So a caller who creates
`pg_temp.role_assignment` and then writes `public.role_assignment` gets all three
guards reading an empty temp table.

Reproduced on the pinned Postgres as a `NOSUPERUSER NOCREATEDB NOCREATEROLE` role
with no `CREATE` on `public`, because creating a temporary table needs only the
`TEMPORARY` privilege, which Postgres grants to `PUBLIC` by default. The
two-assignment cycle and the edge into a `CARE` assignment that the same role had
been refused seconds earlier both committed. The lock key moved too, so the
serialisation ADR 0027 rests on went with it.

The generic security review found it. Nothing could reach it — `pulse_app` holds
only `CONNECT` — but E0-10 is the ticket that grants the DML, and the bypass
would have arrived with those grants, silently and in a file nobody was editing.

**Root cause.** Writing SQL that runs *later* as though it ran *now*. Everything
else in the schema — check constraints, generated columns, foreign keys,
exclusion constraints — is resolved to OIDs when the DDL runs, and is immune;
measured, five for five, with shadows in place. A `plpgsql` body is the one place
in this repository where a name is resolved on every call, and it was written in
the same style as the rest.

**Consequence.** Caught before it could be reached, so the cost was one round.
Had it landed with E0-10's grants, all three of the rules the ticket exists to
enforce would have been bypassable by any authenticated application session, with
276 tests still green — no fixture creates a temporary table, so removing the
qualification is invisible to the suite today.

**Rule.** In any SQL that is parsed at call time — a `plpgsql` body, anything
built for `EXECUTE` — **schema-qualify every relation**, and
put `SET search_path = pg_catalog, public, pg_temp` on the function. Both, not
either: the qualification survives someone dropping the `SET`, and the `SET`
survives someone adding an unqualified reference. Name `pg_temp` **explicitly and
last** — a `search_path` that merely omits it, which is the usual advice, leaves
the hijack open, and that difference was measured rather than assumed. And verify
it the way it is exploited: stand up the shadow table as a non-superuser role and
watch the write be refused, rather than reading the SQL and agreeing with it.

**A view is not in that list, and the first version of this entry said it was.**
E0-10's test author queried the clause rather than editing it, having no shell to
settle it with; it was then measured on the deployed image, and the query is
worth keeping because the result is the opposite of what both this entry and
E0-10 assumed:

| | baseline | after `CREATE TEMP TABLE` shadowing the base table |
|---|---|---|
| `plpgsql` body | `from public` | **`from pg_temp`** |
| view | `from public` | `from public` |

`pg_depend` records the view against `public.<table>`: the oid is resolved at
`CREATE VIEW` and stored, so a view is early-bound like a constraint. The
practical consequence is not that qualification stops mattering — it is that
**a test which shadows a relation and asserts a view is unchanged cannot fail**,
which is entry 3's shape wearing this entry's clothes. Point that test at the
function.

*The general lesson, and the reason this is here rather than only in the ticket:
a rule that names a list of cases invites the list being extended by analogy. Two
of the three items here were measured; the third was added because it sounded
like the other two.*

---

## 6. Shell expansion inside a commit message

**Caught: 1**

**What happened.** `git commit -m "…$$POSTGRES_USER…"` in double quotes. The
shell expanded `$$` to its process id.

**Root cause.** Double quotes in the shell expand `$`. The message explained an
escaped-dollar parser, so it was exactly the text that could not survive it.

**Consequence.** Commit `77620c0` permanently reads `pg_isready -U
1793726POSTGRES_USER`, in the paragraph explaining the subtlest line in the
change. History is not force-pushed here, so it cannot be corrected.

**Rule.** Write commit messages through a quoted heredoc (`<<'EOF'`) or
`git commit -F`. Never `-m` with double quotes when the text contains `$`.

---

## 7. A verification window equal to the thing's own debounce

**Caught: 1**

**What happened.** Checking that a drifted database password made the container
report unhealthy, the poll ran for exactly 60 seconds. Docker needs `retries: 12`
× `interval: 5s` — 60 seconds of consecutive failures — before it flips.

**Root cause.** Choosing the window from the interval without adding the debounce.

**Consequence.** Nearly reported a working fix as broken. The health log already
said `password authentication failed`; only the status had not caught up.

**Rule.** When verifying a debounced state change, wait past the debounce and
read the underlying log as well as the summary status. A negative result inside
the debounce window is not a result.

---

## 18. A deliverable existed in the source tree and not in the built artifact

**Caught: 1**

**What happened.** E0-12 shipped `backend/app/ai/prompts/validity.v1.md`, the
prompt SPEC §7.4 requires a classification to name. Every gate was green: the
unit tests read the file off disk, ruff and mypy had nothing to say about a
`.md`, and it was committed and visible in the diff. Building the wheel the
Dockerfile installs — `pip wheel . --no-deps --no-build-isolation` — produced
`app/ai/__init__.py` and `app/ai/contracts.py` and no `prompts/` at all.
setuptools includes Python modules in a wheel; a data file inside a package
needs `[tool.setuptools.package-data]` and had none.

**Root cause.** Two different ideas of where the code lives. Every test in this
repository runs against the source tree, where the file is simply there. The
container installs a wheel into `/opt/venv` and has no source tree, so
"the file is in the repository" and "the file is in the running system" are
separate facts, and nothing connected them.

**Consequence.** As caught, none — the packaging entry went in with the ticket.
Unrecognised, E0-13's gateway would have loaded the prompt on a developer's
machine and raised on the first real launch in a container, with a green CI run
and a passing Compose health check behind it, because the health check answers
before any AI task is called. The same trap is waiting for four later epics: E2,
E4, E6 and E7 each add a prompt file here, and each will pass every gate.

**Rule.** When a ticket ships a non-Python file that code will read at runtime,
build the artifact and look inside it — `pip wheel . --no-deps
--no-build-isolation` then `unzip -l`. A green test suite proves the file is in
the repository and says nothing about whether it is in the image. This is entry
9 in a new place: the guard is the packaging configuration, and reading it is
not executing it.

For this directory the check is no longer manual:
`tests/unit/test_prompt_directory_layout.py` builds the wheel and asserts every
prompt in the source tree is inside it, so the four later epics get the failure
without knowing this entry exists. Asserting the `package-data` line instead
would not have worked — the glob first shipped here was `prompts/*.md`, which is
present, correct-looking, and matches neither a prompt in a subdirectory nor one
with another extension.

**And that fix was itself wrong, which is the part worth keeping.**
`prompts/*.md` was written to match ADR 0032's naming scheme exactly, and
matching the scheme was the error: a packaging glob that encodes a naming rule
enforces that rule by making the offending file absent from every container,
which is the worst available way to report a broken convention. It was widened to
`prompts/**/*` — the whole directory, any depth, any extension — so that
packaging decides only what reaches production, while the scheme stays enforced
by review and by the version test. Both narrow cases were measured by planting a
file and building rather than argued: `prompts/v2/moderation.md` and
`draft.v1.jinja` were each dropped in silence.

**Second rule, from that.** A fix to packaging, to an ignore rule, or to any
other glob-shaped configuration is not finished when the case in front of you
passes. Ask what the surrounding tests already *permit* — here, a sibling test
deliberately accepts a version held in a directory — and make the configuration
admit all of it. A glob narrower than the layouts the suite allows is a trap
primed for whoever first uses one of them, and it will look correct in review.

---

## 4. `git add` swept untracked files into a commit

**Caught: 0**

**What happened.** Twice on one branch. `.claude/agent-memory/` was committed as
its own `chore:` commit, dropped with a mixed reset, and then re-committed by the
next `git add` — the second time *inside* a commit whose subject said
documentation-only.

**Root cause.** The directory was untracked and not ignored, so every `git add`
re-collected it. Removing the commit recreated the cause.

**Consequence.** A commit whose message and diff disagree, which is the shape
that gets through review. Fixing it meant rewriting two commits.

**Rule.** Run `git show --stat` on each commit before reporting, and read it
against the subject line. If a fix leaves the cause in place, fix the cause —
here, a `.gitignore` entry.

---

## 5. A branch cut from the wrong base

**Caught: 0**

**What happened.** `e0/reviewer-hook-enforcement` was cut while standing on
`e0/backend-skeleton` instead of on the epic branch.

**Root cause.** Cutting a branch without checking out the base first, and not
checking the resulting diff.

**Consequence.** Pull request #12's diff was 35 files and ~3,960 additions rather
than the 5-file hook change its description claimed. Merging it merged E0-01
along with it, so pull request #11 merged as a no-op with no merge commit of its
own. The history now shows one merge where the record says two.

**Rule.** `git checkout <epic-branch>` before `git checkout -b`, then confirm
with `git merge-base --is-ancestor`. Before writing a pull request description,
run `gh pr diff <n> --name-only` and check it against what you think you changed.

---

## 10. Merged with the review loop one round short

**Caught: 0**

**What happened.** Pull request #13 went through three reviewer passes. The third
returned four findings; those were fixed, verified by mutation and by running the
stack, and merged. **No reviewer pass ran against the fixes.** The loop stopped
one round before the code that landed.

The independent `/security-review` did cover the final state and came back clean,
so the §14.2 gate was met. What was missing is narrower and easier to miss: the
last thing the reviewers saw was the code that provoked the findings, not the code
that answered them.

**Root cause.** Treating a fix round as the end of a review round. The findings
were closed, each fix was checked by the person who asked for it, and the checking
felt like the review. It is not — it is the same session that scoped the fix
confirming the fix matches the scope, which cannot notice a fix that is wrong in a
way nobody thought to scope.

**Consequence.** Four changes merged unreviewed, one of them a security fix to how
a database password reaches Postgres. All four have since held up, so the cost
this time was zero — which is exactly why the rule needs writing down rather than
remembering. The three previous rounds each turned up something in the *previous*
round's fixes, including two defects introduced by a fix for that same class of
defect. On the base rate of this branch, the fourth round would have found
something.

**Rule.** A fix round closes with a review pass, not with the fixer's own
verification, however thorough. If the fixes are trivial enough that a pass seems
wasteful, say so in the pull request and let the merge decision be made knowing
it — the judgment is fine, the silence is not. This applies to the coordinating
session too: verifying a fix yourself is evidence it does what you asked for, not
evidence it is right.

---

## 11. A failure in another process, invisible in the traceback that reported it

**Caught: 0**

**What happened.** E0-03's round-trip test timed out after thirty seconds
waiting for a task result. Its traceback pointed at `AsyncResult.get()` and said
nothing else: the worker had started, the broker was the one the test itself
started, and every assertion before the wait had passed. The worker runs in a
thread with `WORKER_LOGLEVEL=error`, so what actually happened was not printed.
Rerunning with `WORKER_LOGLEVEL=info` showed the task had *succeeded* and then
died storing its result — `pyproject.toml`'s `error::DeprecationWarning` turned
redis-py 8.1.0's notice about celery's `setex` call into an exception inside the
task trace, so the result was never written.

**Root cause.** A failure that happens in another thread or another container
does not appear in the traceback of the thing that was waiting for it. What the
waiter reports is the *absence* of an answer, which is the same shape whatever
the cause — a broker that is unreachable, a worker that is not running, and a
worker that ran perfectly and could not save its answer all read as a timeout.

**Consequence.** Half an hour, and a wrong first hypothesis: the obvious reading
of "the result never came back" is that the broker or the backend is
misconfigured. Raising the timeout, changing the result backend, or adding a
retry would each have looked reasonable and fixed nothing.

**Rule.** When something on the other side of a queue, a socket, or a container
boundary does not answer, get *its* log before theorizing about the channel. Turn
its log level up (`WORKER_LOGLEVEL`, `docker compose logs <service>`,
`docker inspect` for a health check's output) and reproduce outside the harness
if the harness is what is hiding it. A timeout is the absence of evidence, not
evidence.

---

## 20. A mutation the fixture undid, read as a test that could not fail

**Caught: 0**

**What happened.** In E0-14, checking by mutation that "issuer keys are generated
per run" is really asserted. The obvious mutation is to make the key survive a
restart, so it was moved to a module-level constant: `_CACHED_KEY =
IssuerKey.generate()` at import, with `create_app()` handing it out. All 27 tests
stayed green, which reads as the criterion being asserted by nothing.

It is not. `import_mock_lms_application` in `tests/conftest.py` drops every
`app.*` module from `sys.modules` and re-imports before each platform starts —
deliberately, and its docstring says why. So a module-level constant is
*regenerated per platform*, and the mutation had not made the key survive
anything. A second mutation that actually did — drawing the primes from a
module-level seeded PRNG, which restarts identically on every re-import — turned
two tests red immediately, and they were the right two.

**Root cause.** Mutating at the wrong layer. The property under test is "two
platform starts produce two keys", and the fixture's definition of a platform
start is a fresh import — so any mutation *above* the import boundary is undone
by the harness before the assertion runs. The mutation looked like it changed the
lifetime of the key and changed nothing at all.

**Consequence.** None this time, because the first result was disbelieved and a
second mutation was tried. Had it been believed, the conclusion available was
"this criterion is asserted by nothing" — followed by either a dispute against a
test that is in fact correct and sharp, or a quiet decision that the key lifetime
does not matter. It is a bad failure mode precisely because the evidence looks
clean: a green suite after a deliberate break is the strongest signal there is,
which is why a false one is expensive.

**Rule.** Before believing a mutation that did not fail, say which mechanism was
supposed to carry it to the assertion, and check the harness does not neutralise
it. `tests/conftest.py` has two fixtures that drop and restore `sys.modules` —
`import_app_module` and `import_mock_lms_application` — so **anything at module
scope is per-test state, not process state**, and a mutation that relies on
process lifetime has to go below the import: into a file, into the environment, or
into a deterministic source of randomness. A mutation that fails to fail is a
result about the mutation until you have shown otherwise.

---

## 19. A test held its expectation in a copy of the thing it was checking

**Caught: 2**

*(The second, in E0-15's tests, over SPEC §8's course-number bands. The mock's seeded
numbers are checked against a transcription of the table, because §8 states the rule
as a markdown table *plus* a sentence of prose about width — three digits only in
`000`–`799`, four only in `8000`–`9999` — and nothing in the repository holds that in
a form a test can read. So this entry's escape clause applies and its condition is
met: the comment says the constants are deliberately not derived and why, and a
control test walks every edge the table names, including `2150` from the `design/`
corpus the ticket warns about. Without the control the transcription is a second copy
of the rule with nobody comparing it to the first.)*

*(The first, in E0-11's tests, and it changed where three constants were read
from. The role ranks that decide which supervision edges are legal are written
out of SPEC §2.1's canonical chain rather than read back out of the trigger under
test — the only other copy of that order is inside the guard, so a test that
queried it would let both be renumbered together while staying green. The
LMS-owned table list is §2.1's ownership sentence rather than a copy of the
module's own `LMS_OWNED_TABLES`, which is the constant it exists to check. The
n-threshold default is §4's "default 5" rather than whatever `Settings` answers,
so a configuration defect and a resolver defect fail as two different
assertions. The `Purview` field list is transcribed from the ticket and says so,
because reading it off the dataclass would admit a seventh field silently — this
entry's rule for a value that genuinely has to be written into the test.)*

**What happened.** E0-12's moderation contract test asserted that the verdict
enum offers exactly the six values SPEC §7.4's table names. The six lived in a
tuple at the top of the test file, hand-copied from the spec, and the assertion
was a generic helper driven by whichever tuple it was handed. So the test did not
have to be defeated to lose a verdict: deleting `SELF_HARM` from the enum *and*
from the tuple left all 169 unit tests green. An eval-gate review found it by
doing exactly that.

The same file taught the edit. Every discovery constant in it carries a comment
saying it is this suite's choice and that a rename is "the one line that
changes", which is right for the constants that guess at class and field names
and wrong for the one that holds the spec's own words — and nothing distinguished
them.

**Root cause.** Two copies of one fact, both inside the blast radius of a single
change. A test that reads its expectation from a file the change also edits is
checking the code against itself. It is not entry 3 — the assertion ran, and
compared what it said it compared — and not entry 2, because the behaviour *was*
asserted. What failed is the independence of the expectation.

**Consequence.** As caught, none. Unrecognised, the merge of threat and self-harm
into one verdict would have passed CI with a diff that reads as tidying: one enum
member and one tuple entry. §6.2's Care queue distinguishes threat-of-harm from
self-harm risk, and §9.3 makes threat and self-harm recall the strictest floor in
the suite — a floor measured over a merged label is measuring something the spec
does not have, while reporting a number that looks like compliance.

**Rule.** When a test asserts that code matches a document, read the document.
`docs/SPEC.md` is parseable and is the authority; a constant beside the test is
neither. Where a value genuinely has to be written into the test — a count, a
pair of names that a second assertion exists to protect — say in the comment that
it is deliberately *not* derived and why, so the next reader can tell it apart
from a fixture that is free to move. And give a distinction that safety rests on
its own named test: a fold that fails a set comparison reads as a fixture needing
an update, while a fold that fails
`test_the_moderation_contract_keeps_threat_and_self_harm_as_two_distinct_verdicts`
says what was lost in the line the runner prints.

---

## 21. A merge was committed with its conflict markers still in the file

**Caught: 0**

**What happened.** `docs/MISTAKES.md` and `.dockerignore` were merged in commit
`7f5b300` (pull request #24) with six and one conflicted regions respectively,
and the markers were committed rather than resolved. The counter values had in
fact been reconciled correctly — every `<<<<<<< HEAD` side carried the right
sum of both branches' increments — so the work of resolving was done and only
the deleting was not. Pull request #27 then re-sorted the same `MISTAKES.md`
by catch count and did not see them, and pull request #24, pull request #27 and
the merge between them all passed every gate.

**Root cause.** Nothing in the build reads a Markdown file or a
`.dockerignore`. `ruff`, `mypy` and pytest sweep `.py`; the Docker gate reads
the Dockerfile and treats an unknown `.dockerignore` line as a pattern that
matches nothing, so a marker there is inert rather than loud. The two files this
repository most depends on being *read by a person* were the two with no
mechanical reader at all.

**Consequence.** None functional — the `.dockerignore` markers matched nothing
and both branches' patterns survived, so no file reached an image that should
not have. The cost was to the documents themselves: for two pull requests
`MISTAKES.md` carried each of five counters twice with different values, which
is the exact confusion the `Caught:` ordering rule exists to prevent, and one of
its entries appeared to end mid-paragraph.

**Rule.** `tests/unit/test_no_unresolved_merge_conflicts.py` sweeps every
tracked file for a marker at column zero. Beyond that: when a merge conflicts in
a file no gate reads, the resolution is not finished until you have looked at
the whole file rather than the region you edited. A conflict in a documentation
file is *more* likely to survive than one in code, not less, because nothing but
a reader will ever object — and the reader who arrives next is reading it for
its content and will take the markers for formatting they do not recognise.

---

## 22. A ticket's new rule made an earlier ticket's tests unrunnable, and the repair was on the other side of the test wall

**Caught: 1**

*(The first, in E0-15's tests, and it stopped a test being written rather than
repaired one. E0-15's scope says "every seeded course needs a title"; E0-14's scope
requires at least one seeded context carrying `id` alone, no title, so that E1's
ingestion meets the empty case in a test rather than in a deployment — and
`test_mock_lms_launch.py::test_a_seeded_context_carries_no_title` asserts exactly
that today. A test of E0-15's sentence would have turned that one red, on a seed
satisfying both tickets read separately. This entry's rule is about rows a new
write-time rule forbids; the same question asked of an existing *assertion* found
this one in a minute. It is reported as a disagreement between two tickets rather
than resolved in a test file, and the course-number half of the same sentence — which
collides with nothing — is asserted. **The ruling then went the way this entry's title
does not lead you to expect**: rather than the new ticket bending, Todd withdrew the
earlier requirement, `test_a_seeded_context_carries_no_title` was deleted in its own
commit, and E0-14's scope now records what the project gave up — the only fixture in
the repository that exercised a titleless course. Worth keeping, because the entry's
own thesis is that these collisions are repaired on the other side of the test wall,
and this one was repaired on the other side of the *product*: neither test was wrong,
and no amount of care inside `tests/` could have settled which requirement to keep.)*

**What happened.** Twice in E0-11, from two unrelated mechanisms, with the same
consequence: the ticket cannot be finished green and the implementer cannot fix
either, because both repairs are edits to `tests/`.

**The first is a rule that changed what is writable.** E0-11's first acceptance
criterion adds a role-rank rule to E0-09's supervision trigger: an edge is legal
only where `rank(child) < rank(parent)` over SPEC §2.1's chain. Its own module goes
from 19 passed and 24 failed to 43 passed. Three of E0-09's tests go red, and not
on their assertions — inside their setup. `test_a_six_assignment_cycle_is_refused`
and both properties in `test_supervision_graph_properties.py` build their graphs out
of `graph.node("CHAIR", reports_to=<another CHAIR>)` and require those writes to
**succeed**, while E0-11's `[chair-chair]` case writes the identical row — same
helper, own person, own department — and requires it **refused**. Two identical rows,
two opposite requirements. E0-09's module docstring even states the choice that
causes it: "one role and one scope grain per graph. Every generated node is a chair
on its own department, so that no uniqueness rule this ticket does not mention can
refuse a row and be read as the cycle guard firing." That was the right call for
E0-09 and it is what a later write-time rule collides with.

**The second is a test pinned to a relative revision.** Three tests in
`tests/integration/test_identity_grants.py` assert what E0-10's `downgrade()`
leaves behind, reaching it with `alembic downgrade -1`. `-1` is relative to head, so
the first revision to land on top of E0-10's — E0-11's — is the one `-1` names, and
all three fail. That is by design and the design is good: the shared guard
`only_the_identity_revision_was_undone` exists precisely so the change is loud
rather than a green test about a downgrade the file is not about, and its message
names the repair. The repair is "point this test at the identity revision
explicitly", inside `tests/`.

Measured, not predicted, and in the cheapest possible order: a throwaway revision
whose entire content was `CREATE VIEW public.probe_view AS SELECT 1` was written
*before* any of E0-11 was designed, and it turned the same three red. The content of
the revision is irrelevant — E0-10's two views are in both the at-head and
after-downgrade sets whenever `-1` names anything else — so no implementation of the
ticket avoids it.

**Root cause.** Two, and they are worth separating.

For the first: a new *write-time* rule was specified without asking which rows in
the existing suite it makes unwritable. A rule that changes what can be stored
changes every fixture that stores it, and a fixture is not a record that quietly
goes stale — it goes red, loudly, in a module nobody is editing. Both tickets'
authors looked at `test_role_assignment_graph.py`: E0-11's new module cites it twice
and correctly predicts which of its tests survive. Neither looked at the *generators*
in the property module, where the role is a constant chosen for an unrelated reason.

For the second: a test whose subject is one specific revision identified it by
position. Nothing declared the dependency, and it holds until the day it does not.

**Consequence.** Two dispute rounds on a ticket whose own 71 tests are green, and a
branch that cannot be merged under `CLAUDE.md`'s "never merge with red CI" until
somebody who may edit `tests/` acts. The expensive part is not the rounds — it is
that both failures look, in a runner, exactly like an implementer having broken
something. The three E0-09 failures print a `CheckViolation` from the new rule, and
the natural reading is that the rule is too strict rather than that two correct
specifications disagree. Six red tests, no defect in any of them, no defect in the
implementation.

**Rule.** **Before specifying a rule that changes what the database will store,
grep the existing suite for the rows it forbids.** `grep -rn 'reports_to='
tests/integration/` would have found all three in a minute, and the collision is a
sentence in the ticket rather than a dispute round. The sweep is not the outward
sweep over *records* that entry 1 asks for — this is over executable setup, and the
question is narrower and mechanical: which fixture writes a row this rule now
refuses?

**And when a guard's failure message prescribes a repair, ask who will meet it.**
`only_the_identity_revision_was_undone` is a well-written guard: it fires exactly
when intended and says what to do. It says it to an agent that is forbidden from
doing it. A guard whose remedy lies outside the reach of whoever it fires on is a
guard that produces an escalation rather than a fix, which is sometimes right — it
is right here — but it should be a chosen outcome and written down, not a surprise.
Where a test's subject is a particular revision, **name the revision**; `-1` and
`head` are convenient and neither is a subject.

---

## 23. A validation created the appearance of a behaviour

**Caught: 0**

**What happened.** In E0-15's mock platform, the AGS Result fold ignored
`gradingProgress` entirely. A score posted `NotReady` — the value that says the
grading process has not started — read back as a finished grade, and so did
`Failed` and `Pending`; measured across all five values by a reviewer.

That is an ordinary omission. What makes it worth an entry is the round in
between. The previous review pass found the field checked only for presence, and
the fix added a vocabulary check: `gradingProgress` had to be one of AGS 2.0's
five exact strings, refused loudly otherwise, with a control asserting all five
were accepted. Every one of those things is correct and none of them made the
grade right. After that fix the field was **validated on the way in, recorded
verbatim in the log, echoed in the readback, and consulted by nothing** — and it
now looked handled from every angle a reader has. The code had a named constant
for its vocabulary. The suite had a case per value. Anyone scanning either would
conclude the field was understood.

**Root cause.** Checking that a value is *well-formed* and never asking what it
is *for*. A vocabulary check is an assertion about the shape of an input; it says
nothing about whether anything downstream reads it. The two are easy to confuse
because a validated field looks like a used field: it appears in a constant, in
an error message, and in the name of something green.

It is entry 2's family — behaviour with nothing asserting it — and it is the
inverse of it, which is why it needs its own heading. There, a guard exists and
nothing covers it. Here, the coverage exists, it passes, and the field it
describes was never wired to anything. Entry 2's rule — try to reintroduce the
defect, and a green suite means you wrote a convention — cannot find this,
because there is nothing to reintroduce: removing the fold's use of the field is
a no-op, since it had none.

**Consequence.** Two rounds, and the second made the defect harder to see than
the first. Had it shipped, E3 would post a score at submit time — before SPEC
§3.3's classification has decided whether the response counts — and the gradebook
would show a participation grade computed from a week that has not been graded.
The student sees a number that will change, and nothing on the tool's side could
find it, because the tool is built against this mock.

**Rule.** **For every field a service validates, name the code that reads it.**
If the answer is "nothing", the field is decorative, and one of two things has to
happen: it gets acted on, or the validation says in writing that it is a shape
check and nothing more. The question to ask of an input is not only "is this
checked?" but "what changes when it changes?".

The cheap version is a search: grep the field name and count the sites that are
not the validator. One hit means the value goes in and stops there. And **a round
that adds validation to a field is the round to ask this**, because adding a
check to a field nothing consumes makes the gap less visible rather than more —
the next reader inherits a field that looks settled.
