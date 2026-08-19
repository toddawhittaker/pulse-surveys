# Entry 37. A harness ran the real artifact under conditions the runtime does not use

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*1 instance recorded.*

*(E0-38, and it was found by an audit written after the build was green. The
`changed` job's classification step was extracted from the parsed workflow and
executed, which is the right instinct and is what this repository does instead of
reading YAML. It was executed with `bash script.sh`. GitHub runs a `run:` block
that declares no `shell:` as **`bash -e {0}`**, and the step's own
`set -uo pipefail` adds two options without clearing an inherited `-e`.

The step's classifier exits 1 to mean "this diff is not inert", which is the
answer every code-touching pull request produces. Under `-e` a bare command
exiting non-zero ends the script, so `status=$?` was never reached. Measured
against the real step: exit 1, nothing emitted, the classifier's correct answer
sitting in the log above it. The `changed` job would have failed, every job
needing it would have reported `skipped`, and E0-36 had just made the aggregate
check treat `skipped` as a failure — so **every code-touching pull request would
have failed the required check**, starting with the one introducing it.

Two details make this worth an entry rather than a footnote. The harness was
correct in extraction and wrong only in invocation, so everything it reported was
real behaviour of the real artifact under a shell the runtime never uses. And the
correct pattern was already in the repository: `test_the_detect_probes_see_the_files_their_jobs_run.py`
invokes probes with `bash -e`, in the same workflow, written the round before.)*

**What happened.** A harness executed the genuine artifact and reported measured
results, and the results were about a configuration that does not occur. The
defect it hid was not subtle once seen — it was the difference between `bash` and
`bash -e` on one line.

**Why it is not entry 12 or entry 20.** Entry 12 is a stale build of the thing
under test: the harness ran something other than the current artifact. Entry 20 is
a mutation the fixture undid. Here the artifact was current and nothing undid
anything — the *environment* was wrong, and the artifact behaved differently in it
than in production. That is a third way for a measurement to be true and useless.

**Rule.** When you extract something to run it, copy the invocation and not just
the body: the shell and its flags, the interpreter, the environment, the working
directory. Prefer a harness that already exists in the repository to one you
write, and when you write one, state which properties of the runtime it
reproduces and which it does not. A measured result is only as good as the
conditions it was measured under, and those conditions are part of the artifact.
