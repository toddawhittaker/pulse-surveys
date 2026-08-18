# Entry 6. Shell expansion inside a commit message

**Caught: 1**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*


**What happened.** `git commit -m "…$$POSTGRES_USER…"` in double quotes. The
shell expanded `$$` to its process id.

**Root cause.** Double quotes in the shell expand `$`. The message explained an
escaped-dollar parser, so it was exactly the text that could not survive it.

**Consequence.** Commit `77620c0` permanently reads `pg_isready -U
1793726POSTGRES_USER`, in the paragraph explaining the subtlest line in the
change. History is not force-pushed here, so it cannot be corrected.

**Rule.** Write commit messages through a quoted heredoc (`<<'EOF'`) or
`git commit -F`. Never `-m` with double quotes when the text contains `$`.

---
