# Mistakes

Things that have actually gone wrong in this repository, and the rule that
prevents each one happening again. Every entry is a real incident with a real
consequence — nothing here is hypothetical, and nothing is here because it
sounded like good advice.

**Read this whole file before you start work.** It is the rules only, and it is
ordered so the first entries are the ones that keep happening. Each links to what
actually happened — read that when the rule does not obviously apply to what you
are about to do, or when you think it is wrong.

## How to use it

**Consulting it.** Read the headings; each one is the shape of a real failure. If
one describes something you are about to do, read its rule and act on it. Open the
linked file when you need the incident behind the rule — the root cause, the
consequence, and the three most recent times it came up.

**Bumping the counter.** When an entry **stops you making the mistake**,
increment its `Caught:` number in the same change as the work it saved, and add
an instance paragraph to the linked file saying what it changed.

Before you bump, answer this: **what would have shipped if I had not read this
entry?** A prevention answers concretely — a test that would have passed against
the defect, a fix that would have been wrong in a way nobody would have noticed.
A detection cannot: if the honest answer is "a reviewer would have found it", the
entry did not stop you and the bump is not earned. Do not bump for reading an
entry, for recording something already found, or for an entry merely describing
what went wrong. The counter is the only signal for what belongs at the top, so
an entry that keeps saving people rises and an entry nobody bumps sinks — and
counting detections would sort by what this project trips over rather than by
what saves it, which is not the same list.

**Adding an entry.** When something goes wrong, add `docs/mistakes/NN-slug.md`
with what happened, the root cause, the consequence, and the rule; then add the
heading, the counter and the rule's first paragraph here. Cite the real artifact —
the commit, the file and line, the pull request. A rule with no incident behind it
is advice, and advice belongs in `CLAUDE.md`.

**Keeping it short.** A detail file holds the **three most recent** instances and
a count of the rest. The thirty-fifth instance of an entry teaches nothing the
third did, and this file reached 2,697 lines because every bump appended one — it
grew with bumps rather than with lessons, and every agent that read it before
starting paid for all of it. Older instances stay in git history and in the pull
requests they cite. Trim when a file passes three.

**Re-ordering.** Sort by `Caught:` descending when you notice it is wrong. Ties
break toward the more expensive consequence. **An entry keeps its number when it
moves**, so the headings below are not in numerical order and are not meant to
be. The number is the entry's name: code comments, commit messages and test
docstrings cite "entry 7", and renumbering would silently repoint every one of
them at a different incident. It is also the detail file's prefix, so the two
move together.

**One caution on the counters.** Two branches cut from the same commit that both
bump the same entry merge without conflicting and count once. If work has been
running in parallel, re-derive every counter from each branch's own diff against
the merge base and apply the totals, rather than trusting the merge.

---

## 3. A test passed for a reason unrelated to what it asserted

**Caught: 35** · [the incidents, the root cause, and the whole rule](mistakes/03-a-test-passed-for-a-reason-unrelated-to-what.md)

**Rule.** Verify by mutation, not by reading: break the thing and watch the test
fail. Where a test can be satisfied by emptiness, assert non-emptiness first, and
say in the message why that guard is not ceremony. A pattern searched against a
file is a case of this and looks like none: run it against the text you claim it
catches *and* against the text you claim it allows, and give it a canary — a
string certainly present — so a search that has gone blind says so.

## 1. A record went on asserting something the change had made false

**Caught: 31** · [the incidents, the root cause, and the whole rule](mistakes/01-a-record-went-on-asserting-something-the-change-had.md)

**Rule.** After changing a thing, ask what else in the repository asserts
something about that thing — comments, ADRs, tickets, indexes, READMEs, the pull
request body, test docstrings. Indexes are the highest risk: written once, never
re-read. "Re-read nearby prose" is not enough; it misses the record that was
never written and the one that drifted out from under you.

## 2. Behaviour shipped with nothing asserting it

**Caught: 29** · [the incidents, the root cause, and the whole rule](mistakes/02-behaviour-shipped-with-nothing-asserting-it.md)

**Rule.** After fixing something, try to reintroduce it. If the suite stays
green, you have written a convention, not a guarantee. Prefer asserting the
*forbidden* state over the permitted one — it keeps working when a legitimate
second case arrives.

## 13. A hazard was written down and worked around in only one of the two places facing it

**Caught: 19** · [the incidents, the root cause, and the whole rule](mistakes/13-a-hazard-was-written-down-and-worked-around-in.md)

