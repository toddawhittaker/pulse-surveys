# Mistakes

Things that have actually gone wrong in this repository, and the rule that
prevents each one happening again. Every entry is a real incident with a real
consequence — nothing here is hypothetical, and nothing is here because it
sounded like good advice.

**Read this whole file before you start work.** Every heading below is the shape
of a real failure, and the file is ordered so the first ones are the ones that
keep happening. Scan the headings; when one describes something you are about to
do, that is the entry to act on.

The first few carry their rule here, because five entries account for four fifths
of every catch ever recorded in this file and they are worth knowing by heart. The
rest carry a link — the rule, the incident and the root cause are one click away,
and they are read on the occasion rather than every time.

## How to use it

**Consulting it.** Read the headings; each one is the shape of a real failure. If
one describes something you are about to do, act on its rule — which is either
here or one click away. Open the linked file when you need the incident behind the
rule: the root cause, the consequence, and the three most recent times it came up.

**A `Caught: 0` does not mean an entry is dead.** Bumping is easy to forget, and
this file has at least one entry that demonstrably stopped a real loss and was
never bumped for it. The counter under-reports, so it decides what is quoted in
full here — never what is worth keeping.

**The top five counters are frozen, as of 2026-08-23.** Entries 3, 1, 2, 13 and
9 — the five that carry their rule in this file — stop being bumped and stop
taking new instance paragraphs. Their numbers stay exactly where they are, dated
frozen 2026-08-23, as history. Two things had happened: the ranking stopped
moving, because those five account for four fifths of every catch recorded here
and the tier has been the same five entries for long enough to call it settled;
and the bookkeeping had grown into a commit per batch, spent to turn a 45 into a
46 that nobody would read differently. Reading these five and acting on their
rules is unchanged. Only the counting stops.

**Bumping the counter, below the top five.** When an entry outside the frozen
five **stops you making the mistake**, increment its `Caught:` number in the
same change as the work it saved, and add an instance paragraph to the linked
file saying what it changed. The tail keeps the counter because a tail entry
that starts saving people repeatedly is exactly the thing worth knowing, and its
count is what detects it.

Before you bump, answer this: **what would have shipped if I had not read this
entry?** A prevention answers concretely — a test that would have passed against
the defect, a fix that would have been wrong in a way nobody would have noticed.
A detection cannot: if the honest answer is "a reviewer would have found it", the
entry did not stop you and the bump is not earned. Do not bump for reading an
entry, for recording something already found, or for an entry merely describing
what went wrong. A tail entry's counter is the only signal that it is doing the
work the top five do, so an entry that keeps saving people rises and an entry
nobody bumps sinks — and counting detections would sort by what this project
trips over rather than by what saves it, which is not the same list.

**A counter retires when its rule becomes mechanically enforced.** Once a test,
a sweep or a CI gate enforces an entry's rule, the gate is the prevention and
the counter stops, and the entry stays here as the record of why the gate
exists. That is the graduation path for every entry in this file, frozen or
tail — a rule people have to remember becomes a rule they cannot break, and a
tally of near misses has nothing left to measure. **Retire a counter only on an
executed gate, never on a judgement that one covers the entry.** The retirement
note names the gate by path and test or job name, and names the case it was run
against: the defect this entry describes, planted, and the gate seen failing on
it. A gate nobody has watched fail against this entry's own defect is entry 9's
mistake wearing a green tick, and it does not retire anything.

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
requests they cite. Trim when a file passes three. This applies to the files
still taking instances; a frozen entry's file keeps the three it has and gains
no more.

**Re-ordering, and the tier.** The top five is settled: entries 3, 1, 2, 13 and
9 carry their rule in this file and keep both their rule and their place. Below
them, sort by `Caught:` descending when you notice it is wrong. A tail entry
whose count climbs past the lowest frozen counter has earned its rule here —
add it, and leave the frozen five where they are, so the tier grows rather than
rotating.

Ties in that tail sort break toward the more expensive consequence. **An entry
keeps its number when it moves**, so the headings below are not in numerical
order and are not meant to be. The number is the entry's name: code comments,
commit messages and test docstrings cite "entry 7", and renumbering would
silently repoint every one of them at a different incident. It is also the
detail file's prefix, so the two move together.

**There is no entry 32, and no entry is missing.** E0-17 reserved the number and
did not use it, and the restructure of 2026-08-18 left the gap rather than
back-filling it, because renumbering is the one thing this file forbids: the
number is the entry's name, and citations in ADRs, test docstrings and commit
messages point at it. So a gap here means a reservation that went unused, never a
deleted entry — and 32 is not free for the next entry to take. The same note in
`docs/adr/README.md` explains the identical gap at 0029, 0033 and 0034.

