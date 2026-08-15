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

**Caught: 8**

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

**Root cause.** Asserting an absence. Absence is satisfied by the thing being
broken in an unrelated way, by a fixture returning nothing, by a parser matching
nothing. In the third case, by the difference between what a sentence looks like
in a file and what it is as a string.

**Consequence. ** A green suite is read as coverage. The first case would have
been counted as proof the leak was fixed when it proved nothing about it.

**Rule.** Verify by mutation, not by reading: break the thing and watch the test
fail. Where a test can be satisfied by emptiness, assert non-emptiness first, and
say in the message why that guard is not ceremony. A pattern searched against a
file is a case of this and looks like none: run it against the text you claim it
catches *and* against the text you claim it allows, and give it a canary — a
string certainly present — so a search that has gone blind says so.

---

## 2. Behaviour shipped with nothing asserting it

**Caught: 7**

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

**Caught: 5**

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

**Root cause.** Changing a mechanism and not asking what else in the repository
makes a claim about it. Three of these were *introduced by a fix for this same
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

**A count in prose is a record with a scheduled expiry**, so prefer not writing
one. Two of these were counts — the ADR index that omitted three ADRs, and "the
two tests below" in `tests/integration/test_term_calendar_schema.py`, left behind
by the commit that added a third and updated the identical count one docstring
over. The fix is to delete the number rather than correct it: "the tests below"
cannot go stale, and a sentence that needs the number usually wants a different
sentence.

---

## 9. Citing a guard as a guarantee without executing it

**Caught: 4**

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

## 13. A hazard was written down and worked around in only one of the two places facing it

**Caught: 1**

**What happened.** In E0-06's test module, `timestamp_columns` discovers timestamp
columns by reflecting from Postgres, and its docstring said why: "a column whose
type is a `TypeDecorator` — the natural place for the criterion 4 guard to live —
is not an instance of `DateTime` and would be missed." The row-seeding helper in
the same file dispatched `isinstance` against the **declared** column type and
got no such accommodation. When the implementation did what the docstring
predicted, both criterion-4 tests died inside the fixture on
`survey_window.closes_at`, before either reached an assertion. It took a dispute
round to settle ([`docs/disputes/E0-06-01.md`](disputes/E0-06-01.md)).

**Root cause.** Meeting a hazard at the call site where it first bit, instead of
asking which other call sites ask the same question. The write-up made it look
handled: the file named the hazard, in prose, one screen above the code that fell
to it.

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

**Caught: 0**

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

## 12. A mutation was reverted on disk and not in the interpreter

**Caught: 0**

**What happened.** In E0-05, checking that `alembic check` warns when a generated
column's expression drifts: edit `app/models/org.py` to change one band edge from
`499` to `498`, run the check, edit it back, run it again. The warning was there
both times. Ten minutes went into the model, the migration and the database
before `grep` showed the file on disk said `499` while the module Python imported
said `498`.

**Root cause.** CPython validates a cached `__pycache__/*.pyc` against the source
file's size and mtime **truncated to the second**. Reverting a mutation of equal
length inside the same second leaves the cache valid, so the stale bytecode is
what runs. `499`→`498`→`499` is exactly that: same length, same second, and the
revert is invisible to the interpreter.

**Consequence.** The reverted run and the mutated run produce identical output,
which reads as "the mutation made no difference" — the conclusion that kills the
finding. Here it would have been "matching the server's own rendering does not
silence the warning, so do not bother", and the drift signal E0-20 now depends on
would have been dropped as not working.

**Rule.** When mutating and reverting source between runs, clear the caches in
the same command (`find <pkg> -name __pycache__ -type d -exec rm -rf {} +`, or
export `PYTHONDONTWRITEBYTECODE=1` for the whole loop). And confirm the revert in
the interpreter rather than in the file: print the value the module actually
holds. `grep` proves what is on disk, which is not what ran.
