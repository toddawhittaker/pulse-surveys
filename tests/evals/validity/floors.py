"""The comment-validity precision and recall floors — E2-12.

**Measured, not estimated.** One clean run over the 98 cases in `cases.py`, valid
on the first pass: every case answered by `gpt-5-mini-2025-08-07` under
`validity.v1`, none stamped by §3.3's character floor, so nothing in the figures
below came from the twenty-five-character rule the set exists to beat. The
prompt-version pin voided two earlier runs that a slow provider had floored
(`docs/disputes/E2-12-06.md`); those produced no numbers and none of them are
here.

    positive class `substantive` (ADR 0119)
    precision 1.000000   tp 53  fp 0
    recall    0.981481   fn 1   tn 44
    exact agreement 96/98

    per verdict:  substantive  p 1.0000  r 0.9815  (n 54)
                  insufficient p 0.9630  r 1.0000  (n 26)
                  nonsense     p 0.9444  r 0.9444  (n 18)

**The floors are 0.95 and 0.94, and they are deliberately below what was
measured.** A floor written at the measurement fails on the first disagreement in
either direction — with 54 actual positives, one future false positive takes
precision to 0.9815 and one more miss takes recall to 0.9630 — so a floor at the
figures is a gate that goes red on ordinary movement and gets lowered the first
time it does. That is the shape
`.claude/review-fixtures/eval-floor-lowered.diff` is built to catch, and the way
to not need it is to leave the headroom now rather than argue for it later.

The headroom is stated as a count of errors, because that is what somebody
reading a red gate has to reason about:

    precision 0.95   53/(53+2) = 0.9636 passes, 53/(53+3) = 0.9464 fails
                     — two new false positives tolerated, the third fires
    recall    0.94   51/54 = 0.9444 passes, 50/54 = 0.9259 fails
                     — three total misses tolerated, the fourth fires; one is
                       the measured miss, so two new ones

**Two new errors of a kind is the line, and the reason is that one clean run sits
behind these numbers and no variance estimate across runs.** A single
disagreement is inside what one measurement cannot tell from noise; a second of
the same kind is a pattern, and this gate fires on prompt and model changes, which
is exactly when a pattern means something. If a later ticket runs the set enough
times to measure run-to-run variance, these are the numbers to revisit — upward,
with the variance quoted.

**Precision is held at least as tightly as recall, which is the opposite of the
threat task.** §3.3 validates synchronously: a student whose comment is judged
insufficient is told so at submit time, with coaching copy and a chance to
rewrite, so a false negative is visible to the person it affects and recoverable
by them. A false positive is not — participation credit awarded for "it was okay"
is silent, reaches §3.4's grade passback, and nobody ever sees it. SPEC §9.3 makes
recall the strictest floor for threat and self-harm because a false negative there
is a student in danger whose comment reached nobody; on this task the invisible
error is the other one.

**What these floors do not measure, said rather than implied.** Both are computed
about the `substantive` class, so a comment the model called `nonsense` where the
set says `insufficient` moves neither figure — and one of the two disagreements in
the measured run, `ns-015`, is exactly that. §3.3 treats the two identically for
participation credit, so the gate is blind to that distinction by design rather
than by oversight. The per-verdict figures above are recorded so that a later
ticket wanting to gate on it has a baseline; nothing enforces them today.

The other disagreement is `ss-005` — "Rubric fights the brief.", twenty-four
characters, substantive, answered `nonsense`. It is stable across rounds, so it is
a real model miss rather than sampling, and it sits in the short-substantive
family the set exists to measure. It is the one miss inside the recall figure
above, and it is worth knowing that the measured recall is not 1.0 because the
classifier misses a case of exactly the kind SPEC §11 question 4 is about.

**Moving these numbers is a deliberate pull request whose subject is moving
them** (`CLAUDE.md`). Lowering one to make a run pass is what the review fixture
plants, and a narrowed set is the same move wearing a costume —
`tests/unit/test_the_validity_eval_set_carries_the_cases_the_heuristic_gets_wrong.py`
holds the set's size and both class counts against that. That the gate *can* go
red is not taken on trust either: `tests/evals/validity/breach.py` is a set the
current prompt fails by construction, run through the real path on demand.
"""

from __future__ import annotations

from tests.evals.declarations import TaskFloors, enforced

FLOORS: TaskFloors = enforced(
    precision=0.95,
    recall=0.94,
    note=(
        "Measured against validity.v1 on gpt-5-mini-2025-08-07 over the 98 cases in "
        "cases.py, in one clean run where every case was answered by the model and none "
        "by §3.3's character floor: precision 1.000000 (tp 53, fp 0), recall 0.981481 "
        "(fn 1, tn 44). The floors sit below those figures on purpose — 0.95 tolerates "
        "two new false positives and fires on the third, 0.94 tolerates two new misses "
        "and fires on the third — because a floor written at a single measurement's own "
        "numbers goes red on the first ordinary disagreement and gets lowered the first "
        "time it does. Precision is held at least as tightly as recall because §3.3 "
        "validates at submit time: a false negative is shown to the student and "
        "recoverable, a false positive is silent credit that reaches §3.4's passback."
    ),
)