**One caution on the tail counters.** Two branches cut from the same commit that
both bump the same entry merge without conflicting and count once. If work has
been running in parallel, re-derive each bumped tail counter from each branch's
own diff against the merge base and apply the totals, rather than trusting the
merge. The frozen five need none of this — nothing bumps them any more.

---

## 3. A test passed for a reason unrelated to what it asserted

**Caught: 52** (frozen 2026-08-23) · [the incidents, the root cause, and the whole rule](mistakes/03-a-test-passed-for-a-reason-unrelated-to-what.md)

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

## 1. A record went on asserting something the change had made false

**Caught: 45** (frozen 2026-08-23) · [the incidents, the root cause, and the whole rule](mistakes/01-a-record-went-on-asserting-something-the-change-had.md)

**Rule.** After changing a thing, ask what else in the repository asserts
something about that thing — comments, ADRs, tickets, indexes, READMEs, the pull
request body, test docstrings. Indexes are the highest risk: written once, never
re-read. "Re-read nearby prose" is not enough; it misses the record that was
never written and the one that drifted out from under you. **Grep the fact,
not the identifier** — a record states "three grants" or "in the same
transaction", and a grep for the name finds none of those sentences. **And
amending a record is not reading it**: open the whole file.

## 2. Behaviour shipped with nothing asserting it

**Caught: 33** (frozen 2026-08-23) · [the incidents, the root cause, and the whole rule](mistakes/02-behaviour-shipped-with-nothing-asserting-it.md)

**Rule.** After fixing something, try to reintroduce it. If the suite stays
green, you have written a convention, not a guarantee. Prefer asserting the
*forbidden* state over the permitted one — it keeps working when a legitimate
second case arrives.

## 13. A hazard was written down and worked around in only one of the two places facing it

**Caught: 25** (frozen 2026-08-23) · [the incidents, the root cause, and the whole rule](mistakes/13-a-hazard-was-written-down-and-worked-around-in.md)

**Rule.** When you work around a quirk of a type, a parser or an API, grep for
every place that asks the same question and route them through one helper, in the
same change. A docstring explaining the quirk is not a fix for the code that does
not call the fix. And when a test fails inside its own fixture, suspect the
fixture first — the message this one printed said exactly that, and was right.

## 9. Citing a guard as a guarantee without executing it

**Caught: 18** (frozen 2026-08-23) · [the incidents, the root cause, and the whole rule](mistakes/09-citing-a-guard-as-a-guarantee-without-executing-it.md)

**Rule.** Before citing a guard, execute it against the case you claim it stops
and the case you claim it allows. A guard that has never been run is a comment.
And never write a prediction that explains away the evidence of its own failure:
if you find yourself saying "there will be no confirmation, and that is expected",
you have removed the only signal that would have told you it did not work.

## 22. A ticket's new rule made an earlier ticket's tests unrunnable, and the repair was on the other side of the test wall

**Caught: 15** · [the incidents, the root cause, and the whole rule](mistakes/22-a-tickets-new-rule-made-an-earlier-tickets-tests.md)

## 16. A mutation harness reported kills it had not made

**Caught: 6** · [the incidents, the root cause, and the whole rule](mistakes/16-a-mutation-harness-reported-kills-it-had-not-made.md)

## 12. A stale build of the thing under test was reused, and the run looked clean

**Caught: 5** · [the incidents, the root cause, and the whole rule](mistakes/12-a-stale-build-of-the-thing-under-test-was.md)

## 8. Prescribing a fix without probing it

**Caught: 7** · [the incidents, the root cause, and the whole rule](mistakes/08-prescribing-a-fix-without-probing-it.md)

## 15. A property test's generator excluded the case its own docstring named

**Caught: 4** · [the incidents, the root cause, and the whole rule](mistakes/15-a-property-tests-generator-excluded-the-case-its-own.md)

## 19. A test held its expectation in a copy of the thing it was checking

**Caught: 7** · [the incidents, the root cause, and the whole rule](mistakes/19-a-test-held-its-expectation-in-a-copy-of.md)

## 14. An enumeration was reported as an impossibility

**Caught: 3** · [the incidents, the root cause, and the whole rule](mistakes/14-an-enumeration-was-reported-as-an-impossibility.md)

## 35. A guard enumerated the currencies a privilege can be held in, and missed the one the design deliberately uses

**Caught: 7** · [the incidents, the root cause, and the whole rule](mistakes/35-a-guard-enumerated-the-currencies-a-privilege.md)

**Rule.** When a guard enumerates mechanisms, require it to *find* each one on a
subject that certainly has it, as a control. A guard that only ever reports
absence cannot tell you which mechanisms it can see — and the role a scheme is
built around is the one least likely to hold its privileges the ordinary way.

