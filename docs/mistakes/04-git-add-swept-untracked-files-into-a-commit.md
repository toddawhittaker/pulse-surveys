# Entry 4. `git add` swept untracked files into a commit

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*


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
