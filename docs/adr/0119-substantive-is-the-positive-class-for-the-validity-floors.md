# 0119 — `substantive` is the positive class the validity precision and recall floors are about

**Status:** Accepted
**Date:** 2026-09-02
**Tickets:** E2-12

## Context

SPEC §9.3 asks for "per-task precision/recall floors". Precision and recall are
defined over a binary decision — one class is positive, everything else is
negative — and the comment-validity task's output is three-way. SPEC §7.4's
table gives its verdicts as `substantive / insufficient / nonsense`, and the spec
says nothing anywhere about which of the three the pair of numbers is about.

Until somebody says, a "precision" figure for this task is not a number with a
meaning. Three readings are available and they measure different things: the
positive class is `substantive`; the positive class is "not substantive", which
is what a moderation instinct reaches for; or the pair is macro-averaged over all
three verdicts, which is one number about three decisions.

This has to be settled before a floor is measured, not after. A floor is a number
somebody will later be asked to defend or to move, and a floor whose positive
class was never written down cannot be compared with the next one — the same
model on the same set produces different figures under each reading.

## Decision

**The positive class is `substantive`.** Precision is the share of comments the
classifier called `substantive` that really are; recall is the share of really
substantive comments it found. `insufficient` and `nonsense` are both negative,
and the runner reports their counts without gating on them.

The reason is that `substantive` is the class with a consequence attached. SPEC
§3.3 gates participation on it: a comment judged substantive earns the student
credit, and a comment judged otherwise does not. So the two error directions are
the two things that can go wrong to a student, and each maps onto one of the two
numbers:

- a **false positive** is credit awarded for "it was okay", which is the
  prototype heuristic's failure mode — §3.3 keeps the twenty-five-character rule
  "solely as the fail-open floor" precisely because it awards credit to a long
  vacuous comment;
- a **false negative** is credit withheld from a student who wrote something
  real and short, which is the same heuristic's other failure.

`insufficient` and `nonsense` differ in what a student is *told* — the coaching
copy §3.3 shows at submit time — and not in what they are given. That is a real
difference and it is not what a participation gate turns on, so it is not what
the gate's floor should be measured over.

## Alternatives rejected, and why

**"Not substantive" as the positive class.** It reads naturally if you come to
this from moderation, where the positive class is the thing you are hunting. It
inverts both numbers — recall then measures how many refusals the classifier
found — and it makes the §9.3 floor for this task read in the opposite direction
from the §9.3 floor for the threat and self-harm task, where the positive class
genuinely is the thing being hunted. Two tasks in one suite whose "recall" means
opposite things is a reading error waiting to happen, on a page where one of the
numbers is a hard safety gate.

**Macro-averaged precision and recall over all three verdicts.** Defensible, and
it is what a general classification report prints. It buys a number that no
decision in this system turns on: nothing distinguishes `insufficient` from
`nonsense` for any purpose §3.3 names, so averaging over that distinction lets a
classifier trade accuracy on the decision that matters for accuracy on one that
does not. It would also make the floor harder to reason about when it is later in
the way — the question "which class regressed" has no short answer.

**Deferring the choice and reporting all three verdicts' rates.** This is what a
runner that refused to choose would do, and it defers the decision to whoever
reads the log — which means it is made differently each time, and never written
down. §9.3's gate is a comparison against a number; a gate needs one number per
rate.

**Deciding it at floor-measurement time, from whichever reading gave the more
comfortable figure.** Named because it is the failure this record exists to make
impossible. The class is fixed before the first measurement, in a file separate
from the floors, so that the numbers cannot be chosen and then justified.

## Consequences

**The eval set has to hold enough of both classes for a rate to mean anything**,
and the runner refuses a set with no case of the positive class rather than
reporting recall over an empty denominator. The set therefore carries a
`POSITIVE_VERDICT` constant beside the cases, and the registry hands it to the
runner per task — so the threat and self-harm set E10 builds names its own
positive class and is not silently measured under this one.

**Both empty denominators resolve toward failing.** A classifier that never
answers the positive class scores zero precision rather than one, and a set with
no positive case is refused rather than scored. Either resolved the other way is
a floor that a gate can clear by doing nothing.

**The two families the set is built around are both about this class.** The short
substantive comment and the long vacuous one are the two cases the
twenty-five-character heuristic gets wrong, in the two directions this decision
names — which is what makes the set one a character counter cannot score
perfectly, and therefore one that measures a classifier rather than a threshold.

**Changing the positive class later invalidates every floor measured under this
one.** Moving it would be a new measurement and a new number, not a reading of
the old figures, and it belongs in a pull request whose subject is moving them
(`CLAUDE.md` — "floors move only in a deliberate PR whose subject is moving
them").