## 17. An unqualified table name let the caller choose which table a guard read

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/17-an-unqualified-table-name-let-the-caller-choose-which.md)

## 34. A pipeline discarded a non-zero exit and printed a line that read as success

**Caught: 5** · [the incidents, the root cause, and the whole rule](mistakes/34-a-pipeline-discarded-a-non-zero-exit-and-printed.md)

**Rule.** Never read a gate's result through a pipe. `cmd | tail` reports the
exit status of `tail`, so a failing gate prints a passing line. Redirect to a
file and check the status, or run the gate bare.

## 6. Shell expansion inside a commit message

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/06-shell-expansion-inside-a-commit-message.md)

## 7. A verification window equal to the thing's own debounce

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/07-a-verification-window-equal-to-the-things-own-debounce.md)

## 18. A deliverable existed in the source tree and not in the built artifact

**Caught: 2** · [the incidents, the root cause, and the whole rule](mistakes/18-a-deliverable-existed-in-the-source-tree-and-not.md)

## 23. A validation created the appearance of a behaviour

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/23-a-validation-created-the-appearance-of-a-behaviour.md)

## 29. A value was repaired before the check that should have refused it

**Caught: 2** · [the incidents, the root cause, and the whole rule](mistakes/29-a-value-was-repaired-before-the-check-that-should.md)

## 33. A class-tree split put a case on the wrong side, and the docstring said otherwise

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/33-a-class-tree-split-put-a-case-on-the.md)

## 4. `git add` swept untracked files into a commit

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/04-git-add-swept-untracked-files-into-a-commit.md)

## 5. A branch cut from the wrong base

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/05-a-branch-cut-from-the-wrong-base.md)

## 10. Merged with the review loop one round short

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/10-merged-with-the-review-loop-one-round-short.md)

## 11. A failure in another process, invisible in the traceback that reported it

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/11-a-failure-in-another-process-invisible-in-the-traceback.md)

## 20. A mutation the fixture undid, read as a test that could not fail

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/20-a-mutation-the-fixture-undid-read-as-a-test.md)

## 21. A merge was committed with its conflict markers still in the file

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/21-a-merge-was-committed-with-its-conflict-markers-still.md)

## 30. A fixture supplied the value under test, so neither the green nor the red meant anything

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/30-a-fixture-supplied-the-value-under-test-so-neither.md)

## 31. "Running it twice is safe" was tested only against a database the loader itself had filled

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/31-running-it-twice-is-safe-was-tested-only-against.md)

## 27. A guard that reads a command as text refused a command that was only reading

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/27-a-guard-that-reads-a-command-as-text-refused.md)

## 28. A driver that could only speak correctly made the invalid half of every guard unreachable

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/28-a-driver-that-could-only-speak-correctly-made-the.md)

## 24. A test asserted a property no implementation could satisfy

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/24-a-test-asserted-a-property-no-implementation-could-satisfy.md)

## 25. Two lockfiles resolved the same package to two versions

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/25-two-lockfiles-resolved-the-same-package-to-two-versions.md)

## 26. A fallback path swallowed the defect that triggered it

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/26-a-fallback-path-swallowed-the-defect-that-triggered-it.md)

## 36. A probe deciding whether a gate runs answered false over a tree that had the thing

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/36-a-probe-deciding-whether-a-gate-runs-answered.md)

**Rule.** A probe that decides whether a gate runs is itself a gate. Plant what
the job actually runs and require a yes; plant nothing and require a no; assert
the whole set of outputs rather than the one you have in mind. `**` in a shell
glob is a single `*` unless `globstar` is set.

## 37. A harness ran the real artifact under conditions the runtime does not use

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/37-a-harness-ran-the-real-artifact-under-conditions.md)

**Rule.** When you extract something to run it, copy the invocation and not just
the body — the shell and its flags, the interpreter, the environment. Prefer a
harness the repository already has to one you write, and say which properties of
the runtime yours reproduces and which it does not. The harness the repository
already has is not exempt: when a result surprises you, reproduce it once against
the real runtime before believing either the green or the red.

## 38. An option parser answered before the guard did, and its answer was the permissive one

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/38-an-option-parser-answered-before-the-guard-did.md)

**Rule.** When a guard takes untrusted names as arguments, the argument parser is
part of the guard: pass `--` before any list that came from a diff or a glob, and
refuse leading-dash arguments in the script too. A decision made before your logic
runs is still your decision. Test the near miss that distinguishes the fix from
doing nothing.

## 39. A gate run was invalidated by edits that landed while it ran

**Caught: 4** · [the incidents, the root cause, and the whole rule](mistakes/39-a-gate-run-was-invalidated-by-edits-that.md)

