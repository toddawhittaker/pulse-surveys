"""SPEC §9.3's eval sets, their per-task floors, and the runner CI calls — E2-12.

`python -m tests.evals.runner --enforce-floors` is the whole surface. It is the
only place in this repository that calls a paid provider, and it runs in exactly
three situations: on a pull request whose diff touches the AI surface, on a
`workflow_dispatch`, and locally through `make evals`.

**Why this lives under `tests/` rather than under `backend/`.** SPEC §7.4 makes
the eval fixtures the same typed contracts the tasks return, and SPEC §9.3 makes
the sets a testing artifact. `.github/workflows/ci.yml`'s `detect` job already
pins `tests/evals/runner.py` by that exact path, so the module name is settled
rather than chosen here.

**The layout.** One package per task, holding that task's cases and that task's
floor declaration side by side, so lowering a floor is a diff in the directory of
the set it governs rather than in a shared file nobody reads. `registry.py` joins
them and is what the runner walks.

  - `declarations.py` — the case, floor and result types every task shares.
  - `measure.py` — precision and recall over one task's answers.
  - `registry.py` — every task the runner knows about.
  - `runner.py` — the command line, the refusals, and the floor comparison.
  - `validity/` — SPEC §3.3's comment-validity task: a real set and a real floor
    slot.
  - `threat/` — SPEC §9.3's strictest floor. The slot exists with no set and no
    number, because setting it is E10's work; the runner reports it as deferred
    and never reports it as passing.
"""
