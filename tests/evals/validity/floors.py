"""The comment-validity precision and recall floors — measured on Luna under validity.v2.

One clean run over the 98 cases in `cases.py`, valid on the first pass: every case
answered by the model under `validity.v2`, none stamped by §3.3's character floor,
so nothing in the figures below came from the twenty-five-character rule the set
exists to beat.

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
long-substantive one instead. It is one run against one run, so it is an
observation rather than a result, and it is recorded because it is the kind of
thing that is invisible three months later.

## The floors: precision 0.94, recall 0.92

Derived from this run's own counts by the three rules this file has carried since
the deferral. The arithmetic is written out because a reader meeting a red gate
has to be able to check it.

**Rule 1 — two errors of a kind is the pattern threshold.** One new error is
inside what a single measurement cannot tell from noise; a second of the same kind
is a pattern, and this gate fires on prompt and model changes, which is exactly
when a pattern means something.

**Rule 3 — and the measured variance sits on top of that, not inside it.** Two
identical runs of this set against the same model and prompt disagree with each
other at about one case per hundred. That is not uncertainty about the model's
quality, it is the model: a rerun that changed nothing scores differently. So the
allowance is the pattern threshold *plus* the variance — two new errors of a kind,
plus one — and the floor fires on the fourth. A floor sized at the pattern
threshold alone would let ordinary variance spend half its headroom, so a single
real regression on top of a rerun would fire it; and a gate that goes red on
ordinary movement is a gate that gets lowered the first time it does.

The variance is granted to each rate independently, which is the conservative
reading: one disagreement per hundred is a count of disagreements, and nothing
says which rate a given one lands on, so each is sized as though it could take it.

    precision 0.94   53/(53+3) = 0.9464 passes — three false positives tolerated
                     53/(53+4) = 0.9298 fails  — the fourth fires
    recall    0.92   50/54     = 0.9259 passes — four total misses tolerated,
                                                 which is three new ones
                     49/54     = 0.9074 fails  — the fifth fires

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
floors tolerate the same number of *new* errors of their own kind — three — and
precision's is the numerically higher bar. It is not strictly tighter in error
count, and it should not be: the three comes from rules 1 and 3, which are
arithmetic rather than preference, and cutting precision's allowance to two would
mean ordinary variance plus one real false positive fires the gate. That is the
failure rule 1 exists to prevent, and buying a stricter-looking number with it
would be a bad trade.

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
    precision=0.94,
    recall=0.92,
    note=(
        "Measured against validity.v2 on gpt-5.6-luna over the 98 cases in cases.py, in "
        "one clean run — a single run, not an average — where every case was answered by "
        "the model and none by §3.3's character floor: precision 1.000000 (tp 53, fp 0), "
        "recall 0.981481 (fn 1, tn 44). The floors sit below those figures by the pattern "
        "threshold plus the measured variance: two new errors of a kind, plus one for the "
        "run-to-run disagreement of about one case per hundred observed between two "
        "identical runs of this set, giving three tolerated and the fourth firing. So "
        "precision 0.94 passes at 53/(53+3)=0.9464 and fails at 53/(53+4)=0.9298, and "
        "recall 0.92 passes at 50/54=0.9259 and fails at 49/54=0.9074. Precision is held "
        "at the numerically higher bar because §3.3 validates at submit time: a false "
        "negative is shown to the student and recoverable, a false positive is silent "
        "credit that reaches §3.4's passback. The model name pins no snapshot — no dated "
        "gpt-5.6-luna exists — so these figures do not fix a set of weights, and that is a "
        "known gap rather than an oversight."
    ),
)
