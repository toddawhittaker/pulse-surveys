# Entry 21. A merge was committed with its conflict markers still in the file

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*


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