**Rule.** When you work around a quirk of a type, a parser or an API, grep for
every place that asks the same question and route them through one helper, in the
same change. A docstring explaining the quirk is not a fix for the code that does
not call the fix. And when a test fails inside its own fixture, suspect the
fixture first — the message this one printed said exactly that, and was right.

## 9. Citing a guard as a guarantee without executing it

**Caught: 18** · [the incidents, the root cause, and the whole rule](mistakes/09-citing-a-guard-as-a-guarantee-without-executing-it.md)

**Rule.** Before citing a guard, execute it against the case you claim it stops
and the case you claim it allows. A guard that has never been run is a comment.
And never write a prediction that explains away the evidence of its own failure:
if you find yourself saying "there will be no confirmation, and that is expected",
you have removed the only signal that would have told you it did not work.

## 16. A mutation harness reported kills it had not made

**Caught: 6** · [the incidents, the root cause, and the whole rule](mistakes/16-a-mutation-harness-reported-kills-it-had-not-made.md)

**Rule.** A mutation harness needs its own controls, and they are cheap. Record
the baseline failures first and report the failures a mutation **adds** to that
set, never the exit code. Never use `-x`. Assert the mutated text was found
before replacing it, and assert the revert restored the file byte for byte. And
read each mutation for whether it changes *meaning*: adding `AND true` in front
of a condition, or widening a value the code never reads, produces a diff and no
mutation. If several mutations report the same result, suspect the harness before
believing them.

## 12. A stale build of the thing under test was reused, and the run looked clean

**Caught: 5** · [the incidents, the root cause, and the whole rule](mistakes/12-a-stale-build-of-the-thing-under-test-was.md)

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

## 8. Prescribing a fix without probing it

**Caught: 5** · [the incidents, the root cause, and the whole rule](mistakes/08-prescribing-a-fix-without-probing-it.md)

**Rule.** Before naming a mechanism in a brief, run it. If you are asking for a
property, say the property and let the implementer find the mechanism.

## 15. A property test's generator excluded the case its own docstring named

**Caught: 4** · [the incidents, the root cause, and the whole rule](mistakes/15-a-property-tests-generator-excluded-the-case-its-own.md)

**Rule.** For every property, read the strategy against the docstring and ask
which named case the generator cannot produce. If the claim is about a boundary —
a limit in the standard library, a column width, a protocol maximum — generate
*around that boundary explicitly*, drawing from a band that straddles it, rather
than trusting a wide range to wander into it. Where a bound stays, say in the
docstring what it does not reach; a stated bound is a scope, and an unstated one
is a false claim of totality.

## 14. An enumeration was reported as an impossibility

**Caught: 3** · [the incidents, the root cause, and the whole rule](mistakes/14-an-enumeration-was-reported-as-an-impossibility.md)

**Rule.** Do not write "no X can" from a list of the X you tried. Say what you
tried and what it did, and let the boundary of the search be visible: "four
shapes, all measured, all fail" is honest and is usually enough to decide. If a
universal is genuinely load-bearing, it needs an argument from the mechanism —
here, from what `adapt_type` does — not a longer list.

## 19. A test held its expectation in a copy of the thing it was checking

**Caught: 3** · [the incidents, the root cause, and the whole rule](mistakes/19-a-test-held-its-expectation-in-a-copy-of.md)

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

## 17. An unqualified table name let the caller choose which table a guard read

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/17-an-unqualified-table-name-let-the-caller-choose-which.md)

**Rule.** In any SQL that is parsed at call time — a `plpgsql` body, anything
built for `EXECUTE` — **schema-qualify every relation**, and
put `SET search_path = pg_catalog, public, pg_temp` on the function. Both, not
either: the qualification survives someone dropping the `SET`, and the `SET`
survives someone adding an unqualified reference. Name `pg_temp` **explicitly and
last** — a `search_path` that merely omits it, which is the usual advice, leaves
the hijack open, and that difference was measured rather than assumed. And verify
it the way it is exploited: stand up the shadow table as a non-superuser role and
watch the write be refused, rather than reading the SQL and agreeing with it.

## 6. Shell expansion inside a commit message

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/06-shell-expansion-inside-a-commit-message.md)

**Rule.** Write commit messages through a quoted heredoc (`<<'EOF'`) or
`git commit -F`. Never `-m` with double quotes when the text contains `$`.

## 7. A verification window equal to the thing's own debounce

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/07-a-verification-window-equal-to-the-things-own-debounce.md)

