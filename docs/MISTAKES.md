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

**Caught: 20**

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

**Root cause.** Asserting an absence. Absence is satisfied by the thing being
broken in an unrelated way, by a fixture returning nothing, by a parser matching
nothing. In the third case, by the difference between what a sentence looks like
in a file and what it is as a string. In the fifth, by a second mechanism in the
same schema that refuses the same row for its own reasons — "the database said
no" does not say which part of it said so.

**Consequence. ** A green suite is read as coverage. The first case would have
been counted as proof the leak was fixed when it proved nothing about it. The
fifth would have let a later ticket delete a constraint as redundant, with the
rule it states surviving only as a side effect of how overlap happens to be
enforced today.

**Rule.** Verify by mutation, not by reading: break the thing and watch the test
fail. Where a test can be satisfied by emptiness, assert non-emptiness first, and
say in the message why that guard is not ceremony. A pattern searched against a
file is a case of this and looks like none: run it against the text you claim it
catches *and* against the text you claim it allows, and give it a canary — a
string certainly present — so a search that has gone blind says so.

**Where two rules can refuse the same row, a behavioural test cannot tell you
which one did.** Mutation is what exposes it — delete the constraint and see
whether anything goes red — and the fix is to assert the rule is *stated*, out of
what the catalog reports, as well as that the row is refused. Both, not either:
the catalog test cannot see whether the rule works and the behavioural test
cannot see whether it exists.

---

## 2. Behaviour shipped with nothing asserting it

**Caught: 18**

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

## 1. A record went on asserting something the change had made false

**Caught: 16**

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
one. Two of these were counts — the ADR index that omitted three ADRs, and "the
two tests below" in `tests/integration/test_term_calendar_schema.py`, left behind
by the commit that added a third and updated the identical count one docstring
over. The fix is to delete the number rather than correct it: "the tests below"
cannot go stale, and a sentence that needs the number usually wants a different
sentence.

---

## 9. Citing a guard as a guarantee without executing it

**Caught: 9**

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

**Caught: 5**

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

## 12. A stale build of the thing under test was reused, and the run looked clean

**Caught: 3**

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

**Caught: 2**

**What happened.** `hide_input_in_errors=True` was the obvious fix for a
credential appearing in a pydantic validation error. It cleans `str(exc)` and
leaves the credential in `errors()`.

**Root cause.** The fix was plausible and cheap, so it went into the brief
without being run.

**Consequence.** Would have shipped green against the one test that existed,
leaving the credential one `json.dumps` from any structured logger.

**Rule.** Before naming a mechanism in a brief, run it. If you are asking for a
property, say the property and let the implementer find the mechanism.

---

## 15. A property test's generator excluded the case its own docstring named

**Caught: 2**

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

## 14. An enumeration was reported as an impossibility

**Caught: 1**

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

## 16. A mutation harness reported kills it had not made

**Caught: 1**

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

## 18. A deliverable existed in the source tree and not in the built artifact

**Caught: 0**

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

## 19. A test held its expectation in a copy of the thing it was checking

**Caught: 0**

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
