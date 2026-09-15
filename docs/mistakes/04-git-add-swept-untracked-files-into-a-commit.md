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

**What happened, again — 2026-09-15, E5-13, commit 37ec568.** A different cause,
the same shape. The implementer ran `git add -A` for a records-only commit in a
checkout where the test author was working in parallel, and swept that author's
half-written module into it. Nothing was untracked this time: the file was
tracked and someone else was editing it, which no `.gitignore` entry can prevent.
The stray file was found by running `git show --stat` against the subject line,
which is this entry's rule, and the message was amended to say whose the file was
and that it was neither read for the commit nor edited. On the heavy lane that is
a sharper problem than a message that disagrees with its diff: the implementer
may not change a test, so a commit of theirs carrying one looks exactly like a
breach of the wall.

**The rule this adds.** In a checkout somebody else is working in, stage by path.
`git add -A` and `git add .` collect whatever the other person has half-finished,
and "I only edited my own files" is not a claim about what the index holds.

---
