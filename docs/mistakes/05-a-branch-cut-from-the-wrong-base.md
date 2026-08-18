# Entry 5. A branch cut from the wrong base

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*


**What happened.** `e0/reviewer-hook-enforcement` was cut while standing on
`e0/backend-skeleton` instead of on the epic branch.

**Root cause.** Cutting a branch without checking out the base first, and not
checking the resulting diff.

**Consequence.** Pull request #12's diff was 35 files and ~3,960 additions rather
than the 5-file hook change its description claimed. Merging it merged E0-01
along with it, so pull request #11 merged as a no-op with no merge commit of its
own. The history now shows one merge where the record says two.

**Rule.** `git checkout <epic-branch>` before `git checkout -b`, then confirm
with `git merge-base --is-ancestor`. Before writing a pull request description,
run `gh pr diff <n> --name-only` and check it against what you think you changed.

---
