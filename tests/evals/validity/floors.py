"""The comment-validity precision and recall floors — measured on Luna under validity.v2.

One clean run over the 98 cases in `cases.py`, valid on the first pass: every case
answered by the model under `validity.v2`, none stamped by §3.3's character floor,
so nothing in the figures below came from the twenty-five-character rule the set
exists to beat.

**`cases.py` holds 108 cases as of this change, and every measured figure on this
page was taken over the 98.** FIX-02 adds ten fluent off-topic English comments to
the `nonsense` family, because nothing in the set measured whether the model
refuses grammatical prose that is not about the course. A re-measurement over the
new composition is being taken in this same change; its figures land in a
follow-up commit, here and in the `note` below, and until that commit arrives
every pair, agreement count and variance figure written down here is one measured
over the 98-case composition and is labelled as such rather than restated as a
measurement of the set that ships. What does not wait for the run is the
arithmetic: the new cases are negatives, the derivation over the new denominators
is under "The floors" below, and it is what says the recorded values still fit the
set they now govern. The floor values themselves do not move either way — a breach
found by the new run is a finding about the model, reported rather than resolved by
lowering a number (`CLAUDE.md`), and any resizing is E10's revisit.

    positive class `substantive` (ADR 0119)
    precision 1.000000   tp 53  fp 0
    recall    0.981481   fn 1   tn 44
    exact agreement 96/98        95.3s wall, longest call 2.61s

    per verdict:  substantive  p 1.000  r 0.9815
                  insufficient p 1.000  r 0.9615
                  nonsense     p 0.900  r 1.0000

Both disagreements are the same mistake in the same direction — the model reaching
for `nonsense`. `ls-025` is a substantive comment called nonsense, and it is the
one miss inside the recall figure; `lv-008` is an insufficient comment called
nonsense, which moves neither gated rate because both are negatives for the
positive class. That blindness is unchanged and deliberate: §3.3 treats
`insufficient` and `nonsense` identically for participation credit, and the
per-verdict figures above are recorded so a later ticket that wants to gate on the
distinction has a baseline. Nothing enforces them today.

**The miss moved, and it moved the right way.** Under `validity.v1` on
`gpt-5-mini-2025-08-07` the miss was `ss-005` — twenty-four characters,
substantive, called nonsense — a case in the short-substantive family this set
exists to measure. That case is answered correctly now and the miss is a
long-substantive one instead. It is recorded because it is the kind of thing that
is invisible three months later.

**`ls-025` stayed a miss across both Luna runs, and it did not stay still.** An
earlier version of this paragraph held it up as the stable one — a model defect
rather than sampling — against `lv-008` as the variable one. A security re-check
read both CI logs and found that wrong. The fill run answered `nonsense` to both
cases, which the per-verdict table above corroborates on its own: `nonsense`
precision 0.900 is two false positives, and those two are them. The second run
answered `insufficient` to both.

So both cases moved, and `ls-025` moved exactly as `lv-008` did. It stayed a miss
only because both of its answers were wrong — it is a substantive comment called
`nonsense` in one run and `insufficient` in the other, and recall cannot tell those
apart. A case can be unstable and still look fixed, if the instability happens
below the level the rate measures.

That is the sharpest thing these two runs say, and it is the opposite of what the
first version of this paragraph claimed: **variance reaches a positive-class
case** — one of the 54 the recall figure is computed over. A third run that
answered `substantive` there would move recall to 1.000 with nothing having
changed.

## The floors: precision 0.92, recall 0.90

Derived from this run's own counts by the three rules this file has carried since
the deferral. The arithmetic is written out because a reader meeting a red gate
has to be able to check it.

**Rule 1 — two errors of a kind is the pattern threshold.** One new error is
inside what a single measurement cannot tell from noise; a second of the same kind
is a pattern, and this gate fires on prompt and model changes, which is exactly
when a pattern means something.

**Rule 3 — and the measured variance sits on top of that, not inside it.** Two
identical runs of this set against **this** model and **this** prompt disagree
with each other by two cases in ninety-eight. That is not uncertainty about the
model's quality, it is the model: a rerun that changed nothing scores differently.
So the allowance is the pattern threshold *plus* the variance — two errors of a
kind plus two cases of variance, **four tolerated and the fifth firing**. A floor
sized at the pattern threshold alone would let ordinary variance spend it: a
single real regression on top of a rerun would fire the gate, and a gate that goes
red on ordinary movement is a gate that gets lowered the first time it does.

Subtracting the variance back out is the number that matters when a red arrives.
Four tolerated less two of measured variance leaves **two of real-regression
headroom**, which is rule 1's pattern threshold intact rather than eroded — the
whole point of composing the two rules instead of letting the larger one win.

**The two runs the figure comes from**, both `validity.v2` on `gpt-5.6-luna` over
the same 98 cases:

    the fill measurement          exact agreement 96/98   p 1.000  r 0.9815
    CI run 33679136272 @ 5f6a927  exact agreement 97/98   p 1.000  r 0.9815

Two cases answered differently between them, and both moved the same way —
`nonsense` in the first run, `insufficient` in the second. `lv-008` is an
insufficient comment, so its second answer was right and the exact-agreement count
went up by one. `ls-025` is a substantive comment, so both of its answers were
wrong and the count did not move for it at all.

So the variance is **two cases in ninety-eight**, measured on the model and the
prompt these floors govern. The exact-agreement counts differ by one and that is
not the figure: a case can move without changing whether it agrees, and one of
these two did exactly that.

**That figure keeps its provenance across FIX-02's composition change.** It was
measured over two runs of the 98-case composition, and it carries over as the
standing estimate until runs over the 108 exist to replace it. It is not restated
as a figure measured on 108 — nothing has measured that yet, and a variance
allowance is exactly the kind of number that acquires a denominator it was never
taken over if the sentence is quietly rewritten. When runs over the new
composition exist, the figure is re-derived from them and this paragraph goes.

**An earlier version of this section said one case, and founded the rule on a
mini/`validity.v1` pair** — a figure from a boundary this same file declares
non-portable. A security review caught the provenance; a re-check against both CI
logs then caught the count. Both corrections run the same way, toward more
variance than was recorded. The mini pair stays below as corroboration, labelled
as what it is, and it is the basis for nothing here.

**The variance is granted to each rate independently, and that is an
over-allowance rather than what these two runs strictly show.** Neither rate
moved: precision was 1.000 and recall 0.9815 in both, because both moves were
`nonsense` against `insufficient` and neither of those is the positive class. Read
strictly from the rates alone, the variance allowance would be zero and the floors
would be rule 1's 0.95 and 0.94.

Two reasons that reading is refused, and the first is now enough on its own:

- **One of the two movers is a positive-class case.** `ls-025` is one of the 54
  cases recall is computed over, and its answer moved between two identical runs.
  It did not move recall only because both answers were wrong; a third run
  answering `substantive` there moves recall to 1.000 with nothing changed. That
  is direct, same-boundary evidence that variance reaches the cases the gated
  rates depend on — a rate that did not move is not a rate that cannot.
- The asymmetry. Over-allowing costs a gate that tolerates one more error than it
  strictly must. Under-allowing costs a gate that reds on a rerun, and a gate that
  reds on ordinary movement is a gate that gets lowered — the failure rules 1 and
  3 exist together to prevent.

The mini/`validity.v1` pair corroborates the first reason from the other boundary:
its variance event was a false positive appearing between identical runs, landing
on a gated rate outright. It is useless as a *figure* here and it is no longer
load-bearing for the *argument* either, which is why it sits below as history
rather than in this list.

The values below were briefly held one step tighter than this composition, while
the corrected variance figure was ruled on; **the ruling of 2026-09-02 is that the
floors follow the composition**, and they do. The alternative — capping the
variance allowance and keeping the tighter pair — was considered and declined,
because it leaves one error of real-regression headroom against a pattern
threshold of two, which is the flaky-gate state rule 3 exists to prevent.

    precision 0.92   53/(53+4) = 0.9298 passes — four false positives tolerated
                     53/(53+5) = 0.9138 fails  — the fifth fires
    recall    0.90   49/54     = 0.9074 passes — five total misses tolerated,
                                                 which is four new ones
                     48/54     = 0.8889 fails  — the sixth fires

**Re-derived over the 108-case composition, and neither line above moves.** FIX-02
adds ten cases and all ten are negatives, so the set goes from 54 positives and 44
negatives to 54 positives and 54 negatives, and from 98 cases to 108. Recall is a
rate over the positive class and the positive class did not move: 49/54 and 48/54
are the same two lines they were, tolerating the same five total misses. Precision's
tolerated count comes from the positive-class count as well, not from the negatives
— the tolerance is four false positives measured against tp 53, so 53/(53+4)=0.9298
passes and 53/(53+5)=0.9138 fails whatever the negative count is, and both remain
reachable because 54 negatives is far more than five.

So the tolerance has not moved and must not be read as having moved. What the ten
new negatives add is ten more *opportunities* to make a false positive under the
same allowance of four: a model that reaches for `substantive` on fluent off-topic
English now has ten more cases on which it can do so, and the same four-error budget
to do it in. That is the floors becoming effectively tighter without a value
changing, which is the cheap direction — and it is why a composition change of this
shape may keep the numbers it was measured with while the re-measurement is taken.

**These may tighten later, and that direction is the cheap one.** The variance
allowance is two because two runs measured two cases; more runs refine that figure,
and a smaller one licenses a higher floor. Moving them is a deliberate pull request
whose subject is moving them either way — but tightening a floor on better evidence
is the move this arrangement is meant to make easy, and loosening one is the move
it is built to make hard.

**Rule 2 — precision is held at least as tightly as recall**, which inverts the
threat task's priority. §3.3 validates synchronously: a student whose comment is
judged insufficient is told so at submit time, with coaching copy and a chance to
rewrite, so a false negative is visible to the person it affects and recoverable
by them. A false positive is not — participation credit awarded for "it was okay"
is silent, reaches §3.4's grade passback, and nobody ever sees it. SPEC §9.3 makes
recall the strictest floor for threat and self-harm because a false negative there
is a student in danger whose comment reached nobody; on this task the invisible
error is the other one.

**How that rule is satisfied here, stated exactly rather than claimed.** Both
floors tolerate the same number of *new* errors of their own kind — four — and
precision's is the numerically higher bar. It is not strictly tighter in error
count, and it should not be: cutting precision's allowance would leave ordinary
variance plus one real false positive firing the gate, which is the failure rule 1
exists to prevent, and buying a stricter-looking number with it would be a bad
trade. The argument is about the two floors relative to each other rather than
about where either sits, so it survives the pair moving together.

## The model string, and the pin this run does not have

The provider is `gpt-5.6-luna`. **No dated snapshot of it exists**, so unlike
`gpt-5-mini-2025-08-07` this name does not pin a set of weights: the provider can
change what answers to it without anything here changing, and these floors would
then be measuring a different model under the same name with nothing saying so.
ADR 0031 makes `model_id` "the provider's own identifier for the model" precisely
so §9.3 can compare runs of different models, and that comparison is weaker here
than it was.

It is recorded rather than worked around, because there is nothing to work around:
a snapshot that does not exist cannot be pinned. The consequence is that an
unexplained movement in these figures has one more possible cause than it used to,
and the first question on a surprising red is whether the name still means what it
meant. If a dated snapshot appears, pinning it is a one-line change here and in
the configuration, and worth making.

## Filling it in again

Moving a floor is a deliberate pull request whose subject is moving it
(`CLAUDE.md`). Lowering one to make a run pass is what
`.claude/review-fixtures/eval-floor-lowered.diff` plants, and a narrowed set is
the same move wearing a costume —
`tests/unit/test_the_validity_eval_set_carries_the_cases_the_heuristic_gets_wrong.py`
holds the set's size and both class counts against that. That the gate can go red
is not taken on trust either: `tests/evals/validity/breach.py` is a set the current
prompt fails by construction, run through the real path on demand.

A re-measurement replaces the numbers and the note together. The note carries the
model, the prompt version, the run basis, the arithmetic for each floor's
headroom, and the variance figure with its provenance — and if the run count
behind that variance is still two, it says two.
"""

