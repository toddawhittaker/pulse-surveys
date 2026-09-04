"""The comment-validity precision and recall floors — measured on Luna under validity.v2.

One clean run over the 108 cases in `cases.py`, valid on the first pass: every case
answered by the model under `validity.v2`, none stamped by §3.3's character floor,
so nothing in the figures below came from the twenty-five-character rule the set
exists to beat.

    positive class `substantive` (ADR 0119)
    precision 1.000000   tp 53  fp 0
    recall    0.981481   fn 1   tn 54
    exact agreement 107/108      100.6s wall, longest call 2.46s

    the fill measurement, taken locally off `.env` on 2026-09-03 against a cold
    cache. A second run over this composition exists — CI run 33830242674 on
    commit 3be69bb — and is recorded under "The floors" below. Those two are the
    runs over the 108 that this page cites.

**The composition moved in this change, and the run above is the re-measurement.**
FIX-02 adds ten fluent off-topic English comments to the `nonsense` family —
grammatical English a reader instantly sees is not about the course — because
nothing in the set measured whether the model refuses that region, and unmeasured
is the state this set exists to remove. All ten are negatives, so the positive
class stays at 54 while the negatives go from 44 to 54. The floor values did not
move, and the derivation under "The floors" below is what says they still fit the
set they now govern.

**The new group cost the measurement nothing.** Every one of `ns-019` through
`ns-028` was answered `nonsense`, first pass, ten out of ten. That is a result
rather than an absence of one: the region is one the model already handles, and
the floors that were being met over a set which could not have told the difference
are now met over a set which can. The ten appear in the figures above as ten more
true negatives — `tn` 44 to 54 — and nowhere else. Both runs over the 108 cited on
this page answered all fifty-four negatives correctly, `fp 0` and `tn 54` in each,
so neither of them has yet seen the model get one of the ten wrong.

**The fill run's one miss is the case that was already unstable.** `ls-025` is a
substantive comment answered `insufficient`. That is the same answer the second of
the two 98-case runs gave it, and one of the two answers recorded for it below;
this run did not find a new defect, it found the old one again. It is the whole of
`fn 1`, and it moves recall rather than precision because an answer of
`insufficient` claims nothing. `lv-008`, the other mover of the 98-case pair, was
answered correctly here. The CI run over the 108 missed `ls-025` the same way and
missed one more, which is the pair recorded under "The floors" below.

**What a disagreement of that shape does not reach.** §3.3 treats `insufficient`
and `nonsense` identically for participation credit, so a case landing on the
wrong one of those two moves neither gated rate. The per-verdict figures are
recorded anyway, so a later ticket that wants to gate on the distinction has a
baseline; nothing enforces them today. **These three are derived from the counts
above rather than transcribed from the run's own report** — one disagreement, and
the run named which case it was, which fixes every cell: `substantive` p 1.000
r 0.9815, `insufficient` p 0.963 r 1.000, `nonsense` p 1.000 r 1.000. The whole of
the movement is `ls-025` landing in the `insufficient` column.

**The fill measurement over the 98-case composition, kept as history** — it is the
first of the two runs the variance figure comes from, and its per-verdict table is
what the `ls-025` correction below reads:

    positive class `substantive` (ADR 0119)
    precision 1.000000   tp 53  fp 0
    recall    0.981481   fn 1   tn 44
    exact agreement 96/98        95.3s wall, longest call 2.61s

    per verdict:  substantive  p 1.000  r 0.9815
                  insufficient p 1.000  r 0.9615
                  nonsense     p 0.900  r 1.0000

Both of that run's disagreements were the same mistake in the same direction — the
model reaching for `nonsense`. `ls-025` was a substantive comment called nonsense,
the one miss inside its recall figure; `lv-008` was an insufficient comment called
nonsense, which moved neither gated rate because both are negatives for the
positive class.

**The miss moved, and it moved the right way.** Under `validity.v1` on
`gpt-5-mini-2025-08-07` the miss was `ss-005` — twenty-four characters,
substantive, called nonsense — a case in the short-substantive family this set
exists to measure. That case is answered correctly now and the miss is a
long-substantive one instead. It is recorded because it is the kind of thing that
is invisible three months later.

**`ls-025` has been a miss in every Luna run, and it did not stay still.** An
earlier version of this paragraph held it up as the stable one — a model defect
rather than sampling — against `lv-008` as the variable one. A security re-check
read both CI logs and found that wrong. The fill run answered `nonsense` to both
cases, which the 98-case per-verdict table above corroborates on its own:
`nonsense` precision 0.900 is two false positives, and those two are them. The
second run answered `insufficient` to both, and both runs over the 108 answered
`insufficient` to `ls-025` and correctly to `lv-008`.

So both cases moved, and `ls-025` moved exactly as `lv-008` did. It stayed a miss
only because each of its answers was wrong — a substantive comment called
`nonsense` in the first run cited here and `insufficient` in each of the three
cited since, and recall cannot tell those apart. A
case can be unstable and still look fixed, if the instability happens below the
level the rate measures.

That is the sharpest thing these runs say, and it is the opposite of what the
first version of this paragraph claimed: **variance reaches a positive-class
case** — one of the 54 the recall figure is computed over. A run that answered
`substantive` there would move recall to 1.000 with nothing having changed, and
none of the runs whose per-case answers are recorded on this page has.

## The floors: precision 0.92, recall 0.90

Derived from the fill measurement's own counts by the three rules this file has
carried since the deferral. The arithmetic is written out because a reader meeting a red gate
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
standing estimate rather than being restated as two cases in a hundred and eight —
a number restated onto a denominator it was never taken over is the move a quietly
rewritten sentence makes.

**The two runs over the 108-case composition cited on this page**, both
`validity.v2` on `gpt-5.6-luna`:

    the fill measurement          p 1.0000  r 0.9815   tp 53  fp 0  fn 1  tn 54
                                  exact agreement 107/108      miss: ls-025
    CI run 33830242674 @ 3be69bb  p 1.0000  r 0.9630   tp 52  fp 0  fn 2  tn 54
                                                       misses: ls-025, ss-011

One case moved between them. `ls-025` did not: it was answered `insufficient` in
both, which is the third and fourth times it has been wrong in the runs cited
here. The mover is `ss-011` — answered correctly in the fill run and
`insufficient` in the CI run — and it is a short-substantive case, which is to say
one of the 54 the recall figure is computed over.

**This is the event rule 3's argument predicted.** Over the 98-case
pair, the argument for granting the variance allowance to each rate separately had
to be made from a case that moved *without* moving a rate: "a rate that did not
move is not a rate that cannot". Here one did. Recall was 0.9815 in the fill run
and 0.9630 in the CI run with nothing changed between them but the run, so the
allowance is no longer defended by an inference about what could happen — the
thing happened, on the gated rate, at this composition. Both runs clear both
floors with headroom: `fn 2` is two of the five total misses the recall floor
tolerates, and neither run made a false positive at all.

**The allowance does not move on this.** One observed mover sits inside the
standing two-case estimate rather than beyond it, so there is nothing here that a
re-derivation would change and no case for touching a floor value in this pull
request. Sizing the allowance over the 108-case composition — including whether
two runs are enough to size anything — is E10's revisit, and that is where a
re-derived figure belongs.

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
shape may keep the numbers it was measured with.

The run at the top of this page bears the derivation out rather than merely
agreeing with it: fifty-four negatives drew no false positive at all, so the whole
four-error budget is unspent over a set that offers ten more ways to spend it than
the set the number was chosen on.

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
        "Measured against validity.v2 on gpt-5.6-luna over the 108 cases in cases.py, in "
        "one clean run — a single run, not an average — where every case was answered by "
        "the model and none by §3.3's character floor: precision 1.000000 (tp 53, fp 0), "
        "recall 0.981481 (fn 1, tn 54), exact agreement 107/108, taken locally on "
        "2026-09-03. A second run over this composition — CI run 33830242674 on commit "
        "3be69bb, and those two are the runs over the 108 cited here — scored precision "
        "1.0000 (tp 52, fp 0) and recall 0.9630 (fn 2, tn 54): both clear both floors with "
        "headroom, since two misses is two of the five the recall floor tolerates and "
        "neither run made a false positive. One case moved between the two, ss-011, and it "
        "is a positive-class case, so this pair moved the gated rate itself — recall 0.9815 "
        "against 0.9630 with nothing changed but the run — which is the event rule 3's "
        "argument had to predict rather than exhibit until now. The allowance does not move "
        "on one observed mover inside a standing estimate of two; sizing it over this "
        "composition is E10's revisit. "
        "FIX-02 grew the set from 98 by adding ten fluent off-topic English "
        "comments to the nonsense family, and both runs say the group cost the measurement "
        "nothing: ns-019 through ns-028 were answered nonsense, ten out of ten, first pass, "
        "and every one of the 54 negatives was answered correctly in each run. "
        "All ten are negatives, so the positive class stays at 54 while the negatives go "
        "from 44 to 54 — ten more opportunities for a false positive under the same "
        "tolerance of four, none of them taken. The fill run's one miss is ls-025, a "
        "substantive comment answered insufficient, which is the answer it also gave in the "
        "second of the two runs over the 98-case composition and in the CI run above; it is "
        "an already-recorded unstable case rather than a new defect. The measured "
        "run-to-run variance is still two cases in "
        "ninety-eight, on this same model and this same prompt, from two independent runs "
        "over that earlier composition "
        "— the fill measurement at 96/98 exact agreement and CI run 33679136272 on commit "
        "5f6a927 at 97/98. The two runs over the 108 disagree on one case, which sits "
        "inside that standing estimate rather than replacing it, so the figure carries over "
        "with its provenance rather than being restated on the new denominator. "
        "Across those two runs both ls-025 and lv-008 answered nonsense in the first and "
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
        "known gap rather than an oversight."
    ),
)
