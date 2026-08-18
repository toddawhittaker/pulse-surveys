# Entry 16. A mutation harness reported kills it had not made

**Caught: 6**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*5 instances recorded; the 3 most recent are below. The earlier 2 are in this file's git history and in the pull requests they cite.*

*(In E0-15, and this entry's last paragraph is the one that fired: "read
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

*(And its subject is a mutation that lives in the database rather than
in a file. The cycle tests plant an inverted edge by reinstalling E0-09's trigger
function, writing the row, and restoring E0-11's — three statements, any of which
can silently not take effect, after which the test measures a database in a state
nobody intended. So the plant reads the edge back out before anything is believed,
asserts the session is off `replica` again, and restores the function in a
`finally` so a failing assertion does not leave E0-09's trigger installed for
whatever runs next.)*

*(In E0-11, and it is this entry's last paragraph applied before
anything went wrong. The object under measurement is a trigger function body, which
lives in the database rather than in a file, and the thing being claimed is that
`downgrade()` puts E0-09's version back. So the baseline is read **from the revision
that installs it** — `014ccb3d0fe5`'s own dollar-quoted constant, parsed off disk —
and never from `pg_proc`, because a downgrade that reinstates whatever the database
happens to hold reinstates nothing and reports success. Control 0 is that E0-11's
`PREVIOUS_…` constant equals E0-09's shipped body byte for byte; control 1 is that
the two bodies differ at head. Without the second, "the bodies match after the
downgrade" is true of a revision that changed the function not at all.)*

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