**Rule.** When verifying a debounced state change, wait past the debounce and
read the underlying log as well as the summary status. A negative result inside
the debounce window is not a result.

## 18. A deliverable existed in the source tree and not in the built artifact

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/18-a-deliverable-existed-in-the-source-tree-and-not.md)

**Rule.** When a ticket ships a non-Python file that code will read at runtime,
build the artifact and look inside it — `pip wheel . --no-deps
--no-build-isolation` then `unzip -l`. A green test suite proves the file is in
the repository and says nothing about whether it is in the image. This is entry
9 in a new place: the guard is the packaging configuration, and reading it is
not executing it.

## 22. A ticket's new rule made an earlier ticket's tests unrunnable, and the repair was on the other side of the test wall

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/22-a-tickets-new-rule-made-an-earlier-tickets-tests.md)

**Rule.** **Before specifying a rule that changes what the database will store,
grep the existing suite for the rows it forbids.** `grep -rn 'reports_to='
tests/integration/` would have found all three in a minute, and the collision is a
sentence in the ticket rather than a dispute round. The sweep is not the outward
sweep over *records* that entry 1 asks for — this is over executable setup, and the
question is narrower and mechanical: which fixture writes a row this rule now
refuses?

## 23. A validation created the appearance of a behaviour

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/23-a-validation-created-the-appearance-of-a-behaviour.md)

**Rule.** **For every field a service validates, name the code that reads it.**
If the answer is "nothing", the field is decorative, and one of two things has to
happen: it gets acted on, or the validation says in writing that it is a shape
check and nothing more. The question to ask of an input is not only "is this
checked?" but "what changes when it changes?".

## 29. A value was repaired before the check that should have refused it

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/29-a-value-was-repaired-before-the-check-that-should.md)

**Rule.** **Validate what arrived, and only reject — never repair.** For every
check, ask what happened to the value between the socket and the check: a guard
whose input passed through `.strip()`, `.lower()`, `.replace()`, a
`urlsplit`-and-rebuild or a type coercion upstream is a guard checking a value
that never existed on the wire.

## 4. `git add` swept untracked files into a commit

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/04-git-add-swept-untracked-files-into-a-commit.md)

**Rule.** Run `git show --stat` on each commit before reporting, and read it
against the subject line. If a fix leaves the cause in place, fix the cause —
here, a `.gitignore` entry.

## 5. A branch cut from the wrong base

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/05-a-branch-cut-from-the-wrong-base.md)

**Rule.** `git checkout <epic-branch>` before `git checkout -b`, then confirm
with `git merge-base --is-ancestor`. Before writing a pull request description,
run `gh pr diff <n> --name-only` and check it against what you think you changed.

## 10. Merged with the review loop one round short

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/10-merged-with-the-review-loop-one-round-short.md)

**Rule.** A fix round closes with a review pass, not with the fixer's own
verification, however thorough. If the fixes are trivial enough that a pass seems
wasteful, say so in the pull request and let the merge decision be made knowing
it — the judgment is fine, the silence is not. This applies to the coordinating
session too: verifying a fix yourself is evidence it does what you asked for, not
evidence it is right.

## 11. A failure in another process, invisible in the traceback that reported it

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/11-a-failure-in-another-process-invisible-in-the-traceback.md)

**Rule.** When something on the other side of a queue, a socket, or a container
boundary does not answer, get *its* log before theorizing about the channel. Turn
its log level up (`WORKER_LOGLEVEL`, `docker compose logs <service>`,
`docker inspect` for a health check's output) and reproduce outside the harness
if the harness is what is hiding it. A timeout is the absence of evidence, not
evidence.

## 20. A mutation the fixture undid, read as a test that could not fail

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/20-a-mutation-the-fixture-undid-read-as-a-test.md)

**Rule.** Before believing a mutation that did not fail, say which mechanism was
supposed to carry it to the assertion, and check the harness does not neutralise
it. `tests/conftest.py` has two fixtures that drop and restore `sys.modules` —
`import_app_module` and `import_mock_lms_application` — so **anything at module
scope is per-test state, not process state**, and a mutation that relies on
process lifetime has to go below the import: into a file, into the environment, or
into a deterministic source of randomness. A mutation that fails to fail is a
result about the mutation until you have shown otherwise.

## 21. A merge was committed with its conflict markers still in the file

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/21-a-merge-was-committed-with-its-conflict-markers-still.md)