**Rule.** While a gate runs, the tree it runs in is read-only — no edits, no
checkouts, no restores. A verdict is valid only for the tree it started on; if
the tree moved mid-run, the verdict is void and the run is repeated, whatever it
printed.

## 40. The suite ran under an environment nobody chose, and it was a different one in CI

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/40-the-suite-ran-under-an-environment-nobody-chose.md)

**Rule.** A test whose subject reads the process environment states the value it
runs under, in its own fixture chain. Anything a fixture runs in process brings
its whole startup with it — a tool that loads `.env` loads it for every test
that follows — so wrap such a run in a full snapshot-and-restore of the state it
mutates, not an enumerated one: the names that need undoing are exactly the ones
the fixture was never told. And when a suite is green locally and red in CI,
probe what each process actually holds at the failing call; do not infer it from
the fixtures that should have set it.

## 41. A request path inherited a background job's dependency, at that dependency's default retry policy

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/41-a-request-path-inherited-a-background-dependency.md)

**Rule.** A request path may not be able to fail because a background dependency
was unavailable, and it may not wait to find out. When a handler enqueues work,
publish with retries off, keep the result backend out of it for a task whose
answer nobody reads, **publish on a connection made for the call, with its own
retries off and its socket timeouts bounded**, and catch broadly — the request has
already done its own job by then, and the scheduled run covers the gap. The third
of those four was added after the other three were measured and found
insufficient: a publish flag governs the publish, while the client library opens
the connection under a retry policy of its own *before* the publish is attempted,
so a broker refusing instantly still costs seconds. Time the enqueue against a
closed port rather than trusting the flags. A client library's defaults are
written for the context that library is usually called from, and a worker's
defaults on a request path turn a dependency that is *down* into a request that is
*hanging*. And the corollary: a change that adds a call to a shared entry point is
not verified by the suites of the ticket that made it — run the whole suite, and
read its timing as well as its result.

## 42. A CI verdict was read off a stale check summary between two pushes

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/42-a-ci-verdict-was-read-off-a-stale-summary.md)

**Rule.** The only CI verdict that exists is a **completed** run whose head SHA
equals the final commit. A pull request's check rollup queried between two
pushes can answer for the superseded run — an empty failure list is not a green.
Before reporting green or marking anything ready, resolve the run by id, assert
`status == completed`, and assert its `headSha` equals the commit being vouched
for; a watch command's clean exit proves only that some run finished.

## 43. A broad guard's pattern matched ordinary prose, and named a file that runs no SQL

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/43-a-broad-guards-pattern-matched-ordinary-prose.md)

**Rule.** Prose in a **non-docstring** string under `backend/app/` is read by the
org-views SQL sweep, which excuses docstrings and nothing else. Before spending a
full-suite run, re-read any `Field(description=...)`, log message or error
sentence you added there for a policed relation name — `course`, `enrollment`,
`prefix`, `section` and the rest of `views_sql/`'s inventory — sitting after a
comma or after `from`, `join`, `into`, `update`, `table` or `using`; running that
one module answers it in under a second. **Reword the prose; never widen the
guard**, and leave a comment beside the reworded string saying why, or the next
edit puts the comma back.

## 44. A guard raised in a fixture turned a module's reds into setup errors

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/44-a-guard-raised-in-a-fixture-turned-reds-into-errors.md)

**Rule.** A tests-first suite's red must be a FAILED, never an ERROR: an error at
setup proves nothing about the assertion the test exists to make, survives the
implementation landing, and a wall of ERRORs reads to a hurried eye as "the suite
is red" — the exact wrong conclusion. Put a schema-or-deliverable guard in the
test body (a plain helper called as the first statement), never in a fixture,
and have the red-run verification count error-kind reds as divergences, not
reds.

## 45. A generated base64url identifier began with a dash and argparse read it as an option

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/45-a-generated-identifier-began-with-a-dash.md)

**Rule.** base64url output begins with `-` about one value in sixty-four, so any
CLI that accepts a generated identifier (a `kid`, a hash, a token) as a
positional argument fails on a schedule that reads as a flake — argparse reports
a *missing* required argument that was in fact given. Insert `--` before
positional values built from generated identifiers, and drive the test with an
identifier that starts with `-` rather than generating until one appears.

## 46. A privilege was attributed to the wrong role, and the ticket was built on it

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/46-a-privilege-was-attributed-to-the-wrong-role.md)

**Rule.** A settled decision that rests on a privilege is a claim about a role,
and the role is the half that gets mistyped: execute the read as that role before
the design is fixed on it, because a triple of column names reads identically
whichever role holds it. And a suite that drives a service through the migrating
engine has not tested the grant at all — where behaviour depends on one, at least
one test reaches the code through the connection production uses, or the
grant-shaped failure passes review as a green suite.
