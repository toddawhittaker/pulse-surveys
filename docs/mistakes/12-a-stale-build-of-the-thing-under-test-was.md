# Entry 12. A stale build of the thing under test was reused, and the run looked clean

**Caught: 5**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*(Applied before anything went wrong rather than after. E0-15's
mutation harness edits `mock-lms/app/*.py` and reverts each edit inside seconds,
which is exactly the size-and-second window this entry's root cause describes —
and `tests/fixtures/app_imports.py` re-imports every `app.*` module per platform, so a stale
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