from __future__ import annotations

from tests.evals.declarations import TaskFloors, enforced

FLOORS: TaskFloors = enforced(
    precision=0.92,
    recall=0.90,
    note=(
        "Measured against validity.v2 on gpt-5.6-luna over the 98 cases cases.py held "
        "before FIX-02, in one clean run — a single run, not an average — where every case "
        "was answered by the model and none by §3.3's character floor: precision 1.000000 "
        "(tp 53, fp 0), recall 0.981481 (fn 1, tn 44). The measured run-to-run variance is "
        "two cases in ninety-eight, on this same model and this same prompt, from two "
        "independent runs "
        "— the fill measurement at 96/98 exact agreement and CI run 33679136272 on commit "
        "5f6a927 at 97/98; it was taken over that same 98-case composition and carries over "
        "as the standing estimate until runs over the 108 exist. "
        "Both ls-025 and lv-008 answered nonsense in the first and "
        "insufficient in the second; the agreement counts differ by one only because "
        "ls-025 was wrong either way, which is why the count is not the figure. Neither "
        "rate moved, and the allowance is still granted to each separately: ls-025 is a "
        "positive-class case, so variance demonstrably reaches the cases recall is "
        "computed over. The floors follow the recorded composition — the pattern threshold "
        "of two errors of a kind plus the variance of two, giving four tolerated and the "
        "fifth firing, which leaves two of real-regression headroom once the variance is "
        "subtracted back out. So precision 0.92 passes at 53/(53+4)=0.9298 and fails at "
        "53/(53+5)=0.9138, and recall 0.90 passes at 49/54=0.9074 and fails at "
        "48/54=0.8889. Ruled 2026-09-02, against the alternative of capping the allowance "
        "and holding a tighter pair, which would have left one error of headroom against a "
        "threshold of two — the flaky-gate state rule 3 exists to prevent. They may tighten "
        "in a later deliberate pull request as more runs refine the variance figure. "
        "Precision is held "
        "at the numerically higher bar because §3.3 validates at submit time: a false "
        "negative is shown to the student and recoverable, a false positive is silent "
        "credit that reaches §3.4's passback. The model name pins no snapshot — no dated "
        "gpt-5.6-luna exists — so these figures do not fix a set of weights, and that is a "
        "known gap rather than an oversight. "
        "cases.py holds 108 cases as of FIX-02, which added ten fluent off-topic English "
        "comments to the nonsense family: all ten are negatives, so the positive class "
        "stays at 54 and both lines of arithmetic above are unmoved while the negatives go "
        "from 44 to 54 — ten more opportunities for a false positive under the same "
        "tolerance of four. Every figure in this note was measured over the 98; the "
        "re-measurement over the 108 is being taken in the same change and its figures land "
        "in a follow-up commit."
    ),
)
