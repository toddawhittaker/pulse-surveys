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

**Re-ordering, and the tier.** Sort by `Caught:` descending when you notice it is
wrong, and re-derive the tier from the same numbers: the five highest carry their
rule in this file, the rest carry a link. An entry that rises into the top five
gains its rule here; one that falls out keeps everything and loses only the
duplication. The tier follows the counter rather than position, so it is a
consequence of the sort rather than a second thing to maintain.

Sort by `Caught:` descending when you notice it is wrong. Ties
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

**Caught: 50** · [the incidents, the root cause, and the whole rule](mistakes/03-a-test-passed-for-a-reason-unrelated-to-what.md)

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

**Caught: 43** · [the incidents, the root cause, and the whole rule](mistakes/01-a-record-went-on-asserting-something-the-change-had.md)

**Rule.** After changing a thing, ask what else in the repository asserts
something about that thing — comments, ADRs, tickets, indexes, READMEs, the pull
request body, test docstrings. Indexes are the highest risk: written once, never
re-read. "Re-read nearby prose" is not enough; it misses the record that was
never written and the one that drifted out from under you. **Grep the fact,
not the identifier** — a record states "three grants" or "in the same
transaction", and a grep for the name finds none of those sentences. **And
amending a record is not reading it**: open the whole file.

## 2. Behaviour shipped with nothing asserting it

**Caught: 32** · [the incidents, the root cause, and the whole rule](mistakes/02-behaviour-shipped-with-nothing-asserting-it.md)

**Rule.** After fixing something, try to reintroduce it. If the suite stays
green, you have written a convention, not a guarantee. Prefer asserting the
*forbidden* state over the permitted one — it keeps working when a legitimate
second case arrives.

## 13. A hazard was written down and worked around in only one of the two places facing it

**Caught: 24** · [the incidents, the root cause, and the whole rule](mistakes/13-a-hazard-was-written-down-and-worked-around-in.md)

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

## 12. A stale build of the thing under test was reused, and the run looked clean

**Caught: 5** · [the incidents, the root cause, and the whole rule](mistakes/12-a-stale-build-of-the-thing-under-test-was.md)

## 8. Prescribing a fix without probing it

**Caught: 6** · [the incidents, the root cause, and the whole rule](mistakes/08-prescribing-a-fix-without-probing-it.md)

## 15. A property test's generator excluded the case its own docstring named

**Caught: 4** · [the incidents, the root cause, and the whole rule](mistakes/15-a-property-tests-generator-excluded-the-case-its-own.md)

## 19. A test held its expectation in a copy of the thing it was checking

**Caught: 5** · [the incidents, the root cause, and the whole rule](mistakes/19-a-test-held-its-expectation-in-a-copy-of.md)

## 14. An enumeration was reported as an impossibility

**Caught: 3** · [the incidents, the root cause, and the whole rule](mistakes/14-an-enumeration-was-reported-as-an-impossibility.md)

## 35. A guard enumerated the currencies a privilege can be held in, and missed the one the design deliberately uses

**Caught: 3** · [the incidents, the root cause, and the whole rule](mistakes/35-a-guard-enumerated-the-currencies-a-privilege.md)

**Rule.** When a guard enumerates mechanisms, require it to *find* each one on a
subject that certainly has it, as a control. A guard that only ever reports
absence cannot tell you which mechanisms it can see — and the role a scheme is
built around is the one least likely to hold its privileges the ordinary way.

## 22. A ticket's new rule made an earlier ticket's tests unrunnable, and the repair was on the other side of the test wall

**Caught: 4** · [the incidents, the root cause, and the whole rule](mistakes/22-a-tickets-new-rule-made-an-earlier-tickets-tests.md)

## 17. An unqualified table name let the caller choose which table a guard read

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/17-an-unqualified-table-name-let-the-caller-choose-which.md)

## 34. A pipeline discarded a non-zero exit and printed a line that read as success

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/34-a-pipeline-discarded-a-non-zero-exit-and-printed.md)

**Rule.** Never read a gate's result through a pipe. `cmd | tail` reports the
exit status of `tail`, so a failing gate prints a passing line. Redirect to a
file and check the status, or run the gate bare.

## 6. Shell expansion inside a commit message

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/06-shell-expansion-inside-a-commit-message.md)

## 7. A verification window equal to the thing's own debounce

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/07-a-verification-window-equal-to-the-things-own-debounce.md)

## 18. A deliverable existed in the source tree and not in the built artifact

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/18-a-deliverable-existed-in-the-source-tree-and-not.md)

## 23. A validation created the appearance of a behaviour

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/23-a-validation-created-the-appearance-of-a-behaviour.md)

## 29. A value was repaired before the check that should have refused it

**Caught: 1** · [the incidents, the root cause, and the whole rule](mistakes/29-a-value-was-repaired-before-the-check-that-should.md)

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

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/31-running-it-twice-is-safe-was-tested-only-against.md)

## 27. A guard that reads a command as text refused a command that was only reading

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/27-a-guard-that-reads-a-command-as-text-refused.md)

## 28. A driver that could only speak correctly made the invalid half of every guard unreachable

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/28-a-driver-that-could-only-speak-correctly-made-the.md)

## 24. A test asserted a property no implementation could satisfy

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/24-a-test-asserted-a-property-no-implementation-could-satisfy.md)

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

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/37-a-harness-ran-the-real-artifact-under-conditions.md)

**Rule.** When you extract something to run it, copy the invocation and not just
the body — the shell and its flags, the interpreter, the environment. Prefer a
harness the repository already has to one you write, and say which properties of
the runtime yours reproduces and which it does not. The harness the repository
already has is not exempt: when a result surprises you, reproduce it once against
the real runtime before believing either the green or the red.

## 38. An option parser answered before the guard did, and its answer was the permissive one

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/38-an-option-parser-answered-before-the-guard-did.md)

**Rule.** When a guard takes untrusted names as arguments, the argument parser is
part of the guard: pass `--` before any list that came from a diff or a glob, and
refuse leading-dash arguments in the script too. A decision made before your logic
runs is still your decision. Test the near miss that distinguishes the fix from
doing nothing.

## 33. A class-tree split put a case on the wrong side, and the docstring said otherwise

**Caught: 0** · [the incidents, the root cause, and the whole rule](mistakes/33-a-class-tree-split-put-a-case-on-the.md)
