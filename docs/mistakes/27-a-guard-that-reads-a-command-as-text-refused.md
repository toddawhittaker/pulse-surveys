# Entry 27. A guard that reads a command as text refused a command that was only reading

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*


**What happened.** Three times in one E0-16 session.
`.claude/hooks/deny-test-edits.sh` stops the implementer writing under the test
directory, which is correct and is the whole point of the loop. It decides by
matching the **text of the command**, so it also refused
`git show <commit> -- <a test path> > /tmp/.../conftest.diff`, which writes to a
scratch directory and reads a test; a `cat > script.py <<'PY'` heredoc whose body
merely *mentioned* test paths; and — best of all — the heredoc carrying the first
draft of this entry, whose subject is the hook itself. None of the three could
have modified a test.

**Root cause.** A textual guard has no way to tell a path being written from a
path being read or quoted, so it fails safe by refusing both. That is the right
direction for the guard — the alternative is parsing shell, whose blind spots are
the same shape — and it means the refusal carries less information than it looks
like it does.

**Consequence.** Three round trips, which is nothing. The expensive version is
the conclusion an agent can draw from it: that the tests cannot be read at all,
and therefore that the implementation should be built from the ticket and a
summary of the tests. `CLAUDE.md` says not to work from a summary of the thing
that governs, and for an implementer the committed tests are exactly that. A
refusal read as "this material is off limits" instead of "this command shape is
off limits" turns a guard against editing into a reason to guess.

**Rule.** When a hook refuses a command, work out which part of the *command* it
matched before concluding anything about what you may know. Read files with the
`Read` tool, which the hook does not gate; keep test paths out of `Bash` command
text by redirecting to a file whose name does not carry the word, or by writing
the script with `Write` and running it by name. And when a guard's refusal seems
to forbid *reading*, say so and check, rather than proceeding on a narrower
picture of the ticket than the loop intended you to have.

---
