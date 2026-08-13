# Mistakes

Things that have actually gone wrong in this repository, and the rule that
prevents each one happening again. Every entry is a real incident with a real
consequence — nothing here is hypothetical, and nothing is here because it
sounded like good advice.

**Read this before you start work.** It is short on purpose, and it is ordered
so the first entries are the ones that keep happening.

## How to use it

**Consulting it.** Read the headings. If one describes something you are about
to do, read that entry and act on its rule.

**Bumping the counter.** When an entry stops you making the mistake, increment
its `Caught:` number in the same change as the work it saved. That number is the
only signal for what belongs at the top, so an entry nobody bumps sinks and an
entry that keeps saving people rises. Do not bump for reading an entry — bump
for an entry changing what you did.

**Adding an entry.** When something goes wrong, append: what happened, the root
cause, the consequence, and the rule. Cite the real artifact — the commit, the
file and line, the pull request. A rule with no incident behind it is advice,
and advice belongs in `CLAUDE.md`.

**Re-ordering.** Sort by `Caught:` descending when you notice it is wrong. Ties
break toward the more expensive consequence.

---

## 1. A record went on asserting something the change had made false

**Caught: 0**

**What happened.** Nine times, across three tickets. `.dockerignore`'s header
claimed it made secret leakage "impossible rather than unlikely" while `!backend`
re-included the whole subtree. The `db` health-check comment described
authentication that `pg_isready` never performs. A comment said the application
role held "nothing but CONNECT" when it kept Postgres's `PUBLIC` defaults. ADR
0007 claimed digest drift "is visible in a diff on both sides"; that was
retracted, and then the retraction itself went stale two commits later when the
guard landed. `.env.example` said both readers resolve `${...}` top-down, which
measurement disproved. The ADR index silently omitted three ADRs the same branch
shipped. Pull request #13's description spent a round describing a one-role
database stack that no longer existed.

**Root cause.** Changing a mechanism and not asking what else in the repository
makes a claim about it. Two of these were *introduced by a fix for this same
class of defect* — the `.env.example` header rewritten to correct one false claim
acquired a different one, that `LOG_LEVEL` is settled by the spec, which the spec
never mentions.

**Consequence.** A reader trusts the record over the code, because reading the
record is cheaper. That is what a record is for, so a false one is worse than
none. The stale pull request body was rated HIGH: it was the artifact the merge
decision rested on.

**Rule.** After changing a thing, ask what else in the repository asserts
something about that thing — comments, ADRs, tickets, indexes, READMEs, the pull
request body, test docstrings. Indexes are the highest risk: written once, never
re-read. "Re-read nearby prose" is not enough; it misses the record that was
never written and the one that drifted out from under you.

---

## 2. Behaviour shipped with nothing asserting it

**Caught: 0**

**What happened.** Four times. `__repr_args__` was added to keep credentials out
of `repr(settings)` — deleting it left the suite green. The `institution_timezone`
validator could be deleted whole with the suite green. "`DATABASE_URL` must never
point at the superuser" was prose, and repointing it passed all 50 tests and the
`docker` gate. The two Postgres image digests could be set to different values
with every gate green.

**Root cause.** Fixing the defect and stopping there. The fix is visible in the
diff, so it feels done; nothing makes the absence of a guard visible.

**Consequence.** The next person deletes it during an unrelated refactor and
every gate stays green. For the superuser case, the exact defect the pull request
existed to fix was reintroducible without any signal.

**Rule.** After fixing something, try to reintroduce it. If the suite stays
green, you have written a convention, not a guarantee. Prefer asserting the
*forbidden* state over the permitted one — it keeps working when a legitimate
second case arrives.

---

## 3. A test passed for a reason unrelated to what it asserted

**Caught: 0**

**What happened.** A test asserting that a startup error carries no credential
passed against a demonstrably leaking implementation, because ten variables
happened to be set and pydantic's repr elision landed between the two passwords.
Separately, a set-equality test would have passed comparing two empty sets, if
a workflow's shape changed so nothing was collected.

**Root cause.** Asserting an absence. Absence is satisfied by the thing being
broken in an unrelated way, by a fixture returning nothing, by a parser matching
nothing.

**Consequence. ** A green suite is read as coverage. The first case would have
been counted as proof the leak was fixed when it proved nothing about it.

**Rule.** Verify by mutation, not by reading: break the thing and watch the test
fail. Where a test can be satisfied by emptiness, assert non-emptiness first, and
say in the message why that guard is not ceremony.

---

## 4. `git add` swept untracked files into a commit

**Caught: 0**

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

## 5. A branch cut from the wrong base

**Caught: 0**

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

## 6. Shell expansion inside a commit message

**Caught: 0**

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

## 7. A verification window equal to the thing's own debounce

**Caught: 0**

**What happened.** Checking that a drifted database password made the container
report unhealthy, the poll ran for exactly 60 seconds. Docker needs `retries: 12`
× `interval: 5s` — 60 seconds of consecutive failures — before it flips.

**Root cause.** Choosing the window from the interval without adding the debounce.

**Consequence.** Nearly reported a working fix as broken. The health log already
said `password authentication failed`; only the status had not caught up.

**Rule.** When verifying a debounced state change, wait past the debounce and
read the underlying log as well as the summary status. A negative result inside
the debounce window is not a result.

---

## 8. Prescribing a fix without probing it

**Caught: 0**

**What happened.** `hide_input_in_errors=True` was the obvious fix for a
credential appearing in a pydantic validation error. It cleans `str(exc)` and
leaves the credential in `errors()`.

**Root cause.** The fix was plausible and cheap, so it went into the brief
without being run.

**Consequence.** Would have shipped green against the one test that existed,
leaving the credential one `json.dumps` from any structured logger.

**Rule.** Before naming a mechanism in a brief, run it. If you are asking for a
property, say the property and let the implementer find the mechanism.

---

## 9. Citing a guard as a guarantee without executing it

**Caught: 1**

**What happened.** Three times. A brief told the test author "a hook denies you
writes elsewhere" — no such hook existed; the hook matched `Read|Grep|Glob` and
denied *reads* of implementation source. Both hooks then turned out to fail open
when `jq` was absent, and one could be bypassed entirely with `cat` through
`Bash`, while their own comments called one "the wall."

The third is the sharpest, and it is a coordination mechanism rather than a hook.
A peer Claude session was asked to run `/clear` before a security review, so the
review would start with fresh eyes. `/clear` is a harness command: nothing a peer
sends can make it fire. The request also carried the line "I know you cannot
report back, because this message goes with it" — which **pre-explained the
silence the failure would produce**. Had the peer simply not replied, that would
have read as confirmation, and the review request would have gone into a context
still holding the previous review and the requester's framing of it. The peer
caught it and said so.

**Root cause.** Reading a mechanism's name and description instead of running it,
then reasoning about what its output would look like instead of observing the
output.

**Consequence.** Two rounds of work proceeded on a guarantee that was not
enforced. The third would have produced a review that looked independent and was
not — *worse than skipping the clear*, because the result would have been trusted
more.

**Rule.** Before citing a guard, execute it against the case you claim it stops
and the case you claim it allows. A guard that has never been run is a comment.
And never write a prediction that explains away the evidence of its own failure:
if you find yourself saying "there will be no confirmation, and that is expected",
you have removed the only signal that would have told you it did not work.

---

## 10. Merged with the review loop one round short

**Caught: 0**

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
