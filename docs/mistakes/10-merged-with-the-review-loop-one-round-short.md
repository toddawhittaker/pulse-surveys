# Entry 10. Merged with the review loop one round short

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*


**What happened.** Pull request #13 went through three reviewer passes. The third
returned four findings; those were fixed, verified by mutation and by running the
stack, and merged. **No reviewer pass ran against the fixes.** The loop stopped
one round before the code that landed.

The independent `/security-review` did cover the final state and came back clean,
so the §14.2 gate was met. What was missing is narrower and easier to miss: the
last thing the reviewers saw was the code that provoked the findings, not the code
that answered them.

**Root cause.** Treating a fix round as the end of a review round. The findings
were closed, each fix was checked by the person who asked for it, and the checking
felt like the review. It is not — it is the same session that scoped the fix
confirming the fix matches the scope, which cannot notice a fix that is wrong in a
way nobody thought to scope.

**Consequence.** Four changes merged unreviewed, one of them a security fix to how
a database password reaches Postgres. All four have since held up, so the cost
this time was zero — which is exactly why the rule needs writing down rather than
remembering. The three previous rounds each turned up something in the *previous*
round's fixes, including two defects introduced by a fix for that same class of
defect. On the base rate of this branch, the fourth round would have found
something.

**Rule.** A fix round closes with a review pass, not with the fixer's own
verification, however thorough. If the fixes are trivial enough that a pass seems
wasteful, say so in the pull request and let the merge decision be made knowing
it — the judgment is fine, the silence is not. This applies to the coordinating
session too: verifying a fix yourself is evidence it does what you asked for, not
evidence it is right.

---