**Rule.** `tests/unit/test_no_unresolved_merge_conflicts.py` sweeps every
tracked file for a marker at column zero. Beyond that: when a merge conflicts in
a file no gate reads, the resolution is not finished until you have looked at
the whole file rather than the region you edited. A conflict in a documentation
file is *more* likely to survive than one in code, not less, because nothing but
a reader will ever object — and the reader who arrives next is reading it for
its content and will take the markers for formatting they do not recognise.

## 30. A fixture supplied the value under test, so neither the green nor the red meant anything

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/30-a-fixture-supplied-the-value-under-test-so-neither.md)

**Rule.** **Before treating a suite result as evidence about how a value is
resolved, find out what the fixture supplies.** If the fixture provides the value
under test, both colours are uninformative and the honest instrument is a hand
measurement of the real path, recorded where somebody can re-run it.

## 31. "Running it twice is safe" was tested only against a database the loader itself had filled

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/31-running-it-twice-is-safe-was-tested-only-against.md)

**Rule.** **Test an idempotent loader against rows it did not write.** Before a
second-run test means anything, put a foreign row in its way — one that shares
the natural key the loader matches on — and assert what the loader does with it.
The interesting answer is usually "refuse", and a loader that has never been
shown a foreign row has not been asked the question.

## 27. A guard that reads a command as text refused a command that was only reading

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/27-a-guard-that-reads-a-command-as-text-refused.md)

**Rule.** When a hook refuses a command, work out which part of the *command* it
matched before concluding anything about what you may know. Read files with the
`Read` tool, which the hook does not gate; keep test paths out of `Bash` command
text by redirecting to a file whose name does not carry the word, or by writing
the script with `Write` and running it by name. And when a guard's refusal seems
to forbid *reading*, say so and check, rather than proceeding on a narrower
picture of the ticket than the loop intended you to have.

## 28. A driver that could only speak correctly made the invalid half of every guard unreachable

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/28-a-driver-that-could-only-speak-correctly-made-the.md)

**Rule.** **When a fixture speaks a protocol, ask what it cannot say.** Enumerate
the values the driver builds for the system under test, and for each one ask
whether any test could send a malformed version — not a *wrong* version, which
drivers usually do allow, but one that violates the shape. A refusal criterion is
only asserted over the inputs the driver can express, so where it cannot express
the malformed shape, either give it a way to send one or write the constant out
by hand in the test module and say why.

## 24. A test asserted a property no implementation could satisfy

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/24-a-test-asserted-a-property-no-implementation-could-satisfy.md)

**Ruled on**, outcome 1 — the test is wrong — and the needle is now random
throughout (`ae7518d`). The ruling found one thing this entry did not, and it is
the expensive half: the *same* needle is used in
`tests/integration/test_ai_gateway_validity_roundtrip.py` as a **positive**
detector, to prove the key was really sent before anything is asserted about it
not leaking. There a collision does not go red at all — it satisfies the
non-vacuity guard against a request that never carried the key, and every leak
assertion beneath it then reports a guarantee that was never tested. A search term
shared between a must-find rule and a must-not-find rule fails in both directions
at once, and only one of those directions announces itself.

## 25. Two lockfiles resolved the same package to two versions

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/25-two-lockfiles-resolved-the-same-package-to-two-versions.md)

**Rule.** **After `make lock`, check that the two lockfiles agree on every package
they share.** One command, and it costs nothing:

## 26. A fallback path swallowed the defect that triggered it

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/26-a-fallback-path-swallowed-the-defect-that-triggered-it.md)

**Rule.** **A fail-open handler must catch the narrowest failure the spec
sanctions, and everything else must be loud.** Ask of every `except` on a
fallback path: what is the *widest* thing this class can carry, and is a bug in
my own code one of them? If it is, split the class until it is not.

## 33. A class-tree split put a case on the wrong side, and the docstring said otherwise

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/33-a-class-tree-split-put-a-case-on-the.md)

**Rule.** **When a check expresses a decision about the world, do not encode it as
a check against a library's class tree.** Write down the question first — here,
"did the request reach an endpoint that could have answered?" — enumerate the
conditions on each side of it, and map each condition to a class explicitly. The
repair was exactly that: four classes of the project's own, one per answer, with
the library's types as inputs to the mapping rather than as the mapping.

## 34. A pipeline discarded a non-zero exit and printed a line that read as success

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/34-a-pipeline-discarded-a-non-zero-exit-and-printed.md)

**Rule.** Redirect and capture the exit status; never pipe a gate.
